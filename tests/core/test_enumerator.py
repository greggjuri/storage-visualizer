from collections import namedtuple

import pytest

from storage_visualizer.core.enumerator import enumerate_mounts
from storage_visualizer.core.models import MountInfo

Part = namedtuple("Part", "device mountpoint fstype opts")


def mps(parts):
    return [m.mount_point for m in enumerate_mounts(parts)]


def test_keeps_dev_block_filesystems():
    parts = [
        Part("/dev/nvme0n1p4", "/", "ext4", ""),
        Part("/dev/sdb1", "/data", "btrfs", ""),
        Part("/dev/sdc1", "/run/media/juri/USB", "vfat", ""),
    ]
    assert mps(parts) == ["/", "/data", "/run/media/juri/USB"]


def test_result_fields():
    [m] = enumerate_mounts([Part("/dev/sdd1", "/mnt/backup", "ext4", "")])
    assert m == MountInfo("/dev/sdd1", "/mnt/backup", "ext4", False)


def test_drops_non_dev_devices_including_network():
    parts = [
        Part("server:/export", "/mnt/nfs", "nfs4", ""),
        Part("//nas/share", "/mnt/smb", "cifs", ""),
        Part("tmpfs", "/tmp", "tmpfs", ""),
    ]
    assert mps(parts) == []


def test_drops_loop_devices():
    assert mps([Part("/dev/loop0", "/mnt/img", "ext4", "")]) == []


@pytest.mark.parametrize("fstype", ["tmpfs", "devtmpfs", "overlay", "squashfs", "efivarfs", "proc"])
def test_drops_pseudo_fstypes(fstype):
    assert mps([Part("/dev/x1", "/mnt/x", fstype, "")]) == []


@pytest.mark.parametrize(
    "mp",
    [
        "/boot",
        "/boot/efi",
        "/snap/core/1",
        "/sys/x",
        "/proc/x",
        "/run",
        "/run/user/1000",
        "/run/mediafoo",
    ],
)
def test_drops_system_trees(mp):
    assert mps([Part("/dev/x1", mp, "ext4", "")]) == []


@pytest.mark.parametrize(
    "mp",
    [
        "/run/media",
        "/run/media/juri/Disk",
        "/bootstrap",
        "/runner",
        "/run/media/juri/My Passport Ultra 2TB",
    ],
)
def test_keeps_component_lookalikes_and_run_media(mp):
    assert mps([Part("/dev/x1", mp, "ext4", "")]) == [mp]


def test_dedupe_keeps_shortest_mount_point():
    parts = [Part("/dev/sda2", "/home", "btrfs", ""), Part("/dev/sda2", "/", "btrfs", "")]
    assert mps(parts) == ["/"]


def test_dedupe_tie_breaks_lexicographically():
    parts = [Part("/dev/sda2", "/mnt/b", "ext4", ""), Part("/dev/sda2", "/mnt/a", "ext4", "")]
    assert mps(parts) == ["/mnt/a"]


def test_output_sorted_by_mount_point():
    parts = [Part("/dev/b", "/z", "ext4", ""), Part("/dev/a", "/a", "ext4", "")]
    assert mps(parts) == ["/a", "/z"]
