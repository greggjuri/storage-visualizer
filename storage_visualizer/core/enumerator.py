from collections.abc import Iterable, Mapping
from typing import Any

import psutil

from storage_visualizer.core.labels import local_label, network_label, read_device_labels
from storage_visualizer.core.models import MountInfo

PSEUDO_FSTYPES = frozenset(
    {
        "tmpfs",
        "devtmpfs",
        "proc",
        "sysfs",
        "overlay",
        "squashfs",
        "efivarfs",
        "cgroup",
        "cgroup2",
        "devpts",
        "mqueue",
        "debugfs",
        "tracefs",
        "securityfs",
        "pstore",
        "bpf",
        "configfs",
        "fusectl",
        "hugetlbfs",
        "autofs",
        "binfmt_misc",
        "ramfs",
        "nsfs",
    }
)
NETWORK_FSTYPES = frozenset({"nfs", "nfs4", "cifs", "smb3", "fuse.sshfs"})  # ADR-003
SYSTEM_TREES = ("/boot", "/snap", "/sys", "/proc", "/run")
SYSTEM_TREE_EXCEPTIONS = ("/run/media",)


def _is_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def _is_system_mount(mount_point: str) -> bool:
    if any(_is_under(mount_point, root) for root in SYSTEM_TREE_EXCEPTIONS):
        return False
    return any(_is_under(mount_point, root) for root in SYSTEM_TREES)


def enumerate_mounts(partitions: Iterable[Any], labels: Mapping[str, str]) -> list[MountInfo]:
    best: dict[str, Any] = {}
    for part in partitions:
        if part.fstype not in NETWORK_FSTYPES:
            if not part.device.startswith("/dev/"):
                continue
            if part.device.startswith("/dev/loop"):
                continue
        if part.fstype in PSEUDO_FSTYPES:
            continue
        if _is_system_mount(part.mountpoint):
            continue
        current = best.get(part.device)
        key = (len(part.mountpoint), part.mountpoint)
        if current is None or key < (len(current.mountpoint), current.mountpoint):
            best[part.device] = part
    mounts = [_mount_info(p, labels) for p in best.values()]
    return sorted(mounts, key=lambda m: m.mount_point)


def _mount_info(part: Any, labels: Mapping[str, str]) -> MountInfo:
    is_network = part.fstype in NETWORK_FSTYPES
    if is_network:
        label = network_label(part.device, part.mountpoint)
    else:
        label = local_label(part.mountpoint, labels.get(part.device))
    return MountInfo(part.device, part.mountpoint, part.fstype, is_network, label)


def enumerate_system_mounts() -> list[MountInfo]:
    parts = psutil.disk_partitions(all=True)  # all=True: ADR-003
    labels = read_device_labels([p.device for p in parts if p.device.startswith("/dev/")])
    return enumerate_mounts(parts, labels)
