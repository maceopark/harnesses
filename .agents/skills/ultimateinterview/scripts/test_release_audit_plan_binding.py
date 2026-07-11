#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest>=8.0", "pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_audit

RUNNER = CliRunner()
EVIDENCE_STAGES = ("red", "green", "surface")
CLEANUP_TASKS = (1, 3, 4, 5, 6, 7, 8, 10, 11, 13)
EXPECTED_PLAN_RELATIVE = ".omo/plans/ultimateinterview-v2-assurance-plane.md"


def _evidence_dir(tmp_path: Path) -> Path:
    evidence = tmp_path / ".omo" / "evidence"
    evidence.mkdir(parents=True)
    for task in range(1, 14):
        for stage in EVIDENCE_STAGES:
            _ = (evidence / f"task-{task}-ultimateinterview-v2-assurance-plane.{stage}.txt").write_text("ok\n")
    for task in CLEANUP_TASKS:
        _ = (evidence / f"task-{task}-ultimateinterview-v2-assurance-plane.cleanup.txt").write_text("ok\n")
    return evidence


def _changed_paths(tmp_path: Path) -> Path:
    relative = ".agents/skills/ultimateinterview/scripts/assurance_schema.py"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text("VALUE = 1\n", encoding="utf-8")
    changed_paths = tmp_path / "changed-paths.txt"
    _ = changed_paths.write_text(f"{relative}\n", encoding="utf-8")
    return changed_paths


def _run(tmp_path: Path, changed_paths: Path):
    return RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(changed_paths),
        ],
    )


def test_release_audit_rejects_a_missing_default_assurance_plan(tmp_path: Path) -> None:
    # Given
    _ = _evidence_dir(tmp_path)
    changed_paths = _changed_paths(tmp_path)

    # When
    result = _run(tmp_path, changed_paths)

    # Then
    assert result.exit_code != 0
    assert "plan must be a file" in result.output


def test_release_audit_rejects_default_plan_missing_assurance_contract_markers(tmp_path: Path) -> None:
    # Given
    _ = _evidence_dir(tmp_path)
    changed_paths = _changed_paths(tmp_path)
    plan = tmp_path / EXPECTED_PLAN_RELATIVE
    plan.parent.mkdir(parents=True, exist_ok=True)
    _ = plan.write_text("# unrelated plan\n", encoding="utf-8")

    # When
    result = _run(tmp_path, changed_paths)

    # Then
    assert result.exit_code != 0
    assert "plan is missing assurance-plane contract markers" in result.output
