#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import postmortem_lint
import postmortem_v2_calibration as calibration

FIXTURES = Path(__file__).parent / "regression_fixtures"
RUNNER = CliRunner()
type Record = dict[str, str | float | dict[str, str]]
type Corpus = dict[str, str | list[Record]]
type ReportTransform = Callable[[Corpus], str]


def _corpus(records: list[Record]) -> Corpus:
    preimage: Corpus = {"corpus_version": "synthetic-v1", "records": records}
    digest = hashlib.sha256(
        json.dumps(preimage, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    corpus: Corpus = {**preimage, "corpus_digest": digest}
    return corpus


def _records() -> list[Record]:
    return [
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


def _report(corpus: Corpus) -> str:
    return f"""# Postmortem: synthetic-only

postmortem_schema: 2

## Synthetic Calibration

Synthetic corpus: synthetic-corpus.json
Corpus version: {corpus.get("corpus_version", "missing")}
Corpus digest: {corpus.get("corpus_digest", "missing")}
Promotion: advisory-only; future owner-approved policy required.

| Metric | Value | Denominator |
| --- | --- | --- |
| false-accept | 1 | reviewed-negative-mechanisms:2 |
| false-alarm | 0 | reviewed-accept-mechanisms:2 |
| unique-catch | 1 | reviewed-negatives:1 |
| cost-milliseconds | 3.5 | cases:2 |
| cost-cases | 2 | records:2 |
"""


def _session(tmp_path: Path, corpus: Corpus, report: str) -> Path:
    session = tmp_path / "session"
    session.mkdir(parents=True)
    _ = (session / "synthetic-corpus.json").write_text(json.dumps(corpus), encoding="utf-8")
    _ = (session / "postmortem.md").write_text(report, encoding="utf-8")
    return session


def test_synthetic_calibration_derives_reviewed_denominators_and_advisory_cost(
    tmp_path: Path,
) -> None:
    # Given
    corpus = _corpus(_records())
    session = _session(tmp_path, corpus, _report(corpus))

    # When
    evaluation = calibration.evaluate_synthetic_calibration(
        session, (session / "postmortem.md").read_text(encoding="utf-8")
    )

    # Then
    assert evaluation.violations == ()
    assert evaluation.summary == "synthetic calibration (advisory): 2 cases, 3.5 ms"


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        ("missing-version", "corpus_version"),
        ("missing-digest", "corpus_digest"),
        ("unknown-label", "reviewed_label"),
    ),
)
def test_synthetic_corpus_rejects_missing_identity_or_unknown_reviewed_label(
    tmp_path: Path, case: str, expected: str
) -> None:
    # Given
    corpus = _corpus(_records())
    match case:
        case "missing-version":
            del corpus["corpus_version"]
        case "missing-digest":
            del corpus["corpus_digest"]
        case "unknown-label":
            records = _records()
            records[0]["reviewed_label"] = "undecided"
            corpus = _corpus(records)
        case unexpected:
            pytest.fail(f"unexpected case: {unexpected}")
    session = _session(tmp_path, corpus, _report(corpus))

    # When
    evaluation = calibration.evaluate_synthetic_calibration(
        session, (session / "postmortem.md").read_text(encoding="utf-8")
    )

    # Then
    assert any(expected in violation for violation in evaluation.violations)


@pytest.mark.parametrize(
    ("replacement", "expected"),
    (
        ("reviewed-negative-mechanisms:2", "false-accept denominator"),
        ("| false-accept | 1 |", "false-accept count"),
        ("advisory-only; future owner-approved policy required.", "promotion"),
    ),
)
def test_synthetic_calibration_rejects_wrong_denominator_count_or_promotion(
    tmp_path: Path, replacement: str, expected: str
) -> None:
    # Given
    corpus = _corpus(_records())
    report = _report(corpus).replace(
        replacement,
        {
            "reviewed-negative-mechanisms:2": "reviewed-negative-mechanisms:1",
            "| false-accept | 1 |": "| false-accept | 0 |",
            "advisory-only; future owner-approved policy required.": "automatic threshold promotion",
        }[replacement],
    )
    session = _session(tmp_path, corpus, report)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(session, report)

    # Then
    assert any(expected in violation for violation in evaluation.violations)


def test_synthetic_calibration_rejects_a_synthetic_case_misfiled_as_real_postmortem(
    tmp_path: Path,
) -> None:
    # Given
    corpus = _corpus(_records())
    report = _report(corpus) + "\n## Divergence Table\n\n| ID | Class |\n| --- | --- |\n| CAL-002 | escaped-requirement |\n"
    session = _session(tmp_path, corpus, report)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(session, report)

    # Then
    assert any("misfiled as real postmortem" in violation for violation in evaluation.violations)


@pytest.mark.parametrize(
    ("report", "expected"),
    (
        (
            lambda corpus: _report(corpus).replace(
                "Promotion: advisory-only; future owner-approved policy required.",
                "Promotion: advisory-only; future owner-approved policy required.\n"
                "Promotion: automatic threshold promotion",
            ),
            "promotion",
        ),
        (
            lambda corpus: _report(corpus).replace(
                "## Synthetic Calibration\n",
                "## Synthetic Calibration\nPromotion: automatic threshold promotion\n\n"
                "## Synthetic Calibration\n",
                1,
            ),
            "exactly one",
        ),
    ),
)
def test_synthetic_calibration_rejects_duplicate_metadata_or_sections(
    tmp_path: Path, report: ReportTransform, expected: str
) -> None:
    # Given
    corpus = _corpus(_records())
    rendered = report(corpus)
    session = _session(tmp_path, corpus, rendered)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(session, rendered)

    # Then
    assert any(expected in violation for violation in evaluation.violations)


@pytest.mark.parametrize(
    ("report", "expected"),
    (
        (
            lambda corpus: _report(corpus).replace(
                "| false-accept | 1 | reviewed-negative-mechanisms:2 |",
                "| false-accept | 999 | reviewed-negative-mechanisms:999 |\n"
                "| false-accept | 1 | reviewed-negative-mechanisms:2 |",
            ),
            "duplicate metric",
        ),
        (
            lambda corpus: _report(corpus).replace(
                "| false-accept | 1 | reviewed-negative-mechanisms:2 |",
                "| false-accept | 999 | reviewed-negative-mechanisms:2 | surplus |\n"
                "| false-accept | 1 | reviewed-negative-mechanisms:2 |",
            ),
            "malformed metric",
        ),
    ),
)
def test_synthetic_calibration_rejects_duplicate_or_malformed_metric_rows(
    tmp_path: Path, report: ReportTransform, expected: str
) -> None:
    # Given
    corpus = _corpus(_records())
    rendered = report(corpus)
    session = _session(tmp_path, corpus, rendered)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(session, rendered)

    # Then
    assert any(expected in violation for violation in evaluation.violations)


def test_synthetic_calibration_rejects_nonfinite_elapsed(tmp_path: Path) -> None:
    # Given
    records = _records()
    records[0]["elapsed_monotonic_ms"] = float("inf")
    corpus = _corpus(records)
    report = _report(corpus).replace("| cost-milliseconds | 3.5 |", "| cost-milliseconds | inf |")
    session = _session(tmp_path, corpus, report)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(session, report)

    # Then
    assert any("elapsed_monotonic_ms" in violation for violation in evaluation.violations)


def test_synthetic_calibration_rejects_an_external_corpus_symlink(tmp_path: Path) -> None:
    # Given
    corpus = _corpus(_records())
    session = _session(tmp_path / "session", corpus, _report(corpus))
    external = tmp_path / "external-corpus.json"
    _ = external.write_text(json.dumps(corpus), encoding="utf-8")
    target = session / "synthetic-corpus.json"
    target.unlink()
    target.symlink_to(external)

    # When
    evaluation = calibration.evaluate_synthetic_calibration(
        session, (session / "postmortem.md").read_text(encoding="utf-8")
    )

    # Then
    assert any("regular non-symlink" in violation for violation in evaluation.violations)


def test_postmortem_lint_cli_accepts_ready_synthetic_calibration_and_rejects_mismatch() -> None:
    # Given
    ready = FIXTURES / "v2-calibration-ready"
    mismatch = FIXTURES / "v2-calibration-mismatch"

    # When
    passing = RUNNER.invoke(postmortem_lint.app, [str(ready)])
    failing = RUNNER.invoke(postmortem_lint.app, [str(mismatch)])

    # Then
    assert passing.exit_code == 0, passing.output
    assert "synthetic calibration (advisory)" in passing.output
    assert failing.exit_code == 1
    assert "false-accept denominator" in failing.output
