# Lens Methods

Full methods for the Diverge techniques. Read the section for a lens when it is triggered (or looks plausibly triggerable); the one-liners in `references/interview-loop.md` §Diverge are routing, not the method.

## 1. Contextual Observation (core path)

Use observed behavior, tests, logs, support tickets, screenshots, CLI output, or current workflows to identify tacit requirements and exceptions.

Ask:

- What does the current workflow already force users to do?
- Which workaround or support issue is the real requirement hiding behind the request?
- What behavior is relied on but not documented?
- What timing, ordering, volume, or environment constraint appears in practice?

## 2. Viewpoint Matrix (`viewpoint` lens)

Build a Viewpoint matrix for affected viewpoints: end user, admin/operator, support, security/privacy, compliance/legal, finance/billing, engineering/maintainer, and external API/system.

For each viewpoint, capture:

- goal
- constraint
- data owned
- failure fear
- acceptance evidence
- open question

Gaps usually appear as an unrepresented viewpoint, missing owner, conflicting acceptance criterion, or data lifecycle without retention/deletion/audit rules.

Mark each row's provenance: `simulated` when you role-played the viewpoint, `confirmed` when the actual stakeholder or their documented policy validated it. Simulated rows are hypotheses, not evidence - they enter the ledger as `assumption` and cannot triangulate a critical requirement on their own.

## 3. EventStorming / Domain Storytelling (core path)

Reconstruct the domain flow as events or actor-action-object stories.

Look for:

- missing event before or after the requested change
- actor handoff without required information
- state transition without owner or trigger
- duplicate, delayed, or out-of-order event
- compensating action when the next step fails
- vocabulary mismatch between user language and repo language

## 4. Domain / State Modeling (`domain/state` lens)

Use this DDD, state-model, and neuro-symbolic world-model lens only when `domain/state` is triggered. The goal is a compact model of the software world being changed, not ceremony.

Capture:

- ubiquitous language: user term, repo term, bounded context, and meaning drift
- concept type: entity, value object, aggregate/root, domain event, external actor, or plain DTO
- lifecycle: state, event, transition, trigger, guard, action/effect, terminal state, error state, and recovery state
- invariant or constraint: what must never be temporarily wrong
- provenance: one of the six evidence channels

Ask:

- Does this term mean the same thing in every screen, table, service, and team?
- If two instances have the same attributes, are they the same thing or just equal values?
- What must be changed or saved as one consistency boundary?
- What states are legal, and which transitions must be rejected?
- What happens if this event arrives while the entity is pending, failed, retried, or already completed?
- Which rule is an invariant, which is validation, and which is a preference?
- Who owns mutation, audit, retention, deletion, and recovery?

Skip this lens for straightforward CRUD, reporting, simple form validation, pure transformations, stable vocabulary, or low-risk changes with no meaningful lifecycle.

Escalate to a decision table, statechart, TLA+, Alloy, or another formalism only when many branches, reachability, ordering, safety, concurrency, or constraint interaction would change implementation risk.

## 5. Goal + Obstacle Analysis (`goal/obstacle` lens)

Turn the desired outcome into goals, assumptions, obstacle lists, derived requirements, and residual risks.

Use this shape:

```text
Goal:
Assumptions:
Obstacles:
Derived requirements:
Residual risk:
```

For each goal, ask what can prevent it through user behavior, dependency failure, stale state, concurrency, data quality, permissions, deployment constraints, or policy.

## 6. Misuse / Abuse Cases (`misuse` lens)

Add hostile, careless, overloaded, and unauthorized actors.

For each core flow, capture:

```text
Misuse actor:
Misuse goal:
Damage:
Prevent:
Detect:
Rate-limit/throttle:
Log/audit:
Reverse/recover:
Escalate:
```

Do this even for non-security work when abuse, privacy, fraud, destructive actions, or irreversible data changes are plausible.

## 7. Quality Attribute Scenarios (`quality` lens)

Convert vague quality claims into quality attribute scenarios.

```text
Quality attribute:
Source:
Stimulus:
Environment:
Artifact:
Response:
Response measure:
```

Cover performance, availability, security, modifiability, observability, recovery, interoperability, data retention, and operability when they could affect implementation.

## 8. Controlled Language (`controlled-language` lens)

Rewrite candidate requirements in EARS or Given/When/Then. If the trigger, actor, condition, response, exception, or measurement cannot be written, the requirement is still ambiguous.

EARS patterns:

```text
The <system> shall <response>.
When <trigger>, the <system> shall <response>.
While <state>, the <system> shall <response>.
If <condition>, then the <system> shall <response>.
Where <feature is included>, the <system> shall <response>.
```

Given/When/Then pattern:

```text
Given <precondition>
When <trigger/action>
Then <observable outcome>
And <measurable or persisted evidence>
```
