#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verification_execution_lint as lint
from postmortem_bundle import JsonValue
from verification_contract import canonical_command_digest, effective_heads

runner = CliRunner()
COLUMNS = (
    "Spec row",
    "Check",
    "Kind",
    "Execution",
    "Result",
    "Captured artifact",
    "Observed effect",
)


def report_row(
    spec_row: int,
    check: str,
    kind: str = "test",
    execution: str = "exact",
    result: str = "pass",
    artifact_id: str = "capture-1",
    observed_effect: str = "command completed",
) -> tuple[str, ...]:
    return (
        str(spec_row),
        check,
        kind,
        execution,
        result,
        artifact_id,
        observed_effect,
    )


def capture(
    *,
    artifact_id: str = "capture-1",
    spec_row: int = 1,
    check: str = "Unit suite",
    command: str = "python -m pytest",
    heads: tuple[str, ...] | None = None,
) -> dict[str, JsonValue]:
    return {
        "artifact_id": artifact_id,
        "file_sha256": "f" * 64,
        "marker": "CAPTURED-OUTPUT",
        "spec_row_number": spec_row,
        "check": check,
        "kind": "test",
        "exact_command": command,
        "command_digest": canonical_command_digest(command),
        "effective_heads": list(heads if heads is not None else effective_heads(command)),
        "cwd": "/repo",
        "started_at": "2026-07-10T00:00:00Z",
        "ended_at": "2026-07-10T00:00:01Z",
        "spawned": True,
        "timed_out": False,
        "timeout_seconds": 60,
        "exit_code": 0,
        "stdout": "ok\n",
        "stderr": "",
        "stdout_full_bytes": 3,
        "stderr_full_bytes": 0,
        "stdout_sha256": "0" * 64,
        "stderr_sha256": "0" * 64,
    }


def write_session(
    tmp_path: Path,
    *,
    specs: tuple[tuple[str, str, str], ...] = (("Unit suite", "test", "python -m pytest"),),
    report_rows: tuple[tuple[str, ...], ...] = (report_row(1, "Unit suite"),),
    bundle: dict[str, JsonValue] | None = None,
) -> Path:
    session = tmp_path / "session"
    session.mkdir()
    handoff_rows = "\n".join(
        f"| {check} | {kind} | {command} |" for check, kind, command in specs
    )
    (session / "handoff.md").write_text(
        "# Part 1 - Build Contract\n\n"
        "## Verification Commands\n\n"
        "| Check | Kind | Command / action |\n"
        "| --- | --- | --- |\n"
        f"{handoff_rows}\n",
        encoding="utf-8",
    )
    report_lines = "\n".join("| " + " | ".join(row) + " |" for row in report_rows)
    (session / "postmortem.md").write_text(
        "# Postmortem\n\n"
        "## Verification Execution\n\n"
        "| " + " | ".join(COLUMNS) + " |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        f"{report_lines}\n",
        encoding="utf-8",
    )
    if bundle is not None:
        (session / "evidence_bundle.json").write_text(
            json.dumps(bundle), encoding="utf-8"
        )
    return session


def bundle(*captures: dict[str, JsonValue], version: int = 4) -> dict[str, JsonValue]:
    return {
        "schema_version": version,
        "artifacts": {"captured_outputs": list(captures)},
    }


def test_exact_pass_with_matching_capture_is_clean_and_cli_exits_zero(tmp_path: Path) -> None:
    session = write_session(tmp_path, bundle=bundle(capture()))

    assert lint.evaluate(session) == []
    result = runner.invoke(lint.app, [str(session)])
    assert result.exit_code == 0, result.output


def test_missing_capture_behind_pass_is_violation_and_cli_exits_one(tmp_path: Path) -> None:
    session = write_session(tmp_path, bundle=bundle())

    violations = lint.evaluate(session)
    assert any("captured-output" in violation for violation in violations)
    result = runner.invoke(lint.app, [str(session)])
    assert result.exit_code == 1, result.output


@pytest.mark.parametrize(
    ("capture_record", "reported_artifact"),
    (
        (capture(spec_row=2), "capture-1"),
        (capture(command="python -m unittest"), "capture-1"),
        (capture(heads=("unrelated",)), "capture-1"),
        (capture(), "wrong-artifact"),
    ),
    ids=("wrong-row-number", "wrong-command-digest", "wrong-head", "wrong-artifact-id"),
)
def test_exact_pass_rejects_mismatched_capture(
    tmp_path: Path, capture_record: dict[str, JsonValue], reported_artifact: str
) -> None:
    session = write_session(
        tmp_path,
        report_rows=(report_row(1, "Unit suite", artifact_id=reported_artifact),),
        bundle=bundle(capture_record),
    )

    assert any("captured-output" in violation for violation in lint.evaluate(session))


def test_adapted_pass_cannot_use_an_exact_capture(tmp_path: Path) -> None:
    session = write_session(
        tmp_path,
        report_rows=(
            report_row(
                1,
                "Unit suite",
                execution="adapted",
                result="adapted-pass",
            ),
        ),
        bundle=bundle(capture()),
    )

    assert any("adapted command" in violation for violation in lint.evaluate(session))


def test_skipped_execution_cannot_claim_pass(tmp_path: Path) -> None:
    session = write_session(
        tmp_path,
        report_rows=(
            report_row(1, "Unit suite", execution="skipped", artifact_id="", observed_effect=""),
        ),
        bundle=bundle(),
    )

    assert any("Execution 'skipped'" in violation for violation in lint.evaluate(session))


def test_skipped_result_needs_no_capture(tmp_path: Path) -> None:
    session = write_session(
        tmp_path,
        report_rows=(
            report_row(
                1,
                "Unit suite",
                execution="skipped",
                result="skipped",
                artifact_id="",
                observed_effect="",
            ),
        ),
    )

    assert lint.evaluate(session) == []


def test_chained_heads_with_fully_matching_capture_are_clean(tmp_path: Path) -> None:
    command = "alpha --check && beta --check"
    session = write_session(
        tmp_path,
        specs=(("Chained", "test", command),),
        report_rows=(report_row(1, "Chained"),),
        bundle=bundle(capture(check="Chained", command=command)),
    )

    assert lint.evaluate(session) == []


def test_action_only_row_is_excluded_from_capture_requirement(tmp_path: Path) -> None:
    session = write_session(
        tmp_path,
        specs=(("Manual walkthrough", "prose", "Run the app and inspect it."),),
        report_rows=(
            report_row(
                1,
                "Manual walkthrough",
                kind="prose",
                artifact_id="",
            ),
        ),
    )

    assert lint.evaluate(session) == []


def test_schema_version_three_is_readable_but_cannot_prove_a_pass(tmp_path: Path) -> None:
    session = write_session(tmp_path, bundle=bundle(version=3))

    result = runner.invoke(lint.app, [str(session)])
    assert result.exit_code == 1
    assert "CAPTURED-OUTPUT" in result.output


def test_unparseable_bundle_exits_two(tmp_path: Path) -> None:
    session = write_session(tmp_path)
    (session / "evidence_bundle.json").write_text("{not json", encoding="utf-8")

    result = runner.invoke(lint.app, [str(session)])
    assert result.exit_code == 2
    assert "did not parse" in result.output


def test_absent_bundle_with_pass_is_normal_violation_not_exit_two(tmp_path: Path) -> None:
    session = write_session(tmp_path)

    result = runner.invoke(lint.app, [str(session)])
    assert result.exit_code == 1
    assert "is absent" in result.output


def test_advisory_downgrades_violations_to_zero(tmp_path: Path) -> None:
    session = write_session(tmp_path, bundle=bundle())

    result = runner.invoke(lint.app, [str(session), "--advisory"])
    assert result.exit_code == 0
    assert "violation" in result.output
