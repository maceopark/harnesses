# Postmortem: todo-cli-app-4

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| Working tree (untracked) | `todo-cli-app-4/src/todo_cli/{model,storage,cli}.py`, `pyproject.toml`, `tests/test_contract_redteam.py` | full new tree |

Handoff written: 2026-07-06. Implementation examined through: 2026-07-06 working tree. Two-direction inventory delegated to a fresh-context `critic` subagent (self-audit guard: the postmortem runner also ran the interview and the implementation).

## Divergence Table

| ID / Behavior | Class | Spec ref | Impl ref | Note |
| --- | --- | --- | --- | --- |
| REQ-001..015 (add/list/completed/all/complete/undo/delete, ID model, usage, storage, first-run, corrupt, durable write, streams) | fulfilled (15) | Part 1 REQ rows | cli.py / storage.py / model.py | all implemented; verification gaps noted below |
| Quality bars (durability w5, stdlib-only w2, no-latency-bar) | fulfilled | Part 1 | storage.save/load; pyproject | durability + stdlib asserted by tests |
| Decision boundaries (ID/corrupt/durability/transition pinned; layout/wording delegable) | fulfilled | Part 1 | cli/storage | outcomes honored |
| Non-goals (multi-user, dates, edit, concurrency, priorities/tags/search) | fulfilled (held) | Part 1 | no such code | none implemented |
| E1 Trust-on-load: `add` validates titles; loaded titles never revalidated | escaped-requirement | — | cli._validate_title (add-only); storage._task_from_validated_data accepts any str title | w3 |
| E2 Store present-but-unreadable (permission/OSError, non-UTF-8) → exit 3 | escaped-requirement (synthesis-loss) | ledger g14, NOT handoff | storage.load | w2 |
| E3a Write-failure (tempfile/write/fsync/replace) → StorageError exit 3 | escaped-requirement (synthesis-loss) | ledger g14, NOT handoff | storage.save | w2 |
| E3b `save` does not create a missing parent dir → mkstemp fails exit 3 | escaped-requirement | — | storage.save | w2 |
| E4 `TODO_FILE` seam edges: empty→silent ~/.todos.json fallback; no ~/env expansion | escaped-requirement | — | storage.resolve_path | w2 |
| E5 Schema exact-key strictness: extra/missing keys + bool-as-int rejected → forward-compat break vs migration non-goal | escaped-requirement | — | storage._store_from_validated_data/_task_from_validated_data | w2 |
| E6 Input-grammar precision: id leading-zeros ok, ASCII-digits-only, signs/Unicode-digits rejected; 1024 counted in code points not bytes | escaped-requirement | — | cli._parse_id/_validate_title | w1 |
| E7 Domain-vs-storage error precedence: `add <bad>` on corrupt store → exit 1 (validated before load) | escaped-requirement | — | cli.main | w1 |
| D1 `requires-python >=3.9` but test imports `tomllib` (3.11+) | divergent-implementation | Part 1 "Python 3" | pyproject vs tests | w1; declared floor contradicts effective test floor |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Evidence |
| --- | --- | --- | --- |
| E1 loaded titles never revalidated; a hand-edited newline title breaks the `<id>\t[ ]\t<title>` list contract | domain/state | enumeration-miss | cli._validate_title runs on `add` only; storage validates title is `str` but not content. Ledger g4 covered add-time only; load-time trust never enumerated in ledger or transcript. |
| E2 permission-denied/unreadable/non-UTF-8 store → exit 3 | domain/state | **synthesis-loss** | Ledger g14 REQ literally says `3 storage error (corrupt/permission/write failure)`; handoff REQ-013 rendered only "invalid JSON OR schema-invalid". Interview enumerated it; Build-Contract drafting compressed it away. |
| E3a write-failure → exit 3 | domain/state | **synthesis-loss** | Same g14 entry named "write failure"; handoff has no write-failure REQ row (REQ-014 is success-path only). |
| E3b no parent-dir creation on save | domain/state | enumeration-miss | storage.save uses `tempfile.mkstemp(dir=path.parent)`; never discussed in ledger/transcript. |
| E4 `TODO_FILE` empty/relative/unexpanded semantics | domain/state (misuse footgun) | enumeration-miss | The seam was named (g9) but its edge values were not; empty `TODO_FILE` silently writes to the real `~/.todos.json` — an isolation footgun. |
| E5 unknown/extra-field policy = reject (exit 3) | domain/state | enumeration-miss | `set(data) != {...}` rejects any extra key; with migration a non-goal, every future field is a breaking change. Never enumerated. |
| E6 id-token lexical grammar + char-count unit | controlled-language | enumeration-miss | `_parse_id` accepts `001`, ASCII digits only; 1024 via `len()` (code points). Spec said "non-integer/non-positive" and "≤1024 chars" without a grammar/unit. |
| E7 title-validation precedes store read | controlled-language | enumeration-miss | main validates title before `resolve_path/load`; spec pinned usage-before-read but not domain-before-storage precedence. |

No escape was traceable to a transcript answer recorded wrong (checked `transcript.md`); E2/E3a were correctly recorded in the ledger and lost only at the handoff synthesis step.

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| (none) | — | — | Handoff had "Deferred Risks: None open." Concurrency was an explicit non-goal, not a deferral. Nothing to track. |

## Verification Execution

- `uv run pytest -q` → **51 passed** (re-run by the leader; reproduces the gate result).
- Verification gaps in an otherwise-fulfilled contract (from the fresh-context inventory): REQ-008 delete-of-a-done-task untested; REQ-010 partial usage coverage (no-title add, extra args on read cmds, undo/delete id errors); REQ-011 default `~/.todos.json` path + raw pretty-print/trailing-newline/non-ASCII bytes not asserted; REQ-013 not every schema branch, not across every subcommand; REQ-014 same-dir-temp/fsync not directly asserted (only the replace-failure outcome); REQ-015 CLI write-failure stream/exit path not verified. Notably the E2/E3 storage-error surfaces are also unverified — the same behaviors the handoff omitted.

## Scope Drift / Divergent Implementations

| Item | Class | Handoff said | Built | User must re-decide? |
| --- | --- | --- | --- | --- |
| D1 Python floor | divergent-implementation | "Python 3, uv-managed" | `requires-python >=3.9` but tests need `tomllib` (3.11+) | no — internal consistency fix (raise floor to >=3.11 or drop the tomllib test dep). Not a reversed user decision. |
| E1 trust-on-load (optional follow-up) | escaped, not divergent | silent | loaded titles trusted | recommended decision, not a gate: should a hand-edited/invalid-content store be rejected on load, or trusted? |

No `divergent-implementation` reversed a decision recorded in the handoff, so no formal re-confirmation gate is raised.

## Lessons Appended Or Updated

Fire-tracked (signal appeared this interview AND its lens produced a `lesson-triggered` ledger entry → Fired+Caught), global store `~/.gjc/agent/skills/ultimateinterview/lessons.md`:
- "free-text user input → misuse" → 3/3 (caught via g4)
- "closed operation set → misuse" → 2/2 (caught via g2/g3)
- "temporal word → domain/state" → 2/2 (caught via g5)
- "file-based store the tool owns → domain/state durability" → 1/1 (caught via g1/g6)
- "date/time behavior + real-surface verification → time-injection seam" → NOT fired (app is dateless; signal absent).

Appended (global store, repo-agnostic):
| Signal | Lens | Failure class |
| --- | --- | --- |
| Spec pins input-validation for an owned store — also decide whether LOADED data is revalidated or trusted (input-only validation lets a hand-edited store violate an output/format invariant) | domain/state | enumeration-miss |
| Spec names a file-store path or store-path override seam — enumerate the store-ACCESS error surface (missing parent dir, permission-denied/unreadable, non-UTF-8) AND the seam's own edge values (empty/relative/unexpanded) | domain/state | enumeration-miss |
| Spec pins a closed on-disk schema + migration non-goal — decide the unknown/extra-field policy (reject vs ignore-and-preserve); strict exact-key rejection makes every future field a breaking change | domain/state | enumeration-miss |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 15 (REQ rows; +quality bars/boundaries/non-goals/constraints all fulfilled) |
| escaped-requirement | 8 (6 enumeration-miss + 2 synthesis-loss) |
| scope-drift | 0 |
| divergent-implementation | 1 |
| deferred-outcome (materialized / total) | 0 / 0 |

| Failure class | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 6 |
| scoring-starved | 0 |
| answer-unpressured | 0 |
| synthesis-loss (not in the skill's taxonomy — see findings) | 2 |

- Raw discovery rate = fulfilled / (fulfilled + escaped + divergent) = 15 / (15+8+1) = **62.5%**.
- Interview-only discovery (excluding the 2 synthesis-loss escapes the interview actually caught) = 15 / (15+6+1) = **68.2%**.
- Weighted (fulfilled REQ weight ≈34; escaped weight 15; divergent 1) = 34 / 50 = **~68%**. Escape profile skews low-weight: 6 of 8 escapes are weight ≤2; the single weight-3 escape (E1, trust-on-load) is the one material product hole.

## Skill Improvement Findings

**ultimateinterview**
1. Headline — ledger→Build-Contract fidelity gap: g14 settled `3 storage error (corrupt/permission/write failure)` yet handoff REQ-013 rendered only "corrupt JSON/schema-invalid", silently narrowing a settled weight-2 behavior. The interview machinery worked; the *synthesis* step lost it, and the fresh-implementer test (Part-1-only) inherited the narrowed contract so it could not catch the loss. Recommended (not edited — postmortems must not modify the interview skill): add a handoff-sequence fidelity check that every settled weight≥2 ledger entry's behavior appears in a Part-1 REQ row or is an explicit non-goal/deferral.
2. The three new lessons above route domain/state to trigger on store-load revalidation, store-access error surface, and closed-schema forward-compat.

**ultimateinterview-postmortem**
1. Failure-class taxonomy has no `synthesis-loss` value; the four existing classes assume the escape was never captured, but 2 of this run's escapes were captured in the ledger and dropped at the handoff. The skill's own rule ("compressed away → answer handling") has no matching failure-class enum. Recommend adding `synthesis-loss` + reporting interview-discovery and handoff-fidelity rates separately.
2. Applied (authorized): the self-audit-guard fresh-context inventory subagent — and any verification subagent — is now dispatched through the task tool with the agent name `critic`, so a `task.agentModelOverrides["critic"]` binding routes it cross-vendor.
