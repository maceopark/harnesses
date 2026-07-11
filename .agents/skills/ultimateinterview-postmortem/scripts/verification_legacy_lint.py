#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)

from postmortem_lint import first_table, section_body, split_sections  # noqa: E402
from verification_contract import (  # noqa: E402
    CAPTURED_OUTPUT_MARKER,
    CapturedOutput,
    VerificationRow,
    canonical_command_digest,
    captured_output_matches,
    effective_heads,
    row_identity,
)

BUNDLE_FILENAME: Final[str] = "evidence_bundle.json"
VIOLATION_PREFIX: Final[str] = "verification-execution:"
CANONICAL_COLUMNS: Final[tuple[str, ...]] = (
    "Spec row",
    "Check",
    "Kind",
    "Execution",
    "Result",
    "Captured artifact",
    "Observed effect",
)
EXECUTIONS: Final[frozenset[str]] = frozenset(
    {"exact", "adapted", "not-run", "skipped"}
)
RESULTS: Final[frozenset[str]] = frozenset(
    {"pass", "fail", "skipped", "not-run", "adapted-pass"}
)
INTEGER: Final[re.Pattern[str]] = re.compile(r"[1-9][0-9]*")


class EvaluationInputError(Exception):
    """A present required input cannot be read or validated."""


@dataclass(frozen=True, slots=True)
class ReportRow:
    number: int
    spec_row: int | None
    check: str
    kind: str
    execution: str
    result: str
    artifact_id: str
    observed_effect: str


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    artifact_id: str
    record: CapturedOutput


def report_violation(message: str) -> str:
    return f"{VIOLATION_PREFIX} report-shape: {message}"


def capture_violation(message: str) -> str:
    return f"{VIOLATION_PREFIX} captured-output: {message}"


def read_required(path: Path, label: str) -> str:
    if not path.is_file():
        raise EvaluationInputError(f"missing {label} at {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise EvaluationInputError(f"could not read {label} at {path}: {error}") from error
    except UnicodeDecodeError as error:
        raise EvaluationInputError(f"could not decode {label} at {path}: {error}") from error


def _parse_capture(projection: Any, index: int) -> CapturedArtifact:
    if not isinstance(projection, dict):
        raise EvaluationInputError(f"{BUNDLE_FILENAME} captured_outputs[{index}] is not an object")
    artifact_id = projection.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        raise EvaluationInputError(
            f"{BUNDLE_FILENAME} captured_outputs[{index}] has no nonblank artifact_id"
        )
    envelope = {
        field: value
        for field, value in projection.items()
        if field not in {"artifact_id", "file_sha256"}
    }
    try:
        record = CapturedOutput.model_validate_json(json.dumps(envelope))
    except (TypeError, ValidationError) as error:
        raise EvaluationInputError(
            f"{BUNDLE_FILENAME} captured_outputs[{index}] did not validate: {error}"
        ) from error
    if record.marker != CAPTURED_OUTPUT_MARKER:
        raise EvaluationInputError(
            f"{BUNDLE_FILENAME} captured_outputs[{index}] has an invalid owner marker"
        )
    return CapturedArtifact(artifact_id=artifact_id.strip(), record=record)


def load_captured_outputs(bundle_path: Path) -> list[CapturedArtifact] | None:
    """Load validated capture projections, or None only when the bundle is absent."""
    if not bundle_path.exists():
        return None
    if not bundle_path.is_file():
        raise EvaluationInputError(f"{BUNDLE_FILENAME} at {bundle_path} is not a file")
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvaluationInputError(f"{BUNDLE_FILENAME} did not parse: {error}") from error
    if not isinstance(bundle, dict):
        raise EvaluationInputError(f"{BUNDLE_FILENAME} root is not an object")
    version = bundle.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 3:
        raise EvaluationInputError(
            f"{BUNDLE_FILENAME} requires schema_version >= 3 (found {version!r})"
        )
    if version == 3:
        return []
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, dict):
        raise EvaluationInputError(f"{BUNDLE_FILENAME} has no artifacts object")
    projections = artifacts.get("captured_outputs")
    if not isinstance(projections, list):
        raise EvaluationInputError(
            f"{BUNDLE_FILENAME} artifacts.captured_outputs is not a list"
        )
    captures = [_parse_capture(projection, index) for index, projection in enumerate(projections)]
    ids = [capture.artifact_id for capture in captures]
    if len(ids) != len(set(ids)):
        raise EvaluationInputError(f"{BUNDLE_FILENAME} has duplicate captured-output artifact ids")
    return captures


def parse_report_rows(report: str, violations: list[str]) -> list[ReportRow]:
    body = section_body(split_sections(report), "verification execution")
    if body is None:
        violations.append(report_violation("missing Verification Execution section"))
        return []
    table = first_table(body)
    if table is None:
        violations.append(report_violation("Verification Execution has no markdown table"))
        return []
    headers, rows = table
    if tuple(headers) != CANONICAL_COLUMNS:
        violations.append(
            report_violation(
                "Verification Execution columns must be exactly: "
                + ", ".join(CANONICAL_COLUMNS)
            )
        )
        return []

    parsed: list[ReportRow] = []
    for number, cells in enumerate(rows, start=1):
        if len(cells) != len(CANONICAL_COLUMNS):
            violations.append(
                report_violation(
                    f"row {number} has {len(cells)} cells; expected {len(CANONICAL_COLUMNS)}"
                )
            )
            continue
        spec_cell, check, kind, execution, result, artifact_id, observed_effect = cells
        spec_row = int(spec_cell) if INTEGER.fullmatch(spec_cell) else None
        if spec_row is None:
            violations.append(report_violation(f"row {number} has invalid Spec row {spec_cell!r}"))
        if not check:
            violations.append(report_violation(f"row {number} has a blank Check"))
        if not kind:
            violations.append(report_violation(f"row {number} has a blank Kind"))
        if execution not in EXECUTIONS:
            violations.append(report_violation(f"row {number} has invalid Execution {execution!r}"))
        if result not in RESULTS:
            violations.append(report_violation(f"row {number} has invalid Result {result!r}"))
        parsed.append(
            ReportRow(
                number=number,
                spec_row=spec_row,
                check=check,
                kind=kind,
                execution=execution,
                result=result,
                artifact_id=artifact_id,
                observed_effect=observed_effect,
            )
        )
    return parsed


def _adapted_capture_matches(row: VerificationRow, capture: CapturedArtifact) -> bool:
    record = capture.record
    return (
        row_identity(row) == (record.spec_row_number, record.check)
        and record.spawned
        and not record.timed_out
        and record.effective_heads == effective_heads(record.exact_command)
        and record.command_digest != canonical_command_digest(row.raw_command)
    )


def require_exact_capture(
    row: VerificationRow,
    report_row: ReportRow,
    captures: list[CapturedArtifact] | None,
    violations: list[str],
) -> None:
    label = f"Spec row {row.row_number} ({row.check!r})"
    if not report_row.artifact_id:
        violations.append(capture_violation(f"{label} passes without a Captured artifact"))
    elif captures is None:
        violations.append(capture_violation(f"{label} passes but {BUNDLE_FILENAME} is absent"))
    elif not any(
        capture.artifact_id == report_row.artifact_id
        and captured_output_matches(row, capture.record)
        for capture in captures
    ):
        violations.append(
            capture_violation(
                f"{label} has no matching CAPTURED-OUTPUT for artifact "
                f"{report_row.artifact_id!r}"
            )
        )
    if not report_row.observed_effect.strip():
        violations.append(capture_violation(f"{label} passes with a blank Observed effect"))


def require_adapted_capture(
    row: VerificationRow,
    report_row: ReportRow,
    captures: list[CapturedArtifact] | None,
    violations: list[str],
) -> None:
    label = f"Spec row {row.row_number} ({row.check!r})"
    if not report_row.artifact_id:
        violations.append(capture_violation(f"{label} adapted-passes without a Captured artifact"))
    elif captures is None:
        violations.append(capture_violation(f"{label} adapted-passes but {BUNDLE_FILENAME} is absent"))
    elif not any(
        capture.artifact_id == report_row.artifact_id
        and _adapted_capture_matches(row, capture)
        for capture in captures
    ):
        violations.append(
            capture_violation(f"{label} has no cited CAPTURED-OUTPUT for an adapted command")
        )
