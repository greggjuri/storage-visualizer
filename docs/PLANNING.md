# Visual Storage Monitor: Project Planning

## Vision

A small always-available window on my Debian desktop that shows every mounted volume, local and network, as a pie chart of used vs free space. It should cost the system next to nothing and never freeze, even when a network share disappears.

## Architecture

```
 Refresher (QTimer 30 s)
      │
      ▼
┌──────────────┐   list[MountInfo]   ┌─────────────────┐ Volume (one at a time) ┌──────────────────────┐
│  Enumerator  │ ──────────────────▶ │   UsageProbe    │ ─────────────────────▶ │     MainWindow       │
│ psutil       │                     │ statvfs per     │                        │ frameless, flow      │
│ all=True +   │                     │ mount in worker │                        │ layout of PieWidgets │
│ own filters, │                     │ thread; busy at │                        │ (one per volume)     │
│ dedupe, label│                     │ tick=unavailable│                        └──────────▲───────────┘
└──────────────┘                     └─────────────────┘                                   │ show/hide
                                                                                ┌──────────┴───────────┐
                                                                                │  TrayIcon (SNI/KDE)  │
                                                                                └──────────────────────┘

core/  (Enumerator, UsageProbe, Volume)  — pure Python, no Qt imports, unit-tested
ui/    (MainWindow, PieWidget, FlowLayout, TrayIcon, Refresher) — PySide6
```

Probe results reach the UI thread through plain `threading.Thread` workers in `core/` (one per mount) that call a callback, plus a queued `ResultBridge` (`Signal(object)` on a UI-thread `QObject`) in `ui/`. See ADR-009. A mount whose probe is still busy at the next tick is reported `unavailable` from `probe_all` on the UI thread, so Qt delivers that one directly; worker results are queued. A late result restores the pie (ADR-011).

Data flows one way: timer tick → enumerate → diff the mount list to add/remove pies → probe; results update pies one volume at a time (ADR-009).

## Tech Stack

- **Platform:** Debian 13 (trixie), KDE Plasma 6, Wayland session. Nothing else is supported.
- **Language:** Python 3.13 (system interpreter)
- **GUI:** PySide6 (Qt 6), native Wayland platform plugin
- **Dependency floors:** `psutil>=6.0` (6.0 dropped the per-mount statvfs in `disk_partitions()`, so enumeration can't hang on a dead mount), `PySide6>=6.8`
- **Disk info:** psutil (mount enumeration), `os.statvfs` (usage), `/dev/disk/by-label` (labels)
- **Tests:** pytest, pytest-qt for widget smoke tests
- **Lint:** ruff excludes `docs/`, because ruff >=0.17 formats Python blocks inside Markdown and would rewrite the docs
- **Install:** pipx from the git repo; XDG autostart `.desktop` file

## Data Models

```python
@dataclass(frozen=True)
class MountInfo:
    device: str          # /dev/nvme0n1p2, server:/export, //nas/share
    mount_point: str
    fstype: str
    is_network: bool

@dataclass(frozen=True)
class Volume:
    mount_point: str     # identity key for diffing
    label: str           # by-label name, else mount point; "/" -> "System"
    fstype: str
    is_network: bool
    status: Literal["ok", "unavailable"]
    total: int | None    # bytes; None when unavailable
    used: int | None
    free: int | None     # space available to unprivileged user (f_bavail)
```

## Volume Rules

- Enumerate with `psutil.disk_partitions(all=True)`. `all=False` drops `nfs`/`cifs` because they are `nodev` filesystems.
- Keep: block devices under `/dev/` and network filesystems (`nfs`, `nfs4`, `cifs`, `smb3`, `fuse.sshfs`).
- Drop: pseudo filesystems (tmpfs, proc, sysfs, overlay, squashfs, efivarfs, etc.), loop devices, and mounts under `/boot`, `/snap`, `/sys`, `/proc`, `/run` (except `/run/media`).
- Dedupe by device: btrfs subvolumes and bind mounts of the same device show once, under the shortest mount point.

## Key Constraints

- Debian 13 + KDE Plasma 6 Wayland only. No portability code.
- Wayland: the app cannot position itself or force always-on-top. Both come from a KWin window rule the user sets once, matched on the app id. The app sets a stable app id (`QGuiApplication.setDesktopFileName("storage-visualizer")`).
- A hung network mount must never block the UI thread or stack up threads (ADR-004, ADR-011).
- Max 500 lines per file
- Conventional commits

## Non-Functional Requirements

- **Resource use:** poll every 30 s; idle CPU effectively zero between polls; no busy loops or file watchers.
- **Responsiveness:** the UI thread never calls `statvfs` directly. A probe still running at the next tick shows its volume as unavailable; a late result restores it.
- **Robustness:** a volume vanishing mid-poll, a dead NFS server or a permission error on one mount degrades that one pie, never the app.

## Testing Approach

- `core/` is fully unit-tested against fake psutil and statvfs data, with no real mounts and no Qt.
- `ui/` gets pytest-qt smoke tests: widgets build, `set_mounts` adds/removes pies, `update_volume` updates them.
- Manual checklist for `docs/TESTING.md` (replaces the web template's DevTools checklist):
  - plug in a USB drive → pie appears within 30 s; unmount → pie disappears
  - stop the NFS/SMB server → that pie shows "unavailable" within one poll, the UI stays responsive, and the thread count stays flat over several polls
  - tray icon shows/hides the window
  - close the window → clean exit; Ctrl+C in the terminal → exits immediately; no traceback either way
  - KWin rule keeps the window on top and in place across logout/login
  - numbers match `df -h` for every shown volume

## Success Criteria

- Every real volume on debian-dev, local and network, shows as one pie with label, used/free and total that match `df -h`.
- Hot-plugged volumes appear and disappear within one poll interval.
- A dead network share never freezes the window.
- Starts on login, lives in the tray, and stays out of the way.
