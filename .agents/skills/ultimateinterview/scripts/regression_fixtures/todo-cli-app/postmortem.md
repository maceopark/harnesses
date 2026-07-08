# Postmortem: todo-cli-app

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| working tree (untracked, pre-commit) | `todo-cli/` — pyproject.toml, todo_cli.py, tests/test_todo.py, README.md; plus `uv tool install todo-cli` | since e4cf1ed (only commit) |

Handoff written: 2026-07-05. Implementation examined through: 2026-07-05 working tree (13 tests green, manual verification passed same session).

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 add one-liner | fulfilled | handoff Part 1 | `cmd_add`; `test_add_and_list` | |
| REQ-002 list open-only, ascending id | fulfilled | handoff Part 1 | `cmd_list` sorts by id; `test_list_ascending_id_and_open_only` | fold-back (id = order source of truth) honored |
| REQ-003 done one-way + retained | fulfilled | handoff Part 1 | `cmd_done`; `test_done_hides_but_retains` | |
| REQ-004 unknown/already-done id fails safely | fulfilled | handoff Part 1 | `cmd_done` guards; 2 tests assert store byte-unchanged | non-integer id rejected by argparse `type=int` — derivable (id is int by contract) |
| REQ-005 bare `todo` = help | fulfilled | handoff Part 1 | `main` prints help; `test_bare_run_prints_help` | exit 0 chosen — delegated (exit codes) |
| REQ-006 single JSON, retention forever | fulfilled | handoff Part 1 | `store_path` = `~/.todo.json`; retention tested | |
| REQ-007 store-unique id + timestamps | fulfilled | handoff Part 1 (as narrowed by fold-back) | `max(id)+1`, created/completed ISO ts; `test_ids_monotonic` | no UUID — per fold-back decision |
| REQ-008 missing file = empty; created on first write | fulfilled | handoff Part 1 | `load_items` returns []; `test_missing_file` | `list` never creates the file (read-only) — consistent reading |
| REQ-009 corrupt = unparseable OR schema-invalid; never overwrite | fulfilled | handoff Part 1 (fold-back) | `StoreError` + `_validate`; 4 corrupt-shape tests | `UnicodeDecodeError` also treated as corrupt — within "unparseable" |
| Atomic write (temp + `os.replace`) | fulfilled | Decision Boundaries ("must never corrupt on crash") | `save_items` | delegated boundary exercised, not an escape |
| Empty/whitespace title rejected on `add` | **escaped-requirement** | absent from spec | `cmd_add` `title.strip()` guard; `test_empty_title_rejected` | see Escaped Requirements |
| "nothing to do" empty-list message | fulfilled | Decision Boundaries (empty-list message delegated) | `cmd_list` | |
| Rollout: local install only | fulfilled | Implementation Constraints | `uv tool install` → `~/.local/bin/todo` | |
| Non-goals (no edit/delete/purge/sync/TUI) | fulfilled | Out of Scope | no such code paths exist | "no" boundaries respected |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Evidence |
| --- | --- | --- | --- |
| `todo add ""` / whitespace-only title is rejected with a non-zero exit (a data rule: titles must be non-blank) | misuse | enumeration-miss | Diff: `todo_cli.py` `cmd_add` strip-and-reject + `test_empty_title_rejected`. Ledger: no entry mentions blank/degenerate input (documented absence). Transcript: misuse lens ran at the interaction-4 sweep but enumerated only corrupt-file and wrong-done; the fresh-implementer gate later probed "empty-title handling" and dismissed it as derivable — the spec text itself neither requires nor forbids rejection, so the implementer decided it unilaterally. |

Severity: low (weight-1 behavior, invisible in normal use). But it is the exact class the misuse lens owns — careless-actor degenerate input — and the lens ran without listing it.

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| Future sync/multi-machine/reminders/GUI ambition | jpark / post-MVP | no | Implementation adds nothing sync-related beyond REQ-007 ids+timestamps; nothing precludes sync |
| Store file grows forever | jpark / accepted for MVP | no | No purge/compact code exists (boundary held); human-readable store keeps manual pruning possible |

## Scope Drift / Divergent Implementations

None. Every spec requirement is implemented and test-verified; no decision boundary marked "no" was crossed; no settled decision was reversed. No user re-decision needed.

## Lessons Appended Or Updated

Written to the **global** store `~/.agents/skills/ultimateinterview/lessons.md` (signal is repo-agnostic); repo store `docs/ultimateinterview-lessons.md` created from skeleton, no repo-specific rows earned this round. No existing lessons to fire-track (both stores were empty at interview time).

| Signal | Lens to trigger | Failure class | Evidence | Date |
| --- | --- | --- | --- | --- |
| New or changed command (CLI/API) accepts free-text user input | misuse | enumeration-miss | todo-cli-app: blank-title rule decided by implementer, absent from spec (`cmd_add`) | 2026-07-05 |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 13 (9 REQs + 4 constraint/boundary behaviors) |
| escaped-requirement | 1 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome (materialized / total) | 0 / 2 |

| Failure class | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 1 |
| scoring-starved | 0 |
| answer-unpressured | 0 |

Interview discovery rate for this change: 13/14 substantive behaviors pre-specified (~93%); the single escape is low-impact and was even surfaced (then dismissed as delegated) by the fresh-implementer gate. Interview cost: 5/12 interactions, `due_now_corrections` 0. Same-session note for latency calibration: interview-to-handoff completed in a single sitting (vs 52 min for the first live interview, attribute-search-mysql) — the round-6/7 latency work appears effective, though a wall-clock breakdown needs the session jsonl and belongs to a separate analysis.
