#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
# (pydantic/rich are pulled in by the shared handoff_coverage import.)

# ─── How to run ───
#      uv run scripts/predicate_lint.py <session-dir> [--strict]
# ──────────────────
#
# Decidable-predicate gate for the Build Contract (controlled-language lens,
# type/coercion extension).
#
# The controlled-language gate already forbids a bare reject category ("invalid
# X" with no rule deciding membership). The three-arm benchmark (claudeplan vs
# codexplan vs app-5) showed the same class escaping through TYPE predicates the
# word-level gate never looked at:
#
#   - claudeplan typed the store's `next_id` as an integer and validated it with
#     `isinstance(x, int)`; a JSON `true` satisfies that (bool subclasses int in
#     Python) and was written straight into the store. The spec named the type
#     but never pinned the coercion boundary (is a JSON boolean an integer? a
#     numeric string? a float?).
#   - claudeplan pinned `version > 1 -> error` but left `version < 1` / `== 0`
#     undefined - a one-sided threshold with no floor.
#   - codexplan's "invalid id value" and app-5's "invalid next_id" named reject
#     categories with no deciding predicate (the app-5 implementer invented
#     `next_id > max(existing id)` on its own; decision-log escape E1).
#
# This lint scans Part 1 and reports, as a checklist:
#   reject-category  - a reject word in a row with no co-located decidability marker
#   numeric-coercion - an int/number-typed persisted field with the type/bool
#                      coercion boundary never pinned anywhere in Part 1
#   version-floor    - a store/schema `version` upper rule with no lower/floor rule
#
# It cannot prove a predicate is CORRECT, only surface where one is missing - so
# it is advisory by default (like verification_lint, whose head heuristic has
# false positives on prose). `--strict` blocks. The interview-rule side of this
# (orientation trigger + audit-checklist gate) is experimental: an interview
# rule cannot be re-measured without a fresh human-in-the-loop cycle.

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_coverage import extract_part1  # noqa: E402
from verification_lint import tables  # noqa: E402

# Reject-category words: a criterion that names one of these describes a set it
# must not accept, so the predicate deciding membership has to be stated.
REJECT_WORDS: Final[frozenset[str]] = frozenset(
    {
        "invalid", "malformed", "corrupt", "corrupted", "unreadable",
        "unsafe", "mistyped", "ill-formed", "illformed", "improper",
    }
)
# Decidability markers: their presence in the same row means the row carries an
# actual rule (a comparison, an enumeration, a membership test), not just the
# bare category word. Deliberately excludes more category nouns (schema, shape,
# root) - those restate the category, they do not decide it.
PREDICATE_SIGNALS: Final[tuple[str, ...]] = (
    "exactly", "one of", "must be", "must not", "matches", "equals",
    "regex", "iff", "if and only if", "non-empty", "nonempty", "positive",
    "negative", "greater", "less than", "at most", "at least", "duplicate",
    "not a", "predicate", "unless", "any of", "none of",
    "boolean", "integer", "digit", "utf-8", "utf8", "non-utf8", "empty",
    "oversized", "control", "newline", ">", "<", ">=", "<=", "==", "!=",
)
# A persisted/loaded field typed as an integer. Two shapes: schema-style
# `next_id: int` / `"id": int`, and prose "next_id ... positive integer".
SCHEMA_INT_FIELD: Final[re.Pattern[str]] = re.compile(
    r"""["'`]?\b\w+\b["'`]?\s*[:=]\s*(?:positive\s+|non-negative\s+)?(?:int|integer|number)\b""",
    re.IGNORECASE,
)
PROSE_INT_FIELD: Final[re.Pattern[str]] = re.compile(
    r"\b\w*(?:id|count|version|next_id|index|size)\b[^\n.]{0,40}?"
    r"\b(?:positive\s+|non-negative\s+)?(?:int|integer|number)\b",
    re.IGNORECASE,
)
# Discussion OF the coercion boundary (not a mere type name): a spec that says
# any of these has looked at the bool/string/float edge, so numeric-coercion
# does not fire. `done: bool` is a type name, not a coercion rule, so plain
# "bool" is intentionally NOT a signal here.
COERCION_DISCUSSED: Final[re.Pattern[str]] = re.compile(
    r"\b(?:true/false|coerc\w+|isinstance|numeric\s+string|stringifi\w+|"
    r"non-integer|float-for-int|type[- ]?check\w*|json\s+bool\w*|"
    r"bool\w*\s+(?:is\s+not|are\s+not|counts?|rejected)|"
    r"(?:reject|accept)s?\s+bool\w*)\b",
    re.IGNORECASE,
)
VERSION_UPPER: Final[re.Pattern[str]] = re.compile(
    r"\bversion\b[^\n.]{0,50}?(?:>\s*\d|greater|newer|above|exceeds?|higher|too new)",
    re.IGNORECASE,
)
VERSION_LOWER: Final[re.Pattern[str]] = re.compile(
    r"\bversion\b[^\n.]{0,50}?(?:<\s*\d|older|below|minimum|floor|earlier|lower|too old|==\s*\d|equal)",
    re.IGNORECASE,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def has_predicate_signal(row_text: str) -> bool:
    lowered = row_text.lower()
    return any(signal in lowered for signal in PREDICATE_SIGNALS)


def reject_findings(part1: str) -> list[str]:
    """Rows that name a reject category with no co-located decidability marker."""
    findings: list[str] = []
    for _headers, rows in tables(part1):
        for row in rows:
            row_text = " ".join(row)
            lowered = row_text.lower()
            hits = sorted({word for word in REJECT_WORDS if re.search(rf"\b{re.escape(word)}\b", lowered)})
            if hits and not has_predicate_signal(row_text):
                locator = row[0] if row and row[0] else row_text[:40]
                findings.append(
                    f"reject-category: row {locator!r} names {', '.join(hits)} "
                    "with no co-located predicate (comparison, enumeration, or membership test)"
                )
    return findings


def coercion_finding(part1: str) -> str | None:
    """One finding when an int-typed persisted field exists but the type/bool
    coercion boundary is never pinned in Part 1."""
    has_int_field = bool(SCHEMA_INT_FIELD.search(part1) or PROSE_INT_FIELD.search(part1))
    if has_int_field and not COERCION_DISCUSSED.search(part1):
        return (
            "numeric-coercion: an integer-typed persisted field is declared but "
            "Part 1 never pins the type-coercion boundary - state whether a JSON "
            "boolean (satisfies a naive isinstance(int) check), a numeric string, "
            "a float, or null/missing is accepted or rejected for it"
        )
    return None


def version_floor_finding(part1: str) -> str | None:
    if VERSION_UPPER.search(part1) and not VERSION_LOWER.search(part1):
        return (
            "version-floor: a store/schema version has an upper/newer rule but no "
            "lower/older/floor rule - pin what happens for a version below the "
            "current one (or == 0), not only above it"
        )
    return None


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Session dir containing handoff.md")
    ],
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit non-zero on any finding. Default is advisory (report only) - "
            "the detectors are heuristic (they surface a missing predicate, they cannot "
            "prove one is correct), so blocking is opt-in.",
        ),
    ] = False,
) -> None:
    handoff_path = session_dir / "handoff.md"
    if not handoff_path.is_file():
        typer.echo(f"error: missing handoff.md at {handoff_path}", err=True)
        raise typer.Exit(2)

    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    findings = reject_findings(part1)
    for maybe in (coercion_finding(part1), version_floor_finding(part1)):
        if maybe is not None:
            findings.append(maybe)

    typer.echo("## Decidable-Predicate Lint\n")
    if findings:
        typer.echo(f"- predicate_ok: no - {len(findings)} row(s)/field(s) need a deciding predicate:")
        for note in findings:
            typer.echo(f"  - {note}")
        typer.echo(
            "\n  Add the predicate to the acceptance criterion, or delegate it as an explicit "
            "decision-boundary row. A bare category or unpinned type forces the implementer to "
            "invent the data rule (claudeplan bool-as-int; app-5 invalid next_id)."
        )
        if strict:
            raise typer.Exit(1)
    else:
        typer.echo("- predicate_ok: yes")


if __name__ == "__main__":
    app()
