from PySide6.QtCore import Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.ui.pie_widget import PieWidget


class MainWindow(QWidget):
    def __init__(self, mounts: list[MountInfo]) -> None:
        super().__init__()
        self.setWindowTitle("Storage")
        self._pies: dict[str, PieWidget] = {}
        layout = QHBoxLayout(self)
        if not mounts:
            layout.addWidget(QLabel("No volumes found"))
        for mount in mounts:
            pie = PieWidget(mount.mount_point)
            self._pies[mount.mount_point] = pie
            layout.addWidget(pie)

    @property
    def pies(self) -> dict[str, PieWidget]:
        return self._pies

    @Slot(object)
    def update_volume(self, volume: Volume) -> None:
        pie = self._pies.get(volume.mount_point)
        if pie is not None:
            pie.set_volume(volume)
