# Postmortem: demo

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| working tree | demo | a..b |

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | h | i | |
| REQ-002 | fulfilled | h | i | |
| REQ-003 | fulfilled (after review fix) | h | i | |
| temp cleanup | escaped-requirement | absent | todo.py:294 | |
| dropped case | escaped-requirement | ledger g9 | todo.py:120 | |

## Escaped Requirements

| REQ-ID | Behavior found in code | Owning lens | Failure class | Weight | Evidence |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | temp cleanup | misuse | enumeration-miss | 1 | diff hunk |
| REQ-002 | dropped case | core-path | synthesis-loss | 2 | ledger vs Part 1 |

## Wonder Generalization

| Escape REQ-ID | Unknown class | Interview-time observable signal | Lens | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | cleanup boundary | request touches temporary files | misuse | not-routing/synthesis-loss | lessons.md | existing signal |
| REQ-002 | handoff transport | settled ledger behavior omitted from Part 1 | core-path | not-routing/synthesis-loss | n/a | not an unknown: handoff transport loss |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

| Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect |
| --- | --- | --- | --- | --- | --- | --- |

## Reward-Hacking Review

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | no | no | no | cleared | Production command path inspected. |
| REQ-002 | fulfilled | yes | no | no | no | cleared | Production list path inspected. |
| REQ-003 | fulfilled | yes | no | no | no | cleared | Production completion path inspected. |

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

### Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md | 1 | free-text input | fired | caught |
| lessons.md | 2 | temporal word | no-signal | - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 3 |
| escaped-requirement | 2 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

Rates: interview-discovery 75.0% (synthesis-loss excluded), handoff-fidelity 60.0%.
Weighted (escape weights in denominator): interview-discovery 75.0%, handoff-fidelity 50.0%.
