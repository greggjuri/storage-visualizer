import errno
import threading
from types import SimpleNamespace

import pytest

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.core.usage import UsageProbe, probe, unavailable

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


def test_unavailable_matches_probe_oserror():
    def boom(path):
        raise OSError("gone")

    assert unavailable(MOUNT) == probe(MOUNT, boom)


def test_errno_oserror_is_unavailable_and_mount_reprobed():
    def stale(path):
        raise OSError(errno.ESTALE, "Stale file handle")

    p, results = UsageProbe(stale), []
    [t] = p.probe_all([A], results.append)
    t.join(5)
    assert results == [unavailable(A)]
    [t2] = p.probe_all([A], results.append)
    t2.join(5)


def test_busy_mount_reports_unavailable_and_probes_others():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [first] = p.probe_all([A], results.append)
    second = p.probe_all([A, B], results.append)
    assert results == [unavailable(A)]  # synchronous: reported before probe_all returned
    assert len(second) == 1  # only B started
    release.set()
    first.join(5)
    second[0].join(5)


def test_late_result_recovers_and_mount_is_probed_again():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [first] = p.probe_all([A], results.append)
    p.probe_all([A], results.append)
    release.set()
    first.join(5)
    assert [v.status for v in results] == ["unavailable", "ok"]
    [again] = p.probe_all([A], results.append)
    again.join(5)


def test_fresh_result_is_never_followed_by_stale_unavailable():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    in_cb, go = threading.Event(), threading.Event()

    def cb(v):
        results.append(v)
        if not in_cb.is_set():
            in_cb.set()
            go.wait(5)  # worker parks inside on_result, holding the lock

    [worker] = p.probe_all([A], cb)
    release.set()
    assert in_cb.wait(5)
    started, ticking = [], threading.Event()

    def tick_body():
        ticking.set()
        started.extend(p.probe_all([A], cb))

    tick = threading.Thread(target=tick_body)
    tick.start()
    assert ticking.wait(5)
    tick.join(0.2)
    assert tick.is_alive()  # busy check waits for the worker's delivery
    go.set()
    tick.join(5)
    worker.join(5)
    for t in started:
        t.join(5)
    assert [v.status for v in results] == ["ok", "ok"]  # mount was idle: fresh probe


def test_close_suppresses_late_results_and_new_probes():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [t] = p.probe_all([A], results.append)
    p.close()
    release.set()
    t.join(5)
    assert results == []
    assert p.probe_all([A, B], results.append) == []
    assert results == []


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
    results = []
    threads = UsageProbe(statvfs).probe_all([A, A], results.append)
    assert len(threads) == 1
    assert results == []  # overmount duplicate: skipped silently, no unavailable flicker
    release.set()
    threads[0].join(5)


def test_mount_busy_from_previous_tick_reports_unavailable_once_when_duplicated():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [first] = p.probe_all([A], results.append)
    assert p.probe_all([A, A], results.append) == []  # still busy: no new thread
    assert results == [unavailable(A)]  # reported once, duplicate skipped
    release.set()
    first.join(5)


def test_stuck_mount_costs_one_thread_over_many_polls():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    started = [t for _ in range(5) for t in p.probe_all([A], results.append)]
    assert len(started) == 1
    assert results == [unavailable(A)] * 4
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
