#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
#
# Shared identity and command parsing contract for verification capture and lint.

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import sys
from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

# Reuse the canonical shell-cell parser from the sibling ultimateinterview skill.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)

import verification_lint  # noqa: E402

HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(.*)$")
COMMAND_HEADER: Final[re.Pattern[str]] = re.compile(r"command|verification", re.IGNORECASE)
CAPTURED_OUTPUT_MARKER: Final[str] = "CAPTURED-OUTPUT"


@dataclass(frozen=True, slots=True)
class VerificationRow:
    """One row from Part 1's Verification Commands table."""

    row_number: int
    check: str
    kind: str
    raw_command: str
    effective_heads: tuple[str, ...]
    is_command_row: bool
    verification_id: str = ""
    pass_condition: str = ""
    run_policy: str = ""


class CapturedOutput(BaseModel):
    """Facts captured while executing one Part-1 verification command."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)

    marker: Literal["CAPTURED-OUTPUT"] = CAPTURED_OUTPUT_MARKER
    spec_row_number: int = Field(ge=1)
    check: str
    kind: str
    exact_command: str
    command_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_heads: tuple[str, ...]
    cwd: str
    started_at: str
    ended_at: str
    spawned: bool
    timed_out: bool
    timeout_seconds: int = Field(gt=0)
    exit_code: int | None
    stdout: str
    stderr: str
    stdout_full_bytes: int = Field(ge=0)
    stderr_full_bytes: int = Field(ge=0)
    stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def command_digest_is_canonical(self) -> CapturedOutput:
        if self.command_digest != canonical_command_digest(self.exact_command):
            raise PydanticCustomError(
                "captured_output_digest",
                "command_digest must match canonical_command_digest(exact_command)",
            )
        return self


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return normalized heading/body pairs, matching postmortem lint helpers."""
    sections: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match is not None:
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
    """Return the first section whose normalized heading contains ``key``."""
    for heading, body in sections:
        if key in heading:
            return body
    return None


def effective_heads(raw_command: str) -> tuple[str, ...]:
    """Return the canonical, unique effective command heads for one cell."""
    return tuple(sorted(set(verification_lint.command_heads(raw_command))))


def _column_index(headers: list[str], pattern: re.Pattern[str]) -> int | None:
    return next(
        (index for index, header in enumerate(headers) if pattern.search(header)), None
    )


def _kind(check: str, kind_cell: str, is_command_row: bool) -> str:
    explicit = kind_cell.strip().strip("`").strip().lower()
    if explicit:
        return explicit
    lowered_check = check.lower()
    if "real-surface" in lowered_check:
        return "real-surface"
    if "test" in lowered_check or "suite" in lowered_check:
        return "test"
    return "other" if is_command_row else "prose"


def _verification_table(part1: str) -> tuple[list[str], list[list[str]]] | None:
    body = section_body(split_sections(part1), "verification commands")
    if body is None:
        return None
    for headers, rows in verification_lint.tables(body):
        if _column_index(headers, COMMAND_HEADER) is not None:
            return headers, rows
    return None


def parse_verification_rows(part1: str) -> list[VerificationRow]:
    """Parse Part 1's Verification Commands table in displayed table order.

    Rows without command heads are retained as prose/action rows so producer and
    consumer share the same stable row-number identity.
    """
    table = _verification_table(part1)
    if table is None:
        return []
    headers, rows = table
    command_column = _column_index(headers, COMMAND_HEADER)
    if command_column is None:
        return []
    check_column = _column_index(headers, re.compile(r"check", re.IGNORECASE))
    kind_column = _column_index(headers, re.compile(r"kind", re.IGNORECASE))
    id_column = _column_index(
        headers, re.compile(r"^(?:id|ver-id|verification id)$", re.IGNORECASE)
    )
    pass_column = _column_index(headers, re.compile(r"pass condition", re.IGNORECASE))
    policy_column = _column_index(headers, re.compile(r"run policy", re.IGNORECASE))
    parsed: list[VerificationRow] = []
    for row_number, row in enumerate(rows, start=1):
        check = row[check_column] if check_column is not None and check_column < len(row) else ""
        raw_command = row[command_column] if command_column < len(row) else ""
        heads = effective_heads(raw_command)
        run_policy = (
            row[policy_column]
            if policy_column is not None and policy_column < len(row)
            else ""
        )
        is_command_row = bool(heads) or run_policy == "safe-auto"
        kind_cell = row[kind_column] if kind_column is not None and kind_column < len(row) else ""
        parsed.append(
            VerificationRow(
                row_number=row_number,
                check=check,
                kind=_kind(check, kind_cell, is_command_row),
                raw_command=raw_command,
                effective_heads=heads,
                is_command_row=is_command_row,
                verification_id=(
                    row[id_column] if id_column is not None and id_column < len(row) else ""
                ),
                pass_condition=(
                    row[pass_column]
                    if pass_column is not None and pass_column < len(row)
                    else ""
                ),
                run_policy=run_policy,
            )
        )
    return parsed


def canonical_command_digest(raw_command: str) -> str:
    """Return a stable SHA-256 digest for a command cell.

    Normalization strips surrounding whitespace and Markdown backticks, removes
    one trailing ``(source: ...)`` tag recognized by ``verification_lint.SOURCE_TAG``,
    and collapses every internal whitespace run to one ASCII space before UTF-8
    hashing. The result is reproducible across equivalent handoff formatting.
    """
    normalized = raw_command.strip()
    source_tag = verification_lint.SOURCE_TAG.search(normalized)
    if source_tag is not None and not normalized[source_tag.end() :].strip():
        normalized = normalized[:source_tag.start()].rstrip()
    normalized = normalized.strip().strip("`").strip()
    normalized = " ".join(normalized.split())
    return sha256(normalized.encode("utf-8")).hexdigest()


def row_identity(row: VerificationRow) -> tuple[int, str]:
    """Return the stable Part-1 identity used to join verification reports."""
    return row.row_number, row.check


def captured_output_matches(row: VerificationRow, rec: CapturedOutput) -> bool:
    """Return whether a capture is a usable fact record for ``row``."""
    return (
        row_identity(row) == (rec.spec_row_number, rec.check)
        and rec.command_digest == canonical_command_digest(row.raw_command)
        and set(row.effective_heads) == set(rec.effective_heads)
        and rec.spawned
        and not rec.timed_out
    )
