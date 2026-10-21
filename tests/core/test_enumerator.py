from collections import namedtuple

import pytest

from storage_visualizer.core import enumerator
from storage_visualizer.core.enumerator import enumerate_mounts
from storage_visualizer.core.labels import network_label
from storage_visualizer.core.models import MountInfo

Part = namedtuple("Part", "device mountpoint fstype opts")


def mps(parts):
    return [m.mount_point for m in enumerate_mounts(parts, {})]


def test_keeps_dev_block_filesystems():
    parts = [
        Part("/dev/nvme0n1p4", "/", "ext4", ""),
        Part("/dev/sdb1", "/data", "btrfs", ""),
        Part("/dev/sdc1", "/run/media/juri/USB", "vfat", ""),
    ]
    assert mps(parts) == ["/", "/data", "/run/media/juri/USB"]


def test_result_fields():
    [m] = enumerate_mounts([Part("/dev/sdd1", "/mnt/backup", "ext4", "")], {})
    assert m == MountInfo("/dev/sdd1", "/mnt/backup", "ext4", False, "backup")


@pytest.mark.parametrize(
    "device,fstype,label",
    [
        ("server:/export", "nfs", "export"),
        ("server:/export", "nfs4", "export"),
        ("//nas/share", "cifs", "share"),
        ("//nas/share", "smb3", "share"),
        ("user@host:/", "fuse.sshfs", "net"),
    ],
)
def test_keeps_network_filesystems_flagged(device, fstype, label):
    [m] = enumerate_mounts([Part(device, "/mnt/net", fstype, "")], {})
    assert m == MountInfo(device, "/mnt/net", fstype, True, label)
    assert m.label == network_label(device, "/mnt/net")


def test_local_mounts_not_flagged_network():
    [m] = enumerate_mounts([Part("/dev/sdd1", "/mnt/backup", "ext4", "")], {})
    assert m.is_network is False


@pytest.mark.parametrize(
    "device,fstype",
    [("portal", "fuse.portal"), ("gvfsd-fuse", "fuse.gvfsd-fuse"), ("tmpfs", "tmpfs")],
)
def test_drops_other_non_dev_devices(device, fstype):
    assert mps([Part(device, "/mnt/x", fstype, "")]) == []


def test_network_mounts_respect_system_trees():
    assert mps([Part("server:/export", "/run/user/1000/x", "nfs", "")]) == []


def test_network_mounts_dedupe_by_device():
    parts = [
        Part("server:/export", "/mnt/nfs/deep", "nfs", ""),
        Part("server:/export", "/mnt/nfs", "nfs", ""),
    ]
    assert mps(parts) == ["/mnt/nfs"]


def test_two_exports_from_one_server_are_two_mounts():
    parts = [
        Part("192.168.1.184:/volume1/media", "/mnt/nas-media", "nfs", ""),
        Part("192.168.1.184:/volume2/media-4k", "/mnt/nas-media-4k", "nfs", ""),
    ]
    assert mps(parts) == ["/mnt/nas-media", "/mnt/nas-media-4k"]


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


def test_local_label_from_mapping():
    [m] = enumerate_mounts(
        [Part("/dev/sda2", "/mnt/hoepsis", "ntfs3", "")], {"/dev/sda2": "Hoepsis"}
    )
    assert m.label == "Hoepsis"


def test_root_is_system_despite_mapping():
    [m] = enumerate_mounts([Part("/dev/nvme0n1p4", "/", "ext4", "")], {"/dev/nvme0n1p4": "debian"})
    assert m.label == "System"


def test_network_label_on_mount():
    [m] = enumerate_mounts([Part("//192.168.1.11/mansion", "/mnt/nas", "cifs", "")], {})
    assert m.label == "mansion"


def test_label_fallback_uses_kept_mount_point():
    parts = [
        Part("/dev/sda2", "/srv/data/deep", "btrfs", ""),
        Part("/dev/sda2", "/srv/data", "btrfs", ""),
    ]
    [m] = enumerate_mounts(parts, {})
    assert (m.mount_point, m.label) == ("/srv/data", "data")


def test_enumerate_system_mounts_uses_all_true_and_reads_labels(monkeypatch):
    calls = []
    seen = []

    def fake_partitions(all):
        calls.append(all)
        return [
            Part("/dev/sda1", "/", "ext4", ""),
            Part("tmpfs", "/tmp", "tmpfs", ""),
            Part("//nas/share", "/mnt/nas", "cifs", ""),
            Part("/dev/sdb1", "/mnt/data", "ext4", ""),
        ]

    def fake_labels(devices):
        seen.append(list(devices))
        return {"/dev/sda1": "root-fs", "/dev/sdb1": "Data"}

    monkeypatch.setattr(enumerator.psutil, "disk_partitions", fake_partitions)
    monkeypatch.setattr(enumerator, "read_device_labels", fake_labels)
    result = enumerator.enumerate_system_mounts()
    assert calls == [True]
    assert seen == [["/dev/sda1", "/dev/sdb1"]]
    assert [m.label for m in result] == ["System", "Data", "share"]
