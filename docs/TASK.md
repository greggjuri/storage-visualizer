# Visual Storage Monitor: Backlog

## Next
- [ ] Pie per volume - enumerate filtered, deduped local mounts once at startup and show one pie each in a plain window

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

## Done

## Known Issues

## Notes
- ADR-008 (QPainter vs QtCharts) is Proposed; settle it while brainstorming the first feature.
- docs/TESTING.md: replace the web checklist with the manual checks in PLANNING.md → Testing Approach.
- TDD scope: core/ strict TDD; ui/ pytest-qt smoke tests only; tray and KWin behavior covered by the manual checklist.
