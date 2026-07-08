# Spec: todo-cli-app-4 — single-user CLI todo app

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners — never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

# Part 1 — Build Contract

## Goal

A single-user command-line todo app that lists open tasks, adds them, marks them complete (with undo and delete), persisting state durably in a JSON file with no date/deadline concept.

## Target Surface

| File / module | Expected change |
| --- | --- |
| `pyproject.toml` | New uv project; one `todo` console-script entrypoint; runtime deps = stdlib only; `pytest` as dev dependency |
| `storage` (module) | Load store; atomic save (temp-file + fsync + `os.replace`); missing/corrupt handling |
| `model` (module) | Task record `{id, title, status}`; status enum open/done; transition guards |
| `cli` (module) | Arg parse + subcommand dispatch; usage/exit-code handling; output formatting |
| `tests/` | pytest suite: subprocess E2E + storage-layer durability unit test |

## Behavior Contract

| ID | Requirement | Acceptance criterion (Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 | `add` creates an open task | Given a store; When `todo add <title...>` (title = remaining args joined by single space); Then title is trimmed, and if non-empty, control-char-free, ≤1024 chars, a task with next monotonic id and status=open is stored; stdout `added <id>`; exit 0. | g2,g4,g11,g15 |
| REQ-002 | `add` rejects degenerate titles | When title is empty/whitespace-only, or contains newline/CR/NUL/other control chars, or exceeds 1024 chars; Then stderr `error: <reason>`, exit 1, store unchanged. | g4 |
| REQ-003 | `list` shows open tasks | When `todo list`; Then open tasks only, ID ascending, one line `<id>\t[ ]\t<title>`; empty view prints nothing; exit 0. | g5,g8,g15 |
| REQ-004 | `completed` shows done tasks | When `todo completed`; Then done tasks only, marker `[x]`, ID ascending; empty prints nothing; exit 0. | g5,g15 |
| REQ-005 | `all` shows open+done | When `todo all`; Then all non-deleted tasks (open and done), ID ascending; deleted tasks never shown. | g5,g15 |
| REQ-006 | `complete` marks done | Given task id exists and is open; When `todo complete <id>`; Then status→done, stdout `completed <id>`, exit 0. Given id absent OR already done; Then stderr `error: no such task: <id>` (absent) / wrong-state error (done); exit 1; store unchanged. | g2,g12 |
| REQ-007 | `undo` reopens a done task | Given id exists and is done; When `todo undo <id>`; Then status→open, stdout `undone <id>`, exit 0. Given absent OR already open; Then exit 1, store unchanged. | g2,g12 |
| REQ-008 | `delete` permanently removes | Given id exists (any status); When `todo delete <id>`; Then record permanently removed, stdout `deleted <id>`, exit 0, no confirmation prompt, id never reused. Given absent; Then exit 1, store unchanged. | g2,g10,g11,g12 |
| REQ-009 | ID model | IDs are immutable positive integers; store holds a monotonic `next_id`; complete/undo/delete never reuse or renumber ids. Given tasks 1,2,3 and delete 3; When `add`; Then new id = 4 (not 3, not max+1 into a reused slot). | g11 |
| REQ-010 | Usage errors | When unknown subcommand / no args / missing arg / extra arg / non-integer or non-positive id; Then stderr usage + specific problem, exit 2, store neither read nor written. | g3,g14 |
| REQ-011 | Storage location & shape | Store path = `Path.home()/".todos.json"`, overridable by env `TODO_FILE`. On-disk shape `{"next_id": int, "tasks": [{"id": int, "title": str, "status": "open"|"done"}]}`, pretty-printed UTF-8, trailing newline. | g1,g11 |
| REQ-012 | First-run / missing store | Given `~/.todos.json` absent; When any read command; Then behave as empty store `{next_id:1, tasks:[]}` and do NOT create the file; the first successful mutation creates it. | g13 |
| REQ-013 | Corrupt store fail-closed | Given the file exists but is invalid JSON OR schema-invalid (wrong shape, duplicate ids, bad status, bad next_id); When any command; Then stderr `error: <msg with path>`, exit 3, file never overwritten or repaired. | g13,g14 |
| REQ-014 | Durable atomic write | When a mutation persists; Then it writes a temp file in the same directory, flush+fsync, atomically `os.replace` onto the target (best-effort parent-dir fsync). Given a crash/interrupt between temp-write and replace; Then the prior store remains intact and loadable. | g6,g13 |
| REQ-015 | Output streams | Success/task output → stdout; all errors → stderr with `error:` prefix; mutations print a concise confirmation including the id. | g15 |

EARS restatement of REQ-014: `When persisting a mutation, the system shall write to a same-directory temp file, fsync it, and atomically replace the target, such that an interrupt before replacement leaves the previous store loadable.`

## Quality Bars

| Attribute | Bar (verifiable) | Weight | Verification |
| --- | --- | --- | --- |
| Durability | After an interrupted write (failure injected between temp-write and `os.replace`), loading the store returns the exact pre-write state; zero partial/corrupt files | 5 | Storage-layer unit test (monkeypatch `os.replace` to raise), then load and assert pre-write state |
| Dependency footprint | `project.dependencies == []`; no third-party runtime imports (stdlib only) | 2 | Assert pyproject; grep imports |
| Latency/throughput | No measurable bar applies — local single-user CLI over a small file; performance is not a stated concern | — | n/a |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Module layout, arg-parsing approach (argparse vs manual), exact usage-text wording | yes | Structural |
| Temp-file naming scheme, whether to fsync the parent directory | yes | Structural (durability outcome still mandatory) |
| ID allocation (immutable, monotonic, no reuse/renumber) | no | Pinned outcome REQ-009; verify delete-then-add → next_id, not reuse |
| Corrupt-store handling | no | Pinned outcome REQ-013: fail-closed exit 3, file byte-unchanged |
| Atomic durability | no | Pinned outcome REQ-014; verify interrupted-write leaves prior store loadable |
| State-transition guards | no | Pinned: complete requires open, undo requires done (REQ-006/007) |

## Out Of Scope / Non-Goals

- Multi-user, sync, network/sharing (personal single-user local tool).
- Recurring tasks, reminders/notifications, due dates/deadlines, any date or "today" scoping.
- Edit-title command.
- Concurrent-process safety (undefined; atomic write only guarantees no torn file, not lost-update protection).
- Priorities, tags, search/filter.

## Implementation Constraints

- Interfaces: single `todo` console entrypoint; subcommands `add`, `list`, `completed`, `all`, `complete`, `undo`, `delete`.
- Compatibility: Python 3, uv-managed project with `pyproject.toml`.
- Migration: none (greenfield; no prior store format to migrate).
- Rollout: none (local install).

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Suite | `uv run pytest` | all pass |
| E2E real surface | Subprocess-invoke installed `todo` with `TODO_FILE=<temp>` | asserts exit code + stdout/stderr + persisted JSON for a full add→list→complete→completed→undo→delete flow |
| Op × store-state matrix | Each op {add,list,completed,all,complete,undo,delete} × store state {absent, valid, invalid-JSON}; assert exit code + stdout/stderr **and raw store bytes / no-write** | every cell has the defined outcome; usage errors (exit 2) and corrupt store (exit 3) never mutate the file |
| Unknown-operation row | `todo bogus` and `todo` (no args) | stderr usage, exit 2, store not read/written |
| ID no-reuse | add 3, delete highest id, then add | new id == next_id (monotonic), not a reused/max+1 slot |
| Corrupt fail-closed (dual) | (a) syntactically bad JSON; (b) valid JSON but schema-invalid (dup ids / bad status) | both → exit 3, file byte-for-byte unchanged |
| Usage-before-read | Corrupt `TODO_FILE` + a usage-error invocation | exit 2 (usage), NOT exit 3 — usage errors detected before store access |
| Durability | Storage-layer unit test: monkeypatch `os.replace` to raise after temp written | store still loads pre-write state; no partial file remains |

## Deferred Risks

None open — every gap is settled at ambiguity ≤ 1. Concurrency is an explicit **non-goal**, not a deferred risk. (No owner/date rows required.)

## Fresh-Implementer Test

| Reviewer | "Would have to ask" items | Gameable criteria | Folded back / re-bound? |
| --- | --- | --- | --- |
| critic (cross-vendor, fresh context) | 1: how to inject a mid-write crash while subprocess-driving the CLI | 8 test-gaming paths (delete tests, stub entrypoint, exit-only matrix asserts, single corrupt case, no-write-only checks, max+1 id reuse, pre-replace-only durability, empty-deps-but-imports) | Yes — durability re-bound to a storage-layer unit test (no production crash hook); gaming paths re-bound via REQ-009/013 verification rows + g17 anti-gaming clauses (raw-store asserts, dual corrupt cases, usage-before-read, no-reuse row, stdlib-only assert) |

> **New decision surfaced by the fresh-implementer test (was not shown to the user):** durability is verified at the **storage layer** (monkeypatch `os.replace`), not by crashing a subprocess — this avoids adding a hidden production crash hook. This is a verification-mechanism choice only; behavior is unchanged.

---

# Part 2 — Audit Trail

State files (source of truth): `.ultimateinterview/todo-cli-app-4/{ledger.json, protocol.json, questions.json, transcript.md}`.

## Problem

The user wants a low-friction morning ritual: open a terminal, see what is still to do, and check items off as they finish. Root cause of "need a tool": a plain file lacks structured completion state and safe mutation. Framing confirmed a CLI is the right artifact.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | Request is the actual need (repeatable check-off workflow), not a symptom |
| Do-nothing option | User would keep an ad-hoc list; loses completion state / durability |
| Simpler alternative | Plain text file + editor — rejected: no structured status, no safe atomic writes |
| Artifact class confirmed | Yes — CLI todo app |

## Desired Outcome

Running `todo list` each morning shows outstanding open tasks; `todo complete <id>` checks them off; state survives crashes and never silently corrupts.

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-user | Personal single-user use; morning check → complete workflow; dateless persistent list; ops undo+delete; immediate delete; storage/output/exit-code defaults accepted; all-correct checkpoint | High |
| from-docs | Interview lessons (durability contract row, temporal-boundary walk, closed-op unknown-branch) | High |
| from-code | Workspace norm Python+uv; single-file atomic-write convention (prior todo builds); fresh-implementer test findings | Medium |

## Triggered Lenses

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | skipped | single-user personal tool; no other stakeholders/ops/compliance/billing |
| domain/state | done | state model (open/done, no-date), durability (REQ-014), first-run/corrupt (REQ-012/013), immutable IDs (REQ-009), transitions (REQ-006/007) |
| goal/obstacle | skipped | single clear outcome; no contested priorities |
| misuse | done | unknown-op (REQ-010), degenerate free-text (REQ-002), destructive delete (REQ-008), invalid/nonexistent id refs (REQ-006/007/008) |
| quality | skipped | tiny local CLI; durability handled under domain/state |
| controlled-language | skipped | acceptance pinned as concrete exit-code + output contracts; no residual fuzzy prose |

## Requirements Ledger (condensed — full table in `ledger.json`)

22 entries. Settled key rows: k1/k2 (artifact + single-user), g1/g6 (storage + durability), g2 (op set), g5 (dateless persistent model), g10 (immediate delete), g11 (immutable ids), g12 (transition/ref errors), g13 (first-run/corrupt), g14 (exit taxonomy), g15 (output), g9/g17 (verification + anti-gaming), g7 (Python+uv), n1/n2/g16 (non-goals). No active score-2/3 gap; no weight-5 open entry.

## Ambiguity Dashboard

| Residual | Blockers | Handoff ready? | Ambiguity % (informational) |
| --- | --- | --- | --- |
| 32 | none | yes | 23% |

Top drivers are all score-1 accepted defaults (g11, g13, g2). No next action required.

## Protocol Dashboard

| Depth | Budget used | Protocol ready? | Outstanding blockers |
| --- | --- | --- | --- |
| focused | 5 / 12 | yes | none |

## Seed-Readiness Audit

| Check | Finding | Action |
| --- | --- | --- |
| Fact vs assumption | Language (Python+uv) was an assumption | Confirmed at checkpoint (g7) |
| Implementation-changing gap | Durability test-injection seam | Resolved: storage-layer unit test |
| Code fact to inspect | Prior workspace atomic-write norm | Adopted as default |
| Missing user decision | Delete confirmation, completed-item disposition | Both settled (immediate delete; retain+hide) |
| Weak boundary | Concurrency scope | Explicit non-goal (g16) |
| Unobservable acceptance criterion | "human-readable" output | Pinned to exact line format (REQ-003/015) |
| Checkpoint since last ledger change | Yes — all-correct, then only evidence-only fold-backs | ✓ |
| Fresh-context reviewer finding | 1 ask + 8 gaming paths | Folded / re-bound (see Part 1) |

## Q&A Record (condensed — full in `transcript.md`)

| # | Question / batch | Decision | Pressure / checkpoint |
| --- | --- | --- | --- |
| 1 | Brain dump + depth | personal, morning check→complete; focused | — |
| 2 | Day-boundary scenario | dateless persistent list | pressured → completed items retained+hidden, not deleted |
| 3 | Bundle: ops / storage / output | undo+delete; single JSON atomic; ID+status+title | — |
| 4 | Batch: usage/validation/ids/corrupt/exit-codes/output/concurrency/verification | all defaults accepted; delete immediate by id | — |
| 5 | Falsification checkpoint (11 statements) | all correct | g7 language confirmed |

## Contested Log

None — no user claim contradicted repo/doc evidence.

## Domain / State Model

Ubiquitous language: task = a todo item; open = not yet done; done = completed (retained, hidden from default list). No user/repo term mismatch.

| State | Trigger | Guard | Effect | Next state | Illegal | Recovery |
| --- | --- | --- | --- | --- | --- | --- |
| open | `complete <id>` | id exists & open | status=done | done | complete on done → exit 1 | no write |
| done | `undo <id>` | id exists & done | status=open | open | undo on open → exit 1 | no write |
| open/done | `delete <id>` | id exists | remove record | (gone) | delete absent → exit 1 | no write |

## Failure And Misuse Cases

| Actor | Goal | Damage | Prevent | Detect | Recover |
| --- | --- | --- | --- | --- | --- |
| Careless user | empty/garbage title | invisible/unreadable tasks | trim + reject empty/control-char/oversized | exit 1 + stderr | store unchanged |
| Careless user | typo'd/unknown command | accidental mutation | usage errors detected before store access | exit 2 | store untouched |
| Crash/interrupt | mid-write | corrupt/lost store | atomic temp+fsync+replace | load succeeds post-crash | prior store intact |
| Hand-edit | corrupt/invalid file | silent data loss on next write | fail-closed, never overwrite | exit 3 + path | user fixes file manually |
| User | mistaken delete | permanent loss | completed items retained (not deleted); delete requires explicit id | — | (accepted: no undo for delete) |

## Restated Approval Check

- Final goal: personal CLI todo app — list/add/complete/undo/delete open tasks, dateless persistent list, durable JSON store.
- Key non-goals: multi-user, dates/deadlines, recurring, reminders, edit, concurrency safety.
- Important assumptions: Python 3 + uv; store at `~/.todos.json` (TODO_FILE override); stdlib-only runtime.
- Unresolved deferred risks: none.
- Decision boundaries: structural detail delegable; ID/corruption/durability/transition outcomes pinned.
- Verification: `uv run pytest` with subprocess E2E + op×store-state matrix + durability unit test.
