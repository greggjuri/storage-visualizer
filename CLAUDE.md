# CLAUDE.md

Visual Storage Monitor: a small always-available window on Debian 13 / KDE Plasma 6 (Wayland) showing every mounted volume, local and network, as a used/free pie chart.

**Stack**: Python 3.13 | PySide6 (Qt 6, native Wayland) | psutil + os.statvfs | pytest, pytest-qt | pipx + XDG autostart

## Commands

```bash
pytest --cov=storage_visualizer.core --cov-report=term-missing --cov-fail-under=100   # all tests; 100% line coverage gate on core/ only
ruff check . && ruff format --check .                                                 # lint + format check
python -m storage_visualizer                                                          # run locally
pipx install --force .                                                                # install (or: pipx upgrade storage-visualizer)
```

## Workflow

Superpowers drives the process (brainstorming → plan → execution → review → finish).
This project adds a persistent context layer on top:

- **Before designing or planning:** use `ce-superpowers:project-context`. Accepted ADRs in
  `docs/DECISIONS.md` are binding; contradicting one needs explicit sign-off.
- **Before finishing a branch:** use `ce-superpowers:recording-decisions` so new ADRs,
  PLANNING.md changes and TASK.md updates merge with the code.
- Specs go in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/` (Superpowers defaults).
- Backlog lives in `docs/TASK.md`. Pick features from there; new ideas go there, not in chat.
- Pilot: log process friction in `docs/PILOT-FINDINGS.md`.

### TDD scope
Default: strict TDD per Superpowers. Exceptions:
- `core/` (Enumerator, UsageProbe, Volume): strict TDD against fake psutil/statvfs data, no real mounts, no Qt.
- `ui/` (MainWindow, PieWidget, FlowLayout, TrayIcon, Refresher): pytest-qt smoke tests only (widgets build, `set_mounts` adds/removes pies, `update_volume` updates them).
- Tray, frameless window and KWin rule behavior: covered by the manual checklist in `docs/TESTING.md`, not automated tests.

## Rules

- Max 500 lines per file; split into modules before you hit it
- Conventional commits: `feat:` `fix:` `refactor:` `docs:` `test:`
- Coverage floor: 100% line coverage for `core/` only (`pytest --cov=storage_visualizer.core --cov-fail-under=100`); `ui/` has no coverage floor, smoke tests only
- Never commit secrets
- After changes to mount enumeration, usage probing, polling, the window or the tray:
  run the manual checklist in `docs/TESTING.md` before finishing

## Conventions

- `core/` never imports Qt; each tick diffs the mount list to add/remove pies; results update pies one volume at a time (ADR-009).
- The UI thread never calls `statvfs` (ADR-004).
- Debian 13 + KDE Wayland only: no portability code (ADR-001).

## Gotchas

- `psutil.disk_partitions(all=False)` silently drops NFS/CIFS; always use `all=True` plus our filters (ADR-003).
- On Wayland the app can't position itself or stay on top; that comes from a KWin rule matched on app id `storage-visualizer` (ADR-006).

## Reference

- `docs/PLANNING.md`: architecture, data models, constraints
- `docs/DECISIONS.md`: ADRs
- `docs/TASK.md`: backlog
- `docs/TESTING.md`: manual checklist, common bugs
