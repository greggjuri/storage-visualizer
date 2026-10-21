import os
import posixpath
import re
from collections.abc import Iterable

_UDEV_ESCAPE = re.compile(rb"\\x([0-9a-fA-F]{2})")


def _basename(mount_point: str) -> str:
    return posixpath.basename(mount_point.rstrip("/"))


def network_label(device: str, mount_point: str) -> str:
    """Last path component of the share (CIFS `//host/a/b`, NFS/sshfs `host:/a/b`)."""
    if device.startswith("//"):
        rest = device[2:].partition("/")[2]
    else:
        rest = device.partition(":")[2]
    return posixpath.basename(rest.rstrip("/")) or _basename(mount_point)


def local_label(mount_point: str, by_label_name: str | None) -> str:
    if mount_point == "/":
        return "System"
    return by_label_name or _basename(mount_point)


def decode_udev(name: str) -> str:
    """Decode udev's `\\xNN` escapes in a /dev/disk/by-label entry name."""
    raw = _UDEV_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), name.encode("utf-8"))
    return raw.decode("utf-8", errors="replace")


def read_device_labels(
    devices: Iterable[str], by_label_dir: str = "/dev/disk/by-label"
) -> dict[str, str]:
    """Map each labelled device to its filesystem label; unlabelled devices are omitted."""
    try:
        names = os.listdir(by_label_dir)
    except OSError:
        return {}
    by_real = {
        os.path.realpath(os.path.join(by_label_dir, name)): decode_udev(name) for name in names
    }
    return {d: by_real[os.path.realpath(d)] for d in devices if os.path.realpath(d) in by_real}
