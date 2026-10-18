import threading
from types import SimpleNamespace

import pytest

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.core.usage import UsageProbe, probe

MOUNT = MountInfo("/dev/sdd1", "/mnt/backup", "ext4", False)


def fake(path):
    return SimpleNamespace(f_frsize=4096, f_blocks=1000, f_bfree=300, f_bavail=250)


def test_probe_computes_df_numbers():
    v = probe(MOUNT, fake)
    assert v == Volume(
        "/mnt/backup",
        "/mnt/backup",
        "ext4",
        False,
        "ok",
        total=4_096_000,
        used=2_867_200,
        free=1_024_000,
    )


def test_probe_passes_mount_point_to_statvfs():
    seen = []
    probe(MOUNT, lambda p: seen.append(p) or fake(p))
    assert seen == ["/mnt/backup"]


@pytest.mark.parametrize("exc", [FileNotFoundError, PermissionError, OSError])
def test_probe_oserror_is_unavailable(exc):
    def boom(path):
        raise exc("gone")

    v = probe(MOUNT, boom)
    assert (v.status, v.total, v.used, v.free) == ("unavailable", None, None, None)
    assert v.mount_point == "/mnt/backup" and v.label == "/mnt/backup"


def test_probe_all_one_result_per_mount():
    mounts = [MountInfo(f"/dev/sd{c}1", f"/mnt/{c}", "ext4", False) for c in "abc"]
    results, lock = [], threading.Lock()

    def collect(v):
        with lock:
            results.append(v)

    threads = UsageProbe(fake).probe_all(mounts, collect)
    for t in threads:
        t.join(timeout=5)
    assert len(threads) == 3
    assert sorted(v.mount_point for v in results) == ["/mnt/a", "/mnt/b", "/mnt/c"]
    assert all(v.status == "ok" for v in results)


def test_probe_all_threads_are_daemon_and_do_not_block_caller():
    release = threading.Event()

    def stuck(path):
        release.wait(5)
        return fake(path)

    threads = UsageProbe(stuck).probe_all([MOUNT], lambda v: None)
    assert all(t.daemon for t in threads)
    assert threads[0].is_alive()  # probe_all returned while statvfs is still blocked
    release.set()
    threads[0].join(timeout=5)


def test_probe_all_empty():
    assert UsageProbe(fake).probe_all([], lambda v: None) == []


A = MountInfo("/dev/sda1", "/mnt/a", "ext4", False)
B = MountInfo("/dev/sdb1", "/mnt/b", "ext4", False)


def blocking():
    """Fake statvfs that parks until the returned Event is set."""
    release = threading.Event()

    def statvfs(path):
        release.wait(5)
        return fake(path)

    return statvfs, release


def test_probe_all_skips_busy_mount_but_probes_others():
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    [first] = p.probe_all([A], lambda v: None)
    second = p.probe_all([A, B], lambda v: None)
    assert len(second) == 1  # only B started
    release.set()
    first.join(5)
    second[0].join(5)


def test_probe_all_mount_eligible_again_after_probe_returns():
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    [t] = p.probe_all([A], lambda v: None)
    release.set()
    t.join(5)
    again = p.probe_all([A], lambda v: None)
    assert len(again) == 1
    again[0].join(5)


def test_probe_all_duplicate_mount_points_start_one_thread():
    statvfs, release = blocking()
    threads = UsageProbe(statvfs).probe_all([A, A], lambda v: None)
    assert len(threads) == 1
    release.set()
    threads[0].join(5)


def test_stuck_mount_costs_one_thread_over_many_polls():
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    started = [t for _ in range(5) for t in p.probe_all([A], lambda v: None)]
    assert len(started) == 1
    release.set()
    started[0].join(5)


def collect_hook(monkeypatch):
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda args: seen.append(args.exc_type))
    return seen


def test_non_oserror_in_statvfs_frees_mount(monkeypatch):
    seen = collect_hook(monkeypatch)

    def boom(path):
        raise RuntimeError("bug")

    p = UsageProbe(boom)
    [t] = p.probe_all([A], lambda v: None)
    t.join(5)
    assert seen == [RuntimeError]
    again = p.probe_all([A], lambda v: None)  # eligible again
    assert len(again) == 1
    again[0].join(5)


def test_raising_on_result_frees_mount(monkeypatch):
    seen = collect_hook(monkeypatch)

    def bad(v):
        raise ValueError("callback")

    p = UsageProbe(fake)
    [t] = p.probe_all([A], bad)
    t.join(5)
    assert seen == [ValueError]
    [t2] = p.probe_all([A], lambda v: None)
    t2.join(5)


def test_thread_start_failure_frees_mount_and_reraises(monkeypatch):
    p = UsageProbe(fake)
    with monkeypatch.context() as m:

        def no_start(self):
            raise RuntimeError("can't start new thread")

        m.setattr(threading.Thread, "start", no_start)
        with pytest.raises(RuntimeError):
            p.probe_all([A], lambda v: None)
    [t] = p.probe_all([A], lambda v: None)
    t.join(5)
