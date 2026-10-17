from types import SimpleNamespace

import pytest

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.core.usage import probe

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
