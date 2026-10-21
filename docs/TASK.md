# Visual Storage Monitor: Backlog

## Next
- [ ] Flow layout - pies in one row that wraps to a grid as volumes are added

## Backlog
### Phase 2: Desktop integration
- [ ] Tray icon - show/hide window on click, Quit in the menu
- [ ] Frameless window - no decorations, drag to move via startSystemMove, stable app id
- [ ] Install and autostart - pipx entry point, XDG autostart .desktop, README section with the KWin "keep above" rule
- [ ] Theme-aware text - pie label uses palette().windowText() so it's readable on Breeze Dark

## Done
- [x] Volume labels - network: last path component of the share source (mount point's last component if none); local: by-label name (udev escapes decoded), else mount point's last component; "/" is System. Three lines under each pie: label / "<used> used · <free> free" / "<total> total", formatted like `df -h` (ADR-012: by-label read at enumerate time)
- [x] Network share probe - nfs/nfs4/cifs/smb3/fuse.sshfs pies, no timeout: busy at next tick → "unavailable", late result recovers (ADR-011, supersedes ADR-004); quit-time race fixed via Refresher.stop on aboutToQuit; Ctrl+C exits at once (SIG_DFL)
- [x] Polling refresh - 30 s Refresher (ADR-010), mount-list diff in MainWindow, busy guard in UsageProbe
- [x] Pie per volume - enumerate filtered, deduped local mounts once at startup and show one pie each in a plain window

## Known Issues
- Non-OSError exception in a probe worker leaves the pie on loading forever; traceback goes to stderr only. Since Polling refresh the busy guard's `finally` frees the mount, so the next tick re-probes and the pie recovers; the traceback still only reaches stderr.
- Qt portal warning on start: "Could not register app ID: App info not found for 'storage-visualizer'" — no installed .desktop file yet. Expect it to go away with the Install and autostart item; verify there.
- Two devices overmounted on the same path collapse into one pie and one probe (identity is the mount point). Harmless; left as is.
- A hard-mounted NFS share that is dead at quit can stall process exit (daemon thread in uninterruptible sleep in statvfs). Accepted: shares are trusted to be available (ADR-011).
- Busy set is keyed by mount point: after `umount -l` of a dead share whose probe is stuck, a new mount at the same path shows "unavailable" every tick until the app restarts. Rare under the trusted-shares scope; fix would be keying by (device, mount point) (final review, Network share probe).
- Pie text metrics (width, line height) are measured once at construction; changing the Plasma font while the app runs can clip the numbers line until restart. Fix: recompute in `changeEvent(QEvent.FontChange)`; natural to do with the Theme-aware text item (final review, Volume labels).
- A bracketed IPv6 NFS root export (`[::1]:/`) gets a wrong label, because `network_label` splits on the first `:`. Non-root IPv6 exports label correctly by accident. No IPv6 shares here (final review, Volume labels).

## Notes
- TDD scope: core/ strict TDD; ui/ pytest-qt smoke tests only; tray and KWin behavior covered by the manual checklist.
