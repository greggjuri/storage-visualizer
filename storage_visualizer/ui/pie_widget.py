"""One used/free pie for a single volume, drawn with plain QPainter (ADR-008)."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from storage_visualizer.core.dfsize import df_size
from storage_visualizer.core.models import Volume

USED_COLOR = QColor("#3daee9")
FREE_COLOR = QColor("#e3e5e7")
RING_COLOR = QColor("#9a9ea3")
UNAVAILABLE_COLOR = QColor("#b0b3b8")
TEXT_COLOR = QColor("#232629")

WORST_CASE_NUMBERS = "1022M used · 1022M free"
MIN_WIDTH = 140
_PIE_SIZE = 120
_FULL_CIRCLE = 5760  # 360 degrees in 1/16 degree units
_START_ANGLE = 90 * 16  # 12 o'clock


def used_percent(used: int, free: int) -> int:
    """df's Use%: ceil(100 * used / (used + free)), in integer arithmetic."""
    total = used + free
    if total == 0:
        return 0
    return -(-100 * used // total)


def pie_text(volume: Volume | None, mount_point: str, label: str) -> list[str]:
    """Lines under the pie: the name, plus df -h style numbers when the volume is ok."""
    name = (volume.label if volume and volume.label else None) or label or mount_point
    if volume is None or volume.status != "ok":
        return [name]
    used = volume.used or 0
    free = volume.free or 0
    total = volume.total if volume.total is not None else used + free
    return [name, f"{df_size(used)} used · {df_size(free)} free", f"{df_size(total)} total"]


class PieWidget(QWidget):
    def __init__(self, mount_point: str, label: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mount_point = mount_point
        self._label = label
        self._volume: Volume | None = None
        metrics = self.fontMetrics()
        self._width = max(MIN_WIDTH, metrics.horizontalAdvance(WORST_CASE_NUMBERS) + 8)
        self._line_height = metrics.height()
        self._height = 10 + _PIE_SIZE + 6 + 3 * self._line_height + 6
        self.setFixedSize(self._width, self._height)

    @property
    def label(self) -> str:
        return self._label

    @property
    def volume(self) -> Volume | None:
        return self._volume

    def set_volume(self, volume: Volume) -> None:
        self._volume = volume
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left = (self._width - _PIE_SIZE) / 2
        rect = QRectF(left, 10, _PIE_SIZE, _PIE_SIZE)
        volume = self._volume

        if volume is None:
            painter.setPen(QPen(RING_COLOR, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
            centre = "…"
        elif volume.status == "unavailable":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(UNAVAILABLE_COLOR)
            painter.drawEllipse(rect)
            centre = "unavailable"
        else:
            used = volume.used or 0
            free = volume.free or 0
            total = used + free
            used_span = -round(_FULL_CIRCLE * used / total) if total else 0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(USED_COLOR)
            if used_span:
                painter.drawPie(rect, _START_ANGLE, used_span)
            painter.setBrush(FREE_COLOR)
            painter.drawPie(rect, _START_ANGLE + used_span, -_FULL_CIRCLE - used_span)
            centre = f"{used_percent(used, free)}%"

        painter.setPen(TEXT_COLOR)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, centre)

        top = 10 + _PIE_SIZE + 6
        for i, line in enumerate(pie_text(volume, self._mount_point, self._label)):
            if i == 0:  # only the name may elide; the numbers must always fit
                line = QFontMetrics(painter.font()).elidedText(
                    line, Qt.TextElideMode.ElideMiddle, self._width - 4
                )
            painter.drawText(
                QRectF(2, top + i * self._line_height, self._width - 4, self._line_height),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                line,
            )
        painter.end()
