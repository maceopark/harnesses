# Ultimateinterview Postmortem

postmortem_schema: 3
contract_digest: SHA256_HEX
evaluator: EVALUATOR_IDENTITY
evaluated_at: ISO_8601_TIMESTAMP

## Conclusion

**Verdict:** `<plain-language outcome, at most 240 characters>`

**Counts:** TOTAL contract requirements — FULFILLED fulfilled, ESCAPED escaped, SCOPE_DRIFT scope-drift, DIVERGENT divergent, DEFERRED deferred, UNVERIFIABLE unverifiable.

**Improvement:** `<optional single bounded rule; omit when none>`

## Findings

Exactly one row per Build Contract requirement and one row per unmatched substantive implementation behavior. Use each `ESC-NNN` once. Every non-fulfilled row requires one root cause and an owner action. Keep every cell at 240 characters or less.

| ID | Class | Behavior | Evidence | Root cause | Owner action |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled / scope-drift / divergent-implementation / deferred-outcome / unverifiable | `<behavior>` | `<direct implementation and verification evidence>` | none / discovery-miss / decision-miss / handoff-loss / contract-defect / implementation-drift / verification-gap | `<action or none>` |
| ESC-001 | escaped-requirement | `<unmatched substantive behavior>` | `<direct evidence>` | `<root cause>` | `<action>` |

## Verification

Exactly one row per Build Contract verification. Keep every cell at 240 characters or less.

| VER-ID | Result | Evidence |
| --- | --- | --- |
| VER-001 | passed / failed / blocked / not-run | `<direct evidence>` |
