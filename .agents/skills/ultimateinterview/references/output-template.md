# Ultimateinterview Output Template

Use this template when the user asks for a persistent or copy-ready spec. Copy the sections, then fill them with the interview ledger. The order is a contract: Part 1 (Build Contract) is what an implementation agent reads and builds from; Part 2 (Audit Trail) is why Part 1 is true. Never bury a build decision in Part 2.

# Spec: <feature/change name>

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. Append every decision this spec did not force to `.ultimateinterview/<slug>/decisions.jsonl` as you make it. Name each acceptance test after the requirement it verifies (`test_req001_*`, or cite `REQ-001` in the test name or docstring) so requirement→test coverage is mechanical for the postmortem. When the implementation lands, STOP - the requester runs the `ultimateinterview-postmortem` skill in a fresh context to diff this spec against the actual change. Do not audit your own implementation; if you write a self-review anyway, save it as `postmortem.self.md`, never `postmortem.md`.

# Part 1 — Build Contract

Self-sufficiency rule: an implementer with no access to the interview reads only this part. It must pass the fresh-implementer test before handoff (record `build_contract_tested` in `protocol.json`).
Traceability rule: every settled weight-`2`-or-higher, non-deferred ledger entry MUST be cited by id somewhere in Part 1 — the Behavior Contract `Source` cell, or an inline `(source: <id>)` tag in Goal, Quality Bars, Decision Boundaries, Out Of Scope, or Implementation Constraints — or moved to Deferred Risks with owner/date. A cited REQ must reproduce the entry's FULL enumerated behavior (every error class / boundary / state), never a narrowed subset. `scripts/handoff_coverage.py <session-dir>` enforces the id-citation floor (fail-closed); the fresh-implementer test catches behavior narrowing.

## Goal

<One sentence.>

## Target Surface

| File / module | Expected change |
| --- | --- |
|  |  |

## Behavior Contract

Settled behavior-changing requirements with their acceptance criteria. `Source` carries the ledger entry id(s) that justify the row — it keeps dispute-resolution and postmortem attribution mechanical.

| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 |  | `When <trigger>, the <system> shall <response>.` | g15 |

```text
Given <precondition>
When <trigger/action>
Then <observable outcome>
And <measurable or persisted evidence>
```

## Quality Bars

Mandatory slot: at least one measurable bar, or exactly one line: `No measurable quality bar applies - <reason>.` Weight reuses the ledger impact-weight scale (`1`/`2`/`3`/`5`) and orders implementer tradeoffs: when bars conflict, satisfy the higher weight first.

| Attribute | Bar (a number an implementer can verify) | Weight | Verification |
| --- | --- | --- | --- |
|  |  |  |  |

## Decision Boundaries

Structural detail is delegable; a data-domain invariant is never - its row pins the observable outcome (and names its verification) while the mechanism stays the agent's.

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
|  | yes/no |  |

## Out Of Scope / Non-Goals

Each non-goal carries a checkable negative assertion where feasible — the observable proof it was NOT built (the forbidden flag/subcommand exits as unknown, the capability's import/dependency is absent, the endpoint is unserved). This lets the postmortem scan for scope creep instead of eyeballing it. (Experimental, adopted from a plan-mode benchmark's Must-NOT block.)

- <non-goal> — negative: <checkable proof it is absent, e.g. `todo --priority` exits 2; no `priority` field in the store schema>

## Implementation Constraints

- Interfaces:
- Compatibility:
- Migration:
- Rollout:

## Guardrail Compile

Split execution risks by what can be checked at stop time. A predicate must have a determinate pass/fail observable; natural-language "done" or "be careful" does not count. Fast/pre-action risks are surfaced as substrate-owned instead of simulated as stop-time checks.

Prompt-injection boundary: product-level prompt injection stays in the misuse/security requirements with trust boundaries and verifiable controls. Only agent/tool prompt-injection interception against the execution harness itself belongs in the fast/pre-action substrate row.

| Risk | Class | Predicate / residual / substrate owner | Evidence |
| --- | --- | --- | --- |
|  | Stop-time predicate | `<command/test/file-state/endpoint/countable threshold>` |  |
|  | Accepted residual | owner: `<name>`; decision date: `<date>`; mitigation: `<how it remains visible>` |  |
|  | Fast/pre-action | substrate: `<permission system/tool guard/human approval>` |  |

## Verification Commands

The exact tests/commands/observations that prove the change works. At least one check exercises the real artifact surface (installed command, running service, endpoint) - not test-suite-only. For command-style artifacts, the checks cover the operation × data-state matrix including the unknown/illegal-operation row (no undefined branch). Every command must be copy-paste executable on this host - `scripts/verification_lint.py` validates each command head against PATH; prose action rows are allowed but never replace the executable rows. Ask the implementer to name each acceptance test after the REQ it covers (`test_req001_*` or a `REQ-001` reference) so the postmortem maps requirements to tests mechanically instead of by hand.

For boundary-spanning work, include this matrix before the command table. Use domain words for the boundaries (screen, click, submit, API admission, queue, workflow branch, review handoff, email, report, terminal status, etc.). Omit only when the work has a single meaningful boundary.

| Scenario | Intended traversal depth | First valid stop/fail boundary | Later boundaries should run? | Terminal evidence |
| --- | --- | --- | --- | --- |
|  |  |  | yes/no |  |

| Check | Command / action | Pass condition |
| --- | --- | --- |
|  |  |  |

## Deferred Risks

Accepted ambiguity the implementer must not silently resolve.

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
|  |  |  |  |

## Fresh-Implementer Test

Records both questions: blocking asks, and acceptance criteria passable without the behavior (verification gaming) with how each was re-bound.

| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? |
| --- | --- | --- | --- |
|  |  |  |  |

# Part 2 — Audit Trail

Render-by-reference rule: sections that mirror session state files verbatim (Requirements Ledger full table, Q&A Record) are rendered as condensed key rows plus a pointer to the state file (`.ultimateinterview/<slug>/ledger.json`, `transcript.md`). Re-render them in full only when the user asks for a fully self-contained committed artifact (e.g. the `docs/` copy) — full re-renders duplicate on-disk state and cost handoff latency, and the fresh implementer reads Part 1 only anyway.

## Problem

<User-facing problem and root cause hypothesis.>

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause |  |
| Do-nothing option |  |
| Simpler alternative |  |
| Artifact class confirmed |  |

## Desired Outcome

<Observable end state.>

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-code |  |  |
| from-docs |  |  |
| from-user |  |  |
| from-research |  |  |
| from-scenario |  |  |

## Triggered Lenses

States mirror `protocol.json` verbatim (lowercase; the script rejects other spellings). A lens still `triggered` at handoff is a protocol blocker.

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | triggered/done/skipped |  |
| domain/state | triggered/done/skipped |  |
| goal/obstacle | triggered/done/skipped |  |
| misuse | triggered/done/skipped |  |
| quality | triggered/done/skipped |  |
| controlled-language | triggered/done/skipped |  |

## Requirements Ledger

Quote entry counts and dashboard numbers from helper output (`ambiguity_ledger.py` or `session_status.py`), never hand-count — the first real handoff wrote "24 entries" when the ledger had 26.

| ID | Requirement | Source | Evidence | Evidence channels | Ambiguity | Impact weight | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 |  |  |  | from-code, from-user | 0/1/2/3 | 1/2/3/5 | Draft/Triangulated/Contested/Blocked/Accepted/Deferred |

## Ambiguity Dashboard

Deterministic source of truth — prefer the single combined invocation `uv run <ultimateinterview-skill>/scripts/session_status.py <session-dir>` (one call emits both dashboards plus the combined ready line); per-script fallback:

```bash
uv run <ultimateinterview-skill>/scripts/ambiguity_ledger.py --format markdown <repo-root>/.ultimateinterview/<slug>/ledger.json
```

```text
residual = sum(impact_weight * ambiguity_score)  over active gaps

Handoff readiness is blocker-based: ready exactly when no active score 2 or 3 gap remains
and no active weight-5 entry sits at score 0 with fewer than two distinct evidence_channels
(assumption never counts) unless its status records explicit acceptance (Accepted)
backed by at least one non-assumption channel.
The percentage (100 * residual / sum(impact_weight * 3)) is the remaining-ambiguity share —
lower is better; it dilutes as settled entries accumulate. Informational only; never gate handoff on it.
Deferred gaps are excluded from the residual and listed under Deferred Risks.
```

| Residual | Blockers | Handoff ready? | Ambiguity % (informational) |
| --- | --- | --- | --- |
|  |  | yes/no |  |

| Top driver | Ambiguity | Impact weight | Reason | Next action |
| --- | --- | --- | --- | --- |
|  | 0/1/2/3 | 1/2/3/5 |  |  |

## Protocol Dashboard

Deterministic source of truth — prefer the single combined invocation `uv run <ultimateinterview-skill>/scripts/session_status.py <session-dir>` (one call emits both dashboards plus the combined ready line); per-script fallback:

```bash
uv run <ultimateinterview-skill>/scripts/protocol_state.py --format markdown <repo-root>/.ultimateinterview/<slug>/protocol.json
```

| Depth | Budget used | Protocol ready? | Outstanding blockers |
| --- | --- | --- | --- |
| minimal/focused/full |  | yes/no |  |

When `Handoff ready?` and `Protocol ready?` are both `yes` and the Gates in `references/handoff-sequence.md` pass (the gates include checks neither helper enforces: Contested entries resolved, testable acceptance criteria, deferred assumptions with owners), write this document to `.ultimateinterview/<slug>/handoff.md` and offer once to copy it to `docs/<slug>-handoff.md` as a durable committed artifact.

## Seed-Readiness Audit

Use when the readiness gate is triggered.

| Check | Finding | Action |
| --- | --- | --- |
| Fact vs assumption |  |  |
| Implementation-changing gap |  |  |
| Code fact to inspect |  |  |
| Missing user decision |  |  |
| Weak boundary |  |  |
| Unobservable acceptance criterion |  |  |
| Falsification checkpoint run since last ledger change |  |  |
| Fresh-context reviewer finding |  |  |

## Q&A Record

Condensed from `.ultimateinterview/<slug>/transcript.md`. Batched smart-default rounds and critical-path bundles appear as one row with per-item outcomes.

| # | Question / batch | Decision | Pressure test / checkpoint correction |
| --- | --- | --- | --- |
|  |  |  |  |

## Contested Log

| Entry | User claim | Repo evidence | Governing source | Resolution |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Domain Flow

### EventStorming

- `<Event>`

### Domain Storytelling

- `<actor> -> <action> -> <work object> -> <result>`

## Domain / State Model

Use only when the `domain/state` lens is triggered.

### Ubiquitous Language

| User term | Repo term | Bounded context | Meaning / mismatch |
| --- | --- | --- | --- |
|  |  |  |  |

### Domain Concepts

| Concept | Type | Owner | Invariants / constraints | Evidence |
| --- | --- | --- | --- | --- |
|  | Entity/Value object/Aggregate root/Domain event/External actor/DTO |  |  |  |

### State Model

| State | Event / trigger | Guard | Effect | Next state | Illegal transitions | Recovery |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Viewpoint Matrix

Provenance: `simulated` rows are hypotheses (`assumption`), not evidence; `confirmed` rows were validated by the stakeholder or their documented policy.

| Viewpoint | Provenance | Goals | Constraints | Data owned | Failure fears | Acceptance evidence | Open questions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| End user | simulated/confirmed |  |  |  |  |  |  |
| Admin/operator | simulated/confirmed |  |  |  |  |  |  |
| Support | simulated/confirmed |  |  |  |  |  |  |
| Security/privacy | simulated/confirmed |  |  |  |  |  |  |
| Compliance/legal | simulated/confirmed |  |  |  |  |  |  |
| Finance/billing | simulated/confirmed |  |  |  |  |  |  |
| Engineering/maintainer | simulated/confirmed |  |  |  |  |  |  |
| External API/system | simulated/confirmed |  |  |  |  |  |  |

## Goal + Obstacle Analysis

| Goal | Assumptions | Obstacles | Derived requirements | Residual risk |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Failure And Misuse Cases

| Misuse actor | Misuse goal | Damage | Prevent | Detect | Log/audit | Recover/escalate |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Quality Attribute Scenarios

| Attribute | Source | Stimulus | Environment | Artifact | Response | Response measure |
| --- | --- | --- | --- | --- | --- | --- | 
|  |  |  |  |  |  |  |

## Verification Plan Detail

Manual QA surface and observability evidence beyond the contract's verification commands.

| Evidence | Surface | Command/action | Pass condition |
| --- | --- | --- | --- |
| Manual QA |  |  |  |
| Logs/metrics/audit |  |  |  |

## Glossary Updates

Use when the repo keeps a glossary (`CONTEXT.md` or equivalent). Propose updates from this interview's ubiquitous-language findings so the next interview inherits them.

| Term | Current glossary meaning | Proposed update / addition | Evidence |
| --- | --- | --- | --- |
|  |  |  |  |

## Restated Approval Check

Use before seed-like handoff, or when the readiness gate is triggered.

- Final goal:
- Key non-goals:
- Important assumptions:
- Deferred risks:
- Implementation decision boundaries:
- Verification expectations:
- Approval status: Approved / Draft pending approval / Not required for this depth
