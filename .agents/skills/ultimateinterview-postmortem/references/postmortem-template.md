# Postmortem Output Templates

Two skeletons: the per-change postmortem report, and the durable lessons file.

## 1. Postmortem Report

Write to `.ultimateinterview/<slug>/postmortem.md`.

# Postmortem: <slug>

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| PR / commits / branch / working tree |  |  |

Handoff written: <date>. Implementation examined through: <date/commit>.

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled / escaped-requirement / scope-drift / divergent-implementation / deferred-outcome |  |  |  |

## Escaped Requirements

One row here per `escaped-requirement` row in the Divergence Table (the lint enforces the 1:1 match). Weight uses the ledger impact scale.

| Behavior found in code | Owning lens | Failure class | Weight | Evidence (diff hunk + ledger/transcript line or absence) |
| --- | --- | --- | --- | --- |
|  | viewpoint / domain/state / goal/obstacle / misuse / quality / controlled-language / core-path | trigger-too-narrow / enumeration-miss / scoring-starved / answer-unpressured / synthesis-loss | 1/2/3/5 |  |

Owning-lens values are ultimateinterview's canonical trigger names. Use `core-path` when the miss belongs to always-on machinery (contextual observation, the framing challenge): those are `enumeration-miss` by definition and become routing lessons only if a repo-observable signal could have routed a heavier lens instead. `known-deferred` items are not escapes - record them under Deferred Outcomes.

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
|  |  | yes/no |  |

## Verification Execution

Whether the spec's Verification Commands actually ran and passed - run them when cheap; name the ones not executed. Note any command that needed host adaptation (a substituted interpreter is a portability defect `verification_lint.py` should have caught at handoff time).

| Verification command / check | Ran? | Result |
| --- | --- | --- |
|  | yes/no/adapted: <how> | pass/fail/skipped: <why> |

## Scope Drift / Divergent Implementations

| Item | Class | What the handoff said | What was built | User must re-decide? |
| --- | --- | --- | --- | --- |
|  | scope-drift / divergent-implementation |  |  | yes/no |

## Lessons Appended Or Updated

| Signal | Lens to trigger | Failure class | Evidence | Date |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Lessons Fire-Tracking

One row per active lesson per store, every run - `no-signal` is a verdict, not a reason to skip the row. `postmortem_lint.py --lessons` fails the report on any missing row.

| Store | Row | Signal (truncated) | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md / ultimateinterview-lessons.md | 1 |  | fired / no-signal | caught / dry / - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled |  |
| escaped-requirement |  |
| scope-drift |  |
| divergent-implementation |  |
| deferred-outcome (materialized / total) |  |

| Failure class | Count |
| --- | --- |
| trigger-too-narrow |  |
| enumeration-miss |  |
| scoring-starved |  |
| answer-unpressured |  |
| synthesis-loss (interview caught it; handoff drafting narrowed/dropped it) |  |

Rates - recomputed from the Divergence Table by `postmortem_lint.py`; state both, plus the weighted pair when any escape exists:

- interview-discovery: `fulfilled / (fulfilled + non-synthesis-loss escapes + divergent-implementation)` = N%
- handoff-fidelity: `fulfilled / (fulfilled + all escapes + divergent-implementation)` = N%
- weighted (escape/divergent rows enter the denominator at their impact weight): N% / N%

## 2. Lessons File Skeleton

Create as `docs/ultimateinterview-lessons.md` in the repo root (repo-specific signals) or `~/.agents/skills/ultimateinterview/lessons.md` (repo-agnostic signals, compounds across repos) when missing. Append rows; dedupe against both files first.

# Ultimateinterview Lessons

Signal-to-lens routing rules learned from spec postmortems. The `ultimateinterview` skill reads this file during Orientation: when a signal below appears in a new request or the touched code, treat the named lens as triggered. Keep signals observable at interview time, never hindsight. `Fired/Caught` is fire-tracking: postmortems increment Fired when the signal appeared, Caught when the triggered lens actually produced a ledger entry; Fired ≥ 3 with Caught 0 retires the row.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  | 0/0 |

## Retired

Rows moved here after 3 dry fires (signal appeared, lens caught nothing). Kept for the record; Orientation skips them.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
|  |  |  |  |
