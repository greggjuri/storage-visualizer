from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QWidget

from storage_visualizer.ui.flow_layout import FlowLayout

W, H, SP, M = 100, 50, 10, 5


def make(qtbot, n, hidden=0):
    """Callers keep `parent`: once it is collected Qt deletes the layout's items."""
    parent = QWidget()
    qtbot.addWidget(parent)
    lay = FlowLayout(parent)
    lay.setSpacing(SP)
    lay.setContentsMargins(M, M, M, M)
    items = []
    for i in range(n + hidden):
        w = QWidget()
        w.setFixedSize(W, H)
        lay.addWidget(w)
        if i >= n:
            w.hide()
        else:
            w.show()  # child of an unshown parent: show() clears isHidden()
        items.append(w)
    return parent, lay, items


def test_wraps_to_width(qtbot):  # 4 items, room for 2 per row
    parent, lay, items = make(qtbot, 4)
    width = M + W + SP + W + M  # 220
    assert lay.hasHeightForWidth()
    assert lay.heightForWidth(width) == M + H + SP + H + M  # 120
    lay.setGeometry(QRect(0, 0, width, 120))
    assert [(w.x(), w.y()) for w in items] == [(5, 5), (115, 5), (5, 65), (115, 65)]


def test_minimum_size_is_widest_item(qtbot):
    parent, lay, _ = make(qtbot, 3)
    assert lay.minimumSize() == QSize(W + 2 * M, H + 2 * M)


def test_size_hint_is_one_row(qtbot):
    parent, lay, _ = make(qtbot, 4)
    assert lay.sizeHint() == QSize(4 * W + 3 * SP + 2 * M, H + 2 * M)


def test_insert_widget_at_index(qtbot):
    parent, lay, items = make(qtbot, 2)
    new = QWidget()
    lay.insertWidget(1, new)
    assert [lay.itemAt(i).widget() for i in range(lay.count())] == [items[0], new, items[1]]
    assert new.parent() is lay.parentWidget()
    assert lay.takeAt(1).widget() is new and lay.count() == 2
    assert lay.itemAt(5) is None and lay.takeAt(5) is None


def test_hidden_items_add_no_spacing_or_row(qtbot):  # 3 visible + 1 hidden, room for exactly 3
    parent, lay, _ = make(qtbot, 3, hidden=1)
    width = 3 * W + 2 * SP + 2 * M  # 330
    assert lay.heightForWidth(width) == H + 2 * M
    assert lay.sizeHint().width() == width
