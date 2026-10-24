# Visual Storage Monitor - Testing Standards

## Testing Pyramid

```
        /\
       /  \     Manual checklist (few)
      /----\
     /      \   pytest-qt smoke tests (some)
    /--------\
   /          \ core/ unit tests (many)
  --------------
```

## When to Test What

| Test Type | When | Tools |
|-----------|------|-------|
| Unit (`core/`) | Every code change, strict TDD | pytest with fake psutil/statvfs data |
| Smoke (`ui/`) | Every UI change | pytest-qt |
| Manual | Before finishing a branch that touches enumeration, probing, polling, window or tray | Checklist below |

## Automated Tests

```bash
.venv/bin/pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100
ruff check . && ruff format --check .
```

**Minimum Coverage**: 100% line coverage for `core/` only; `ui/` has no coverage floor, smoke tests only.

## Manual Integration Testing

Required before finishing any branch that touches:
- Mount enumeration or filters
- Usage probing, worker threads, busy-at-tick unavailable
- Polling / pie diffing
- Window, tray, app id or autostart

### Setup
1. `pipx install --force .` (or `.venv/bin/python -m storage_visualizer` from the checkout; Debian has no `python`, and the deps live in `.venv`)
2. Have a USB drive and an NFS or SMB share available
3. Keep these handy:
   - Numbers: `df -h`
   - Threads: `watch -n5 'ps -o nlwp= -p $(pgrep -f storage_visualizer)'`
   - CPU: `pidstat -p $(pgrep -f storage_visualizer) 5` (sysstat), or `top -p $(pgrep -f storage_visualizer)`
   - USB: mount through the KDE device notifier, confirm the path with `findmnt`

### Checklist
- [ ] Every pie's label follows the label rules (the Labels bullet under PLANNING.md Volume Rules); `<used> used · <free> free` / `<total> total` match `df -h` Used / Avail / Size exactly; no number is elided
- [ ] Plug in a USB drive → pie appears within 30 s; unmount → pie disappears
- [ ] Existing pies don't flicker to "…" on a tick
- [ ] Drag the width narrower and wider → pies rewrap; the height follows without visible jitter or clipped rows
- [ ] At a width you chose, plug in or remove a USB drive → the width stays; only the height changes
- [ ] First launch with more pies than fit the screen → the window is no wider than the screen
- [ ] Restored size from the KWin rule → the height still fits, even when the remembered height is stale (N/A until the KWin rule exists)
- [ ] Thread count returns to baseline between polls
- [ ] Stop the NFS/SMB server → that pie shows "unavailable" within one poll after the probe hangs, the UI stays responsive, and the thread count stays flat over several polls
- [ ] Tray icon shows/hides the window; tray Quit → clean exit, no traceback (N/A until the tray lands)
- [ ] Close the window → clean exit, no traceback
- [ ] Ctrl+C in the terminal → exits immediately, no traceback
- [ ] KWin rule keeps the window on top and in place across logout/login
- [ ] No tracebacks in the terminal / journal

### Common Bugs to Catch

| Bug | How to Detect | Fix Pattern |
|-----|---------------|-------------|
| Network share missing | Share in `df -h` but no pie | Check `all=True` and the network fstype keep-list (ADR-003) |
| Duplicate pies | Same device twice (btrfs subvolume, bind mount) | Dedupe by device, keep shortest mount point |
| UI freeze on dead share | Window stops repainting | Something called `statvfs` on the UI thread (ADR-004) |
| Thread leak | `nlwp` grows every poll | Re-dispatch while a probe is still outstanding (ADR-004) |
| Window not pinned | Not on top / wrong position after login | KWin rule must match app id `storage-visualizer` |
| Stale "unavailable" after recovery | Share answers but its pie stays grey for a poll | Release the busy flag and deliver the result under the probe lock (ADR-011) |
| Free space off vs `df` | Free differs by reserved blocks | Use `f_bavail`, not `f_bfree` |
| Label shows `\x20` | by-label name not decoded | `decode_udev` (core/labels.py) |

## Testing Patterns

### core/ Unit Tests
```python
# Test file naming: tests/core/test_{module}.py

Part = namedtuple("Part", "device mountpoint fstype")

def test_enumerate_keeps_ext4_and_drops_tmpfs():
    # Arrange
    parts = [
        Part("/dev/nvme0n1p4", "/", "ext4"),
        Part("tmpfs", "/tmp", "tmpfs"),
    ]

    # Act
    mounts = enumerate_mounts(parts)

    # Assert
    assert [m.mount_point for m in mounts] == ["/"]
```

### ui/ Smoke Tests
```python
# Test file naming: tests/ui/test_{widget}.py

def test_update_volume_sets_matching_pie(qtbot):
    # Arrange
    mounts = [
        MountInfo("/dev/a1", "/", "ext4", False),
        MountInfo("/dev/b1", "/mnt/backup", "ext4", False),
    ]
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_mounts(mounts)
    vol = Volume("/mnt/backup", "/mnt/backup", "ext4", False, "ok", 100, 40, 60)

    # Act
    window.update_volume(vol)

    # Assert
    assert list(window.pies) == ["/", "/mnt/backup"]
    assert window.pies["/mnt/backup"].volume == vol
```

## Bug Report Template

```markdown
### Bug
[Brief description]

### Environment
- Plasma version / session: {Wayland}
- Mount table: `findmnt -o TARGET,SOURCE,FSTYPE`

### Steps to Reproduce
1. {Step 1}
2. {Step 2}

### Expected
[What should happen]

### Actual
[What actually happened]

### Output
```
[Paste tracebacks / journalctl output]
```
```

## Debugging Workflow

1. **Reproduce**: Confirm the bug exists
2. **Isolate**: Capture the mount table and turn it into a fake-psutil fixture
3. **Diagnose**: Check terminal/journal output, thread count, `findmnt`
4. **Fix**: Make minimal change
5. **Verify**: Confirm fix works
6. **Test**: Add test to prevent regression

## Lessons Learned

{Add lessons as you encounter and fix bugs}

---

## Pre-Finish Checklist

- [ ] All tests pass
- [ ] `core/` line coverage is 100%
- [ ] No ruff errors
- [ ] Manual checklist completed (if applicable)
- [ ] Idle CPU effectively zero between polls
