---
name: ultimateinterview-postmortem
description: Spec-vs-implementation retrospective that calibrates ultimateinterview's unknown-unknown discovery rate. Use after code implementing an ultimateinterview handoff has been written or merged, when the user says "spec postmortem", "postmortem the spec", "what did the interview miss", "requirements retrospective", "compare spec to PR", "missed requirements", "interview lessons", or wants lessons accumulated so the next interview triggers the right lenses earlier.
---

# Ultrainterview Postmortem

Compare what the spec promised with what the implementation actually needed. Every substantive behavior the code contains that the spec never mentioned is an unknown unknown that escaped the interview; attribute each escape to the interview mechanism that should have caught it, and store it as a durable lesson the next interview inherits. Lenses and gates improve coverage, but only a postmortem measures what still got through - this is the feedback loop that calibrates the discovery rate itself.

## Preconditions

- An interview session folder exists: `.ultimateinterview/<slug>/` with `handoff.md` and `ledger.json`, and ideally `transcript.md`. If several slugs exist, ask which one. If none exists, say this skill needs an ultimateinterview handoff and stop; offer an ordinary code review instead.
- Implementation evidence exists: a merged PR, a commit range, a branch diff, or the working tree. Prefer `git log` and `git diff` scoped since the handoff was written; ask the user to point at the PR or range when it is ambiguous.
- Do not run this before the implementation is substantially done. A postmortem of half-built work misclassifies in-progress items as scope drift.

## Divergence Audit

Read the handoff's requirements ledger, acceptance criteria, decision boundaries, non-goals, and deferred risks. Read the implementation diff. Then walk both directions:

- for each diff hunk: which spec requirement does this serve?
- for each spec requirement: where is it implemented, and where is it verified?
- deterministic first pass (before the two-direction walk): run `ultimateinterview/scripts/handoff_coverage.py <session-dir> --advisory`. Any settled weight-`2`-or-higher ledger id absent from Part 1 is a `synthesis-loss` candidate — the interview caught it but the Build-Contract drafting dropped it untraced. Then read each *cited* settled entry against its Part-1 row for sub-case narrowing (behavior-level synthesis-loss the id-citation script cannot see).

Classify every requirement and every unmatched piece of implementation:

| Class | Meaning | Signal |
| --- | --- | --- |
| `fulfilled` | in spec and implemented | none - confirms the interview |
| `escaped-requirement` | implemented but absent from the spec | an unknown unknown got through - attribute it |
| `scope-drift` | in spec, not implemented, not deferred | handoff overpromised, or implementation dropped it silently |
| `divergent-implementation` | implemented differently than spec'd | a decision boundary was crossed or a settled/`Contested` decision reversed |
| `deferred-outcome` | deferred in the handoff | record whether the risk materialized |

Rules:

- Only substantive behavior counts as an escaped requirement: error handling, edge cases, data rules, compatibility shims, migrations, configuration, security checks, operational hooks. Renames, formatting, comments, and pure refactors do not.
- Check non-goals before classifying: behavior a non-goal explicitly excluded is a scope change decided during implementation - `divergent-implementation`, not an interview miss.
- Check `transcript.md` before declaring an escape: if the topic was asked and answered but recorded wrong or compressed away, the failure is answer handling, not enumeration - the attribution differs.
- Self-audit guard: when the postmortem runner also wrote the implementation (or shares its context - same session or same agent), delegate the two-direction inventory to a fresh-context subagent given ONLY the spec and the diff (no conversation, no ledger); it returns the substantive-behavior inventory and both unmatched lists, while classification and attribution stay with the main agent. An implementer auditing its own code for escapes is circular - the same reason ultimateinterview sends fresh-context gates to a subagent. Dispatch this fresh-context inventory subagent - and any other verification subagent this skill spawns - through the harness task tool with the agent name `critic` (a read-only review role); the lane's functional role lives in its per-task prompt, never the agent name, so a `task.agentModelOverrides["critic"]` binding can route it to a cross-vendor model without changing the postmortem model.

## Lens Attribution

For each `escaped-requirement`, name the mechanism that should have caught it and why it did not:

- `trigger-too-narrow`: the lens that owns this class of gap never triggered. Lesson: a new signal-to-lens trigger.
- `enumeration-miss`: the lens ran but never listed the gap. Lesson: a new question or check inside that lens.
- `scoring-starved`: the gap was in the ledger but its question never ranked high enough before the budget ran out. Lesson: note which scoring dimension was systematically underestimated.
- `answer-unpressured`: settled without pressure or triangulation, and the answer was wrong or incomplete. Pressure is scoped, so name the sub-case in the lesson: a required pressure trigger fired but was skipped (which Answer Handling rule was ignored), or no trigger fired and the answer was pressure-exempt yet wrong - the scoping missed a risk signal. The second sub-case covers accepted smart-default batch items and unpressured brain-dump claims, and its lesson is a trigger or batch-routing widening, not a skipped rule.
- `synthesis-loss`: the interview enumerated AND settled the behavior in the ledger, but the Build-Contract drafting narrowed or dropped it from Part 1 — the escape lives in the handoff synthesis step, not the enumeration. Distinct from `enumeration-miss` (never captured) and `answer-unpressured` (captured but settled wrong). Two sub-cases: the settled entry id is absent from Part 1 (caught deterministically by `handoff_coverage.py`), or the id is cited but the Part-1 REQ reproduces only a subset of the entry's enumerated behavior (e.g. ledger `corrupt/permission/write failure` → REQ keeps only `corrupt`). The lesson is NOT a lens-routing rule; it is a handoff-fidelity fix (the coverage gate + the behavior-fidelity rule in `ultimateinterview/references/handoff-sequence.md`), so it does not go in the lessons store.
- `known-deferred`: deferred with owner/date. Not a miss; record it under deferred outcomes.

Every attribution carries evidence: the diff hunk, and the ledger or transcript line - or its documented absence.

## Lessons Store

Two stores, same format: `docs/ultimateinterview-lessons.md` in the repo root for repo-specific signals (committed and durable, because `.ultimateinterview/` is gitignored working state), and the global `~/.agents/skills/ultimateinterview/lessons.md` for signals not tied to this repo's domain - generalize the signal and write it there instead, so lessons compound across a multi-repo solo workflow. Dedupe across both stores. Create either file from the skeleton in `references/postmortem-template.md` when missing.

Each lesson row: `| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |`

- The signal must be observable in the request or repo at interview time ("change touches a scheduled/cron path", "request mentions export or download"), never hindsight ("we forgot X").
- Dedupe before appending: read the existing lessons and strengthen or generalize an existing row instead of adding a near-duplicate.
- Lessons are routing rules, not methodology: they make existing lenses trigger earlier; they do not add new interview machinery.
- Fire-tracking and retirement: for each existing lesson whose signal appeared in the interview under postmortem, increment `Fired`; if its lens produced any ledger entry carrying a `lesson-triggered` marker - in `origin` (`lens:<name>`) or in `reason` (orientation-time triggers record `origin: orientation` with a lesson-triggered reason) - also increment `Caught`. Apply increments with the ultimateinterview skill's `scripts/lessons.py fire <lessons.md> <row-index-or-signal-substring> [--caught]` - it owns the arithmetic and the retirement rule (Fired ≥ 3 with Caught 0 auto-moves the row to `## Retired`; dry-firing lessons are a tax on every future interview). `scripts/lessons.py validate` checks the table shape after any hand-edit.

The `ultimateinterview` skill reads this file during Orientation and treats a lesson's lens as triggered when its signal appears in a new request. That closes the loop.

## Output Contract

Write the report to `.ultimateinterview/<slug>/postmortem.md` and update `docs/ultimateinterview-lessons.md` in the same turn. The report must include:

- `Implementation evidence`: the PR, commit range, or diff examined
- `Divergence table`: every spec requirement and every unmatched implementation behavior, classified
- `Escaped requirements`: each with lens attribution, failure class, and evidence
- `Deferred outcomes`: which deferred risks materialized
- `Verification execution`: whether the spec's Verification Commands actually ran and passed (run them when cheap; otherwise name which were not executed) - unrun verification can hide scope drift
- `Scope drift / divergent implementations`: each with whether the user must re-decide
- `Lessons appended or updated`: the exact rows written
- `Calibration summary`: counts per divergence class and per failure class (the failure classes include `synthesis-loss`), plus the discovery rate computed as `fulfilled / (fulfilled + escaped-requirement + divergent-implementation)` at divergence-table-row granularity - the table IS the denominator, never recount informally. Report TWO rates: **interview-discovery** (exclude `synthesis-loss` escapes from the numerator's escape count, since the interview actually caught them) and **handoff-fidelity** (include them) - lumping the two hides whether the miss was in enumeration or in the ledger→handoff synthesis. Give each escaped requirement an impact weight (ledger `1`/`2`/`3`/`5` scale) and report the weighted rate beside the raw one; escape-severity trends across runs are unmeasurable otherwise.

If a `divergent-implementation` reversed a user decision recorded in the handoff, flag it to the user explicitly as a decision needing re-confirmation, not just a log line. When the user answers a re-confirmation flag, record the decision as a `## Resolution addendum` in the report; applying it (handoff edit, code change) happens outside the postmortem.

Do not modify the ultimateinterview skill, the handoff, or the implementation from inside a postmortem. The only outputs are the report and the lessons file.
