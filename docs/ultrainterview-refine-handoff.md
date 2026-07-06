# Spec: Ultrainterview false-ready hardening + rehearsal

# Part 1 — Build Contract

Self-sufficiency rule: an implementer with no access to this interview reads only this part and can build the change.

## Goal

Make it impossible for the ultrainterview skill to report `handoff_ready`/`protocol_ready` on a spec that is actually incomplete (the "false-ready" failure), then prove it by running one synthetic rehearsal interview end-to-end.

## Target Surface

| File / module | Expected change |
| --- | --- |
| `~/.agents/skills/ultrainterview/scripts/ambiguity_ledger.py` | Add `extra="forbid"` to `LedgerDocument`; error when a parsed document normalizes to zero entries (zero-entry check takes precedence over the multi-section check when all sections are empty); error when more than one section (`requirements`/`gaps`/`entries`/`ledger`) is non-empty; validate `status` (case-insensitive) against exactly: the six documented values `draft`, `triangulated`, `contested`, `blocked`, `accepted`, `deferred`, plus the existing synonym sets `DEFERRED_STATUSES` and `accepted-single-source`; keep the `Accepted` single-source waiver but require ≥1 non-`assumption` channel for it (the existing one-`from-user`-channel test case keeps passing; zero-channel or assumption-only `Accepted` weight-5 at score 0 becomes an untriangulated blocker); add a report-only `contested` list (entry ids with status `contested`) as a `contested` key in JSON output and a `### Contested` section in markdown; wrap parse/read in try/except → clean `typer.BadParameter` (no raw traceback); reject a directory path (`is_file()`); reject duplicate entry ids |
| `~/.agents/skills/ultrainterview/scripts/protocol_state.py` | Add validator `stagnation_escalated_at <= len(residual_history)`; add depth→budget cap check (error when `question_budget` strictly exceeds minimal=3 / focused=12 / full=20) unless a new `budget_extension_reason: str` field is non-empty (add the field to the schema, default `""`); add new field `gap_count_history: tuple[int, ...]` (active-gap count appended alongside each residual) and redefine `is_stagnant` to fire only when residual is non-decreasing AND gap count is non-increasing across the window (a round that adds gaps never counts as stagnant); add obligation when `interactions_used - len(residual_history) >= 2` ("residual_history lags interactions - stagnation detection degrading"); wrap parse/read like the ledger script; reject a directory path |
| `~/.agents/skills/ultrainterview/scripts/question_score.py` | Add `extra="forbid"` to `QuestionDocument`; error on dual-populated sections; error when a document normalizes to zero candidates (covers both well-keyed-but-empty `{"questions": []}` and the post-`forbid` residue); clean error UX; reject a directory path and duplicate ids |
| `~/.agents/skills/ultrainterview/scripts/test_deterministic_helpers.py` | Add coverage for every new rejection above + the untested behaviors listed in finding A9 (mixed/unknown sections, empty ledger, Accepted-zero-channels, escalated_at overflow, rising-residual, depth↔budget, CLI layer, status vocabulary) |
| `~/.agents/skills/ultrainterview/SKILL.md` | Fix B2 (restate the stop condition as "handoff_ready AND protocol blockers ⊆ {build-contract}" at all 4 occurrences); fix B11 (make the six Orientation ledger sections a conceptual taxonomy expressed inside one recognized container key, or delete them — must not produce a document the hardened script rejects); fix B1 by documenting the new `gap_count_history` field and the revised stagnation rule (fires only when residual non-decreasing AND gap count non-increasing) plus `budget_extension_reason`; delete prose promises the scripts now enforce (net non-increase in size per principle G7) |
| `~/.agents/skills/ultrainterview/references/example-session.md` (new) | The rehearsal's four session files + final Build Contract, as the worked example (D2) |
| `~/.agents/skills/ultrainterview/references/` (transcript format) | A ~15-line transcript convention (D1): one heading per interaction with a typed marker (`[scored-question]`/`[batch]`/`[checkpoint]`/`[pressure-followup]`/`[sweep]`) and an `interaction: N` counter |

## Behavior Contract

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| REQ-1 | Unknown/typo'd top-level ledger key is rejected, not parsed as empty | `If a ledger document has any key outside {requirements,gaps,entries,ledger}, then ambiguity_ledger.py shall exit non-zero with an actionable message.` |
| REQ-2 | Zero-entry document is never handoff-ready | `When a ledger normalizes to zero entries, ambiguity_ledger.py shall not report handoff_ready: yes (error or explicit empty-ledger blocker).` |
| REQ-3 | Multiple populated sections are rejected | `If more than one of requirements/gaps/entries/ledger is non-empty, then the script shall error rather than silently pick one.` |
| REQ-4 | Status vocabulary is validated | `If an entry status (case-insensitive) is outside {draft, triangulated, contested, blocked, accepted, deferred} ∪ DEFERRED_STATUSES ∪ {accepted-single-source}, then the script shall reject it.` |
| REQ-5 | `Accepted` cannot waive triangulation with zero evidence | `While an Accepted weight-5 entry at score 0 has zero non-assumption channels, the script shall treat it as an untriangulated blocker; with ≥1 non-assumption channel the single-source waiver continues to apply (existing test case preserved).` |
| REQ-6 | Contested entries are surfaced | `The summary shall list every entry with status contested: a "contested" key (entry ids) in JSON output and a "### Contested" section in markdown (report-only, not a readiness blocker).` |
| REQ-7 | `stagnation_escalated_at` beyond history is rejected | `If stagnation_escalated_at > len(residual_history), then protocol_state.py shall reject the file.` |
| REQ-8 | Depth↔budget is consistent | `If question_budget strictly exceeds the cap for its depth (minimal 3, focused 12, full 20) and budget_extension_reason is empty, then protocol_state.py shall reject it (budget exactly at cap remains valid - existing fixtures pass).` |
| REQ-9 | Validation failures are actionable, not tracebacks | `When input is malformed, a directory, or schema-invalid, the script shall emit a one-line actionable error and exit non-zero - verified through the CLI via typer CliRunner (exit code + message), not only via library-level exceptions.` |
| REQ-10 | Productive divergence is not flagged as stagnation | `While the gap_count_history window shows the active-gap count increased in any round of the window, the stagnation obligation shall not fire; it fires only when residual is non-decreasing AND gap count is non-increasing across the window.` |
| REQ-11 | Rehearsal reaches a real handoff without a false-ready shortcut | `Given the hardened scripts, when the synthetic rehearsal interview runs to completion, then handoff.md is produced only after both helpers report ready on a ledger with ≥8 entries that exercised ≥1 triggered lens, ≥1 pressure follow-up, ≥1 smart-default batch, and ≥1 falsification checkpoint, and the run's session files (ledger.json, protocol.json, questions.json, transcript.md) plus the final Build Contract are embedded verbatim in references/example-session.md.` |
| REQ-12 | question_score never "ranks" nothing silently | `When a question document normalizes to zero candidates, question_score.py shall exit non-zero with an actionable message instead of printing an empty ranking.` |
| REQ-13 | Residual-history lag is surfaced | `When interactions_used - len(residual_history) >= 2, protocol_state.py shall emit a Due-Now obligation naming the lag.` |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Exact error message wording | yes | Must name the offending key/field and be one line |
| Whether empty-ledger is a hard error vs an explicit `handoff_ready: false` blocker | yes | Either is acceptable; must not report ready |
| New protocol.json fields (`gap_count_history`, `budget_extension_reason`) | authorized | Both are additive with safe defaults; SKILL.md field list must document them (this is the one permitted prose addition, offset by deleted promises) |
| Exact obligation message wording for REQ-13 | yes | Must name the lag |
| Synthetic rehearsal's example request | yes | Any realistic brownfield change; must exercise at least one triggered lens and one pressure follow-up |
| SKILL.md prose trimmed vs the references/ split | no | Full references/ cost-diet (C) is DEFERRED; this round only deletes now-redundant enforcement promises |

## Out Of Scope / Non-Goals

- Rest of cluster B (interaction-accounting rework, from-scenario channel definition, lens lifecycle `pending` state, checkpoint-loop termination), all of cluster C (46k→references/ split), rest of cluster D (language protocol, AskUserQuestion mapping, plan-mode guard, fatigue signal, run-1 instrumentation origin/timestamps/exit-check, self-reference rules, abandonment artifact, consumer-preamble, global lessons) — all DEFERRED with the user's checkpoint sign-off.
- The 4 standing rejections (MCQ removal, MCP migration, automatic protocol.json recording, postmortem restructure) stay rejected.
- No change to the postmortem skill body or `agents/openai.yaml` (record the cross-harness delta only if convenient).

## Implementation Constraints

- Interfaces: the three scripts keep their CLI (`--format`, `--top`, stdin, path arg) and JSON/markdown outputs; new rejections are additive, existing valid inputs must still pass.
- Compatibility: the current session's own `ledger.json`/`protocol.json` (this refine session) must still validate under the hardened scripts — run them against it as a regression check.
- Governing principle (G7): enforcement lives in scripts (fail-closed), not new SKILL.md prose; SKILL.md size must not increase net.

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Existing suite still green | `cd ~/.agents/skills/ultrainterview && uv run scripts/test_deterministic_helpers.py` | all prior + new tests pass |
| False-ready repros now rejected | synthesize one input per REQ-1..REQ-10 from the behavior contract (the reviewer's original repro catalogue is in Part 2 / findings.md §Cluster A, available on dispute) and run each against the hardened scripts | every one exits non-zero with an actionable message (no `handoff_ready: yes`) |
| This session regresses clean | run both helpers against `.ultrainterview/ultrainterview-refine/{ledger,protocol}.json` | same ready/blocker verdicts as today |
| Rehearsal produces a real handoff | run the synthetic interview end-to-end | `references/example-session.md` exists with a non-empty ledger and a handoff reached only via both-helpers-ready |
| SKILL.md did not grow | `wc -c SKILL.md` before/after | after ≤ before |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| Cluster A makes completion trustworthy but does nothing for discovery rate; a thin rehearsal ledger would be an escaped-requirements (#1) problem this round deferred | user | after rehearsal | The rehearsal itself is the probe — if its ledger looks thin, reprioritize the deferred lens/enumeration work (contrarian probe finding) |
| The deferred B/C/D set is large; deferring is the user's explicit choice, not an oversight | user | after rehearsal | Revisit informed by real rehearsal data; council re-review waits for ≥1 real interview |
| Per-answer bookkeeping cost (C1, ~30-60k tokens/interview) remains unfixed | user | deferred | Out of scope this round |

## Fresh-Implementer Test

| Reviewer | "Would have to ask" items found | Folded back as gaps? |
| --- | --- | --- |
| Fresh-context subagent (Part 1 only, no conversation/ledger/Part 2) | 12 items, 5 blockers: REQ-4 six statuses unenumerated; REQ-5 waiver-tightening ambiguous vs existing test; REQ-6 contested input signal undefined; REQ-10 stagnation redefinition required an unauthorized new field and contradicted current rising=stagnant logic; "materially lags" threshold undefined. Plus 7 clarifications (CLI test harness, repro location, session-file set, rehearsal minimum bar, REQ-2/3 precedence, question_score acceptance row, extension-field shape). | Yes - all 12 resolved by contract edits in this revision (none required a user decision; each was settled from already-approved scope and evidence). No interview-reopening gap found. |

# Part 2 — Audit Trail

## Problem

A solo developer built ultrainterview and, after 6 static-review rounds, feels general anxiety that specs it produces could be weak. The skill has never run a real interview. Root-cause reframe (accepted at checkpoint): the fear is concretely **false-ready** — the skill declaring completion on an incomplete spec — and the deeper gap is zero field data.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | "make it complete" reframed to "make completion trustworthy + prove it once" |
| Do-nothing option | Not defensible for cluster A (execution-confirmed contradictions of the fail-closed promise) |
| Simpler alternative | Fix blockers + one rehearsal, instead of a 7th exhaustive static pass — user confirmed |
| Artifact class confirmed | Spec for a fix round + a rehearsal, not textual polish |

## Existing Evidence

| Source | Evidence |
| --- | --- |
| from-code | 31/31 tests pass; scripts read in full; skill symlinked; not under git |
| from-scenario | reviewer 2 executed every cluster-A repro against the real scripts; refuted 11 candidates |
| from-user | trigger=anxiety, no queued task, fear=false-ready, verification=(a) rehearsal |
| from-research | reviewer 3 field-readiness design audit (transcript format, worked example, harness mapping) |

## Triggered Lenses

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | done | four-consumer analysis surfaced the D cluster |
| domain/state | done | protocol.json state machine; A/B are its broken guards |
| goal/obstacle | done | goal=trustworthy completion; obstacle=fail-open + false rehearsal |
| misuse | skipped | no security/privacy/irreversible surface |
| quality | done | "complete" made measurable = rehearsal reaches handoff, no false-ready |
| controlled-language | done | fix acceptance criteria observable in verification commands |

## Requirements Ledger

Source of truth: `.ultrainterview/ultrainterview-refine/ledger.json`. Settled: F1-F9 (facts), G1 (dimension=false-ready), G5 (vehicle=rehearsal), G6 (staging), G2 (scope), G4 (rejections), G7 (principle). Deferred: G3 (council ideas).

## Ambiguity Dashboard

Residual 19 / denominator 171 (11%, informational). Handoff ready: yes (blocker-based). No active score 2/3 gaps; both weight-5 settlements triangulated (2 channels each).

## Protocol Dashboard

Depth full, 3/20 interactions used. Only outstanding blocker before this test: build-contract fresh-implementer test.

## Q&A Record

Condensed in `.ultrainterview/ultrainterview-refine/transcript.md`: dump (I1) → pressure+vehicle (I2) → falsification checkpoint "다 맞음" (I3) → sweep (nothing new) → contrarian probe (model survived, escaped-requirements risk recorded) → lens completion.

## Contested Log

None — no user claim contradicted repo evidence this interview.

## Restated Approval Check

- Final goal: make false-ready impossible, prove via one rehearsal.
- Key non-goals: rest of B, all C, rest of D, the 4 rejections.
- Important assumptions: plain-file + script model is sufficient (no MCP).
- Deferred risks: discovery-rate untouched; large deferred set; bookkeeping cost.
- Boundaries: enforcement→scripts, SKILL.md no net growth.
- Verification: hardened tests + rehearsal reaching a real handoff.
- Approval status: draft pending approval.
