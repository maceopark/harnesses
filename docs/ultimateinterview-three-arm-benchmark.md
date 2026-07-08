# Three-Arm Spec-Elicitation Benchmark: claudeplan vs codexplan vs todo-cli-app-5

Date: 2026-07-07/08. Council: agent-council (members: agy, codex; chairman synthesis by the
session agent, who also ran an independent drift pass with live probes). Raw member outputs:
`.omo/council-three-arm/{agy,codex}.md`. Briefing: `.omo/council-briefing-three-arm-spec-eval.md`.

## Arms

| Arm | Mode | Spec artifact | Impl | Scope |
|---|---|---|---|---|
| A `claudeplan` | Claude plan mode (3 Q&A rounds, 10 decisions) | `~/.claude/plans/humble-churning-pony.md` (39 REQs) | `claudeplan/` (54 tests) | Standard: CRUD + priority + due + filters |
| B `codexplan` | Codex/OMO work plan (plan-first waves, 3 sanity-checks) | `.omo/plans/codexplan.md` | `todo-cli-codexplan/` (8 tests) | Basic CRUD, Must-NOT: priority/due |
| C `todo-cli-app-5` | ultimateinterview (8+ interactions, 21 ledger entries) | `.ultimateinterview/todo-cli-app-5/handoff.md` (15 REQs, Build Contract) | `todo-cli-app-5/` (23 tests) | CRUD + list-completed, dateless |

Caveat: Arm A's near-zero drift is confounded — planner == implementer == same session/context.
Arms B and C handed off to fresh-context executors. Drift risk scales with planner→executor
context distance; A's cleanliness says little about its plan's standalone quality.

## Headline finding

**All three modes escaped in the same failure class — undefined predicates — and only Arm C
detected its own escapes.** Confirmed instances:

- **Arm A (live-probed, CONFIRMED)**: store validation uses `isinstance(x, int)`, so
  `"next_id": true` passes (bool is int in Python) → `Added todo True`, writes `"id": true`
  into the store. REQ-33 said "mistyped keys" without a deciding rule; 54 tests never probed it.
  Also unpinned: `version < 1` handling, missing `created_at`/`completed_at` on load, and
  newline/control chars in titles (live probe: multi-line title accepted, breaks one-row format).
- **Arm B**: plan's exit taxonomy says "invalid id value" = domain error exit 1; implementation
  splits the undefined predicate — non-integer token → usage exit 2, signed non-positive → exit 1
  (`cli.py:98-129`) — and **locked the contradiction into tests** (`test_usage_errors_return_2`).
  Also invented on load: duplicate-id rejection, `id < next_id`, `created_at` parseability.
  `requires-python >=3.12` chosen with no floor in the plan.
- **Arm C**: postmortem's own E1 (`next_id` predicate invented, logged in decisions.jsonl) and
  E2 (version floor `>=3.11`, unlogged). Council added two predicate notes already recorded in
  the postmortem but not counted as escapes: canonical id form (`str(int(raw)) != raw`) and
  control chars = C0+DEL only.

Second headline: **drift observability is itself a property of the mode.** Arms A/B have no
audit loop — their drift was first discovered by this external council, and in B's case the
contradiction was test-institutionalized (TDD locks in whatever reading the implementer takes).
Arm C's cost (21 ledger entries vs 10/3 decisions) buys not just spec precision but the
postmortem machinery that detects and quantifies its own escapes (17/17 fulfilled + 2 escapes,
89.5%). A large share of ultimateinterview's cost is buying auditability, not just spec text.

## Drift summary (agreed across evaluators)

| Arm | D1 unplanned | D2 missing | D3 contradiction | D4 silent decision |
|---|---|---|---|---|
| A | temp-cleanup extra | bool-as-int leak vs REQ-33 intent; created_at unvalidated | sort-key literal (`date.max` vs `""`, equivalent) | version<1, column widths, temp naming |
| B | load-time schema strictness beyond plan | `tests/test_domain_contract.py` never created; evidence files renamed (`task-N-codexplan.md` → ad hoc `codexplan-*.txt`); `--help` untested in pytest | non-integer id → exit 2 vs plan's exit 1 | version floor 3.12; title strip; id-syntax split |
| C | — | — | — | E1 (logged), E2 (unlogged), canonical id form, C0-only control chars |

## Spec quality (postmortem lens; member disagreement noted)

- **Decidable predicates**: members split on B (agy 9, codex 6) — agy credited the typed JSON
  schema, codex weighted the observed "invalid id value" accident. Chairman sides with codex:
  the criterion is decidability *as evidenced by outcomes*, and B's predicate demonstrably
  failed. A ~7 (bool leak), B ~6, C ~8.
- **Testability**: A 9, B 7, C 9 (both members).
- **Edge/misuse coverage**: C 9 > A 8 > B 6. C's misuse lens (256-char cap, control chars,
  operation × data-state matrix) caught what A missed entirely (newline titles).
- **Non-goals/guardrails**: B 10 (Must-NOT block is the single best artifact any arm produced),
  C 9, A 7.
- **Verification executability**: all ~8; C's matrix strongest but `python` vs `python3`
  portability failed on host (already sealed by verification_lint in 15차).
- **Traceability**: C 10/10 unanimous (REQ → gN source ids → ledger/transcript/decisions);
  A 7 (decisions exist, uncited per-REQ); B 5.

**Verdict (unanimous): Arm C produced the best spec for its scope**; B contributed the best
guardrail artifact; A the broadest REQ surface but with a self-implementation confound.

## Improvement candidates for ultimateinterview

Already implemented (15–17차) — council independently re-derived these, confirming their value:
predicate gate ("invalid X" requires deciding predicate), verification_lint (command-head PATH
check), version-floor rule in Implementation Constraints, postmortem_lint / self-audit block.

New, actionable (deduped against current skill state):

1. **Type-coercion predicates into the predicate gate + regression fixtures.** The gate reacts
   to words like "invalid/corrupt"; Arm A's bool-as-int leak shows type predicates escape it
   ("mistyped" had no deciding rule; bool/int coercion, version<1, missing-field policy).
   Extend the gate's noun list (id, version, schema, type) and require accepted/rejected
   example pairs. Add this benchmark's four cross-arm cases (A bool-int, A version<1,
   B invalid-id split, C canonical-id form) as `regression_fixtures/` cases for
   `regression_check.py` (17차 harness).
2. **REQ-keyed test naming contract (from Arm A).** Handoff instructs the executor to name
   acceptance tests `test_reqNNN_*`; postmortem's coverage mapping (handoff_coverage.py) then
   becomes mechanical REQ↔test matching, and unasserted-REQ detection (app-5's §C3 gap list)
   is deterministic instead of inventory-based.
3. **decisions.jsonl coverage check in postmortem.** E2 and the control-char choice were
   unlogged. Add a postmortem step: hunt diff for decision-shaped changes (version floors,
   canonicalization rules, dependency/config pins, error-taxonomy mappings) and diff that list
   against decisions.jsonl; unlogged material choices become findings.
4. **Bind non-goals to negative assertions (from Arm B).** UI has Out-of-Scope sections;
   postmortem does not systematically scan for forbidden capabilities. Add a scope-creep scan:
   each non-goal gets a checkable negative (no flag exists, no import exists, command exits 2).
5. **Promised-artifact existence check.** Arm B promised evidence paths and a test file that
   never materialized. Cheap postmortem/verification_lint addition: verify artifacts named in
   the spec/plan actually exist at audit time.

## Follow-up experiment

Arm A's zero-drift is untrustworthy as a mode property. To isolate it, hand A's plan
(`humble-churning-pony.md`) to a fresh-context executor (as UI does) and re-measure drift —
this doubles as the deferred half-2c (blind-rebuild discovery rate) partial substitute.
