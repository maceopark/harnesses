# Session State Files

Schema and edge-case reference for `.ultimateinterview/<slug>/`. The always-on rules (one bookkeeping pass, reload after summarization, dashboard-only echo, channel semantics) are SKILL.md invariants; this file is the field-level law. All scripts validate fail-closed - on a validation error, follow the script's one-line message instead of re-deriving the schema.

Canonical creation path: `scripts/session_init.py <repo-root> <slug> --entries '<json array>'` writes all four working files already valid (schema versions 1, material revision 0, all six lenses `pending` as objects, counters 0, flags false, empty histories), applies the fresh-suffix rule for completed slugs, refuses to overwrite an unfinished session, and ensures `.gitignore` covers `.ultimateinterview`.

Canonical write path: `scripts/session_update.py <session-dir> --delta '<json>'` (delta schema: the script's `--help` and its `Delta` model) - it validates fail-closed, commits ledger/protocol/questions/transcript as one journaled file set, computes history and review digests itself, and emits the dashboards; hand-edit only what a delta cannot express.

## Typed events (delta `event`)

The delta's `event` field makes the script compute every counter. Event-managed counters cannot be set through `protocol` at all, with or without an event.

| Event | Cost | Effects |
| --- | --- | --- |
| `brain-dump` | 1 | `interactions_used`+1, `answers_since_sweep`+1, `brain_dump_done` |
| `framing` | 1 | +1/+1, `framing_challenged` |
| `scored-question` / `bundle` / `batch` | 1 | +1/+1; a scored question requires `asked_question_id`, which derives its target ledger ids and appends its locality snapshot |
| `checkpoint_confirm` (not `event`) | 1 | requires at least one covered id; +1/+1, `falsification_checkpoints_run`+1, `checkpoint_since_last_material_change` true |
| `sweep-asked` | 1 | `interactions_used`+1, cadence reset, `sweeps_run`+1, update dry streak from required `sweep_result` |
| `sweep-free` | 0 | cadence reset, `sweeps_run`+1, update dry streak from required `sweep_result` |
| `contrarian-asked` | 1 | +1/+1, `contrarian_probes_run`+1 |
| `contrarian-free` | 0 | `contrarian_probes_run`+1 |
| `pressure-followup` | 0 | requires `pressure_parent`; increments its persisted count up to 2; a third is rejected and must be sent as `scored-question` |
A scored-question snapshot records `asked_question_id`, its resolved `ledger_ids`, and normalized `categories`, `domains`, and `target_files` derived from those ledger entries' `track` metadata. A `pressure-followup` inherits the latest snapshot; `sweep-asked`, `sweep-free`, `checkpoint_confirm`, `contrarian-free`, and a multi-track batch clear the window. This makes the locality detector replayable from state rather than conversation memory.

Other delta fields (exact shape with an example: `session_update.py --help`):

- `set` (update existing entries by id; schema v1 uses `evidence_records` or `add_evidence_records`; `add_channels` is legacy-only), `add` (full new entries), `protocol` (partial merge; `lenses` merges per-lens), `questions` (validated full replacement, including `[]` to clear), `append_history`, `open_world_sweep`, `probe_decision`, `probe_attempt`, and `sweep_result` (`dry` or `new-gaps`; required only with sweep events). A v1 sweep event requires a same-delta fresh breadth open-world record. A `new-gaps` sweep must add an entry with `origin: "sweep"`; a dry sweep must not. Material probe divergence adds `origin: "probe"`; neutral results cannot mutate ledger settlement. The writer locks the session and journals the prior generation before committing state; the next canonical status/update command recovers an interrupted generation before reading it.
- `transcript`: `{"title": "...", "lines": ["..."], "awaiting": false}` - appends the typed transcript section with the COMPUTED interaction number (costed events get a `## interaction N [marker]` heading; free events get their sub-bullet marker). WITHOUT an event it appends a 0-cost `- [note]` sub-bullet (invitations, process feedback, lane fold-backs) - never hand-append transcript notes. `awaiting: true` marks the line `[awaiting-answer]`; any answer-bearing delta (costed event, `pressure-followup`, or `checkpoint_confirm`) auto-resolves prior awaiting markers to `[answered]` (repo-only `sweep-free`/`contrarian-free` do not). Fails if `transcript.md` is missing.
- `checkpoint_confirm`: `{"ids": [...], "fatigue": false}` - the checkpoint event plus crediting. Schema v1 writes one stable `checkpoint:user:<entry-id>` owner record in `user-dependency:<entry-id>`; repeats do not mint a new causal group. `fatigue: true` counts the run but credits nothing. Mutually exclusive with `event`.
- `build_contract_test`: `{"reviewer": "<agent-or-self-audit-name>"}` - dedicated delta after `handoff.md` exists. For contract schema v1 the writer compiles reviewed Part 1 into strict `build-contract.json` and commits it atomically with `build_contract_tested`, reviewer, and the source Part-1 SHA-256. A later Part-1 edit, invalid sidecar, or stale source digest makes `--gate` fail. Schema v0 keeps digest-only compatibility.
- Pressure gate: a schema-v1 set/add op that puts a weight-3+ user-backed entry below score `2` with fewer than two eligible independence groups is rejected unless the op carries `pressure`: `survived` | `second-channel` | `exempt:<reason>`. An owner/delegated single-source record may explicitly accept one group; that is decision authority, not triangulation. Schema v0 retains channel-counting behavior.

## protocol.json fields

`depth`, `evidence_schema_version`, `contract_schema_version`, `material_revision`, `question_budget` (3/12/20 cap unless `budget_extension_reason` is set), interaction/sweep/checkpoint counters, `checkpoint_since_last_material_change`, framing/intake flags, reviewed-contract fields, `open_world_records`, typed `probe_decision`/`probe_sequence`, `implementer_scout_run`, `pressure_followups_by_parent`, `lenses`, histories, `due_now_corrections`, and `recent_question_tracks`.

Any material requirement, resolution, evidence-record, or probe change increments `material_revision` and resets `checkpoint_since_last_material_change`, `dry_sweeps_in_row`, and the bound build-contract review. Existing open-world records remain as replay history but become stale because their revision binding no longer matches. A checkpoint delta covers its own typed user confirmation without immediately invalidating itself. A ledger mutation without a `questions` replacement clears `questions.json` so a stale queue cannot survive; include the regenerated queue in the same delta when it is already known.

## Migration from the previous helper contract

Old protocol files parse with both schema versions defaulting to `0`, preserving channel-only readiness and digest-only Build Contract behavior. Do not rewrite historical fixtures merely to add v1 fields. New sessions initialize both versions to `1`; v1 readiness additionally requires fresh orientation-before-lens and breadth-before-dry open-world records, a resolved typed probe obligation, structured evidence for settlements, and a valid current sidecar. Legacy `origin: "bundle"` normalizes to `batch` only while parsing old state; v1 writers must emit `batch`.

The initial `protocol.json` written at orientation must already validate: depth, `question_budget`, all six lens decisions (`pending` where genuinely undecided - it blocks handoff until decided), every counter at `0`, all boolean flags `false`, and `residual_history: []` with `gap_count_history: []`. Each lens value is an OBJECT, not a string: `{"state": "pending" | "triggered" | "done" | "skipped", "reason": ""}` - `skipped` requires a non-empty reason.

## Ledger JSON

A list of entries or an object with exactly one populated section among `requirements`, `gaps`, `entries`, or `ledger` - unknown keys, multiple populated sections, duplicate ids, and an empty ledger are rejected. Each entry uses a unique `id`, scores/weight/status, optional `evidence_records`, exact `evidence_channels` projection, optional requirement/reason/structured deferral/origin/track. A v1 evidence record declares `id`, channel, claim kind, source actor, provenance mode, optional derivation, `independence_group`, observation time/environment when runtime-produced, freshness, warrant, counterevidence, epistemic authority, and decision authority. A derived record uses `derivation: {"derived_from": ["<immediate-parent-evidence-id>"], "method": "<explanation>"}`; references must exist, remain acyclic, and resolve to the record's one root independence group. Multiple roots are permitted only when they already share that group. Derived records never add independence credit, and any model-prior, assumption, or hypothesis-only ancestor keeps every descendant hypothesis-only. Only current, firsthand/non-assumption records marked `establishes` earn causal-group credit. `model-prior` and `assumption` are always causal-hypothesis/hypothesis-only.

Channel semantics (the SKILL.md invariant names the closed vocabulary; these are its edge cases): a channel names the evidence *source*, not the elicitation - a user answer is `from-user` even when a scenario question prompted it, so two user statements are one channel and never a triangulation pair; `from-scenario` means a scenario was actually walked against the repo or a running system, constraining the entry independently of the user's judgment (a hypothetical the user narrates is still `from-user`); `assumption` is never an evidence channel and can never triangulate.

`origin` value set (the surfacing mechanism, for postmortem attribution): `orientation`, `dump`, `scored-question`, `pressure`, `batch`, `checkpoint`, `sweep`, `probe`, `contrarian`, `lens:<name>`, `fold-back`. Open-world candidate records use their own literal `origin:open-world` inside `protocol.json`.

Hidden methodology tags use compact ASCII in `reason`; `artifact` is the one structured lens-output field:

- `deficit=<class>` for hidden ORIENT deficit recognition, such as `deficit=context-insufficient` or `deficit=execution-blind`.
- `reverse-evidence=<condition>` for the observation that would shrink, falsify, or complete a hypothesis or lens.
- `artifact` (structured field, not a reason tag): exact enum `ViewpointMatrix|StateModel|GoalObstacleMap|MisuseCaseSet|QualityScenarioSet|ControlledAcceptanceCriteria`; required when `state` is `done`, forbidden otherwise, and must match the lens.
- `skip=<reason>` when a lens is skipped or marked done because no reverse-evidence remains.

The text tags are conventions for auditability; `artifact` is modeled and enforced in `protocol.json`. Do not rely on any other unmodeled field being preserved, ranked, emitted, or enforced.

## Question JSON

A list of candidates or an object with `questions` or `candidates`. Each candidate uses `id`, `question`, `impact`, `branch_split`, `uncertainty_reduction`, `coverage`, `user_cost`, `redundancy`, and `target_ids` (the ledger ids the question addresses). Booking `event: "scored-question"` requires its `asked_question_id` and nonempty, extant `target_ids`.

## Crash, resume, and environment rules

- In-flight state must survive a crash: an asked-but-unanswered question is `[awaiting-answer]` in the transcript; its selected `asked_question_id` and derived locality snapshot are in `recent_question_tracks`; a pressure-pending entry stays at score `2` with `pressure-pending` in its reason; batchable-but-unflushed gaps live in `questions.json` as candidates. The journal recovers interrupted writes before status/update reads, so the locality window and its sweep reset replay from files alone.
- Re-interviewing a slug that already has a handoff gets a fresh suffixed folder (`<slug>-2`); never overwrite a completed session.
- If writes are blocked (plan mode, read-only harness, no repo root), do not stall Orientation: keep the ledger and protocol state inline in the conversation, say so, and persist all session files verbatim at the first write opportunity, noting `deferred-writes` in the transcript.
- Language protocol: interview in the user's language; write artifacts (ledger, protocol, handoff) in the repo's documentation language (default English) unless the user asks otherwise. Verbatim answers stay in the language they were given, and the ubiquitous-language table carries the user-language term beside the repo term when they differ.
- When the harness has a todo/task tracker, mirror the interview phases in it (orient → dump+frame → loop → checkpoint → gates → handoff), updating at phase transitions only - visible progress is fatigue mitigation.
- `transcript.md` format: `references/transcript-format.md`. A complete worked session (all four files, real dashboards): `references/example-session.md`.
