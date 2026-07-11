# Part 1 — Build Contract

## Goal

Preserve an executable local validation surface. (source: R1)

## Target Surface

| File / module | Expected change |
| --- | --- |
| local validation command | preserve executable behavior |

## Behavior Contract

| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | R1 |

## Change Impact & Preservation

| Source | Current evidence | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | captured executable command | command remains runnable | no behavior change | local command | REQ-001 | process exit status |

## Quality Bars

No measurable quality bar applies - this fixture validates gate wiring only.

## Decision Boundaries

No implementation choice may change REQ-001. Standing instruction: append every decision the spec did not force to `.ultimateinterview/ready-minimal/decisions.jsonl` as you make it (the execution substrate does not record it automatically).

## Out Of Scope / Non-Goals

No product behavior is implemented by this fixture.

## Implementation Constraints

Keep the existing runtime.
Decision core: fixed command invocation maps to a process result.
Effects boundary: process execution only; no persistent or remote effect.

## Rollout & Recovery

| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |
| --- | --- | --- | --- | --- | --- |
| fixture execution | no backfill | REQ-001 fails | restore the prior fixture | exit status for one regression run | test owner |

## Guardrail Compile

No stop-time or pre-action guardrail applies - the fixture has no destructive effects.

## Verification Commands

| Check | Kind | Command / action | Pass condition |
| --- | --- | --- | --- |
| REQ-001 unit | test | `uv --version` | exits 0 |
| REQ-001 surface | real-surface | `uv --version` | exits 0 on the command surface |

## Deferred Risks

None.

## Fresh-Implementer Test

| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? | Unresolved after disposition |
| --- | --- | --- | --- | --- |
| fixture-review | none | none | no fold-back required | none |

# Part 2 — Audit Trail

This is the positive-control fixture for the composite implementation gate.
