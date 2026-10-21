# Volume Labels: Design

**Date**: 2026-10-20
**Backlog item**: "Volume labels" (docs/TASK.md, Next)
**Status**: Approved (branch feat/volume-labels)

## Goal

Each pie shows a readable name and, under it, used / free / total formatted exactly like `df -h`, so the manual check compares the window with `df -h` column for column.

## Context

- **ADR-003**: `psutil.disk_partitions(all=True)` plus our own filters; dedupe by device, shortest mount point wins. Labels are computed after dedupe, from the kept partition.
- **ADR-004 / ADR-011**: the UI thread never blocks on a mounted filesystem; `statvfs` runs in per-mount workers. Reading `/dev/disk/by-label` (devtmpfs) happens on the UI thread at enumerate time; recorded as **ADR-012** (see Decisions).
- **ADR-008**: `PieWidget` draws with `QPainter`; this design adds two text lines.
- **ADR-009 / ADR-010**: results arrive one `Volume` at a time; the `Refresher` calls `enumerate_fn()` every tick. `enumerate_system_mounts` stays the default `enumerate_fn`.
- **PLANNING.md**: Data Models (`MountInfo`, `Volume.label`), Tech Stack ("`/dev/disk/by-label` (labels)"), Testing Approach, Success Criteria ("label, used/free and total that match `df -h`"), 500-line limit, `core/` never imports Qt.

## Scope

**In scope**
- Label rules for local and network volumes, resolved in `core/` at enumerate time
- `MountInfo.label`; `Volume.label` copied from it (also for "unavailable")
- `df_size()`: coreutils `human_ceiling` formatting
- `PieWidget`: label shown while loading; three text lines when ok; width fits the worst-case numbers line
- ADR-012, Key Principle 2 rewording, PLANNING.md, TESTING.md, TASK.md updates

**Out of scope**
- Flow layout, tray, frameless window, theme-aware text colour
- Showing network pies differently from local ones
- Re-reading labels between ticks (a relabel shows up on the next tick)

## Label Rules

Applied to each kept partition after dedupe. `basename(mp)` means the last component of the mount point with trailing slashes stripped.

**Network** (`fstype` in `NETWORK_FSTYPES`): `network_label(device, mount_point)`
1. Source starting with `//` (CIFS/SMB): drop the leading `//host`, keep the rest.
   Otherwise (`host:/path`, `user@host:dir`): drop everything up to and including the first `:`.
2. Strip trailing `/`; take the last `/`-separated component.
3. Empty → `basename(mp)`.

| Source | Mount point | Label |
|---|---|---|
| `//192.168.1.11/mansion` | `/mnt/nas` | `mansion` |
| `//nas/share/sub/` | `/mnt/x` | `sub` |
| `//nas` | `/mnt/x` | `x` |
| `192.168.1.184:/volume1/media` | `/mnt/nas-media` | `media` |
| `host:/export/` | `/mnt/e` | `export` |
| `user@host:` | `/mnt/remote` | `remote` |
| `user@host:/` | `/mnt/remote` | `remote` |
| `user@host:docs` | `/mnt/remote` | `docs` |

**Local**: `local_label(mount_point, by_label_name)`
1. `mount_point == "/"` → `System` (even if the root filesystem has a by-label name, e.g. `debian`).
2. by-label name present (non-empty) → that name.
3. Otherwise → `basename(mp)`.

## core/

### models.py

```python
@dataclass(frozen=True)
class MountInfo:
    device: str
    mount_point: str
    fstype: str
    is_network: bool
    label: str = ""      # "" only for MountInfos built outside enumerate_mounts (tests)
```

The default keeps existing `MountInfo(...)` call sites and tests valid. `Volume` is unchanged.

### labels.py (new)

Pure functions plus one reader; no Qt.

- `decode_udev(name: str) -> str`: udev escapes unsafe bytes in by-label link names as `\xNN` (`Bork\x20Bork`). Replace each `\xNN` with its byte, then decode the bytes as UTF-8 with `errors="replace"`. Other characters pass through (encoded as UTF-8 first).
- `network_label(device: str, mount_point: str) -> str` and `local_label(mount_point: str, by_label_name: str | None) -> str`: the rules above.
- `read_device_labels(devices: Iterable[str], by_label_dir: str = "/dev/disk/by-label") -> dict[str, str]`:
  - Lists `by_label_dir`; maps `os.path.realpath(link)` → `decode_udev(link name)`.
  - Returns `{device: label}` for each requested device whose `os.path.realpath(device)` is in that map. Real paths on both sides, so `/dev/mapper/x` (symlink to `dm-0`) matches a by-label link to `../../dm-0`.
  - `by_label_dir` missing (`FileNotFoundError`) or unreadable (`OSError`) → `{}`. Nothing else is caught.
  - This is the only label code that touches the filesystem; tests use symlinks under `tmp_path` (fake data, no real mounts).

### enumerator.py

- `enumerate_mounts(partitions: Iterable[Any], labels: Mapping[str, str]) -> list[MountInfo]` stays pure: after dedupe it builds each `MountInfo` with
  `network_label(device, mp)` for network filesystems, else `local_label(mp, labels.get(device))`.
  `labels` is a required argument; existing callers in tests pass `{}`.
- `enumerate_system_mounts()`:
  ```python
  parts = psutil.disk_partitions(all=True)              # all=True: ADR-003
  labels = read_device_labels(p.device for p in parts if p.device.startswith("/dev/"))
  return enumerate_mounts(parts, labels)
  ```

### usage.py

`_base(mount)` uses `mount.label` instead of `mount.mount_point` for `Volume.label`, so ok and "unavailable" volumes both carry the label.

### dfsize.py (new)

`df_size(n: int) -> str`: coreutils `human_readable` with ceiling rounding, autoscale and base 1024, as `df -h` uses it (edge cases cross-checked with `numfmt --to=iec --round=up`). Integer arithmetic only.

1. `n < 1024` → `str(n)` (e.g. `0`, `512`).
2. Pick the largest unit `K M G T P E` (power `k`, `base = 1024**k`) with `n >= base`.
3. If `n < 10 * base`: `tenths = ceil(10 * n / base)`. If `tenths < 100` → `f"{tenths // 10}.{tenths % 10}{unit}"`; else (rounded up to 10) → `f"10{unit}"`.
4. Else: `whole = ceil(n / base)`. If `whole == 1024` and a larger unit exists → `f"1.0{next_unit}"`; else `f"{whole}{unit}"`.

Fixtures from this machine (`df -B1` vs `df -h`, coreutils 9.7):

| Bytes | df -h |
|---|---|
| 420536655872 | 392G |
| 122371670016 | 114G |
| 276727062528 | 258G |
| 1071628288 | 1022M |
| 4743168 | 4.6M |
| 1066885120 | 1018M |
| 3829392867328 | 3.5T |
| 2660562370560 | 2.5T |
| 1168830496768 | 1.1T |
| 9589459386368 | 8.8T |
| 2865106944 | 2.7G |
| 8251813888 | 7.7G |
| 131072 | 128K |
| 26255 | 26K |
| 99697 | 98K |
| 0 | 0 |

Plus edge cases: `1023` → `1023`, `1024` → `1.0K`, `10239` → `10K` (9.999K rounds to 10.0), `1024**2 - 1` → `1.0M` (1023.999K rounds to 1024K), `1024**7` → `1024E` (no larger unit).

## ui/

### pie_widget.py

- `PieWidget(mount_point: str, label: str = "", parent=None)`. The label shows from construction, so a "…" pie already has its name.
- Pure helper `pie_text(volume: Volume | None, mount_point: str, label: str) -> list[str]`:
  - name = `volume.label` if volume and it is non-empty, else `label`, else `mount_point`.
  - ok → `[name, f"{df_size(used)} used · {df_size(free)} free", f"{df_size(total)} total"]`
  - loading (`None`) or "unavailable" → `[name]`
- Layout below the pie: one line per entry, top-aligned, line height `QFontMetrics.height()`. Only line 1 (the name) is middle-elided; lines 2 and 3 are drawn unelided.
- Width: `max(140, horizontalAdvance("1022M used · 1022M free") + 8)` using the widget's font metrics, computed once in `__init__`. Every pie gets the same width, so rows stay aligned. (Digits are tabular in the default fonts, so `1022M` stands for any four-digit value.)
- Height: current pie area plus three text lines (`10 + 120 + 6 + 3 * lineHeight + 6`).
- Centre text (`…`, `unavailable`, `NN%`) unchanged.

### main_window.py

`set_mounts` constructs `PieWidget(m.mount_point, m.label)`. An existing pie keeps its construction label until the next `Volume` arrives (which carries the current label).

## Error Handling

- by-label directory missing or unreadable → no by-label names; local volumes fall back to `basename(mp)` (or `System`).
- A broken symlink in by-label resolves to a path no device matches; ignored.
- Undecodable bytes in a by-label name → U+FFFD replacement, never an exception.
- A volume with `total == 0` shows `0 used · 0 free` / `0 total` (pie already handles zero total).

## Testing

**core/ (strict TDD, 100% line coverage)**
- `test_labels.py`: the network table above; local rules (`/` → System even with a name, name wins, empty/None name → basename); `decode_udev` (`\x20`, multi-byte UTF-8 escape `\xc3\xa9` → `é`, invalid byte → U+FFFD, plain text unchanged); `read_device_labels` with `tmp_path` symlinks (relative link targets, device given as a symlink, unmatched device omitted, missing dir → `{}`, `OSError` on listing → `{}`).
- `test_enumerator.py`: existing tests pass `labels={}`; new tests for label on local (with and without mapping, `/`), network, and the deduped partition's mount point used for the fallback. `enumerate_system_mounts` test with monkeypatched psutil and `read_device_labels` checks only `/dev/` devices are passed.
- `test_usage.py`: ok and unavailable `Volume.label` equal `mount.label`.
- `test_dfsize.py`: the fixture table and edge cases.

**ui/ (pytest-qt smoke tests)**
- `pie_text`: ok → three lines with df strings; loading and unavailable → one line; name fallback order.
- `PieWidget` width ≥ worst-case advance + padding and ≥ 140; constructing with a label and painting doesn't raise.
- `MainWindow.set_mounts` passes the label to new pies.

**Manual (`docs/TESTING.md`)**: every pie's label follows the rules; the three numbers match `df -h` Size/Used/Avail exactly; no number is elided at the default font.

## Decisions

- **ADR-012 (new, Accepted)**: `/dev/disk/by-label` is read on the UI thread at enumerate time. devtmpfs is a kernel pseudo-filesystem and cannot block like a mounted network filesystem, the same reasoning that already allows psutil's `/proc/self/mounts` read there. Alternative rejected: resolving labels in the probe worker (no label while loading or when unavailable, and label lookup repeated per probe).
- **Key Principle 2** in DECISIONS.md is reworded to the rule it protects: "The UI thread never makes calls that can block on a mounted filesystem (statvfs etc.); reading kernel pseudo-filesystems (/proc, devtmpfs under /dev) is fine. Usage probes run in per-mount workers (ADR-004/011)." (Plan's docs task.)
