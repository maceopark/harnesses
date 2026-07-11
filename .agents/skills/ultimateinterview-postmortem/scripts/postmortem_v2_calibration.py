#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Final, NamedTuple, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

if __package__:
    from . import postmortem_taxonomy as taxonomy
    from . import postmortem_v2_markdown as markdown
else:
    import postmortem_taxonomy as taxonomy  # pyright: ignore[reportImplicitRelativeImport] -- direct script execution.
    import postmortem_v2_markdown as markdown  # pyright: ignore[reportImplicitRelativeImport] -- direct script execution.

CORPUS_NAME: Final[str] = "synthetic-corpus.json"
PROMOTION: Final[str] = "advisory-only; future owner-approved policy required."
HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(.*)$")
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class CalibrationError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class ReviewedLabel(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


class MechanismResult(StrEnum):
    PASS = "pass"
    REJECT = "reject"


class SyntheticRecord(StrictModel):
    case_id: Annotated[str, StringConstraints(strict=True, pattern=r"^CAL-\d{3}$")]
    reviewed_label: ReviewedLabel
    mechanism_results: Annotated[dict[NonBlank, MechanismResult], Field(min_length=1)]
    elapsed_monotonic_ms: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class SyntheticCorpus(StrictModel):
    corpus_version: NonBlank
    records: tuple[SyntheticRecord, ...]
    corpus_digest: Digest

    @field_validator("records")
    @classmethod
    def records_have_unique_cases(cls, value: tuple[SyntheticRecord, ...]) -> tuple[SyntheticRecord, ...]:
        if not value or len({record.case_id for record in value}) != len(value):
            raise CalibrationError("synthetic corpus requires unique reviewed case records")
        return value

    @model_validator(mode="after")
    def binds_immutable_records(self) -> Self:
        preimage = {
            "corpus_version": self.corpus_version,
            "records": [record.model_dump(mode="json") for record in self.records],
        }
        actual = hashlib.sha256(
            json.dumps(preimage, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        if self.corpus_digest != actual:
            raise CalibrationError("synthetic corpus digest does not match canonical reviewed records")
        return self


class CalibrationEscape(NamedTuple):
    failure_mode: taxonomy.FailureMode
    structure: str
    owning_frame: taxonomy.OwningFrame


class SyntheticCalibrationEvaluation(NamedTuple):
    violations: tuple[str, ...]
    summary: str | None


def _sections(text: str) -> tuple[tuple[str, str], ...]:
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            if heading is not None:
                sections.append((heading, "\n".join(lines)))
            heading = match.group(1).strip().lower()
            lines = []
        else:
            lines.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(lines)))
    return tuple(sections)


def _tables(body: str) -> tuple[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]], ...]:
    lines = tuple(line.strip() for line in body.splitlines())
    tables: list[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]] = []
    index = 0
    while index + 1 < len(lines):
        if not lines[index].startswith("|") or "---" not in lines[index + 1]:
            index += 1
            continue
        headers = tuple(value.strip().lower() for value in lines[index].strip("|").split("|"))
        rows: list[tuple[str, ...]] = []
        index += 2
        while index < len(lines) and lines[index].startswith("|"):
            rows.append(tuple(value.strip() for value in lines[index].strip("|").split("|")))
            index += 1
        tables.append((headers, tuple(rows)))
    return tuple(tables)


def _lines(body: str, name: str) -> tuple[str, ...]:
    prefix = f"{name.lower()}:"
    return tuple(
            line.strip()[len(prefix):].strip()
            for line in body.splitlines()
            if line.strip().lower().startswith(prefix)
    )


def _load_corpus(path: Path) -> SyntheticCorpus:
    if path.is_symlink() or not path.is_file():
        raise CalibrationError("synthetic corpus must be regular non-symlink file")
    try:
        return SyntheticCorpus.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise CalibrationError(f"synthetic corpus is invalid: {error}") from error


def _totals(corpus: SyntheticCorpus) -> tuple[dict[str, tuple[str, str]], float, int]:
    false_accept = false_accept_denominator = false_alarm = false_alarm_denominator = 0
    unique_catch = unique_catch_denominator = 0
    elapsed = 0.0
    for record in corpus.records:
        elapsed += record.elapsed_monotonic_ms
        rejected = sum(result is MechanismResult.REJECT for result in record.mechanism_results.values())
        match record.reviewed_label:
            case ReviewedLabel.ACCEPT:
                false_alarm_denominator += len(record.mechanism_results)
                false_alarm += rejected
            case ReviewedLabel.REJECT:
                false_accept_denominator += len(record.mechanism_results)
                false_accept += len(record.mechanism_results) - rejected
                unique_catch_denominator += 1
                unique_catch += int(rejected == 1)
    case_count = len(corpus.records)
    return {
        "false-accept": (str(false_accept), f"reviewed-negative-mechanisms:{false_accept_denominator}"),
        "false-alarm": (str(false_alarm), f"reviewed-accept-mechanisms:{false_alarm_denominator}"),
        "unique-catch": (str(unique_catch), f"reviewed-negatives:{unique_catch_denominator}"),
        "cost-milliseconds": (_decimal(elapsed), f"cases:{case_count}"),
        "cost-cases": (str(case_count), f"records:{case_count}"),
    }, elapsed, case_count


def _decimal(value: float) -> str:
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _metric_rows(body: str) -> tuple[dict[str, tuple[str, str]], tuple[str, ...]]:
    tables = tuple(table for table in _tables(body) if table[0] == ("metric", "value", "denominator"))
    if len(tables) != 1:
        return {}, ("synthetic calibration requires exactly one metric table",)
    metrics: dict[str, tuple[str, str]] = {}
    violations: list[str] = []
    for row in tables[0][1]:
        if len(row) != 3:
            violations.append("synthetic calibration has malformed metric row")
            continue
        metric = row[0].lower()
        if metric in metrics:
            violations.append(f"synthetic calibration has duplicate metric: {metric}")
            continue
        metrics[metric] = (row[1], row[2])
    return metrics, tuple(violations)


def evaluate_synthetic_calibration(session_dir: Path, report: str) -> SyntheticCalibrationEvaluation:
    sections = _sections(report)
    bodies = tuple(body for heading, body in sections if heading == "synthetic calibration")
    corpus_path = session_dir / CORPUS_NAME
    if not bodies and not corpus_path.exists():
        return SyntheticCalibrationEvaluation((), None)
    if len(bodies) != 1:
        return SyntheticCalibrationEvaluation(("synthetic calibration requires exactly one Synthetic Calibration section",), None)
    body = bodies[0]
    if corpus_path.is_symlink():
        return SyntheticCalibrationEvaluation(("synthetic corpus must be regular non-symlink file",), None)
    if not corpus_path.is_file():
        return SyntheticCalibrationEvaluation(("synthetic corpus requires a Synthetic Calibration section",), None)
    try:
        corpus = _load_corpus(corpus_path)
    except CalibrationError as error:
        return SyntheticCalibrationEvaluation((str(error),), None)
    violations: list[str] = []
    if _lines(body, "Synthetic corpus") != (CORPUS_NAME,):
        violations.append(f"synthetic calibration must bind {CORPUS_NAME}")
    if _lines(body, "Corpus version") != (corpus.corpus_version,):
        violations.append("synthetic calibration corpus version does not match reviewed corpus")
    if _lines(body, "Corpus digest") != (corpus.corpus_digest,):
        violations.append("synthetic calibration corpus digest does not match reviewed corpus")
    if _lines(body, "Promotion") != (PROMOTION,):
        violations.append("synthetic calibration promotion must stay advisory and require a future owner-approved policy")
    expected_metrics, elapsed, case_count = _totals(corpus)
    metrics, metric_violations = _metric_rows(body)
    violations.extend(metric_violations)
    for metric in metrics:
        if metric not in expected_metrics:
            violations.append(f"synthetic calibration has unknown metric: {metric}")
    for metric, (value, denominator) in expected_metrics.items():
        actual = metrics.get(metric)
        if actual is None:
            violations.append(f"synthetic calibration is missing {metric}")
            continue
        if actual[0] != value:
            violations.append(f"synthetic calibration {metric} count does not match reviewed corpus")
        if actual[1] != denominator:
            violations.append(f"synthetic calibration {metric} denominator does not match reviewed corpus")
    synthetic_ids = tuple(
        markdown.identifier_skeleton(record.case_id).lower().replace("-", "") for record in corpus.records
    )
    for heading in ("divergence table", "escaped requirements"):
        real_body = "\n".join(body for current, body in sections if current == heading)
        compact = re.sub(r"[^a-z0-9]", "", markdown.identifier_skeleton(real_body).lower())
        if markdown.has_bidi_synthetic_candidate(real_body) or any(case_id in compact for case_id in synthetic_ids):
            violations.append("synthetic calibration case is misfiled as real postmortem evidence")
    return SyntheticCalibrationEvaluation(
        tuple(violations),
        f"synthetic calibration (advisory): {case_count} cases, {_decimal(elapsed)} ms",
    )


def evaluate_calibration(
    declared: dict[str, int], escapes: tuple[CalibrationEscape, ...]
) -> tuple[str, ...]:
    expected = {
        **{mode.value: 0 for mode in taxonomy.FailureMode},
        **{base.value: 0 for base in taxonomy.RequirementBase},
        **{f"modifier:{modifier.value}": 0 for modifier in taxonomy.RequirementModifier},
        "owning-frame:none": 0,
    }
    for escape in escapes:
        expected[escape.failure_mode.value] += 1
        structure = taxonomy.parse_requirement_structure(escape.structure)
        match structure.base:
            case taxonomy.RequirementBase() as base:
                base_key = base.value
            case taxonomy.NovelBase(slug=slug):
                base_key = f"novel:{slug}"
        expected[base_key] = expected.get(base_key, 0) + 1
        for modifier in structure.modifiers:
            key = f"modifier:{modifier.value}"
            expected[key] = expected.get(key, 0) + 1
        if escape.owning_frame is taxonomy.OwningFrame.NONE:
            expected["owning-frame:none"] = expected.get("owning-frame:none", 0) + 1
    return tuple(
        f"v2 calibration: {key} declares {declared.get(key)!r}; escape rows derive {count}"
        for key, count in expected.items()
        if declared.get(key) != count
    )
