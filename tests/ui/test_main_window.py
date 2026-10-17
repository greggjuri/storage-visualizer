import threading

from PySide6.QtWidgets import QLabel

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.ui.bridge import ResultBridge
from storage_visualizer.ui.main_window import MainWindow

MOUNTS = [
    MountInfo("/dev/a1", "/", "ext4", False),
    MountInfo("/dev/b1", "/mnt/backup", "ext4", False),
]
VOL = Volume("/mnt/backup", "/mnt/backup", "ext4", False, "ok", 100, 40, 60)


def test_window_has_one_pie_per_mount(qtbot):
    w = MainWindow(MOUNTS)
    qtbot.addWidget(w)
    assert list(w.pies) == ["/", "/mnt/backup"]
    assert w.windowTitle() == "Storage"


def test_update_volume_targets_matching_pie(qtbot):
    w = MainWindow(MOUNTS)
    qtbot.addWidget(w)
    w.update_volume(VOL)
    assert w.pies["/mnt/backup"].volume == VOL
    assert w.pies["/"].volume is None


def test_update_volume_ignores_unknown_mount(qtbot):
    w = MainWindow(MOUNTS)
    qtbot.addWidget(w)
    w.update_volume(Volume("/nope", "/nope", "ext4", False, "ok", 1, 0, 1))
    assert all(p.volume is None for p in w.pies.values())


def test_empty_window_shows_message(qtbot):
    w = MainWindow([])
    qtbot.addWidget(w)
    assert w.pies == {}
    assert w.findChild(QLabel).text() == "No volumes found"


def test_bridge_delivers_from_worker_thread(qtbot):
    w = MainWindow(MOUNTS)
    qtbot.addWidget(w)
    bridge = ResultBridge()
    bridge.volume_ready.connect(w.update_volume)
    t = threading.Thread(target=bridge.volume_ready.emit, args=(VOL,))
    t.start()
    t.join()
    # Queued delivery: nothing is applied until the event loop runs.
    assert w.pies["/mnt/backup"].volume is None
    qtbot.waitUntil(lambda: w.pies["/mnt/backup"].volume == VOL, timeout=2000)
