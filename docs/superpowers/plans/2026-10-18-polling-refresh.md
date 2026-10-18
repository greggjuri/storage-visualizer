# Polling Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 30 s, re-run enumerate and probe, add and remove pies in place by mount point, and never re-probe a mount whose previous probe is still running.

**Architecture:** `core.usage.UsageProbe` gains a lock-protected busy set so `probe_all` skips mounts with a probe in flight (ADR-004). `core.enumerator.enumerate_system_mounts()` wraps `psutil.disk_partitions(all=True)`. A new `ui.refresher.Refresher` owns a 30 s `QTimer` and one `UsageProbe`; its `refresh()` (startup and every tick) enumerates, calls `MainWindow.set_mounts()` to diff pies, then `probe_all` with the queued bridge's `emit` (ADR-009). Proposed ADR-010 records the Refresher placement.

**Tech Stack:** Python 3.13, PySide6>=6.8, psutil>=6.0, pytest, pytest-qt, pytest-cov, ruff==0.17.1

**Spec:** `docs/superpowers/specs/2026-10-18-polling-refresh-design.md` (read it alongside this plan; test numbers 1–16 below refer to its Testing section)

## Global Constraints

- `core/` never imports Qt (PLANNING.md Architecture).
- The UI thread never calls `statvfs` (ADR-004). Enumeration on the UI thread is fine only because of `psutil>=6.0`.
- Enumerate with `psutil.disk_partitions(all=True)`, never `all=False` (ADR-003).
- Poll interval exactly `30_000` ms via `QTimer` (ADR-005).
- Debian 13 + KDE Wayland only; no portability code (ADR-001).
- Max 500 lines per file.
- 100% line coverage on `storage_visualizer.core`; `ui/` gets pytest-qt smoke tests only, with no real timer waits.
- Conventional commits (`feat:`, `test:`, `docs:`, `refactor:`).
- Before each commit: `.venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/ruff format --check .` and the full test command below. Test snippets here are condensed; let ruff reformat them.
- All commands run from the repo root with the venv: `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/python`.
- Full test command: `.venv/bin/pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100`

## Review Focus

1. **A permanently stuck mount over many ticks:** thread count must stay bounded at one parked thread for that mount, however many polls run. Test in Task 1.
2. **Unchanged mount list across ticks:** the common case; no pie is recreated, so nothing flickers to "…". Test in Task 3.
3. **Mount removed and re-added at the same path on a later tick:** gets a fresh pie in loading state, in sorted position. Test in Task 3.
4. **Mount points that sort awkwardly** (`/mnt/a b` with a space, `/mnt/a` vs `/mnt/ab`, `/mnt/a/b`): insertion order always equals `sorted()` of the current mount points, matching the enumerator. Test in Task 3.
5. **A tick that enumerates nothing** (every volume unmounted): all pies go, the empty label shows, and `probe_all` is called with `[]` without error. Test in Task 4.

---

### Task 1: Busy guard in UsageProbe

**Files:**
- Modify: `storage_visualizer/core/usage.py` (class `UsageProbe`)
- Test: `tests/core/test_usage.py`

**Interfaces:**
- Consumes: existing `probe(mount, statvfs) -> Volume`, `MountInfo`.
- Produces: `UsageProbe(statvfs=os.statvfs).probe_all(mounts: Iterable[MountInfo], on_result: Callable[[Volume], None]) -> list[threading.Thread]`, same signature as today; now skips busy mounts and returns only started threads.

Shared test helper, add once at the top of the new tests:

```python
def blocking():
    """Fake statvfs that parks until the returned Event is set."""
    release = threading.Event()
    def statvfs(path):
        release.wait(5)
        return fake(path)
    return statvfs, release

A = MountInfo("/dev/sda1", "/mnt/a", "ext4", False)
B = MountInfo("/dev/sdb1", "/mnt/b", "ext4", False)
```

- [ ] **Step 1: Write the failing tests (spec tests 1, 2, 6, Review Focus 1)**

```python
def test_probe_all_skips_busy_mount_but_probes_others():          # spec 1
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    [first] = p.probe_all([A], lambda v: None)
    second = p.probe_all([A, B], lambda v: None)
    assert len(second) == 1                    # only B started
    release.set(); first.join(5); second[0].join(5)

def test_probe_all_mount_eligible_again_after_probe_returns():    # spec 2
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    [t] = p.probe_all([A], lambda v: None)
    release.set(); t.join(5)
    again = p.probe_all([A], lambda v: None)
    assert len(again) == 1
    again[0].join(5)

def test_probe_all_duplicate_mount_points_start_one_thread():     # spec 6
    statvfs, release = blocking()
    threads = UsageProbe(statvfs).probe_all([A, A], lambda v: None)
    assert len(threads) == 1
    release.set(); threads[0].join(5)

def test_stuck_mount_costs_one_thread_over_many_polls():          # Review Focus 1
    statvfs, release = blocking()
    p = UsageProbe(statvfs)
    started = [t for _ in range(5) for t in p.probe_all([A], lambda v: None)]
    assert len(started) == 1
    release.set(); started[0].join(5)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/core/test_usage.py -v`
Expected: the four new tests FAIL (`len(second) == 2`, etc.); existing tests PASS.

- [ ] **Step 3: Implement the busy set in `UsageProbe`**

`__init__` adds `self._busy: set[str] = set()` and `self._lock = threading.Lock()`. In `probe_all`, per mount: under the lock, `continue` if `mount.mount_point in self._busy`, else add it; then create and start the daemon thread outside the lock. The worker target is a method `_run(self, mount, on_result)` whose body is `try: on_result(probe(mount, self._statvfs))` / `finally:` discard under the lock. Update the class docstring to mention the busy guard (ADR-004).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/core/test_usage.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing tests for the release paths (spec tests 3, 4, 5)**

```python
def collect_hook(monkeypatch):
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda args: seen.append(args.exc_type))
    return seen

def test_non_oserror_in_statvfs_frees_mount(monkeypatch):         # spec 3
    seen = collect_hook(monkeypatch)
    def boom(path): raise RuntimeError("bug")
    p = UsageProbe(boom)
    [t] = p.probe_all([A], lambda v: None); t.join(5)
    assert seen == [RuntimeError]
    assert len(p.probe_all([A], lambda v: None)) == 1   # eligible again

def test_raising_on_result_frees_mount(monkeypatch):              # spec 4
    seen = collect_hook(monkeypatch)
    def bad(v): raise ValueError("callback")
    p = UsageProbe(fake)
    [t] = p.probe_all([A], bad); t.join(5)
    assert seen == [ValueError]
    [t2] = p.probe_all([A], lambda v: None); t2.join(5)

def test_thread_start_failure_frees_mount_and_reraises(monkeypatch):  # spec 5
    p = UsageProbe(fake)
    with monkeypatch.context() as m:
        def no_start(self): raise RuntimeError("can't start new thread")
        m.setattr(threading.Thread, "start", no_start)
        with pytest.raises(RuntimeError):
            p.probe_all([A], lambda v: None)
    [t] = p.probe_all([A], lambda v: None); t.join(5)
```

Join any thread the second `probe_all` in spec 3 returns, too.

- [ ] **Step 6: Run to verify the start-failure test fails**

Run: `.venv/bin/pytest tests/core/test_usage.py -v`
Expected: `test_thread_start_failure_frees_mount_and_reraises` FAILS (the second `probe_all` returns `[]`, mount still busy). Spec 3 and 4 already PASS from Step 3's `finally`; that is expected, they pin it.

- [ ] **Step 7: Wrap `thread.start()` in `probe_all`**

`try: t.start()` / `except BaseException:` discard the mount point under the lock, then `raise`.

- [ ] **Step 8: Run the full suite with coverage**

Run: full test command (Global Constraints)
Expected: all PASS, `storage_visualizer/core/usage.py` 100%.

- [ ] **Step 9: Commit**

```bash
git add storage_visualizer/core/usage.py tests/core/test_usage.py
git commit -m "feat: skip re-probing a mount while its previous probe is running"
```

---

### Task 2: enumerate_system_mounts

**Files:**
- Modify: `storage_visualizer/core/enumerator.py`
- Test: `tests/core/test_enumerator.py`

**Interfaces:**
- Consumes: existing `enumerate_mounts(partitions) -> list[MountInfo]`.
- Produces: `storage_visualizer.core.enumerator.enumerate_system_mounts() -> list[MountInfo]`.

- [ ] **Step 1: Write the failing test (spec test 7)**

```python
def test_enumerate_system_mounts_uses_all_true(monkeypatch):
    calls = []
    def fake_partitions(all):
        calls.append(all)
        return [Part("/dev/sda1", "/", "ext4", ""), Part("tmpfs", "/tmp", "tmpfs", "")]
    monkeypatch.setattr(enumerator.psutil, "disk_partitions", fake_partitions)
    assert enumerator.enumerate_system_mounts() == [MountInfo("/dev/sda1", "/", "ext4", False)]
    assert calls == [True]
```

Import as `from storage_visualizer.core import enumerator`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/core/test_enumerator.py -v`
Expected: FAIL with `AttributeError` (no `psutil` / `enumerate_system_mounts` on the module).

- [ ] **Step 3: Implement**

`import psutil` at module top; `enumerate_system_mounts()` returns `enumerate_mounts(psutil.disk_partitions(all=True))` with the comment `# all=True: ADR-003`.

- [ ] **Step 4: Run the full suite with coverage**

Run: full test command
Expected: all PASS, core 100%.

- [ ] **Step 5: Commit**

```bash
git add storage_visualizer/core/enumerator.py tests/core/test_enumerator.py
git commit -m "feat: enumerate system mounts with psutil all=True in core"
```

---

### Task 3: MainWindow.set_mounts diff

**Files:**
- Modify: `storage_visualizer/ui/main_window.py`, `storage_visualizer/ui/app.py` (interim one-liner, replaced in Task 4)
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `PieWidget(mount_point)`, `PieWidget.volume`, `MountInfo`, `Volume`.
- Produces: `MainWindow()` (no arguments); `MainWindow.set_mounts(mounts: list[MountInfo]) -> None`; unchanged `MainWindow.pies -> dict[str, PieWidget]` and `MainWindow.update_volume(volume: Volume) -> None` slot.

Test helpers:

```python
def mi(mp): return MountInfo("/dev/x" + mp, mp, "ext4", False)

def layout_order(w):
    """Mount points of the pies in layout order, then 'label' for the empty label."""
    by_id = {id(p): mp for mp, p in w.pies.items()}   # PieWidget has no public mount-point accessor
    lay = w.layout()
    return ["label" if isinstance(lay.itemAt(i).widget(), QLabel) else by_id[id(lay.itemAt(i).widget())]
            for i in range(lay.count())]
```

- [ ] **Step 1: Migrate existing tests**

Every `MainWindow(MOUNTS)` becomes `w = MainWindow(); w.set_mounts(MOUNTS)`; `MainWindow([])` becomes `MainWindow()`. Keep all five existing tests and their assertions (one pie per mount, title, update, unknown mount, empty message, bridge delivery).

- [ ] **Step 2: Write the new failing tests (spec 8–11, Review Focus 2–4)**

```python
def test_added_pie_goes_in_sorted_position(qtbot):                   # spec 8
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/home")])
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    assert layout_order(w) == ["/", "/data", "/home", "label"]

def test_removed_pie_goes_and_survivors_keep_volume(qtbot):          # spec 9
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data"), mi("/home")])
    root, home = w.pies["/"], w.pies["/home"]
    vol = Volume("/", "/", "ext4", False, "ok", 100, 40, 60)
    w.update_volume(vol)
    w.set_mounts([mi("/"), mi("/home")])
    assert list(w.pies) == ["/", "/home"] and layout_order(w) == ["/", "/home", "label"]
    assert w.pies["/"] is root and w.pies["/home"] is home and root.volume == vol

def test_empty_label_tracks_pies(qtbot):                             # spec 10
    w = MainWindow(); qtbot.addWidget(w)
    label = w.findChild(QLabel)
    assert not label.isHidden()
    w.set_mounts([mi("/")]); assert label.isHidden()
    w.set_mounts([]); assert not label.isHidden()

def test_late_result_for_removed_mount_is_ignored(qtbot):            # spec 11
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/data")]); w.set_mounts([mi("/")])
    w.update_volume(Volume("/data", "/data", "ext4", False, "ok", 1, 0, 1))
    assert list(w.pies) == ["/"]

def test_unchanged_mounts_keep_same_pies(qtbot):                     # Review Focus 2
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/home")])
    before = dict(w.pies)
    w.set_mounts([mi("/"), mi("/home")])
    assert all(w.pies[k] is before[k] for k in before)

def test_readded_mount_gets_fresh_loading_pie(qtbot):                # Review Focus 3
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([mi("/"), mi("/usb")])
    old = w.pies["/usb"]
    w.update_volume(Volume("/usb", "/usb", "vfat", False, "ok", 10, 5, 5))
    w.set_mounts([mi("/")]); w.set_mounts([mi("/"), mi("/usb")])
    assert w.pies["/usb"] is not old and w.pies["/usb"].volume is None
    assert layout_order(w) == ["/", "/usb", "label"]

def test_insert_order_matches_sorted_for_awkward_paths(qtbot):       # Review Focus 4
    w = MainWindow(); qtbot.addWidget(w)
    paths = ["/mnt/ab", "/mnt/a/b", "/mnt/a b", "/mnt/a", "/"]
    for i in range(1, len(paths) + 1):
        w.set_mounts([mi(p) for p in paths[:i]])
    assert layout_order(w) == sorted(paths) + ["label"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: FAIL with `TypeError` (`MainWindow()` missing `mounts`) / `AttributeError` (`set_mounts`).

- [ ] **Step 4: Implement `MainWindow()` and `set_mounts`**

Per spec ui/main_window.py: constructor builds the `QHBoxLayout` and the "No volumes found" label (kept as `self._empty`, always last). `set_mounts`: remove (`layout.removeWidget`, `deleteLater`, `del`), insert new pies at `sum(1 for mp in self._pies if mp < new_mp)` via `layout.insertWidget`, `self._empty.setVisible(not self._pies)`, and `self.adjustSize()` only if something was added or removed. Add a one-line comment at the `adjustSize()` call: deliberate, `SetFixedSize` would fight the future Flow layout's width-based wrapping.

- [ ] **Step 5: Interim app.py change**

In `ui/app.py`: `window = MainWindow()` then `window.set_mounts(mounts)`; nothing else changes. Task 4 replaces this.

- [ ] **Step 6: Run the full suite with coverage**

Run: full test command
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add storage_visualizer/ui/main_window.py storage_visualizer/ui/app.py tests/ui/test_main_window.py
git commit -m "feat: main window adds and removes pies in place by mount point"
```

---

### Task 4: Refresher and app wiring

**Files:**
- Create: `storage_visualizer/ui/refresher.py`
- Modify: `storage_visualizer/ui/app.py`
- Test: `tests/ui/test_refresher.py`

**Interfaces:**
- Consumes: `enumerate_system_mounts()` (Task 2), `UsageProbe().probe_all(...)` (Task 1), `MainWindow()` / `set_mounts` / `update_volume` (Task 3), `ResultBridge.volume_ready`.
- Produces: `storage_visualizer.ui.refresher.INTERVAL_MS = 30_000`; `Refresher(window, bridge, probe=None, enumerate_fn=enumerate_system_mounts, parent=None)` (a `QObject`) with `timer -> QTimer` (read-only property), `start() -> None`, `refresh() -> None` (`@Slot()`).

Test fakes:

```python
class FakeWindow:
    def __init__(self, log): self.log = log
    def set_mounts(self, mounts): self.log.append(("set_mounts", list(mounts)))

class FakeProbe:
    def __init__(self, log, volumes=()): self.log, self.volumes = log, volumes
    def probe_all(self, mounts, on_result):
        self.log.append(("probe_all", list(mounts)))
        for v in self.volumes: on_result(v)    # synchronous, on the UI thread
        return []
```

Use `qtbot` in every test so a `QApplication` exists; call `r.timer.stop()` at the end of any test that starts it.

- [ ] **Step 1: Write the failing tests (spec 12–16, Review Focus 5)**

```python
M = [MountInfo("/dev/a1", "/", "ext4", False)]

def test_interval_and_timeout_wired_to_refresh(qtbot):               # spec 12
    calls = []
    r = Refresher(FakeWindow([]), ResultBridge(), FakeProbe([]),
                  enumerate_fn=lambda: calls.append(1) or M)
    assert r.timer.interval() == 30_000 == INTERVAL_MS
    r.timer.timeout.emit()
    assert calls == [1]

def test_refresh_sets_mounts_before_probing(qtbot):                  # spec 13
    log, bridge = [], ResultBridge()
    vol = Volume("/", "/", "ext4", False, "ok", 100, 40, 60)
    r = Refresher(FakeWindow(log), bridge, FakeProbe(log, [vol]), enumerate_fn=lambda: M)
    with qtbot.waitSignal(bridge.volume_ready) as sig:
        r.refresh()
    assert log == [("set_mounts", M), ("probe_all", M)]
    assert sig.args == [vol]                   # on_result is the bridge's emit

def test_two_refreshes_add_and_remove_pies(qtbot):                   # spec 14
    w = MainWindow(); qtbot.addWidget(w)
    bridge = ResultBridge(); bridge.volume_ready.connect(w.update_volume)
    lists = iter([M, [MountInfo("/dev/b1", "/usb", "vfat", False)]])
    vol = Volume("/usb", "/usb", "vfat", False, "ok", 10, 5, 5)
    probe = FakeProbe([])
    r = Refresher(w, bridge, probe, enumerate_fn=lambda: next(lists))
    r.refresh(); assert list(w.pies) == ["/"]
    probe.volumes = [vol]; r.refresh()
    assert list(w.pies) == ["/usb"] and w.pies["/usb"].volume == vol

def test_start_refreshes_once_and_starts_timer(qtbot):               # spec 15
    calls = []
    r = Refresher(FakeWindow([]), ResultBridge(), FakeProbe([]),
                  enumerate_fn=lambda: calls.append(1) or M)
    r.start()
    assert calls == [1] and r.timer.isActive()
    r.timer.stop()

def test_default_probe_built_once(qtbot, monkeypatch):               # spec 16
    built = []
    class CountingProbe:
        def __init__(self): built.append(1)
        def probe_all(self, mounts, on_result): return []
    monkeypatch.setattr(refresher, "UsageProbe", CountingProbe)
    r = refresher.Refresher(FakeWindow([]), ResultBridge(), enumerate_fn=lambda: M)
    r.refresh(); r.refresh()
    assert built == [1]

def test_empty_enumeration_clears_window(qtbot):                     # Review Focus 5
    w = MainWindow(); qtbot.addWidget(w)
    log = []
    lists = iter([M, []])
    r = Refresher(w, ResultBridge(), FakeProbe(log), enumerate_fn=lambda: next(lists))
    r.refresh(); r.refresh()
    assert w.pies == {} and not w.findChild(QLabel).isHidden()
    assert log[-1] == ("probe_all", [])
```

Import as `from storage_visualizer.ui import refresher` and `from storage_visualizer.ui.refresher import INTERVAL_MS, Refresher`.

Spec 14 uses a synchronous direct emit: `bridge.volume_ready.emit` called on the UI thread delivers directly, so no wait is needed.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_refresher.py -v`
Expected: FAIL with `ModuleNotFoundError: storage_visualizer.ui.refresher`.

- [ ] **Step 3: Implement `ui/refresher.py`**

Per spec ui/refresher.py: `QTimer(self)`, `setInterval(INTERVAL_MS)`, `timeout.connect(self.refresh)`; `self._probe = probe if probe is not None else UsageProbe()` built once in `__init__`; `refresh()` is enumerate → `set_mounts` → `probe_all(mounts, self._bridge.volume_ready.emit)`; `start()` is `refresh()` then `self._timer.start()`. Import `UsageProbe` as a module-level name (`from storage_visualizer.core.usage import UsageProbe`) so spec 16's monkeypatch works.

- [ ] **Step 4: Rewire `ui/app.py`**

Replace the enumerate and `probe_all` lines with the spec's app.py block: `MainWindow()`, `ResultBridge`, connect, `refresher = Refresher(window, bridge)` (comment: keep referenced until `app.exec()` returns), `refresher.start()` before `window.show()`. Drop the `psutil`, `enumerate_mounts` and `UsageProbe` imports from `app.py`. No `try` around `start()`: an enumerate failure at startup exits the app (spec Error Handling).

- [ ] **Step 5: Run the full suite, lint, and a launch smoke check**

Run: full test command, then `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
Expected: all PASS, core 100%, ruff clean.
Run: `QT_QPA_PLATFORM=offscreen timeout 3 .venv/bin/python -m storage_visualizer; echo $?`
Expected: exit code `124` (killed by timeout, i.e. the event loop ran) and no traceback on stderr. This checks wiring only; it is not the visual check.

- [ ] **Step 6: Commit**

```bash
git add storage_visualizer/ui/refresher.py storage_visualizer/ui/app.py tests/ui/test_refresher.py
git commit -m "feat: refresh mounts and usage every 30 s via a ui Refresher"
```

---

### Task 5: Doc wording fixes

**Files:**
- Modify: `CLAUDE.md`, `docs/PLANNING.md`, `docs/TESTING.md`

**Interfaces:** none (docs only). Exact replacements are in the spec's Doc Changes section, "In the implementation plan".

- [ ] **Step 1: CLAUDE.md**

Conventions bullet becomes: "`core/` never imports Qt; each tick diffs the mount list to add/remove pies; results update pies one volume at a time (ADR-009)." TDD scope `ui/` bullet: list becomes `(MainWindow, PieWidget, FlowLayout, TrayIcon, Refresher)` and the parenthetical becomes "(widgets build, `set_mounts` adds/removes pies, `update_volume` updates them)".

- [ ] **Step 2: docs/PLANNING.md**

Data flow line becomes: "Data flows one way: timer tick → enumerate → diff the mount list to add/remove pies → probe; results update pies one volume at a time (ADR-009)." Diagram: `QTimer (30 s)` → `Refresher (QTimer 30 s)`; the arrow label `list[Volume]` → `Volume (one at a time)` (keep the box alignment); `ui/` list gains `Refresher`. Testing Approach `ui/` line gets the same wording as CLAUDE.md's TDD scope.

- [ ] **Step 3: docs/TESTING.md**

Setup step 3 lists: threads `watch -n5 'ps -o nlwp= -p $(pgrep -f storage_visualizer)'`; CPU `pidstat -p $(pgrep -f storage_visualizer) 5` (sysstat) or `top -p $(pgrep -f storage_visualizer)`; USB: mount via the KDE device notifier, confirm the path with `findmnt`. Checklist gains "Existing pies don't flicker to '…' on a tick" and "Thread count returns to baseline between polls". The `ui/` smoke-test example uses `window = MainWindow()` + `window.set_mounts(mounts)`.

- [ ] **Step 4: Verify**

Run: `grep -n "list\[Volume\]" CLAUDE.md docs/PLANNING.md docs/TESTING.md`
Expected: no output. Run: `grep -n "MainWindow(mounts)" docs/TESTING.md` → no output.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/PLANNING.md docs/TESTING.md
git commit -m "docs: describe per-tick mount diff and per-volume updates"
```

---

### Task 6: Manual checklist — STOP, human hand-off

**Files:** none.

The agent cannot see the window. Do not run the GUI interactively and do not mark these checks yourself.

- [ ] **Step 1: Hand off**

Post the checklist from the spec's "Manual checklist: STOP, human hand-off" section (commands and checks, including the N/A line) to the human, with the launch command `.venv/bin/python -m storage_visualizer`. STOP and wait for a pass/fail report per check.

- [ ] **Step 2: Record the result**

On all-pass, note it in the finish summary. On any fail, switch to `superpowers:systematic-debugging` with the reported symptom before touching code.

After this task: `ce-superpowers:recording-decisions` (ADR-010 Accepted, TASK.md updates per the spec), then `superpowers:finishing-a-development-branch`.
