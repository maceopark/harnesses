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
# Provenance gate for the Verification Execution postmortem table.

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)

from handoff_coverage import extract_part1  # noqa: E402
from legacy_v3_report import is_legacy_v3_report, verification_violations  # noqa: E402
from verification_legacy_lint import (  # noqa: E402
    BUNDLE_FILENAME,
    EvaluationInputError,
    ReportRow,
    load_captured_outputs,
    parse_report_rows,
    read_required,
    report_violation,
    require_adapted_capture,
    require_exact_capture,
)
from verification_contract import (  # noqa: E402
    parse_verification_rows,
    row_identity,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def evaluate(session_dir: Path) -> list[str]:
    """Return deterministic Verification Execution contract violations.

    Raises EvaluationInputError only for missing or unparseable required inputs,
    or for a present but invalid evidence bundle. An absent bundle is represented
    as None and becomes a normal violation only when a capture is required.
    """
    session_dir = Path(session_dir)
    handoff = read_required(session_dir / "handoff.md", "handoff.md")
    report = read_required(session_dir / "postmortem.md", "postmortem.md")
    if is_legacy_v3_report(session_dir / BUNDLE_FILENAME, report):
        return list(verification_violations(report))
    from verification_return_lint import StableInputError, bundle_mode, evaluate_stable

    try:
        mode = bundle_mode(session_dir / BUNDLE_FILENAME)
        if mode == "stable-v5":
            return evaluate_stable(session_dir, report)
    except StableInputError as error:
        raise EvaluationInputError(str(error)) from error
    try:
        verification_rows = parse_verification_rows(extract_part1(handoff))
    except ValueError as error:
        raise EvaluationInputError(f"handoff.md did not parse: {error}") from error

    captures = load_captured_outputs(session_dir / BUNDLE_FILENAME)
    violations: list[str] = []
    report_rows = parse_report_rows(report, violations)

    expected = {row_identity(row): row for row in verification_rows}
    reports_by_identity: dict[tuple[int, str], list[ReportRow]] = {}
    for report_row in report_rows:
        if report_row.spec_row is not None:
            reports_by_identity.setdefault((report_row.spec_row, report_row.check), []).append(report_row)

    for identity, row in expected.items():
        matching = reports_by_identity.get(identity, [])
        if not matching:
            violations.append(
                report_violation(
                    f"missing report row for Spec row {row.row_number} ({row.check!r})"
                )
            )
        elif len(matching) > 1:
            violations.append(
                report_violation(
                    f"duplicate report rows for Spec row {row.row_number} ({row.check!r})"
                )
            )
    for report_row in report_rows:
        identity = (
            (report_row.spec_row, report_row.check)
            if report_row.spec_row is not None
            else None
        )
        if identity not in expected:
            violations.append(
                report_violation(f"row {report_row.number} does not match a Part-1 verification row")
            )

    for report_row in report_rows:
        if report_row.execution in {"skipped", "not-run"} and report_row.result == "pass":
            violations.append(
                report_violation(
                    f"row {report_row.number} has Execution {report_row.execution!r} but Result 'pass'"
                )
            )
        if report_row.execution == "adapted" and report_row.result == "pass":
            violations.append(
                report_violation(
                    f"row {report_row.number} has adapted execution but claims exact Result 'pass'"
                )
            )
        if report_row.result == "adapted-pass" and report_row.execution != "adapted":
            violations.append(
                report_violation(
                    f"row {report_row.number} has Result 'adapted-pass' without adapted execution"
                )
            )

        if report_row.spec_row is None:
            continue
        row = expected.get((report_row.spec_row, report_row.check))
        if row is None or not row.is_command_row:
            continue
        if report_row.result == "pass" and row.kind in {"test", "real-surface"}:
            require_exact_capture(row, report_row, captures, violations)
        if report_row.result == "adapted-pass":
            require_adapted_capture(row, report_row, captures, violations)

    return violations


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Session dir with handoff.md and postmortem.md")
    ],
    advisory: Annotated[
        bool, typer.Option(help="Report violations but never exit non-zero.")
    ] = False,
) -> None:
    try:
        violations = evaluate(session_dir)
    except EvaluationInputError as error:
        typer.echo(f"verification_execution_lint: error: {error}", err=True)
        raise typer.Exit(2) from error

    if violations:
        typer.echo(f"verification_execution_lint: {len(violations)} violation(s)")
        for violation in violations:
            typer.echo(f"- {violation}")
        if not advisory:
            raise typer.Exit(1)
    else:
        typer.echo("verification_execution_lint: ok - pass claims cite matching captures")


if __name__ == "__main__":
    app()
