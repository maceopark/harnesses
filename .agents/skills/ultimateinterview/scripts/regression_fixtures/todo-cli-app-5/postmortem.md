# Postmortem: todo-cli-app-5

Independent audit. The implementing executor (Codex ulw-loop session `todo-cli-app-5-20260707`) had written its own `postmortem.md` — a self-audit scoring itself 17/17 fulfilled, with no lessons fire-tracking, REQ ranges aggregated into single divergence rows, and one informal rate. Per the self-report rule it is preserved as `postmortem.self.md` and treated as evidence, not as an audit; disagreements are reconciled in §Reconciliation below. The auditor of this report did not write the implementation; a fresh-context critic subagent (spec Part 1 + diff only) returned a 63-behavior two-direction inventory that was reconciled into this report — it reclassified one of the auditor's initial escapes back into a quality bar and surfaced one the auditor had missed (§Reconciliation) — and every Verification Command was re-executed first-hand.

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| Working tree (staged adds) | `todo-cli-app-5/{todo.py, tests/test_todo.py, pyproject.toml, uv.lock}` | `implementation.diff` (72 KB) in the session dir |
| Evidence bundle | `evidence_bundle.json`, schema v2, 344,623 bytes (rebuilt by this audit; the executor's v1 bundle was 5.1 MB) | 21 ledger entries, 5 decisions, 34 ulw events, 52 artifacts, 0 warnings, 0 missing |
| Runtime artifacts | `.omo/evidence/todo-cli-app-5/` (red/green pytest, tmux walkthroughs, temp-write red/green, QA outputs) | 2026-07-07 14:08–14:45 |
| Implementer decision log | `decisions.jsonl` — 5 records (3 `legitimate_spec_evolution`, 2 `execution_process_gap`) | 2026-07-07 |

Handoff written: 2026-07-07 13:57. Implementation examined through: working tree at audit time (unchanged since 14:45).

## Divergence Table

Deterministic first pass: `handoff_coverage.py --advisory` → 17/17 material-settled entries cited in Part 1, `coverage_ok: yes`; behavior-fidelity read of each cited entry found no sub-case narrowing → zero `synthesis-loss` candidates.

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 command set + unknown/missing/extra args exit 2 | fulfilled | Part 1 | `todo.py:63-127` (`run`, `require_arg_count`) | verified live: unknown/missing/extra all exit 2, stderr-only |
| REQ-002 dateless not-done default view | fulfilled | Part 1 | `todo.py:67-70` | |
| REQ-003 complete hides + retains; list-completed | fulfilled | Part 1 | `todo.py:72-78,93-104` | |
| REQ-004 stable monotonic int id; duplicate titles | fulfilled | Part 1 | `todo.py:84-91` | duplicate-title walkthrough passed |
| REQ-005 creation-order rendering, no reorder | fulfilled | Part 1 | `todo.py:70,178-181` | |
| REQ-006 fixed output strings + single trailing newline | fulfilled | Part 1 | `todo.py:59,91,104,118,178-181` | live output byte-matched the spec examples |
| REQ-007 add joins args; title validation at add | fulfilled | Part 1 | `todo.py:130-148` | predicate note: "control characters" implemented as C0+DEL only — C1 controls (e.g. U+0085) pass; title stored unstripped. Spec named the category, not the set |
| REQ-008 complete id errors incl. already-completed message | fulfilled | Part 1 | `todo.py:93-104,151-165` | predicate note: id canonical form (`"01"`, `"+1"`, `" 1"` rejected via `str(int(raw))!=raw`) is implementer-chosen under "malformed" |
| REQ-009 delete any existing task; errors exit 2 | fulfilled | Part 1 | `todo.py:106-118` | |
| REQ-010 fixed `$HOME/.todo-cli-app-5.json`; create parent dir on save | fulfilled | Part 1 | `todo.py:184-185,263` | verified live with nested missing `HOME` |
| REQ-011 schema `{next_id, tasks[]}`; ids never reused | fulfilled | Part 1 | `todo.py:201-234,84-91` | |
| REQ-012 unknown root/task keys preserved on round-trip | fulfilled | Part 1 | `todo.py:223-227,252-257,302-314` | preserved at both root and task level |
| REQ-013 invalid readable store → exit 3, no overwrite | fulfilled | Part 1 | `todo.py:201-257` | see escape E1 for the `next_id` predicate the spec never defined |
| REQ-014 unreadable/corrupt/non-UTF8 → exit 3, no overwrite | fulfilled | Part 1 | `todo.py:188-198` | `OSError` catch also covers permission-denied |
| REQ-015 atomic save; failure = stderr, nonzero, no partial store | fulfilled | Part 1 | `todo.py:260-299` | executor's own review found the pre-`os.replace` temp-write failure case, locked it red→green (`temp-write-red/green.txt`); temp-residue cleanup is in-spec via the quality bar's "never a partial JSON file" wording — this audit initially miscounted it as an escape and the fresh-context inventory's quality-bar mapping corrected it |
| Quality bar: store durability (temp+rename, no partial file) | fulfilled | Part 1 Quality Bars | `todo.py:260-299` + monkeypatched failure tests | fsync before rename exceeds the bar |
| Quality bar: stdlib-only runtime | fulfilled | Part 1 Quality Bars | `todo.py:1-10` imports; `pyproject.toml` (pytest dev-only via uv) | verified by inspection |
| E1: store-level `next_id` validity predicate (`next_id` > every existing id; bool rejected) | escaped-requirement | REQ-013 names "invalid `next_id`" with no deciding rule; ledger g17 likewise | `todo.py:219-221,231-234` | decision #3 documents the forced invention; entailed-by-monotonicity is one reading, but `next_id == max(id)` rejection is observable behavior the spec cannot falsify |
| E2: runtime version floor `requires-python = ">=3.11"` | escaped-requirement | Implementation Constraints pin "Python 3 stdlib runtime only" (g5) with no version floor | `pyproject.toml` `requires-python`; `todo.py` uses 3.10+ syntax (PEP 604 unions, `TypeAlias`) | the implementer chose the floor and never logged it in `decisions.jsonl` — an unpinned compatibility predicate, plus a decision-log discipline gap |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Weight | Evidence (diff hunk + ledger/transcript line or absence) |
| --- | --- | --- | --- | --- |
| E1: `next_id` must exceed every existing task id (and not be bool) or the store is rejected exit 3 | controlled-language | enumeration-miss | 1 | `todo.py:219-234`; ledger g17 lists "invalid `next_id`" among reject cases but defines no predicate; transcript interaction 6-7 accepted the scout batch without pinning it; `decisions.jsonl` #3 records the implementer inventing the rule |
| E2: Python version floor `>=3.11` declared in pyproject | controlled-language | enumeration-miss | 1 | `pyproject.toml` `requires-python`; ledger g5 settled "Python 3, stdlib only" with no floor; transcript interaction 8 batch-accepted g5 without a version question; `decisions.jsonl` carries no version-floor record (an unlogged unforced decision) |

Both escapes are unpinned-predicate misses inside categories the interview did enumerate — E1 a reject-rule without a deciding predicate, E2 a compatibility constraint without a version floor. Same shape as the app-3/app-4 escapes (durability, time seam), one severity notch smaller. Neither warrants a new lessons-store row: the generalized rules were folded into the skill body this same audit (controlled-language predicate gate; version-floor line in the Implementation Constraints rule) — see §Lessons.

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none deferred in the handoff | n/a | no | n/a |

## Verification Execution

All Verification Commands were re-executed by this audit. Spec portability defect: every `python` invocation required substitution to `python3` (host has no `python`; no global `pytest`) — exactly decisions #4/#5. The new `verification_lint.py` reproduces this finding deterministically on this handoff (`python: MISSING on this host`).

| Verification command / check | Ran? | Result |
| --- | --- | --- |
| `python -m pytest` (unit/behavior suite) | adapted: `uv run python -m pytest` | pass — 23 tests |
| Real-surface absent-store walkthrough | adapted: `python3` | pass — `No tasks.` / `No completed tasks.`, exit 0 |
| Real-surface valid-store walkthrough | adapted: `python3` | pass — add/list/complete/list-completed/delete byte-matched |
| Real-surface invalid-store walkthrough | adapted: `python3` | pass — exit 3, stderr `error: `, corrupt file unchanged |
| User error matrix (malformed/nonexistent/already-completed/unknown/missing/extra/invalid title) | yes | pass — all exit 2, stderr-only; already-completed message verbatim |
| Operation × data-state matrix (absent/valid/invalid × ops + unknown op) | yes | pass — absent initialized-as-empty, invalid exits 3 without overwrite, unknown op exits 2 |
| Quality bar: durability (simulated save failure) | yes (pytest monkeypatch + executor red/green artifacts) | pass — old store or no store, never partial; temp cleaned |
| Quality bar: stdlib-only runtime | yes (import inspection) | pass — stdlib imports only; pytest is dev-only |
| REQ-014 permission-denied unreadable store (audit addendum) | yes (live: `chmod 000` on store) | pass — exit 3, stderr `error: could not read todo store`, file unchanged |

Test-suite coverage gaps (fresh-context inventory §C3 — implemented and audit-verified, but unasserted by pytest): parent-dir creation on save and permission-denied reads (both verified live by this audit), several REQ-013 sub-shapes (non-dict root, non-list `tasks`, wrong field types, oversized/control-char stored titles, bool/≤0/≤max `next_id` — only duplicate-id, one bad-title, and missing-`tasks` are pytest-covered), stderr-only/no-success-line assertions on save failure, a stdlib-only import assertion, and the no-path-override negative. These are implementer test-depth choices, not spec violations — the spec's operation × data-state matrix is covered at the walkthrough level.

## Scope Drift / Divergent Implementations

| Item | Class | What the handoff said | What was built | User must re-decide? |
| --- | --- | --- | --- | --- |
| none | — | — | — | no |

Decision-log dispositions (bundle `decisions[]`, walked as first-class): #1 module layout and #2 JSON formatting are inside explicit Decision Boundaries (fulfilled, no row); #3 is escape E1; #4 (uv-managed dev pytest + `uv.lock`) and #5 (`python3` for evidence commands) are `execution_process_gap` — verification-portability defects of the spec, not behavior divergences; both sealed at the rule layer by `verification_lint.py` + the handoff-sequence host-executability rule.

## Reconciliation With The Implementer Self-Report

`postmortem.self.md` (executor-authored) agrees with this audit on: zero scope drift, zero divergence, REQ-015 fulfilled after its red→green fix, runtime footprint clean. It differs where self-audit blind spots predict: it counted 17/17 fulfilled with no escapes (this audit: 2 unpinned-predicate escapes — one visible in the executor's own decision log, one an unlogged decision); it aggregated REQ-001..006 and 007..009 into single rows (denominator 7 rows for a claimed 17); it reported no rates by formula, no failure classes, and never walked the lessons stores. Structural fix applied this audit: the handoff preamble no longer instructs the implementer to run the postmortem, and `postmortem_lint.py` rejects the report shape the self-report used.

Fresh-context inventory reconciliation: the critic subagent (given only Part 1 and the diff) returned 63 substantive behaviors. Agreements: all 15 REQs and both quality bars implemented; nothing contradicts Part 1; error-wording variance sits inside the free-wording decision boundary. Corrections it forced on this audit: temp-residue cleanup maps to the durability quality bar's "never a partial JSON file" (initial escape reclassified fulfilled), and the `requires-python >=3.11` floor surfaced as the second escape. Its remaining UNMATCHED items are observations, not divergences: fsync-before-rename (mechanism inside the delegated durability boundary), best-effort cleanup error-swallowing (double-failure sliver), and uncaught non-TodoError exceptions — including `KeyboardInterrupt`/`BrokenPipeError` — propagating as a traceback with exit 1, an exit class outside the spec's 0/2/3 taxonomy. That last one is a residual product risk for a piped morning CLI (`todo | head`) but nothing was implemented and nothing promised, so no divergence class applies; it is left as a candidate question for a future app iteration. Its "decisions.jsonl not implemented" verdict is a scope artifact — the file exists in the session dir, outside the diff it was allowed to read.

## Lessons Appended Or Updated

| Signal | Lens to trigger | Failure class | Evidence | Date |
| --- | --- | --- | --- | --- |
| none appended — E1 and E2 were generalized into the skill body (one-off rows are not portable): controlled-language predicate gate (audit-checklists + behavior-contract rule + orientation trigger) covers E1; the Implementation-Constraints version-floor rule (handoff-sequence) covers E2. The three pre-existing store rows that fired this run were **kept in staging at 1/1**, not absorbed — a council review judged one closed loop too little evidence to promote to unconditional method | — | — | — | 2026-07-07 |

### Lessons Fire-Tracking

Walked against the stores as they stood at audit start (global store: 5 active rows; repo store: 0). All five fired and caught. Disposition (revised after an agent-council review of this run): the two strong-evidence rows were absorbed into the skill body and retired; the three `1/1` store rows were **returned to active staging** — one closed loop is not enough evidence to become blanket methodology, so they keep eliciting at Orientation and the audit-checklists store-trust gate that verifies them was made conditional (durable/hand-editable stores only).

Anchor caveat: this table predates the bundle-snapshot mechanism (schema v3). It walks the five rows active in the working tree at the real audit start; a bundle re-packed now snapshots the post-revision state (3 active store rows). `postmortem_lint --bundle` therefore validates the three store signals against this table (present as rows 3–5), which is the historically accurate subset — the two absorbed rows are extra, harmless context.

| Store | Row | Signal (truncated) | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md | 1 | free-text input → misuse degenerate enumeration | fired | caught — g3 `origin: lens:misuse`, reason "misuse lens (lesson-triggered)"; → 4/4, absorbed + retired |
| lessons.md | 2 | temporal word → time-boundary falsification | fired | caught — g4 `origin: lens:domain/state`, reason "(lesson-triggered)", Q1 walked the boundary; → 3/3, absorbed + retired |
| lessons.md | 3 | store input-validation → load revalidation decision | fired | caught — g3 "revalidate on load from store", g17 load-time invalid-record rules; → 1/1, kept in staging |
| lessons.md | 4 | file-store path → store-access error surface | fired | caught — g2 parent-dir-create/permission/non-UTF8 → REQ-010/013/014; → 1/1, kept in staging |
| lessons.md | 5 | closed schema + migration non-goal → unknown-field policy | fired | caught — g2/g17 ignore-and-preserve → REQ-012; → 1/1, kept in staging |
| ultimateinterview-lessons.md | - | (repo store: no active rows) | - | - |

Marker-discipline note: rows 3–5 were caught on substance — g2 wrote "from-docs lesson corroboration" instead of the literal `lesson-triggered` token that orientation.md prescribes and the mechanical Caught rule matches on. Counted as caught (the lesson demonstrably produced the entries); interviews should keep the literal token so the credit never needs judgment.

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 17 |
| escaped-requirement | 2 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome (materialized / total) | 0 / 0 |

| Failure class | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 2 |
| scoring-starved | 0 |
| answer-unpressured | 0 |
| synthesis-loss (interview caught it; handoff drafting narrowed/dropped it) | 0 |

Rates — recomputed from the Divergence Table (17 fulfilled, 2 escaped, 0 divergent; 0 synthesis-loss):

- interview-discovery: 17 / (17 + 2 + 0) = 89.5%
- handoff-fidelity: 17 / (17 + 2 + 0) = 89.5% (identical — no synthesis-loss this run)
- weighted (escape rows in the denominator at impact weight; both escapes weight 1): 89.5% / 89.5%

Run trend (raw interview-discovery): app-1 93% → app-2 89% → app-3 86% → app-5 89.5%, with escape severity flattening to weight-1 predicate/residue depth — the enumeration layer is holding; remaining misses live below category level, which is what the new predicate gate targets.
