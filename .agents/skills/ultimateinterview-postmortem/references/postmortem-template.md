# Ultimateinterview Postmortem

postmortem_schema: 2
contract_digest: `<sha256>`
evaluator: `<independent evaluator identity>`
evaluated_at: `<ISO-8601>`

## Implementation Evidence

| Source | Scope | Digest / revision | Notes |
| --- | --- | --- | --- |
| Build Contract | `.ultimateinterview/<session>/build-contract.json` | `<contract digest>` | sole normative source |
| Repository evidence | `<diff/range/working tree>` | `<revision or bundle hash>` | scoped by contract |
| Verification | `<commands/scenarios>` | `<observed result>` | direct evidence |
| Implementation return | `implementation-return.json` or absent | `<digest binding>` | self-report only |
| Decision log | `decision.jsonl` or absent | `<row count>` | evidence, never authority |

## Divergence Table

One row per Build Contract requirement and one row per unmatched substantive implementation behavior.

| ID | Behavior | Class | Contract authority / requirement | Implementation evidence | Verification evidence | Owner decision needed? |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 |  | fulfilled / scope-drift / divergent-implementation / deferred-outcome / unverifiable | AUTH / REQ / ACC / VER |  |  | yes/no |
| ESC-001 |  | escaped-requirement | absent or insufficient contract clause |  |  | yes/no |

## Escaped Requirements

One row per `ESC-NNN` from the Divergence Table.

| ESC-ID | Behavior | Failure mode | Requirement structure | Owning frame | Intent attribution | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| ESC-001 |  | trigger-too-narrow / enumeration-miss / answer-unpressured / synthesis-loss / ontology-miss | item / boundary / interaction / system / novel:<slug> |  | owned-signal:<decision row> / run-blind |  |

## Wonder Generalization

Exactly one row per escaped requirement.

| ESC-ID | Reusable unknown class | Interview-time precursor | Lens | Lesson candidate | Disposition |
| --- | --- | --- | --- | --- | --- |
| ESC-001 |  |  |  |  | routed / deduped / not-routing/synthesis-loss / not-routing/ontology-miss |

## Deferred Outcomes

| Requirement | Deferred boundary | Materialized outcome | Evidence |
| --- | --- | --- | --- |
|  |  |  |  |

## Verification Execution

One row per Build Contract verification.

| VER-ID | Procedure | Direct execution | Result | Evidence | Return agreement |
| --- | --- | --- | --- | --- | --- |
| VER-001 |  | run / not-run / blocked | passed / failed / blocked / not-run |  | agrees / contradicts / return absent |

## Reward-Hacking Review

One row per Build Contract requirement.

| REQ-ID | Production-source support | Mock substitution | Tautological assertion | Hardcoded expectation | Disposition | Evidence | Divergence class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | yes/no | yes/no | yes/no | yes/no | clear / concern |  |  |

## Execution Process-Gap Candidates

| Item | Evidence | Product authority impact | Required action |
| --- | --- | --- | --- |
|  |  | none / owner decision required |  |

## Scope Drift / Divergent Implementations

| Item | Contract behavior | Implemented behavior | Evidence | Owner must re-decide? |
| --- | --- | --- | --- | --- |
|  |  |  |  | yes/no |

## Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught with owned Discovery Record marker? |
| --- | --- | --- | --- | --- |
|  |  |  | yes/no | yes/no |

## Lessons Appended Or Updated

| Store | Signal | Action | Evidence |
| --- | --- | --- | --- |
|  |  | appended / strengthened / deduped / none |  |

## Calibration Summary

| Metric | Count / rate |
| --- | --- |
| fulfilled | 0 |
| escaped-requirement | 0 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |
| unverifiable | 0 |
| discovery rate | N/A |
| contract fidelity | N/A |

## Missing Evidence

- `<explicitly unavailable evidence; never infer>`

## Resolution Addendum

Owner responses belong here as postmortem evidence only. They do not modify the sealed Build Contract or authorize code changes without a newly compiled contract.
