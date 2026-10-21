"""Runs the enumerate -> diff -> probe cycle at startup and every 30 s (ADR-005, ADR-010)."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Slot

from storage_visualizer.core.enumerator import enumerate_system_mounts
from storage_visualizer.core.models import MountInfo
from storage_visualizer.core.usage import UsageProbe

INTERVAL_MS = 30_000


class Refresher(QObject):
    def __init__(
        self,
        window,
        bridge,
        probe: UsageProbe | None = None,
        enumerate_fn: Callable[[], list[MountInfo]] = enumerate_system_mounts,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._bridge = bridge
        # One probe for the app's lifetime: its busy set must persist across ticks.
        self._probe = probe if probe is not None else UsageProbe()
        self._enumerate = enumerate_fn
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)

    @property
    def timer(self) -> QTimer:
        return self._timer

    def start(self) -> None:
        self.refresh()
        self._timer.start()

    @Slot()
    def stop(self) -> None:
        """On aboutToQuit: no more ticks, and no result reaches the bridge after this."""
        self._timer.stop()
        self._probe.close()

    @Slot()
    def refresh(self) -> None:
        mounts = self._enumerate()
        self._window.set_mounts(mounts)
        self._probe.probe_all(mounts, self._bridge.volume_ready.emit)
