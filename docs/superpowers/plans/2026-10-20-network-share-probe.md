# Network Share Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Task 5 is a STOP, human hand-off: a sanctioned stop for inline execution too (PILOT-FINDINGS E7). The final branch review may run while the human does the check.

**Goal:** Show NFS/SMB/sshfs shares as pies. A probe still busy at the next tick reports "unavailable", and a late result restores the pie. Also fix the quit-time race and make Ctrl+C exit at once.

**Architecture:** The enumerator keeps ADR-003's network fstypes. `UsageProbe.probe_all` reports `unavailable(mount)` for busy mounts, synchronously on the calling (UI) thread and under the probe's lock. Workers release the busy flag and deliver their result under the same lock, and `close()` suppresses all later deliveries. `Refresher.stop()` (on `aboutToQuit`) closes the probe. `main()` restores `SIG_DFL` for SIGINT.

**Tech Stack:** Python 3.13, PySide6, psutil, pytest, pytest-qt

**Spec:** `docs/superpowers/specs/2026-10-20-network-share-probe-design.md`. Read it with this plan, in particular "core/ → usage.py" (worker body, why under the lock, docstring contract) and "Doc Changes".

## Global Constraints

- `core/` never imports Qt.
- The UI thread never calls `statvfs` (ADR-004, ADR-011).
- 100% line coverage on `storage_visualizer.core`; `ui/` gets smoke tests only.
- Max 500 lines per file; ruff line length 100.
- Conventional commits: `feat:` `fix:` `refactor:` `docs:` `test:`.
- Network keep-list, verbatim: `nfs`, `nfs4`, `cifs`, `smb3`, `fuse.sshfs` (ADR-003, unchanged).
- No probe timeout, no wake-up timer for signals (idle CPU near zero).
- Tests order threads with `threading.Event` handshakes, never sleeps. The only short timeout allowed is a `join(0.2)` used to assert that a thread is still blocked.

## Review Focus

1. A share that answers exactly as a tick arrives must not end up with a stale "unavailable" over its fresh result. Pinned by Task 2 `test_fresh_result_is_never_followed_by_stale_unavailable`.
2. Quitting while a probe is blocked: the worker returns after `close()` and must not emit. Pinned by Task 2 `test_close_suppresses_late_results_and_new_probes`.
3. Two exports from the same NFS server (`host:/volume1/media`, `host:/volume2/media-4k`) are two pies, not deduped by host. Pinned by Task 1 `test_two_exports_from_one_server_are_two_mounts`.
4. A share returning `ESTALE`/`EIO` (an errno `OSError`, not a subclass) shows unavailable right away and is probed again next tick. Pinned by Task 2 `test_errno_oserror_is_unavailable_and_mount_reprobed`.
5. Direct delivery of "unavailable" on the UI thread under the lock must not deadlock through the real bridge and window. Pinned by Task 3 `test_busy_share_unavailable_then_recovers_through_real_bridge`.

---

### Task 1: Network filesystems in the enumerator

**Files:**
- Modify: `storage_visualizer/core/enumerator.py`
- Test: `tests/core/test_enumerator.py`

**Interfaces:**
- Produces: `NETWORK_FSTYPES: frozenset[str]` in `core.enumerator`; `enumerate_mounts()` returns network mounts with `is_network=True`.

- [ ] **Step 1: Write the failing tests.** Delete `test_drops_non_dev_devices_including_network` and add:

```python
@pytest.mark.parametrize(
    "device,fstype",
    [
        ("server:/export", "nfs"),
        ("server:/export", "nfs4"),
        ("//nas/share", "cifs"),
        ("//nas/share", "smb3"),
        ("user@host:/", "fuse.sshfs"),
    ],
)
def test_keeps_network_filesystems_flagged(device, fstype):
    [m] = enumerate_mounts([Part(device, "/mnt/net", fstype, "")])
    assert m == MountInfo(device, "/mnt/net", fstype, True)


def test_local_mounts_not_flagged_network():
    [m] = enumerate_mounts([Part("/dev/sdd1", "/mnt/backup", "ext4", "")])
    assert m.is_network is False


@pytest.mark.parametrize(
    "device,fstype",
    [("portal", "fuse.portal"), ("gvfsd-fuse", "fuse.gvfsd-fuse"), ("tmpfs", "tmpfs")],
)
def test_drops_other_non_dev_devices(device, fstype):
    assert mps([Part(device, "/mnt/x", fstype, "")]) == []


def test_network_mounts_respect_system_trees():
    assert mps([Part("server:/export", "/run/user/1000/x", "nfs", "")]) == []


def test_network_mounts_dedupe_by_device():
    parts = [
        Part("server:/export", "/mnt/nfs/deep", "nfs", ""),
        Part("server:/export", "/mnt/nfs", "nfs", ""),
    ]
    assert mps(parts) == ["/mnt/nfs"]


def test_two_exports_from_one_server_are_two_mounts():
    parts = [
        Part("192.168.1.184:/volume1/media", "/mnt/nas-media", "nfs", ""),
        Part("192.168.1.184:/volume2/media-4k", "/mnt/nas-media-4k", "nfs", ""),
    ]
    assert mps(parts) == ["/mnt/nas-media", "/mnt/nas-media-4k"]
```

- [ ] **Step 2: Run** `pytest tests/core/test_enumerator.py -v`. Expected: the network-kept, dedupe and two-exports tests FAIL (empty result); the drop tests pass.

- [ ] **Step 3: Implement.** Add `NETWORK_FSTYPES = frozenset({"nfs", "nfs4", "cifs", "smb3", "fuse.sshfs"})`. In `enumerate_mounts`, `is_network = part.fstype in NETWORK_FSTYPES`. When it's set, skip the `/dev/` and `/dev/loop` checks. The pseudo-fstype, system-tree and dedupe logic applies to all mounts. Store the flag so `MountInfo(..., is_network)` is built from it, for example by keeping `best[device] = (part, is_network)` or by recomputing it from `p.fstype` when the list is built.

- [ ] **Step 4: Run** `pytest tests/core/test_enumerator.py -v`. Expected: all PASS.

- [ ] **Step 5: Commit** `git commit -am "feat: enumerate network shares (nfs, nfs4, cifs, smb3, fuse.sshfs)"`

---

### Task 2: UsageProbe reports busy mounts unavailable, delivers atomically, closes

**Files:**
- Modify: `storage_visualizer/core/usage.py`
- Test: `tests/core/test_usage.py`

**Interfaces:**
- Produces:
  - `unavailable(mount: MountInfo) -> Volume` (module function in `core.usage`).
  - `UsageProbe.probe_all(mounts, on_result) -> list[threading.Thread]`, same signature, new busy behavior.
  - `UsageProbe.close() -> None`.

- [ ] **Step 1: Write the failing tests.** Import `unavailable` next to `probe`. Add:

```python
def test_unavailable_matches_probe_oserror():
    def boom(path):
        raise OSError("gone")

    assert unavailable(MOUNT) == probe(MOUNT, boom)


def test_errno_oserror_is_unavailable_and_mount_reprobed():
    def stale(path):
        raise OSError(errno.ESTALE, "Stale file handle")

    p, results = UsageProbe(stale), []
    [t] = p.probe_all([A], results.append)
    t.join(5)
    assert results == [unavailable(A)]
    [t2] = p.probe_all([A], results.append)
    t2.join(5)


def test_busy_mount_reports_unavailable_and_probes_others():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [first] = p.probe_all([A], results.append)
    second = p.probe_all([A, B], results.append)
    assert results == [unavailable(A)]  # synchronous: reported before probe_all returned
    assert len(second) == 1  # only B started
    release.set()
    first.join(5)
    second[0].join(5)


def test_late_result_recovers_and_mount_is_probed_again():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [first] = p.probe_all([A], results.append)
    p.probe_all([A], results.append)
    release.set()
    first.join(5)
    assert [v.status for v in results] == ["unavailable", "ok"]
    [again] = p.probe_all([A], results.append)
    again.join(5)


def test_fresh_result_is_never_followed_by_stale_unavailable():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    in_cb, go = threading.Event(), threading.Event()

    def cb(v):
        results.append(v)
        if not in_cb.is_set():
            in_cb.set()
            go.wait(5)  # worker parks inside on_result, holding the lock

    [worker] = p.probe_all([A], cb)
    release.set()
    assert in_cb.wait(5)
    started = []
    tick = threading.Thread(target=lambda: started.extend(p.probe_all([A], cb)))
    tick.start()
    tick.join(0.2)
    assert tick.is_alive()  # busy check waits for the worker's delivery
    go.set()
    tick.join(5)
    worker.join(5)
    for t in started:
        t.join(5)
    assert [v.status for v in results] == ["ok", "ok"]  # mount was idle: fresh probe, no unavailable


def test_close_suppresses_late_results_and_new_probes():
    statvfs, release = blocking()
    p, results = UsageProbe(statvfs), []
    [t] = p.probe_all([A], results.append)
    p.close()
    release.set()
    t.join(5)
    assert results == []
    assert p.probe_all([A, B], results.append) == []
    assert results == []
```

Update these existing tests:
- Replace `test_probe_all_skips_busy_mount_but_probes_others` with `test_busy_mount_reports_unavailable_and_probes_others` above.
- `test_probe_all_duplicate_mount_points_start_one_thread`: collect results and assert `results == [unavailable(A)]` right after the call.
- `test_stuck_mount_costs_one_thread_over_many_polls`: collect results and assert `results == [unavailable(A)] * 4` before release.

Add `import errno`.

- [ ] **Step 2: Run** `pytest tests/core/test_usage.py -v`. Expected: an ImportError on `unavailable` first. After adding a stub, the new and updated tests FAIL on behavior.

- [ ] **Step 3: Implement in `core/usage.py`.**
  - Add `unavailable(mount)` and use it in `probe()`'s `OSError` branch.
  - Add `self._closed = False` to `UsageProbe`.
  - `probe_all`:
    - Return `[]` if closed; check under the lock.
    - For a busy mount, call `on_result(unavailable(mount))` inside the `with self._lock:` block, then `continue`.
  - `_run`: use the worker body from the spec. Compute `vol` outside the lock; in `finally`, under the lock, discard from `_busy` and call `on_result(vol)` if `vol is not None and not self._closed`.
  - `close()`: set `_closed` under the lock.
  - Replace the class docstring with the spec's docstring contract: "unavailable" emitted from `probe_all` on the calling (UI) thread, delivered directly by Qt while the lock is held; worker results emitted under the lock and queued; `on_result` must be quick and must never call into this probe from either thread. Also replace ADR-004 with ADR-011 in the docstring.

- [ ] **Step 4: Run** `pytest tests/core --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100`. Expected: all PASS, 100%. The existing `test_non_oserror_in_statvfs_frees_mount`, `test_raising_on_result_frees_mount` and `test_thread_start_failure_frees_mount_and_reraises` must pass unchanged.

- [ ] **Step 5: Commit** `git commit -am "feat: report busy probes as unavailable and deliver results under the probe lock"`

---

### Task 3: Refresher.stop, aboutToQuit wiring, SIGINT default

**Files:**
- Modify: `storage_visualizer/ui/refresher.py`, `storage_visualizer/ui/app.py`
- Test: `tests/ui/test_refresher.py`

**Interfaces:**
- Consumes: `UsageProbe.close()`, `unavailable(mount)` (Task 2).
- Produces: `Refresher.stop() -> None` (a `@Slot()`).

- [ ] **Step 1: Write the failing tests** in `tests/ui/test_refresher.py`. Give `FakeProbe` a `close()` that does `self.log.append(("close",))`. Then add:

```python
def test_stop_stops_timer_and_closes_probe(qtbot):
    log = []
    r = Refresher(FakeWindow(log), ResultBridge(), FakeProbe(log), enumerate_fn=lambda: M)
    r.start()
    r.stop()
    assert not r.timer.isActive() and log[-1] == ("close",)
    r.stop()  # idempotent


NET = MountInfo("server:/export", "/mnt/net", "nfs", True)


def test_busy_share_unavailable_then_recovers_through_real_bridge(qtbot):
    faulthandler.dump_traceback_later(5, exit=True)  # a deadlock kills the run with a stack dump
    try:
        release = threading.Event()

        def statvfs(path):
            release.wait(5)
            return SimpleNamespace(f_frsize=4096, f_blocks=1000, f_bfree=300, f_bavail=250)

        w = MainWindow()
        qtbot.addWidget(w)
        bridge = ResultBridge()
        bridge.volume_ready.connect(w.update_volume)
        r = Refresher(w, bridge, UsageProbe(statvfs), enumerate_fn=lambda: [NET])
        r.refresh()  # worker parks in statvfs
        r.refresh()  # busy: unavailable delivered directly, under the probe lock
        assert w.pies["/mnt/net"].volume == unavailable(NET)
        release.set()
        qtbot.waitUntil(lambda: w.pies["/mnt/net"].volume.status == "ok", timeout=5000)
        r.stop()
    finally:
        faulthandler.cancel_dump_traceback_later()
```

Add `import faulthandler, threading`, `from types import SimpleNamespace` and `from storage_visualizer.core.usage import UsageProbe, unavailable`.

- [ ] **Step 2: Run** `pytest tests/ui/test_refresher.py -v`. Expected: `test_stop_...` FAILS with AttributeError `stop`. The bridge test may already pass after Task 2; it pins the contract.

- [ ] **Step 3: Implement.**
  - `Refresher.stop()`: `self._timer.stop(); self._probe.close()`.
  - `app.py`:
    - `import signal`.
    - In `main()`, before `app.exec()`: `signal.signal(signal.SIGINT, signal.SIG_DFL)`, with a comment. Python can't run its SIGINT handler while `app.exec()` blocks in C++, so Ctrl+C would only land at the next tick as a `KeyboardInterrupt` in `refresh()`. `SIG_DFL` terminates at once. The graceful quit is window close (`aboutToQuit` → `Refresher.stop`). There's no wake-up timer, because of idle CPU.
    - After the Refresher is created: `app.aboutToQuit.connect(refresher.stop)`.
  - `test_default_probe_built_once`'s `CountingProbe` needs no `close` (never stopped).

- [ ] **Step 4: Run** the full gate: `pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100 && ruff check . && ruff format --check .`. Expected: all PASS.

- [ ] **Step 5: Commit** `git commit -am "fix: close the probe on aboutToQuit and exit on Ctrl+C immediately"`

---

### Task 4: Docs

**Files:**
- Modify: `docs/PLANNING.md`, `docs/TESTING.md`, `CLAUDE.md`, `docs/DECISIONS.md`

- [ ] **Step 1: Apply the spec's "Doc Changes → In the implementation plan" list exactly.** It covers the PLANNING diagram, Responsiveness and Architecture paragraph; the TESTING checklist line and Common Bugs row; the CLAUDE.md Conventions line; and DECISIONS Key Principle #2.
- [ ] **Step 2: TESTING.md checklist:** replace "Tray icon shows/hides the window; Quit exits cleanly" with two lines. "Close the window → clean exit, no traceback" and "Ctrl+C in the terminal → exits immediately, no traceback". Keep the tray line as "Tray icon shows/hides the window".
- [ ] **Step 3: DECISIONS.md:** append ADR-011 from the spec's "Decisions Recorded on This Branch" in the file's ADR format, Status **Proposed**, Date 2026-10-20, with References to the spec and this plan. Leave ADR-004's status for finishing.
- [ ] **Step 4: Verify** with `ruff check . && ruff format --check .` (docs are excluded; this confirms nothing else changed) and `grep -n "2 s" docs/PLANNING.md CLAUDE.md`. Expected: no stale 2 s timeout mentions remain.
- [ ] **Step 5: Commit** `git commit -am "docs: describe busy-at-tick unavailable and propose ADR-011"`

---

### Task 5: Manual checklist: STOP, human hand-off

The agent cannot see the window. Stop here: give the human the checks below, wait for a pass/fail report, and record it. Run from the checkout with `python -m storage_visualizer` (or `pipx install --force .`).

- [ ] Every mounted share of a kept fstype (`findmnt -t nfs,nfs4,cifs,smb3,fuse.sshfs`) has exactly one pie, and its numbers match `df -h`.
- [ ] Local pies are unchanged and match `df -h`.
- [ ] No tracebacks over several polls.
- [ ] Close the window → clean exit, no traceback (exercises `aboutToQuit` → `Refresher.stop` → `close()`).
- [ ] Ctrl+C in the terminal → exits immediately, no traceback.
- Not run, covered by unit tests: stopping the NFS/SMB server. N/A: tray, KWin rule.

After the report: run `ce-superpowers:recording-decisions` (the spec's "At finish" list: ADR-011 Accepted, ADR-004 Superseded by ADR-011, TASK.md updates including the dead-NFS-at-quit Known Issue), then `superpowers:finishing-a-development-branch`.
