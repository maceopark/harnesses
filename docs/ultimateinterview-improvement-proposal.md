# Ultrainterview Improvement Proposal

## Summary

`ultimateinterview` should not become a workflow that runs every requirements method with equal weight on every task. A better design is a two-pass requirements pipeline:

1. Structure the user's intent into a draft spec.
2. Audit that draft as if it were about to become an implementation seed.

This matches the workflow that has produced good results in practice:

```text
deep-interview -> ouroboros interview -> seed generation
```

The improvement is to encode that pipeline directly into `ultimateinterview`, while treating requirement-gap methods as conditional lenses rather than mandatory ceremony.

## Why The Current Combination Works

`deep-interview` is strong at intent structuring. It clarifies:

- why the user wants the change
- desired outcome
- scope
- non-goals
- decision boundaries
- success criteria

This produces a better initial context than a vague user request.

`ouroboros interview` is strong at readiness auditing. It does not treat a plausible draft as ready by default. It adds:

- code facts vs human decisions routing
- ambiguity ledger
- lateral or contrarian review
- breadth checks
- closure audit
- restate gate
- explicit approval before seed generation

The two tools work well together because their failure modes are complementary. `deep-interview` can produce a coherent but overconfident draft. `ouroboros` then challenges that draft before it becomes a seed.

## Proposed Ultrainterview Shape

`ultimateinterview` should become:

```text
Pass 1: Draft Spec Structuring
Pass 2: Seed-Readiness Audit
Pass 3: Restated Approval + Handoff
```

### Pass 1: Draft Spec Structuring

Goal: turn vague intent into a draft spec, not a final answer.

Always capture:

- intent
- desired outcome
- in scope
- out of scope / non-goals
- decision boundaries
- success criteria
- known code facts
- user decisions
- assumptions
- unresolved gaps

Every item should be labeled:

- `confirmed`
- `assumed`
- `unresolved`
- `from-code`
- `from-docs`
- `from-user`
- `from-research`
- `from-scenario`

### Pass 2: Seed-Readiness Audit

Goal: challenge the draft before implementation.

Audit questions:

- What did the draft treat as fact that is actually an assumption?
- Which unresolved gap would change implementation?
- Which code facts can be inspected instead of asked?
- Which user decision is still missing?
- Which scope boundary is weak?
- Which acceptance criterion is not observable?
- Would another engineer implement the same thing from this spec?

The audit should maintain an ambiguity ledger and ask one highest-impact question at a time.

### Pass 3: Restated Approval + Handoff

Before declaring the spec implementation-ready, restate:

- final goal
- key non-goals
- important assumptions
- unresolved deferred risks
- implementation decision boundaries
- verification expectations

Then ask for explicit approval before generating the final spec or seed-like handoff.

## Conditional Lenses

The current `ultimateinterview` includes many useful methods, but they should not all be mandatory for every task. Use them as conditional lenses.

Always apply:

- intent / outcome / scope / non-goals / decision boundaries
- code facts vs human decisions routing
- assumptions / unresolved gaps
- acceptance criteria
- closure audit
- restated approval

Apply conditionally:

| Lens | Use when |
| --- | --- |
| State model | The feature has lifecycle, status, permissions, state transitions, retries, or recovery |
| Entity / aggregate model | The change creates or mutates domain objects with identity, ownership, or invariants |
| EventStorming / Domain Storytelling | Multiple actors, async events, handoffs, delayed work, or external systems are involved |
| Viewpoint matrix | Admin, support, operator, security, finance, compliance, or external API viewpoints could disagree |
| Misuse / abuse cases | The flow touches auth, privacy, money, destructive actions, public input, or fraud risk |
| Quality attribute scenarios | Words like fast, reliable, safe, stable, scalable, secure, compatible, observable, or simple would change implementation |
| EARS / Given-When-Then | Final requirements or acceptance criteria need to become testable |

## Neuro-Symbolic / World-Model Integration

The useful part of neuro-symbolic world-model thinking is not the label. The useful part is making the system model explicit:

- entities
- states
- state transitions
- constraints
- invariants
- allowed actions
- impossible actions
- observations / evidence

For software requirements, this should become a conditional modeling pass:

```text
If a request changes domain state, lifecycle, ownership, permission, or recovery behavior,
build a minimal world model before finalizing the spec.
```

Minimal world model:

| Element | Question |
| --- | --- |
| Entity | What domain object exists, and how is identity determined? |
| State | What states can it be in? |
| Transition | What events or actions move it between states? |
| Actor | Who or what may trigger each transition? |
| Constraint | What must always be true? |
| Invalid transition | What must never happen? |
| Evidence | How do we observe or verify the state? |
| Recovery | What happens after failure or partial completion? |

This is valuable for many brownfield tasks, but it should not be forced onto simple copy changes, styling tweaks, or reversible local edits.

## Recommended Skill Change

Replace the current "sweep all channels below" framing with a risk-routed version:

```text
Run the always-on pass first. Then select conditional lenses based on implementation risk.
Do not run a lens only for completeness; run it when skipping it could hide a requirement
that changes behavior, data, security, ownership, rollout, or verification.
Record skipped lenses with a one-line reason.
```

Add a new section:

```text
## Two-Pass Flow

Ultrainterview first produces a draft spec, then audits that draft as if it were about
to become an implementation seed. The draft is not ready until the audit, closure gate,
and restated approval pass.
```

Add a new conditional section:

```text
## Conditional Modeling Lens

Use this when the request changes entities, states, state transitions, ownership,
permissions, invariants, or recovery behavior.
```

## Expected Benefit

This keeps the strongest part of the previous `ultimateinterview` design: broad requirements-gap discovery.

It also fixes the main risk: overloading every task with every methodology.

The revised skill would be closer to the proven workflow:

```text
deep-interview style structuring
-> ouroboros style audit
-> conditional modeling lenses
-> restated approval
-> implementation-ready spec
```

## Bottom Line

The right improvement is not to add more methods. The right improvement is to improve routing and gates.

`ultimateinterview` should ask:

```text
What kind of implementation risk does this request create?
Which lens would expose missing requirements for that risk?
What must be settled before this can safely become a seed/spec?
```

That makes it more practical, less ceremonial, and closer to the workflow that has already worked well.
