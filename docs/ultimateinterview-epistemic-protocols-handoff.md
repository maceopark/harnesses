# Spec: Ultimateinterview Epistemic-Protocols Hardening

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence and rationale. Do not ask the user to choose, invoke, or understand any Epistemic Protocol. The whole point of this change is to absorb the useful methodology into `ultimateinterview` while reducing user friction. Preserve unrelated dirty work in this repository.

# Part 1 - Build Contract

## Goal

Strengthen `ultimateinterview`'s unknown-unknown discovery method by internalizing selected Epistemic Protocols ideas as hidden interview machinery, without adding user-facing protocol choices or extra ceremony.

## Current Worktree Context

This handoff was written in `/Users/jpark/IdeaProjects/harnesses` on top of an already dirty tree.

Known existing state at handoff creation:

| Path / area | State | Instruction |
| --- | --- | --- |
| `.gitmodules`, `AGENTS.md`, `epistemic-protocols` | staged from the earlier submodule add | Do not unstage, revert, or alter unless the user asks. |
| `.agents/skills/ultimateinterview/references/audit-checklists.md` | modified before this handoff | Treat as existing user/agent work; inspect before editing. |
| `.agents/skills/ultimateinterview/references/handoff-sequence.md` | modified before this handoff | Treat as existing user/agent work; inspect before editing. |
| `.agents/skills/ultimateinterview/references/orientation.md` | modified before this handoff | Treat as existing user/agent work; inspect before editing. |
| `.agents/skills/ultimateinterview/scripts/regression_check.py` | modified before this handoff | Treat as existing user/agent work; inspect before editing. |
| `.agents/skills/ultimateinterview/scripts/predicate_lint.py` and related tests/fixtures | untracked before this handoff | Preserve unless the user explicitly scopes them into this work. |
| `.agents/skills/ultimateinterview-postmortem/scripts/audit_scan.py` and `test_audit_scan.py` | unrelated untracked files observed during handoff verification | Preserve unless the user explicitly scopes them into this work. |
| `docs/ultimateinterview-three-arm-benchmark.md` | untracked before this handoff | Preserve. |
| `claudeplan/`, `todo-cli-codexplan/` | untracked before this handoff | Preserve. |

Before coding, run:

```bash
git status --short --branch
git diff --stat -- .agents/skills/ultimateinterview docs
git diff --cached --stat
```

## Target Surface

| File / module | Expected change |
| --- | --- |
| `.agents/skills/ultimateinterview/SKILL.md` | Keep the hot-path contract short. Add only routing-level instructions if needed. Prefer moving method detail into references. Do not expose Epistemic Protocol names as required user choices. |
| `.agents/skills/ultimateinterview/references/orientation.md` | Add a hidden deficit-recognition pass during ORIENT. It should tag likely deficit classes internally and use them to trigger lenses, not present protocol menus to the user. |
| `.agents/skills/ultimateinterview/references/interview-loop.md` | Add reverse-evidence / would-falsify handling to question generation and lens continuation. Strengthen recognition-style checkpoints that ask the user to correct the model, not select a protocol. |
| `.agents/skills/ultimateinterview/references/lenses.md` | Define per-lens output contracts so each lens produces a typed artifact or a documented skip reason. The output contract matters more than the lens label. |
| `.agents/skills/ultimateinterview/references/handoff-sequence.md` | Add an endgame guardrail-compile pass: split handoff risks into verifiable stop-time predicates, accepted residuals, and fast/pre-action risks that belong to the harness substrate. |
| `.agents/skills/ultimateinterview/references/state-files.md` | If persistent state is needed, document it here. Prefer reusing existing `ledger.origin`, `ledger.reason`, `lenses.reason`, and `questions.json` fields before adding new protocol schema fields. |
| `.agents/skills/ultimateinterview/scripts/protocol_state.py` | Change only if new protocol state is unavoidable. Existing `extra="forbid"` means any new protocol field requires model, initializer, updater, and tests. |
| `.agents/skills/ultimateinterview/scripts/session_init.py` | Update initial `protocol.json` only if a new persistent field is added. |
| `.agents/skills/ultimateinterview/scripts/session_update.py` | Update delta validation / managed-key logic only if new persistent fields are added or modified mechanically. |
| `.agents/skills/ultimateinterview/scripts/question_score.py` or related tests | Add scoring support only if `would_falsify` or reverse-evidence becomes structured data in `questions.json`; otherwise keep it prose-level in question records. |
| `.agents/skills/ultimateinterview/scripts/test_*.py` | Add focused tests for any schema or script behavior. Prose-only changes still need at least static/read-through verification and, where possible, regression fixtures. |
| `epistemic-protocols/` | Read-only reference. Do not modify the submodule for this task. |

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | Users are never asked to choose an Epistemic Protocol or learn its vocabulary. | When an interview starts, the visible user flow remains brain dump / dashboard / highest-leverage question / checkpoint. No new user-facing prompt asks "which protocol" or offers `/probe`, `/bound`, `/attend`, etc. | user-goal-1 |
| REQ-002 | ORIENT performs hidden deficit recognition. | When ORIENT inspects repo/request context, it internally classifies likely gap classes such as context insufficiency, boundary undefined, framework absent, execution blind, application mismatch, context tethering, recall/comprehension, or method underdetermined. Those tags influence lens triggers or skip reasons. | epi-probe |
| REQ-003 | Hidden deficit recognition is multi-hypothesis and falsifiable. | When two plausible interpretations exist, ORIENT records at least two candidate readings with evidence and reverse-evidence in internal state, transcript, or ledger reason text. It must not silently collapse to a single confident frame unless the evidence is unambiguous. | epi-probe |
| REQ-004 | Lens triggers carry reverse-evidence. | Every triggered heavy lens records why it fired and what observation would make the lens unnecessary or complete. A lens without remaining reverse-evidence can be marked done or skipped-with-reason instead of continuing to ask questions. | epi-probe |
| REQ-005 | Lens output is typed by artifact, not by method ceremony. | Each triggered lens produces the artifact expected for that lens, or records a skip reason: `ViewpointMatrix`, `StateModel`, `GoalObstacleMap`, `MisuseCaseSet`, `QualityScenarioSet`, or `ControlledAcceptanceCriteria`. The user does not see this as a menu. | ui-method-1 |
| REQ-006 | Questions do more work per round-trip. | Question shaping should prefer recognition/checkpoint style where possible: present the current model and ask the user to correct wrong or incomplete lines. Do not replace this with more open-ended questions unless narration is needed. | friction-1 |
| REQ-007 | Scored question candidates include falsification value. | Candidate generation considers what answer or observation would falsify the current model, not only what would fill a known blank. If represented in JSON, tests cover it; if prose-level, the interview-loop guidance names it explicitly. | ui-method-2 |
| REQ-008 | Smart-default batches stay scope-neutral. | Any new defaulting behavior must keep the existing rule: defaults can settle how an in-scope behavior works, never add a capability or narrow settled scope without explicit user decision. | existing-ui-rule |
| REQ-009 | Endgame compiles execution guardrails. | Before final handoff, the Build Contract includes a guardrail compile section or equivalent rows that split risks into stop-time verifiable predicates, accepted residuals, and fast/pre-action risks delegated to harness/tool permissions. | epi-prosoche |
| REQ-010 | Natural-language "done" conditions do not count as predicates. | A guardrail is considered compiled only if it has an executable or objectively observable pass/fail condition: command exit status, test result, countable threshold, file-state assertion, endpoint response, or similarly determinate check. | epi-prosoche |
| REQ-011 | Fast risks are surfaced, not simulated. | Risks requiring pre-action interception, such as destructive command blocking, permission prompts, prompt-injection defense, or irreversible external side effects, are not converted into stop-time checks. They are named as out-of-scope for interview guardrails and delegated to the harness/substrate. | epi-prosoche |
| REQ-012 | Build Contract remains the implementer-facing surface. | The final handoff still opens with Part 1 Build Contract, and the new guardrail/lens material must not bury implementation decisions in audit-only prose. | existing-handoff |
| REQ-013 | Method hardening does not increase visible friction. | Minimal/focused interviews must not require extra visible user turns solely because hidden deficit tags or reverse-evidence exist. New prompts must replace or compress existing prompts unless a genuine critical-path gap appears. | friction-2 |
| REQ-014 | Existing deterministic helper invariants remain valid. | If schema fields are added, `session_init.py`, `session_update.py`, `protocol_state.py`, and tests all validate them fail-closed. If no fields are added, existing helpers continue to pass unchanged. | existing-scripts |
| REQ-015 | The change is covered by a cold-start rehearsal or regression fixture. | A fresh session can demonstrate the new method on a small brownfield request and show: hidden deficit tags were used, a lens had reverse-evidence, a recognition-style checkpoint ran, and guardrail compile produced at least one predicate/residual/fast-risk classification. | qa-1 |

## Recommended Implementation Shape

Prefer this minimal internal model before inventing new schema:

1. ORIENT writes hidden method conclusions into ordinary ledger entries and lens reasons:
   - `origin: "orientation"` or `origin: "lens:<name>"`
   - `reason` includes compact tags such as `deficit=context-insufficient` and `reverse-evidence=<short condition>`
   - `lenses.<name>.reason` records trigger + reverse-evidence + skip/done rationale
2. `questions.json` remains backward compatible:
   - If adding `would_falsify` to candidate records, update `question_score.py` and tests.
   - If not adding fields, document the concept in `interview-loop.md` and include it in candidate question prose.
3. Endgame guardrail compile is represented in the handoff template / handoff-sequence prose, not necessarily in protocol state.
4. Add schema only if the prose representation becomes ambiguous or untestable.

If new protocol fields are necessary, use an additive object such as:

```json
{
  "methodology": {
    "deficit_hypotheses": [
      {
        "name": "ContextInsufficient",
        "evidence": "...",
        "reverse_evidence": "...",
        "disposition": "active|dismissed|resolved"
      }
    ],
    "guardrail_compile_done": false
  }
}
```

But this is a fallback, not the preferred first move, because `protocol_state.py` forbids extra fields and every new field increases deterministic-helper surface area.

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Exact internal names for deficit tags | yes | Use clear ASCII names. Do not require user-facing Greek or slash-command names. |
| Whether to persist deficit hypotheses as new schema | yes, but prefer no | Add schema only if ledger/lens reasons are insufficient for replay or testing. |
| Whether to update `question_score.py` | yes | Required only if adding structured candidate fields. Do not change the scoring formula unless necessary. |
| Whether guardrail compile gets its own section in the handoff template | yes | It must be visible in Part 1 or in verification/decision-boundary rows. |
| Whether to mention Epistemic Protocols in runtime docs | limited | Source attribution in contributor/audit docs is fine. Runtime user instructions should not depend on Epistemic docs. |
| How much SKILL.md changes | constrained | Keep SKILL.md as phase routing + invariants. Move method detail to references. |

## Out Of Scope / Non-Goals

- Do not build a separate `/probe`, `/attend`, `/conduct`, or protocol-selection UI inside `ultimateinterview`.
- Do not require users to learn Epistemic Protocol names, Greek terms, or plugin taxonomy.
- Do not modify the `epistemic-protocols` submodule.
- Do not redesign the entire interview state machine.
- Do not remove existing ledger, pressure, sweep, contrarian, checkpoint, or handoff gates.
- Do not address unrelated dirty changes unless they directly block this work.
- Do not commit or push unless the user explicitly asks.

## Quality Bars

| Attribute | Bar | Weight | Verification |
| --- | --- | --- | --- |
| User friction | No new mandatory visible user turn in minimal/focused flow solely for hidden deficit recognition. | 5 | Rehearsal transcript or example flow shows hidden work folded into existing ORIENT/checkpoint/batch turns. |
| Method rigor | At least one lens trigger records reverse-evidence, and at least one guardrail predicate is determinate. | 5 | Rehearsal handoff / fixture includes these rows. |
| Runtime self-containment | A user can run `ultimateinterview` without reading `epistemic-protocols`. | 3 | Runtime docs contain no dependency on Epistemic docs for correct use. |
| Helper stability | Existing deterministic-helper tests still pass. | 5 | Commands below pass, or failures are clearly pre-existing and unrelated. |

## Verification Commands

Run from `/Users/jpark/IdeaProjects/harnesses` unless noted.

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Worktree awareness | `git status --short --branch` | Existing staged submodule docs and unrelated dirty files are visible; implementation touches only intended files. |
| Core helper tests | `cd .agents/skills/ultimateinterview && uv run scripts/test_deterministic_helpers.py` | Passes. |
| Verification lint tests | `cd .agents/skills/ultimateinterview && uv run scripts/test_verification_lint.py` | Passes. |
| Regression harness tests | `cd .agents/skills/ultimateinterview && uv run scripts/test_regression_check.py` | Passes if that current dirty test harness is in scope; otherwise report skipped because it predates this task. |
| Predicate lint tests | `cd .agents/skills/ultimateinterview && uv run scripts/test_predicate_lint.py` | Passes if current untracked predicate lint work is in scope; otherwise do not claim it. |
| Protocol-state schema smoke | `cd .agents/skills/ultimateinterview && uv run scripts/protocol_state.py --format markdown references/example-session/protocol.json` or the current example-session protocol path if different | Parses, or report exact missing fixture path. |
| Markdown lint by Git | `git diff --check -- .agents/skills/ultimateinterview docs/ultimateinterview-epistemic-protocols-handoff.md` | No whitespace errors. |
| Fresh-session rehearsal | Run one small interview or fixture that exercises the new method | Demonstrates hidden deficit recognition, reverse-evidence, recognition-style checkpoint, and guardrail compile without adding a protocol-selection prompt. |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| Whether hidden deficit tags deserve first-class schema | user / implementer | after first implementation attempt | Start with ledger/lens reasons. Add schema only if replay or tests are weak. |
| Discovery-rate improvement is not proven by static docs alone | user | after one real postmortem | Use `ultimateinterview-postmortem` after the first implemented interview-based task. |
| Current dirty predicate-lint work may overlap with this handoff | implementer | before editing scripts | Inspect current diffs first; do not overwrite unrelated changes. |
| Guardrail compile could become new ceremony | implementer | during rehearsal | Keep it in endgame and Part 1 rows; do not add a new user decision turn unless it reveals a critical-path gap. |

# Part 2 - Audit Trail

## Problem

The user wants to learn from `epistemic-protocols` without making `ultimateinterview` harder to use. The shared purpose is unknown-unknown discovery. The friction risk is that Epistemic Protocols require good judgment about when humans should intervene and which protocol fits; the user explicitly does not want to push that burden onto the operator.

Therefore the implementation should absorb methodology, not UX.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | The problem is not lack of more protocol choices; it is that hidden ambiguity-routing can be stronger while visible questioning gets lighter. |
| Do-nothing option | Leaves useful Epistemic insights unused, especially reverse-evidence and execution guardrail compilation. |
| Simpler alternative | Add a small hidden methodology layer to existing ORIENT/LOOP/ENDGAME instead of new commands or UI. |
| Artifact class confirmed | Durable coding handoff for a clean session. |

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-docs | `ultimateinterview` already states its purpose as evidence-led requirements ambiguity removal and unknown-unknown hunting. | high |
| from-docs | `ultimateinterview` already has phases, ledger, evidence channels, pressure, checkpoint, sweep, contrarian probe, and handoff gates. | high |
| from-docs | `epistemic-protocols` decomposes collaboration failures into protocols spanning planning, analysis, decision, execution, verification, recall, and comprehension. | high |
| from-docs | `/probe` provides multi-hypothesis deficit recognition with evidence and reverse-evidence, but would be too high-friction if exposed directly inside `ultimateinterview`. | high |
| from-docs | `/attend` compiles autonomous execution risk into verifiable predicates, accepted residuals, and fast risks delegated to a substrate. | high |
| from-user | The user wants friction reduction and methodology strengthening, not manual skill selection. | high |

## Methodology Mapping

| Epistemic idea | Useful part | How to absorb into `ultimateinterview` |
| --- | --- | --- |
| Deficit recognition (`/probe`) | Multi-hypothesis frame detection with reverse-evidence | Hidden ORIENT pass that informs lens triggers and checkpoint statements. |
| Recognition over resolution | User confirms/corrects the model instead of the AI scoring the final truth | More checkpoint-style prompts: "correct wrong/incomplete lines" rather than protocol menus. |
| Reverse-evidence | Each hypothesis names what would shrink or falsify it | Add to lens trigger reasons and question generation. |
| Protocol output types | Each move produces a named resolution artifact | Convert lenses into output contracts: matrix, state model, obstacle map, misuse cases, quality scenarios, acceptance criteria. |
| Execution attention (`/attend`) | Compile slow risks into verifiable predicates; surface fast risks as substrate-owned | Add endgame guardrail compile before handoff. |
| Audience-layer separation | Runtime users should not need maintainer theory | Keep Epistemic rationale in docs/handoff, not in the hot user path. |

## Source Pointers

Read these files before coding:

| File | Why |
| --- | --- |
| `.agents/skills/ultimateinterview/SKILL.md` | Hot-path runtime contract. Keep it short and self-contained. |
| `.agents/skills/ultimateinterview/references/orientation.md` | ORIENT, framing challenge, depth, lens trigger rules. |
| `.agents/skills/ultimateinterview/references/interview-loop.md` | Question scoring, checkpoints, smart defaults, advisory lanes. |
| `.agents/skills/ultimateinterview/references/lenses.md` | Lens methods and where typed outputs should be specified. |
| `.agents/skills/ultimateinterview/references/handoff-sequence.md` | Build Contract and endgame gates. |
| `.agents/skills/ultimateinterview/references/state-files.md` | State schema and delta rules. |
| `.agents/skills/ultimateinterview/scripts/protocol_state.py` | Protocol schema; `extra="forbid"` makes schema changes explicit. |
| `.agents/skills/ultimateinterview/scripts/session_init.py` | Initial protocol defaults. |
| `.agents/skills/ultimateinterview/scripts/session_update.py` | Delta writer and managed counters. |
| `epistemic-protocols/epistemic-cooperative/skills/probe/SKILL.md` | Reference for hidden multi-hypothesis + reverse-evidence, read-only. |
| `epistemic-protocols/prosoche/skills/attend/SKILL.md` | Reference for guardrail compile, read-only. |
| `epistemic-protocols/docs/mission-bridge.md` | Reference for audience-layer separation, read-only. |

## Suggested Work Plan For Fresh Session

1. Inspect current dirty diffs and decide whether current uncommitted changes overlap.
2. Implement the smallest no-schema version first:
   - orientation hidden deficit tags in prose;
   - reverse-evidence in lens trigger guidance;
   - per-lens output contracts;
   - endgame guardrail compile section.
3. Run docs/static verification.
4. If the no-schema version cannot be tested or replayed, add minimal schema and update deterministic helpers/tests.
5. Add or update one worked example/rehearsal proving the method does not add visible friction.
6. Run the helper tests and report any pre-existing failures separately.

## Fresh-Implementer Test Notes

A clean implementing agent should be able to start from Part 1 and answer:

1. What files do I touch?
2. What behavior changes are required?
3. What must not change?
4. How do I prove friction did not increase?
5. How do I prove the method got stronger?

If any answer is unclear, treat it as a spec gap and ask before coding.

## Restated Approval Check

This document assumes the user's intended direction is:

- strengthen `ultimateinterview` methodology using lessons from `epistemic-protocols`;
- do not make the user choose skills/protocols;
- reduce friction by using recognition/checkpoint-style confirmation and smarter internal routing;
- keep implementation focused on `ultimateinterview`, with `epistemic-protocols` as read-only reference.

Approval status: draft handoff created from the conversation, pending implementation in a fresh session.
