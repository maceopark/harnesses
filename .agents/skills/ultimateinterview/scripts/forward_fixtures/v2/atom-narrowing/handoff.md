# Part 1 - Build Contract

## Goal

Preserve an executable local validation surface. (source: REQ-001)

## Target Surface

| File / module | Expected change |
| --- | --- |
| local validation command | preserve executable behavior |

## Behavior Contract

| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source | Assurance class | Atom IDs |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | high | ATOM-001 |

Behavior atom catalog:

| Source | Assurance class | Atom ID | Condition | Polarity | Observable response | Boundary context | Temporal context | Coercion context |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | high | ATOM-001 | The local validation command is invoked. | must-not | The command exits successfully. | Exit status zero is the success boundary. |  |  |

## Change Impact & Preservation

| Source | Current evidence / behavior | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | captured executable command | command remains runnable | no behavior change | local command | REQ-001 | process exit status |

## Quality Bars

No measurable quality bar applies - this fixture validates gate wiring only.

## Decision Boundaries

Append every unforced decision to `.ultimateinterview/v2-ready/decisions.jsonl` as it is made.
Decision log: `.ultimateinterview/v2-ready/decisions.jsonl`
Probe decision: L0 - static contract and fresh review are sufficient.

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| command presentation | yes | REQ-001 behavior must remain unchanged |

## Out Of Scope / Non-Goals

- No product behavior is implemented by this fixture - negative: only the validation command is invoked.

## Implementation Constraints

- Interfaces: local command
- Compatibility: preserve the current invocation
- Migration: none
- Decision core: fixed command invocation maps to a process result
- Effects boundary: process execution only; no persistent or remote effect

## Rollout & Recovery

| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |
| --- | --- | --- | --- | --- | --- |
| fixture execution | no backfill | REQ-001 fails | restore the prior fixture | exit status for one regression run | test owner |

## Guardrail Compile

No stop-time or pre-action guardrail applies - the fixture has no destructive effects.

## Verification Commands

| ID | Covers | Check | Kind | Command / action | Pass condition | Run policy |
| --- | --- | --- | --- | --- | --- | --- |
| VER-001 | REQ-001 | unit command | test | python3 -m pytest -q | exit code = 0 and output reports passed | safe-auto |
| VER-002 | REQ-001 | installed surface | real-surface | uv --version | exit code = 0 and output contains uv | manual |

## Consumer Verification

| Grant kind | Receipt kind | Required ID | Target | Environment / scope | Outcome | Expected exit | Run policy | Auto execute |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| implementation-readiness | verification | VER-001 | REQ-001 | local | success | 0 | safe-auto | yes |
| implementation-readiness | verification | VER-002 | REQ-001 | local | success | 0 | manual | no |
| probe | probe | PROBE-L0-fixture | REQ-001 | l0:local | success | 0 | manual | no |

## Deferred Risks

No deferred risks - no accepted ambiguity remains.

## Fresh-Implementer Test

| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? | Unresolved after disposition |
| --- | --- | --- | --- | --- |
| fixture-review | none | none | no fold-back required | none |

# Part 2 - Audit Trail

This is the v1 positive-control fixture for structured evidence, open-world freshness, typed probe state, and the compiled sidecar gate.
