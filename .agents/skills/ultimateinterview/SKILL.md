---
name: ultimateinterview
description: Evidence-led requirements ambiguity management for brownfield software changes. Use when a developer wants to expose consequential unknowns and produce an implementation-ready contract before coding. Especially for "ultimateinterview", "requirements gap", "clarify before coding", "unknown unknowns", "make a spec", brownfield feature requests, bugfixes with unclear desired behavior, or mentions of Socratic interview, deep-interview, grill-me, PRD, acceptance criteria, non-goals, edge cases, misuse cases, DDD, domain model, falsification checkpoint, brain dump, or build contract.
---

# Ultimateinterview

Run a requirements interview that treats code, docs, logs, domain flow, stakeholder viewpoints, failure modes, and user judgment as separate evidence channels. The result is implementation-ready under the recorded evidence, not proof that uncertainty is zero.

This file is the runtime: phase map, per-round loop, invariants. Method detail lives in `references/`, read at the phase that needs it - the read instructions below are mandatory, not suggestions.

## Phase Map

| Phase | Enter when | Do |
| --- | --- | --- |
| ORIENT | skill start | Scan `.ultimateinterview/` for folders without `handoff.md`; offer to resume the most recent before starting new. Then read `references/orientation.md` and follow it: classify, inspect repo + lessons, create session state via `scripts/session_init.py`, choose depth. |
| DUMP + FRAME | session state initialized | Per `references/orientation.md`: brain-dump invitation bundled with the depth calibration (or waiver / context-first checkpoint), then the framing challenge. |
| LOOP | framing recorded | Read `references/interview-loop.md` once, then run the Per-Round Loop below until the stop condition. Lens methods load from `references/lenses.md` as techniques activate. |
| ENDGAME | stop condition met; a readiness-gate trigger fires (`full` depth; a score `3` near handoff; a behavior/data/security-changing score `2`; the output seeds another agent or team; security/privacy, data/schema, irreversible writes, external integration, performance/reliability, or multi-stakeholder workflow touched); or the user asks for independent gating / seed readiness | Read `references/handoff-sequence.md` and execute its canonical pre-handoff sequence (flush → sweep/probe → checkpoint → audit → build contract → implementation gate → handoff) in the same turn. |

At any phase:

- If the user abandons ("enough, just build it"), do not exit empty-handed: write a `DRAFT - abandoned` handoff carrying the current Build Contract and every open gap as unresolved deferred risk (procedure: `references/handoff-sequence.md` §Abandonment).
- Do not implement inside `ultimateinterview` unless the user explicitly exits and asks you to code.
- If asked how this differs from other interview tools, read `references/comparison.md`.

## Core Rule

Do not ask the user for facts the repo can answer. Inspect first, let the user narrate before you interrogate, then ask the single highest-leverage human-decision question. Batch evidence probes into few tool calls; delegate longer probe chains to a read-only subagent returning conclusions plus minimal evidence rows, keeping raw outputs out of the interview context. Probe conclusions take the channel of their evidence source (a delegated repo walk is `from-code`, not `from-research`). Every settled requirement carries one of the six channels. Treat every substantive user answer as a claim, and pressure-test the ones that carry implementation risk.

## Invariants (every turn)

- Session state: persist four files under repo-root `.ultimateinterview/<slug>/` (kebab-case slug) - `ledger.json` (evidence ledger, the scoring source of truth), `protocol.json` (what the interview has executed), `questions.json` (scored candidates), append-only `transcript.md` (`references/transcript-format.md`). After each answer, ONE bookkeeping pass - a single `session_update.py` delta covering all file updates and ending with the dashboard line; mid-walk discoveries fold in. Never quote file contents back - the dashboard line is the only echo. A protocol step not recorded in `protocol.json` did not happen. Schemas, crash/resume, language, environment: `references/state-files.md`.
- After context summarization or a long gap, reload `ledger.json`, `protocol.json`, `questions.json`, and the transcript tail as the source of truth (conversation memory is not trusted); determine the phase from `protocol.json` flags and re-read that phase's references before continuing.
- Evidence channels (closed vocabulary; scripts reject anything else): `from-code`, `from-docs`, `from-user`, `from-research`, `from-scenario`, `assumption`. Channels name the evidence source, not the elicitation; two same-channel statements are never a triangulation pair; `assumption` never counts as a channel. Semantics and edge cases (`from-user` even when scenario-prompted, what `from-scenario` requires): `references/state-files.md`. Record channels on every entry you settle; the script counts distinct channels.
- Ledger entries carry a unique `id`, `ambiguity_score` (`0` settled, `1` assumption accepted, `2` implementation could branch, `3` unsafe to code), `impact_weight` (`1`/`2`/`3`/`5` = low/moderate/high/critical), `status` (`Draft`, `Triangulated`, `Contested`, `Blocked`, `Accepted`, `Deferred`), `evidence_channels`, and `origin` (the surfacing mechanism, for postmortem attribution; value set in `references/state-files.md`).
- Budget: an interaction is one round-trip to the user - it counts user interruptions, not question marks. The costing table (which events cost 1 vs 0, the two-free-pressure-follow-ups-per-thread rule) lives with the typed events in `references/state-files.md`. NEVER hand-set counters: pass the typed `event` and the script computes them all.
- At budget, stop ordinary questioning: present the remaining gaps, ask the user to defer them (owner/date) or extend - never silently continue (`--next` fires this obligation).
- While interviewing, a turn's visible output is the dashboard line plus the question (or batch) - no unsolicited narrative synthesis (rule-mandated outputs are exempt).
- Self-referential interviews (subject is this skill or its own files): the skill's prose is `from-docs`, never ground truth; running the scripts and tests is the `from-code` channel; fresh-context gates must go to a subagent (self-auditing your own program is circular).
- Subagent naming (cross-vendor routing): dispatch every subagent this skill spawns (fresh-context reviewer, fresh-implementer test, the advisory lanes, slim contrarian review) through the harness task tool with the agent name `critic` - a read-only role. Keep each lane's functional role in its per-task prompt, never the agent name, so a `task.agentModelOverrides["critic"]` binding routes these read-only lanes to a cross-vendor model without changing the interview model.

## Deterministic Helpers

Never calculate script outputs mentally - use the scripts whenever state is representable as JSON.

- `scripts/session_init.py <repo-root> <slug> --entries '<json array>'`: ORIENT initializer - already-valid state files, fresh-suffix rule, `.gitignore` coverage.
- `scripts/session_update.py <session-dir> --delta '<json>'`: the whole bookkeeping pass in ONE validated call - typed events/counters, entry changes, checkpoint/lens state, atomic transcript/history writes, and reviewed-contract digest - then emits dashboards. PREFERRED writer; delta schema: `references/state-files.md`.
- `scripts/session_status.py <session-dir>`: read-only dashboards + `Due Now` + `interview_converged`. `--next`: deterministic next-action routing - obey like Due Now; its critical-path call is a floor. `--gate`: composite implementation gate over ledger/protocol readiness, handoff coverage and sections, decidable predicates, and host-resolvable verification commands; exit 1 blocks.
- `scripts/ambiguity_ledger.py`/`scripts/protocol_state.py`: per-file checks. `scripts/question_score.py`: the converge formula (`references/interview-loop.md`). `scripts/transcript_check.py`: transcript↔protocol consistency (pre-handoff, post-resume). `scripts/lessons.py`: Fired/Caught + auto-retirement. All fail closed - follow the one-line error.
- `scripts/handoff_coverage.py <session-dir>`: pre-handoff traceability gate - every settled weight-`2`+ non-deferred entry id must be cited in Part 1 (fail-closed, exit 1). The deterministic floor under the behavior-fidelity rule (`references/handoff-sequence.md`): proves no settled entry vanished untraced; a human still confirms each cited REQ reproduces the entry's FULL enumerated behavior (synthesis-loss).
- `scripts/verification_lint.py` and `scripts/predicate_lint.py`: focused post-draft diagnostics. Their checks are composed fail-closed by `session_status.py --gate`.

Handoff readiness is the script's blocker-based `handoff_ready` verdict - do not re-derive it (exact definition in `references/handoff-sequence.md` §Gates); the percentage is informational, never a gate.

The stop condition (not implementation readiness): the combined `interview_converged: yes` line - `handoff_ready` while protocol blockers are empty or only the untested build contract. Only `--gate` may emit `implementation_ready: yes`.

Run scripts from the skill directory or with absolute paths (e.g. `uv run scripts/session_status.py --format markdown <session-dir>`).

## Per-Round Loop

1. `Process the answer` with Answer Handling (below), then the one bookkeeping pass; end it with the dashboard line: residual + top 1-3 drivers (recompute after every answer and material repo/research discovery; `residual = sum(impact_weight * ambiguity_score)` over active gaps; deferred gaps are excluded but listed under deferred risks with owner/date).
2. `Obey Due Now / --next` before any scored question: `--next` resolves obligations in fixed order (residual-history lag, budget exhaustion, overdue sweep, stagnation escalation - a contrarian probe or checkpoint replaces the scored question; the script vetoes false-stagnation when a rising residual comes from newly found gaps). Take its first action; escalate beyond it, never skip it. Increment `due_now_corrections` when an obligation preempts your planned action. Sweep, checkpoint, contrarian methods: `references/interview-loop.md`.
3. `Diverge when armed`: re-run an affected lens when an answer contradicts prior evidence, a new module, stakeholder, or lifecycle state appears, or a sweep finds an unvisited track. End enumeration only after two consecutive `sweep_result: dry` events; `new-gaps` must add a ledger entry with `origin: sweep` and resets the streak. Technique routing: `references/interview-loop.md`; methods: `references/lenses.md`.
4. `Select by criticality`: a gap is `critical-path` when it touches a weight `3`/`5` entry, would settle a score `3` gap, genuinely branches the implementation, contradicts existing evidence, or would narrow scope. Critical-path gaps get the top-ranked question, one at a time, full adaptivity - except up to three independent ones MAY share one structured multi-question round-trip (conditions in `references/interview-loop.md` §Smart-default batches). Everything else (weight `1`/`2` confirmations, preferences, repo-suggested defaults) accumulates into a smart-default batch; never batch a critical-path gap, and never batch while one is open and askable. Flush rule: when no critical-path gap is askable and batchable gaps are pending, send the batch even below 3 items; always flush before the pre-handoff checkpoint.
5. `Checkpoint triggers`: run a falsification checkpoint as the first user interaction on context-first entry; at a sweep when several pending questions score low and one synthesis is cheaper; on stagnation escalation; and mandatorily once before the readiness gate and handoff. Pattern and fatigue rules: `references/interview-loop.md`; crediting: Checkpoint Invariants below.
6. `Contrarian minimum`: at least one contrarian probe per interview before handoff, independent of stagnation; pair it with the pre-handoff checkpoint if no earlier moment was natural. Log its outcome even when it changes nothing.
7. `Score and ask`: rank candidates with `scripts/question_score.py`; regenerate `questions.json` through the same `session_update.py` delta only when the gap set changed (a gap opened, a critical-path gap settled, or 3+ rounds since last scoring) - otherwise reuse the previous ranking minus answered items. Prune questions the repo can answer, duplicates, non-implementation-affecting ones, and low-confidence speculation. Ask every scored choice and batch through the harness's structured-question tool - its built-in Other is the always-open escape hatch - defaulting to it for any enumerable answer space, the falsification checkpoint included. Evidenced options may carry a recommendation; invented ones are labeled suggestions, never recommended. Stay UI-less only for inherently open narration - the brain-dump invitation and story-eliciting pressure/checkpoint follow-ups. Full shaping (scenario-over-abstract, option wording) and checkpoint rendering: `references/interview-loop.md`. After sending the question, dispatch background advisory lanes (`references/interview-loop.md` §Advisory lanes) so findings are ready when the answer lands.
8. `Stop`: when the stop condition (Deterministic Helpers) is met, the next action - same turn - is ENDGAME (`references/handoff-sequence.md`), not another summary.

## Answer Handling

Between asking a question and rescoring the ledger, process every answer with these rules:

1. `Pressure where it pays`: an answer must survive one pressure follow-up before its gap can drop below score `2` when the answer settles a weight `3`/`5` gap, collapses a score `3` gap, contradicts `from-code`/`from-docs` evidence, narrows scope or artifact class, or is hedged ("probably", "I think", "usually"). Corroboration by a second evidence channel counts instead of a follow-up. Outside those triggers - low-weight preferences, confirmations of repo-derived defaults, quick picks - settle directly with the evidence channel recorded. Follow-up techniques (example, assumption, boundary, scenario): `references/interview-loop.md` §Pressure follow-ups. Script-enforced: settling a weight-3+ from-user entry below `2` on a single channel needs the op's `pressure` token (`survived`|`second-channel`|`exempt:<reason>`).
2. `Stay deep`: do not rotate to the next scored question while the current answer is vague. Stay on the thread until the answer names a trigger, boundary, or observable evidence - within the free-follow-up cap (Invariants); a thread still vague past the cap records its entry at the current score and returns to the queue.
3. `Preserve nuance`: when an answer carries reasoning, constraints, or scope statements beyond the direct decision, decompose it into separate ledger entries (decision, reasoning, user-stated constraints, user-stated non-goals). If you compressed a rich answer, show the decomposition and ask whether anything was lost.
4. `Collide evidence`: if a user claim contradicts `from-code` or `from-docs` evidence, do not silently pick one. Present both sources, mark the entry `Contested`, and ask which governs.
5. `Triangulate critical entries`: an `impact_weight` `5` entry at score `0` or `1` requires two evidence channels, or explicit single-source `Accepted` status backed by one real channel. The script enforces this boundary.
6. `Guard intent`: if a candidate option or recommendation would narrow a previously settled scope, artifact class, or outcome - or expand it beyond the stated need - label it `scope reduction` or `scope addition`, never mark it recommended, and require an explicit user decision.
7. `Pivot protocol`: when an answer changes the artifact class or outcome, re-run the framing challenge against the new problem statement, re-scan lens triggers, re-check depth/budget fit, and mark superseded entries in the same bookkeeping pass.

## Checkpoint Invariants

- Book every checkpoint with the `checkpoint_confirm` delta (`{ids, fatigue}`): tag the covered ledger id(s); on a decisive, non-fatigue confirmation it credits `from-user` corroboration on single-channel covered entries (can complete weight-5 triangulation); a fatigue-flagged reflexive "all correct" is never credited. Crediting and counters land mechanically.
- Feed every correction back into the ledger as a new or `Contested` entry. A correction to a statement you believed settled is an unknown unknown surfacing - flip the affected lens back to `triggered` in `protocol.json` and re-run it before returning to scored questions.
