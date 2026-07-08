# Spec: todo-cli — minimal personal todo CLI

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

# Part 1 — Build Contract

## Goal

Build `todo`, a deliberately minimal personal todo CLI (Python + uv) with exactly three commands — add / list / done — storing tasks in one human-readable JSON file in the user's home directory.

## Target Surface

Greenfield: new top-level subproject in the `harnesses` workspace.

| File / module | Expected change |
| --- | --- |
| `todo-cli/pyproject.toml` | New uv-managed project; console script entry point named `todo` |
| `todo-cli/` main module | CLI with `add` / `list` / `done` subcommands + JSON store I/O (internal layout: implementer's choice) |
| `todo-cli/tests/` | pytest smoke suite (see Verification) |

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | `todo add "<title>"` registers a new open task; the title is a single positional argument, no other user-supplied fields | Given any store state, When `todo add "장보기"` runs, Then a new open item with a unique id, the title, and a created timestamp is persisted, And the command confirms success | assume-add-format, gap-feature-scope |
| REQ-002 | `todo list` shows only open (not-done) items in insertion order (oldest first), each line carrying the stable numeric id used by `done`; **ascending id is the source of truth for order** (equals file order in normal use; id order governs after hand-edits) | Given 2 open and 1 done item, When `todo list` runs, Then exactly the 2 open items print in ascending-id order with their ids, And the done item does not appear | gap-feature-scope, assume-list-order |
| REQ-003 | `todo done <id>` completes the open item with that id; done is one-way (no undo command exists) | Given an open item with id 3, When `todo done 3` runs, Then the item is marked done with a completed timestamp, And it no longer appears in `todo list`, And it remains in the store file | assume-done-one-way, gap-feature-scope |
| REQ-004 | Unknown or already-done id to `done` fails safely | Given no open item with id 9, When `todo done 9` runs, Then the command exits non-zero with a clear error, And the store file is unchanged | assume-done-one-way |
| REQ-005 | Bare `todo` (no subcommand) prints usage/help, not the list | Given any store state, When `todo` runs with no arguments, Then usage/help text prints, And the task list does not | assume-bare-run |
| REQ-006 | Storage is a single JSON file in the home directory; done items are retained forever (marked done, never auto-purged) | Given items completed over time, When any command runs, Then the store remains one JSON file under the user's home dir containing all items ever added, open and done | gap-storage |
| REQ-007 | Every item carries an id **unique within this store file** plus created/completed timestamps; global (cross-machine) uniqueness is NOT required — sequential ints are fine, and a future merge tool may renumber using timestamps. Adding an extra UUID field is permitted but not required | Given a persisted item, When the store file is inspected, Then the item has a store-unique id, created timestamp, and (when done) completed timestamp | assume-sync-ready-schema |
| REQ-008 | Missing store file behaves as an empty list; the file is created on first write | Given no store file, When `todo list` runs, Then it reports an empty list without error; When `todo add` runs, Then the file is created | assume-corrupt-file |
| REQ-009 | A corrupt store file — **unparseable JSON OR parseable-but-schema-invalid** (wrong top-level shape, item missing required fields) — aborts with a clear error and is never overwritten or "leniently" rewritten | Given a store file with invalid JSON or a valid-JSON wrong shape, When any command runs, Then the command exits non-zero naming the file and problem, And the file's contents are not modified | assume-corrupt-file |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Exact store path/filename under home dir | yes | Single JSON file under `$HOME` (e.g. `~/.todo.json` or `~/.todo/todos.json`) |
| JSON field names / id scheme | yes | Ids stable and unique within the store (sequential int fine); numeric display ids in `list`; timestamps required (REQ-007) |
| CLI parsing library | yes | stdlib-first (argparse); no heavy dependencies |
| Output formatting, error wording, empty-list message, exit codes | yes | Errors non-zero; keep output plain and scannable |
| Write durability strategy (e.g. atomic temp+rename) | yes | Must never corrupt or truncate the store on crash |
| Adding any command beyond add/list/done | **no** | Non-goal — stop and ask |
| Purging/compacting done items | **no** | Retention is forever (REQ-006) — stop and ask |

## Out Of Scope / Non-Goals

- Priorities, due dates (no such fields, no sort keys)
- Tags, projects, search, filters
- `edit` / `delete` / undo commands (mistakes: re-add, or hand-edit the JSON — it must stay human-editable)
- TUI / interactive mode; GUI; reminders/notifications; sync — all excluded from MVP (sync/GUI/reminders are deliberately future-open, see Deferred Risks)

## Implementation Constraints

- Interfaces: console script `todo` installed by the uv project; subcommands only.
- Compatibility: Python + uv, consistent with sibling workspace projects (ouroboros, SkillOpt); stdlib-first.
- Store format: human-readable, hand-editable JSON (pretty-printed) — hand-editing is the sanctioned recovery path.
- Migration: none — fully greenfield, no existing data to import.
- Rollout: local install on the user's work machine only.

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Smoke suite | `uv run pytest` in `todo-cli/` | Green; covers add/list/done happy path + done-hidden-from-list rule (REQ-001..003) |
| Morning scene | `uv run todo add "x"` → `uv run todo list` → `uv run todo done <id>` → `uv run todo list` | Item appears with id, then disappears after done; store file still contains it marked done |
| Help default | `uv run todo` | Usage text, no list output |
| Corrupt store | Write junk into the store file, run `uv run todo list` | Non-zero exit, clear error, file unmodified |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| Future sync/multi-machine, reminders, GUI (deliberate post-MVP ambition; contrarian probe surfaced no concrete current need — user kept it) | jpark | post-MVP, unscheduled | REQ-007 keeps merge possible; implementer must not add sync features nor preclude them |
| Store file grows forever (done items never purged) | jpark | accepted for MVP | Human-readable JSON keeps manual pruning possible; no purge command allowed |

## Fresh-Implementer Test

| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Folded back as gaps? |
| --- | --- | --- |
| fresh-context subagent (Part 1 + repo read access only, no interview context) | 3: (1) schema-invalid-but-parseable store handling; (2) id uniqueness scope (per-store vs global for future merge); (3) source of truth for "insertion order" after hand-edits | All 3 folded back as evidence-consistent defaults into REQ-009 / REQ-007 / REQ-002; surfaced one-line each in the handoff message (no new user decision required, checkpoint not re-armed) |

# Part 2 — Audit Trail

Render-by-reference: full ledger and Q&A live in `.ultimateinterview/todo-cli-app/` (`ledger.json`, `transcript.md`, `protocol.json`).

## Problem

The user wants a daily personal todo tool; no existing tool (taskwarrior, todo.txt, Obsidian tasks) appeals because all are more complex than the need: walk into work, run one command, see what to do.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | Request is the real need (deliberate build; dissatisfaction with existing tools probed and confirmed) |
| Do-nothing option | Rejected by user — current workflow has no appealing tool |
| Simpler alternative | Adopting existing tools raised and rejected ("마음에 드는게 없어서") |
| Artifact class confirmed | CLI app, unchanged throughout |

## Desired Outcome

Each morning at work, `todo list` instantly shows open tasks; adding (`todo add "…"`) and completing (`todo done <id>`) are one-liners; everything lives in one hand-editable JSON file.

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-code | Workspace is polyglot multi-project; py-uv most common (ouroboros, SkillOpt) → stack corroboration | high |
| from-user | Brain dump + 2 pressure rounds + bundle/batch picks + checkpoint "전부 맞아" | high |
| from-scenario / from-docs / from-research | not used (greenfield personal tool; no docs surface) | — |

## Triggered Lenses

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | skipped | single-stakeholder personal tool; no ops/support/compliance surface |
| domain/state | done | lifecycle open→done modeled; one-way transition + retention settled |
| goal/obstacle | done | goal (frictionless morning check) and obstacle (existing tools too complex) settled via pressure |
| misuse | done | careless-actor pass at sweep: corrupt-file + wrong-done covered; no hostile surface |
| quality | done | "아주 간단" operationalized as explicit non-goal list + minimal command tier |
| controlled-language | done | Behavior Contract written Given/When/Then (REQ-001..009) |

## Ambiguity / Protocol Dashboards (final, from session_status.py)

| Residual | Blockers | Handoff ready? | Ambiguity % (informational) |
| --- | --- | --- | --- |
| 0 | none | yes | 0% |

| Depth | Budget used | Protocol ready? | Outstanding blockers |
| --- | --- | --- | --- |
| focused | 5 / 12 | yes (after build-contract test) | none |

## State Model (domain/state lens)

| State | Event / trigger | Guard | Effect | Next state | Illegal transitions | Recovery |
| --- | --- | --- | --- | --- | --- | --- |
| (none) | `todo add` | title present | item persisted w/ id + created ts | open | — | — |
| open | `todo done <id>` | id exists & open | completed ts recorded; hidden from list; retained in file | done | done→open (no undo) | re-add or hand-edit JSON |

## Q&A Record (condensed; full record in transcript.md)

| # | Question / batch | Decision | Pressure test / checkpoint correction |
| --- | --- | --- | --- |
| 1 | Brain dump + depth calibration | Daily personal tool; no stack; greenfield | Pressure ×2: rejects existing tools, wants "very simple"; morning-check scene |
| 2 | Bundle: stack / storage / command set | Python+uv; single JSON file; add/list/done | Pressure ×2: done items retained in file; explicit `todo list` (no bare-run list) |
| 3 | Non-goals multi-select | Excluded: priorities·due dates / tags·search / edit·delete | Collision probe: sync/GUI/reminders left un-excluded **deliberately** → future-open; corrected assume-single-machine |
| 4 | Smart-default batch ×4 | pytest smoke; harnesses/todo-cli/; title-only add; insertion order + numeric id | all defaults accepted |
| 5 | Falsification checkpoint (9 statements) + contrarian probe | "전부 맞아" — zero corrections | Contrarian (sync-ready schema is speculative weight): model survived, user kept it |

## Contested Log

| Entry | User claim | Repo evidence | Governing source | Resolution |
| --- | --- | --- | --- | --- |
| assume-single-machine | sync group deliberately not excluded | (assumption, not repo) | user | "No sync ever" assumption corrected → MVP-local, future-open |

## Restated Approval Check

- Final goal: minimal 3-command personal todo CLI, one JSON store, morning-check flow.
- Key non-goals: priorities/due dates, tags/search, edit/delete, TUI/GUI/sync/reminders (MVP).
- Important assumptions (all user-confirmed at checkpoint): help on bare run; done one-way; corrupt file aborts; sync-ready ids/timestamps.
- Deferred risks: future sync ambition; unbounded store growth — owner jpark.
- Decision boundaries: store path, schema field names, argparse details, formatting, atomicity strategy.
- Verification expectations: pytest smoke + manual morning-scene walk.
- Approval status: Approved (checkpoint "전부 맞아", 2026-07-05).
