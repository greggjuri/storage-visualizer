# ce-superpowers Pilot: Findings

Pilot project: storage-visualizer (Visual Storage Monitor). Started 2026-10-17.
Purpose: find what to fix in the ce-superpowers templates, skills, hooks and guide before using them on real projects.

Status: **Open** = not fixed yet · **Fixed** = changed in ce-superpowers (commit noted) · **Works** = confirmed working as designed, keep it

Each entry: what happened, where the fix belongs, what to change.

## Setup and Guide (GETTING-STARTED.md)

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| G1 | Guide assumed `git init` locally; a repo created on GitHub with a README rejects the first push | GETTING-STARTED | Local-first flow with `gh repo create --source . --push` | Fixed (guide rewrite, 2026-10-17) |
| G2 | `mkdir docs` with nothing in it isn't tracked by git, so it never reached GitHub | GETTING-STARTED | Note it; docs/ lands with the drafts | Fixed (guide rewrite) |
| G3 | `&&` chains fail in Windows PowerShell 5.1 | GETTING-STARTED | Use Git Bash or PowerShell 7 | Fixed (guide rewrite) |
| G4 | Misplaced backtick in `claude plugin uninstall <name> --scope user` | GETTING-STARTED | Typo fix | Fixed (guide rewrite) |
| G5 | Embedded feature-loop diagram didn't survive export | GETTING-STARTED | Replaced with text | Fixed (guide rewrite) |
| G6 | claude.ai's GitHub sync reads only `main`, so the "optional spec review in claude.ai" step can't see a spec on an unmerged branch | GETTING-STARTED + skill | Push the feature branch after the spec commit and after the plan commit; for review, paste the spec or have claude.ai fetch the branch | Open |

## Project Instructions (PROJECT-INSTRUCTIONS.md)

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| P1 | Short DECISIONS format had no template tail (Template / Status Definitions / Key Principles) that `recording-decisions` depends on, and ce-init never touched existing files | ce-init | ce-init appends missing tail sections after the last ADR | Fixed (33c7941) |
| P2 | The "Paste everything below the line…" header gets pasted into the Project instructions along with the rest | PROJECT-INSTRUCTIONS | Move the paste instruction out of the file (into GETTING-STARTED), so the whole file is pasteable | Open |
| P3 | `Repository: {github.com/greggjuri/repo}` placeholder is easy to leave unfilled | PROJECT-INSTRUCTIONS | Put fill-in fields at the very top as a short checklist | Open |

## Hooks

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| H1 | `decisions-index.sh` drops any ADR line containing `{`, which hides real titles with braces | hooks/decisions-index.sh | Filter only template placeholders, e.g. `\{[A-Za-z_ ]+\}`, not any brace | Open (documented as "no `{` in titles") |
| H2 | SessionStart ADR index showed up after `/clear` and project-context used it | — | — | Works |

## ce-init

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| I1 | Replaced the web TESTING.md checklist with the desktop checks from PLANNING.md; appended the DECISIONS tail without touching ADRs | — | — | Works |
| I2 | Left Key Principles as template placeholders; project-context reads the whole file and may take them literally | commands/ce-init.md | Seed Key Principles from Accepted ADRs and PLANNING constraints, or leave the section empty (no placeholder text) | Open |
| I3 | Coverage target asked as one project-wide number; this project needed 100% on core/ only, none on ui/ | commands/ce-init.md, templates/CLAUDE.md | Ask for coverage per package/scope; CLAUDE.md template shows a scoped `--cov=... --cov-fail-under=N` example | Open |
| I4 | Template dev tools are unpinned; ruff 0.17 started formatting Python blocks inside Markdown and rewrote approved docs | templates (CLAUDE.md / TESTING.md / pyproject guidance) | Pin dev tool versions at scaffold time; exclude docs/ from the formatter by default | Open |

## Brainstorming and Specs

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| B1 | project-context confirmed ADRs instead of re-asking stack questions; spec had a proper Context section citing ADRs | — | — | Works |
| B2 | Spec weighed alternatives ("approach 1") for the thread→Qt bridge but said "no new ADR needed", contradicting `recording-decisions`' own criteria | skills/project-context or recording-decisions | During brainstorming, apply the "what counts as a decision" test to every choice between alternatives and draft the ADR as Proposed then | Open |
| B3 | Spec baked in machine state ("should show two pies"); a third mounted drive made the manual check look like a failure | skills/project-context (spec guidance) | Specs and plans state expected behavior as rules, not as a snapshot of the dev machine | Open |
| B4 | During Polling refresh brainstorming, a choice between alternatives (where the refresh cycle lives) was proposed as ADR-010 up front, as recording-decisions intends | — | — | Works |

## Plans and Execution

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| E1 | Plan told the agent to run the GUI and verify visually; an agent can't see the window, and `app.exec()` blocks | templates/CLAUDE.md (Workflow) | Manual/visual checks are human hand-offs: the plan marks them STOP, the agent waits for a pass/fail report and records it | Open |
| E2 | Plan tasks said "per the spec"; subagent implementer briefs didn't include the spec, so details (pseudo-fs list, main() order) were missing until the controller pointed briefs at the spec | skills (plan guidance) | Plans inline every detail a task needs, or each task names the exact spec sections to read | Open |
| E3 | Code recommended Native execution while the plan header (from Superpowers) says subagent-driven is recommended | — | Note only; pick per feature. Subagent-driven was used for the pilot's first feature | Note |
| E4 | Subagent-driven per-task review worked; final branch review found only doc nits | — | — | Works |
| E5 | Polling refresh spec marks the manual check as a STOP hand-off and states expectations as rules (E1/B3 applied) | — | — | Works |

## Finishing (recording-decisions)

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| R1 | Step 8 ("show the human ADRs and diffs, ask for corrections") was skipped; docs were committed first and shown afterwards | skills/recording-decisions | Make step 8 an explicit hard stop before the commit, also in subagent-driven runs | Open |
| R2 | After checking off the finished item, TASK.md's Next section was left empty | skills/recording-decisions | Step 7: if Next is empty, promote the top Backlog item | Open |
| R3 | Known Issues and the quit-time race from review were recorded correctly in TASK.md | — | — | Works |
