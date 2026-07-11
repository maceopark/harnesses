# Postmortem

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| working tree | fixture | a..b |

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | handoff | fixture | |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Weight | Evidence |
| --- | --- | --- | --- | --- |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

| Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Exact capture check | test | exact | pass | capture-1 | echoed exact-ok |

## Reward-Hacking Review

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | no | no | no | cleared | fixture review |

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

### Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md | 1 | fixture signal | no-signal | - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 1 |
| escaped-requirement | 0 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

Rates: interview-discovery 100.0%, handoff-fidelity 100.0%.
