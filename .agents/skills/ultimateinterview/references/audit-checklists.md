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
- `domain/state` (boundary-qualified scenarios): when a requirement crosses multiple surfaces, actors, channels, time steps, systems, queues, approvals, or handoffs, every meaningful happy/negative scenario is classified by traversal depth: intended boundary reached, first valid stop/fail boundary, whether later boundaries should run, and terminal evidence. A scenario meant to stop early is not end-to-end coverage; a scenario meant to pass early boundaries and fail later must be verified at that later boundary
- `domain/state` (transitions): every meaningful state transition has an owner, trigger, guard, effect, and illegal-transition rule
- `domain/state` (invariants): every invariant or consistency boundary is stated as a rule with evidence or an owner
- `quality` (integration): every external dependency has timeout, retry, fallback, and failure visibility rules
- `domain/state` + `misuse` (data/schema): every relevant data object has ownership, retention, deletion, durability (crash/interrupt mid-write, plus what residue a failed write may leave behind), privacy, and audit rules
- `domain/state` (store trust): **for a durable or hand-editable tool-owned store** (skip for ephemeral/in-memory state), pin three decisions - whether values loaded from the store are revalidated or trusted (input-time-only validation lets a hand-edited store break an output invariant); the store-access error surface beyond corrupt content (missing parent directory, permission-denied/unreadable, undecodable bytes, and the path/override seam's own edge values), each with a defined exit class; and the unknown/extra-field policy (reject vs ignore-and-preserve - strict exact-key rejection makes every future schema addition a breaking change). Conditional by design: these three came from `1/1` lessons rows (`lessons.md`), still staging - Orientation triggers them by signal, and this gate only verifies them where store durability makes them load-bearing, not on every store
- `domain/state` (operation surface): every user-facing operation has a defined observable outcome for every legal data/store state (absent, valid, invalid), and the unknown/illegal-operation branch has a defined outcome too - no undefined branch
- `quality`: every vague quality word has a measurable quality attribute scenario
- `misuse` (security/privacy): every security-sensitive flow has misuse or abuse cases
- `misuse` (input surface): every operation accepting free-text or user-supplied values has explicit degenerate-input outcomes - empty/whitespace-only, oversized, control/newline characters - at input time and on load when persisted
- `controlled-language` (predicates): every acceptance criterion that names a validity/reject category (invalid, malformed, corrupt, unsafe) states the predicate that decides membership, or explicitly delegates that predicate as a decision-boundary row - a bare category makes the implementer invent the data rule (an `invalid next_id` reject case with no rule forced the app-5 implementer to define next_id > max existing id on its own). Extends to TYPE predicates on persisted/loaded data (experimental, from the three-arm benchmark; not yet re-measured): a field named by type (integer, boolean, count) pins its coercion boundary - whether a JSON boolean (which satisfies a naive `isinstance(int)` check), a numeric string, a float, or null/missing is accepted (claudeplan wrote `next_id: true` straight into the store); a one-sided threshold on a store/schema version (`> 1` handled, `< 1`/`== 0` undefined) pins the floor too. `scripts/predicate_lint.py <session-dir>` surfaces these three shapes deterministically (advisory - it flags a missing predicate, it cannot prove one correct)
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
