#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

LEGACY_COLUMNS: Final[tuple[str, ...]] = (
    "Verification command / check",
    "Ran?",
    "Result",
)
LEGACY_RESULTS: Final[tuple[str, ...]] = ("pass", "fail", "skipped", "not-run")


def _cells(line: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in line.strip().strip("|").split("|"))


def _verification_table(report: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]] | None:
    lines = report.splitlines()
    in_section = False
    for index, line in enumerate(lines):
        lowered = line.strip().lower()
        if lowered.startswith("#"):
            in_section = "verification execution" in lowered
            continue
        if not in_section or not line.strip().startswith("|"):
            continue
        if index + 1 >= len(lines) or "---" not in lines[index + 1]:
            continue
        rows: list[tuple[str, ...]] = []
        cursor = index + 2
        while cursor < len(lines) and lines[cursor].strip().startswith("|"):
            rows.append(_cells(lines[cursor]))
            cursor += 1
        return _cells(line), tuple(rows)
    return None


def is_legacy_v3_report(bundle_path: Path, report: str) -> bool:
    if "postmortem_schema:" in report:
        return False
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 3:
        return False
    table = _verification_table(report)
    return table is not None and table[0] == LEGACY_COLUMNS


def verification_violations(report: str) -> tuple[str, ...]:
    table = _verification_table(report)
    if table is None or table[0] != LEGACY_COLUMNS:
        return ("verification-execution: legacy-v3 report table is missing or malformed",)
    rows = table[1]
    violations: list[str] = []
    if not rows:
        violations.append("verification-execution: legacy-v3 report has no verification rows")
    for number, row in enumerate(rows, start=1):
        if len(row) != len(LEGACY_COLUMNS) or any(not value for value in row):
            violations.append(
                f"verification-execution: legacy-v3 row {number} must contain three nonblank cells"
            )
            continue
        if not row[2].lower().startswith(LEGACY_RESULTS):
            violations.append(
                f"verification-execution: legacy-v3 row {number} has an unknown result"
            )
    return tuple(violations)
