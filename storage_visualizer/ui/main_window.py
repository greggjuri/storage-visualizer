from PySide6.QtCore import Slot
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QWidget

from storage_visualizer.core.models import MountInfo, Volume
from storage_visualizer.ui.flow_layout import FlowLayout
from storage_visualizer.ui.pie_widget import PieWidget


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Storage")
        self._pies: dict[str, PieWidget] = {}
        self._shown_once = False
        self._width_owned = False  # set once shown with pies; never resized again after that
        self._layout = FlowLayout(self)
        self._empty = QLabel("No volumes found")  # always last; pies are inserted before it
        self._layout.addWidget(self._empty)
        self._fit_height()  # an explicit size, or show() would run adjustSize() itself

    @property
    def pies(self) -> dict[str, PieWidget]:
        return self._pies

    def set_mounts(self, mounts: list[MountInfo]) -> None:
        """Add and remove pies by mount point; pies still present keep their last volume."""
        by_mp = {m.mount_point: m for m in mounts}
        wanted = set(by_mp)
        removed = [mp for mp in self._pies if mp not in wanted]
        for mp in removed:
            pie = self._pies.pop(mp)
            self._layout.removeWidget(pie)
            pie.hide()  # removeWidget leaves it a visible child until deleteLater runs
            pie.deleteLater()
        added = sorted(wanted - self._pies.keys())
        for mp in added:
            index = sum(1 for existing in self._pies if existing < mp)
            pie = PieWidget(mp, by_mp[mp].label)
            self._pies[mp] = pie
            self._layout.insertWidget(index, pie)
            pie.show()  # a never-shown pie is isHidden(); FlowLayout treats it as empty
        self._empty.setVisible(not self._pies)
        if removed or added:
            # Never adjustSize(): it snaps the width to one pie (ADR-013).
            self._fit_height()

    def _available_width(self) -> int:
        return self.screen().availableGeometry().width()

    def _fit_height(self) -> None:
        """Clamp the height to the wrapped rows; the width is the user's once shown with pies (ADR-013)."""
        min_w = self._layout.totalMinimumSize().width()
        if self._width_owned:
            target = max(min_w, self.width())
        else:  # first launch, or pies arriving at a window first shown empty: one row
            target = max(min_w, min(self._layout.sizeHint().width(), self._available_width()))
        h = self._layout.totalHeightForWidth(target)
        if (min_w, h, h) != (self.minimumWidth(), self.minimumHeight(), self.maximumHeight()):
            # Not setFixedHeight: it would freeze whatever minimum width is current.
            # Keep min <= max at every step; xdg-shell treats min > max as a protocol error.
            if h > self.maximumHeight():
                self.setMaximumHeight(h)
                self.setMinimumSize(min_w, h)
            else:
                self.setMinimumSize(min_w, h)
                self.setMaximumHeight(h)
            # The guard above ends the resizeEvent loop.
        if not self._width_owned:
            self.resize(target, h)
            # A label-only width is nobody's choice; one with pies on screen is the user's.
            self._width_owned = self._shown_once and bool(self._pies)

    def showEvent(self, event: QShowEvent) -> None:
        self._shown_once = True
        self._width_owned = self._width_owned or bool(self._pies)
        super().showEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._fit_height()

    @Slot(object)
    def update_volume(self, volume: Volume) -> None:
        pie = self._pies.get(volume.mount_point)
        if pie is not None:
            pie.set_volume(volume)
