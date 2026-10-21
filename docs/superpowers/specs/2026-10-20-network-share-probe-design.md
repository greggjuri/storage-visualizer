# Network Share Probe: Design

**Date**: 2026-10-20
**Backlog item**: "Network share probe" (docs/TASK.md, Next)
**Status**: Approved, not yet implemented (branch feat/network-share-probe)

## Goal

Network shares (NFS, SMB, sshfs) show as pies alongside local volumes. Shares are trusted to be available, so there is no probe timeout. If a share's previous probe is still running when the next tick arrives, its pie shows "unavailable". When that slow probe finally returns, its result restores the pie. The quit-time race on the deleted `ResultBridge` is fixed.

## Context

- **ADR-003** (Accepted, unchanged): `psutil.disk_partitions(all=True)` plus our own filters. Network keep-list is `nfs`, `nfs4`, `cifs`, `smb3`, `fuse.sshfs`. PLANNING.md Volume Rules is unchanged.
- **ADR-004** (Accepted → **Superseded by ADR-011** on this branch): the busy guard (no re-dispatch while a probe is outstanding) stays; the 2 s wait is dropped. The 2 s wait was never implemented, so dropping it changes docs, not code.
- **ADR-005**: 30 s `QTimer` poll; the tick is what detects a stuck probe.
- **ADR-009**: plain threads in `core/` call `on_result`; `ResultBridge.volume_ready` queues worker results to the UI thread. This design adds a second delivery path: "unavailable" volumes emitted from `probe_all` on the UI thread, which Qt delivers directly.
- **ADR-010**: the `Refresher` owns the timer and the single `UsageProbe`; it gains `stop()`.
- **PLANNING.md**: Architecture diagram, Key Constraints (hung mount must not block the UI thread or stack threads), Non-Functional Requirements (Responsiveness), Testing Approach, 500-line limit.

## Scope

**In scope**
- Network filesystems in `core/enumerator.py`, with `is_network=True`
- `UsageProbe.probe_all` reports "unavailable" for a mount that is still busy
- Worker result delivery and busy-flag release made atomic under the probe's lock
- `UsageProbe.close()`, `Refresher.stop()`, wired to `QApplication.aboutToQuit` (quit-time race fix)
- ADR-011, ADR-004 marked superseded, PLANNING.md updates, TASK.md Known Issues

**Out of scope**
- Any probe timeout or cancelling a stuck `statvfs`
- Showing network pies differently from local ones (`is_network` is set but not rendered yet)
- Labels, flow layout, tray, frameless window
- Process exit stalling on a dead hard-mounted NFS share (accepted Known Issue, see Error Handling)

## Architecture

```
 Refresher.refresh()  (UI thread, start() then every 30 s)
   ├─ mounts = enumerate_fn()            # now includes nfs/nfs4/cifs/smb3/fuse.sshfs
   ├─ window.set_mounts(mounts)
   └─ probe.probe_all(mounts, bridge.volume_ready.emit)
         for each mount, under lock:
           busy?  → on_result(unavailable(mount))   # UI thread → Qt direct call → update_volume
           idle?  → mark busy, start worker
                         │
                         ▼
         worker: vol = probe(mount)                  # may block for a long time; no lock held
                 under lock: busy.discard(mount); if not closed: on_result(vol)
                                                     # worker thread → Qt queued → update_volume

 app.aboutToQuit → Refresher.stop(): timer.stop(); probe.close()
```

## core/

### enumerator.py: network filesystems

- Add `NETWORK_FSTYPES = frozenset({"nfs", "nfs4", "cifs", "smb3", "fuse.sshfs"})` (ADR-003).
- In `enumerate_mounts`, a partition whose `fstype` is in `NETWORK_FSTYPES` skips the `/dev/` and loop checks and is kept with `is_network=True`. The system-tree filter and dedupe by device still apply to it (the device string is `server:/export` or `//host/share`).
- Everything else that isn't on `/dev/` is still dropped, including `fuse.portal` and `fuse.gvfsd-fuse`.
- Local mounts keep `is_network=False`.

### usage.py: unavailable when busy, atomic delivery, close

New helper `unavailable(mount) -> Volume`, which builds the same `Volume` as `probe()`'s `OSError` branch. `probe()` uses it, so there's a single place that defines an unavailable volume.

`UsageProbe` state: `_busy: set[str]`, `_closed: bool = False`, `_lock = threading.Lock()` (not reentrant).

`probe_all(mounts, on_result) -> list[threading.Thread]`:
- If `_closed`, return `[]` without calling `on_result`.
- For each mount, under the lock:
  - busy → call `on_result(unavailable(mount))` **while holding the lock**, start no thread.
  - idle → add to `_busy`.
- Start the daemon thread outside the lock. If `start()` raises, discard from `_busy` under the lock and re-raise (as today).
- Duplicate mount points within one call: the first starts a thread, and later ones see it busy and report unavailable. This is acceptable since the enumerator dedupes, but the existing test changes accordingly.
- Returns only the threads actually started.

Worker body:
```python
vol = None
try:
    vol = probe(mount, self._statvfs)
finally:
    with self._lock:
        self._busy.discard(mount.mount_point)
        if vol is not None and not self._closed:
            on_result(vol)
```
A non-`OSError` from `probe` still frees the mount and reaches `threading.excepthook` (unchanged). An exception from `on_result` propagates out of the `with` block, so the lock is released, and then reaches `threading.excepthook`.

**Why under the lock.** The tick's busy check and the worker's release-and-deliver are serialized. Any "unavailable" for a mount is passed to `on_result` before that mount's late real result, so a share that answers just as a tick arrives can't have its fresh result overwritten by a stale "unavailable" for 30 s.

`close()`: under the lock, set `_closed = True`. After `close()` returns, `on_result` is never called again from any thread. A worker that is mid-delivery finishes before `close()` acquires the lock.

**Docstring contract (on `UsageProbe` / `probe_all`):** "unavailable" volumes are emitted from `probe_all` on the calling thread (the UI thread). Qt therefore delivers them to `MainWindow.update_volume` directly, not queued, while the probe's lock is held. Worker results are also emitted under the lock, and Qt queues them. So `on_result` must be quick and must never call into this `UsageProbe` from either thread, or it deadlocks.

## ui/

### refresher.py

`stop()`: stops the timer and calls `self._probe.close()`. It's idempotent, since `QTimer.stop()` and `close()` can both be called twice.

### app.py

After the Refresher is created: `app.aboutToQuit.connect(refresher.stop)`. `aboutToQuit` fires on the UI thread before `app.exec()` returns and before the bridge is torn down, so no worker can emit on a deleted `ResultBridge` afterwards. Disconnecting the signal instead would not fix this, because emitting on an already-deleted C++ object raises regardless.

### main_window.py, bridge.py, pie_widget.py

Unchanged. `PieWidget` already renders `status == "unavailable"`; `update_volume` already ignores unknown mount points.

## Error Handling

| Situation | Behavior |
|---|---|
| `statvfs` raises `OSError` | Volume `unavailable` (unchanged) |
| Probe still busy at the next tick | `unavailable` emitted for it from `probe_all`; no new thread |
| Busy probe returns later | Mount freed and its real result delivered; pie recovers. The next tick probes it again |
| Share stuck on its very first probe | Pie shows "…" until the next tick, then "unavailable" (up to 30 s) |
| `probe` raises non-`OSError` | Mount freed, no result; traceback to `threading.excepthook`; next tick re-probes. The non-OSError Known Issue still applies |
| `on_result` raises | Lock released, mount freed; traceback to `threading.excepthook` |
| Result after quit | Suppressed by `close()` via `aboutToQuit` |
| Hard-mounted NFS share dead at quit | Process exit can stall: a daemon thread sits in uninterruptible sleep in `statvfs`. Accepted because shares are trusted to be available; recorded in TASK.md Known Issues |

## Testing

### tests/core/test_enumerator.py (strict TDD)

1. `nfs`, `nfs4`, `cifs`, `smb3` and `fuse.sshfs` mounts (`server:/export`, `//nas/share`, `user@host:/`) are kept with `is_network=True`; local mounts keep `is_network=False`.
2. `fuse.portal` and `fuse.gvfsd-fuse` (non-`/dev/` devices) are dropped. This replaces `test_drops_non_dev_devices_including_network`.
3. Network mounts still go through the system-tree filter (e.g. `nfs` at `/run/user/1000/x` dropped) and dedupe by device (same `server:/export` at two mount points shows once, under the shorter one).

### tests/core/test_usage.py (strict TDD)

The fake `statvfs` blocks on a `threading.Event`, so no test depends on timing.

4. `unavailable(mount)` matches `probe()`'s `OSError` result.
5. A second `probe_all` while a mount is blocked calls `on_result` with `unavailable` for that mount (synchronously, before `probe_all` returns), probes the others, and returns no thread for it. This updates `test_probe_all_skips_busy_mount_but_probes_others`.
6. Late result recovers: after the unavailable report, release the event; the next `on_result` for that mount is the `ok` volume, and the mount is probed again on the next `probe_all`.
7. Ordering: pause the worker inside `on_result` (the callback blocks on a second event while the worker holds the lock), then start `probe_all` for the same mount on another thread. That `probe_all` can't run its busy check until the worker's delivery finishes. When it does, the mount is idle, so it starts a fresh probe instead of reporting unavailable. The recorded results contain no `unavailable` after the `ok`. This pins down the "stale unavailable never follows a fresh result" rule.
8. `close()`: a worker released after `close()` doesn't call `on_result`; `probe_all` after `close()` returns `[]` and doesn't call `on_result`.
9. Duplicate mount points in one call start one thread and report one `unavailable` (updated from today's test).
10. `test_stuck_mount_costs_one_thread_over_many_polls` keeps its thread-count assertion and also asserts one `unavailable` per later poll.
11. The existing tests (non-`OSError` frees mount, raising `on_result` frees mount, `start()` failure frees mount) keep passing under the new worker body.

### tests/ui/test_refresher.py (pytest-qt smoke)

12. `stop()` stops the timer and calls `close()` on the injected probe. A second `stop()` doesn't raise.
13. **No-deadlock path**: a real `UsageProbe` with a blocking fake `statvfs`, a real `ResultBridge` connected to a real `MainWindow.update_volume`, and a mount set via `set_mounts`.
    - First `probe_all` starts the blocked worker.
    - Second `probe_all` on the UI thread returns (guarded by `faulthandler.dump_traceback_later(5, exit=True)`, so a deadlock kills the run with a stack dump instead of hanging it; cancelled at the end), and the pie's volume is `unavailable` immediately after it returns, which proves direct delivery under the lock.
    - Release the event; `qtbot.waitUntil` sees the pie go to `ok`.

### Gates

- `pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100`
- `ruff check . && ruff format --check .`
- Every file under 500 lines.

### Manual checklist: STOP, human hand-off

The agent cannot see the window. The plan stops here, the human runs the checks and reports pass/fail, and the agent records the result. Expectations are stated as rules, not as a snapshot of this machine.

- [ ] Every mounted network share of a kept fstype (`findmnt -t nfs,nfs4,cifs,smb3,fuse.sshfs`) has exactly one pie, and its numbers match `df -h`.
- [ ] Local pies are unchanged and still match `df -h`.
- [ ] Quit (Ctrl+C, or close the window) exits with no traceback in the terminal.
- [ ] No tracebacks over several polls.
- **Not run on this branch, covered by unit tests:** stopping the NFS/SMB server ("unavailable" within one poll, flat thread count). Shares are trusted to be available, so the human won't take them offline.
- N/A: tray, KWin rule.

## Doc Changes

**In the implementation plan (a `docs:` task):**
- `docs/PLANNING.md`
  - Diagram: the UsageProbe box's "2 s timeout" becomes "busy at next tick → unavailable".
  - Non-Functional Requirements, Responsiveness: drop "A full refresh, including timeouts, finishes within about 3 s." Replace it with "A probe still running at the next tick shows its volume as unavailable; a late result restores it."
  - Architecture paragraph: note that "unavailable" for busy mounts is emitted from the UI thread (direct delivery), and worker results are queued.
- `docs/TESTING.md`: checklist line "Stop the NFS/SMB server → that pie shows 'unavailable' within one poll" stays, with "(within one poll after the probe hangs)"; Common Bugs gains a "Stale 'unavailable' after recovery" row (fix pattern: deliver under the probe lock, ADR-011).
- `CLAUDE.md`: Conventions line about ADR-004 becomes "The UI thread never calls `statvfs` (ADR-004, ADR-011)".
- `docs/DECISIONS.md` "Key Principles" #2: "usage probes run in per-mount workers; a probe still busy at the next tick reports unavailable (ADR-011)".

**At finish, via `ce-superpowers:recording-decisions`:**
- `docs/DECISIONS.md`: ADR-011 Accepted; ADR-004 status → "Superseded by ADR-011".
- `docs/TASK.md`:
  - Check off Network share probe.
  - Remove the quit-time race from Known Issues.
  - Add a Known Issue: "A hard-mounted NFS share that is dead at quit can stall process exit (daemon thread in uninterruptible sleep in statvfs). Accepted: shares are trusted to be available (ADR-011)."
  - Promote the top Backlog item into Next.
- `docs/PILOT-FINDINGS.md`: any new rows.

## Decisions Recorded on This Branch

### ADR-011 (Proposed): No probe timeout; a probe still busy at the next tick reports unavailable

**Supersedes**: ADR-004

**Context**: ADR-004 planned a 2 s wait per probe before marking a volume unavailable. The network shares on this machine are trusted to be available. A timeout adds a second clock next to the 30 s tick, and a stuck `statvfs` can't be cancelled anyway.

**Decision**:
- No timeout. Each mount's `statvfs` runs in its own daemon thread (as before).
- At each tick, a mount whose previous probe is still outstanding gets no new probe and is reported `unavailable` from `probe_all`.
- When the stuck call returns, its result is delivered (the pie recovers) and the mount becomes eligible again.
- The busy-flag release and result delivery happen under the same lock as the tick's busy check, so a stale "unavailable" never overwrites a fresh result.
- `close()` (on `aboutToQuit`) suppresses all later deliveries.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Busy at next tick → unavailable, late result recovers | One clock (the tick); no timer per probe; recovery is automatic | Hang detection takes up to 30 s; `on_result` runs under the probe lock | Accepted (on finish) |
| 2 s wait per probe (ADR-004) | Fast detection | Second timing mechanism; refresh waits on the slowest mount; nothing to gain for trusted shares | Rejected |
| Subprocess per probe | Killable from our side | Can still hang in D-state; spawn cost every poll (rejected in ADR-004 too) | Rejected |

**Consequences**:
- **Positive:** Simpler probe, no timer threads; a recovered share shows correct numbers as soon as its call returns.
- **Negative:** A share that hangs on its first probe shows "…" for up to 30 s before "unavailable". `on_result` must be quick and must not re-enter the probe. A dead hard-mounted NFS share can stall process exit.
