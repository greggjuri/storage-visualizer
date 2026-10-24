# Flow Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Task 4 is a STOP, human hand-off: a sanctioned stop for inline execution too (PILOT-FINDINGS E7). The final branch review may run while the human does the check.

**Goal:** Pies wrap to the window's width; the user (later the KWin rule) owns the width, and mount changes only ever change the height.

**Architecture:** A new `ui/flow_layout.py` `FlowLayout(QLayout)` ported from the PySide6 example (heightForWidth, left-aligned, skips hidden items, one-row `sizeHint`, `insertWidget`). `MainWindow` swaps `QHBoxLayout` for it and replaces `adjustSize()` with `_fit_height()`: width is the one-row width capped at the screen until the window is first shown, the current width afterwards; height is clamped with minimum = maximum = `totalHeightForWidth(width)` (minimum width = one pie, from the layout), refit on mount changes and on width changes.

**Tech Stack:** Python 3.13, PySide6, pytest, pytest-qt

**Spec:** `docs/superpowers/specs/2026-10-21-flow-layout-design.md`. Read it with this plan, in particular "The adjustSize Problem", "FlowLayout" and "MainWindow Sizing".

## Global Constraints

- `core/` is not touched; `core/` never imports Qt.
- 100% line coverage on `storage_visualizer.core` stays green; `ui/` gets smoke tests only.
- Max 500 lines per file; ruff line length 100; `ruff check . && ruff format --check .` clean.
- Conventional commits: `feat:` `fix:` `refactor:` `docs:` `test:`.
- MainWindow never calls `adjustSize()`.
- After the first show, the app never changes the window's width.
- `pie.show()` stays before `_fit_height()` in `set_mounts` (unshown children are `isHidden()` and count as empty).
- Flow-layout tests set explicit `setSpacing` and `setContentsMargins`; never rely on style defaults.
- Run tests with `.venv/bin/pytest` (Debian has no `python`).

## Review Focus

1. Window hidden after it was shown (the tray item will do this), then a mount change: the width must stay. "Shown" means *ever shown*, not `isVisible()`. Pinned by Task 2 `test_width_kept_on_mount_change_while_hidden`.
2. A removed pie is hidden but not yet deleted (`deleteLater`); the height must already drop. Pinned by Task 2 `test_width_kept_and_height_refits_on_add_and_remove` (no `processEvents()`).
3. User drags narrower than one pie: the window stops at one pie wide, height = one pie per row. Pinned by Task 2 `test_width_never_below_one_pie`.
4. First launch with zero mounts (only the label): the window must still get an explicit size before `show()`, or Qt's `show()` runs `adjustSize()` itself and later pies start from the label's width. `_fit_height()` also runs at the end of `__init__`. Pinned by Task 2 `test_first_show_keeps_one_row_width`.
5. `setFixedHeight` inside `resizeEvent` re-enters `resizeEvent`; the height guard must end the loop. Pinned by Task 2 `test_clamp_wins_over_stale_height`.

---

### Task 1: FlowLayout

**Files:**
- Create: `storage_visualizer/ui/flow_layout.py`
- Test: `tests/ui/test_flow_layout.py`

**Interfaces:**
- Produces: `FlowLayout(parent: QWidget | None = None)` with `addItem`, `count`, `itemAt`, `takeAt`, `insertWidget(index: int, widget: QWidget) -> None`, `hasHeightForWidth() -> True`, `heightForWidth(width: int) -> int`, `minimumSize()`, `sizeHint()`, `setGeometry(rect)`, `expandingDirections() -> Qt.Orientation(0)`.

- [ ] **Step 1: Write the failing tests.** Shared setup: `W, H, SP, M = 100, 50, 10, 5`.

```python
def make(qtbot, n, hidden=0):
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
        w.hide() if i >= n else w.show()  # child of an unshown parent: show() clears isHidden()
        items.append(w)
    return parent, lay, items

def test_wraps_to_width(qtbot):  # 4 items, room for 2 per row
    _, lay, items = make(qtbot, 4)
    width = M + W + SP + W + M  # 220
    assert lay.hasHeightForWidth()
    assert lay.heightForWidth(width) == M + H + SP + H + M  # 120
    lay.setGeometry(QRect(0, 0, width, 120))
    assert [(w.x(), w.y()) for w in items] == [(5, 5), (115, 5), (5, 65), (115, 65)]

def test_minimum_size_is_widest_item(qtbot):
    _, lay, _ = make(qtbot, 3)
    assert lay.minimumSize() == QSize(W + 2 * M, H + 2 * M)

def test_size_hint_is_one_row(qtbot):
    _, lay, _ = make(qtbot, 4)
    assert lay.sizeHint() == QSize(4 * W + 3 * SP + 2 * M, H + 2 * M)

def test_insert_widget_at_index(qtbot):
    _, lay, items = make(qtbot, 2)
    new = QWidget()
    lay.insertWidget(1, new)
    assert [lay.itemAt(i).widget() for i in range(lay.count())] == [items[0], new, items[1]]
    assert new.parent() is lay.parentWidget()
    assert lay.takeAt(1).widget() is new and lay.count() == 2
    assert lay.itemAt(5) is None and lay.takeAt(5) is None

def test_hidden_items_add_no_spacing_or_row(qtbot):  # 3 visible + 1 hidden, room for exactly 3
    _, lay, _ = make(qtbot, 3, hidden=1)
    width = 3 * W + 2 * SP + 2 * M  # 330
    assert lay.heightForWidth(width) == H + 2 * M
    assert lay.sizeHint().width() == width
```

- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/ui/test_flow_layout.py -v` → FAIL with `ModuleNotFoundError: storage_visualizer.ui.flow_layout`.

- [ ] **Step 3: Implement `FlowLayout` in `storage_visualizer/ui/flow_layout.py`.** Module docstring names the PySide6 FlowLayout example as the base. Keep items in a `list[QLayoutItem]`; `__del__` not needed (Qt owns the widgets). One private pass `_do_layout(rect: QRect, test_only: bool) -> int` shared by `heightForWidth` and `setGeometry`, as in the example, with spacing `max(0, self.spacing())` for both directions, margins from `contentsMargins()`, and `item.isEmpty()` items skipped (no x advance, no spacing, no row). `minimumSize()` = `expandedTo` over non-empty items' `minimumSize()` plus margins; `sizeHint()` = sum of non-empty `sizeHint().width()` plus `(n-1)*spacing`, max height, plus margins (zero items: just margins). `insertWidget`: `self.addChildWidget(widget)`, `self._items.insert(index, QWidgetItem(widget))`, `self.invalidate()`.

- [ ] **Step 4: Run to verify they pass.** `.venv/bin/pytest tests/ui/test_flow_layout.py -v` → 5 passed.

- [ ] **Step 5: Commit.**

```bash
git add storage_visualizer/ui/flow_layout.py tests/ui/test_flow_layout.py
git commit -m "feat: add FlowLayout with heightForWidth and hidden-item skipping"
```

---

### Task 2: MainWindow on FlowLayout with height clamp

**Files:**
- Modify: `storage_visualizer/ui/main_window.py`
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `FlowLayout` from Task 1 (`insertWidget`, `removeWidget`, `addWidget`, `totalHeightForWidth`, `sizeHint`).
- Produces: `MainWindow._available_width() -> int` (monkeypatchable), `MainWindow._fit_height() -> None`; public API (`pies`, `set_mounts`, `update_volume`) unchanged.

- [ ] **Step 1: Write the failing tests.** Delete `test_window_grows_immediately_when_pie_added`. Add (helpers use the window's real layout metrics and pie size):

```python
def metrics(w):
    lay = w.layout()
    m = lay.contentsMargins()
    pie = next(iter(w.pies.values()))
    return pie.width(), pie.height(), max(0, lay.spacing()), m

def width_for(w, per_row):
    pw, _, sp, m = metrics(w)
    return m.left() + m.right() + per_row * pw + (per_row - 1) * sp

def height_for(w, rows):
    _, ph, sp, m = metrics(w)
    return m.top() + m.bottom() + rows * ph + (rows - 1) * sp

def test_width_kept_and_height_refits_on_add_and_remove(qtbot):
    w = MainWindow(); qtbot.addWidget(w); w.show()
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 2), w.height())
    width = w.width()
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert w.width() == width and w.height() == height_for(w, 2)
    w.set_mounts([mi("/"), mi("/home")])  # removed pie hidden, deleteLater not run yet
    assert w.width() == width and w.height() == height_for(w, 1)

def test_width_change_refits_height(qtbot):
    w = MainWindow(); qtbot.addWidget(w); w.show()
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    w.resize(width_for(w, 1), w.height())
    assert w.height() == height_for(w, 3)

def test_width_never_below_one_pie(qtbot):
    w = MainWindow(); qtbot.addWidget(w); w.show()
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(10, w.height())
    assert w.width() == width_for(w, 1) and w.height() == height_for(w, 2)

def test_clamp_wins_over_stale_height(qtbot):  # offscreen stand-in for a KWin-restored size
    w = MainWindow(); qtbot.addWidget(w); w.show()
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 2), 2000)
    assert w.height() == height_for(w, 1)

def test_first_show_keeps_one_row_width(qtbot):
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])  # before show(), as main() does
    w.show()
    assert w.width() == width_for(w, 3) and w.height() == height_for(w, 1)

def test_first_launch_width_capped_at_screen(qtbot, monkeypatch):
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/")])
    monkeypatch.setattr(w, "_available_width", lambda: width_for(w, 2))
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    w.show()
    assert w.width() == width_for(w, 2) and w.height() == height_for(w, 2)

def test_width_kept_on_mount_change_while_hidden(qtbot):
    w = MainWindow(); qtbot.addWidget(w); w.show()
    w.set_mounts([mi("/"), mi("/home")])
    w.resize(width_for(w, 1), w.height())
    w.hide()
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert w.width() == width_for(w, 1) and w.height() == height_for(w, 3)
```

- [ ] **Step 2: Run to verify they fail.** `.venv/bin/pytest tests/ui/test_main_window.py -v` → the new tests FAIL (the `QHBoxLayout` window never wraps); existing tests pass.

- [ ] **Step 3: Implement in `storage_visualizer/ui/main_window.py`.**
  - `self._layout = FlowLayout(self)`; `insertWidget`/`removeWidget`/`addWidget` calls unchanged. Add `self._shown_once = False`; set it `True` in `showEvent` (call `super().showEvent(event)`).
  - `_available_width(self) -> int`: `self.screen().availableGeometry().width()`.
  - `_fit_height(self) -> None`, in this order:
    1. `min_w = self._layout.totalMinimumSize().width()` (includes the widget's contents margins, matching `totalHeightForWidth`).
    2. Target width: before the first show `max(min_w, min(self._layout.sizeHint().width(), self._available_width()))`; after it `max(min_w, self.width())`.
    3. `h = self._layout.totalHeightForWidth(target)`.
    4. If `(min_w, h, h) != (self.minimumWidth(), self.minimumHeight(), self.maximumHeight())`: `self.setMinimumSize(min_w, h)` then `self.setMaximumHeight(h)` (the guard ends the `resizeEvent` loop). Do **not** use `setFixedHeight`: it calls `setMinimumSize(minimumWidth(), h)`, which marks the current minimum width as explicit, so Qt's layout would stop updating it and a minimum taken from the label alone would stick. Setting the minimum width from `totalMinimumSize()` ourselves keeps the spec's rule (the minimum width is one pie) without depending on that.
    5. Before the first show only: `self.resize(target, h)`. After the first show the width is never set; growing the minimum in step 4 is the only thing that can widen a window narrower than one pie.
  - Call `_fit_height()` at the end of `__init__`, at the end of `set_mounts` in place of `adjustSize()` (keep `if removed or added:` and the `pie.show()` comment; replace the "Deliberate: SetFixedSize…" comment with one line: never `adjustSize()`, it snaps the width to one pie, see ADR-013), and in `resizeEvent(self, event)` after `super().resizeEvent(event)` when `event.size().width() != event.oldSize().width()`.

- [ ] **Step 4: Run the full suite.** `.venv/bin/pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100` → all pass, core 100%. `ruff check . && ruff format --check .` → clean.

- [ ] **Step 5: Commit.**

```bash
git add storage_visualizer/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: wrap pies with FlowLayout and clamp window height to fit"
```

---

### Task 3: Docs

**Files:**
- Modify: `docs/TESTING.md`, `docs/TASK.md`

- [ ] **Step 1: TESTING.md checklist.** Add after the "Existing pies don't flicker" item, verbatim:
  - `- [ ] Drag the width narrower and wider → pies rewrap; the height follows without visible jitter or clipped rows`
  - `- [ ] At a width you chose, plug in or remove a USB drive → the width stays; only the height changes`
  - `- [ ] First launch with more pies than fit the screen → the window is no wider than the screen`
  - `- [ ] Restored size from the KWin rule → the height still fits, even when the remembered height is stale (N/A until the KWin rule exists)`
- [ ] **Step 2: TASK.md.** Append to the Frameless window item: `; without decorations, width changes need Meta+right-drag (Plasma 6 default), the KWin rule, or startSystemResize edges`. (Checking off Flow layout, ADR-013 Accepted and PLANNING.md happen in recording-decisions at finish.)
- [ ] **Step 3: Commit.** `git add docs/TESTING.md docs/TASK.md && git commit -m "docs: add flow layout checks and frameless resize note"`

---

### Task 4: Manual checklist: STOP, human hand-off

- [ ] **Step 1:** Ask the human to run `.venv/bin/python -m storage_visualizer` and the four new TESTING.md items plus "Plug in a USB drive", "Close the window", "Ctrl+C" and "No tracebacks". Record pass / fail / N/A per item. The final whole-branch review may run meanwhile.
