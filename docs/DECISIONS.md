# Visual Storage Monitor: Architecture Decisions

## ADR-001: Target Debian 13 with KDE Plasma 6 on Wayland only

**Date**: 2026-10-17
**Status**: Accepted

### Context
The app is for one workstation (debian-dev). Supporting macOS and Windows as well would mean multiple tray, window and disk-enumeration code paths.

### Decision
Support only Debian 13 (trixie), KDE Plasma 6, Wayland session.

### Rationale
- It's the only machine the app is for.
- KDE has a native system tray (StatusNotifierItem), so no extensions are needed.
- Dropping portability removes the hardest parts of the design.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| macOS + Debian + Windows | Runs on every machine I use | Three tray/window/disk paths, three test setups | Rejected |
| Any Linux desktop | Wider reuse | GNOME has no tray without an extension; DE-specific window behavior | Rejected |
| Debian 13 + KDE Wayland | One target, native tray | Not portable | Accepted |

### Consequences
**Positive:** One code path, no platform abstraction layer.
**Negative:** Porting later means revisiting the window, tray and volume-filter decisions.

### References
- Planning chat, 2026-10-17

---

## ADR-002: Python 3.13 with PySide6

**Date**: 2026-10-17
**Status**: Accepted

### Context
Needs a GUI toolkit with a frameless window, system tray and custom drawing that works natively on KDE Wayland.

### Decision
Python 3.13 (Debian system interpreter) with PySide6 (Qt 6), using the native Wayland platform plugin.

### Rationale
- Python is my main language; psutil already covers mount enumeration.
- KDE is Qt-native: tray, Wayland and HiDPI fractional scaling all just work.
- PySide6 is LGPL and pip-installable.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Tauri (Rust + web UI) | Small binary, easy pretty charts | New toolchain on a process pilot | Rejected |
| GTK4 / PyGObject | Native on GNOME | Foreign on KDE, tray needs extra libs | Rejected |
| Plasma plasmoid (QML) | A real KDE desktop widget | Tied to Plasma APIs, QML, harder to test | Rejected |
| PySide6 | Native on KDE, Python | pip wheel is large (~200 MB) and won't inherit Breeze theming | Accepted |

### Consequences
**Positive:** Single language, testable core, good Wayland support.
**Negative:** Heavy dependency for a small app. Pies are custom-painted anyway, so theming barely matters.

### References
- Planning chat, 2026-10-17

---

## ADR-003: Enumerate mounts with psutil all=True and our own filters

**Date**: 2026-10-17
**Status**: Accepted

### Context
"Every connected storage device" has to include network shares and exclude pseudo, system and duplicate mounts. `psutil.disk_partitions(all=False)` drops NFS and CIFS because they're `nodev` filesystems.

### Decision
Call `disk_partitions(all=True)` and filter it ourselves:
- **Keep:** `/dev/` block devices and network filesystems (nfs, nfs4, cifs, smb3, fuse.sshfs).
- **Drop:** pseudo filesystems, loop devices, and system mount trees.
- **Dedupe** by device, keeping the shortest mount point.

### Rationale
- It's the only way to get network shares from psutil.
- An explicit filter is unit-testable against fixture mount tables.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| psutil all=False | Zero filtering code | Loses network shares | Rejected |
| UDisks2 over D-Bus | Rich metadata, labels | No network mounts; adds a D-Bus dependency | Rejected |
| Parse /proc/self/mountinfo directly | No dependency | Reimplements psutil | Rejected |

### Consequences
**Positive:** One source for local and network mounts; the filter is plain data plus tests.
**Negative:** The filter lists need maintaining when a new filesystem type shows up.

### References
- Planning chat, 2026-10-17

---

## ADR-004: Probe usage in per-mount worker threads with timeout, no re-dispatch while stuck

**Date**: 2026-10-17
**Status**: Accepted

### Context
`statvfs()` on a hard-mounted NFS share whose server is gone blocks in uninterruptible kernel sleep. It can't be cancelled, only abandoned.

### Decision
Each mount's `statvfs` runs in its own worker thread, and the poller waits up to 2 s before marking that volume `unavailable`. Then:
- While a mount's previous probe is still outstanding, no new probe is started for it; it stays `unavailable`.
- When the stuck call finally returns, the mount becomes eligible again.

### Rationale
- The UI thread never blocks.
- A permanently dead mount costs exactly one parked thread, not one per poll.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| statvfs on UI thread | Simplest | One dead share freezes the app | Rejected |
| New thread every poll + timeout | Simple | Leaks a thread every 30 s per dead mount | Rejected |
| Subprocess per probe | Killable from our side | Process can still hang in D-state; spawn cost every poll | Rejected |

### Consequences
**Positive:** Bounded resource use, UI always responsive.
**Negative:** A recovered share shows `unavailable` until its stuck call returns.

### References
- Planning chat, 2026-10-17

---

## ADR-005: Poll every 30 s instead of watching for mount events

**Date**: 2026-10-17
**Status**: Accepted

### Context
Volumes come and go (USB, network), and usage changes. The app must add negligible system load.

### Decision
A `QTimer` fires every 30 s and runs a full enumerate-and-probe cycle. There are no udev, inotify or D-Bus watchers.

### Rationale
- One code path for both "mounts changed" and "usage changed".
- 30 s latency is fine for a glanceable monitor.
- The polling cost is a few syscalls.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Poll /proc/mounts changes + 30 s usage | Instant hot-plug | Two paths, more state | Rejected |
| UDisks2 signals | Instant, rich events | No network mounts, D-Bus dependency | Rejected |

### Consequences
**Positive:** Simple and testable, with near-zero idle cost.
**Negative:** Up to 30 s before a new drive appears.

### References
- Planning chat, 2026-10-17

---

## ADR-006: Frameless window plus tray icon; on-top and position via KWin window rule

**Date**: 2026-10-17
**Status**: Accepted

### Context
I want a small frameless window that stays put and on top, with a tray icon to show and hide it. On Wayland, clients cannot position themselves, and Qt's stay-on-top hint is ignored.

### Decision
- Run natively on Wayland with a frameless window, using `startSystemMove()` for dragging.
- Add a `QSystemTrayIcon` with show/hide and Quit.
- The app sets the stable app id `storage-visualizer`.
- "Keep above" and position come from a KWin window rule the user creates once; the README documents it.

### Rationale
- Native Wayland stays sharp at fractional scaling (1.45 on the main 4K display).
- KWin rules are the Plasma-sanctioned way to pin a window.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Force XWayland (`QT_QPA_PLATFORM=xcb`) | App controls on-top and position | Blurry at fractional scaling; X11 behavior I moved away from | Rejected |
| True desktop widget (plasmoid) | Native widget behavior | See ADR-002 | Rejected |

### Consequences
**Positive:** Clean app code, crisp rendering.
**Negative:** A manual one-time KWin rule; window placement isn't reproducible from the app alone.

### References
- Planning chat, 2026-10-17

---

## ADR-007: Install with pipx and start via XDG autostart

**Date**: 2026-10-17
**Status**: Accepted

### Context
The app is for a single machine and needs to start on login.

### Decision
- Install with `pipx install git+https://github.com/greggjuri/storage-visualizer`.
- A console entry point launches the app.
- An XDG autostart `.desktop` file starts it on login, and its file name matches the app id.

### Rationale
- Isolated environment, trivial upgrade (`pipx upgrade`), no packaging work.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| .deb package | System-native install | Packaging effort for one machine | Rejected |
| PyInstaller binary | No Python needed | Large, pointless when Python 3.13 is present | Rejected |

### Consequences
**Positive:** Zero packaging overhead.
**Negative:** The ~200 MB PySide6 wheel lives in the pipx venv.

### References
- Planning chat, 2026-10-17

---

## ADR-008: Draw pies with QPainter rather than QtCharts

**Date**: 2026-10-17
**Status**: Proposed

### Context
Each volume needs a small pie (used/free) with text. QtCharts can do it, but it is a heavy module, and Qt 6 is steering toward Qt Graphs.

### Decision
A custom `PieWidget` painting two arcs with `QPainter`, plus labels.

### Rationale
- About 50 lines, no extra Qt module, and full control over look and the "unavailable" state.

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| QtCharts QPieSeries | Built-in legend, hover | Heavy, legacy path in Qt 6 | Proposed reject |
| Qt Graphs | Current Qt direction | Overkill for a two-slice pie | Proposed reject |

### Consequences
**Positive:** Lightweight, easy to test with pytest-qt.
**Negative:** Hover and animation are on us if ever wanted.

### References
- Planning chat, 2026-10-17; settle in brainstorming for the first feature

---

## Template for New Decisions

```markdown
## ADR-XXX: Title

**Date**: YYYY-MM-DD  
**Status**: Proposed/Accepted/Deprecated/Superseded

### Context
What is the issue that we're seeing that is motivating this decision?

### Decision
What is the change that we're proposing and/or doing?

### Rationale
Why is this the best choice? What alternatives were considered?

### Alternatives Considered (optional)
| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Option A | ... | ... | Selected/Rejected |

### Consequences
What becomes easier or more difficult because of this change?

**Positive:**
- Benefit 1
- Benefit 2

**Negative:**
- Tradeoff 1
- Tradeoff 2

### References (optional)
- Spec: `docs/superpowers/specs/YYYY-MM-DD-xxx-design.md`
- Plan: `docs/superpowers/plans/YYYY-MM-DD-xxx.md`
- External: [link]
```

---

## ADR Status Definitions

| Status | Meaning |
|--------|---------|
| **Proposed** | Under discussion, not yet approved |
| **Accepted** | Approved and in effect |
| **Deprecated** | No longer recommended, but may still be in use |
| **Superseded** | Replaced by another ADR (link to replacement) |

## When to Create an ADR

Create an ADR when:
- Choosing between multiple valid approaches
- Making a decision that's hard to reverse
- Setting a pattern others should follow
- Explicitly rejecting an approach
- Learning something that changes future decisions

## ADR Numbering

- Use sequential numbers: ADR-001, ADR-002, etc.
- Never reuse numbers, even for superseded ADRs
- Reference superseded ADRs: "Supersedes ADR-003"

## Key Principles Captured in ADRs

{As you make decisions, summarize key principles here}

1. **{Principle 1}**: {Brief explanation}
2. **{Principle 2}**: {Brief explanation}
3. **{Principle 3}**: {Brief explanation}
