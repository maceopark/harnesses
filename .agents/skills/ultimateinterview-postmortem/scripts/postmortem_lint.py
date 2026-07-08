#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
# (pydantic/rich are pulled in by the shared handoff_coverage/lessons imports.)

# ─── How to run ───
#      uv run scripts/postmortem_lint.py <session-dir> \
#        [--lessons <lessons.md>]... [--advisory]
# ──────────────────
#
# Report-contract gate for postmortem.md.
#
# The first executor-authored postmortem (todo-cli-app-5) skipped whole
# Output-Contract sections, aggregated REQ ranges into single divergence rows
# ("REQ-001 through REQ-006" - which silently corrupts the discovery-rate
# denominator), reported one informal rate instead of the two required ones,
# and never walked the lessons stores for fire-tracking. Every one of those
# failures is mechanical, so this gate owns them: section completeness, row
# granularity, class vocabulary, calibration arithmetic recomputed FROM the
# divergence table (the table IS the denominator), and one fire-tracking row
# per active lesson. Semantic quality (correct classification, honest
# evidence) stays with the auditor - a lint cannot judge it.
#
# Fail-closed like its siblings: exit 1 on any violation unless --advisory;
# exit 2 when an input file is missing or unparseable.

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

# Deterministic helpers shared with the sibling ultimateinterview skill.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)

import lessons as lessons_store  # noqa: E402
from handoff_coverage import extract_part1  # noqa: E402

DIVERGENCE_CLASSES: Final[tuple[str, ...]] = (
    "fulfilled",
    "escaped-requirement",
    "scope-drift",
    "divergent-implementation",
    "deferred-outcome",
)
FAILURE_CLASSES: Final[tuple[str, ...]] = (
    "trigger-too-narrow",
    "enumeration-miss",
    "scoring-starved",
    "answer-unpressured",
    "synthesis-loss",
)
ESCAPE_WEIGHTS: Final[frozenset[int]] = frozenset({1, 2, 3, 5})
REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "implementation evidence",
    "divergence table",
    "escaped requirements",
    "deferred outcomes",
    "verification execution",
    "scope drift",
    "lessons appended",
    "lessons fire-tracking",
    "calibration summary",
)
REQ_ID: Final[re.Pattern[str]] = re.compile(r"REQ-\d+")
REQ_RANGE: Final[re.Pattern[str]] = re.compile(
    r"REQ-\d+\s*(?:through|to|[–—~]|\.\.)\s*(?:REQ-)?\d+", re.IGNORECASE
)
HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(.*)$")
PERCENT: Final[re.Pattern[str]] = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RATE_TOLERANCE: Final[float] = 0.55

app = typer.Typer(add_completion=False, no_args_is_help=True)


def split_sections(text: str) -> list[tuple[str, str]]:
    """(normalized heading, body-until-next-heading) pairs, any heading level."""
    sections: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            if current is not None:
                sections.append((current, "\n".join(body)))
            current = match.group(1).strip().lower()
            body = []
        else:
            body.append(line)
    if current is not None:
        sections.append((current, "\n".join(body)))
    return sections


def section_body(sections: list[tuple[str, str]], key: str) -> str | None:
    for heading, body in sections:
        if key in heading:
            return body
    return None


def first_table(body: str) -> tuple[list[str], list[list[str]]] | None:
    lines = [line.strip() for line in body.splitlines()]
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("|")), None
    )
    if start is None or start + 1 >= len(lines):
        return None
    if not lines[start + 1].startswith("|") or "---" not in lines[start + 1]:
        return None

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    headers = cells(lines[start])
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(cells(line))
    return headers, rows


def column_index(headers: list[str], needle: str) -> int | None:
    for index, header in enumerate(headers):
        if needle in header.lower():
            return index
    return None


def cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def whole_token(needle: str, haystack: str) -> bool:
    pattern = re.compile(rf"(?<![0-9A-Za-z_-]){re.escape(needle)}(?![0-9A-Za-z_-])")
    return pattern.search(haystack) is not None


def leading_class(value: str, vocabulary: tuple[str, ...]) -> str | None:
    lowered = value.strip().lower()
    for token in vocabulary:
        if lowered.startswith(token):
            return token
    return None


def check_divergence(
    body: str, part1: str, violations: list[str]
) -> dict[str, int]:
    counts = dict.fromkeys(DIVERGENCE_CLASSES, 0)
    table = first_table(body)
    if table is None:
        violations.append("Divergence Table section has no markdown table")
        return counts
    headers, rows = table
    class_column = column_index(headers, "class")
    if class_column is None:
        violations.append("Divergence Table has no Class column")
        return counts
    if not rows:
        violations.append("Divergence Table has no rows - the audit has no denominator")

    table_ids: set[str] = set()
    for number, row in enumerate(rows, start=1):
        id_cell = cell(row, 0)
        if REQ_RANGE.search(id_cell):
            violations.append(
                f"Divergence Table row {number} aggregates a REQ range ({id_cell!r}) - "
                "one row per requirement; ranges corrupt the discovery-rate denominator"
            )
        table_ids.update(REQ_ID.findall(id_cell))
        token = leading_class(cell(row, class_column), DIVERGENCE_CLASSES)
        if token is None:
            violations.append(
                f"Divergence Table row {number} has unknown class "
                f"{cell(row, class_column)!r} (expected one of {', '.join(DIVERGENCE_CLASSES)})"
            )
        else:
            counts[token] += 1

    missing = sorted(set(REQ_ID.findall(part1)) - table_ids)
    if missing:
        violations.append(
            "Part-1 requirement(s) absent from the Divergence Table: " + ", ".join(missing)
        )
    return counts


def check_escapes(
    body: str | None, escaped_count: int, violations: list[str]
) -> int:
    """Validate the Escaped Requirements table; return the synthesis-loss row count."""
    table = first_table(body) if body is not None else None
    if table is None:
        if escaped_count:
            violations.append(
                f"Divergence Table counts {escaped_count} escaped-requirement row(s) "
                "but the Escaped Requirements section has no table"
            )
        return 0
    headers, rows = table
    if len(rows) != escaped_count:
        violations.append(
            f"Escaped Requirements table has {len(rows)} row(s) but the Divergence Table "
            f"counts {escaped_count} escaped-requirement row(s) - they must match 1:1"
        )
    if not rows:
        return 0
    failure_column = column_index(headers, "failure")
    weight_column = column_index(headers, "weight")
    if failure_column is None:
        violations.append("Escaped Requirements table has no failure-class column")
    if weight_column is None:
        violations.append("Escaped Requirements table has no Weight column (1/2/3/5)")
    synthesis = 0
    for number, row in enumerate(rows, start=1):
        if failure_column is not None:
            token = leading_class(cell(row, failure_column), FAILURE_CLASSES)
            if token is None:
                violations.append(
                    f"Escaped Requirements row {number} has unknown failure class "
                    f"{cell(row, failure_column)!r}"
                )
            elif token == "synthesis-loss":
                synthesis += 1
        if weight_column is not None:
            digits = re.search(r"\d+", cell(row, weight_column))
            if digits is None or int(digits.group()) not in ESCAPE_WEIGHTS:
                violations.append(
                    f"Escaped Requirements row {number} weight "
                    f"{cell(row, weight_column)!r} is not one of 1/2/3/5"
                )
    return synthesis


def check_calibration(
    body: str | None,
    counts: dict[str, int],
    synthesis: int,
    violations: list[str],
) -> None:
    if body is None:
        return  # section-presence check already reported it
    table = first_table(body)
    if table is None:
        violations.append("Calibration Summary has no divergence-class count table")
    else:
        _, rows = table
        for token in DIVERGENCE_CLASSES:
            declared = next(
                (row for row in rows if cell(row, 0).lower().startswith(token)), None
            )
            if declared is None:
                violations.append(f"Calibration Summary is missing a count row for {token}")
                continue
            digits = re.search(r"\d+", cell(declared, 1))
            if digits is None or int(digits.group()) != counts[token]:
                violations.append(
                    f"Calibration Summary declares {token} = {cell(declared, 1)!r} "
                    f"but the Divergence Table counts {counts[token]}"
                )

    fulfilled = counts["fulfilled"]
    escaped = counts["escaped-requirement"]
    divergent = counts["divergent-implementation"]
    lowered = body.lower()
    for label in ("interview-discovery", "handoff-fidelity"):
        if label not in lowered:
            violations.append(f"Calibration Summary never states the {label} rate")
    if escaped and "weighted" not in lowered:
        violations.append(
            "Calibration Summary has escapes but no weighted rate beside the raw one"
        )

    denominator = fulfilled + escaped + divergent
    if denominator == 0:
        return
    stated = [float(match.group(1)) for match in PERCENT.finditer(body)]
    expected = {
        "interview-discovery": 100.0 * fulfilled / (fulfilled + (escaped - synthesis) + divergent),
        "handoff-fidelity": 100.0 * fulfilled / denominator,
    }
    for label, rate in expected.items():
        if not any(abs(value - rate) <= RATE_TOLERANCE for value in stated):
            violations.append(
                f"Calibration Summary states no percentage within {RATE_TOLERANCE} "
                f"of the recomputed {label} rate {rate:.1f}%"
            )


def check_fire_tracking(
    body: str | None, lessons_paths: list[Path], violations: list[str]
) -> None:
    if not lessons_paths:
        return
    table = first_table(body) if body is not None else None
    for path in lessons_paths:
        try:
            active_rows = len(lessons_store.parse_file(path).rows)
        except typer.BadParameter as error:
            violations.append(f"lessons store {path} did not parse: {error}")
            continue
        if active_rows == 0:
            continue
        if table is None:
            violations.append(
                f"Lessons Fire-Tracking has no table but {path.name} has "
                f"{active_rows} active row(s) to walk"
            )
            continue
        _, rows = table
        for index in range(1, active_rows + 1):
            hit = any(
                whole_token(path.name, cell(row, 0))
                and whole_token(str(index), cell(row, 1))
                for row in rows
            )
            if not hit:
                violations.append(
                    f"Lessons Fire-Tracking is missing a row for {path.name} "
                    f"active lesson #{index} - every active lesson gets a "
                    "fired/no-signal verdict, every run"
                )


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Session dir with postmortem.md and handoff.md")
    ],
    lessons: Annotated[
        list[Path] | None,
        typer.Option(
            "--lessons",
            help="Lessons store to enforce fire-tracking against (repeatable).",
        ),
    ] = None,
    advisory: Annotated[
        bool, typer.Option(help="Report only; never exit non-zero.")
    ] = False,
) -> None:
    report_path = session_dir / "postmortem.md"
    handoff_path = session_dir / "handoff.md"
    for path, label in ((report_path, "postmortem.md"), (handoff_path, "handoff.md")):
        if not path.is_file():
            typer.echo(f"error: missing {label} at {path}", err=True)
            raise typer.Exit(2)

    report = report_path.read_text(encoding="utf-8")
    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    sections = split_sections(report)

    violations: list[str] = []
    for key in REQUIRED_SECTIONS:
        if section_body(sections, key) is None:
            violations.append(f"required section missing: a heading containing {key!r}")

    counts = dict.fromkeys(DIVERGENCE_CLASSES, 0)
    divergence_body = section_body(sections, "divergence table")
    if divergence_body is not None:
        counts = check_divergence(divergence_body, part1, violations)
    synthesis = check_escapes(
        section_body(sections, "escaped requirements"),
        counts["escaped-requirement"],
        violations,
    )
    check_calibration(
        section_body(sections, "calibration summary"), counts, synthesis, violations
    )
    check_fire_tracking(
        section_body(sections, "lessons fire-tracking"), list(lessons or []), violations
    )

    if violations:
        typer.echo(f"postmortem_lint: {len(violations)} violation(s)")
        for note in violations:
            typer.echo(f"- {note}")
        if not advisory:
            raise typer.Exit(1)
    else:
        typer.echo(
            "postmortem_lint: ok - sections complete, divergence rows well-formed, "
            "calibration matches the table"
        )


if __name__ == "__main__":
    app()
