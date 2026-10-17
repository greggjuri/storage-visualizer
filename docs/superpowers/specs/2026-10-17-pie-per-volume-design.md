# Pie per Volume: Design

**Date**: 2026-10-17
**Backlog item**: "Pie per volume" (docs/TASK.md, Next)
**Status**: Approved in brainstorming, awaiting spec review

## Goal

At startup, enumerate the filtered, deduplicated local mounts, probe their usage once in the background, and show one used/free pie per volume in a plain decorated window. This is also the first code in the repo, so it scaffolds the package, test setup and tooling.

On debian-dev today this should show two pies: `/` (`/dev/nvme0n1p4`) and `/mnt/backup` (`/dev/sdd1`). `/boot/efi` is filtered out.

## Context

- **ADR-001**: Debian 13 + KDE Plasma 6 Wayland only. No portability code.
- **ADR-002**: Python 3.13 + PySide6.
- **ADR-003**: `psutil.disk_partitions(all=True)` plus our own filters; dedupe by device, shortest mount point wins.
- **ADR-004**: the UI thread never calls `statvfs`. This feature uses one worker thread per mount. The timeout and the no-re-dispatch logic are deferred to the "Network share probe" item.
- **ADR-006**: the app id `storage-visualizer` is set now (one line). Frameless, tray and KWin are out of scope.
- **ADR-008**: pies are drawn with QPainter. Settled in this brainstorming; to be marked Accepted on this branch.
- **PLANNING.md**: Architecture (`core/` has no Qt imports), Data Models (`MountInfo`, `Volume`), Volume Rules, Testing Approach, 500-line file limit.

## Scope

**In scope**
- Package scaffold, `pyproject.toml`, `.gitignore`, test and lint config
- `core/`: models, enumerator, usage probe with per-mount threads
- `ui/`: app entry, main window, pie widget, signal bridge
- `python -m storage_visualizer` and a `storage-visualizer` console script

**Out of scope** (each is its own backlog item)
- Polling or refresh (data is read once at startup)
- Network filesystems, the 2 s timeout and stuck-probe tracking
- By-label names, "System" for `/`, used/free/total text
- Flow layout, frameless window, tray, pipx install and autostart docs

## Architecture

```
main()
  ├─ enumerate_mounts(psutil.disk_partitions(all=True))   # UI thread; reads /proc/self/mounts only
  ├─ MainWindow(mounts)  → one PieWidget per mount, state "loading"
  └─ UsageProbe.probe_all(mounts, bridge.volume_ready.emit)
          │  one daemon threading.Thread per mount: probe(mount) -> Volume
          ▼
     ResultBridge.volume_ready (Signal(object), queued to UI thread)
          ▼
     MainWindow.update_volume(volume) → pies[volume.mount_point].set_volume(volume)
```

Enumeration runs on the UI thread on purpose: `disk_partitions` parses `/proc/self/mounts` and never touches a mounted filesystem, so it cannot hang on a dead device. Only `statvfs` can, and that always runs in a worker.

## Package Layout

```
pyproject.toml
.gitignore
storage_visualizer/
  __init__.py
  __main__.py              # from storage_visualizer.ui.app import main; main()
  core/
    __init__.py
    models.py
    enumerator.py
    usage.py
  ui/
    __init__.py
    app.py
    bridge.py
    main_window.py
    pie_widget.py
tests/
  core/test_enumerator.py, test_usage.py
  ui/test_pie_widget.py, test_main_window.py
```

## core/

### models.py

Exactly as in PLANNING.md:

```python
@dataclass(frozen=True)
class MountInfo:
    device: str
    mount_point: str
    fstype: str
    is_network: bool

@dataclass(frozen=True)
class Volume:
    mount_point: str
    label: str
    fstype: str
    is_network: bool
    status: Literal["ok", "unavailable"]
    total: int | None
    used: int | None
    free: int | None
```

### enumerator.py

`enumerate_mounts(partitions: Iterable[Any]) -> list[MountInfo]` is a pure function. Each item needs `.device`, `.mountpoint` and `.fstype` attributes, matching psutil's `sdiskpart`.

Rules, applied in this order:
1. Keep only devices starting with `/dev/`. This also drops every network filesystem for now.
2. Drop `/dev/loop*`.
3. Drop pseudo filesystem types: `tmpfs`, `devtmpfs`, `proc`, `sysfs`, `overlay`, `squashfs`, `efivarfs`, `cgroup`, `cgroup2`, `devpts`, `mqueue`, `debugfs`, `tracefs`, `securityfs`, `pstore`, `bpf`, `configfs`, `fusectl`, `hugetlbfs`, `autofs`, `binfmt_misc`, `ramfs`, `nsfs`.
4. Drop mounts equal to or under `/boot`, `/snap`, `/sys`, `/proc`, `/run`, except those equal to or under `/run/media`. Matching is by path component, so `/bootstrap` is not under `/boot`.
5. Dedupe by device. The shortest mount point wins; on a tie, the lexicographically smallest.
6. Sort the result by mount point.

`is_network` is always `False` in this feature.

### usage.py

`probe(mount: MountInfo, statvfs: Callable[[str], Any] = os.statvfs) -> Volume`
- `total = f_blocks * f_frsize`
- `used = (f_blocks - f_bfree) * f_frsize`
- `free = f_bavail * f_frsize`, the space an unprivileged user can use, matching `df`'s Avail
- `label = mount.mount_point` (placeholder until the labels item)
- `OSError` from `statvfs` gives `status="unavailable"` with `total`, `used` and `free` all `None`

`class UsageProbe`
- `__init__(self, statvfs=os.statvfs)`
- `probe_all(self, mounts, on_result: Callable[[Volume], None]) -> list[threading.Thread]` starts one daemon thread per mount; each calls `on_result(probe(mount, self._statvfs))`. It returns the threads so tests can join them; the UI ignores the return value.
- No timeout and no in-flight tracking. Both are added by the "Network share probe" item, and this shape (one thread per mount, results delivered by callback) is what that item builds on.

## ui/

### app.py

`main() -> int`:
1. `QApplication(sys.argv)`, then `setApplicationName("storage-visualizer")` and `setDesktopFileName("storage-visualizer")`
2. `mounts = enumerate_mounts(psutil.disk_partitions(all=True))`
3. `window = MainWindow(mounts)`, then `bridge = ResultBridge()` and `bridge.volume_ready.connect(window.update_volume)`
4. `window.show()`, then `UsageProbe().probe_all(mounts, bridge.volume_ready.emit)`
5. `return app.exec()`

`__main__.py` calls `sys.exit(main())`. The console script `storage-visualizer` points at `storage_visualizer.ui.app:main`.

### bridge.py

`class ResultBridge(QObject)` with `volume_ready = Signal(object)`. The bridge lives on the UI thread and is emitted from worker threads, so Qt's auto connection queues delivery to the UI thread.

### main_window.py

`class MainWindow(QWidget)`
- Ordinary decorated window titled "Storage".
- Uses a `QHBoxLayout` with one `PieWidget` per mount, in enumerator order.
- `self._pies: dict[str, PieWidget]` is keyed by mount point.
- `update_volume(volume)` updates the pie for `volume.mount_point`. Unknown mount points are ignored.
- An empty mount list shows a single `QLabel("No volumes found")`.

### pie_widget.py

`class PieWidget(QWidget)`, constructed with `PieWidget(mount_point: str)`.
- Fixed size of about 140 × 170 logical px: a 120 px pie with the label underneath.
- `volume` property, `None` until the first result arrives.
- `set_volume(volume)` stores the volume and calls `update()`.
- `paintEvent` uses QPainter with antialiasing and draws one of three states:
  - **loading** (`volume is None`): grey outline ring, "…" in the centre
  - **ok**: the used slice in an accent colour from 12 o'clock clockwise, the free slice in light grey, and the used percent (rounded integer) in the centre. If `total == 0`, it shows 0%.
  - **unavailable**: solid grey disc with "unavailable" in the centre
- Under the pie: the label (the volume's label once known, otherwise the mount point), elided to the widget width.
- Colours are module constants; no theming.

## Error Handling

- A mount vanishing between enumeration and probe (`OSError` from `statvfs`) makes that pie "unavailable", never a crash.
- An exception escaping a worker thread is not caught specially. `probe` already turns `OSError` into "unavailable", and anything else is a bug that should surface as a traceback.
- Zero mounts shows the "No volumes found" label.

## Testing

**core/**: strict TDD, 100% line coverage (`pytest --cov=storage_visualizer.core --cov-fail-under=100`), no Qt and no real mounts.
- `test_enumerator.py` uses fixture `sdiskpart` lists to check:
  - kept: ext4 on `/`, btrfs, vfat on `/run/media/...`
  - dropped: each pseudo type sampled, `/dev/loop0`, `/boot/efi`, `/snap/x`, `/run/user/1000` (while `/run/media/...` is kept), and nfs or cifs entries
  - not dropped: `/bootstrap`, which is not treated as under `/boot`
  - dedupe: btrfs subvolumes at `/` and `/home` on one device give `/`; equal-length mount points tie-break lexicographically
  - output is sorted
- `test_usage.py`:
  - `probe` with a fake `statvfs` result checks total, used and free against hand-computed values
  - `probe` with a fake that raises `OSError` gives "unavailable" and `None` numbers
  - `UsageProbe.probe_all` with a fake `statvfs` and a lock-protected collector: after joining the returned threads, there is exactly one `Volume` per mount and the mount points match

**ui/**: pytest-qt smoke tests, no coverage floor.
- `PieWidget` `grab()` works in the loading, ok (including `total == 0`) and unavailable states.
- `MainWindow` with 2 mounts has 2 pies; `update_volume` sets the right pie's volume; an unknown mount point is ignored.
- `MainWindow([])` shows the "No volumes found" label.
- Bridge: emitting `volume_ready` from a `threading.Thread` updates the window's pie (`qtbot.waitUntil`).

**Manual** (`docs/TESTING.md`): run `python -m storage_visualizer` and confirm the pies and percentages match `df -h` for `/` and `/mnt/backup`. The other checklist lines belong to later features and are N/A on this branch.

## Tooling

- `pyproject.toml` (setuptools):
  - Python `>=3.13`; dependencies `PySide6`, `psutil`
  - extra `dev` = `pytest`, `pytest-qt`, `pytest-cov`, `ruff`
  - script `storage-visualizer = storage_visualizer.ui.app:main`
  - `[tool.ruff]`: line length 100, target py313
  - `[tool.pytest.ini_options]`: `testpaths = ["tests"]`
- Development: `python3 -m venv .venv && .venv/bin/pip install -e .[dev]`
- `.gitignore`: `.venv/`, `__pycache__/`, `*.egg-info/`, `.coverage`, `.pytest_cache/`, `.ruff_cache/`, `build/`, `dist/`

## Decisions to Record on This Branch

- ADR-008 → Accepted (QPainter)
- No new ADR needed: approach 1 (plain threads in `core/`, Qt signal bridge in `ui/`) follows directly from PLANNING.md's architecture and ADR-004. It goes in PLANNING.md's architecture notes instead.
