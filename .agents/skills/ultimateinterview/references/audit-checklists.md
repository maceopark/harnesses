# Audit Checklists

Read the relevant checklist at the moment it runs; `references/handoff-sequence.md` points here.

## Pass 2 — Seed-Readiness Audit (when the readiness gate is triggered)

- What did the draft treat as fact that is actually an assumption?
- Which unresolved gap would change implementation?
- Which code facts can be inspected instead of asked?
- Which user decision is still missing?
- Which scope boundary is weak?
- Which acceptance criterion is not observable?
- Would another engineer implement the same thing from this spec?
- Which requirement did the interview introduce rather than the user ask for (scope inflation)?
- Which data-domain invariant is left to implementer discretion instead of pinned as an observable outcome?

## Pass 3 — Restated Approval (seed-like handoff or triggered gate)

- final goal
- key non-goals
- important assumptions
- unresolved deferred risks
- implementation decision boundaries
- verification expectations

## Per-Lens Gate Checks (each named by its owning protocol lens; parenthetical = concern area)

- `goal/obstacle` (workflows): every important workflow has a normal path, exception path, and recovery path
- `domain/state` (transitions): every meaningful state transition has an owner, trigger, guard, effect, and illegal-transition rule
- `domain/state` (invariants): every invariant or consistency boundary is stated as a rule with evidence or an owner
- `quality` (integration): every external dependency has timeout, retry, fallback, and failure visibility rules
- `domain/state` + `misuse` (data/schema): every relevant data object has ownership, retention, deletion, durability (crash/interrupt mid-write), privacy, and audit rules
- `domain/state` (operation surface): every user-facing operation has a defined observable outcome for every legal data/store state (absent, valid, invalid), and the unknown/illegal-operation branch has a defined outcome too - no undefined branch
- `quality`: every vague quality word has a measurable quality attribute scenario
- `misuse` (security/privacy): every security-sensitive flow has misuse or abuse cases
- `viewpoint`: every affected stakeholder viewpoint has either a settled requirement or a recorded non-applicability note
- `domain/state` (formal-modeling escalation): every modelled property has a clear reason, expected payoff, and stop condition

## Fresh-Context Reviewer — what to ask it to find

- facts that are really assumptions
- missing implementation-changing decisions
- uninspected code facts
- weak non-goals or decision boundaries
- unobservable acceptance criteria
- triggered lenses that were skipped without a good reason
- places where another engineer could implement a materially different behavior
- requirements that serve the spec's completeness rather than the stated need (scope inflation)
- acceptance criteria passable without the behavior (test-editing or other verification gaming)
