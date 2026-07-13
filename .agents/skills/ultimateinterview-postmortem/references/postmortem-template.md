# Ultimateinterview Postmortem

postmortem_schema: 2
contract_digest: `<sha256>`
evaluator: `<independent evaluator identity>`
evaluated_at: `<ISO-8601>`

## Conclusion

**Verdict:** `<plain-language outcome>`

**Counts:** `<total>` contract requirements — `<fulfilled>` fulfilled, `<escaped>` escaped, `<scope-drift>` scope-drift, `<divergent>` divergent, `<deferred>` deferred, `<unverifiable>` unverifiable.

**Root causes:**

1. `<cause supported by finding IDs>`
2. `<cause, when distinct>`

### Ultimateinterview improvement proposals

| Proposal | Prevents | Rule to add or strengthen | Cross-domain reason | Compatible existing rule |
| --- | --- | --- | --- | --- |
| `<short proposal or "No skill change recommended">` | `<finding IDs>` | `<one bounded rule/check>` | `<reusable class of work>` | `<current SKILL.md rule or noncompliance explanation>` |

## Implementation Evidence

| Source | Scope | Digest / revision | Notes |
| --- | --- | --- | --- |
| Build Contract | `.ultimateinterview/<session>/build-contract.json` | `<contract digest>` | sole normative source |
| Repository evidence | `<diff/range/working tree>` | `<revision or bundle hash>` | scoped by contract |
| Verification | `<commands/scenarios>` | `<observed result>` | direct evidence |
| Implementation return | `implementation-return.json` or absent | `<digest binding>` | self-report only |
| Decision log | `decision.jsonl` or absent | `<row count>` | evidence, never authority |

## Divergence Table

Exactly one row per Build Contract requirement and one row per unmatched substantive implementation behavior. Each row contributes to exactly one Conclusion class.

| ID | Behavior | Class | Contract mapping | Implementation evidence | Verification evidence | Owner decision needed? |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 |  | fulfilled / scope-drift / divergent-implementation / deferred-outcome / unverifiable | AUTH / REQ / ACC / VER |  |  | yes/no |
| ESC-001 |  | escaped-requirement | absent or insufficient clause |  |  | yes/no |

## Finding Details

Include only escaped requirements, scope drift, divergent implementations, deferred outcomes, and unverifiable rows.

| ID | Behavior | Class / failure mode | Structure / owning frame | Intent attribution | Evidence | Owner action |
| --- | --- | --- | --- | --- | --- | --- |
| ESC-001 |  | escaped-requirement / trigger-too-narrow / enumeration-miss / answer-unpressured / synthesis-loss / ontology-miss | item / boundary / interaction / system / novel:`<slug>`; frame | owned-signal:`<decision row>` / run-blind |  |  |
| REQ-001 |  | scope-drift / divergent-implementation / deferred-outcome / unverifiable | n/a | n/a |  |  |

## Verification Execution

One row per Build Contract verification.

| VER-ID | Procedure | Direct execution | Result | Evidence | Return agreement |
| --- | --- | --- | --- | --- | --- |
| VER-001 |  | run / not-run / blocked | passed / failed / blocked / not-run |  | agrees / contradicts / return absent |

Record substantive mock substitution, tautological assertions, or hardcoded expectations in the affected row's evidence; omit clear/no-signal boilerplate.

## Lessons

Only rows fired, changed, retired, or considered and rejected during this audit.

| Store | Signal | Action | Evidence |
| --- | --- | --- | --- |
|  |  | fired / appended / strengthened / retired / rejected / none |  |

## Process Gaps and Missing Evidence

| Item | Evidence | Authority impact | Required action |
| --- | --- | --- | --- |
|  |  | none / owner decision required |  |

## Resolution Addendum

Owner responses belong here as postmortem evidence only. They do not modify the sealed Build Contract or authorize code or skill changes without the applicable separate workflow.