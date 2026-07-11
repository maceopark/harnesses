# Postmortem Output Templates

Two skeletons: the per-change postmortem report, and the durable lessons file.

## 1. Postmortem Report

Write to `.ultimateinterview/<slug>/postmortem.md`.

# Postmortem: <slug>

postmortem_schema: 2

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| PR / commits / branch / working tree |  |  |

Handoff written: <date>. Implementation examined through: <date/commit>.

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Supporting diff paths | Note |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled / scope-drift / divergent-implementation / deferred-outcome |  |  | `path/to/production.py` |  |
| ESC-001 | escaped-requirement | absent |  | `path/to/production.py` |  |

## Escaped Requirements

One `ESC-NNN` row here per `escaped-requirement` row in the Divergence Table. The lint enforces the exact Divergence → Escaped Requirements → Wonder join; a fulfilled Part-1 `REQ-NNN` cannot double as an escape. Weight uses the ledger impact scale.

| ESC-ID | Behavior found in code | Failure mode | Requirement structure | Owning frame | Weight | Intent attribution | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ESC-001 |  | trigger-too-narrow / enumeration-miss / scoring-starved / answer-unpressured / synthesis-loss / ontology-miss | item / boundary / interaction / system / novel:<slug>, optionally +negative-space and/or +runtime-only | viewpoint / domain/state / goal/obstacle / misuse / quality / controlled-language / core-path / none | 1/2/3/5 | owned-signal:<ref> / run-blind | new / strengthened / deduped / not-routing/synthesis-loss / not-routing/ontology-miss |  |  |

`Intent attribution` is a closed structural vocabulary: `owned-signal:<decision-id|capture-id>` identifies an owned validated signal; `run-blind` records no owned signal. It does not reconstruct a motive, and a REQ-named test or prose never lifts `run-blind`.

`ontology-miss` requires `owning frame:none`, a `novel:<slug>` base, `not-routing/ontology-miss`, and no lesson store/write. A `negative-space` row must cite an observed bundle artifact; any external artifact kind is sufficient. Use `core-path` for always-on machinery. `known-deferred` items are not escapes.
## Wonder Generalization

Run one bounded pass after escape classification. One row per escape, joined by `ESC-NNN`; the actual lesson remains in Lessons Appended Or Updated. Ontology misses never route or write a lesson.

| Escape ID | Unknown class | Interview-time observable signal | Owning frame | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| ESC-001 |  |  |  | new / strengthened / deduped / not-routing/synthesis-loss / not-routing/ontology-miss |  |  |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
|  |  | yes/no |  |

## Verification Execution

For a stable-v5 bundle, join each row to the validated ExecutionReturn by `VER-ID` and contract digest. Reordering cannot change the join. Legacy schema-v3/v4 evidence uses the positional `Spec row` table instead and never proves a pass without a matching capture.

| VER-ID | Check | Kind | Execution | Result | Captured artifact | Observed effect |
| --- | --- | --- | --- | --- | --- | --- |
| VER-001 | Unit/behavior suite | test | exact | pass | artifact-... | Tests passed; captured output records the run. |

## Reward-Hacking Review

One row per Part-1 REQ-ID. This is a human-entered consistency record, not an automated path classification: `audit_scan.py` candidates remain advisory. Any `yes` in mock substitution, tautological assertion, or hardcoded expected requires `confirmed-gaming`, which requires `divergent-implementation`. `legitimate-test-doc-only` requires nonblank rationale/evidence.

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | no | no | no | cleared | Production path and assertion were reviewed. |
| REQ-002 | fulfilled | no | no | no | no | legitimate-test-doc-only | Documentation-only REQ; no production change was expected. |

## Scope Drift / Divergent Implementations

| Item | Class | What the handoff said | What was built | User must re-decide? |
| --- | --- | --- | --- | --- |
|  | scope-drift / divergent-implementation |  |  | yes/no |

## Lessons Appended Or Updated

| Signal | Lens to trigger | Failure class | Evidence | Date |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Lessons Fire-Tracking

One row per lesson active AT AUDIT START per store, every run - `no-signal` is a verdict, not a reason to skip the row. `postmortem_lint.py` validates this table against the bundle's audit-start lessons snapshot (not the live store, which the run may have emptied) and fails the report on any missing row.

| Store | Row | Signal (truncated) | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md / ultimateinterview-lessons.md | 1 |  | fired / no-signal | caught / dry / - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled |  |
| escaped-requirement |  |
| scope-drift |  |
| divergent-implementation |  |
| deferred-outcome (materialized / total) |  |

| Failure class | Count |
| --- | --- |
| trigger-too-narrow |  |
| enumeration-miss |  |
| scoring-starved |  |
| answer-unpressured |  |
| synthesis-loss (interview caught it; handoff drafting narrowed/dropped it) |  |
| ontology-miss |  |

| Structure / modifier / owner | Count |
| --- | --- |
| item |  |
| boundary |  |
| interaction |  |
| system |  |
| novel:<slug> (one row per observed novel base) |  |
| modifier:negative-space |  |
| modifier:runtime-only |  |
| owning-frame:none |  |

Rates - recomputed from the Divergence Table by `postmortem_lint.py`; state both, plus the weighted pair when any escape exists:

- interview-discovery: `fulfilled / (fulfilled + non-synthesis-loss escapes + divergent-implementation)` = N%
- handoff-fidelity: `fulfilled / (fulfilled + all escapes + divergent-implementation)` = N%
- weighted (escape/divergent rows enter the denominator at their impact weight): N% / N%

### Synthetic Calibration (optional and separate)

Use this section only with an immutable local `synthetic-corpus.json`; it is
not a real postmortem row source. See
[`synthetic-calibration.md`](synthetic-calibration.md) for the canonical corpus
digest and denominator definitions.

```text
Synthetic corpus: synthetic-corpus.json
Corpus version: <reviewed version>
Corpus digest: <reviewed SHA-256>
Promotion: advisory-only; future owner-approved policy required.
```

| Metric | Value | Denominator |
| --- | --- | --- |
| false-accept |  | reviewed-negative-mechanisms:<N> |
| false-alarm |  | reviewed-accept-mechanisms:<N> |
| unique-catch |  | reviewed-negatives:<N> |
| cost-milliseconds |  | cases:<N> |
| cost-cases |  | records:<N> |

Cost is advisory only. Do not insert synthetic `CAL-NNN` records into
Divergence Table or Escaped Requirements, and do not auto-promote a label.

## 2. Lessons File Skeleton

Create as `docs/ultimateinterview-lessons.md` in the repo root (repo-specific signals) or `~/.agents/skills/ultimateinterview/lessons.md` (repo-agnostic signals, compounds across repos) when missing. Append rows; dedupe against both files first.

# Ultimateinterview Lessons

Signal-to-lens routing rules learned from spec postmortems. The `ultimateinterview` skill reads this file during Orientation: when a signal below appears in a new request or the touched code, treat the named lens as triggered. Keep signals observable at interview time, never hindsight. `Fired/Caught` is fire-tracking: postmortems increment Fired when the signal appeared, Caught when the triggered lens actually produced a ledger entry; Fired ≥ 3 with Caught 0 retires the row.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  | 0/0 |

## Retired

Rows moved here after 3 dry fires (signal appeared, lens caught nothing). Kept for the record; Orientation skips them.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
|  |  |  |  |
