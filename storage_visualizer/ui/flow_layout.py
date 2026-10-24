"""Left-aligned rows that wrap to the available width, based on the PySide6 FlowLayout example.

Hidden widgets (item.isEmpty()) take no space, spacing or row.
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def insertWidget(self, index: int, widget: QWidget) -> None:
        # addWidget lets Qt create and own the item; removeWidget deletes it in C++.
        self.addWidget(widget)
        self._items.insert(index, self._items.pop())

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._visible():
            size = size.expandedTo(item.minimumSize())
        return size + self._margin_size()

    def sizeHint(self) -> QSize:
        """All visible items in one row: the width the window opens at."""
        hints = [item.sizeHint() for item in self._visible()]
        width = sum(h.width() for h in hints) + max(0, len(hints) - 1) * self._spacing()
        height = max((h.height() for h in hints), default=0)
        return QSize(width, height) + self._margin_size()

    def _visible(self) -> list[QLayoutItem]:
        return [item for item in self._items if not item.isEmpty()]

    def _spacing(self) -> int:
        return max(0, self.spacing())

    def _margin_size(self) -> QSize:
        m = self.contentsMargins()
        return QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        spacing = self._spacing()
        x, y, line_height = area.x(), area.y(), 0
        for item in self._visible():
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > area.right() + 1 and line_height > 0:
                x = area.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()
