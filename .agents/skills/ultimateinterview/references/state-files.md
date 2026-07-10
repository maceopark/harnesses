# Session State Files

Schema and edge-case reference for `.ultimateinterview/<slug>/`. The always-on rules (one bookkeeping pass, reload after summarization, dashboard-only echo, channel semantics) are SKILL.md invariants; this file is the field-level law. All scripts validate fail-closed - on a validation error, follow the script's one-line message instead of re-deriving the schema.

Canonical creation path: `scripts/session_init.py <repo-root> <slug> --entries '<json array>'` writes all four files already valid (all six lenses `pending` as objects, counters 0, flags false, empty histories), applies the fresh-suffix rule for completed slugs, refuses to overwrite an unfinished session, and ensures `.gitignore` covers `.ultimateinterview`.

Canonical write path: `scripts/session_update.py <session-dir> --delta '<json>'` (delta schema: the script's `--help` and its `Delta` model) - it validates fail-closed, commits ledger/protocol/questions/transcript as one journaled file set, computes history and review digests itself, and emits the dashboards; hand-edit only what a delta cannot express.

## Typed events (delta `event`)

The delta's `event` field makes the script compute every counter. Event-managed counters cannot be set through `protocol` at all, with or without an event.

| Event | Cost | Effects |
| --- | --- | --- |
| `brain-dump` | 1 | `interactions_used`+1, `answers_since_sweep`+1, `brain_dump_done` |
| `framing` | 1 | +1/+1, `framing_challenged` |
| `scored-question` / `bundle` / `batch` | 1 | +1/+1 |
| `checkpoint_confirm` (not `event`) | 1 | requires at least one covered id; +1/+1, `falsification_checkpoints_run`+1, `checkpoint_since_last_material_change` true |
| `sweep-asked` | 1 | `interactions_used`+1, cadence reset, `sweeps_run`+1, update dry streak from required `sweep_result` |
| `sweep-free` | 0 | cadence reset, `sweeps_run`+1, update dry streak from required `sweep_result` |
| `contrarian-asked` | 1 | +1/+1, `contrarian_probes_run`+1 |
| `contrarian-free` | 0 | `contrarian_probes_run`+1 |
| `pressure-followup` | 0 | requires `pressure_parent`; increments its persisted count up to 2; a third is rejected and must be sent as `scored-question` |

Other delta fields (exact shape with an example: `session_update.py --help`):

- `set` (update existing entries by id; supports `append_reason`, `add_channels`, `pressure`), `add` (full new entries), `protocol` (partial merge; `lenses` merges per-lens), `questions` (validated full replacement, including `[]` to clear), `append_history`, `sweep_result` (`dry` or `new-gaps`; required only with sweep events). A `new-gaps` sweep must add an entry with `origin: "sweep"`; a `dry` sweep must not. The writer locks the session and journals the prior generation before committing ledger, protocol, questions, and transcript changes; the next canonical status/update command recovers an interrupted generation before reading it. These helpers currently require a POSIX host because the lock uses `fcntl`; unsupported hosts fail explicitly rather than running without serialization.
- `transcript`: `{"title": "...", "lines": ["..."], "awaiting": false}` - appends the typed transcript section with the COMPUTED interaction number (costed events get a `## interaction N [marker]` heading; free events get their sub-bullet marker). WITHOUT an event it appends a 0-cost `- [note]` sub-bullet (invitations, process feedback, lane fold-backs) - never hand-append transcript notes. `awaiting: true` marks the line `[awaiting-answer]`; any answer-bearing delta (costed event, `pressure-followup`, or `checkpoint_confirm`) auto-resolves prior awaiting markers to `[answered]` (repo-only `sweep-free`/`contrarian-free` do not). Fails if `transcript.md` is missing.
- `checkpoint_confirm`: `{"ids": [...], "fatigue": false}` - the checkpoint event plus crediting: covered entries on a single evidence channel gain `from-user` corroboration; `fatigue: true` counts the run but credits nothing. Mutually exclusive with `event`.
- `build_contract_test`: `{"reviewer": "<agent-or-self-audit-name>"}` - dedicated delta after `handoff.md` exists. The writer records `build_contract_tested`, reviewer, and the SHA-256 of the current Part 1; those three fields cannot be patched through `protocol`, and a later Part-1 edit makes `--gate` fail.
- Pressure gate: a set/add op that puts a weight-3+ entry carrying `from-user` below score `2` with fewer than two distinct non-assumption channels is rejected unless the op carries `pressure`: `survived` | `second-channel` | `exempt:<reason>` (recorded into the entry's reason). Settles evidenced by a second channel or without `from-user` pass automatically.

## protocol.json fields

`depth`, `question_budget` (3/12/20 cap unless `budget_extension_reason` is set), `interactions_used`, `answers_since_sweep`, `sweeps_run`, `dry_sweeps_in_row`, `contrarian_probes_run`, `falsification_checkpoints_run`, `checkpoint_since_last_material_change`, `framing_challenged`, `brain_dump_done` (or `brain_dump_waiver` with a reason), `build_contract_tested`, `build_contract_digest`, `build_contract_reviewer`, `implementer_scout_run`, `pressure_followups_by_parent`, `lenses`, `residual_history`, `gap_count_history`, `stagnation_escalated_at`, and `due_now_corrections`.

Any material ledger projection change (requirement, score, weight, status, deferral, add/remove) resets `checkpoint_since_last_material_change`, `dry_sweeps_in_row`, and the bound build-contract review. A checkpoint delta covers corrections in that same delta. A new accepted/triangulated score-`0`/`1` `fold-back` entry backed by a real evidence channel is evidence-only and resets neither. A ledger mutation without a `questions` replacement clears `questions.json` so a stale queue cannot survive; include the regenerated queue in the same delta when it is already known. `residual_history`, `gap_count_history`, and `stagnation_escalated_at` are writer-managed and cannot be patched through `protocol`.

## Migration from the previous helper contract

Old protocol files still parse, but cannot become ready until they record two consecutive dry sweep events, typed artifacts for every `done` lens, and fresh-review evidence through `build_contract_test`. Sweep producers must now send `sweep_result`. JSON consumers must read `interview_converged` instead of the former ambiguous `ready`; only the composite gate emits `implementation_ready`. Gate mode intentionally rejects `--ledger`/`--protocol` overrides so one session's handoff cannot be paired with another session's state.

The initial `protocol.json` written at orientation must already validate: depth, `question_budget`, all six lens decisions (`pending` where genuinely undecided - it blocks handoff until decided), every counter at `0`, all boolean flags `false`, and `residual_history: []` with `gap_count_history: []`. Each lens value is an OBJECT, not a string: `{"state": "pending" | "triggered" | "done" | "skipped", "reason": ""}` - `skipped` requires a non-empty reason.

## Ledger JSON

A list of entries or an object with exactly one populated section among `requirements`, `gaps`, `entries`, or `ledger` - unknown keys, multiple populated sections, duplicate ids, and an empty ledger are rejected. Each entry uses a unique `id`, `ambiguity_score` or `ambiguity`, `impact_weight` or `weight`, `status` (case-insensitive; anything outside the SKILL.md status vocabulary is rejected, apart from script-recognized aliases such as `accepted-single-source` and `explicitly-deferred`; `Contested` entries are surfaced in the summary), `evidence_channels` (or `channels`), optional `requirement`, optional `reason`, optional `deferred` (either a bool or - required at the gates - the structured form `{"owner": "...", "decision_date": "..."}`; `session_status.py --gate` fails boolean-only deferrals), and optional `origin` (for postmortem attribution). Short channel forms like `code` are normalized; any value outside the six-channel vocabulary is rejected with an error - fix the ledger instead of inventing channel names.

Channel semantics (the SKILL.md invariant names the closed vocabulary; these are its edge cases): a channel names the evidence *source*, not the elicitation - a user answer is `from-user` even when a scenario question prompted it, so two user statements are one channel and never a triangulation pair; `from-scenario` means a scenario was actually walked against the repo or a running system, constraining the entry independently of the user's judgment (a hypothetical the user narrates is still `from-user`); `assumption` is never an evidence channel and can never triangulate.

`origin` value set (the surfacing mechanism, for postmortem attribution): `orientation`, `dump`, `scored-question`, `pressure`, `batch`, `checkpoint`, `sweep`, `contrarian`, `lens:<name>`, `fold-back`.

Hidden methodology tags use compact ASCII in `reason`; `artifact` is the one structured lens-output field:

- `deficit=<class>` for hidden ORIENT deficit recognition, such as `deficit=context-insufficient` or `deficit=execution-blind`.
- `reverse-evidence=<condition>` for the observation that would shrink, falsify, or complete a hypothesis or lens.
- `artifact` (structured field, not a reason tag): exact enum `ViewpointMatrix|StateModel|GoalObstacleMap|MisuseCaseSet|QualityScenarioSet|ControlledAcceptanceCriteria`; required when `state` is `done`, forbidden otherwise, and must match the lens.
- `skip=<reason>` when a lens is skipped or marked done because no reverse-evidence remains.

The text tags are conventions for auditability; `artifact` is modeled and enforced in `protocol.json`. Do not rely on any other unmodeled field being preserved, ranked, emitted, or enforced.

## Question JSON

A list of candidates or an object with `questions` or `candidates`. Each candidate uses `id`, `question`, `impact`, `branch_split`, `uncertainty_reduction`, `coverage`, `user_cost`, and `redundancy`.

## Crash, resume, and environment rules

- In-flight state must survive a crash: an asked-but-unanswered question is `[awaiting-answer]` in the transcript; a pressure-pending entry stays at score `2` with `pressure-pending` in its reason; batchable-but-unflushed gaps live in `questions.json` as candidates. All three are re-derivable from files alone.
- Re-interviewing a slug that already has a handoff gets a fresh suffixed folder (`<slug>-2`); never overwrite a completed session.
- If writes are blocked (plan mode, read-only harness, no repo root), do not stall Orientation: keep the ledger and protocol state inline in the conversation, say so, and persist all session files verbatim at the first write opportunity, noting `deferred-writes` in the transcript.
- Language protocol: interview in the user's language; write artifacts (ledger, protocol, handoff) in the repo's documentation language (default English) unless the user asks otherwise. Verbatim answers stay in the language they were given, and the ubiquitous-language table carries the user-language term beside the repo term when they differ.
- When the harness has a todo/task tracker, mirror the interview phases in it (orient → dump+frame → loop → checkpoint → gates → handoff), updating at phase transitions only - visible progress is fatigue mitigation.
- `transcript.md` format: `references/transcript-format.md`. A complete worked session (all four files, real dashboards): `references/example-session.md`.
