# Polling Refresh: Design

**Date**: 2026-10-18
**Backlog item**: "Polling refresh" (docs/TASK.md, Next)
**Status**: Approved design (branch feat/polling-refresh)

## Goal

Every 30 s, re-run enumerate and probe, and add, update or remove pies in place by mount point. A hot-plugged drive appears within one poll and disappears within one poll after unmount; existing pies keep their last reading until a new one arrives.

Polling makes ADR-004's no-re-dispatch rule apply, so this feature adds the busy guard: a mount whose previous probe is still running is not probed again.

## Context

- **ADR-003**: enumerate with `psutil.disk_partitions(all=True)` plus our own filters. The psutil call moves into `core/enumerator.py` as `enumerate_system_mounts()`.
- **ADR-004**: no new probe for a mount whose previous probe is outstanding. This feature implements that guard. The 2 s timeout and "unavailable" for stuck probes stay in the Network share probe item.
- **ADR-005**: a `QTimer` fires every 30 s and runs a full enumerate-and-probe cycle. No mount watchers.
- **ADR-009**: plain threads in `core/` call `on_result` from the worker; `ResultBridge.volume_ready` queues delivery to the UI thread. Results arrive one volume at a time.
- **ADR-010** (Proposed, this spec): the refresh cycle is owned by a `ui/` Refresher.
- **PLANNING.md**: Architecture (`core/` has no Qt imports, data flow), Non-Functional Requirements (idle CPU near zero, UI thread never calls `statvfs`), Testing Approach, 500-line file limit.

## Scope

**In scope**
- Busy guard in `core.usage.UsageProbe`
- `enumerate_system_mounts()` in `core/enumerator.py`
- `MainWindow()` without constructor mounts, plus `set_mounts()` that diffs by mount point
- New `ui/refresher.py`: `Refresher` with a 30 s `QTimer` and one `refresh()` used at startup and on every tick
- `ui/app.py` rewired to use the Refresher
- Doc wording fixes in CLAUDE.md, PLANNING.md and TESTING.md (see Doc Changes)

**Out of scope**
- 2 s probe timeout, "unavailable" for stuck probes, network filesystems (Network share probe)
- A mount re-added at the same path while its previous probe is still stuck shows "…" until that probe returns, because the busy guard skips it (ADR-004). The Network share probe item's timeout turns this into "unavailable".
- Quit-time race on the deleted `ResultBridge` (Known Issue, fixed in Network share probe)
- Labels, flow layout, tray, frameless window

## Architecture

```
 app.py: MainWindow(), ResultBridge, Refresher(window, bridge); refresher.start(); window.show()

 Refresher.refresh()   ◀── start() once, then QTimer.timeout every 30 000 ms
   │
   ├─ mounts = enumerate_fn()                   # default: core.enumerator.enumerate_system_mounts
   ├─ window.set_mounts(mounts)                 # add / remove pies by mount point
   └─ probe.probe_all(mounts, bridge.volume_ready.emit)
                    │  skips busy mounts; one daemon thread per started probe
                    ▼
        worker: on_result(probe(m)) ──queued signal──▶ MainWindow.update_volume(volume)
```

Each tick diffs the mount list to add or remove pies; results update pies one volume at a time (ADR-009). `set_mounts` runs before `probe_all`, so a result never targets a pie the current cycle has not created yet.

## core/

### usage.py: busy guard

`UsageProbe.__init__` adds `self._busy: set[str]` (mount points with a probe in flight) and `self._lock = threading.Lock()`. The `statvfs` injection is unchanged.

`probe_all(mounts, on_result) -> list[threading.Thread]`:
- For each mount, under the lock: if `mount.mount_point` is in `_busy`, skip it; otherwise add it.
- Start the daemon thread outside the lock. If `thread.start()` raises, discard the mount point from `_busy` under the lock and re-raise.
- Return only the threads actually started.

Worker body:
```python
try:
    on_result(probe(m, self._statvfs))
finally:
    with self._lock:
        self._busy.discard(m.mount_point)
```

The busy flag clears after delivery, also when `probe` raises a non-`OSError` or `on_result` raises. The exception still reaches `threading.excepthook` (stderr), as today. Side effect: a crashed probe no longer leaves its mount stuck, because the next tick probes it again. The Known Issue stays open since the traceback still only reaches stderr.

`probe()`, `Volume` and the callback-from-worker contract are unchanged.

### enumerator.py: enumerate_system_mounts

```python
def enumerate_system_mounts() -> list[MountInfo]:
    return enumerate_mounts(psutil.disk_partitions(all=True))  # all=True: ADR-003
```

Qt-free and covered by the 100% `core/` gate.

## ui/

### main_window.py

- `MainWindow()` takes no arguments. It builds the existing `QHBoxLayout` (the wrapping layout is the Flow layout item) and the "No volumes found" label, which is always the last widget in the layout; pies are inserted before it.
- `set_mounts(mounts: list[MountInfo])`:
  - **Remove**: each pie whose mount point is not in `mounts` is removed from the layout, `deleteLater()`'d and deleted from `_pies`.
  - **Add**: each new mount point gets a `PieWidget` in loading state, inserted with `layout.insertWidget(i, pie)` where `i` is the number of current pies whose mount point sorts before it (plain string comparison, the same order as `enumerate_mounts`).
  - **Keep**: pies for mount points still present are untouched and keep their widget and last `Volume`, so nothing flickers to "…" on a tick.
  - The empty label is visible exactly when `_pies` is empty.
  - If anything was added or removed, call `adjustSize()` so the window shrinks after an unmount. This is deliberate: `SetFixedSize` on the layout would conflict with the future Flow layout's width-based wrapping.
- `update_volume(volume)` is unchanged: a result for a mount point without a pie is ignored, which covers a late result for a mount removed between dispatch and delivery.
- Identity is the mount point only. A different device mounted at the same path keeps the pie; its numbers update on the next result.

### refresher.py (new)

```python
INTERVAL_MS = 30_000

class Refresher(QObject):
    def __init__(self, window, bridge, probe=None,
                 enumerate_fn=enumerate_system_mounts, parent=None): ...
    timer -> QTimer          # read-only property, for tests
    def start(self): self.refresh(); self._timer.start()
    @Slot()
    def refresh(self):
        mounts = self._enumerate()
        self._window.set_mounts(mounts)
        self._probe.probe_all(mounts, self._bridge.volume_ready.emit)
```

- `QTimer(self)` with `setInterval(INTERVAL_MS)`, `timeout` connected to `refresh`. No separate startup path: `start()` is one `refresh()` and then the timer.
- If `probe` is None, the Refresher builds one `UsageProbe()` in `__init__` and reuses it for the app's lifetime; the busy set only works across ticks through one instance.
- `enumerate_fn` is a single callable, so Refresher tests never touch psutil.
- If `enumerate_fn` raises on a timer tick, PySide prints the traceback, pies stay as they are and the timer keeps running. At startup the exception propagates out of `start()` and the app exits (see Error Handling). No extra handling: psutil ≥6 only reads `/proc/mounts`.

### app.py

```python
window = MainWindow()
bridge = ResultBridge()
bridge.volume_ready.connect(window.update_volume)
refresher = Refresher(window, bridge)   # keep referenced until app.exec() returns
refresher.start()                       # first refresh before show(): window opens at its final size
window.show()
return app.exec()
```

The `psutil` and `enumerate_mounts` imports leave `app.py`.

## Error Handling

| Situation | Behavior |
|---|---|
| `statvfs` raises `OSError` | Volume `unavailable` (unchanged) |
| `probe` raises non-`OSError`, or `on_result` raises | Mount freed in `finally`; exception to `threading.excepthook`; next tick re-probes |
| `thread.start()` raises | Mount freed, exception re-raised to the caller |
| Probe stuck in `statvfs` | Mount stays busy and is skipped each tick; pie keeps its last state ("…" if new) until the call returns |
| Late result for a removed mount | Ignored by `update_volume` |
| `enumerate_fn` raises on a timer tick | Traceback printed by PySide; pies unchanged; timer keeps running |
| `enumerate_fn` raises at startup (`refresher.start()` called directly from `main()`) | Exception propagates and the app exits; intended, since there is nothing to show |

## Testing

### tests/core/test_usage.py (strict TDD)

Fake `statvfs` blocks on a `threading.Event`; no timing assumptions.
1. A second `probe_all` while a mount is blocked skips that mount, still probes the others, and the returned threads exclude the skipped one.
2. After release and join, the mount is probed again on the next `probe_all`.
3. A fake `statvfs` raising `RuntimeError` still frees the mount. `threading.excepthook` is monkeypatched to a collector, which must receive the `RuntimeError` (so pytest's unhandled-thread-exception plugin does not report it).
4. An `on_result` that raises still frees the mount; same excepthook collector assertion.
5. With `threading.Thread.start` monkeypatched to raise, `probe_all` re-raises and the mount is no longer busy (a later `probe_all` with a working `start` probes it).
6. Duplicate mount points in one `probe_all` start one thread.

### tests/core/test_enumerator.py (strict TDD)

7. `enumerate_system_mounts()` calls `psutil.disk_partitions(all=True)` (monkeypatched) and returns the filtered, deduped result.

### tests/ui/test_main_window.py (pytest-qt smoke)

Existing tests migrate to `MainWindow()` plus `set_mounts(...)`, keeping one-pie-per-mount, ordering, update, unknown-mount, empty-message and bridge coverage. New:
8. Start with `/` and `/home`; `set_mounts` with `/`, `/data`, `/home` gives layout order `/`, `/data`, `/home`, then the label.
9. Removing `/data` removes its pie from `pies` and the layout; the `/` and `/home` pies are the same objects and keep their `Volume`.
10. The empty label is visible with no mounts, hidden with pies, visible again after all are removed.
11. `update_volume` for a removed mount point does not raise and creates no pie.

### tests/ui/test_refresher.py (pytest-qt smoke)

Fake `enumerate_fn`, fake window and fake probe append to one shared call log where ordering matters; no psutil, no real timer waits.
12. `timer.interval() == 30_000`; emitting `timer.timeout` manually calls `refresh` (seen as a fake `enumerate_fn` call).
13. `refresh()` calls `set_mounts(mounts)` before `probe_all(mounts, bridge.volume_ready.emit)` (asserted from the shared call log).
14. With a real `MainWindow`: two `refresh()` calls with different mount lists add and remove pies; a volume passed synchronously to `on_result` updates the matching pie.
15. `start()` calls `refresh()` exactly once and leaves the timer active (stopped at teardown).
16. Without an injected probe: `UsageProbe` in `storage_visualizer.ui.refresher` is monkeypatched with a counting stub; two `refresh()` calls construct it once.

### Gates

- `pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100`
- `ruff check . && ruff format --check .`
- Every file under 500 lines.

### Manual checklist: STOP, human hand-off

The agent cannot see the window. The plan stops here; the human runs the checks and reports pass/fail, and the agent records the result. Expectations are rules, not a snapshot of this machine.

Commands:
- Threads: `watch -n5 'ps -o nlwp= -p $(pgrep -f storage_visualizer)'`
- CPU: `pidstat -p $(pgrep -f storage_visualizer) 5` (sysstat), or `top -p $(pgrep -f storage_visualizer)`
- USB: mount through the KDE device notifier, confirm the path with `findmnt`
- Numbers: `df -h`

Checks:
- [ ] Every shown pie matches `df -h` for its mount point; each mounted local block device outside the filtered trees has exactly one pie, in mount-point order.
- [ ] USB drive mounted: within 30 s a pie appears in its sorted position. Unmounted: within 30 s the pie disappears and the window shrinks.
- [ ] Existing pies don't flicker to "…" on a tick; their numbers follow a large file copy within one poll.
- [ ] Over several polls the thread count returns to its baseline between polls.
- [ ] Idle CPU is effectively zero between polls; no tracebacks in the terminal.
- N/A on this branch: dead NFS/SMB share (network mounts not enumerated yet), tray, KWin rule.

## Doc Changes

**In the implementation plan (a `docs:` task):**
- `CLAUDE.md`
  - Conventions: replace "`ui/` gets a fresh `list[Volume]` each poll and diffs by `mount_point`" with "each tick diffs the mount list to add/remove pies; results update pies one volume at a time (ADR-009)".
  - TDD scope, `ui/` bullet: add `Refresher`; "pies update from a `list[Volume]`" becomes "`set_mounts` adds/removes pies, `update_volume` updates them".
- `docs/PLANNING.md`
  - Data flow line: "timer tick → enumerate → diff the mount list to add/remove pies → probe; results update pies one volume at a time (ADR-009)".
  - Diagram: `QTimer (30 s)` becomes `Refresher (QTimer 30 s)`; the probe→window arrow label `list[Volume]` becomes `Volume (one at a time)`; `Refresher` joins the `ui/` list.
  - Testing Approach: same wording fix as CLAUDE.md's TDD scope.
- `docs/TESTING.md`
  - Setup: the thread, CPU and USB commands above.
  - Checklist: "existing pies don't flicker to '…' on a tick" and "thread count returns to baseline between polls".
  - `ui/` smoke-test example: `MainWindow()` plus `set_mounts(...)` instead of `MainWindow(mounts)`.

**At finish, on the branch, via `ce-superpowers:recording-decisions`:**
- `docs/DECISIONS.md`: ADR-010 recorded with status Accepted.
- `docs/TASK.md`: check off Polling refresh; under the non-`OSError` Known Issue note that the busy guard's `finally` now lets the next tick re-probe, but the traceback still only reaches stderr; promote Network share probe into Next.
- `docs/PILOT-FINDINGS.md`: any new rows from planning and execution.

## Decisions Recorded on This Branch

### ADR-010 (Proposed): Refresh cycle owned by a ui/ Refresher

**Context**: Polling (ADR-005) needs something that owns the 30 s `QTimer` and runs enumerate → diff → probe on startup and on every tick. `core/` can't hold a `QTimer`, and `MainWindow` is a view.

**Decision**: A `Refresher(QObject)` in `ui/refresher.py` owns the timer and a single `UsageProbe`, takes the enumerate step as one callable (default `core.enumerator.enumerate_system_mounts`), and exposes `refresh()` (used at startup and on every tick) and `start()`.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| `Refresher` in `ui/` | `MainWindow` stays a plain view; cycle testable with fakes and no timer waits | One more small class | Accepted (on finish) |
| Timer and `refresh()` in `MainWindow` | Fewer classes | View takes on enumeration and probing; widget tests need psutil and probe fakes | Rejected |
| `threading.Timer` loop in `core/` | Qt-free | Contradicts ADR-005 (`QTimer`); needs a second thread-to-Qt path | Rejected |

**Consequences**: Positive: clear seams (`enumerate_fn`, `probe`, window, bridge) and a one-line `app.py` start. Negative: the Refresher must outlive `app.exec()`, so `app.py` keeps it referenced.
