# Spec: Todo CLI App 5

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

# Part 1 - Build Contract

## Goal

Build a clean-room fifth todo CLI for personal morning use: running the CLI with no arguments shows the current not-done task list, with dateless tasks carrying over until completed or deleted. (source: f1, g4, g7)

## Target Surface

| File / module | Expected change |
| --- | --- |
| `todo-cli-app-5/` | Create a new Python CLI project. Do not copy or reference the prior todo CLI app implementations/specs. (source: f1) |
| `todo-cli-app-5/todo.py` | Single runnable stdlib-only CLI implementation. (source: g5) |
| `todo-cli-app-5/pyproject.toml` | Minimal project metadata plus pytest configuration if useful; no runtime dependencies. (source: g5, g6) |
| `todo-cli-app-5/tests/` | Pytest coverage for command behavior, persistence, validation, storage errors, and the command x data-state matrix. (source: g6) |

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | Supported operations are exactly: no-arg/default list, `list`, `add <title...>`, `complete <id>`, `delete <id>`, and `list-completed`. | Given the CLI is invoked with one of those commands, When its arguments are valid, Then it performs the specified operation. Given any unknown command or missing/extra argument, Then it exits 2, writes one `error: ...` line to stderr, and writes no stdout. | g1, g12, g14 |
| REQ-002 | The default/no-arg view and `list` show all not-done tasks; tasks have no date or due-date field and unfinished tasks remain visible indefinitely. | Given tasks exist across multiple days/runs, When the user invokes the CLI with no args or `list`, Then every not-done task is shown regardless of creation date and no completed task is shown. | g4, g7 |
| REQ-003 | Completing a task hides it from default/list output but retains it in the store for completed history. | Given an existing not-done task, When `complete <id>` succeeds, Then default/list omits it and `list-completed` includes it. | g8, g9 |
| REQ-004 | Task identity is a stable monotonic integer id assigned at add time; duplicate titles are allowed and disambiguated only by id. | Given tasks are added, When any list is printed, Then each task line starts with its original id and duplicate titles remain separate records. | g7, g16 |
| REQ-005 | List ordering is creation/insertion order. Completing or deleting a task never reorders remaining records. | Given tasks `1`, `2`, and `3`, When task `2` is completed or deleted, Then remaining rendered tasks keep their prior relative order. | g11 |
| REQ-006 | Output format is fixed. | On success: list/list-completed output is one `<id>. <title>` line per task; empty list prints `No tasks.`; empty completed list prints `No completed tasks.`; add prints `Added <id>. <title>`; complete prints `Completed <id>. <title>`; delete prints `Deleted <id>. <title>`; every stdout response has a single trailing newline. | g10, g13 |
| REQ-007 | `add <title...>` joins remaining args with single spaces and validates the resulting title. | Given `add buy milk` succeeds, Then title is `buy milk`. Given a title is empty/whitespace-only, longer than 256 characters, or contains newline/control characters, Then the command exits 2, writes one `error: ...` line to stderr, writes no stdout, and does not add a task. | g3, g12, g14 |
| REQ-008 | `complete <id>` accepts only an existing not-done task id. | Given id is malformed, missing, nonexistent, or already completed, When `complete <id>` runs, Then it exits 2, writes one `error: ...` line to stderr, writes no stdout, and does not mutate the store. For already completed ids, the message includes `task <id> is already completed`. | g14, g15 |
| REQ-009 | `delete <id>` deletes any existing task, done or not-done. | Given an existing task id in any done state, When `delete <id>` runs, Then the task is removed from future list/list-completed output and stdout is `Deleted <id>. <title>`. Given malformed/missing/nonexistent id, Then exit 2 with stderr only and no mutation. | g1, g14, g15 |
| REQ-010 | Persistence uses a single fixed JSON file under the current home directory. | Given `HOME=/tmp/example`, When the CLI reads or writes state, Then it uses `/tmp/example/.todo-cli-app-5.json`; no `TODO_FILE` or alternate path override exists. If the parent directory is missing during save, create it. | g2 |
| REQ-011 | Store schema is `{next_id:int, tasks:[{id:int,title:str,done:bool}]}` and ids are monotonic. | Given a valid store, When a task is added, Then it receives `next_id`, `next_id` increments, and existing ids are never reused after complete or delete. | g2, g17 |
| REQ-012 | Unknown root/task keys are forward-compatible and preserved on round-trip. | Given a syntactically valid store with extra unknown keys, When a mutating command succeeds, Then required fields update and the unknown keys remain present in the rewritten JSON. | g2, g17 |
| REQ-013 | Invalid readable store data is a storage error and is not overwritten. | Given the store JSON is readable but has wrong root shape, missing required fields, wrong field types, duplicate ids, invalid/oversized/control-char titles, or invalid `next_id`, When any command loads it, Then the command exits 3, writes stderr only, and leaves the file unchanged. | g2, g3, g17 |
| REQ-014 | Unreadable/corrupt/non-UTF8 storage is a storage error and is not overwritten. | Given the store is unreadable, corrupt JSON, or non-UTF8, When any command loads it, Then the command exits 3, writes stderr only, and leaves the file unchanged. | g2, g14 |
| REQ-015 | Saves are atomic. | Given a mutating command writes state, Then it writes via a temp file in the same directory and rename. Given save failure, Then it exits nonzero, writes stderr only, prints no success line, and never leaves a partially written store. | g18 |

## Quality Bars

| Attribute | Bar | Weight | Verification |
| --- | --- | --- | --- |
| Store durability | Every mutating write uses same-directory temp file plus atomic rename; a simulated save failure leaves either the old complete store or no store, never a partial JSON file. | 2 | Pytest monkeypatches or temp-directory permission scenario plus manual inspection of the store. (source: g18) |
| Dependency footprint | Runtime imports are Python stdlib only. | 2 | `python - <<'PY'\nimport modulefinder\n# or inspect pyproject/runtime imports; no third-party runtime deps\nPY` plus pyproject review. (source: g5) |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Internal module layout | yes | May keep all code in `todo.py` or split helpers if tests still run through the real CLI surface. |
| Exact stderr wording except pinned phrases | yes | Must be one line beginning `error: `; already-completed complete must include `task <id> is already completed`; error class and exit code must match REQ rows. (source: g14, g15) |
| JSON formatting | yes | Pretty vs compact is free, but schema, unknown-key preservation, monotonic ids, validation, and atomic rewrite behavior are not. (source: g2, g17, g18) |
| Storage location | no | Fixed to `~/.todo-cli-app-5.json` resolved through `HOME`; no env/path override. (source: g2) |
| Task lifecycle | no | Dateless not-done -> done or deleted; no due dates, defer/snooze, edit, or reopen. (source: g1, g4, n1) |
| Post-spec assumptions | no | Every decision the spec did not force, every deviation, and every filled assumption must be appended to `.ultimateinterview/todo-cli-app-5/decisions.jsonl`. |

## Out Of Scope / Non-Goals

- No multi-user support, network sync, server/daemon, GUI/web UI, edit command, reopen/un-complete command, due dates, scheduling, defer, or snooze. (source: n1, g1, g4)
- Do not reuse or consult prior todo CLI app specs/implementations for behavior. (source: f1)

## Implementation Constraints

- Interfaces: local command-line app invoked through Python; expose behavior through the real CLI, not only importable functions. (source: g5, g6)
- Compatibility: Python 3 stdlib runtime only; pytest is allowed for tests. (source: g5, g6)
- Migration: no migration from prior todo apps; this is a clean store at `~/.todo-cli-app-5.json`. (source: f1, g2)
- Rollout: local filesystem only; no deployment, service, credentials, or external integration. (source: f1, n1)
- Test seam: use `HOME` override to point at a temp directory in tests and manual checks. (source: g2)

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Unit/behavior suite | `cd todo-cli-app-5 && python -m pytest` | Passes tests covering add/list/complete/delete/list-completed, validation, store errors, forward-compatible unknown keys, ordering, duplicate titles, atomic save, and exit-code taxonomy. |
| Real-surface absent-store walkthrough | `tmp=$(mktemp -d); HOME="$tmp" python todo.py; HOME="$tmp" python todo.py list-completed` | First command prints `No tasks.` exit 0; second prints `No completed tasks.` exit 0; store absence does not error. |
| Real-surface valid-store walkthrough | `tmp=$(mktemp -d); HOME="$tmp" python todo.py add buy milk; HOME="$tmp" python todo.py add buy milk; HOME="$tmp" python todo.py; HOME="$tmp" python todo.py complete 1; HOME="$tmp" python todo.py list; HOME="$tmp" python todo.py list-completed; HOME="$tmp" python todo.py delete 1` | Adds print `Added 1. buy milk` and `Added 2. buy milk`; list shows `1. buy milk` and `2. buy milk`; after complete, list shows only id 2; completed shows id 1; delete removes id 1. |
| Real-surface invalid-store walkthrough | `tmp=$(mktemp -d); printf '{bad json' > "$tmp/.todo-cli-app-5.json"; HOME="$tmp" python todo.py list` | Exits 3, stderr starts `error: `, stdout empty, corrupt file unchanged. |
| User error matrix | Run malformed id, nonexistent id, already-completed complete, unknown command, missing args, extra args, invalid title. | Each exits 2, stderr only, no mutation. |
| Operation x data-state matrix | Exercise each legal operation against absent store, valid store, and invalid store; exercise unknown operation once. | Absent store is initialized/read as empty for legal commands; valid store follows REQs; invalid store exits 3 without overwrite; unknown operation exits 2. |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| None | n/a | n/a | No active score 2 or 3 gaps and no deferred ledger entries. |

## Fresh-Implementer Test

| Reviewer | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? |
| --- | --- | --- | --- |
| Self-audit, fresh pass over Part 1 only | None blocking. Part 1 specifies command set, data model, persistence path, error taxonomy, output strings, validation, and non-goals. | A pytest-only suite could pass without proving the installed/real CLI surface; storage durability could be claimed without simulating failure. | Re-bound through real-surface walkthrough rows and explicit durability check in Verification Commands. |

# Part 2 - Audit Trail

## Problem

The user wants a fifth todo CLI app for real personal use, especially a morning run that shows the day's todos. The interview removed ambiguity around whether "today" meant dated scheduling versus a dateless active-list model.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | Root need is a quick local active-task view, not calendar scheduling. |
| Do-nothing option | Not accepted; user wants a buildable CLI spec. |
| Simpler alternative | Dateless active list accepted instead of due-date scheduling. |
| Artifact class confirmed | Python stdlib-only CLI app with pytest verification. |

## Desired Outcome

A local CLI in `todo-cli-app-5/` where no-arg execution reliably shows not-done tasks, completed tasks are retained for review, and errors/storage edge cases are deterministic.

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-user | Personal use, morning not-done view, command choices, retention, validation, language/runtime, and checkpoint all confirmed. | High |
| from-docs | Prior lessons required care around store/schema and title validation edge cases. | Medium |
| from-research | Implementer-scout style fold-back surfaced CLI grammar/output/schema/exit-code details, all confirmed by user batch. | Medium |
| from-code | No product code for app 5 existed at handoff; target is new `todo-cli-app-5/`. | High |
| from-scenario | Scenario probes covered day-boundary, completed retention, mis-added task deletion, invalid stores, and nagging carryover consequence. | Medium |

## Triggered Lenses

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | skipped | Single personal local user; no other stakeholders, ops, billing, or compliance surface. |
| domain/state | done | Dateless model, not-done/done/deleted lifecycle, retained completed tasks, store schema, and load validation settled. |
| goal/obstacle | done | Morning active-task goal and obstacles such as mis-add cleanup and stale carryover were analyzed. |
| misuse | done | Degenerate title inputs, corrupt stores, invalid ids, and save failures were enumerated. |
| quality | skipped | Personal single-user local CLI; no architecture-significant performance/scale/availability quality attribute. |
| controlled-language | done | Behavior expressed as observable command contracts, exit codes, stdout/stderr, and store-state checks. |

## Requirements Ledger

State files are the source of truth: `.ultimateinterview/todo-cli-app-5/ledger.json`, `protocol.json`, `questions.json`, and `transcript.md`.

| ID | Requirement summary | Evidence channels | Ambiguity | Impact | Status |
| --- | --- | --- | --- | --- | --- |
| f1 | Clean-room app 5, personal morning todo use. | from-user | 0 | 2 | Accepted |
| g1 | Final command set includes add/list/complete/delete/list-completed, no edit/reopen. | assumption, from-user | 1 | 3 | Accepted |
| g2 | Fixed home JSON store and storage robustness. | assumption, from-docs, from-user | 1 | 3 | Accepted |
| g3 | Title validation at add and load. | assumption, from-docs, from-user | 1 | 2 | Accepted |
| g4 | Dateless active-list temporal model with indefinite carryover. | assumption, from-user | 1 | 3 | Accepted |
| g5 | Python 3 stdlib-only implementation. | assumption, from-user | 1 | 2 | Accepted |
| g6 | Pytest plus manual CLI walkthrough verification. | assumption, from-user | 1 | 2 | Accepted |
| g7 | Default view, stable ids, id display/reference. | from-user | 1 | 3 | Accepted |
| g8/g9 | Completed tasks hidden but retained and listable. | from-user | 1 | 2 | Accepted |
| g11-g18 | Ordering, grammar, output, exit codes, state errors, duplicates, schema, atomic saves. | assumption, from-research, from-user | 1 | 1-3 | Accepted |
| n1 | Non-goals: sync, GUI, edit, reopen, dates/scheduling. | assumption, from-user | 1 | 1 | Accepted |

## Ambiguity Dashboard

| Residual | Blockers | Handoff ready? | Ambiguity % |
| --- | --- | --- | --- |
| 41 | None active at score 2 or 3 | yes | 31% |

| Top driver | Ambiguity | Impact weight | Reason | Next action |
| --- | --- | --- | --- | --- |
| g1 | 1 | 3 | Command set settled with delete after pressure follow-up. | Implement as specified. |
| g14 | 1 | 3 | Exit taxonomy settled from scout plus user confirmation. | Implement as specified. |
| g17 | 1 | 3 | Schema/load validation settled from scout plus user confirmation. | Implement as specified. |

## Protocol Dashboard

| Depth | Budget used | Protocol ready? | Outstanding blockers |
| --- | --- | --- | --- |
| focused | 9 / 12 | yes | None; final helper checks passed. |

## Seed-Readiness Audit

| Check | Finding | Action |
| --- | --- | --- |
| Fact vs assumption | Remaining score-1 assumptions are accepted defaults, not blockers. | Cite in Part 1 and decisions boundary. |
| Implementation-changing gap | None active at score 2 or 3. | No further user question. |
| Code fact to inspect | No app-5 code exists yet; target surface is creation. | Spec names new directory. |
| Missing user decision | None after checkpoint confirmation. | Proceed to handoff. |
| Weak boundary | Clean-room and no due-date/defer/snooze boundaries could be easy to blur. | Explicit non-goals in Part 1. |
| Unobservable acceptance criterion | Pytest-only could be gamed. | Added real CLI walkthroughs and matrix checks. |
| Falsification checkpoint run since last material ledger change | Yes, user replied `all correct`. | Recorded in transcript. |
| Fresh-context reviewer finding | Self-audit found no blocking ask; re-bound gameable checks to real surface. | Build contract tested; protocol ready. |

## Q&A Record

| # | Question / batch | Decision | Pressure test / checkpoint correction |
| --- | --- | --- | --- |
| 1 | Brain dump | Personal morning todo CLI. | Framing accepted. |
| 2 | Date/day-boundary model | Dateless active list; completed hidden. | Completed retention pressure asked. |
| 3 | Completed fate | Retain completed and add completed-list view. | Survived pressure. |
| 4 | Command set | Add delete; no edit/reopen. | Mis-add without delete pressure changed command set. |
| 5 | Validation batch | Enforce all title validation and load validation. | Accepted. |
| 6 | Storage | Fixed home file and HOME test seam. | Accepted. |
| 7 | Identity/display | Stable monotonic integer id and `<id>. <title>`. | Accepted. |
| 8 | Defaults batch | Empty state, ordering, grammar, output, exit codes, schema, save semantics. | Accepted all defaults. |
| 9 | Final batch | Python stdlib-only, pytest/manual verification, non-goals. | Accepted. |
| 10 | Pre-handoff checkpoint | All 12 falsifiable statements correct. | No corrections. |

## Contested Log

| Entry | User claim | Other evidence | Governing source | Resolution |
| --- | --- | --- | --- | --- |
| none | n/a | n/a | n/a | No contested entries. |

## Domain Flow

### EventStorming

- Task added.
- Task listed as not-done.
- Task completed.
- Completed task listed in history.
- Task deleted.
- Store load fails.
- Store save succeeds atomically or fails without partial state.

### Domain Storytelling

- User -> runs CLI in morning -> sees not-done tasks -> chooses what to do.
- User -> adds task -> task receives stable id -> future commands reference that id.
- User -> completes task -> task leaves active list -> remains reviewable.
- User -> deletes task -> task disappears from all future views.

## Domain / State Model

### Ubiquitous Language

| User term | Repo term | Bounded context | Meaning / mismatch |
| --- | --- | --- | --- |
| today's todos | not-done task list | local todo CLI | Does not mean dated tasks; means active not-done tasks. |
| completed | done task | local todo CLI | Hidden from default view but retained. |
| delete | remove task | local todo CLI | Allowed for done and not-done tasks. |

### Domain Concepts

| Concept | Type | Owner | Invariants / constraints | Evidence |
| --- | --- | --- | --- | --- |
| Task | Entity | CLI/store | `id:int`, `title:str`, `done:bool`; id stable and unique. | g7, g17 |
| Store | Aggregate root | CLI | `{next_id:int,tasks:[...]}`; fixed home path; invalid readable data blocks all commands. | g2, g17 |
| Title | Value object | CLI | Non-empty after trim, max 256 chars, no newline/control chars. | g3 |

### State Model

| State | Event / trigger | Guard | Effect | Next state | Illegal transitions | Recovery |
| --- | --- | --- | --- | --- | --- | --- |
| absent store | list/list-completed | none | Treat as empty. | absent/empty | none | n/a |
| absent store | add valid title | valid title | Create store and first task. | valid store | invalid title exits 2 | Correct title. |
| not-done task | complete id | id exists and not done | Set done true. | done task | complete malformed/nonexistent exits 2 | Use listed id. |
| done task | complete id | already done | No mutation. | done task | exits 2 with already-completed message | n/a |
| any existing task | delete id | id exists | Remove task. | deleted | malformed/nonexistent exits 2 | Use listed id. |
| invalid store | any command | load invalid/corrupt/unreadable | No mutation. | invalid store | exits 3 | User repairs/removes store manually. |

## Goal + Obstacle Analysis

| Goal | Obstacle | Derived requirement | Residual risk |
| --- | --- | --- | --- |
| See morning tasks quickly | Due-date model would add unnecessary scheduling complexity. | Dateless not-done list by default. | Old unfinished tasks may accumulate. |
| Avoid polluting completed history | Mis-added tasks need removal. | Add `delete <id>`. | Delete is permanent. |
| Preserve completed review | Completion should not delete records. | Add `list-completed`. | No reopen by design. |

## Misuse Cases

| Misuse / failure | Expected response | Source |
| --- | --- | --- |
| Empty/whitespace/oversized/control-char title | Exit 2, stderr only, no add. | g3, g14 |
| Malformed/nonexistent id | Exit 2, stderr only, no mutation. | g14 |
| Already-completed task completed again | Exit 2 with `task <id> is already completed`, no mutation. | g15 |
| Corrupt/non-UTF8/invalid store | Exit 3, stderr only, no overwrite. | g2, g17 |
| Save failure | Nonzero stderr only, no success line, no partial store. | g18 |

## Restated Approval Check

The user confirmed the final falsification checkpoint with `all correct`. No deferred risks remain.
