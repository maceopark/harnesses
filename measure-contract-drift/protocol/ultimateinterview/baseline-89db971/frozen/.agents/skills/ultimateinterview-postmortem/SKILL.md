---
name: ultimateinterview-postmortem
description: Spec-vs-implementation retrospective for compiler-only ultimateinterview sessions. Use after code implementing a sealed Build Contract has been written or merged, when the user asks what the interview or contract missed, requests a requirements retrospective, or wants durable lessons.
---

# Ultimateinterview Postmortem

Compare what the spec promised with what the implementation actually needed. Attribute every substantive escape to the mechanism that should have caught it. Store eligible routed findings as durable lessons; keep ontology misses explicitly non-routing until the ontology is separately revised. Lenses and gates improve coverage, but only a postmortem measures what still got through.

## JSON Contract Reference

Before accepting or parsing a compiler-only session, read `../ultimateinterview/references/json-contracts.md`. Validate every owned JSON/JSONL artifact against that shared reference and the current compiler/checker; never maintain a divergent postmortem-only copy of these formats.

## Preconditions

- A repository-local session exists at `.ultimateinterview/<slug>/` with `build-contract.json` using schema `ultimateinterview.build-contract.v1` and its `discovery-record.json`. `implementation-return.json` and `decision.jsonl` are implementation evidence and may be absent but must never be fabricated. A session without both compiler artifacts is not auditable; report the missing artifact and stop.
- The Build Contract is the sole normative source. The Discovery Record, repository behavior, implementation return, decision log, tests, and prior conversation are evidence only. Verify the contract digest, recompile the Discovery Record with the authority compiler, and require structural equality before auditing.
- Implementation evidence exists: a merged PR, commit range, branch diff, or working tree. Scope the evidence to the Build Contract's normalized scope entries. Ask for a PR or range only when repository state cannot disambiguate the implementation.
- Do not run this before implementation is substantially done. A postmortem of half-built work misclassifies in-progress items as divergence.
- Evidence packing is this skill's job. First run `python3 scripts/compiler_session_check.py <session-dir> [--diff-range <range> | --diff-file <path>]` from this skill directory. It validates the sealed digest, recompiles the Discovery Record, validates `implementation-return.json` and `decision.jsonl` digest binding, scopes repository evidence from the contract, and writes `compiler-evidence-bundle.json`. Rebuild the bundle even when one already exists.
- A pre-existing `postmortem.md` whose evaluator provenance is absent or not independent is a self-report: preserve it as `postmortem.self.md`, consume it only as evidence, and write a new independent report.

## Divergence Audit

Read the compiler-produced Build Contract's goal, scope, non-goals, authorities, requirements, acceptance predicates, verifications, trace, bounded delegations, and implementation-decision policy. Read the Discovery Record and implementation evidence as non-authoritative context. Then walk both directions:

First check every verification command for a stated working directory, exact target, and selection or isolation semantics. Treat a missing execution-context element as a contract gap, not as permission for an implementation hook.

- each implementation change -> an authorized requirement or bounded delegation;
- each contract requirement -> implementation location and directly observed verification evidence;
- each `decision.jsonl` row -> the contract gap it records, its authority boundary, and the resulting implementation behavior;
- each substantive branch, refusal, fallback, preflight, hook, recovery behavior, or policy -> an authorized requirement, acceptance predicate, or bounded delegation;
- deterministic pass: run `scripts/compiler_session_check.py` and require a valid digest-bound bundle. Trace completeness is compiler-owned; compare every requirement, acceptance, verification, authority reference, and decision record represented by the bundle.

Classify every requirement and every unmatched piece of implementation:

| Class | Meaning | Signal |
| --- | --- | --- |
| `fulfilled` | in spec and implemented | none - confirms the interview |
| `escaped-requirement` | implemented but absent from the spec | an unknown unknown got through - attribute it |
| `scope-drift` | in contract, not implemented, not deferred | the sealed contract overpromised, or implementation dropped it silently |
| `divergent-implementation` | implemented differently than contracted | an authority or decision boundary was crossed |
| `deferred-outcome` | explicitly deferred in the Build Contract | record whether the risk materialized |

Rules:

- New reports start with `postmortem_schema: 2`. Keep one divergence row per Build Contract `REQ-NNN`; give every escape its own stable `ESC-NNN`, then join that identity exactly once through Divergence → Escaped Requirements → Wonder. A fulfilled requirement cannot masquerade as an escape.
- Only substantive behavior counts as an escaped requirement: error handling, edge cases, data rules, compatibility shims, migrations, configuration, security checks, operational hooks, refusals, fallbacks, preflights, and recovery policies. Renames, formatting, comments, and other non-substantive internal choices do not. Every substantive behavior must map to an authorized requirement, acceptance predicate, or bounded delegation.
- Check non-goals before classifying: behavior a non-goal explicitly excluded is a scope change decided during implementation - `divergent-implementation`, not an interview miss.
- Check the Discovery Record before declaring an escape: when an owner decision or supporting observation was captured but narrowed or dropped before sealing, classify the mechanism as answer handling or `synthesis-loss`, not an enumeration miss.
- Walk each `decision.jsonl` row as evidence, not as an automatic failure. A logged non-substantive internal choice may proceed. A logged substantive behavior with no authority mapping is an `escaped-requirement`; a logged choice contradicting a governed clause is a `divergent-implementation`. Missing evidence keeps that audit axis explicit rather than authorizing or classifying around the hole.
- Self-audit guard: when the postmortem runner also wrote the implementation or shares its context, delegate the two-direction inventory to a fresh-context `critic` subagent given only the sealed Build Contract and implementation diff. It returns substantive behavior and both unmatched lists; classification and attribution remain with the evaluator.

## Lens Attribution

For each `escaped-requirement`, name the mechanism that should have caught it and why it did not:

- `trigger-too-narrow`: the lens that owns this class of gap never triggered. Lesson: a new signal-to-lens trigger.
- `enumeration-miss`: the lens ran but never listed the gap. Lesson: a new question or check inside that lens.
- `answer-unpressured`: the Discovery Record captured an owner answer without enough pressure or triangulation and the authorized clause is wrong or incomplete. Name the skipped or missing pressure trigger.
- `synthesis-loss`: discovery evidence or an authorized decision contains behavior that the compiler input or sealed requirement narrowed or dropped. Distinguish Discovery Record loss from impossible post-compile loss by inspecting compiler trace and acceptance bindings. This is a contract-fidelity fix, not a routing lesson.
- `known-deferred`: explicitly deferred with owner and boundary. Not a miss; record it under deferred outcomes.

Every attribution carries implementation evidence plus a Build Contract or Discovery Record authority, requirement, acceptance, verification, or evidence reference. Absence must be explicit.
Intent is not deterministically reconstructable. A digest-bound `decision.jsonl` record is owned execution evidence only when its `requirement_refs` covers the row; it never supplies authority. Otherwise record `intent: run-blind (no owned signal)`.

## Improvement Proposals

After classification, derive improvements from observed escapes and divergences. The report is an evaluator output, so proposals remain non-authoritative until separately accepted and applied.

For each distinct root cause, draft at most one proposal. Keep only proposals that satisfy all four gates:

1. **Simple:** expressible as one short rule or one bounded check; no new workflow, role, ontology, scoring system, or mandatory ceremony.
2. **Effective:** names the escaped or divergent behavior it would have prevented and the interview or handoff point where it acts.
3. **General:** applies to a reusable class of work across multiple domains, not to the audited product, framework, command, or file layout.
4. **Compatible:** does not contradict or duplicate the current `ultimateinterview` skill. Read that skill before proposing a change, cite the nearest existing rule, and prefer a narrow strengthening or clarification over parallel doctrine.

Reject proposals that merely restate the missed behavior, rely on hindsight-only signals, or cannot identify a concrete prevention mechanism. Group multiple findings under one proposal when the same general rule prevents them. Usually one to three proposals are enough; zero is valid when the current skill already contains the necessary rule and the failure was execution noncompliance.

For each `escaped-requirement`, retain the reusable unknown class, interview-time observable precursor, owning lens or frame, and lesson disposition as supporting detail. A `synthesis-loss` is a contract-fidelity finding, not a routing lesson. An `ontology-miss` uses `owning frame:none`, a `novel:<slug>` requirement structure, and remains non-routing until the ontology is separately revised.

A new lesson starts at `Fired/Caught` `0/0`; the audit that generated it cannot retroactively fire it. Improvement analysis MUST NOT recurse, mutate the ontology, use similarity scoring, or graduate a lesson automatically.
## Lessons Store

Two stores, same format: `docs/ultimateinterview-lessons.md` in the repo root for repo-specific signals (committed and durable, because `.ultimateinterview/` is gitignored working state), and the global `~/.agents/skills/ultimateinterview/lessons.md` for signals not tied to this repo's domain - generalize the signal and write it there instead, so lessons compound across a multi-repo solo workflow. Dedupe across both stores. Create either file from the skeleton in `references/postmortem-template.md` when missing.

Each lesson row: `| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |`

- The signal must be observable in the request or repo at interview time ("change touches a scheduled/cron path", "request mentions export or download"), never hindsight ("we forgot X").
- Dedupe before appending: read the existing lessons and strengthen or generalize an existing row instead of adding a near-duplicate.
- Lessons are routing rules, not methodology: they make existing lenses trigger earlier; they do not add new interview machinery.
- Fire-tracking and retirement: for each existing lesson whose signal appeared in the audited request or repository, increment `Fired`. Increment `Caught` only when the Discovery Record explicitly preserves a `lesson-triggered` marker and the resulting requirement or evidence reference covers that signal. Without that owned marker, record not-caught rather than inferring success. Preserve the report's `Lessons Fire-Tracking` table as the audit trail.
- Graduation to methodology: a lesson row whose rule has been absorbed into the interview skill's own body (a lens trigger, a lens method line, an audit-checklist gate) moves to `## Retired` with reason `absorbed: <where>` and its final `Was Fired/Caught`. Graduation needs EVIDENCE, not a single catch: a row at `1/1` has proven itself exactly once and belongs in staging, not in permanent method - promoting it makes a conditional routing rule into unconditional ceremony on every future interview (the app-5 run over-promoted three `1/1` store rows to a blanket gate and a council review sent them back to staging; the gate that survived was made conditional). Absorb only rows with repeated catches OR rules that are inherently unconditional (a predicate must exist for "invalid X"; an implementer must not audit its own escapes) - those do not depend on a signal at all. Absorption is the end-state for proven routing rules, exactly as 3-dry-fire retirement is for dead ones.

The `ultimateinterview` skill reads this file during Orientation and treats a lesson's lens as triggered when its signal appears in a new request. That closes the loop.

## Output Contract

Write the report to `.ultimateinterview/<slug>/postmortem.md` and update eligible lesson rows in `docs/ultimateinterview-lessons.md` in the same turn.

The report MUST be conclusion-first. After the schema, digest, evaluator, and timestamp metadata, its first substantive section is `## Conclusion` containing:

- one plain-language verdict;
- a count line stating: total Build Contract requirements, fulfilled, escaped, scope-drift, divergent, deferred, and unverifiable;
- the distinct root causes in priority order;
- an `Ultimateinterview improvement proposals` table with at most three proposals, each naming the prevented finding, the exact skill rule to add or strengthen, why it works across domains, and the existing rule it is compatible with;
- an explicit `no skill change recommended` result when the current skill already contains the preventive rule and the failure was implementation or evaluator noncompliance.

A reader must be able to understand the outcome and recommended skill changes from `## Conclusion` without reading the rest of the report. Do not delay counts or recommendations until a calibration appendix.

After the conclusion, include only the evidence needed to substantiate it:

1. `Implementation Evidence`: contract digest, repository diff/range, directly observed verification, implementation return, and decision log.
2. `Divergence Table`: exactly one row per Build Contract requirement plus one row per unmatched substantive implementation behavior.
3. `Finding Details`: only escaped requirements, scope drift, divergent implementations, deferred outcomes, and unverifiable items. Include failure mode, requirement structure, owning frame, intent attribution, evidence, and whether the owner must decide again.
4. `Verification Execution`: one row per Build Contract `VER-ID`, with honest `passed`, `failed`, `blocked`, or `not-run` state and return agreement.
5. `Lessons`: only lesson rows fired, appended, strengthened, retired, or considered and rejected during this audit. Do not reproduce unaffected stores.
6. `Process Gaps and Missing Evidence`: logged contract gaps, absent required decision records, unbound returns, and verification gaps. These remain evidence, never product authority.
7. `Resolution Addendum`: owner responses, when any, as postmortem evidence only.

Do not emit separate Wonder, Reward-Hacking, or Calibration sections. Fold substantive reward-hacking concerns into the affected Divergence or Verification row; omit clear/no-signal boilerplate. Derive all headline counts mechanically from the Divergence Table and ensure each row contributes to exactly one class.

Run `python3 scripts/compiler_session_check.py <session-dir>` again after the report to prove all owned machine artifacts still bind the same sealed digest. Manually verify that the Conclusion counts equal the Divergence Table and that every proposal passes the Simple/Effective/General/Compatible gates.

If a `divergent-implementation` reversed an owner decision in the Build Contract, flag it explicitly for re-confirmation. Changing the contract, skill, or code remains outside the postmortem.

Do not modify the ultimateinterview skill, Discovery Record, Build Contract, implementation, or implementation return from inside a postmortem. Outputs are the report, eligible lesson updates, and the evaluator-owned regenerated compiler evidence bundle.
