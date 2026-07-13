# Ultimateinterview Deterministic Readiness Hardening

## Why this change exists

A brownfield requirement cannot be proven free of uncertainty. The practical target is narrower: expose every unresolved uncertainty that could change implementation, preserve the evidence behind settled decisions, and block coding when the remaining contract is not testable or safely reversible.

The hardening therefore separates two claims:

- `interview_converged`: the question-discovery process has no remaining blocker except completing and testing the Build Contract.
- `implementation_ready`: the current Build Contract, and not an earlier draft, passes the composite deterministic gate.

Only the second claim authorizes implementation. Neither claim says uncertainty is zero.

## Thin skill architecture

The runtime prose stays deliberately small. `.agents/skills/ultimateinterview/SKILL.md` routes phases, establishes invariants, and tells the agent when to load focused references. Mechanics that can be computed are scripts instead of prompt instructions:

| Layer | Responsibility |
| --- | --- |
| `SKILL.md` | Phase routing, evidence rules, user-interaction policy, stop semantics |
| `references/` | Method detail, schemas, handoff sequence, examples |
| `session_init.py` | Atomic creation of a valid four-file session generation |
| `session_update.py` | One validated answer-to-state transition, including counters and history |
| `session_status.py` | Read-only status, next-action routing, and composite gate entry point |
| `implementation_gate.py` | Pure evaluation of ledger, protocol, contract, predicate, and verification readiness |
| focused linters | Coverage, verification-command, predicate, transcript, and postmortem checks |
| regression fixtures/tests | Positive and negative controls for stable verdicts and crash recovery |

This keeps judgment in the interview method and moves repeatable accounting, validation, and transitions into deterministic code.

## State and crash invariants

Every session persists four source-of-truth files: `ledger.json`, `protocol.json`, `questions.json`, and append-only `transcript.md`.

- Initialization is staged and renamed as one directory generation. A process killed mid-initialization leaves no half-valid public session and a retry can complete safely.
- Updates take a session lock and journal the previous generation before replacing state files. A later canonical status or update command recovers an interrupted commit before reading it.
- One answer maps to one `session_update.py` delta. Event costs, pressure counts, residual history, dry-sweep history, checkpoint invalidation, and contract-review digests cannot be hand-set.
- A material ledger change clears an omitted question queue, resets the two-dry-sweep proof, invalidates the post-change checkpoint, and invalidates fresh-review evidence. Known replacement questions may be committed in the same delta.
- The helpers require POSIX `fcntl` locking. Unsupported hosts fail closed instead of silently losing serialization.

## Readiness model

The composite implementation gate rejects a session when any of these remain:

1. An active high-impact ambiguity, contested fact, invalid deferral, or insufficiently evidenced critical decision.
2. An incomplete protocol: an undecided lens, fewer than two consecutive dry sweeps, no contrarian probe, no post-change checkpoint, or a stale/unreviewed Build Contract.
3. Missing traceability from settled weight-2+ decisions into Part 1.
4. Missing or empty contract sections, unresolved placeholders, malformed tables, non-measurable quality bars, incomplete rollout/recovery, or verification that lacks both a test and a real changed-surface check.
5. Acceptance predicates that name categories but not observable triggers, boundaries, or outcomes.
6. Verification commands that rely on shell wrappers, environment assignments, `eval`, or command heads that cannot be resolved on the current host.
7. Fresh-implementer findings whose disposition remains unresolved, or a review digest that no longer matches the raw current Part 1, including fenced content.

`session_status.py` reports interview state. `session_status.py --gate` composes all readiness checks, returns exit `1` on any failure, and is the only surface allowed to emit `implementation_ready: yes`.
## Postmortem evidence model

Postmortem verification is a separate, after-implementation contract. A `pass` claim for an executable test or real-surface verification row requires a matching `CAPTURED-OUTPUT` projection in schema-v4 `evidence_bundle.json`; capture first, then regenerate the final bundle. Missing captures are deterministic `verification-execution:` violations, while old v3 bundles degrade to precise input errors rather than tracebacks.

Reward-hacking checks deliberately split advisory detection from enforceable consistency. `audit_scan.py` may identify test/doc-only changed paths or fulfilled support mappings, but those heuristic candidates never fail `postmortem_lint.py` by themselves. The lint only checks the human-entered Reward-Hacking Review: gaming flags require `confirmed-gaming`, and confirmed gaming must be reported as `divergent-implementation`.

A green `postmortem_lint` therefore proves execution provenance and human-entered self-consistency only. It does not prove that no gaming occurred or that the implementation semantically passed its specification.

## Enumeration and pressure semantics

Unknown-unknown discovery has explicit evidence rather than a single “done” flag:

- Every completed lens records its typed artifact.
- Enumeration requires two consecutive dry sweeps. A sweep that discovers a gap must add an entry with `origin: sweep` and resets the streak.
- Deferred risks discovered by a sweep remain valid when they record an owner and decision date; deferral does not erase their discovery origin.
- Free pressure follow-ups are keyed by `pressure_parent`. The first two follow-ups on a thread cost zero; a third is rejected and must become a scored interaction. This prevents callers from resetting the allowance by changing question text.

## Regression contract

The fixture sweep includes a synthetic `ready-minimal` positive control and four historical negative/legacy controls. It pins coverage, ledger readiness, protocol readiness, convergence, implementation readiness, gate exit codes, and postmortem verdict classes. Each child process has a timeout; live sweeps distinguish recorded sessions, unrecorded completed sessions, and in-progress sessions without a handoff.

Run the verification from `.agents/skills/ultimateinterview/`:

```bash
uv run --with pytest --with typer --with pydantic --with rich python -m pytest scripts
uv run --with ruff ruff check scripts/atomic_write.py scripts/implementation_gate.py scripts/session_init.py scripts/session_status.py scripts/session_update.py scripts/regression_check.py scripts/test_atomic_write.py scripts/test_deterministic_helpers.py scripts/test_predicate_lint.py scripts/test_regression_check.py scripts/test_verification_lint.py
uv run --with basedpyright --with typer --with pydantic --with rich basedpyright --level error scripts/atomic_write.py scripts/implementation_gate.py scripts/session_init.py scripts/session_status.py scripts/session_update.py scripts/regression_check.py
uv run scripts/regression_check.py --format json
```

At the time of this hardening, the deterministic test suite reports `284 passed`, the captured fixture sweep reports five passing sessions and zero regressions, and the changed production scripts pass Ruff and BasedPyright. These results establish implementation stability; they do not establish a higher real-world discovery rate. A discovery-rate claim still requires a fresh interview → implementation → independent postmortem cycle on measured projects.

## Migration notes

- Consumers must read `interview_converged` instead of the former ambiguous `ready` field.
- Only the composite gate provides `implementation_ready`.
- Existing sessions may parse but cannot become ready until they record typed lens artifacts, two dry sweep events, a current checkpoint, and a fresh Build Contract review.
- Gate mode deliberately refuses alternate ledger/protocol paths so state from one session cannot be paired with another session's handoff.
- Direct callers of the update helper must supply `sweep_result` for sweep events and `pressure_parent` for pressure follow-ups.
