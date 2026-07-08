# Session State Files

Schema and edge-case reference for `.ultimateinterview/<slug>/`. The always-on rules (one bookkeeping pass, reload after summarization, dashboard-only echo, channel semantics) are SKILL.md invariants; this file is the field-level law. All scripts validate fail-closed - on a validation error, follow the script's one-line message instead of re-deriving the schema.

Canonical creation path: `scripts/session_init.py <repo-root> <slug> --entries '<json array>'` writes all four files already valid (all six lenses `pending` as objects, counters 0, flags false, empty histories), applies the fresh-suffix rule for completed slugs, refuses to overwrite an unfinished session, and ensures `.gitignore` covers `.ultimateinterview`.

Canonical write path: `scripts/session_update.py <session-dir> --delta '<json>'` (delta schema: the script's `--help` and its `Delta` model) - it validates fail-closed, computes the history append itself, and emits the dashboards; hand-edit only what a delta cannot express.

## Typed events (delta `event`)

The delta's `event` field makes the script compute every counter - never set the managed counters manually alongside an event (the script rejects the conflict):

| Event | Cost | Effects |
| --- | --- | --- |
| `brain-dump` | 1 | `interactions_used`+1, `answers_since_sweep`+1, `brain_dump_done` |
| `framing` | 1 | +1/+1, `framing_challenged` |
| `scored-question` / `bundle` / `batch` | 1 | +1/+1 |
| `checkpoint` | 1 | +1/+1, `falsification_checkpoints_run`+1, `checkpoint_since_last_material_change` true |
| `sweep-asked` | 1 | `interactions_used`+1, `answers_since_sweep`→0, `sweeps_run`+1 |
| `sweep-free` | 0 | `answers_since_sweep`→0, `sweeps_run`+1 |
| `contrarian-asked` | 1 | +1/+1, `contrarian_probes_run`+1 |
| `contrarian-free` | 0 | `contrarian_probes_run`+1 |
| `pressure-followup` | 0 | nothing (free within 2 per parent thread; a third costs 1 - send it as `scored-question`) |

Other delta fields (exact shape with an example: `session_update.py --help`):

- `set` (update existing entries by id; supports `append_reason`, `add_channels`, `pressure`), `add` (full new entries), `protocol` (partial merge; `lenses` merges per-lens), `append_history`.
- `transcript`: `{"title": "...", "lines": ["..."], "awaiting": false}` - appends the typed transcript section with the COMPUTED interaction number (costed events get a `## interaction N [marker]` heading; free events get their sub-bullet marker). WITHOUT an event it appends a 0-cost `- [note]` sub-bullet (invitations, process feedback, lane fold-backs) - never hand-append transcript notes. `awaiting: true` marks the line `[awaiting-answer]`; any answer-bearing delta (costed event, `pressure-followup`, or `checkpoint_confirm`) auto-resolves prior awaiting markers to `[answered]` (repo-only `sweep-free`/`contrarian-free` do not). Fails if `transcript.md` is missing.
- `checkpoint_confirm`: `{"ids": [...], "fatigue": false}` - the checkpoint event plus crediting: covered entries on a single evidence channel gain `from-user` corroboration; `fatigue: true` counts the run but credits nothing. Mutually exclusive with `event`.
- Pressure gate: a set/add op that puts a weight-3+ entry carrying `from-user` below score `2` with fewer than two distinct non-assumption channels is rejected unless the op carries `pressure`: `survived` | `second-channel` | `exempt:<reason>` (recorded into the entry's reason). Settles evidenced by a second channel or without `from-user` pass automatically.

## protocol.json fields

`depth`, `question_budget` (3/12/20 cap unless `budget_extension_reason` is set), `interactions_used` (see SKILL.md budget costing), `answers_since_sweep`, `sweeps_run`, `contrarian_probes_run`, `falsification_checkpoints_run`, `checkpoint_since_last_material_change`, `framing_challenged`, `brain_dump_done` (or `brain_dump_waiver` with a reason), `build_contract_tested`, `implementer_scout_run` (set true when the advisory lane dispatches; `--next` arms it while false), `lenses` (the six lenses, each `pending`, `triggered`, `done`, or `skipped` with a reason - unknown names, missing lenses, and reasonless skips are rejected), `residual_history` and `gap_count_history` (appended after every human-decision round; the script flags a 2+ lag behind `interactions_used`), `stagnation_escalated_at` (set to `len(residual_history)` at each stagnation escalation; must not exceed it), and `due_now_corrections` (increment when a Due-Now obligation preempts your planned action).

The initial `protocol.json` written at orientation must already validate: depth, `question_budget`, all six lens decisions (`pending` where genuinely undecided - it blocks handoff until decided), every counter at `0`, all boolean flags `false`, and `residual_history: []` with `gap_count_history: []`. Each lens value is an OBJECT, not a string: `{"state": "pending" | "triggered" | "done" | "skipped", "reason": ""}` - `skipped` requires a non-empty reason.

## Ledger JSON

A list of entries or an object with exactly one populated section among `requirements`, `gaps`, `entries`, or `ledger` - unknown keys, multiple populated sections, duplicate ids, and an empty ledger are rejected. Each entry uses a unique `id`, `ambiguity_score` or `ambiguity`, `impact_weight` or `weight`, `status` (case-insensitive; anything outside the SKILL.md status vocabulary is rejected, apart from script-recognized aliases such as `accepted-single-source` and `explicitly-deferred`; `Contested` entries are surfaced in the summary), `evidence_channels` (or `channels`), optional `requirement`, optional `reason`, optional `deferred` (either a bool or - required at the gates - the structured form `{"owner": "...", "decision_date": "..."}`; `session_status.py --gate` fails boolean-only deferrals), and optional `origin` (for postmortem attribution). Short channel forms like `code` are normalized; any value outside the six-channel vocabulary is rejected with an error - fix the ledger instead of inventing channel names.

Channel semantics (the SKILL.md invariant names the closed vocabulary; these are its edge cases): a channel names the evidence *source*, not the elicitation - a user answer is `from-user` even when a scenario question prompted it, so two user statements are one channel and never a triangulation pair; `from-scenario` means a scenario was actually walked against the repo or a running system, constraining the entry independently of the user's judgment (a hypothetical the user narrates is still `from-user`); `assumption` is never an evidence channel and can never triangulate.

`origin` value set (the surfacing mechanism, for postmortem attribution): `orientation`, `dump`, `scored-question`, `pressure`, `batch`, `checkpoint`, `sweep`, `contrarian`, `lens:<name>`, `fold-back`.

## Question JSON

A list of candidates or an object with `questions` or `candidates`. Each candidate uses `id`, `question`, `impact`, `branch_split`, `uncertainty_reduction`, `coverage`, `user_cost`, and `redundancy`.

## Crash, resume, and environment rules

- In-flight state must survive a crash: an asked-but-unanswered question is `[awaiting-answer]` in the transcript; a pressure-pending entry stays at score `2` with `pressure-pending` in its reason; batchable-but-unflushed gaps live in `questions.json` as candidates. All three are re-derivable from files alone.
- Re-interviewing a slug that already has a handoff gets a fresh suffixed folder (`<slug>-2`); never overwrite a completed session.
- If writes are blocked (plan mode, read-only harness, no repo root), do not stall Orientation: keep the ledger and protocol state inline in the conversation, say so, and persist all session files verbatim at the first write opportunity, noting `deferred-writes` in the transcript.
- Language protocol: interview in the user's language; write artifacts (ledger, protocol, handoff) in the repo's documentation language (default English) unless the user asks otherwise. Verbatim answers stay in the language they were given, and the ubiquitous-language table carries the user-language term beside the repo term when they differ.
- When the harness has a todo/task tracker, mirror the interview phases in it (orient → dump+frame → loop → checkpoint → gates → handoff), updating at phase transitions only - visible progress is fatigue mitigation.
- `transcript.md` format: `references/transcript-format.md`. A complete worked session (all four files, real dashboards): `references/example-session.md`.
