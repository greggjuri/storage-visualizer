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
    """Probes mounts concurrently so one hung mount cannot block the rest.

    A mount whose previous probe is still running is skipped (ADR-004), so a
    permanently stuck mount costs one parked thread, not one per poll.
    """

    def __init__(self, statvfs: Callable[[str], Any] = os.statvfs) -> None:
        self._statvfs = statvfs
        self._busy: set[str] = set()
        self._lock = threading.Lock()

    def probe_all(
        self, mounts: Iterable[MountInfo], on_result: Callable[[Volume], None]
    ) -> list[threading.Thread]:
        """Start one daemon thread per idle mount; each calls on_result from its thread."""
        threads = []
        for mount in mounts:
            with self._lock:
                if mount.mount_point in self._busy:
                    continue
                self._busy.add(mount.mount_point)
            t = threading.Thread(target=self._run, args=(mount, on_result), daemon=True)
            try:
                t.start()
            except BaseException:
                with self._lock:
                    self._busy.discard(mount.mount_point)
                raise
            threads.append(t)
        return threads

    def _run(self, mount: MountInfo, on_result: Callable[[Volume], None]) -> None:
        try:
            on_result(probe(mount, self._statvfs))
        finally:
            with self._lock:
                self._busy.discard(mount.mount_point)
