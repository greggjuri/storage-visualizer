# Visual Storage Monitor: Backlog

## Next
- [ ] Network share probe - network fstypes in enumeration, 2 s probe timeout, "unavailable" pie for stuck probes, fix the quit-time race on the deleted ResultBridge (shutdown flag or disconnect in aboutToQuit) (the no-re-dispatch busy guard shipped with Polling refresh, ADR-004)

## Backlog
### Phase 1: Working monitor
- [ ] Volume labels - by-label name, else mount point, "/" as System; used/free/total text under each pie
- [ ] Flow layout - pies in one row that wraps to a grid as volumes are added

### Phase 2: Desktop integration
- [ ] Tray icon - show/hide window on click, Quit in the menu
- [ ] Frameless window - no decorations, drag to move via startSystemMove, stable app id
- [ ] Install and autostart - pipx entry point, XDG autostart .desktop, README section with the KWin "keep above" rule
- [ ] Theme-aware text - pie label uses palette().windowText() so it's readable on Breeze Dark

## Done
- [x] Polling refresh - 30 s Refresher (ADR-010), mount-list diff in MainWindow, busy guard in UsageProbe
- [x] Pie per volume - enumerate filtered, deduped local mounts once at startup and show one pie each in a plain window

## Known Issues
- Non-OSError exception in a probe worker leaves the pie on loading forever; traceback goes to stderr only. Since Polling refresh the busy guard's `finally` frees the mount, so the next tick re-probes and the pie recovers; the traceback still only reaches stderr.
- Qt portal warning on start: "Could not register app ID: App info not found for 'storage-visualizer'" — no installed .desktop file yet. Expect it to go away with the Install and autostart item; verify there.
- Quit-time race: a probe worker finishing after app.exec() returns can emit on the deleted ResultBridge and print a RuntimeError traceback. Unlikely with local disks; fix in Network share probe (shutdown flag or disconnect in aboutToQuit).
- Two devices overmounted on the same path collapse into one pie and one probe (identity is the mount point). Harmless; left as is.

## Notes
- TDD scope: core/ strict TDD; ui/ pytest-qt smoke tests only; tray and KWin behavior covered by the manual checklist.
