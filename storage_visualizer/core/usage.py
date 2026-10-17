import os
from collections.abc import Callable
from typing import Any

from storage_visualizer.core.models import MountInfo, Volume


def probe(mount: MountInfo, statvfs: Callable[[str], Any] = os.statvfs) -> Volume:
    """Probe one mount's usage; numbers match df (used vs Avail)."""
    base = (mount.mount_point, mount.mount_point, mount.fstype, mount.is_network)
    try:
        st = statvfs(mount.mount_point)
    except OSError:
        return Volume(*base, "unavailable", None, None, None)
    return Volume(
        *base,
        "ok",
        total=st.f_blocks * st.f_frsize,
        used=(st.f_blocks - st.f_bfree) * st.f_frsize,
        free=st.f_bavail * st.f_frsize,
    )
