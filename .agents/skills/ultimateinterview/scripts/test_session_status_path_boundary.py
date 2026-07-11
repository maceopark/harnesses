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

import shutil
import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import session_status

FIXTURE = Path(__file__).parent / "regression_fixtures" / "ready-minimal"
RUNNER = CliRunner()


def status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def copy_ready_session(parent: Path, name: str) -> Path:
    session = parent / name
    shutil.copytree(FIXTURE, session)
    return session


def session_tree(session: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(session): path.read_bytes()
        for path in sorted(session.rglob("*"))
        if path.is_file()
    }


def test_session_status_explicit_legacy_paths_do_not_mutate_the_session(
    tmp_path: Path,
) -> None:
    # Given
    session = copy_ready_session(tmp_path, "session")
    (session / ".session-update.lock").unlink(missing_ok=True)
    before = session_tree(session)

    # When
    result = RUNNER.invoke(
        status_app(),
        [
            "--ledger",
            str(session / "ledger.json"),
            "--protocol",
            str(session / "protocol.json"),
        ],
    )

    # Then
    assert result.exit_code == 0, result.output
    assert session_tree(session) == before
    assert not (session / ".session-update.lock").exists()


def test_session_status_rejects_foreign_override_paths(tmp_path: Path) -> None:
    # Given
    session = copy_ready_session(tmp_path, "session")
    foreign = copy_ready_session(tmp_path, "foreign")

    # When
    result = RUNNER.invoke(
        status_app(),
        [
            str(session),
            "--ledger",
            str(foreign / "ledger.json"),
            "--protocol",
            str(foreign / "protocol.json"),
        ],
    )

    # Then
    assert result.exit_code != 0
    assert "must resolve within the session directory" in result.output


def test_session_status_rejects_relative_override_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    session = copy_ready_session(tmp_path, "session")
    copy_ready_session(tmp_path, "foreign")
    monkeypatch.chdir(session)

    # When
    result = RUNNER.invoke(
        status_app(),
        [str(session), "--ledger", "../foreign/ledger.json"],
    )

    # Then
    assert result.exit_code != 0
    assert "must resolve within the session directory" in result.output


@pytest.mark.parametrize("member", ("ledger", "protocol"))
def test_session_status_rejects_symlinked_override_escape(
    tmp_path: Path,
    member: str,
) -> None:
    # Given
    session = copy_ready_session(tmp_path, "session")
    foreign = copy_ready_session(tmp_path, "foreign")
    link = session / f"{member}-link.json"
    link.symlink_to(foreign / f"{member}.json")

    # When
    result = RUNNER.invoke(
        status_app(),
        [str(session), f"--{member}", str(link)],
    )

    # Then
    assert result.exit_code != 0
    assert "must resolve within the session directory" in result.output


def test_session_status_accepts_safe_local_override_paths(tmp_path: Path) -> None:
    # Given
    session = copy_ready_session(tmp_path, "session")
    overrides = session / "overrides"
    overrides.mkdir()
    ledger = overrides / "ledger.json"
    protocol = overrides / "protocol.json"
    shutil.copy2(session / "ledger.json", ledger)
    shutil.copy2(session / "protocol.json", protocol)
    (session / ".session-update.lock").unlink(missing_ok=True)
    before = session_tree(session)

    # When
    result = RUNNER.invoke(
        status_app(),
        [str(session), "--ledger", str(ledger), "--protocol", str(protocol)],
    )

    # Then
    assert result.exit_code == 0, result.output
    assert "- interview_converged: yes" in result.output
    assert session_tree(session) == before
    assert not (session / ".session-update.lock").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
