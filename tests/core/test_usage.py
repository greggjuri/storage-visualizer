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
