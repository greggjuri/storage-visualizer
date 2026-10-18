from PySide6.QtCore import Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.ui.pie_widget import PieWidget


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Storage")
        self._pies: dict[str, PieWidget] = {}
        self._layout = QHBoxLayout(self)
        self._empty = QLabel("No volumes found")  # always last; pies are inserted before it
        self._layout.addWidget(self._empty)

    @property
    def pies(self) -> dict[str, PieWidget]:
        return self._pies

    def set_mounts(self, mounts: list[MountInfo]) -> None:
        """Add and remove pies by mount point; pies still present keep their last volume."""
        wanted = {m.mount_point for m in mounts}
        removed = [mp for mp in self._pies if mp not in wanted]
        for mp in removed:
            pie = self._pies.pop(mp)
            self._layout.removeWidget(pie)
            pie.hide()  # removeWidget leaves it a visible child until deleteLater runs
            pie.deleteLater()
        added = sorted(wanted - self._pies.keys())
        for mp in added:
            index = sum(1 for existing in self._pies if existing < mp)
            pie = PieWidget(mp)
            self._pies[mp] = pie
            self._layout.insertWidget(index, pie)
            pie.show()  # Qt defers the show; adjustSize would size without the new pie
        self._empty.setVisible(not self._pies)
        if removed or added:
            # Deliberate: SetFixedSize on the layout would fight the Flow layout's wrapping.
            self.adjustSize()

    @Slot(object)
    def update_volume(self, volume: Volume) -> None:
        pie = self._pies.get(volume.mount_point)
        if pie is not None:
            pie.set_volume(volume)
