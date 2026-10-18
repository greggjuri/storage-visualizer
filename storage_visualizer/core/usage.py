import os
import threading
from collections.abc import Callable, Iterable
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


class UsageProbe:
    """Probes mounts concurrently so one hung mount cannot block the rest."""

    def __init__(self, statvfs: Callable[[str], Any] = os.statvfs) -> None:
        self._statvfs = statvfs

    def probe_all(
        self, mounts: Iterable[MountInfo], on_result: Callable[[Volume], None]
    ) -> list[threading.Thread]:
        """Start one daemon thread per mount; each calls on_result from its thread."""
        threads = []
        for mount in mounts:
            t = threading.Thread(
                target=lambda m=mount: on_result(probe(m, self._statvfs)),
                daemon=True,
            )
            t.start()
            threads.append(t)
        return threads
