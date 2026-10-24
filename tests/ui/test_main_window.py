import threading

from PySide6.QtWidgets import QApplication, QLabel

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.ui.bridge import ResultBridge
from storage_visualizer.ui.main_window import MainWindow

MOUNTS = [
    MountInfo("/dev/a1", "/", "ext4", False),
    MountInfo("/dev/b1", "/mnt/backup", "ext4", False),
]
VOL = Volume("/mnt/backup", "/mnt/backup", "ext4", False, "ok", 100, 40, 60)


def test_window_has_one_pie_per_mount(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts(MOUNTS)
    assert list(w.pies) == ["/", "/mnt/backup"]
    assert w.windowTitle() == "Storage"


def test_update_volume_targets_matching_pie(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts(MOUNTS)
    w.update_volume(VOL)
    assert w.pies["/mnt/backup"].volume == VOL
    assert w.pies["/"].volume is None


def test_update_volume_ignores_unknown_mount(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts(MOUNTS)
    w.update_volume(Volume("/nope", "/nope", "ext4", False, "ok", 1, 0, 1))
    assert all(p.volume is None for p in w.pies.values())


def test_empty_window_shows_message(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.pies == {}
    assert w.findChild(QLabel).text() == "No volumes found"


def test_bridge_delivers_from_worker_thread(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts(MOUNTS)
    bridge = ResultBridge()
    bridge.volume_ready.connect(w.update_volume)
    t = threading.Thread(target=bridge.volume_ready.emit, args=(VOL,))
    t.start()
    t.join()
    # Queued delivery: nothing is applied until the event loop runs.
    assert w.pies["/mnt/backup"].volume is None
    qtbot.waitUntil(lambda: w.pies["/mnt/backup"].volume == VOL, timeout=2000)


def mi(mp):
    return MountInfo("/dev/x" + mp, mp, "ext4", False)


def layout_order(w):
    """Mount points of the pies in layout order, then 'label' for the empty label."""
    by_id = {id(p): mp for mp, p in w.pies.items()}  # PieWidget has no public mount-point accessor
    lay = w.layout()
    widgets = [lay.itemAt(i).widget() for i in range(lay.count())]
    return ["label" if isinstance(x, QLabel) else by_id[id(x)] for x in widgets]


def test_added_pie_goes_in_sorted_position(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/home")])
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert layout_order(w) == ["/", "/data", "/home", "label"]


def test_removed_pie_goes_and_survivors_keep_volume(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    root, home = w.pies["/"], w.pies["/home"]
    vol = Volume("/", "/", "ext4", False, "ok", 100, 40, 60)
    w.update_volume(vol)
    w.set_mounts([mi("/"), mi("/home")])
    assert list(w.pies) == ["/", "/home"]
    assert layout_order(w) == ["/", "/home", "label"]
    assert w.pies["/"] is root and w.pies["/home"] is home and root.volume == vol


def test_empty_label_tracks_pies(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    label = w.findChild(QLabel)
    assert not label.isHidden()
    w.set_mounts([mi("/")])
    assert label.isHidden()
    w.set_mounts([])
    assert not label.isHidden()


def test_late_result_for_removed_mount_is_ignored(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data")])
    w.set_mounts([mi("/")])
    w.update_volume(Volume("/data", "/data", "ext4", False, "ok", 1, 0, 1))
    assert list(w.pies) == ["/"]


def test_unchanged_mounts_keep_same_pies(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/home")])
    before = dict(w.pies)
    w.set_mounts([mi("/"), mi("/home")])
    assert all(w.pies[k] is before[k] for k in before)


def test_readded_mount_gets_fresh_loading_pie(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/usb")])
    old = w.pies["/usb"]
    w.update_volume(Volume("/usb", "/usb", "vfat", False, "ok", 10, 5, 5))
    w.set_mounts([mi("/")])
    w.set_mounts([mi("/"), mi("/usb")])
    assert w.pies["/usb"] is not old and w.pies["/usb"].volume is None
    assert layout_order(w) == ["/", "/usb", "label"]


def test_insert_order_matches_sorted_for_awkward_paths(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    paths = ["/mnt/ab", "/mnt/a/b", "/mnt/a b", "/mnt/a", "/"]
    for i in range(1, len(paths) + 1):
        w.set_mounts([mi(p) for p in paths[:i]])
    assert layout_order(w) == sorted(paths) + ["label"]


def test_removed_pie_is_hidden_before_deferred_delete(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.set_mounts([mi("/"), mi("/data")])
    QApplication.processEvents()  # let the deferred show of the new pies run
    old = w.pies["/data"]
    assert old.isVisible()
    w.set_mounts([mi("/")])
    assert not old.isVisible()  # no event loop turn yet: deleteLater has not run


def test_new_pie_gets_mount_label(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([MountInfo("/dev/sda2", "/mnt/hoepsis", "ntfs3", False, "Hoepsis")])
    assert w.pies["/mnt/hoepsis"].label == "Hoepsis"


def metrics(w):
    lay = w.layout()
    m = lay.contentsMargins()
    pie = next(iter(w.pies.values()))
    return pie.width(), pie.height(), max(0, lay.spacing()), m


def width_for(w, per_row):
    pw, _, sp, m = metrics(w)
    return m.left() + m.right() + per_row * pw + (per_row - 1) * sp


def height_for(w, rows):
    _, ph, sp, m = metrics(w)
    return m.top() + m.bottom() + rows * ph + (rows - 1) * sp


def shown_window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


def test_width_kept_and_height_refits_on_add_and_remove(qtbot):
    w = shown_window(qtbot)
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 2), w.height())
    width = w.width()
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert w.width() == width and w.height() == height_for(w, 2)
    w.set_mounts([mi("/"), mi("/home")])  # removed pie hidden, deleteLater not run yet
    assert w.width() == width and w.height() == height_for(w, 1)


def test_width_change_refits_height(qtbot):
    w = shown_window(qtbot)
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    w.resize(width_for(w, 1), w.height())
    assert w.height() == height_for(w, 3)


def test_width_never_below_one_pie(qtbot):
    w = shown_window(qtbot)
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(10, w.height())
    assert w.width() == width_for(w, 1) and w.height() == height_for(w, 2)


def test_clamp_wins_over_stale_height(qtbot):  # offscreen stand-in for a KWin-restored size
    w = shown_window(qtbot)
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 2), 2000)
    assert w.height() == height_for(w, 1)


def test_first_show_keeps_one_row_width(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])  # before show(), as main() does
    w.show()
    assert w.width() == width_for(w, 3) and w.height() == height_for(w, 1)


def test_first_launch_width_capped_at_screen(qtbot, monkeypatch):
    w = MainWindow()
    qtbot.addWidget(w)
    w.set_mounts([mi("/")])
    monkeypatch.setattr(w, "_available_width", lambda: width_for(w, 2))
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    w.show()
    assert w.width() == width_for(w, 2) and w.height() == height_for(w, 2)


def test_width_kept_on_mount_change_while_hidden(qtbot):
    w = shown_window(qtbot)
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 1), w.height())
    w.hide()
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert w.width() == width_for(w, 1) and w.height() == height_for(w, 3)
