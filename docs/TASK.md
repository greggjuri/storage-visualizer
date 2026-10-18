# Visual Storage Monitor: Backlog

## Next

## Backlog
### Phase 1: Working monitor
- [ ] Polling refresh - re-run enumerate + probe every 30 s; add, update and remove pies in place by mount point
- [ ] Network share probe - per-mount worker with 2 s timeout, "unavailable" pie state, no re-dispatch while a probe is stuck (ADR-004)
- [ ] Volume labels - by-label name, else mount point, "/" as System; used/free/total text under each pie
- [ ] Flow layout - pies in one row that wraps to a grid as volumes are added

### Phase 2: Desktop integration
- [ ] Tray icon - show/hide window on click, Quit in the menu
- [ ] Frameless window - no decorations, drag to move via startSystemMove, stable app id
- [ ] Install and autostart - pipx entry point, XDG autostart .desktop, README section with the KWin "keep above" rule
- [ ] Theme-aware text - pie label uses palette().windowText() so it's readable on Breeze Dark

## Done
- [x] Pie per volume - enumerate filtered, deduped local mounts once at startup and show one pie each in a plain window

## Known Issues
- Non-OSError exception in a probe worker leaves the pie on loading forever; traceback goes to stderr only. Revisit with polling.
- Qt portal warning on start: "Could not register app ID: App info not found for 'storage-visualizer'" — no installed .desktop file yet. Expect it to go away with the Install and autostart item; verify there.
- Quit-time race: a probe worker finishing after app.exec() returns can emit on the deleted ResultBridge and print a RuntimeError traceback. Unlikely with local disks; fix in Network share probe (shutdown flag or disconnect in aboutToQuit).

## Notes
- TDD scope: core/ strict TDD; ui/ pytest-qt smoke tests only; tray and KWin behavior covered by the manual checklist.
