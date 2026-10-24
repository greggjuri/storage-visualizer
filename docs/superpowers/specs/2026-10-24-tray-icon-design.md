# Tray Icon: Design

**Date**: 2026-10-24
**Backlog item**: "Tray icon" (docs/TASK.md, Next)
**Status**: Approved (branch feat/tray-icon)

## Goal

The app lives in the KDE system tray. A left-click on the tray icon shows or hides the window; the tray menu's Quit is the real exit. Closing the window only hides it. Polling keeps running while the window is hidden, so it is current the moment it is shown.

## Context

- **ADR-006**: frameless window plus a `QSystemTrayIcon` with show/hide and Quit; on-top and position come from a KWin rule. This design adds the tray part.
- **ADR-001**: Debian 13 + KDE Plasma 6 Wayland only. KDE always has a tray (StatusNotifierItem), so there is no "no tray" fallback.
- **ADR-005**: polling every 30 s is cheap, so it continues while the window is hidden.
- **ADR-010 / ADR-011**: `app.aboutToQuit` → `Refresher.stop` → `UsageProbe.close()`. Quit must still go through this path.
- **ADR-013**: once shown with pies, the width is the user's. Hiding and showing doesn't change that (`_width_owned` stays set).
- **PLANNING.md**: Architecture (TrayIcon in `ui/`, show/hide arrow to MainWindow), Testing Approach (ui/ smoke tests only), 500-line limit, `core/` never imports Qt.
- `app.py` keeps `signal.signal(SIGINT, SIG_DFL)`: Ctrl+C still terminates at once.
- New decision, recorded as **ADR-014 (Proposed)** until the branch finishes; see Decisions.

## Scope

**In scope**
- `ui/tray.py`: `TrayIcon(QSystemTrayIcon)`
- `app.py`: `setQuitOnLastWindowClosed(False)`, build and show the tray
- Smoke tests, TESTING.md checklist changes, ADR-014, PLANNING.md and TASK.md updates

**Out of scope**
- A Show/Hide entry in the menu (left-click does it)
- A fallback when no tray is available
- An icon that shows usage (backlog, Later)
- Frameless window, KWin rule, autostart
- Any `core/` or `MainWindow` change

## TrayIcon

`storage_visualizer/ui/tray.py`:

```python
class TrayIcon(QSystemTrayIcon):
    def __init__(self, window: QWidget, on_quit: Callable[[], None], parent: QObject | None = None) -> None
    def toggle(self) -> None
```

- **Icon**: `QIcon.fromTheme("drive-harddisk-symbolic", fallback_icon())`. Breeze's symbolic drive icon matches the other monochrome panel icons. `fallback_icon()` (module-level function) paints a small two-slice pie (used/free colours like `PieWidget`) into a `QPixmap` with `QPainter` and returns it as a `QIcon`. The offscreen test platform may not load Breeze; the fallback keeps the icon non-null there and on any machine without the theme icon.
- **Tooltip**: "Storage" (matches the window title).
- **Context menu**: a `QMenu` with one action, **Quit**, whose `triggered` calls `on_quit()`. The `TrayIcon` keeps the menu in an attribute: `setContextMenu` does not take ownership, and a `QMenu` cannot have a non-widget parent.
- **Activation**: `activated(reason)`: `reason == QSystemTrayIcon.ActivationReason.Trigger` (left-click) calls `toggle()`. Every other reason (Context, DoubleClick, MiddleClick) does nothing; right-click opens the menu by itself.
- **`toggle()`**: if `window.isVisible()`, `window.hide()`. Otherwise `window.show()`, `window.raise_()`, `window.activateWindow()`. On Wayland the compositor may refuse to raise or focus without an activation token; the manual check records what actually happens.

## App Wiring

`storage_visualizer/ui/app.py`, after the window is built:

```python
app.setQuitOnLastWindowClosed(False)  # close hides to the tray; tray Quit is the exit (ADR-014)
...
tray = TrayIcon(window, app.quit)  # keep referenced until app.exec() returns
tray.show()
```

- **Close**: a top-level `QWidget` without `WA_DeleteOnClose` is only hidden by `close()`. With `quitOnLastWindowClosed` off, the app keeps running. `MainWindow` needs no `closeEvent`.
- **Quit**: `app.quit()` emits `aboutToQuit`, so `Refresher.stop` runs exactly as before. It is the only graceful exit; Ctrl+C (SIG_DFL) stays an immediate kill.
- **Hidden window**: the Refresher keeps calling `set_mounts` / `update_volume`. `_fit_height` only sets size limits and, before the width is owned, `resize`; both work on a hidden widget. On re-show, `showEvent` runs again; `_width_owned` is already set, so the width stays (ADR-013).
- **Wayland**: hiding unmaps the toplevel; KWin chooses where it reappears until the KWin rule (ADR-006) pins it.
- The window still opens shown at startup (`window.show()` unchanged).

## Error Handling

Nothing new can fail at runtime. A missing theme icon falls back to the painted pie. No tray available is not handled (ADR-001); if autostart ever runs before plasmashell's tray is up, that is checked in the Install and autostart item.

## Testing

Smoke tests only (ui/); `core/` is unchanged, so the 100% `core/` coverage gate is unaffected.

**`tests/ui/test_tray.py`** (new), with a plain `QWidget` as the window and a recording `on_quit`:
- The tray icon is not null (`tray.icon().isNull()` is False), whichever of theme or fallback was used.
- `fallback_icon()` is not null.
- The context menu has exactly one action, text "Quit"; triggering it calls `on_quit` once.
- `toggle()` on a shown window hides it; `toggle()` on a hidden window shows it.
- `activated.emit(Trigger)` toggles; `activated.emit(Context)` does not.

`app.py` wiring (`setQuitOnLastWindowClosed`, real tray behaviour) is covered by the manual checklist.

**TESTING.md** checklist:
- Replace "Tray icon shows/hides the window; tray Quit → clean exit, no traceback (N/A until the tray lands)" with:
  - Tray icon appears in the panel (Breeze drive icon)
  - Left-click on the tray icon hides a visible window and shows a hidden one; when shown, record whether it comes to the front with focus (Wayland activation may block raise)
  - Right-click → menu with Quit only; Quit → clean exit, no traceback
  - While hidden, plug in or remove a USB drive, wait one poll, show → the pie set is current
- Replace "Close the window → clean exit, no traceback" with "Close the window → it hides, the process keeps running, the tray icon stays".
- "Ctrl+C in the terminal → exits immediately, no traceback" stays.

## Decisions

**ADR-014 (Proposed): Closing the window hides it to the tray; tray Quit is the only graceful exit.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Close hides, tray Quit exits (`setQuitOnLastWindowClosed(False)`) | Always-available monitor survives an accidental close; standard tray-app behaviour | Two ways to "close"; a hidden process is easy to forget | Accepted |
| Close quits (current) | One obvious exit | Closing loses the monitor; the tray adds little | Rejected |
| Close minimizes | Window stays in the task manager | Wayland minimize is compositor-owned; duplicates the tray | Rejected |

## Docs to Update

- **PLANNING.md**: Testing Approach manual checks: tray and close lines as above.
- **TASK.md**: tick the tray item at finish. "Tray icon shows usage — small pie of the fullest volume" is added under Backlog → Later with this spec.
- **DECISIONS.md**: ADR-014, Proposed until finish.
