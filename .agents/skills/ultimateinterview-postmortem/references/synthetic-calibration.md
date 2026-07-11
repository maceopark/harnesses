# Synthetic Calibration

Synthetic calibration is a local, reviewed corpus check. It measures fixed
mechanism outcomes against reviewed `accept` or `reject` labels; it is not a
postmortem and does not produce, replace, or promote a real postmortem label.

## Immutable corpus

Store `synthetic-corpus.json` beside the synthetic report. It contains a
nonblank `corpus_version`, a SHA-256 `corpus_digest`, and immutable records:

```json
{
  "corpus_version": "synthetic-v1",
  "records": [
    {
      "case_id": "CAL-001",
      "reviewed_label": "accept",
      "mechanism_results": {"lint": "pass"},
      "elapsed_monotonic_ms": 1.5
    }
  ],
  "corpus_digest": "sha256(canonical JSON of corpus_version plus records)"
}
```

The digest excludes only its own `corpus_digest` field. Each record has a
reviewed label, every named mechanism result, and a non-negative elapsed value
measured from a monotonic clock. No live telemetry, upload, or production
postmortem input belongs in this corpus.

## Advisory measures

`postmortem_lint.py` derives and checks these exact values:

| Metric | Numerator | Denominator |
| --- | --- | --- |
| false-accept | reviewed-negative mechanism results that pass | all reviewed-negative mechanism results |
| false-alarm | reviewed-accept mechanism results that reject | all reviewed-accept mechanism results |
| unique-catch | reviewed-negative cases rejected by exactly one mechanism | reviewed-negative cases |
| cost-milliseconds | total `elapsed_monotonic_ms` | case count |
| cost-cases | record count | record count |

Cost is reported for interpretation only. The linter validates that the
reported cost matches the immutable corpus but has no threshold and never
blocks on a cost value.

## Promotion boundary

Every synthetic report must state exactly:

```text
Promotion: advisory-only; future owner-approved policy required.
```

Automatic threshold promotion is prohibited. Real postmortem labels remain
owned by completed implementation evidence and the normal divergence audit;
synthetic `CAL-NNN` records must not appear in Divergence or Escaped
Requirements tables.

To prevent visually confusable synthetic IDs, the linter applies a fixed
Unicode confusable skeleton to candidate identifiers and rejects a skeleton
that matches a reviewed `CAL-NNN` case. Unrelated non-ASCII identifiers remain
real evidence, not synthetic cases.

Bidirectional formatting controls are rejected when they occur in a
CAL-shaped three-digit candidate, because rendered order can differ from the
stored character order.
