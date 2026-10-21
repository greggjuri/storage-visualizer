from collections.abc import Iterable
from typing import Any

import psutil

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


def enumerate_mounts(partitions: Iterable[Any]) -> list[MountInfo]:
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
    mounts = [
        MountInfo(p.device, p.mountpoint, p.fstype, p.fstype in NETWORK_FSTYPES)
        for p in best.values()
    ]
    return sorted(mounts, key=lambda m: m.mount_point)


def enumerate_system_mounts() -> list[MountInfo]:
    return enumerate_mounts(psutil.disk_partitions(all=True))  # all=True: ADR-003
