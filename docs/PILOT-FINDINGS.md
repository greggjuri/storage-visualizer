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
| E6 | Native (executing-plans) vs subagent-driven (E4). Polling refresh: 5 code/doc tasks committed in about 3 min by commit time (00:31–00:34), no per-task reviews, one final review round on opus (~1.6 min): 0 Critical, 0 Important, 3 Minor (removed pie not hidden before deleteLater, adjustSize ignoring a not-yet-shown pie, overmount collapse). Commit timestamps don't measure effort (they only show when commits landed). Session usage from /cost for the whole Polling refresh session (brainstorming, spec, plan, execution, final review): $6.47, 15m 7s API time (11h 55m wall, mostly waiting on the human), Opus 5.5 25.3k input / 77.3k output / 10.7M cache read / 360k cache write tokens. Pie per volume (E4): 9 implementation commits 19:27–19:34 by commit time, no comparable usage figure, so future comparisons should record usage per feature; per-task reviews (round count not recorded in the repo), final review found doc nits only. The two Qt lifecycle minors sat in Task 3 and a per-task reviewer might have caught them earlier, but the final review caught them anyway and they were fixed with tests at the user's request. TDD, not review, caught the one real slip: the first hide test passed vacuously because Qt defers show()  Network share probe (second Native data point): 4 code/doc tasks plus a STOP manual check, no per-task reviews, one final whole-branch review on opus (~3.7 min, 83k subagent tokens): 0 Critical, 0 Important, 8 Minor, 7 fixed with tests, 1 deferred as a Known Issue. The human then had one fix pinned with an extra red→green test. The final review was stopped once by the human before it reported and then restarted with the same brief (reason for the stop not captured). Session usage from /cost for the whole Network share probe session (brainstorm → finish), same scope as the Polling refresh figure: $5.61, 14m 12s API time (2d 9h 50m wall, mostly waiting on the human), Opus 5.5 17.4k input / 77.6k output / 8.9M cache read / 321.1k cache write tokens (Haiku negligible). 1 prompt-cache miss after idling past the 1 h TTL. Two Native runs now: $6.47 and $5.61 per feature. Final review found no Important issues either time. Volume labels (subagent-driven, third data point; ledger summary per E8): 5 code/doc tasks plus a STOP manual check (1 pass, 2 pass, 3 n/a, 4 pass). Per-task reviews on sonnet, one round each: T1 df_size 0C/0I/2 Minor, T2 label rules 0/0/3, T3 enumerate wiring 0/0/2 (+2 ⚠️ the controller resolved), T4 PieWidget 0/0/3 (+1 controller note on the total fallback), T5 docs 0/0/2; no fix rounds. Final whole-branch review on opus (~1.9 min, 88.8k subagent tokens): 0 Critical, 0 Important, 4 Minor; one fix dispatch on haiku fixed the 2 doc minors, a scoped haiku re-review found 1 residual wording minor (folded into recording-decisions), and the other 2 went to TASK.md Known Issues. Implementers on sonnet, fix and re-review on haiku. 4 controller rulings recorded in the ledger, none changed behaviour. Session usage from /cost for the whole Volume labels session (brainstorm → PR, same scope as the Native figures): $9.45, 20m 44s API time (18h 56m wall, mostly waiting on the human). Opus 5.5 (controller + final review): 83.2k input / 83.5k output / 15.1M cache read / 414.1k cache write ($8.07). Sonnet 5.5 (implementers + task reviewers): 673 input / 31.7k output / 1.6M cache read / 295.3k cache write ($1.37). Haiku 5.5 (fix + re-review): 1.4k input / 5.4k output / 278.1k cache read / 63.7k cache write ($0.01). 2 prompt-cache misses, one after idling past the 1 h TTL and one after a context compaction (115.5k re-cached). So subagent-driven came to $9.45 against $6.47 and $5.61 for the two Native runs, about 1.5–1.7×. Most of the extra cost is the Opus controller ($8.07, more than either Native session in total), not the subagents ($1.38). Per-task reviews found only Minors and needed no fix rounds; as in both Native runs, nothing Important surfaced anywhere. Flow layout (Native, fourth data point): 3 code/doc tasks plus a STOP manual check, no per-task reviews, one final whole-branch review on opus (~2.9 min, 71k subagent tokens): 0 Critical, 1 Important (a Review Focus case claimed pinned but untested, see E11), 5 Minor; the Important fixed with a red→green test, and the human promoted 2 Minors to fixes (each with a test or comment), 3 Minors to Known Issues. Session usage from /cost for the whole Flow layout session (brainstorm → PR, same scope as the other figures): $5.20, 12m 12s API time (2d 16h 58m wall, mostly waiting on the human), Opus 5.5 13.3k input / 73.4k output / 7.7M cache read / 294.5k cache write tokens (Haiku negligible). 1 prompt-cache miss after idling past the 1 h TTL (82.4k re-cached). Three Native runs now: $6.47, $5.61 and $5.20 per feature, against $9.45 for subagent-driven; this run's final review found 1 Important, the first in any mode, and it was a plan defect (E11), not an implementation slip. Conclusion: For ≤6 mostly chained tasks, default to Native + strongest-model final review; per-task review found nothing Important in any of 3 runs, and subagent-driven's extra cost is controller overhead (~$8 Opus vs $1.38 subagents). Use subagent-driven for large or risky features. Caveats: feature sizes differ; idle-gap cache misses affect both modes. | — | Compare again on a feature with more cross-task interfaces before picking a default | Proposed guidance |
| E7 | executing-plans says "do not pause; only four things stop you" (destructive, security, external side effect, broken plan); a plan task marked "STOP, human hand-off" for the manual check is none of these, so the executor has to rule the skill and the plan into agreement | ce-superpowers plan guidance / templates/CLAUDE.md (Workflow) | State in the plan header/CLAUDE.md that a STOP hand-off task is a fifth sanctioned stop for inline execution, and that the final review may run while the human does the check | Open (applied in this repo: the Network share probe and Volume labels plan headers name the hand-off as a sanctioned stop; under subagent-driven, the final review ran while the human did the check. Still needs the fix in ce-superpowers) |
| E8 | subagent-driven execution deletes its ledger (.superpowers/sdd/...) at finish, losing review-round counts needed to evaluate the process | Superpowers / ce-superpowers finishing | Keep a short summary (tasks, review rounds, issues per round) in the PR body or PILOT-FINDINGS before deleting | Open |
| E9 | Plan execution is strictly sequential even when tasks are independent | writing-plans + execution | Plans could mark independent tasks; parallel execution needs a worktree per task and a merge step. Low value for small chained features; feature-level parallelism (separate branches/sessions) works today | Idea |
| E10 | The plan's verbatim test code had a Qt object-lifetime bug (parent discarded → segfault); caught by running the tests, not by plan review (Flow layout) | writing-plans | Plans for Qt/PySide code should state ownership rules (keep parents alive; layouts own their items; don't build QWidgetItem in Python) | Open |
| E11 | A Review Focus item claimed "pinned by test_first_show_keeps_one_row_width", but that test never exercised the case (zero mounts at first show); the final review caught it as Important (Flow layout) | writing-plans self-review | Every "pinned by test X" claim must be verified by watching X fail without the fix, or by stating the exact precondition the test sets up | Open |

## Finishing (recording-decisions)

| # | Finding | Fix belongs in | Change | Status |
|---|---|---|---|---|
| R1 | Step 8 ("show the human ADRs and diffs, ask for corrections") was skipped; docs were committed first and shown afterwards. Applied correctly in the Native run (Polling refresh); skipped only under subagent-driven (Pie per volume) | skills/recording-decisions | Make step 8 an explicit hard stop before the commit, also in subagent-driven runs | Open (shown before commit under subagent-driven too (Volume labels)) |
| R2 | After checking off the finished item, TASK.md's Next section was left empty | skills/recording-decisions | Step 7: if Next is empty, promote the top Backlog item | Open (applied in this repo (Volume labels promoted Flow layout); skill fix still needed) |
| R3 | Known Issues and the quit-time race from review were recorded correctly in TASK.md | — | — | Works |
| R4 | On the third feature, the spec commit wasn't pushed (G6) and a new ADR was recorded Accepted at spec time instead of Proposed | skills/project-context + recording-decisions | State both rules explicitly in the brainstorming→spec handoff, not only in recording-decisions | Open |
