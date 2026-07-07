#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
#      uv run scripts/lessons.py validate <lessons.md>
#      uv run scripts/lessons.py list <lessons.md>
#      uv run scripts/lessons.py fire <lessons.md> <index-or-signal-substring> [--caught]
# ──────────────────

# Deterministic lessons-store bookkeeping for the postmortem loop: validates
# the table shape, lists active rows, and applies Fired/Caught increments with
# the automatic 3-dry-fire retirement - so fire-tracking arithmetic and the
# retirement rule never run in model memory.

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final

import typer

app = typer.Typer(add_completion=False)

ACTIVE_HEADER: Final[str] = "| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |"
RETIRED_HEADING: Final[str] = "## Retired"
RETIRED_HEADER: Final[str] = "| Signal | Lens to trigger | Retired date | Reason |"
FIRE_FORMAT: Final[re.Pattern[str]] = re.compile(r"^(\d+)/(\d+)$")
RETIRE_AFTER_DRY_FIRES: Final[int] = 3
ACTIVE_COLUMNS: Final[int] = 6


@dataclass(frozen=True, slots=True)
class LessonRow:
    signal: str
    lens: str
    failure_class: str
    evidence: str
    date: str
    fired: int
    caught: int

    def as_line(self) -> str:
        return (
            f"| {self.signal} | {self.lens} | {self.failure_class} "
            f"| {self.evidence} | {self.date} | {self.fired}/{self.caught} |"
        )


@dataclass(frozen=True, slots=True)
class LessonsFile:
    lines: list[str]
    active_header_index: int  # index of the ACTIVE_HEADER line
    row_indices: list[int]  # line indices of active rows, in order
    rows: list[LessonRow]
    retired_header_index: int  # index of the RETIRED_HEADER line (-1 when absent)


def split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_row(line: str, line_number: int) -> LessonRow:
    cells = split_cells(line)
    if len(cells) != ACTIVE_COLUMNS:
        raise typer.BadParameter(
            f"line {line_number}: active lesson row needs {ACTIVE_COLUMNS} cells, got {len(cells)}",
        )
    match = FIRE_FORMAT.match(cells[5])
    if match is None:
        raise typer.BadParameter(
            f"line {line_number}: Fired/Caught must look like '2/1', got {cells[5]!r}",
        )
    return LessonRow(
        signal=cells[0],
        lens=cells[1],
        failure_class=cells[2],
        evidence=cells[3],
        date=cells[4],
        fired=int(match.group(1)),
        caught=int(match.group(2)),
    )


def parse_file(path: Path) -> LessonsFile:
    if not path.is_file():
        raise typer.BadParameter(f"lessons file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        header_index = next(
            index for index, line in enumerate(lines) if line.strip() == ACTIVE_HEADER
        )
    except StopIteration:
        raise typer.BadParameter(
            f"{path}: active table header not found; expected exactly: {ACTIVE_HEADER}",
        ) from None
    if header_index + 1 >= len(lines) or not lines[header_index + 1].strip().startswith("| ---"):
        raise typer.BadParameter(f"{path}: separator row missing under the active table header")
    row_indices: list[int] = []
    rows: list[LessonRow] = []
    for index in range(header_index + 2, len(lines)):
        line = lines[index]
        if not line.strip().startswith("|"):
            break
        rows.append(parse_row(line, index + 1))
        row_indices.append(index)
    signals = [row.signal for row in rows]
    duplicates = sorted({signal for signal in signals if signals.count(signal) > 1})
    if duplicates:
        raise typer.BadParameter(f"{path}: duplicate signal row(s): {duplicates}")
    retired_header_index = next(
        (index for index, line in enumerate(lines) if line.strip() == RETIRED_HEADER),
        -1,
    )
    if RETIRED_HEADING not in {line.strip() for line in lines}:
        raise typer.BadParameter(f"{path}: '{RETIRED_HEADING}' section missing")
    if retired_header_index < 0:
        raise typer.BadParameter(
            f"{path}: retired table header not found; expected exactly: {RETIRED_HEADER}",
        )
    return LessonsFile(
        lines=lines,
        active_header_index=header_index,
        row_indices=row_indices,
        rows=rows,
        retired_header_index=retired_header_index,
    )


def select_row(parsed: LessonsFile, selector: str) -> int:
    """Return the position (0-based within rows) matched by a 1-based index
    or a unique case-insensitive signal substring."""
    if selector.isdigit():
        position = int(selector) - 1
        if not 0 <= position < len(parsed.rows):
            raise typer.BadParameter(
                f"row {selector} out of range; the file has {len(parsed.rows)} active row(s)",
            )
        return position
    needle = selector.lower()
    hits = [
        position
        for position, row in enumerate(parsed.rows)
        if needle in row.signal.lower()
    ]
    if len(hits) != 1:
        raise typer.BadParameter(
            f"signal substring {selector!r} matched {len(hits)} row(s); "
            "use a unique substring or the 1-based row index",
        )
    return hits[0]


@app.command()
def validate(
    path: Annotated[Path, typer.Argument(help="Lessons markdown file.")],
) -> None:
    """Fail-closed structural check of both tables."""
    parsed = parse_file(path)
    typer.echo(
        f"- valid: {len(parsed.rows)} active lesson row(s), retired section present",
    )


@app.command("list")
def list_rows(
    path: Annotated[Path, typer.Argument(help="Lessons markdown file.")],
) -> None:
    """Active rows with their fire-tracking state."""
    parsed = parse_file(path)
    if not parsed.rows:
        typer.echo("- no active lesson rows")
        return
    for position, row in enumerate(parsed.rows, start=1):
        signal = row.signal if len(row.signal) <= 80 else row.signal[:77] + "..."
        typer.echo(f"{position}. [{row.lens}] {row.fired}/{row.caught} — {signal}")


@app.command()
def fire(
    path: Annotated[Path, typer.Argument(help="Lessons markdown file.")],
    selector: Annotated[
        str,
        typer.Argument(help="1-based row index or unique signal substring."),
    ],
    caught: Annotated[
        bool,
        typer.Option("--caught", help="The triggered lens produced a ledger entry."),
    ] = False,
) -> None:
    """Increment Fired (and Caught with --caught); auto-retire at 3 dry fires."""
    parsed = parse_file(path)
    position = select_row(parsed, selector)
    row = parsed.rows[position]
    updated = replace(
        row,
        fired=row.fired + 1,
        caught=row.caught + (1 if caught else 0),
    )
    lines = list(parsed.lines)
    if updated.fired >= RETIRE_AFTER_DRY_FIRES and updated.caught == 0:
        stamp = datetime.now().strftime("%Y-%m-%d")
        retired_line = (
            f"| {updated.signal} | {updated.lens} | {stamp} "
            f"| auto-retired by lessons.py: {updated.fired} fires, 0 catches |"
        )
        del lines[parsed.row_indices[position]]
        # Recompute the retired header position after the deletion above.
        retired_header = parsed.retired_header_index
        if retired_header > parsed.row_indices[position]:
            retired_header -= 1
        insert_at = retired_header + 2  # header + separator
        lines.insert(insert_at, retired_line)
        outcome = f"- RETIRED (dry-fired {updated.fired}x): {updated.signal[:60]}"
    else:
        lines[parsed.row_indices[position]] = updated.as_line()
        outcome = (
            f"- fired: {updated.fired}/{updated.caught} "
            f"({'caught' if caught else 'dry fire'}): {updated.signal[:60]}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    typer.echo(outcome)


if __name__ == "__main__":
    app()
