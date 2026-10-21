# Flow Layout: Design

**Date**: 2026-10-21
**Backlog item**: "Flow layout" (docs/TASK.md, Next)
**Status**: Approved (branch feat/flow-layout)

## Goal

Pies wrap to the window's width. The user chooses the width (later remembered by a KWin rule); there is no fixed number of pies per row. Adding or removing a pie may change the window's height but never the width the user chose.

## Context

- **ADR-006**: on Wayland the app can't position itself; size, position and keep-above come from a KWin rule on app id `storage-visualizer`. This design keeps the width owned by the user/KWin and clamps only the height.
- **ADR-009 / ADR-010**: the Refresher calls `MainWindow.set_mounts` each tick; `set_mounts` diffs by mount point and inserts pies in sorted order. Unchanged.
- **ADR-008**: `PieWidget` has a fixed size; the flow layout relies on that.
- **PLANNING.md**: Architecture ("frameless, flow layout of PieWidgets"), Testing Approach (ui/ smoke tests only), 500-line limit, `core/` never imports Qt.
- New decision, recorded as **ADR-013 (Proposed)** until the branch finishes; see Decisions.

## Scope

**In scope**
- `ui/flow_layout.py`: a `FlowLayout(QLayout)` based on the PySide6 FlowLayout example (heightForWidth)
- `MainWindow`: swap `QHBoxLayout` for `FlowLayout`, replace `adjustSize()` with a height clamp
- Smoke tests, TESTING.md checklist items, ADR-013, PLANNING.md and TASK.md updates

**Out of scope**
- Frameless window, resize edges, tray, KWin rule setup
- Centred or justified rows, animations, scrolling
- Any `core/` change

## The adjustSize Problem

`QWidget.adjustSize()` on a window with a heightForWidth layout sets the width to `layout.sizeHint().width()` and the height to `totalHeightForWidth` of that width. The example's `sizeHint()` returns `minimumSize()` (the largest item), so `adjustSize()` collapses the window to one pie per column. Verified offscreen: 150×200 items, window resized to 500 wide, one pie added, `adjustSize()` → 172 px wide. `resize(width(), totalHeightForWidth(width()))` kept 500 and refit the height.

So MainWindow never calls `adjustSize()` again. It owns the window size through a height clamp.

## FlowLayout

`storage_visualizer/ui/flow_layout.py`, a port of the PySide6 example with these differences:

- **Left-aligned rows**, horizontal and vertical spacing both from `spacing()` (the example's style-dependent smart spacing is dropped), contents margins respected.
- **Skips empty items**: every pass (`sizeHint`, `minimumSize`, `heightForWidth`, `setGeometry`) ignores items where `item.isEmpty()` (hidden widgets). A hidden widget adds no width, no spacing and no row. This keeps the hidden "No volumes found" label from causing a phantom row.
- **`minimumSize()`**: the widest/tallest non-empty item, plus margins. The window can't get narrower than one pie.
- **`sizeHint()`**: all non-empty items in **one row** (sum of widths plus spacing, max height, plus margins). Used only for the first-launch width.
- **`hasHeightForWidth()`** is `True`; `heightForWidth(w)` runs the layout pass without placing items.
- **`expandingDirections()`**: none.
- **`insertWidget(index, widget)`**: `addChildWidget(widget)` then insert a `QWidgetItem` at `index`, then `invalidate()`. Needed because `set_mounts` inserts pies in sorted position; the example only appends. `addItem`, `count`, `itemAt`, `takeAt` behave like the example, so `removeWidget` and `itemAt`-based iteration keep working.

## MainWindow Sizing

- `self._layout = FlowLayout(self)`; the "No volumes found" label stays the last item; pies are inserted before it, as today.
- **`_available_width()`** returns `self.screen().availableGeometry().width()`. A separate method so tests can monkeypatch it.
- **`_fit_height()`**:
  - Width: if the window has never been shown, `min(self._layout.sizeHint().width(), self._available_width())`, applied with `resize(width, …)`. Once shown, the current `width()`; the app never changes the width after the first show.
  - Height: `h = self._layout.totalHeightForWidth(width)`; if `h` or the layout's minimum width differ from the window's current limits, `setMinimumSize(layout.minimumSize().width(), h)` and `setMaximumHeight(h)` (minimum = maximum height). Not `setFixedHeight`: it marks the current minimum width as explicit, so Qt would stop updating it from the layout.
- **Called from**:
  - the end of `set_mounts` when pies were added or removed, replacing `adjustSize()`;
  - `resizeEvent` when the width changed (`event.size().width() != event.oldSize().width()`). The guard on `h` stops the clamp → `resizeEvent` loop.
- **`pie.show()` stays before `_fit_height()`** in `set_mounts`. A child widget that was never shown is still `isHidden()` until `show()`, so `FlowLayout` would count it as empty and size the window without it.
- **Why min/max instead of `resize()`**: Equal minimum and maximum heights hand the compositor a minimum and maximum height. During a drag KWin limits the height itself instead of the app correcting it afterwards, and a size forced by a KWin rule (a stale remembered height) is clamped to the fitted height. The minimum width (one pie) is set explicitly from `FlowLayout.minimumSize()`.

## Error Handling

Nothing new can fail at runtime. Zero pies: the label is the only visible item, so the window fits one label. A pie wider than the available screen width: the width is the layout's minimum (one pie) and wins over `_available_width()` through the window's minimum size.

## Testing

Smoke tests only (ui/); `core/` is unchanged, so the 100% `core/` coverage gate is unaffected.

**`tests/ui/test_flow_layout.py`** (new). Fixed-size dummy widgets in a plain parent widget; every test sets explicit `setSpacing` and `setContentsMargins` instead of relying on style defaults.
- Wraps by width: 4 items at a width that fits 2 → two rows; item geometries in two rows; `heightForWidth` = 2 rows + spacing + margins.
- `minimumSize()` = widest item + margins.
- `sizeHint()` = one-row width.
- `insertWidget(index, w)` puts the item at `index`; `takeAt`/`count` behave like the example.
- Hidden items are skipped: N items plus one hidden widget at a width that fits exactly N per row → one row, and `sizeHint` has no extra spacing.

**`tests/ui/test_main_window.py`**
- Remove `test_window_grows_immediately_when_pie_added` (asserts a width change, which now contradicts the goal).
- Width kept on add and remove: show, resize to about 2 pies wide, add a pie → same width, height grows to two rows; remove it → same width, height back to one row. No `processEvents()` needed.
- Width change refits height: resize to 1 pie wide → height of N rows.
- Clamp wins over a stale size: `resize(width, 2000)` → height equals the fitted height.
- First-launch width: `set_mounts` before `show()` → one-row width.
- Small screen: monkeypatch `_available_width` to a small value → width equals that value and the height fits the wrapped rows.
- Existing order tests keep passing unchanged (`layout_order` iterates `layout().itemAt()`).

**docs/TESTING.md checklist additions**
- Drag the width narrower and wider → pies rewrap; the height follows without visible jitter or clipped rows.
- At a width you chose, plug in or remove a USB drive → the width stays; only the height changes.
- First launch with more pies than fit the screen → the window is no wider than the screen.
- Restored size from the KWin rule → the height still fits, even when the remembered height is stale (n/a until the KWin rule exists).

## Decisions

**ADR-013 (Proposed): Window height clamped to the flow's heightForWidth; width owned by the user and KWin.** MainWindow clamps the height (minimum = maximum = `layout.totalHeightForWidth(width())`) on mount changes and width changes and never calls `adjustSize()` after this change; the first-launch width is the one-row width capped at the available screen width. Rejected: clamping inside `FlowLayout.setGeometry` (re-entrant, mixes layout with window sizing); a scroll area (hides the problem instead of fitting the content); refitting with `resize()` only on mount changes (stale heights after a drag or a KWin-restored size). Becomes Accepted at finish via recording-decisions.

## Follow-ups (TASK.md)

- Frameless window item: without decorations, width changes need Meta+right-drag (Plasma 6 default), the KWin rule, or `startSystemResize` edges.
