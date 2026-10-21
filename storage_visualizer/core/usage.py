import os
import threading
from collections.abc import Callable, Iterable
from typing import Any

from storage_visualizer.core.models import MountInfo, Volume


def _base(mount: MountInfo) -> tuple[str, str, str, bool]:
    return (mount.mount_point, mount.mount_point, mount.fstype, mount.is_network)


def unavailable(mount: MountInfo) -> Volume:
    return Volume(*_base(mount), "unavailable", None, None, None)


def probe(mount: MountInfo, statvfs: Callable[[str], Any] = os.statvfs) -> Volume:
    """Probe one mount's usage; numbers match df (used vs Avail)."""
    try:
        st = statvfs(mount.mount_point)
    except OSError:
        return unavailable(mount)
    return Volume(
        *_base(mount),
        "ok",
        total=st.f_blocks * st.f_frsize,
        used=(st.f_blocks - st.f_bfree) * st.f_frsize,
        free=st.f_bavail * st.f_frsize,
    )


class UsageProbe:
    """Probes mounts concurrently so one hung mount cannot block the rest.

    No timeout (ADR-011): a mount whose previous probe is still running gets no
    new probe and is reported unavailable instead, so a permanently stuck mount
    costs one parked thread, not one per poll. Its late result still arrives.

    Both deliveries happen under the probe's lock, so a stale "unavailable" can
    never follow a fresh result. "Unavailable" is emitted from probe_all on the
    calling (UI) thread, so Qt delivers it directly, not queued, while the lock
    is held; worker results are emitted from the worker and queued. on_result
    must therefore be quick and must never call into this probe from either
    thread, or it deadlocks.
    """

    def __init__(self, statvfs: Callable[[str], Any] = os.statvfs) -> None:
        self._statvfs = statvfs
        self._busy: set[str] = set()
        self._closed = False
        self._lock = threading.Lock()

    def probe_all(
        self, mounts: Iterable[MountInfo], on_result: Callable[[Volume], None]
    ) -> list[threading.Thread]:
        """Start one daemon thread per idle mount; report busy mounts unavailable."""
        threads = []
        for mount in mounts:
            with self._lock:
                if self._closed:
                    return threads
                if mount.mount_point in self._busy:
                    on_result(unavailable(mount))
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

    def close(self) -> None:
        """After this returns, on_result is never called again (quit-time race)."""
        with self._lock:
            self._closed = True

    def _run(self, mount: MountInfo, on_result: Callable[[Volume], None]) -> None:
        vol = None
        try:
            vol = probe(mount, self._statvfs)
        finally:
            with self._lock:
                self._busy.discard(mount.mount_point)
                if vol is not None and not self._closed:
                    on_result(vol)
