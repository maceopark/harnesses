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
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/handoff_coverage.py <session-dir>
#      uv run scripts/handoff_coverage.py --format markdown <session-dir>
# ──────────────────
#
# Ledger -> Build-Contract traceability gate.
#
# Every material-settled ledger entry (low ambiguity, weight >= --min-weight,
# not deferred) MUST be cited by id somewhere in Part 1 (the Build Contract) of
# handoff.md, or be an explicit non-goal/deferral living in Part 1. This is the
# DETERMINISTIC floor under the non-deterministic behavior-fidelity rule in
# references/handoff-sequence.md: the ledger→handoff synthesis step silently
# narrowing or dropping a settled behavior (todo-cli-app-4 postmortem: ledger
# g14 settled "corrupt/permission/write failure" but the Build Contract kept
# only "corrupt") is a synthesis-loss escape. Id-citation coverage cannot prove
# a REQ reproduced the FULL behavior of its source entry, but it does prove no
# settled entry vanished from the contract untraced. Fail-closed: exit 1 when a
# material-settled entry id is absent from Part 1.

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ambiguity_ledger import LedgerEntry, parse_entries  # noqa: E402

DEFAULT_MIN_WEIGHT: Final[int] = 2
PART1_START: Final[re.Pattern[str]] = re.compile(r"^#+\s*Part\s*1\b", re.IGNORECASE | re.MULTILINE)
PART2_START: Final[re.Pattern[str]] = re.compile(r"^#+\s*Part\s*2\b", re.IGNORECASE | re.MULTILINE)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def extract_part1(handoff_text: str) -> str:
    """Return the Build Contract (Part 1) slice, or the whole doc when the
    Part 1 / Part 2 markers are absent (a single-part handoff is all contract)."""
    visible_offsets: list[tuple[int, str]] = []
    fence_character: str | None = None
    fence_length = 0
    offset = 0
    for line in handoff_text.splitlines(keepends=True):
        match = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line)
        marker = match.group(1) if match is not None else ""
        if fence_character is None and marker:
            fence_character = marker[0]
            fence_length = len(marker)
        elif (
            fence_character is not None
            and marker
            and match is not None
            and marker[0] == fence_character
            and len(marker) >= fence_length
            and not line[match.end() :].strip()
        ):
            fence_character = None
            fence_length = 0
        elif fence_character is None:
            visible_offsets.append((offset, line))
        offset += len(line)

    part1_offsets = [offset for offset, line in visible_offsets if PART1_START.match(line)]
    start = part1_offsets[0] if part1_offsets else 0
    part2_offsets = [
        offset
        for offset, line in visible_offsets
        if offset >= start and PART2_START.match(line)
    ]
    end = part2_offsets[0] if part2_offsets else len(handoff_text)
    return handoff_text[start:end]


def id_is_cited(entry_id: str, text: str) -> bool:
    # Whole-token match so `g1` does not match inside `g11`.
    pattern = re.compile(rf"(?<![0-9A-Za-z_-]){re.escape(entry_id)}(?![0-9A-Za-z_-])")
    return pattern.search(text) is not None


def material_settled(entry: LedgerEntry, min_weight: int) -> bool:
    return (
        not entry.is_deferred
        and entry.impact_weight >= min_weight
        and entry.ambiguity_score <= 1
    )


@app.command()
def main(
    session_dir: Annotated[Path, typer.Argument(help="Session dir with ledger.json and handoff.md")],
    min_weight: Annotated[int, typer.Option(help="Minimum impact_weight to require Part-1 citation.")] = DEFAULT_MIN_WEIGHT,
    fmt: Annotated[str, typer.Option("--format", help="json or markdown")] = "markdown",
    advisory: Annotated[bool, typer.Option(help="Report only; never exit non-zero.")] = False,
) -> None:
    ledger_path = session_dir / "ledger.json"
    handoff_path = session_dir / "handoff.md"
    if not ledger_path.is_file():
        typer.echo(f"error: missing ledger.json at {ledger_path}", err=True)
        raise typer.Exit(2)
    if not handoff_path.is_file():
        typer.echo(f"error: missing handoff.md at {handoff_path}; run this after the handoff is written", err=True)
        raise typer.Exit(2)

    try:
        entries = parse_entries(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - fail closed with the one-line reason
        typer.echo(f"error: ledger.json did not validate: {exc}", err=True)
        raise typer.Exit(2) from exc

    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    considered = [e for e in entries if material_settled(e, min_weight)]
    covered = [e for e in considered if id_is_cited(e.id, part1)]
    uncovered = [e for e in considered if not id_is_cited(e.id, part1)]

    if fmt == "json":
        import json

        typer.echo(
            json.dumps(
                {
                    "min_weight": min_weight,
                    "considered": len(considered),
                    "covered": [e.id for e in covered],
                    "uncovered": [
                        {"id": e.id, "impact_weight": e.impact_weight, "ambiguity_score": e.ambiguity_score, "requirement": e.requirement}
                        for e in uncovered
                    ],
                    "coverage_ok": not uncovered,
                },
                indent=2,
            )
        )
    else:
        typer.echo("## Handoff Coverage Gate\n")
        typer.echo(f"- Material-settled entries (weight >= {min_weight}, score <= 1, not deferred): {len(considered)}")
        typer.echo(f"- Cited in Part 1 (Build Contract): {len(covered)}")
        typer.echo(f"- Uncovered (settled but absent from Part 1): {len(uncovered)}")
        if uncovered:
            typer.echo("\n### Uncovered — synthesis-loss risk\n")
            typer.echo("| ID | Weight | Requirement (truncated) |")
            typer.echo("| --- | --- | --- |")
            for e in uncovered:
                req = (e.requirement or "").replace("\n", " ")[:80]
                typer.echo(f"| {e.id} | {e.impact_weight} | {req} |")
            typer.echo(
                "\nEach uncovered entry was SETTLED in the ledger but its id is not cited in Part 1. "
                "Cite it in the Part-1 row that implements it (Behavior Contract Source cell, or an inline "
                "`(source: <id>)` tag in Goal/Quality Bars/Decision Boundaries/Out-of-scope), or move it to "
                "Deferred Risks with owner/date. Then confirm the Part-1 row reproduces the FULL enumerated "
                "behavior of the entry, not a narrowed subset."
            )
        typer.echo(f"\n- coverage_ok: {'yes' if not uncovered else 'no'}")

    if uncovered and not advisory:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
