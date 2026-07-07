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

| Behavior found in code | Owning lens | Failure class | Evidence (diff hunk + ledger/transcript line or absence) |
| --- | --- | --- | --- |
|  | viewpoint / domain/state / goal/obstacle / misuse / quality / controlled-language / core-path | trigger-too-narrow / enumeration-miss / scoring-starved / answer-unpressured / synthesis-loss |  |

Owning-lens values are ultimateinterview's canonical trigger names. Use `core-path` when the miss belongs to always-on machinery (contextual observation, the framing challenge): those are `enumeration-miss` by definition and become routing lessons only if a repo-observable signal could have routed a heavier lens instead. `known-deferred` items are not escapes - record them under Deferred Outcomes.

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
|  |  | yes/no |  |

## Scope Drift / Divergent Implementations

| Item | Class | What the handoff said | What was built | User must re-decide? |
| --- | --- | --- | --- | --- |
|  | scope-drift / divergent-implementation |  |  | yes/no |

## Lessons Appended Or Updated

| Signal | Lens to trigger | Failure class | Evidence | Date |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

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

## 2. Lessons File Skeleton

Create as `docs/ultimateinterview-lessons.md` in the repo root (repo-specific signals) or `~/.agents/skills/ultimateinterview/lessons.md` (repo-agnostic signals, compounds across repos) when missing. Append rows; dedupe against both files first.

# Ultrainterview Lessons

Signal-to-lens routing rules learned from spec postmortems. The `ultimateinterview` skill reads this file during Orientation: when a signal below appears in a new request or the touched code, treat the named lens as triggered. Keep signals observable at interview time, never hindsight. `Fired/Caught` is fire-tracking: postmortems increment Fired when the signal appeared, Caught when the triggered lens actually produced a ledger entry; Fired ≥ 3 with Caught 0 retires the row.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  | 0/0 |

## Retired

Rows moved here after 3 dry fires (signal appeared, lens caught nothing). Kept for the record; Orientation skips them.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
|  |  |  |  |
