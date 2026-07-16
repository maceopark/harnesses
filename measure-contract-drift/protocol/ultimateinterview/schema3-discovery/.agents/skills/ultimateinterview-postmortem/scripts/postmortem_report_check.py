#!/usr/bin/env python3
"""Fail-closed structural validator for Ultimateinterview postmortem reports."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence


BUNDLE_SCHEMA = "ultimateinterview.compiler-postmortem-evidence.v1"
LEGACY_REPORT_SCHEMA = "2"
COMPACT_REPORT_SCHEMA = "3"
LEGACY_REQUIRED_SECTIONS = (
    "Conclusion",
    "Implementation Evidence",
    "Divergence Table",
    "Finding Details",
    "Verification Execution",
    "Lessons",
    "Process Gaps and Missing Evidence",
    "Resolution Addendum",
)
COMPACT_REQUIRED_SECTIONS = ("Conclusion", "Findings", "Verification")
DIVERGENCE_HEADERS = (
    "ID",
    "Behavior",
    "Class",
    "Contract mapping",
    "Implementation evidence",
    "Verification evidence",
    "Owner decision needed?",
)
FINDING_HEADERS = (
    "ID",
    "Behavior",
    "Class / failure mode",
    "Structure / owning frame",
    "Intent attribution",
    "Evidence",
    "Owner action",
)
VERIFICATION_HEADERS = (
    "VER-ID",
    "Procedure",
    "Direct execution",
    "Result",
    "Evidence",
)
COMPACT_FINDING_HEADERS = ("ID", "Class", "Behavior", "Evidence", "Root cause", "Owner action")
COMPACT_VERIFICATION_HEADERS = ("VER-ID", "Result", "Evidence")
LESSON_HEADERS = (
    "Store",
    "Signal",
    "Action",
    "Pre-state",
    "Post-state",
    "Evidence",
)
PROPOSAL_HEADERS = (
    "Proposal",
    "Prevents",
    "Rule to add or strengthen",
    "Cross-domain reason",
    "Compatible existing rule",
)
CLASS_TO_COUNT = {
    "fulfilled": "fulfilled",
    "escaped-requirement": "escaped",
    "scope-drift": "scope-drift",
    "divergent-implementation": "divergent",
    "deferred-outcome": "deferred",
    "unverifiable": "unverifiable",
}
REQUIREMENT_CLASSES = frozenset(CLASS_TO_COUNT) - {"escaped-requirement"}
LESSON_ACTIONS = frozenset({"fired", "appended", "strengthened", "retired", "rejected", "none"})
MUTATING_LESSON_ACTIONS = frozenset({"fired", "appended", "strengthened", "retired"})
ROOT_CAUSES = frozenset(
    {
        "none",
        "discovery-miss",
        "decision-miss",
        "handoff-loss",
        "contract-defect",
        "implementation-drift",
        "verification-gap",
    }
)
MAX_COMPACT_TEXT = 240
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ESCAPE_ID_RE = re.compile(r"ESC-[0-9]{3,}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COUNTS_RE = re.compile(
    r"^\*\*Counts:\*\*\s*(?P<total>[0-9]+)\s+contract requirements\s*[—-]\s*"
    r"(?P<fulfilled>[0-9]+)\s+fulfilled,\s*(?P<escaped>[0-9]+)\s+escaped,\s*"
    r"(?P<scope_drift>[0-9]+)\s+scope-drift,\s*(?P<divergent>[0-9]+)\s+divergent,\s*"
    r"(?P<deferred>[0-9]+)\s+deferred,\s*(?P<unverifiable>[0-9]+)\s+unverifiable\.\s*$"
)


class ReportError(ValueError):
    """A stable report-contract diagnostic."""


def _strict_json_loads(text: str) -> Any:
    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON value {token}")

    def reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = item
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_duplicate_object_keys)


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReportError(f"{label} not found")
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ReportError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ReportError(f"{label} must be a JSON object")
    return value


def require_ids(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ReportError(f"compiler evidence bundle {name} ids must be a string array")
    if len(value) != len(set(value)):
        raise ReportError(f"compiler evidence bundle {name} ids contain duplicates")
    return tuple(value)


def bundle_ids(bundle: Mapping[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if bundle.get("schema") != BUNDLE_SCHEMA:
        raise ReportError(f"compiler evidence bundle schema must be {BUNDLE_SCHEMA}")
    digest = bundle.get("contract_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ReportError("compiler evidence bundle has an invalid contract_digest")
    ids = bundle.get("ids")
    if not isinstance(ids, dict):
        raise ReportError("compiler evidence bundle ids must be an object")
    return digest, require_ids(ids.get("requirements"), "requirement"), require_ids(
        ids.get("verifications"), "verification"
    )


def heading_index(lines: Sequence[str]) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))
    return headings


def section_ranges(
    lines: Sequence[str], required_sections: Sequence[str], *, exact: bool = False
) -> dict[str, tuple[int, int]]:
    headings = heading_index(lines)
    if not headings or headings[0][1:] != (1, "Ultimateinterview Postmortem"):
        raise ReportError("report must begin with '# Ultimateinterview Postmortem'")
    level_two = [(index, title) for index, level, title in headings if level == 2]
    if not level_two or level_two[0][1] != "Conclusion":
        raise ReportError("Conclusion must be the first substantive section")
    positions: dict[str, int] = {}
    for index, title in level_two:
        if title in positions:
            raise ReportError(f"report contains duplicate section '{title}'")
        positions[title] = index
    for name in required_sections:
        if name not in positions:
            raise ReportError(f"report is missing required section '{name}'")
    if exact:
        extras = sorted(set(positions) - set(required_sections))
        if extras:
            raise ReportError(f"compact report has unsupported sections: {', '.join(extras)}")
    result: dict[str, tuple[int, int]] = {}
    ordered = sorted((index, name) for name, index in positions.items())
    for offset, (start, name) in enumerate(ordered):
        end = ordered[offset + 1][0] if offset + 1 < len(ordered) else len(lines)
        if name in required_sections:
            result[name] = (start + 1, end)
    return result


def metadata_values(lines: Sequence[str], conclusion_heading: int) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines[1:conclusion_heading]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ReportError("report metadata must use key: value lines")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value or key in values:
            raise ReportError("report metadata is malformed")
        values[key] = value
    return values


def metadata(
    lines: Sequence[str], conclusion_heading: int, contract_digest: str, expected_schema: str
) -> None:
    values = metadata_values(lines, conclusion_heading)
    if values.get("postmortem_schema") != expected_schema:
        raise ReportError(f"postmortem_schema must be {expected_schema}")
    if values.get("contract_digest") != contract_digest:
        raise ReportError("report contract_digest does not match compiler evidence bundle")
    if not values.get("evaluator"):
        raise ReportError("report evaluator metadata is required")
    timestamp = values.get("evaluated_at")
    if not timestamp:
        raise ReportError("report evaluated_at metadata is required")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportError("report evaluated_at must be ISO-8601") from error


def split_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells)


def tables(lines: Sequence[str], start: int, end: int) -> list[tuple[tuple[str, ...], list[list[str]]]]:
    result: list[tuple[tuple[str, ...], list[list[str]]]] = []
    index = start
    while index < end - 1:
        header = split_table_row(lines[index])
        separator = split_table_row(lines[index + 1])
        if header is None or separator is None or len(header) != len(separator) or not is_separator(separator):
            index += 1
            continue
        if any(not cell for cell in header) or len(set(header)) != len(header):
            raise ReportError("table header is malformed")
        rows: list[list[str]] = []
        index += 2
        while index < end:
            row = split_table_row(lines[index])
            if row is None:
                break
            if len(row) != len(header) or any(not cell for cell in row):
                raise ReportError("table row is malformed")
            rows.append(row)
            index += 1
        result.append((tuple(header), rows))
    return result


def require_table(
    lines: Sequence[str], section: tuple[int, int], headers: Sequence[str], label: str
) -> list[dict[str, str]]:
    matches = [(found, rows) for found, rows in tables(lines, *section) if found == tuple(headers)]
    if len(matches) != 1:
        raise ReportError(f"{label} must contain exactly one required table")
    _, rows = matches[0]
    return [dict(zip(headers, row, strict=True)) for row in rows]


def subsection(lines: Sequence[str], section: tuple[int, int], heading: str) -> tuple[int, int]:
    start, end = section
    expected = f"### {heading}"
    found = [index for index in range(start, end) if lines[index].strip() == expected]
    if len(found) != 1:
        raise ReportError(f"Conclusion must contain '{expected}'")
    child_start = found[0] + 1
    child_end = end
    for index in range(child_start, end):
        match = HEADING_RE.match(lines[index])
        if match and len(match.group(1)) <= 3:
            child_end = index
            break
    return child_start, child_end


def validate_conclusion(
    lines: Sequence[str], section: tuple[int, int], requirement_count: int
) -> tuple[dict[str, int], list[dict[str, str]]]:
    body = lines[slice(*section)]
    if not any(re.fullmatch(r"\*\*Verdict:\*\*\s+.+", line.strip()) for line in body):
        raise ReportError("Conclusion requires a plain-language Verdict")
    count_lines = [line.strip() for line in body if line.strip().startswith("**Counts:**")]
    if len(count_lines) != 1:
        raise ReportError("Conclusion requires exactly one Counts line")
    match = COUNTS_RE.fullmatch(count_lines[0])
    if not match:
        raise ReportError("Conclusion Counts line has an invalid mechanical format")
    counts = {
        "total": int(match.group("total")),
        "fulfilled": int(match.group("fulfilled")),
        "escaped": int(match.group("escaped")),
        "scope-drift": int(match.group("scope_drift")),
        "divergent": int(match.group("divergent")),
        "deferred": int(match.group("deferred")),
        "unverifiable": int(match.group("unverifiable")),
    }
    if counts["total"] != requirement_count:
        raise ReportError("Conclusion total does not equal the Build Contract requirement count")
    root_causes = [line for line in body if re.fullmatch(r"1\.\s+.+", line.strip())]
    if not root_causes:
        raise ReportError("Conclusion requires at least one root cause")
    proposal_section = subsection(lines, section, "Ultimateinterview improvement proposals")
    proposals = require_table(lines, proposal_section, PROPOSAL_HEADERS, "improvement proposals")
    if len(proposals) > 3:
        raise ReportError("Conclusion has more than three improvement proposals")
    return counts, proposals


def validate_compact_text(value: str, label: str) -> None:
    if len(value) > MAX_COMPACT_TEXT:
        raise ReportError(f"{label} exceeds {MAX_COMPACT_TEXT} characters")


def validate_compact_conclusion(
    lines: Sequence[str], section: tuple[int, int], requirement_count: int
) -> dict[str, int]:
    body = lines[slice(*section)]
    unsupported = [
        line.strip()
        for line in body
        if line.strip()
        and not line.strip().startswith(("**Verdict:**", "**Counts:**", "**Improvement:**"))
    ]
    if unsupported:
        raise ReportError("compact Conclusion contains unsupported prose")
    verdicts = [
        match.group(1)
        for line in body
        if (match := re.fullmatch(r"\*\*Verdict:\*\*\s+(.+)", line.strip()))
    ]
    if len(verdicts) != 1:
        raise ReportError("Conclusion requires exactly one plain-language Verdict")
    validate_compact_text(verdicts[0], "Conclusion Verdict")
    count_lines = [line.strip() for line in body if line.strip().startswith("**Counts:**")]
    if len(count_lines) != 1:
        raise ReportError("Conclusion requires exactly one Counts line")
    match = COUNTS_RE.fullmatch(count_lines[0])
    if not match:
        raise ReportError("Conclusion Counts line has an invalid mechanical format")
    counts = {
        "total": int(match.group("total")),
        "fulfilled": int(match.group("fulfilled")),
        "escaped": int(match.group("escaped")),
        "scope-drift": int(match.group("scope_drift")),
        "divergent": int(match.group("divergent")),
        "deferred": int(match.group("deferred")),
        "unverifiable": int(match.group("unverifiable")),
    }
    if counts["total"] != requirement_count:
        raise ReportError("Conclusion total does not equal the Build Contract requirement count")
    improvements = [
        match.group(1)
        for line in body
        if (match := re.fullmatch(r"\*\*Improvement:\*\*\s+(.+)", line.strip()))
    ]
    if len(improvements) > 1:
        raise ReportError("Conclusion allows at most one Improvement line")
    if improvements:
        validate_compact_text(improvements[0], "Conclusion Improvement")
    return counts


def validate_compact_findings(
    lines: Sequence[str], section: tuple[int, int], requirement_ids: Sequence[str], counts: Mapping[str, int]
) -> None:
    if any(line.strip() and not line.strip().startswith("|") for line in lines[slice(*section)]):
        raise ReportError("compact Findings may contain only its required table")
    rows = require_table(lines, section, COMPACT_FINDING_HEADERS, "Findings")
    known_requirements = set(requirement_ids)
    seen_requirements: set[str] = set()
    seen_escapes: set[str] = set()
    actual = {key: 0 for key in ("fulfilled", "escaped", "scope-drift", "divergent", "deferred", "unverifiable")}
    for row in rows:
        identifier = row["ID"]
        classification = row["Class"]
        for header, value in row.items():
            validate_compact_text(value, f"Findings row {identifier} {header}")
        if identifier in known_requirements:
            if identifier in seen_requirements:
                raise ReportError(f"Findings has duplicate requirement row {identifier}")
            if classification not in REQUIREMENT_CLASSES:
                raise ReportError(f"Findings row {identifier} has invalid requirement class")
            seen_requirements.add(identifier)
        elif ESCAPE_ID_RE.fullmatch(identifier):
            if identifier in seen_escapes:
                raise ReportError(f"Findings has duplicate escape row {identifier}")
            if classification != "escaped-requirement":
                raise ReportError(f"Findings escape row {identifier} must be escaped-requirement")
            seen_escapes.add(identifier)
        else:
            raise ReportError(f"Findings row has unknown ID {identifier}")
        root_cause = row["Root cause"]
        if root_cause not in ROOT_CAUSES:
            raise ReportError(f"Findings row {identifier} has invalid root cause")
        if classification == "fulfilled" and root_cause != "none":
            raise ReportError(f"Findings row {identifier} must use root cause none when fulfilled")
        if classification != "fulfilled" and root_cause == "none":
            raise ReportError(f"Findings row {identifier} requires a root cause")
        actual[CLASS_TO_COUNT[classification]] += 1
    missing = sorted(known_requirements - seen_requirements)
    if missing:
        raise ReportError(f"Findings is missing requirement rows: {', '.join(missing)}")
    for key, value in actual.items():
        if counts[key] != value:
            raise ReportError(f"Conclusion {key} count does not match Findings")
    if sum(actual[key] for key in ("fulfilled", "scope-drift", "divergent", "deferred", "unverifiable")) != counts["total"]:
        raise ReportError("Findings requirement partition does not equal the Conclusion total")


def validate_compact_verifications(
    lines: Sequence[str], section: tuple[int, int], verification_ids: Sequence[str]
) -> None:
    if any(line.strip() and not line.strip().startswith("|") for line in lines[slice(*section)]):
        raise ReportError("compact Verification may contain only its required table")
    rows = require_table(lines, section, COMPACT_VERIFICATION_HEADERS, "Verification")
    known = set(verification_ids)
    seen: set[str] = set()
    for row in rows:
        identifier = row["VER-ID"]
        for header, value in row.items():
            validate_compact_text(value, f"Verification row {identifier} {header}")
        if identifier not in known:
            raise ReportError(f"Verification has unknown verification row {identifier}")
        if identifier in seen:
            raise ReportError(f"Verification has duplicate verification row {identifier}")
        if row["Result"] not in {"passed", "failed", "blocked", "not-run"}:
            raise ReportError(f"Verification row {identifier} has invalid result")
        seen.add(identifier)
    missing = sorted(known - seen)
    if missing:
        raise ReportError(f"Verification is missing rows: {', '.join(missing)}")


def validate_divergence(
    lines: Sequence[str], section: tuple[int, int], requirement_ids: Sequence[str], counts: Mapping[str, int]
) -> tuple[dict[str, str], set[str]]:
    rows = require_table(lines, section, DIVERGENCE_HEADERS, "Divergence Table")
    known_requirements = set(requirement_ids)
    seen_requirements: set[str] = set()
    seen_escapes: set[str] = set()
    classes: dict[str, str] = {}
    for row in rows:
        identifier = row["ID"]
        classification = row["Class"]
        if row["Owner decision needed?"] not in {"yes", "no"}:
            raise ReportError(f"Divergence Table row {identifier} has invalid owner decision value")
        if identifier in known_requirements:
            if identifier in seen_requirements:
                raise ReportError(f"Divergence Table has duplicate requirement row {identifier}")
            if classification not in REQUIREMENT_CLASSES:
                raise ReportError(f"Divergence Table row {identifier} has invalid requirement class")
            seen_requirements.add(identifier)
        elif ESCAPE_ID_RE.fullmatch(identifier):
            if identifier in seen_escapes:
                raise ReportError(f"Divergence Table has duplicate escape row {identifier}")
            if classification != "escaped-requirement":
                raise ReportError(f"Divergence Table escape row {identifier} must be escaped-requirement")
            seen_escapes.add(identifier)
        else:
            raise ReportError(f"Divergence Table row has unknown ID {identifier}")
        if classification not in CLASS_TO_COUNT:
            raise ReportError(f"Divergence Table row {identifier} has invalid class {classification}")
        classes[identifier] = classification
    missing = sorted(known_requirements - seen_requirements)
    if missing:
        raise ReportError(f"Divergence Table is missing requirement rows: {', '.join(missing)}")
    actual = {key: 0 for key in ("fulfilled", "escaped", "scope-drift", "divergent", "deferred", "unverifiable")}
    for identifier, classification in classes.items():
        actual[CLASS_TO_COUNT[classification]] += 1
    for key, value in actual.items():
        if counts[key] != value:
            raise ReportError(f"Conclusion {key} count does not match the Divergence Table")
    if sum(actual[key] for key in ("fulfilled", "scope-drift", "divergent", "deferred", "unverifiable")) != counts["total"]:
        raise ReportError("Divergence Table requirement partition does not equal the Conclusion total")
    return classes, seen_escapes


def validate_finding_details(
    lines: Sequence[str], section: tuple[int, int], classes: Mapping[str, str]
) -> None:
    rows = require_table(lines, section, FINDING_HEADERS, "Finding Details")
    expected = {identifier for identifier, classification in classes.items() if classification != "fulfilled"}
    seen: set[str] = set()
    for row in rows:
        identifier = row["ID"]
        if identifier not in expected:
            raise ReportError(f"Finding Details has an unexpected row {identifier}")
        if identifier in seen:
            raise ReportError(f"Finding Details has duplicate row {identifier}")
        classification = classes[identifier]
        if not row["Class / failure mode"].split(" / ", 1)[0] == classification:
            raise ReportError(f"Finding Details row {identifier} does not match its divergence class")
        seen.add(identifier)
    missing = sorted(expected - seen)
    if missing:
        raise ReportError(f"Finding Details is missing rows: {', '.join(missing)}")


def validate_verifications(
    lines: Sequence[str], section: tuple[int, int], verification_ids: Sequence[str]
) -> None:
    rows = require_table(lines, section, VERIFICATION_HEADERS, "Verification Execution")
    known = set(verification_ids)
    seen: set[str] = set()
    for row in rows:
        identifier = row["VER-ID"]
        if identifier not in known:
            raise ReportError(f"Verification Execution has unknown verification row {identifier}")
        if identifier in seen:
            raise ReportError(f"Verification Execution has duplicate verification row {identifier}")
        if row["Direct execution"] not in {"run", "not-run", "blocked"}:
            raise ReportError(f"Verification Execution row {identifier} has invalid direct execution state")
        if row["Result"] not in {"passed", "failed", "blocked", "not-run"}:
            raise ReportError(f"Verification Execution row {identifier} has invalid result")
        seen.add(identifier)
    missing = sorted(known - seen)
    if missing:
        raise ReportError(f"Verification Execution is missing rows: {', '.join(missing)}")


def state_descriptor(path: str) -> str:
    if path == "-":
        return "absent"
    target = Path(path)
    if not target.is_file():
        raise ReportError(f"lesson state path is not a regular file: {path}")
    try:
        return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError as error:
        raise ReportError(f"lesson state path cannot be read: {path}") from error


def lesson_state_arguments(arguments: Iterable[Sequence[str]]) -> dict[str, tuple[str, str]]:
    states: dict[str, tuple[str, str]] = {}
    for values in arguments:
        store, before, after = values
        if not store or store in states:
            raise ReportError("lesson store names must be non-empty and unique")
        states[store] = (state_descriptor(before), state_descriptor(after))
    return states


def valid_state(value: str) -> bool:
    return value == "absent" or DIGEST_RE.fullmatch(value) is not None


def validate_lessons(
    lines: Sequence[str], section: tuple[int, int], state_inputs: Mapping[str, tuple[str, str]]
) -> None:
    rows = require_table(lines, section, LESSON_HEADERS, "Lessons")
    for row in rows:
        action = row["Action"]
        if action not in LESSON_ACTIONS:
            raise ReportError(f"Lessons row has invalid action {action}")
        before = row["Pre-state"]
        after = row["Post-state"]
        if not valid_state(before) or not valid_state(after):
            raise ReportError("Lessons rows must declare pre/post state as absent or sha256:<digest>")
        store = row["Store"]
        if store not in state_inputs:
            raise ReportError(f"Lessons row for {store} has no supplied pre/post lesson state")
        actual_before, actual_after = state_inputs[store]
        if (before, after) != (actual_before, actual_after):
            raise ReportError(f"Lessons row for {store} does not match supplied pre/post lesson digests")
        if action in MUTATING_LESSON_ACTIONS and before == after:
            raise ReportError(f"Lessons row for {store} claims {action} without a lesson-state delta")
        if action in {"rejected", "none"} and before != after:
            raise ReportError(f"Lessons row for {store} claims {action} despite a lesson-state delta")


def validate_implementation_evidence(lines: Sequence[str], section: tuple[int, int]) -> None:
    headers = ("Source", "Scope", "Digest / revision", "Notes")
    rows = require_table(lines, section, headers, "Implementation Evidence")
    sources = {row["Source"] for row in rows}
    expected = {"Build Contract", "Repository evidence", "Verification", "Decision log"}
    missing = sorted(expected - sources)
    if missing:
        raise ReportError(f"Implementation Evidence is missing sources: {', '.join(missing)}")


def validate_supporting_sections(lines: Sequence[str], ranges: Mapping[str, tuple[int, int]]) -> None:
    require_table(
        lines,
        ranges["Process Gaps and Missing Evidence"],
        ("Item", "Evidence", "Authority impact", "Required action"),
        "Process Gaps and Missing Evidence",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument(
        "--lesson-store",
        action="append",
        nargs=3,
        metavar=("STORE", "PRE", "POST"),
        default=[],
        help="bind one report Store label to pre- and post-audit lesson files; use '-' for absent",
    )
    arguments = parser.parse_args(argv)
    try:
        bundle = load_object(arguments.bundle, "compiler evidence bundle")
        contract_digest, requirement_ids, verification_ids = bundle_ids(bundle)
        if not arguments.report.is_file():
            raise ReportError("postmortem report not found")
        try:
            lines = arguments.report.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            raise ReportError("postmortem report is not valid UTF-8 text") from error
        headings = heading_index(lines)
        conclusion_headings = [index for index, level, title in headings if level == 2 and title == "Conclusion"]
        if len(conclusion_headings) != 1:
            raise ReportError("report requires exactly one Conclusion section")
        schema = metadata_values(lines, conclusion_headings[0]).get("postmortem_schema")
        if schema == COMPACT_REPORT_SCHEMA:
            if arguments.lesson_store:
                raise ReportError("postmortem_schema 3 does not support lesson-store rows")
            ranges = section_ranges(lines, COMPACT_REQUIRED_SECTIONS, exact=True)
            metadata(lines, ranges["Conclusion"][0] - 1, contract_digest, COMPACT_REPORT_SCHEMA)
            counts = validate_compact_conclusion(lines, ranges["Conclusion"], len(requirement_ids))
            validate_compact_findings(lines, ranges["Findings"], requirement_ids, counts)
            validate_compact_verifications(lines, ranges["Verification"], verification_ids)
        elif schema == LEGACY_REPORT_SCHEMA:
            ranges = section_ranges(lines, LEGACY_REQUIRED_SECTIONS)
            metadata(lines, ranges["Conclusion"][0] - 1, contract_digest, LEGACY_REPORT_SCHEMA)
            counts, _ = validate_conclusion(lines, ranges["Conclusion"], len(requirement_ids))
            classes, _ = validate_divergence(lines, ranges["Divergence Table"], requirement_ids, counts)
            validate_implementation_evidence(lines, ranges["Implementation Evidence"])
            validate_finding_details(lines, ranges["Finding Details"], classes)
            validate_verifications(lines, ranges["Verification Execution"], verification_ids)
            validate_lessons(lines, ranges["Lessons"], lesson_state_arguments(arguments.lesson_store))
            validate_supporting_sections(lines, ranges)
        else:
            raise ReportError("postmortem_schema must be 2 or 3")
        print(
            f"postmortem report valid: {contract_digest} | requirements {len(requirement_ids)} | "
            f"verifications {len(verification_ids)}"
        )
        return 0
    except (OSError, UnicodeError, ReportError, ValueError) as error:
        print(f"postmortem_report_check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
