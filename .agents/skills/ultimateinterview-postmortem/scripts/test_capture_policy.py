from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_verification

runner = CliRunner()


def policy_session(tmp_path: Path, command: str, run_policy: str) -> Path:
    session = tmp_path / ".ultimateinterview" / "policy"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(
        "# Part 1 - Build Contract\n\n## Verification Commands\n\n"
        "| ID | Covers | Check | Kind | Command / action | Pass condition | Run policy |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        f"| VER-001 | REQ-001 | policy | test | {command} | exit code = 0 | {run_policy} |\n",
        encoding="utf-8",
    )
    return session


def artifact_path(tmp_path: Path) -> Path:
    return tmp_path / ".omo" / "evidence" / "demo" / "captured-output-row-0001.json"


@pytest.mark.parametrize("run_policy", ("manual", "expensive", "destructive", "credentialed"))
def test_non_safe_auto_policy_refuses_without_spawning(
    tmp_path: Path, run_policy: str
) -> None:
    sentinel = tmp_path / f"{run_policy}-ran"
    session = policy_session(tmp_path, f"touch {sentinel}", run_policy)

    result = runner.invoke(capture_verification.app, [str(session), "--row", "1"])

    assert result.exit_code == 2
    assert run_policy in result.output
    assert "safe-auto" in result.output
    assert not sentinel.exists()
    assert not artifact_path(tmp_path).exists()


def test_safe_auto_executes_validated_argv_without_shell(tmp_path: Path) -> None:
    session = policy_session(
        tmp_path, "python3 -m compileall -q .ultimateinterview", "safe-auto"
    )

    result = runner.invoke(
        capture_verification.app, [str(session), "--row", "1", "--slug", "demo"]
    )

    assert result.exit_code == 0, result.output
    capture = json.loads(artifact_path(tmp_path).read_text(encoding="utf-8"))
    assert capture["spawned"] is True
    assert capture["exit_code"] == 0


def test_safe_auto_shell_controls_are_refused_without_side_effect(tmp_path: Path) -> None:
    sentinel = tmp_path / "shell-control-ran"
    session = policy_session(
        tmp_path,
        f"python3 -m compileall -q .ultimateinterview && touch {sentinel}",
        "safe-auto",
    )

    result = runner.invoke(capture_verification.app, [str(session), "--row", "1"])

    assert result.exit_code == 2
    assert "safe-auto" in result.output.lower()
    assert not sentinel.exists()


def test_cleanup_proof_failure_is_typed_cli_error_without_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = policy_session(
        tmp_path, "python3 -m compileall -q .ultimateinterview", "safe-auto"
    )

    def fail_cleanup(*_args: str | int | Path | None) -> None:
        raise capture_verification.ProcessCleanupError(1234, 2.0)

    monkeypatch.setattr(capture_verification, "capture", fail_cleanup)
    result = runner.invoke(capture_verification.app, [str(session), "--row", "1"])

    assert result.exit_code == 1
    assert "could not prove process-group exit" in result.output
    assert not artifact_path(tmp_path).exists()
