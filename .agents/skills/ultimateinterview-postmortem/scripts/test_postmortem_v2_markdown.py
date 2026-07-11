#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8"]
# ///

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import TypedDict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import postmortem_v2_calibration as calibration


class CorpusRecord(TypedDict):
    case_id: str
    reviewed_label: str
    mechanism_results: dict[str, str]
    elapsed_monotonic_ms: float


class SyntheticCorpusDocument(TypedDict):
    corpus_version: str
    records: list[CorpusRecord]
    corpus_digest: str


def _corpus() -> SyntheticCorpusDocument:
    records: list[CorpusRecord] = [
        {
            "case_id": "CAL-001",
            "reviewed_label": "accept",
            "mechanism_results": {"lint": "pass", "taxonomy": "pass"},
            "elapsed_monotonic_ms": 1.5,
        },
        {
            "case_id": "CAL-002",
            "reviewed_label": "reject",
            "mechanism_results": {"lint": "reject", "taxonomy": "pass"},
            "elapsed_monotonic_ms": 2.0,
        },
    ]
    corpus_version = "synthetic-v1"
    preimage = {"corpus_version": corpus_version, "records": records}
    digest = hashlib.sha256(json.dumps(preimage, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return {"corpus_version": corpus_version, "records": records, "corpus_digest": digest}


def _report(corpus: SyntheticCorpusDocument) -> str:
    return f"""# Postmortem: synthetic-only

postmortem_schema: 2

## Synthetic Calibration

Synthetic corpus: synthetic-corpus.json
Corpus version: {corpus["corpus_version"]}
Corpus digest: {corpus["corpus_digest"]}
Promotion: advisory-only; future owner-approved policy required.

| Metric | Value | Denominator |
| --- | --- | --- |
| false-accept | 1 | reviewed-negative-mechanisms:2 |
| false-alarm | 0 | reviewed-accept-mechanisms:2 |
| unique-catch | 1 | reviewed-negatives:1 |
| cost-milliseconds | 3.5 | cases:2 |
| cost-cases | 2 | records:2 |
"""


def _evaluate(tmp_path: Path, real_evidence: str) -> tuple[str, ...]:
    corpus = _corpus()
    report = _report(corpus) + real_evidence
    _ = (tmp_path / "synthetic-corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    return calibration.evaluate_synthetic_calibration(tmp_path, report).violations


@pytest.mark.parametrize(
    "benign_text", ("C-AL notation", "C A L notation", "CA1-002 reference", "Δ-123 reference", "é-002 reference")
)
def test_synthetic_calibration_allows_unrelated_cal_text_in_real_evidence(
    tmp_path: Path, benign_text: str
) -> None:
    # Given, When
    violations = _evaluate(tmp_path, f"\n## Escaped Requirements\n\n{benign_text} is unrelated evidence.\n")

    # Then
    assert violations == ()


@pytest.mark.parametrize(
    "obfuscated_id",
    (
        "C**AL**-002",
        "CAL-001",
        "CAL&#45;002",
        "CAL<!-- -->-002",
        "CAL<span></span>-002",
        "CAL\\-002",
        "C[AL](https://example.invalid)-002",
        "C[AL](https://example.invalid/segment(one))-002",
        "C[AL](https://example.invalid/foo\\)bar)-002",
        "C[AL][r]-002\n\n[r]: https://example.invalid",
        "C[AL][]-002\n\n[AL]: https://example.invalid",
        "C\u200dAL-002",
        "C\u034fAL-002",
        "CAL\ufe0f-002",
        "CAL-\u202e200\u202c",
        "САL-002",
        "CΑL-002",
        "ϹΑL-002",
        "ⲤΑL-002",
    ),
)
def test_synthetic_calibration_rejects_an_obfuscated_real_case_id(
    tmp_path: Path, obfuscated_id: str
) -> None:
    # Given, When
    violations = _evaluate(
        tmp_path,
        "\n## Divergence Table\n\n| ID | Class |\n| --- | --- |\n"
        f"| {obfuscated_id} | escaped-requirement |\n",
    )

    # Then
    assert any("misfiled as real postmortem" in violation for violation in violations)
