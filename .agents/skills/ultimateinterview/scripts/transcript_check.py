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
#      uv run scripts/transcript_check.py .ultimateinterview/<session>/
# ──────────────────

# Cross-checks transcript.md against protocol.json: interaction numbering,
# typed-marker vocabulary, per-type heading counts vs protocol counters,
# leftover [awaiting-answer] markers, and the exit-check line once a handoff
# exists. Hard numbering/counter violations exit 1; soft issues are warnings.
# This is the mechanical precondition for the postmortem's transcript parsing.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import ValidationError

from scripts import protocol_state

HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^## interaction (\d+) \[([a-z-]+)\]",
)
SUB_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*- \[([^\]]+)\]")
HEADING_TYPES: Final[frozenset[str]] = frozenset(
    {
        "brain-dump",
        "scored-question",
        "bundle",
        "batch",
        "checkpoint",
        "sweep",
        "framing",
        "contrarian-probe",
    },
)
KNOWN_SUB_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "pressure-followup",
        "sweep: from-ledger",
        "contrarian: self-run",
        "contrarian: lane",
        "note",
        "repo-work",
        "decomposition",
        "scope-reduction",
        "scope-addition",
        "single-channel",
        "fatigue",
        "awaiting-answer",
    },
)
AWAITING_MARKER: Final[str] = "[awaiting-answer]"
EXIT_CHECK_PATTERN: Final[re.Pattern[str]] = re.compile(r"exit.check", re.IGNORECASE)

# Heading counts cross-checked against protocol counters. Free variants
# (sub-bullet sweeps/contrarians) also increment the counters, so headings
# may undershoot the counter but never exceed it.
COUNTER_FOR_TYPE: Final[dict[str, str]] = {
    "checkpoint": "falsification_checkpoints_run",
    "sweep": "sweeps_run",
    "contrarian-probe": "contrarian_probes_run",
}


def main(
    session_dir: Annotated[
        Path,
        typer.Argument(help="Session directory containing transcript.md and protocol.json."),
    ],
) -> None:
    transcript_path = session_dir / "transcript.md"
    protocol_path = session_dir / "protocol.json"
    if not transcript_path.is_file():
        raise typer.BadParameter(f"transcript.md not found: {transcript_path}")
    if not protocol_path.is_file():
        raise typer.BadParameter(f"protocol.json not found: {protocol_path}")
    try:
        state = protocol_state.parse_state(protocol_path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as error:
        raise typer.BadParameter(
            f"protocol.json: {protocol_state.summarize_validation_error(error)}",
        ) from error

    lines = transcript_path.read_text(encoding="utf-8").splitlines()
    failures: list[str] = []
    warnings: list[str] = []

    headings: list[tuple[int, int, str]] = []  # (line number, interaction, type)
    for line_number, line in enumerate(lines, start=1):
        match = HEADING_PATTERN.match(line)
        if match:
            headings.append((line_number, int(match.group(1)), match.group(2)))

    expected = 1
    for line_number, number, heading_type in headings:
        if heading_type not in HEADING_TYPES:
            failures.append(
                f"line {line_number}: unknown interaction type [{heading_type}]; "
                f"use one of: {', '.join(sorted(HEADING_TYPES))}",
            )
        if number != expected:
            failures.append(
                f"line {line_number}: interaction {number} out of order (expected {expected})",
            )
            expected = number + 1
        else:
            expected += 1

    if headings:
        last_interaction = headings[-1][1]
        if last_interaction != state.interactions_used:
            failures.append(
                f"last transcript interaction is {last_interaction} but "
                f"protocol interactions_used is {state.interactions_used}; "
                "the counter is wrong, not the transcript",
            )
    elif state.interactions_used > 0:
        warnings.append(
            f"protocol counts {state.interactions_used} interaction(s) but the "
            "transcript has no typed interaction headings",
        )

    type_counts: dict[str, int] = {}
    for _, _, heading_type in headings:
        type_counts[heading_type] = type_counts.get(heading_type, 0) + 1
    for heading_type, counter_name in COUNTER_FOR_TYPE.items():
        heading_count = type_counts.get(heading_type, 0)
        counter = getattr(state, counter_name)
        if heading_count > counter:
            failures.append(
                f"{heading_count} [{heading_type}] heading(s) but {counter_name} is {counter}",
            )

    awaiting_lines = [
        line_number
        for line_number, line in enumerate(lines, start=1)
        if AWAITING_MARKER in line
    ]
    if awaiting_lines:
        last_heading_line = headings[-1][0] if headings else 0
        stale = [number for number in awaiting_lines if number < last_heading_line]
        if stale:
            failures.append(
                f"[awaiting-answer] marker(s) in already-answered sections at line(s) "
                f"{', '.join(map(str, stale))}; replace them when the answer lands",
            )
        if len(awaiting_lines) > 1:
            warnings.append(
                f"{len(awaiting_lines)} [awaiting-answer] markers; at most one "
                "question should be in flight",
            )

    for line_number, line in enumerate(lines, start=1):
        match = SUB_MARKER_PATTERN.match(line)
        if not match:
            continue
        marker = match.group(1)
        if marker in KNOWN_SUB_MARKERS or marker.startswith("correction"):
            continue
        warnings.append(f"line {line_number}: unrecognized sub-bullet marker [{marker}]")

    if (session_dir / "handoff.md").is_file():
        text = "\n".join(lines)
        if not EXIT_CHECK_PATTERN.search(text):
            warnings.append(
                "handoff.md exists but the transcript has no exit-check line "
                "(interactions used, due_now_corrections, origin histogram)",
            )

    for failure in failures:
        typer.echo(f"- FAIL: {failure}")
    for warning in warnings:
        typer.echo(f"- warn: {warning}")
    if not failures and not warnings:
        typer.echo("- transcript consistent with protocol.json")
    elif not failures:
        typer.echo("- no hard failures")
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
