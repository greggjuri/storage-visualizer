import faulthandler
import threading
from types import SimpleNamespace

from PySide6.QtWidgets import QLabel

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.core.usage import UsageProbe, unavailable
from storage_visualizer.ui import refresher
from storage_visualizer.ui.bridge import ResultBridge
from storage_visualizer.ui.main_window import MainWindow
from storage_visualizer.ui.refresher import INTERVAL_MS, Refresher

M = [MountInfo("/dev/a1", "/", "ext4", False)]


class FakeWindow:
    def __init__(self, log):
        self.log = log

    def set_mounts(self, mounts):
        self.log.append(("set_mounts", list(mounts)))


class FakeProbe:
    def __init__(self, log, volumes=()):
        self.log, self.volumes = log, volumes

    def probe_all(self, mounts, on_result):
        self.log.append(("probe_all", list(mounts)))
        for v in self.volumes:
            on_result(v)  # synchronous, on the UI thread
        return []

    def close(self):
        self.log.append(("close",))


def test_interval_and_timeout_wired_to_refresh(qtbot):
    calls = []
    r = Refresher(
        FakeWindow([]), ResultBridge(), FakeProbe([]), enumerate_fn=lambda: calls.append(1) or M
    )
    assert r.timer.interval() == 30_000 == INTERVAL_MS
    r.timer.timeout.emit()
    assert calls == [1]


def test_refresh_sets_mounts_before_probing(qtbot):
    log, bridge = [], ResultBridge()
    vol = Volume("/", "/", "ext4", False, "ok", 100, 40, 60)
    r = Refresher(FakeWindow(log), bridge, FakeProbe(log, [vol]), enumerate_fn=lambda: M)
    with qtbot.waitSignal(bridge.volume_ready) as sig:
        r.refresh()
    assert log == [("set_mounts", M), ("probe_all", M)]
    assert sig.args == [vol]  # on_result is the bridge's emit


def test_two_refreshes_add_and_remove_pies(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    bridge = ResultBridge()
    bridge.volume_ready.connect(w.update_volume)
    lists = iter([M, [MountInfo("/dev/b1", "/usb", "vfat", False)]])
    vol = Volume("/usb", "/usb", "vfat", False, "ok", 10, 5, 5)
    probe = FakeProbe([])
    r = Refresher(w, bridge, probe, enumerate_fn=lambda: next(lists))
    r.refresh()
    assert list(w.pies) == ["/"]
    probe.volumes = [vol]
    r.refresh()
    assert list(w.pies) == ["/usb"] and w.pies["/usb"].volume == vol


def test_start_refreshes_once_and_starts_timer(qtbot):
    calls = []
    r = Refresher(
        FakeWindow([]), ResultBridge(), FakeProbe([]), enumerate_fn=lambda: calls.append(1) or M
    )
    r.start()
    assert calls == [1] and r.timer.isActive()
    r.timer.stop()


def test_default_probe_built_once(qtbot, monkeypatch):
    built = []

    class CountingProbe:
        def __init__(self):
            built.append(1)

        def probe_all(self, mounts, on_result):
            return []

    monkeypatch.setattr(refresher, "UsageProbe", CountingProbe)
    r = refresher.Refresher(FakeWindow([]), ResultBridge(), enumerate_fn=lambda: M)
    r.refresh()
    r.refresh()
    assert built == [1]


def test_empty_enumeration_clears_window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    log = []
    lists = iter([M, []])
    r = Refresher(w, ResultBridge(), FakeProbe(log), enumerate_fn=lambda: next(lists))
    r.refresh()
    r.refresh()
    assert w.pies == {} and not w.findChild(QLabel).isHidden()
    assert log[-1] == ("probe_all", [])


def test_stop_stops_timer_and_closes_probe(qtbot):
    log = []
    r = Refresher(FakeWindow(log), ResultBridge(), FakeProbe(log), enumerate_fn=lambda: M)
    r.start()
    r.stop()
    assert not r.timer.isActive() and log[-1] == ("close",)
    r.stop()  # idempotent


NET = MountInfo("server:/export", "/mnt/net", "nfs", True)


def test_busy_share_unavailable_then_recovers_through_real_bridge(qtbot):
    faulthandler.dump_traceback_later(15, exit=True)  # a deadlock kills the run with a stack dump
    release = threading.Event()

    def statvfs(path):
        release.wait(5)
        return SimpleNamespace(f_frsize=4096, f_blocks=1000, f_bfree=300, f_bavail=250)

    w = MainWindow()
    qtbot.addWidget(w)
    bridge = ResultBridge()
    bridge.volume_ready.connect(w.update_volume)
    r = Refresher(w, bridge, UsageProbe(statvfs), enumerate_fn=lambda: [NET])
    try:
        r.refresh()  # worker parks in statvfs
        r.refresh()  # busy: unavailable delivered directly, under the probe lock
        assert w.pies["/mnt/net"].volume == unavailable(NET)
        release.set()
        qtbot.waitUntil(lambda: w.pies["/mnt/net"].volume.status == "ok", timeout=5000)
    finally:
        release.set()
        r.stop()  # a failed assertion must not leave the worker emitting on a deleted bridge
        faulthandler.cancel_dump_traceback_later()
