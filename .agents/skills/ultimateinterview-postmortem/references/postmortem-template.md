# Ultimateinterview Postmortem

postmortem_schema: 2
contract_digest: `<sha256>`
evaluator: `<independent evaluator identity>`
evaluated_at: `<ISO-8601>`

## Conclusion

**Verdict:** `<plain-language outcome>`

**Counts:** `<total>` contract requirements — `<fulfilled>` fulfilled, `<escaped>` escaped, `<scope-drift>` scope-drift, `<divergent>` divergent, `<deferred>` deferred, `<unverifiable>` unverifiable.

**Root causes:**

1. `<cause supported by finding IDs, or no divergence identified>`

### Ultimateinterview improvement proposals

| Proposal | Prevents | Rule to add or strengthen | Cross-domain reason | Compatible existing rule |
| --- | --- | --- | --- | --- |
| `<short proposal or No skill change recommended>` | `<finding IDs or implementation/evaluator noncompliance>` | `<one bounded rule/check>` | `<reusable class of work>` | `<current SKILL.md rule or noncompliance explanation>` |

Use at most three proposal rows. Remove this placeholder row when no proposal is warranted; zero rows is valid.

## Implementation Evidence

| Source | Scope | Digest / revision | Notes |
| --- | --- | --- | --- |
| Build Contract | `.ultimateinterview/<session>/build-contract.json` | `<contract digest>` | sole normative source |
| Repository evidence | `<explicit diff range or diff file>` | `<bundle repository diff hash>` | scoped by contract |
| Verification | `<commands/scenarios>` | `<observed result>` | direct evidence |
| Decision log | `decision.jsonl` or absent | `<row count or absent>` | evidence, never authority |

## Divergence Table

Exactly one row per Build Contract requirement and one row per unmatched substantive implementation behavior. Each row contributes to exactly one Conclusion class. Use each `ESC-NNN` identity exactly once; `ESC` rows must be `escaped-requirement`.

| ID | Behavior | Class | Contract mapping | Implementation evidence | Verification evidence | Owner decision needed? |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | `<behavior>` | fulfilled / scope-drift / divergent-implementation / deferred-outcome / unverifiable | `<AUTH / REQ / ACC / VER>` | `<direct evidence>` | `<direct evidence or absent>` | yes/no |
| ESC-001 | `<unmatched substantive behavior>` | escaped-requirement | absent or insufficient clause | `<direct evidence>` | `<direct evidence or absent>` | yes/no |

## Finding Details

Include exactly one row for each escaped requirement, scope drift, divergent implementation, deferred outcome, and unverifiable item. Do not include fulfilled requirements.

| ID | Behavior | Class / failure mode | Structure / owning frame | Intent attribution | Evidence | Owner action |
| --- | --- | --- | --- | --- | --- | --- |
| ESC-001 | `<behavior>` | escaped-requirement / discovery-miss / decision-miss / handoff-loss / contract-defect / implementation-drift / verification-gap | observed evidence / material decision / contract / acceptance-verification / implementation | owned-signal:`<decision row>` / run-blind | `<evidence>` | `<action>` |
| REQ-001 | `<behavior>` | scope-drift / handoff-loss, divergent-implementation / implementation-drift, deferred-outcome / decision-miss, unverifiable / verification-gap | `<lineage stage or n/a>` | n/a | `<evidence>` | `<action>` |

## Verification Execution

Exactly one row per Build Contract verification.

| VER-ID | Procedure | Direct execution | Result | Evidence |
| --- | --- | --- | --- | --- |
| VER-001 | `<contract procedure>` | run / not-run / blocked | passed / failed / blocked / not-run | `<direct evidence>` |

Record substantive mock substitution, tautological assertions, or hardcoded expectations in the affected row's evidence; omit clear/no-signal boilerplate.

## Lessons

Leave this table empty unless the user separately requested a durable lesson-store update. When used, pass the same stable `Store` label to `postmortem_report_check.py --lesson-store <Store> <pre-path|-> <post-path|->`. `Pre-state` and `Post-state` must be `absent` or the exact `sha256:<digest>` of those files. `fired`, `appended`, `strengthened`, and `retired` require a state delta; `rejected` and `none` require no delta.

| Store | Signal | Action | Pre-state | Post-state | Evidence |
| --- | --- | --- | --- | --- | --- |
| repo | `<observable signal>` | fired / appended / strengthened / retired / rejected / none | absent / `sha256:<digest>` | absent / `sha256:<digest>` | `<evidence>` |

## Process Gaps and Missing Evidence

| Item | Evidence | Authority impact | Required action |
| --- | --- | --- | --- |
| `<gap or missing artifact>` | `<evidence>` | none / owner decision required | `<action>` |

## Resolution Addendum

Owner responses belong here as postmortem evidence only. They do not modify the sealed Build Contract or authorize code or skill changes without the applicable separate workflow.
