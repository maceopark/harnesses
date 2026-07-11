#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from postmortem_taxonomy import (
    Disposition,
    EscapeClassification,
    EscapeFields,
    FailureMode,
    OwningFrame,
    RequirementModifier,
    TaxonomyError,
    parse_requirement_structure,
)
from postmortem_v2_calibration import CalibrationEscape, evaluate_calibration
from postmortem_bundle import artifact_ids

CLASSES: Final[tuple[str, ...]] = (
    "fulfilled",
    "escaped-requirement",
    "scope-drift",
    "divergent-implementation",
    "deferred-outcome",
)
REQ_ID: Final[re.Pattern[str]] = re.compile(r"REQ-\d+")
ESC_ID: Final[re.Pattern[str]] = re.compile(r"ESC-\d{3}")
HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(.*)$")


@dataclass(frozen=True, slots=True)
class EscapeRow:
    escape_id: str
    failure_mode: FailureMode
    structure: str
    owning_frame: OwningFrame
    disposition: Disposition


@dataclass(frozen=True, slots=True)
class V2Evaluation:
    counts: dict[str, int]
    synthesis_count: int
    violations: tuple[str, ...]


def _sections(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            if current is not None:
                result[current] = "\n".join(lines)
            current = match.group(1).strip().lower()
            lines = []
        else:
            lines.append(line)
    if current is not None:
        result[current] = "\n".join(lines)
    return result


def _section(sections: dict[str, str], needle: str) -> str:
    return sections.get(needle, "")


def _cells(line: str) -> list[str]:
    return [value.strip() for value in line.strip("|").split("|")]


def _tables(body: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = [line.strip() for line in body.splitlines()]
    found: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index + 1 < len(lines):
        if not lines[index].startswith("|") or "---" not in lines[index + 1]:
            index += 1
            continue
        headers = _cells(lines[index])
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and lines[index].startswith("|"):
            rows.append(_cells(lines[index]))
            index += 1
        found.append((headers, rows))
    return found


def _column(headers: list[str], needle: str) -> int | None:
    return next((index for index, value in enumerate(headers) if needle in value.lower()), None)


def _cell(row: list[str], index: int | None) -> str:
    return row[index] if index is not None and index < len(row) else ""


def _leading(value: str) -> str | None:
    lowered = value.strip().lstrip("*_`~ ").lower()
    return next((item for item in CLASSES if lowered.startswith(item)), None)


def _divergence(
    body: str, part1: str, violations: list[str]
) -> tuple[dict[str, int], frozenset[str]]:
    counts: dict[str, int] = dict.fromkeys(CLASSES, 0)
    tables = _tables(body)
    if not tables:
        violations.append("v2 divergence: missing table")
        return counts, frozenset()
    headers, rows = tables[0]
    class_column = _column(headers, "class")
    seen: set[str] = set()
    escapes: set[str] = set()
    reqs: set[str] = set()
    for number, row in enumerate(rows, start=1):
        identity = _cell(row, 0)
        token = _leading(_cell(row, class_column))
        if token is None:
            violations.append(f"v2 divergence row {number}: unknown class")
            continue
        counts[token] += 1
        if identity in seen:
            violations.append(f"v2 divergence: duplicate identity {identity}")
        seen.add(identity)
        if token == "escaped-requirement":
            if ESC_ID.fullmatch(identity) is None:
                violations.append(
                    f"v2 divergence: escaped row {identity!r} must use an ESC-NNN identity; REQ IDs cannot masquerade as escapes"
                )
            else:
                escapes.add(identity)
        elif REQ_ID.fullmatch(identity) is None:
            violations.append(f"v2 divergence: non-escape row {identity!r} must use a REQ ID")
        else:
            reqs.add(identity)
    if missing := sorted(set(REQ_ID.findall(part1)) - reqs):
        violations.append("v2 divergence: Part-1 requirements absent: " + ", ".join(missing))
    return counts, frozenset(escapes)


def _escapes(
    body: str,
    expected: frozenset[str],
    artifact_ids: frozenset[str],
    violations: list[str],
) -> dict[str, EscapeRow]:
    tables = _tables(body)
    if not tables:
        violations.append("v2 escapes: missing table")
        return {}
    headers, rows = tables[0]
    names = (
        "esc-id", "failure mode", "requirement structure", "owning frame",
        "disposition", "store", "evidence",
    )
    columns = {name: _column(headers, name) for name in names}
    missing_columns = [name for name, index in columns.items() if index is None]
    if missing_columns:
        violations.append("v2 escapes: missing column(s): " + ", ".join(missing_columns))
        return {}
    parsed: dict[str, EscapeRow] = {}
    for number, row in enumerate(rows, start=1):
        escape_id = _cell(row, columns["esc-id"])
        store = _cell(row, columns["store"])
        evidence = _cell(row, columns["evidence"])
        try:
            fields = EscapeFields(
                escape_id=escape_id,
                failure_mode=FailureMode(_cell(row, columns["failure mode"])),
                requirement_structure=parse_requirement_structure(
                    _cell(row, columns["requirement structure"])
                ).canonical,
                owning_frame=OwningFrame(_cell(row, columns["owning frame"])),
                disposition=Disposition(_cell(row, columns["disposition"])),
                lesson_store=None if store.lower() in {"", "n/a", "none", "-"} else store,
            )
            classified = EscapeClassification.from_report("postmortem_schema: 2", fields)
        except (TaxonomyError, ValidationError, ValueError) as error:
            violations.append(f"v2 escapes row {number}: {error}")
            continue
        if escape_id in parsed:
            violations.append(f"v2 escapes: duplicate row {escape_id}")
        if not evidence:
            violations.append(f"v2 escapes: {escape_id} has missing causal evidence")
        structure = parse_requirement_structure(str(classified.requirement_structure))
        if RequirementModifier.NEGATIVE_SPACE in structure.modifiers and not any(
            artifact_id in evidence for artifact_id in artifact_ids
        ):
            violations.append(
                f"v2 escapes: {escape_id} negative-space evidence must cite an observed artifact; any external artifact kind is sufficient"
            )
        parsed[escape_id] = EscapeRow(
            escape_id, classified.failure_mode, str(classified.requirement_structure),
            classified.owning_frame, classified.disposition,
        )
    if set(parsed) != set(expected):
        violations.append("v2 escapes: rows must join escaped Divergence identities exactly once")
    return parsed


def _wonder(body: str, escapes: dict[str, EscapeRow], violations: list[str]) -> None:
    tables = _tables(body)
    if not tables:
        violations.append("v2 wonder: missing table")
        return
    headers, rows = tables[0]
    columns = {name: _column(headers, name) for name in ("escape id", "owning frame", "disposition", "store")}
    if any(index is None for index in columns.values()):
        violations.append("v2 wonder: missing identity/frame/disposition/store column")
        return
    seen: set[str] = set()
    for number, row in enumerate(rows, start=1):
        escape_id = _cell(row, columns["escape id"])
        if escape_id in seen:
            violations.append(f"v2 wonder: duplicate row {escape_id}")
        seen.add(escape_id)
        escape = escapes.get(escape_id)
        if escape is None:
            violations.append(f"v2 wonder row {number}: {escape_id!r} has no escaped row")
            continue
        disposition = _cell(row, columns["disposition"])
        frame = _cell(row, columns["owning frame"])
        store = _cell(row, columns["store"]).lower()
        if disposition != escape.disposition.value or frame != escape.owning_frame.value:
            violations.append(f"v2 wonder: {escape_id} taxonomy does not match its escaped row")
        if escape.failure_mode is FailureMode.ONTOLOGY_MISS and (
            disposition != Disposition.ONTOLOGY_NONROUTING.value
            or store not in {"", "n/a", "none", "-"}
        ):
            violations.append(
                f"v2 wonder: {escape_id} requires not-routing/ontology-miss and no lesson write"
            )
    if seen != set(escapes):
        violations.append("v2 wonder: rows must join escaped identities exactly once")


def _declared_calibration(body: str) -> dict[str, int]:
    tables = _tables(body)
    return {
        _cell(row, 0): int(_cell(row, 1))
        for headers, rows in tables
        if _column(headers, "count") is not None
        for row in rows
        if _cell(row, 1).isdigit()
    }


def evaluate(report: str, part1: str, bundle_path: Path) -> V2Evaluation:
    violations: list[str] = []
    sections = _sections(report)
    counts, escape_ids = _divergence(_section(sections, "divergence table"), part1, violations)
    escapes = _escapes(
        _section(sections, "escaped requirements"),
        escape_ids,
        artifact_ids(bundle_path),
        violations,
    )
    _wonder(_section(sections, "wonder generalization"), escapes, violations)
    violations.extend(
        evaluate_calibration(
            _declared_calibration(_section(sections, "calibration summary")),
            tuple(
                CalibrationEscape(row.failure_mode, row.structure, row.owning_frame)
                for row in escapes.values()
            ),
        )
    )
    synthesis = sum(
        escape.failure_mode is FailureMode.SYNTHESIS_LOSS for escape in escapes.values()
    )
    return V2Evaluation(counts, synthesis, tuple(violations))
