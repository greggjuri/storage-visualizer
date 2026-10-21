# Volume Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Task 6 is a STOP, human hand-off: a sanctioned stop for inline execution too (PILOT-FINDINGS E7). The final branch review may run while the human does the check.

**Goal:** Each pie shows a readable label and, under it, used / free / total formatted exactly like `df -h`.

**Architecture:** `core/labels.py` holds pure label rules plus one reader of `/dev/disk/by-label`. `enumerate_mounts(partitions, labels)` stays pure and puts the label on `MountInfo`; `enumerate_system_mounts` reads by-label and passes the mapping in. `usage._base` copies the label into `Volume`. `core/dfsize.py` formats bytes like `df -h`; `PieWidget` draws label plus two number lines, sized so the numbers never elide.

**Tech Stack:** Python 3.13, PySide6, psutil, pytest, pytest-qt

**Spec:** `docs/superpowers/specs/2026-10-20-volume-labels-design.md`. Read it with this plan, in particular "Label Rules" (both tables), "core/ → dfsize.py" (algorithm and fixture table) and "ui/ → pie_widget.py".

## Global Constraints

- `core/` never imports Qt.
- The UI thread never calls `statvfs` (ADR-004, ADR-011). Reading `/dev/disk/by-label` at enumerate time is allowed (ADR-012, Proposed on this branch).
- 100% line coverage on `storage_visualizer.core`; `ui/` gets smoke tests only.
- Max 500 lines per file; ruff line length 100.
- Conventional commits: `feat:` `fix:` `refactor:` `docs:` `test:`.
- `/` is always `System`, even with a by-label name.
- Numbers line copy, verbatim: `f"{used} used · {free} free"` (U+00B7 middle dot, spaces around it) and `f"{total} total"`.
- Worst-case width string, verbatim: `"1022M used · 1022M free"`; minimum width 140.
- Only the label line may elide (middle elision); the number lines never do.

## Review Focus

1. A by-label name with spaces or non-ASCII (`Bork\x20Bork`, `\xc3\xa9`) shows decoded, never raw escapes. Pinned by Task 2 `test_decode_udev`.
2. An LVM/dm volume whose psutil device is `/dev/mapper/x` still gets its by-label name (link targets `../../dm-0`). Pinned by Task 2 `test_read_device_labels_matches_through_symlinked_device`.
3. A btrfs subvolume or bind mount deduped to its shortest mount point takes the fallback label from the kept mount point, not the dropped one. Pinned by Task 3 `test_label_fallback_uses_kept_mount_point`.
4. A volume that is "unavailable" keeps its label instead of reverting to the mount point. Pinned by Task 3 `test_unavailable_keeps_label`.
5. Multi-terabyte shares never elide a number at the default font. Pinned by Task 4 `test_pie_width_fits_worst_case_numbers`.

---

### Task 1: df -h size formatting

**Files:**
- Create: `storage_visualizer/core/dfsize.py`
- Test: `tests/core/test_dfsize.py`

**Interfaces:**
- Produces: `df_size(n: int) -> str` in `storage_visualizer.core.dfsize`.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from storage_visualizer.core.dfsize import df_size

# df -B1 vs df -h on debian-dev, coreutils 9.7
DF_FIXTURES = [
    (420536655872, "392G"), (122371670016, "114G"), (276727062528, "258G"),
    (1071628288, "1022M"), (4743168, "4.6M"), (1066885120, "1018M"),
    (3829392867328, "3.5T"), (2660562370560, "2.5T"), (1168830496768, "1.1T"),
    (9589459386368, "8.8T"), (2865106944, "2.7G"), (8251813888, "7.7G"),
    (131072, "128K"), (26255, "26K"), (99697, "98K"), (0, "0"),
]
EDGES = [
    (1023, "1023"), (1024, "1.0K"), (10239, "10K"),
    (1024**2 - 1, "1.0M"), (1024**7, "1024E"),
]


@pytest.mark.parametrize("n,expected", DF_FIXTURES + EDGES)
def test_df_size_matches_df_h(n, expected):
    assert df_size(n) == expected
```

(`ruff format` will re-wrap the lists; that's fine.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_dfsize.py -v`
Expected: FAIL, `ModuleNotFoundError: storage_visualizer.core.dfsize`

- [ ] **Step 3: Implement `df_size(n: int) -> str`** in integer arithmetic only, units `"KMGTPE"`, following the spec's four steps:

1. `n < 1024` → `str(n)`.
2. Largest unit `k` (1..6, `base = 1024**k`) with `n >= base`.
3. `n < 10 * base`: `tenths = ceil(10 * n / base)`; `< 100` → `f"{tenths // 10}.{tenths % 10}{unit}"`, else `f"10{unit}"`.
4. Else `whole = ceil(n / base)`; `whole == 1024` and `k < 6` → `f"1.0{next unit}"`, else `f"{whole}{unit}"`.

Ceil as `-(-a // b)`, as `used_percent` does. One-line docstring: "Format bytes like `df -h` (coreutils human_ceiling, base 1024)."

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_dfsize.py -v`
Expected: 21 passed

- [ ] **Step 5: Commit**

```bash
git add storage_visualizer/core/dfsize.py tests/core/test_dfsize.py
git commit -m "feat: format sizes like df -h"
```

---

### Task 2: Label rules and by-label reader

**Files:**
- Create: `storage_visualizer/core/labels.py`
- Test: `tests/core/test_labels.py`

**Interfaces:**
- Produces, in `storage_visualizer.core.labels`:
  - `decode_udev(name: str) -> str`
  - `network_label(device: str, mount_point: str) -> str`
  - `local_label(mount_point: str, by_label_name: str | None) -> str`
  - `read_device_labels(devices: Iterable[str], by_label_dir: str = "/dev/disk/by-label") -> dict[str, str]`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(
    "device,mp,expected",
    [
        ("//192.168.1.11/mansion", "/mnt/nas", "mansion"),
        ("//nas/share/sub/", "/mnt/x", "sub"),
        ("//nas", "/mnt/x", "x"),
        ("192.168.1.184:/volume1/media", "/mnt/nas-media", "media"),
        ("host:/export/", "/mnt/e", "export"),
        ("user@host:", "/mnt/remote", "remote"),
        ("user@host:/", "/mnt/remote", "remote"),
        ("user@host:docs", "/mnt/remote", "docs"),
        ("user@host:", "/mnt/remote/", "remote"),  # trailing slash on the mount point
    ],
)
def test_network_label(device, mp, expected):
    assert network_label(device, mp) == expected


@pytest.mark.parametrize(
    "mp,name,expected",
    [
        ("/", "debian", "System"),
        ("/", None, "System"),
        ("/mnt/hoepsis", "Hoepsis", "Hoepsis"),
        ("/mnt/hoepsis", None, "hoepsis"),
        ("/mnt/hoepsis", "", "hoepsis"),
        ("/run/media/juri/My Disk", None, "My Disk"),
    ],
)
def test_local_label(mp, name, expected):
    assert local_label(mp, name) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bork\\x20Bork", "Bork Bork"),
        ("caf\\xc3\\xa9", "café"),
        ("bad\\xff", "bad�"),
        ("plain-Name_1", "plain-Name_1"),
        ("ünï", "ünï"),
    ],
)
def test_decode_udev(raw, expected):
    assert decode_udev(raw) == expected
```

`read_device_labels` tests build a fake `/dev` under `tmp_path`: files `dev/sdc4`, `dev/dm-0`, dir `dev/disk/by-label`, links `by-label/Bork\x20Bork -> ../../sdc4` (literal backslash in the file name), `by-label/vg-data -> ../../dm-0`, a dangling `by-label/ghost -> ../../nope`, and `dev/mapper/x -> ../dm-0`.

```python
def test_read_device_labels_decodes_and_matches(fake_dev):
    assert read_device_labels([str(fake_dev / "sdc4")], str(fake_dev / "disk/by-label")) == {
        str(fake_dev / "sdc4"): "Bork Bork"
    }

def test_read_device_labels_matches_through_symlinked_device(fake_dev):
    mapper = str(fake_dev / "mapper/x")
    assert read_device_labels([mapper], str(fake_dev / "disk/by-label")) == {mapper: "vg-data"}

def test_read_device_labels_omits_unlabelled_devices(fake_dev):
    assert read_device_labels([str(fake_dev / "sdz9")], str(fake_dev / "disk/by-label")) == {}

def test_read_device_labels_missing_dir_is_empty(tmp_path):
    assert read_device_labels(["/dev/sda1"], str(tmp_path / "nope")) == {}

def test_read_device_labels_unreadable_dir_is_empty(monkeypatch, fake_dev):
    def boom(path):
        raise PermissionError("denied")
    monkeypatch.setattr(labels.os, "scandir", boom)  # or listdir — whichever the code uses
    assert read_device_labels([str(fake_dev / "sdc4")], str(fake_dev / "disk/by-label")) == {}
```

`fake_dev` is a fixture in the test module returning `tmp_path / "dev"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core/test_labels.py -v`
Expected: FAIL, `ModuleNotFoundError: storage_visualizer.core.labels`

- [ ] **Step 3: Implement the four functions** in `storage_visualizer/core/labels.py`:
  - `basename(mp)` helper: `posixpath.basename(mp.rstrip("/"))`; pure string, no filesystem.
  - `network_label`: rules in the spec's "Network" list (strip `//host` for sources starting `//`, else everything through the first `:`; strip trailing `/`; last component; empty → `basename(mp)`).
  - `local_label`: `"/"` → `"System"`; truthy name → name; else `basename(mp)`.
  - `decode_udev`: `re.sub(rb"\\x([0-9a-fA-F]{2})", ...)` over `name.encode("utf-8")`, then `.decode("utf-8", errors="replace")`.
  - `read_device_labels`: list the dir, catching `OSError` (covers `FileNotFoundError`) → `{}`; map `os.path.realpath(entry path)` → `decode_udev(entry name)`; return `{d: by_real[os.path.realpath(d)] for d in devices if os.path.realpath(d) in by_real}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/core/test_labels.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add storage_visualizer/core/labels.py tests/core/test_labels.py
git commit -m "feat: label rules for local and network volumes"
```

---

### Task 3: Labels on MountInfo and Volume

**Files:**
- Modify: `storage_visualizer/core/models.py` (`MountInfo`)
- Modify: `storage_visualizer/core/enumerator.py` (`enumerate_mounts`, `enumerate_system_mounts`)
- Modify: `storage_visualizer/core/usage.py` (`_base`)
- Test: `tests/core/test_enumerator.py`, `tests/core/test_usage.py`, `tests/core/test_models.py`

**Interfaces:**
- Consumes: `network_label`, `local_label`, `read_device_labels` (Task 2).
- Produces: `MountInfo.label: str = ""` (last field); `enumerate_mounts(partitions: Iterable[Any], labels: Mapping[str, str]) -> list[MountInfo]`; `Volume.label == mount.label` for ok and unavailable volumes.

- [ ] **Step 1: Update existing tests and write the failing ones.**
  - `test_enumerator.py`: `mps()` and every direct `enumerate_mounts(parts)` call pass `{}` as `labels`. Expected `MountInfo`s gain the label: `test_result_fields` → `MountInfo("/dev/sdd1", "/mnt/backup", "ext4", False, "backup")`; `test_keeps_network_filesystems_flagged` → label `network_label(device, "/mnt/net")` written out per case (`export`, `export`, `share`, `share`, `net`); add a `label` column to its parametrize.
  - New enumerator tests:

```python
def test_local_label_from_mapping():
    [m] = enumerate_mounts([Part("/dev/sda2", "/mnt/hoepsis", "ntfs3", "")], {"/dev/sda2": "Hoepsis"})
    assert m.label == "Hoepsis"

def test_root_is_system_despite_mapping():
    [m] = enumerate_mounts([Part("/dev/nvme0n1p4", "/", "ext4", "")], {"/dev/nvme0n1p4": "debian"})
    assert m.label == "System"

def test_network_label_on_mount():
    [m] = enumerate_mounts([Part("//192.168.1.11/mansion", "/mnt/nas", "cifs", "")], {})
    assert m.label == "mansion"

def test_label_fallback_uses_kept_mount_point():
    parts = [Part("/dev/sda2", "/srv/data/deep", "btrfs", ""), Part("/dev/sda2", "/srv/data", "btrfs", "")]
    [m] = enumerate_mounts(parts, {})
    assert (m.mount_point, m.label) == ("/srv/data", "data")
```

  - Replace `test_enumerate_system_mounts_uses_all_true` with one that also monkeypatches `enumerator.read_device_labels` to record its argument (as a list) and return `{"/dev/sda1": "root-fs", "/dev/sdb1": "Data"}`; partitions `/dev/sda1 → /`, `tmpfs → /tmp`, `//nas/share → /mnt/nas (cifs)`, `/dev/sdb1 → /mnt/data`. Assert `calls == [True]`, the recorded devices are `["/dev/sda1", "/dev/sdb1"]` (only `/dev/`), and the result labels are `["System", "Data", "share"]` in mount-point order (`/`, `/mnt/data`, `/mnt/nas`).
  - `test_models.py`: add `test_mountinfo_label_defaults_empty` (`MountInfo("/dev/sda1", "/mnt/x", "ext4", False).label == ""`) and `test_mountinfo_label_field` (fifth positional argument lands in `.label`).
  - `test_usage.py`: `MOUNT = MountInfo("/dev/sdd1", "/mnt/backup", "ext4", False, "backup")`; expected `Volume` label in `test_probe_computes_df_numbers` becomes `"backup"`; the unavailable assertion becomes `v.label == "backup"`. Add:

```python
def test_unavailable_keeps_label():
    assert unavailable(MOUNT).label == "backup"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/core -v`
Expected: FAIL (`TypeError` on the extra `labels` argument / `MountInfo` field, label mismatches)

- [ ] **Step 3: Implement**
  - `MountInfo`: add `label: str = ""` as the last field.
  - `enumerate_mounts`: required `labels: Mapping[str, str]`; build each `MountInfo` with `network_label(p.device, p.mountpoint)` if network else `local_label(p.mountpoint, labels.get(p.device))`.
  - `enumerate_system_mounts`: `parts = psutil.disk_partitions(all=True)`; `labels = read_device_labels([p.device for p in parts if p.device.startswith("/dev/")])`; `return enumerate_mounts(parts, labels)`. Keep the `# all=True: ADR-003` comment; import `read_device_labels` into `enumerator`'s namespace so the test can monkeypatch it.
  - `usage._base`: label = `mount.label`.

- [ ] **Step 4: Run all tests with the coverage gate**

Run: `pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100`
Expected: all pass, `core/` 100%. (ui tests that build `Volume`/`MountInfo` positionally are unaffected: `MountInfo.label` has a default.)

- [ ] **Step 5: Commit**

```bash
git add storage_visualizer/core tests/core
git commit -m "feat: put volume labels on mounts and volumes"
```

---

### Task 4: Pie text lines and width

**Files:**
- Modify: `storage_visualizer/ui/pie_widget.py`
- Modify: `storage_visualizer/ui/main_window.py` (`set_mounts`)
- Test: `tests/ui/test_pie_widget.py`, `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `df_size` (Task 1); `MountInfo.label` (Task 3).
- Produces: `pie_text(volume: Volume | None, mount_point: str, label: str) -> list[str]` and `PieWidget(mount_point: str, label: str = "", parent: QWidget | None = None)` in `ui.pie_widget`; module constants `WORST_CASE_NUMBERS = "1022M used · 1022M free"`, `MIN_WIDTH = 140`.

- [ ] **Step 1: Write the failing smoke tests**

```python
OK_LABELLED = Volume("/", "System", "ext4", False, "ok", 420536655872, 122371670016, 276727062528)

def test_pie_text_ok_has_three_df_lines():
    assert pie_text(OK_LABELLED, "/", "System") == ["System", "114G used · 258G free", "392G total"]

@pytest.mark.parametrize("volume", [None, Volume("/x", "x", "nfs", True, "unavailable", None, None, None)])
def test_pie_text_label_only_when_not_ok(volume):
    assert pie_text(volume, "/x", "x") == ["x"]

@pytest.mark.parametrize(
    "volume,label,expected",
    [
        (Volume("/x", "fresh", "ext4", False, "unavailable", None, None, None), "old", "fresh"),
        (Volume("/x", "", "ext4", False, "unavailable", None, None, None), "old", "old"),
        (None, "", "/x"),
    ],
)
def test_pie_text_name_fallback(volume, label, expected):
    assert pie_text(volume, "/x", label)[0] == expected

def test_pie_width_fits_worst_case_numbers(qtbot):
    w = PieWidget("/mnt/nas-media-4k", "media-4k")
    qtbot.addWidget(w)
    assert w.width() >= max(MIN_WIDTH, w.fontMetrics().horizontalAdvance(WORST_CASE_NUMBERS) + 8)
    assert w.height() > 170  # three text lines below the pie
```

Extend `test_pie_renders_each_state` to construct `PieWidget(..., "Very Long Label …")` and include `OK_LABELLED`. In `test_main_window.py`:

```python
def test_new_pie_gets_mount_label(qtbot):
    w = MainWindow(); qtbot.addWidget(w)
    w.set_mounts([MountInfo("/dev/sda2", "/mnt/hoepsis", "ntfs3", False, "Hoepsis")])
    assert w.pies["/mnt/hoepsis"].label == "Hoepsis"
```

(so `PieWidget` also gets a read-only `label` property, the construction label.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ui -v`
Expected: FAIL, `ImportError: cannot import name 'pie_text'`

- [ ] **Step 3: Implement**
  - `pie_text` per the spec (name fallback: `volume.label` → `label` → `mount_point`; ok → three lines using `df_size`).
  - `PieWidget.__init__(mount_point, label="", parent=None)`: store label; width `max(MIN_WIDTH, self.fontMetrics().horizontalAdvance(WORST_CASE_NUMBERS) + 8)`; height `10 + _PIE_SIZE + 6 + 3 * fontMetrics().height() + 6`; `setFixedSize`. Centre the pie horizontally in the (possibly wider) widget. Keep `self._width`/`self._height` for painting instead of the module `_WIDTH`/`_HEIGHT`.
  - `paintEvent`: after the centre text, draw each `pie_text(...)` line in its own row (`QRectF(2, top + i * lh, width - 4, lh)`, `AlignHCenter | AlignTop`); elide only line 0 with `ElideMiddle`.
  - `MainWindow.set_mounts`: build `{m.mount_point: m for m in mounts}` and create `PieWidget(mp, by_mp[mp].label)`.

- [ ] **Step 4: Run the full suite and lint**

Run: `pytest --cov=storage_visualizer.core --cov-fail-under=100 && ruff check . && ruff format --check .`
Expected: all pass, no lint or format errors

- [ ] **Step 5: Commit**

```bash
git add storage_visualizer/ui tests/ui
git commit -m "feat: show label and df -h numbers under each pie"
```

---

### Task 5: Docs

**Files:**
- Modify: `docs/DECISIONS.md`, `docs/PLANNING.md`, `docs/TESTING.md`

- [ ] **Step 1: DECISIONS.md**
  - Add **ADR-012: Read `/dev/disk/by-label` on the UI thread at enumerate time**, **Status: Proposed** (flipped to Accepted at finish by recording-decisions), date 2026-10-20, in the file's ADR format. Content from the spec's "Decisions": devtmpfs is a kernel pseudo-filesystem that can't block like a mounted network filesystem, same reasoning as psutil's `/proc/self/mounts` read; alternatives table: by-label on UI thread at enumerate (Accepted), resolve in probe worker (Rejected: no label while loading/unavailable, repeated per probe), UDisks2 (Rejected: ADR-003, D-Bus dependency). References: this spec and plan.
  - Replace Key Principle 2 with, verbatim: "**The UI thread never makes calls that can block on a mounted filesystem** (statvfs etc.); reading kernel pseudo-filesystems (/proc, devtmpfs under /dev) is fine. Usage probes run in per-mount workers (ADR-004/011)."

- [ ] **Step 2: PLANNING.md**
  - Data Models: `MountInfo` gains `label: str = ""  # see Volume Rules → Labels`; `Volume.label` comment becomes `# copied from MountInfo.label`.
  - Volume Rules: add a "Labels" bullet list: network = last path component of the source (trailing `/` stripped), else the mount point's last component; local = `/` → System, else by-label name (udev `\xNN` decoded), else the mount point's last component; resolved at enumerate time (ADR-012).
  - Non-Functional Requirements / Responsiveness: "never calls `statvfs`" stays; add "by-label is read at enumerate time (ADR-012)".
  - Testing Approach manual list: "numbers match `df -h`" becomes "label follows the label rules; used/free/total match `df -h` Used/Avail/Size exactly, no number elided".

- [ ] **Step 3: TESTING.md** checklist: replace "Numbers match `df -h` for every shown volume" with "Every pie's label follows the label rules (PLANNING.md Volume Rules → Labels); `<used> used · <free> free` / `<total> total` match `df -h` Used / Avail / Size exactly; no number is elided". Add a Common Bugs row: "Label shows `\x20` | by-label name not decoded | `decode_udev` (core/labels.py)".

- [ ] **Step 4: Verify and commit**

Run: `ruff check . && ruff format --check .` (docs/ is excluded; this just confirms nothing else changed)

```bash
git add docs/DECISIONS.md docs/PLANNING.md docs/TESTING.md
git commit -m "docs: describe volume labels, propose ADR-012, reword key principle 2"
```

---

### Task 6: Manual check (STOP, human hand-off)

The agent can't see the window. Stop here and ask the human to run, from the checkout:

```bash
python -m storage_visualizer    # and in another terminal: df -h
```

and report pass/fail for each item in `docs/TESTING.md`'s checklist, in particular:
- [ ] Labels: `/` → System; local volumes show their by-label names (e.g. a label with a space shows the space); network shares show the last component of their source.
- [ ] Every pie's three numbers match `df -h` Used / Avail / Size exactly; no number is elided.
- [ ] "…" and "unavailable" pies show their label only.
- [ ] Earlier items (USB hot-plug, no flicker, thread count, clean exit, Ctrl+C) still pass.

Record the result; fix failures with a failing test first, then re-run the check.
