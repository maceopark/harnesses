# Endgame: Audit, Gates, and Handoff

Read when the stop condition is met - or earlier if a readiness-gate trigger below fires or the user asks for independent gating, fresh-context review, or seed readiness. Execute the canonical pre-handoff sequence (flush → dry sweeps/probe → checkpoint + audit → draft/test contract → implementation gate → handoff; detail in §Handoff) in the same turn; do not stop for another summary.

## Draft, Audit, Approval

Use a right-sized three-pass flow. For `minimal` work, Pass 2 and Pass 3 can be a compact self-check unless the user asks for a seed-like handoff.

1. `Draft spec structuring`: turn vague intent into a structured draft, not a final answer.
2. `Seed-readiness audit`: challenge the draft as if another agent were about to implement from it when the readiness gate is triggered.
3. `Restated approval + handoff`: restate the final contract before treating it as a seed-like handoff.

Pass 1 must capture: intent, desired outcome, in/out of scope and non-goals, decision boundaries, success criteria, known code facts, user decisions, assumptions, unresolved gaps.

Trigger the explicit readiness gate when:

- depth is `full`
- any ambiguity score `3` remains near handoff
- a `2` gap would change behavior, touched modules, data, security, rollout, recovery, or verification
- the output will be used as an implementation seed for another agent or team
- the work touches security/privacy, data/schema, irreversible writes, external integration, performance/reliability, or multi-stakeholder workflow
- the user asks for independent gating, fresh-context review, seed readiness, or extra confidence

When triggered, Pass 2 runs the seed-readiness audit questions and Pass 3 (seed-like handoff or triggered gate) restates the contract - both checklists are in `references/audit-checklists.md`; read it when the pass runs.

Ask for explicit approval before telling another agent to build from the spec. If the user asked for a one-shot written spec and cannot approve in the same turn, include the restated approval check and label it as `draft pending approval`.

## Fresh-Context Gate

When the readiness gate is triggered by `full` depth, seed-like handoff, high residual ambiguity, or an explicit user request for independent gating, use a fresh-context reviewer if subagent or delegation tools are available.
Spawn the reviewer through the task tool with the agent name `critic` (a read-only review role); the fresh-implementer-test reviewer below uses the same `critic` agent name. This fixed name lets a `task.agentModelOverrides["critic"]` binding route the review to a cross-vendor model without changing the interview model (see SKILL.md Invariants → Subagent naming).

Give the reviewer only the draft spec, evidence ledger, relevant file paths, and the reviewer checklist from `references/audit-checklists.md`. Do not give it the full conversation or your intended conclusion.

At handoff time, additionally run the fresh-implementer test on the Build Contract: give a reviewer (or yourself, fresh-eyed) only Part 1 of the spec plus repo read access (a real implementer has the repo) - no ledger, no conversation - and ask TWO questions: (1) what would you have to ask before you could implement; (2) which acceptance criterion could you pass WITHOUT the behavior - by editing or gaming the test suite, stubbing the check's target, or satisfying the letter off the real surface? Every (1) item is a gap, except items the repo can answer: those are reviewer misses, not gaps - validate every finding against the repo before folding it back. Every (2) item is re-bound to the observable surface (real command/endpoint, exit codes, persisted state) before handoff - autonomous implementers game verification in practice; an evolution loop on the same target grew explicit anti-gaming clauses only after suffering it. Record `build_contract_tested` in `protocol.json` only after this runs. A mid-loop `implementer-scout` lane (`references/interview-loop.md` §Advisory lanes) never substitutes for this test or sets the flag - it runs early on ledger extracts, not the final Part 1.
Also diff Part 1 against the settled ledger for synthesis-loss: for every settled weight-`2`-or-higher ledger entry, confirm its full enumerated behavior survived into a Part-1 row (not a narrowed subset) and its id is cited there. `scripts/handoff_coverage.py <session-dir>` is the deterministic id-citation floor (it cannot see behavior narrowing); the reviewer/self-audit still reads each cited entry and checks the REQ reproduces every sub-case. A settled entry that enumerated N sub-cases (e.g. `corrupt/permission/write failure`) compressed to a subset is a synthesis-loss escape, not an implementer gap.

Fold accepted reviewer findings back into the ledger and ask the highest-scoring follow-up question. If a fresh-context reviewer is unavailable for a triggered gate, run the same checklist yourself and mark `fresh-context gate: self-audited`. For `minimal` and ordinary `focused` work, do not spawn a reviewer.

Self-referential interviews (the subject is this skill or its own files): the skill's prose is `from-docs` evidence, never ground truth - executing the scripts and tests is the `from-code` channel; fresh-context gates must go to a subagent (a self-audit of your own program is circular).

## Output Contract

End with a spec, not just a summary. Use `references/output-template.md` when the user wants a copy-ready artifact. Include optional sections only when their lens was triggered; otherwise record a skip reason if absence could mislead the implementation agent.

The spec has two parts in a fixed order. Part 1 is the `Build Contract`: the compact, self-sufficient section an implementation agent reads first and can build from alone. Part 2 is the audit trail: everything that justifies the contract. Do not let dashboards, matrices, and logs bury the build decisions.

`Build Contract` (Part 1):

- `Goal`: one sentence
- `Target surface`: files/modules to touch and the expected shape of the change in each
- `Behavior contract`: the settled requirements that change behavior, each with its acceptance criterion (EARS or Given/When/Then - patterns in `references/lenses.md`) and a `Source` cell citing the ledger id(s) it implements. A REQ MUST reproduce the FULL enumerated behavior of its cited entries: when a settled ledger entry lists several sub-cases (multiple error classes, boundary values, states), carry every sub-case or split into multiple REQs - never silently compress a settled entry to a subset (that is the synthesis-loss failure `ultimateinterview-postmortem` measures). A criterion may name a validity/reject category (invalid, malformed, corrupt) only together with the predicate that decides membership - or an explicit decision-boundary row delegating that predicate; a bare category forces the implementer to invent a data rule the spec cannot falsify (app-5: `invalid next_id`, an undefined control-character set, and id canonical form were all implementer-invented). A persisted field named by type carries its coercion boundary for the same reason: an integer field states whether a JSON boolean, a numeric string, or a float is accepted (claudeplan's `isinstance(int)` accepted `true`), and a versioned store pins the below-floor case, not only the above rule
- `Change impact & preservation`: current evidence, preserved invariant, target difference, code surface, acceptance check, and runtime signal for every material source
- `Quality bars`: measurable quality criteria (each a number an implementer can verify: latency, size, freshness, reliability), or one explicit line `no measurable quality bar applies - <reason>`. Each bar carries an impact weight (the ledger `1`/`2`/`3`/`5` scale) so the implementer can order tradeoffs when bars conflict. The slot is mandatory even when the quality lens never triggered - lens-conditional elicitation has missed load-bearing bars in practice.
- `Decision boundaries`: what the implementation agent may decide without asking. Split by kind: structural detail (module layout, parsing library, formatting) is delegable; data-domain invariants (id/key allocation, corruption behavior, retention, durability) are never delegated as such - pin each as an observable outcome with its verification, even when the mechanism stays the implementer's choice. MANDATORY standing instruction (the implementation gate fails Part 1 without a `decisions.jsonl` mention in this section): every decision the spec did not force (a filled gap, a deviation, an assumption) is appended to `.ultimateinterview/<slug>/decisions.jsonl`, one JSON line as it is made. State it inline with the minimal schema (`{"decision","reason",...}`, only `decision`+`reason` required) so Part 1 is self-sufficient - do NOT rely on the implementer opening the postmortem's evidence-bundle schema, and do NOT assume the execution substrate (e.g. lazycodex ulw-loop) records it automatically; it does not. The postmortem reads the file to separate spec gaps from implementation deviations, and records the axis as run-blind when it is absent
- `Out of scope / non-goals`: each non-goal carries a checkable negative assertion where feasible - the observable proof it was not built (a forbidden flag/subcommand exits as unknown, the capability's import/dependency is absent, the endpoint is unserved). Bound negatives let the postmortem scan for scope creep deterministically instead of by eye (`ultimateinterview-postmortem/scripts/audit_scan.py` section C). Experimental, adopted from a plan-mode benchmark's Must-NOT block
- `Implementation constraints`: interfaces, compatibility, migration, rollout. Compatibility names its version floors explicitly - "Python 3" without a minimum lets the implementer pick one silently (app-5 shipped `requires-python >=3.11` without even a decision-log entry)
- `Rollout & recovery`: activation, compatibility/backfill, rollback trigger/action, observation window, and owner; use `N/A - <reason>` only when genuinely indistinguishable from the current local flow
- `Guardrail Compile`: split execution risks before handoff into (a) stop-time verifiable predicates the implementer or downstream loop can check, (b) accepted residuals whose owner/date/disposition is explicit, and (c) fast/pre-action risks that belong to the harness substrate, such as destructive command blocking, permission prompts, agent/tool prompt-injection interception, or irreversible external side effects. Product-level prompt-injection risk is not substrate-owned: when the product consumes untrusted text, keep it in the misuse/security contract with trust boundaries and verifiable acceptance criteria. Natural-language "be careful" entries are not predicates; each predicate needs an executable or objectively observable pass/fail condition such as a command exit status, test result, countable threshold, file-state assertion, endpoint response, or similarly determinate check. Fast risks are surfaced, not simulated as stop-time checks.
- `Verification commands`: the exact tests/commands/observations that prove the change works. At least one check must exercise the real artifact surface - the installed command, running service, endpoint, human handoff, channel transition, or user-observed state - not only the test suite. For command-style artifacts (CLI, API), cover the operation × data-state matrix: every user-facing operation has a defined, checkable outcome for every legal store/data state (absent, valid, invalid), plus one row for an operation outside the specified set (unknown/illegal operation) - no undefined branch. For boundary-spanning work (multiple surfaces, actors, systems, channels, time steps, approvals, queues, or handoffs), add a boundary-depth matrix before or inside Verification Commands: each happy/negative scenario names its intended traversal depth, first valid stop/fail boundary, whether later boundaries should run, and terminal evidence. Do not count an early-stop scenario as end-to-end coverage; require later-boundary evidence when a scenario should pass earlier boundaries and fail or complete downstream. Commands are a contract with the build host: write each in the invocation this host actually resolves (`scripts/verification_lint.py` checks every command head against PATH - app-5 shipped `python -m pytest` to a host with only `python3` and no pytest, forcing mid-run substitutions). Instruct the implementer to name each acceptance test after the REQ it verifies (`test_req001_*` or a `REQ-001` reference) so the postmortem maps requirement→test coverage mechanically instead of hand-inventorying unasserted REQs
- `Deferred risks`: accepted ambiguity the implementer must not silently resolve
- `Fresh-Implementer Test`: reviewer, blocking asks, gameable criteria, every fold-back/rebinding, and the explicit unresolved remainder after disposition

The Build Contract must pass the fresh-implementer test before handoff (see Fresh-Context Gate).
Every settled weight-`2`-or-higher ledger entry that is not a deferral MUST be traceable into Part 1: cite its id in the Behavior Contract `Source` cell, or inline as `(source: <id>)` in Goal / Quality Bars / Decision Boundaries / Out-of-scope / Implementation Constraints, or move it to Deferred Risks with owner/date. This is enforced deterministically by `scripts/handoff_coverage.py <session-dir>` (fail-closed, exit 1 on any untraced settled entry).

Audit trail (Part 2): the full section list, order, and per-section shapes are in `references/output-template.md` - read it when drafting the handoff. Core sections are always present (problem, framing outcome, evidence, ledger, both dashboards, Q&A record, contested log, restated approval check); lens artifacts (domain/state model, viewpoint matrix, goal+obstacle, misuse cases, quality scenarios) appear only when their lens was triggered.

## Gates

Do not declare the spec implementation-ready until the core gates pass:

- no active score `2` or `3` gap remains, and every schema-v1 weight-5 score-`0`/`1` entry has two eligible causal groups or an explicit owner/delegated single-source acceptance; schema v0 retains the historical channel rule
- every `Contested` entry is resolved or explicitly deferred with an owner, and every deferral carries the structured `{"owner", "decision_date"}` form - `session_status.py --gate` enforces both mechanically (exit 1 blocks)
- a falsification checkpoint has run since the last material ledger change; the checkpoint's own corrections (user-authored) and evidence-only build-contract fold-backs (see Handoff) do not re-arm it - a correction that opens a score `2`/`3` gap blocks through readiness instead, and its settling answers re-arm as usual
- the current material revision has an orientation open-world record before lens selection, a breadth open-world record before the dry streak, and at most three surviving model-prior candidates that remain hypothesis-only
- two consecutive breadth sweeps are dry, and the persisted L0-L3 probe decision has a resolved bounded sequence; L2/L3 carry exact scoped authorization, while no divergence/inconclusive contributes zero settlement credit
- every acceptance criterion is testable, observable, or auditable
- verification includes at least one real-surface check (installed command / running service / endpoint), not test-suite-only
- when boundary-depth signals appear, the Build Contract includes a boundary-depth matrix or equivalent rows; early-stop cases and later-boundary cases are not collapsed into the same "negative e2e" bucket
- every verification row that requires manipulating the environment (time/date, network, permissions, clock) names its sanctioned injection seam in the contract - an unnamed seam forces the implementer to mint a hidden one
- the Build Contract's `Quality bars` slot is filled: at least one measurable bar with an impact weight, or the explicit reasoned none-applies line
- the Guardrail Compile slot is filled: every slow/threshold execution risk is either compiled into a determinate predicate or recorded as an accepted residual, and every fast/pre-action risk is named as substrate-owned rather than disguised as a stop-time check
- every unresolved assumption is recorded with an owner or explicit deferral
- every implementation-impacting user decision is settled or deferred
- if the readiness gate was triggered, the seed-readiness audit has either passed, produced follow-up questions, or been explicitly deferred
- `scripts/protocol_state.py` reports `protocol_ready: yes` - it enforces framing, intake, open-world freshness, two dry sweeps, typed probe/checkpoint obligations, typed artifacts for completed lenses, and the fresh-implementer test
- `scripts/handoff_coverage.py <session-dir>` reports `coverage_ok: yes` - every settled weight-`2`-or-higher non-deferred ledger entry id is cited in Part 1 (traceability floor against synthesis-loss); an uncovered entry either belongs in a Part-1 row that was never written or was dropped during Build-Contract drafting
- standalone `verification_lint.py` remains advisory for cross-host diagnostics, but `session_status.py --gate` blocks any command head missing on the current build host
- standalone `predicate_lint.py` remains advisory for diagnosis, but `--gate` blocks every finding; put a category's deciding predicate in the same row rather than relying on adjacent prose

For triggered lenses, also apply the per-lens gate checks in `references/audit-checklists.md` - read them when the gates run.

If a gate fails, ask the one question that would close the highest-risk gap.

## Handoff

When the stop condition is met and the gates pass, create the handoff document instead of asking more ordinary interview questions.

Pre-handoff obligations run in one canonical order: flush pending batches, reach two dry sweeps, run any missing probe, run the mandatory falsification checkpoint and fresh-context audit, then draft and test the Build Contract, run the implementation gate, and hand off.

The build-contract obligation resolves in a fixed sequence: when everything else is ready and only the untested build contract blocks, (1) draft Part 1 from the ledger with stable REQ/VER ids, typed run policies, decision-log path, and probe decision, (2) run the fresh-implementer test, (3) fold every accepted finding back and rerun any invalidated open-world/checkpoint/probe obligation, (4) otherwise record the exact reviewed Part 1 with `session_update.py <session-dir> --delta '{"build_contract_test":{"reviewer":"<name>"}}'`. For schema v1 the writer atomically compiles canonical `build-contract.json`, stores the Part-1 SHA-256 and reviewer, and binds the sidecar's self-digest. Any later Part-1 edit or malformed/stale sidecar invalidates `--gate`; Markdown remains the authoring source.

After drafting `.ultimateinterview/<slug>/handoff.md`, run `scripts/session_status.py --format markdown --gate <session-dir>`. Only `implementation_ready: yes` permits delivery; the v1 gate composes structured evidence, open-world/probe freshness, Contested/deferral checks, Part-1 traceability, semantic affirmative decision logging, current sidecar validity, decidable predicates, and verification commands available on this host. Append the exit-check line to the transcript, run `transcript_check.py`, and fix any failure before delivery.

Write the handoff to `.ultimateinterview/<slug>/handoff.md` (gitignored working state); offer once to copy it to `docs/<slug>-handoff.md` as a durable committed artifact. If no durable file can be written, deliver the handoff in the conversation and say why.

The handoff document must open with the Build Contract (Part 1, fresh-implementer tested) and follow with the audit trail: the final ambiguity and protocol dashboards, the requirements ledger, the condensed Q&A record with pressure-test findings and checkpoint corrections (referencing `transcript.md`), and the contested-resolution log. When the repo keeps a glossary (`CONTEXT.md` or equivalent), also propose glossary updates from this interview's ubiquitous-language findings so the next interview inherits them.

The handoff opens with the consumer preamble (verbatim block in `references/output-template.md`): build from Part 1 only, never silently resolve a deferred risk, log every unforced decision to `decisions.jsonl`, name each acceptance test after the REQ it verifies (`test_req001_*` / `REQ-001`), and stop after implementation - the requester runs `ultimateinterview-postmortem` in a fresh context; the implementer never audits its own escapes (an executor once wrote its own `postmortem.md` scoring itself 17/17 - preserved as a self-report, not an audit).

## Abandonment

If the user abandons the interview at any phase ("enough, just build it"), do not exit empty-handed: write `handoff.md` marked `DRAFT - abandoned at interaction N` carrying the current Build Contract (Part-1 shape in §Output Contract), every open score `2`/`3` gap listed under deferred risks as unresolved, and a one-line list of the gates that were skipped. This is a degraded handoff, not a silent stop - the requester still gets the partial contract and an explicit risk list.
