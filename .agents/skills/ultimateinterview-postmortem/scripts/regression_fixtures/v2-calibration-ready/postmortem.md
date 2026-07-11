# Postmortem: synthetic calibration fixture

postmortem_schema: 2

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| immutable local fixture | synthetic-corpus.json | n/a |

## Divergence Table

| ID | Class | Spec reference | Implementation reference |
| --- | --- | --- | --- |
| REQ-001 | fulfilled | Part 1 | fixture |

## Escaped Requirements

| ESC-ID | Failure mode | Requirement structure | Owning frame | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- |

## Wonder Generalization

| Escape ID | Owning frame | Disposition | Store |
| --- | --- | --- | --- |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

| Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect |
| --- | --- | --- | --- | --- | --- | --- |

## Reward-Hacking Review

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | no | no | no | cleared | local fixture only |

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

## Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 1 |
| escaped-requirement | 0 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

| Failure mode | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 0 |
| scoring-starved | 0 |
| answer-unpressured | 0 |
| synthesis-loss | 0 |
| ontology-miss | 0 |

| Structure / modifier / owner | Count |
| --- | --- |
| item | 0 |
| boundary | 0 |
| interaction | 0 |
| system | 0 |
| modifier:negative-space | 0 |
| modifier:runtime-only | 0 |
| owning-frame:none | 0 |

Rates: interview-discovery 100.0%, handoff-fidelity 100.0%.

## Synthetic Calibration

Synthetic corpus: synthetic-corpus.json
Corpus version: synthetic-v1
Corpus digest: 6b4b06f586ae175429d6cfe97483251c04355e4bf8d9f6d29cb59e91da424aff
Promotion: advisory-only; future owner-approved policy required.

| Metric | Value | Denominator |
| --- | --- | --- |
| false-accept | 1 | reviewed-negative-mechanisms:2 |
| false-alarm | 0 | reviewed-accept-mechanisms:2 |
| unique-catch | 1 | reviewed-negatives:1 |
| cost-milliseconds | 3.5 | cases:2 |
| cost-cases | 2 | records:2 |
