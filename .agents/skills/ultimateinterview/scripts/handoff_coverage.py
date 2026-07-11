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

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ambiguity_ledger import LedgerEntry, parse_entries  # noqa: E402
from scripts.behavior_atoms import BehaviorAtom  # noqa: E402

DEFAULT_MIN_WEIGHT: Final[int] = 2
PART1_START: Final[re.Pattern[str]] = re.compile(r"^#+\s*Part\s*1\b", re.IGNORECASE | re.MULTILINE)
PART2_START: Final[re.Pattern[str]] = re.compile(r"^#+\s*Part\s*2\b", re.IGNORECASE | re.MULTILINE)
ATOM_CATALOG_HEADERS: Final[tuple[str, ...]] = ("source", "assurance class", "atom id", "condition", "polarity", "observable response", "boundary context", "temporal context", "coercion context")

app = typer.Typer(add_completion=False, no_args_is_help=True)


@dataclass(frozen=True, slots=True)
class AtomMismatch:
    atom_id: str
    field: str
    expected: str
    actual: str

    def describe(self) -> str:
        return f"{self.atom_id} {self.field} mismatch: expected {self.expected!r}, got {self.actual!r}"


@dataclass(frozen=True, slots=True)
class AtomCoverage:
    expected_count: int
    catalog_count: int
    mismatches: tuple[AtomMismatch, ...]


@dataclass(frozen=True, slots=True)
class HandoffAtom:
    source: str
    assurance_class: str
    id: str
    condition: str
    polarity: str
    observable_response: str
    boundary_context: str
    temporal_context: str
    coercion_context: str


def extract_part1(handoff_text: str) -> str:
    """Return the Build Contract (Part 1) slice, or the whole doc when the
    Part 1 / Part 2 markers are absent (a single-part handoff is all contract)."""
    visible_offsets = _visible_markdown_lines(handoff_text)
    part1_offsets = [offset for offset, line in visible_offsets if PART1_START.match(line)]
    start = part1_offsets[0] if part1_offsets else 0
    part2_offsets = [offset for offset, line in visible_offsets if offset >= start and PART2_START.match(line)]
    end = part2_offsets[0] if part2_offsets else len(handoff_text)
    return handoff_text[start:end]


def _visible_markdown_lines(text: str) -> tuple[tuple[int, str], ...]:
    visible: list[tuple[int, str]] = []
    fence_character: str | None = None
    fence_length = 0
    offset = 0
    for line in text.splitlines(keepends=True):
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
        elif fence_character is None:
            visible.append((offset, line))
        offset += len(line)
    return tuple(visible)


def id_is_cited(entry_id: str, text: str) -> bool:
    # Whole-token match so `g1` does not match inside `g11`.
    pattern = re.compile(rf"(?<![0-9A-Za-z_-]){re.escape(entry_id)}(?![0-9A-Za-z_-])")
    return pattern.search(text) is not None


def material_settled(entry: LedgerEntry, min_weight: int) -> bool:
    return not entry.is_deferred and entry.impact_weight >= min_weight and entry.ambiguity_score <= 1


def _behavior_contract_body(part1: str) -> str:
    visible = "".join(line for _, line in _visible_markdown_lines(part1))
    visible = re.sub(r"<!--.*?(?:-->|\Z)", "", visible, flags=re.DOTALL)
    match = re.search(r"(?im)^##+\s+Behavior Contract\s*$", visible)
    if match is None:
        return ""
    body = visible[match.end() :]
    next_heading = re.search(r"(?m)^##+\s+", body)
    body = body[: next_heading.start()] if next_heading is not None else body
    return "" if re.search(r"<(?!https?://|mailto:)/?[A-Za-z][^>\n]*>", body, re.IGNORECASE) else body


def _catalog_atoms(part1: str) -> tuple[dict[str, HandoffAtom], tuple[AtomMismatch, ...]]:
    lines = tuple(line.strip() for _, line in _visible_markdown_lines(part1))
    for start, line in enumerate(lines[:-1]):
        headers = tuple(cell.lower() for cell in _table_cells(line))
        if headers != ATOM_CATALOG_HEADERS or not lines[start + 1].startswith("|") or "---" not in lines[start + 1]:
            continue
        atoms: dict[str, HandoffAtom] = {}
        mismatches: list[AtomMismatch] = []
        for row_line in lines[start + 2 :]:
            if not row_line.startswith("|"):
                break
            row = _table_cells(row_line)
            if len(row) != len(ATOM_CATALOG_HEADERS):
                mismatches.append(AtomMismatch("<catalog>", "row", "9 cells", str(len(row))))
                continue
            atom = HandoffAtom(*row)
            if atom.id in atoms:
                mismatches.append(AtomMismatch(atom.id, "id", "unique", "duplicate"))
            else:
                atoms[atom.id] = atom
        return atoms, tuple(mismatches)
    return {}, ()


def _table_cells(line: str) -> tuple[str, ...]:
    escaped_pipe = "\x00ULTIMATEINTERVIEW_PIPE\x00"
    protected = line.replace("\\|", escaped_pipe)
    return tuple(cell.replace(escaped_pipe, "|").strip() for cell in protected.strip().strip("|").split("|"))


def v2_atom_coverage(entries: tuple[LedgerEntry, ...], handoff_text: str, evidence_schema_version: int | None = 2) -> AtomCoverage:
    expected: dict[str, tuple[str, str, BehaviorAtom]] = {}
    mismatches: list[AtomMismatch] = []
    for entry in entries:
        assurance_class = "" if entry.assurance_class is None else entry.assurance_class.value
        for atom in entry.behavior_atoms:
            if atom.id in expected:
                mismatches.append(AtomMismatch(atom.id, "id", "unique", "duplicate"))
            else:
                expected[atom.id] = (entry.id, assurance_class, atom)
    if evidence_schema_version != 2:
        actual = "absent" if evidence_schema_version is None else str(evidence_schema_version)
        mismatches.append(AtomMismatch("<protocol>", "evidence_schema_version", "2", actual))
        return AtomCoverage(len(expected), 0, tuple(mismatches))
    catalog, malformed = _catalog_atoms(_behavior_contract_body(extract_part1(handoff_text)))
    mismatches.extend(malformed)
    if expected and not catalog:
        mismatches.append(AtomMismatch("<catalog>", "catalog", "present", "absent"))
    for atom_id in sorted(set(expected) - set(catalog)):
        mismatches.append(AtomMismatch(atom_id, "id", "present", "absent"))
    for atom_id in sorted(set(catalog) - set(expected)):
        mismatches.append(AtomMismatch(atom_id, "id", "absent", "present"))
    for atom_id in sorted(set(expected) & set(catalog)):
        source_id, assurance_class, expected_atom = expected[atom_id]
        actual = catalog[atom_id]
        comparisons = (
            ("source", source_id, actual.source),
            ("assurance_class", assurance_class, actual.assurance_class),
            ("condition", expected_atom.condition, actual.condition),
            ("polarity", expected_atom.polarity.value, actual.polarity),
            ("observable_response", expected_atom.observable_response, actual.observable_response),
            ("boundary_context", expected_atom.boundary_context or "", actual.boundary_context),
            ("temporal_context", expected_atom.temporal_context or "", actual.temporal_context),
            ("coercion_context", expected_atom.coercion_context or "", actual.coercion_context),
        )
        mismatches.extend(
            AtomMismatch(atom_id, field, expected_value, actual_value)
            for field, expected_value, actual_value in comparisons
            if expected_value != actual_value
        )
    return AtomCoverage(len(expected), len(catalog), tuple(mismatches))


def v2_trace_coverage(entries: tuple[LedgerEntry, ...], handoff_text: str) -> tuple[bool, bool]:
    part1 = extract_part1(handoff_text)
    requirements_covered = all(
        id_is_cited(entry.id, part1)
        for entry in entries
        if material_settled(entry, DEFAULT_MIN_WEIGHT)
    )
    atoms_covered = not v2_atom_coverage(entries, handoff_text).mismatches
    return requirements_covered, atoms_covered


def _evidence_schema_version(session_dir: Path) -> int | None:
    protocol_path = session_dir / "protocol.json"
    if not protocol_path.is_file():
        return None
    try:
        payload = json.loads(protocol_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"protocol.json is not valid JSON: {error.msg}") from error
    if not isinstance(payload, dict):
        raise typer.BadParameter("protocol.json must contain an object")
    version = payload.get("evidence_schema_version")
    if version is None:
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        raise typer.BadParameter("protocol evidence_schema_version must be an integer")
    if version not in (0, 1, 2):
        raise typer.BadParameter("protocol evidence_schema_version must be 0, 1, or 2")
    return version


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
    except (ValidationError, ValueError) as error:
        typer.echo(f"error: ledger.json did not validate: {error}", err=True)
        raise typer.Exit(2) from error

    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    evidence_schema_version = _evidence_schema_version(session_dir)
    atom_coverage = v2_atom_coverage(entries, part1, evidence_schema_version) if evidence_schema_version == 2 or any(entry.assurance_class is not None or entry.behavior_atoms for entry in entries) else None
    considered = [e for e in entries if material_settled(e, min_weight)]
    covered = [e for e in considered if id_is_cited(e.id, part1)]
    uncovered = [e for e in considered if not id_is_cited(e.id, part1)]

    if fmt == "json":
        payload = {
            "min_weight": min_weight,
            "considered": len(considered),
            "covered": [e.id for e in covered],
            "uncovered": [
                {"id": e.id, "impact_weight": e.impact_weight, "ambiguity_score": e.ambiguity_score, "requirement": e.requirement}
                for e in uncovered
            ],
            "coverage_ok": not uncovered,
        }
        if atom_coverage is not None:
            payload["atom_coverage_ok"] = not atom_coverage.mismatches
            payload["atom_mismatches"] = [item.describe() for item in atom_coverage.mismatches]
        typer.echo(json.dumps(payload, indent=2))
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
        if atom_coverage is not None:
            typer.echo(f"- Atom catalog entries: {atom_coverage.catalog_count}")
            typer.echo(f"- atom_coverage_ok: {'yes' if not atom_coverage.mismatches else 'no'}")
            if atom_coverage.mismatches:
                typer.echo("\n### Atom mismatches — structured synthesis-loss risk\n")
                for mismatch in atom_coverage.mismatches:
                    typer.echo(f"- {mismatch.describe()}")

    if (uncovered or (atom_coverage is not None and atom_coverage.mismatches)) and not advisory:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
