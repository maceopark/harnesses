#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest>=8.0", "pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
from typer import BadParameter
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_audit

RUNNER = CliRunner()
EVIDENCE_STAGES = ("red", "green", "surface")
CLEANUP_TASKS = (1, 3, 4, 5, 6, 7, 8, 10, 11, 13)
EXPECTED_PLAN_RELATIVE = ".omo/plans/ultimateinterview-v2-assurance-plane.md"
VALID_PLAN = """# ultimateinterview-v2-assurance-plane - Work Plan

Create `scripts/assurance_schema.py` with immutable strict models and this exact state matrix: `abi={pass,fail}`, `trace={pass,fail}`, `property={not-run,receipt-invalid,observed-pass,observed-fail}`, `adequacy={not-assessed,challenge-passed,challenge-found-gap}`, `stakeholder={not-sought,attestation-invalid,accepted,rejected}`.

F1. Plan compliance audit

PASS only if no historical research bundle path changed.
"""


class InvalidSuppliedPath(NamedTuple):
    option: str
    name: str
    expected: str
    is_directory: bool


def _paths_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "changed-paths.txt"
    _ = path.write_text(content, encoding="utf-8")
    return path


def _evidence_dir(tmp_path: Path) -> Path:
    evidence = tmp_path / ".omo" / "evidence"
    evidence.mkdir(parents=True)
    for task in range(1, 14):
        for stage in EVIDENCE_STAGES:
            _ = (evidence / f"task-{task}-ultimateinterview-v2-assurance-plane.{stage}.txt").write_text("ok\n")
    for task in CLEANUP_TASKS:
        _ = (evidence / f"task-{task}-ultimateinterview-v2-assurance-plane.cleanup.txt").write_text("ok\n")
    _ = _plan(tmp_path)
    return evidence


def _mapped_path(tmp_path: Path, source: str = "VALUE = 1\n") -> str:
    relative = ".agents/skills/ultimateinterview/scripts/assurance_schema.py"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text(source, encoding="utf-8")
    return relative


def _plan(tmp_path: Path, content: str = VALID_PLAN, relative: str = EXPECTED_PLAN_RELATIVE) -> Path:
    plan = tmp_path / relative
    plan.parent.mkdir(parents=True, exist_ok=True)
    _ = plan.write_text(content, encoding="utf-8")
    return plan


def _run(tmp_path: Path, paths: str):
    return RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(_paths_file(tmp_path, paths)),
        ],
    )


def test_release_map_materializes_exact_c1_through_c6_components() -> None:
    # Given, When
    component_ids = tuple(component.id for component in release_audit.load_map())

    # Then
    assert component_ids == ("C1", "C2", "C3", "C4", "C5", "C6")


def test_release_audit_accepts_mapped_paths_with_complete_evidence(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 0, result.output


def test_release_audit_accepts_documented_evidence_and_plan_options(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    evidence = _evidence_dir(tmp_path)
    plan = _plan(tmp_path)

    # When
    result = RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(_paths_file(tmp_path, f"{relative}\n")),
            "--evidence-dir",
            str(evidence),
            "--plan",
            str(plan),
        ],
    )

    # Then
    assert result.exit_code == 0, result.output


def test_release_audit_rejects_a_plan_other_than_the_assurance_plane(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    _ = _evidence_dir(tmp_path)
    plan = _plan(tmp_path, relative=".omo/plans/other-plan.md")

    # When
    result = RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(_paths_file(tmp_path, f"{relative}\n")),
            "--plan",
            str(plan),
        ],
    )

    # Then
    assert result.exit_code != 0
    assert "plan must be" in result.output


def test_release_audit_rejects_a_plan_missing_assurance_contract_markers(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    _ = _evidence_dir(tmp_path)
    plan = _plan(tmp_path, content="# unrelated plan\n")

    # When
    result = RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(_paths_file(tmp_path, f"{relative}\n")),
            "--plan",
            str(plan),
        ],
    )

    # Then
    assert result.exit_code != 0
    assert "plan is missing assurance-plane contract markers" in result.output


@pytest.mark.parametrize(
    "supplied",
    (
        InvalidSuppliedPath("--evidence-dir", "outside-evidence", "evidence-dir must be inside --workspace-root", True),
        InvalidSuppliedPath("--plan", "outside-plan.md", "plan must be inside --workspace-root", False),
    ),
)
def test_release_audit_rejects_supplied_paths_outside_workspace(tmp_path: Path, supplied: InvalidSuppliedPath) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    _ = _evidence_dir(tmp_path)
    outside = tmp_path.parent / supplied.name
    if supplied.is_directory:
        outside.mkdir()
    else:
        _ = outside.write_text("# unrelated plan\n", encoding="utf-8")

    # When
    result = RUNNER.invoke(
        release_audit.app,
        [
            "--workspace-root",
            str(tmp_path),
            "--changed-paths",
            str(_paths_file(tmp_path, f"{relative}\n")),
            supplied.option,
            str(outside),
        ],
    )

    # Then
    assert result.exit_code != 0
    assert supplied.expected in result.output


def test_release_audit_rejects_an_unmapped_changed_path(tmp_path: Path) -> None:
    # Given
    relative = ".agents/skills/ultimateinterview/scripts/unmapped.py"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text("VALUE = 1\n")

    # When
    _ = _evidence_dir(tmp_path)
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert "unmapped-path" in result.output


def test_release_audit_rejects_an_unrelated_postmortem_path(tmp_path: Path) -> None:
    # Given
    relative = ".agents/skills/ultimateinterview-postmortem/scripts/process_cleanup.py"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text("VALUE = 1\n", encoding="utf-8")
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert f"unmapped-path: {relative}" in result.output


@pytest.mark.parametrize(
    "relative",
    (
        "docs/unrelated.md",
        ".omo/ulw-research/20260710-214016/SYNTHESIS.md",
    ),
)
def test_release_audit_rejects_changed_paths_outside_the_assurance_plane(tmp_path: Path, relative: str) -> None:
    # Given
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text("unrelated\n", encoding="utf-8")
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert f"outside-release-scope: {relative}" in result.output


def test_release_audit_rejects_documented_verdict_outside_task1_matrix(tmp_path: Path) -> None:
    # Given
    relative = ".agents/skills/ultimateinterview/references/assurance-invalid.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text("property=authenticated\n", encoding="utf-8")
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert "invalid-verdict-value: property=authenticated" in result.output


def test_release_audit_accepts_documented_task1_verdict_matrix(tmp_path: Path) -> None:
    # Given
    relative = ".agents/skills/ultimateinterview/references/assurance-states.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    _ = target.write_text(
        "abi=pass\ntrace: fail\nproperty=`observed-pass`\nadequacy=challenge-found-gap\nstakeholder: accepted\n",
        encoding="utf-8",
    )
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 0, result.output


def test_release_audit_defers_process_api_inspection_to_f4(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path, "import subprocess\n")
    _ = _evidence_dir(tmp_path)

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 0, result.output


def test_release_audit_rejects_missing_required_evidence(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    evidence = _evidence_dir(tmp_path)
    (evidence / "task-8-ultimateinterview-v2-assurance-plane.green.txt").unlink()

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert "missing-evidence: task-8: green" in result.output


def test_release_audit_rejects_missing_declared_cleanup_evidence(tmp_path: Path) -> None:
    # Given
    relative = _mapped_path(tmp_path)
    evidence = _evidence_dir(tmp_path)
    (evidence / "task-11-ultimateinterview-v2-assurance-plane.cleanup.txt").unlink()

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert "missing-evidence: task-11: cleanup" in result.output


def test_release_map_rejects_any_component_set_other_than_c1_through_c6(tmp_path: Path) -> None:
    # Given
    malformed = tmp_path / "release-audit-map.json"
    _ = malformed.write_text('{"components": []}', encoding="utf-8")

    # When, Then
    with pytest.raises(BadParameter, match="exactly C1 through C6"):
        release_audit.load_map(malformed)


def test_release_map_rejects_weakened_path_families(tmp_path: Path) -> None:
    # Given
    weakened = tmp_path / "release-audit-map.json"
    payload = {"components": [{"id": component_id, "paths": ["*"]} for component_id in ("C1", "C2", "C3", "C4", "C5", "C6")]}
    _ = weakened.write_text(json.dumps(payload), encoding="utf-8")

    # When, Then
    with pytest.raises(BadParameter, match="path families must match"):
        release_audit.load_map(weakened)


def test_release_audit_rejects_task14_evidence_path(tmp_path: Path) -> None:
    # Given
    _ = _evidence_dir(tmp_path)
    relative = ".omo/evidence/task-14-ultimateinterview-v2-assurance-plane.green.txt"
    target = tmp_path / relative
    _ = target.write_text("unexpected\n", encoding="utf-8")

    # When
    result = _run(tmp_path, f"{relative}\n")

    # Then
    assert result.exit_code == 1
    assert f"unmapped-path: {relative}" in result.output
