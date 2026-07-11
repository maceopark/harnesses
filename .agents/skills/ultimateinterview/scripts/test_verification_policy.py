#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pytest>=8.0"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import verification_policy


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest tests/test_app.py -q",
        "pytest tests -q",
        "uv run pytest tests -q",
        "uv run python3 -m pytest tests -q",
        "ruff check .",
        "ruff format --check .",
        "basedpyright src",
        "npm test",
        "npm run build",
        "bun test",
        "cargo test --workspace",
        "go test ./...",
        "go test ./... -count=1",
        "git diff --check",
        "pytest tests/test_app.py::test_save[param] -q",
        "pytest --junitxml artifacts/report.xml tests",
        "pytest --junitxml=artifacts/report.xml tests",
    ],
)
def test_safe_auto_allows_recognized_bounded_local_verification(command: str) -> None:
    # Given a recognized bounded local verification command
    # When policy validation runs, Then it accepts the command
    verification_policy.validate_safe_auto(command, "exit code = 0")


@pytest.mark.parametrize(
    "command",
    [
        "python3 unknown.py",
        "python3 -c 'print(1)'",
        "python3 -m http.server",
        "bash -c 'pytest -q'",
        "./scripts/test.sh",
        "curl https://example.test/health",
        "AWS_PROFILE=prod python3 -m pytest",
        "git checkout -- .",
        "git switch --discard-changes master",
        "gh pr merge 123 --merge",
        "python3 -m uvicorn app:app",
        "pytest --watch",
        "pytest --count 10",
        "pytest --reruns 2",
        "pytest --remote-cluster dev",
        "pytest https://example.test/test.py",
        "pytest -q\ncurl https://example.test/health",
        "while true; do pytest; done",
        "pytest &",
        "pytest | tee result.txt",
        "uv run python3 unknown.py",
        "npm run serve",
        "cargo watch -x test",
        "go test ./... -count=10",
        "go test ./... -count 10",
        "make deploy",
        "pytest /tmp/benign_test.py",
        "pytest ../outside-tests",
        "pytest $HOME",
        "pytest ${HOME}",
        "pytest ~/tests",
        "pytest --junitxml /tmp/benign-report.xml",
        "pytest --junitxml=/tmp/benign-report.xml",
        "pytest C:/outside/test_app.py",
        "pytest tests\\test_app.py",
        "pytest tests/\x07case.py",
        "pytest tests/\u202ecase.py",
    ],
)
def test_safe_auto_rejects_unknown_external_mutating_or_unbounded_command(command: str) -> None:
    # Given a command outside the bounded local allowlist
    # When policy validation runs, Then it fails closed
    with pytest.raises(verification_policy.SafeAutoPolicyError, match="safe-auto"):
        verification_policy.validate_safe_auto(command, "exit code = 0")


@pytest.mark.parametrize(
    "pass_condition",
    [
        "process returns zero",
        "process returns 0",
        "return code zero",
        "no error",
        "no errors occurred",
        "no error is reported",
        "exit code 0 or 1",
        "command succeeds",
        "exits successfully",
        "passes",
    ],
)
def test_safe_auto_rejects_generic_success_synonym(pass_condition: str) -> None:
    # Given a success claim with no explicit numeric or artifact/output assertion
    # When policy validation runs, Then it fails closed
    with pytest.raises(verification_policy.SafeAutoPolicyError, match="observable"):
        verification_policy.validate_safe_auto("pytest -q", pass_condition)


@pytest.mark.parametrize(
    "pass_condition",
    [
        "artifact /tmp/foreign.json exists",
        "file ../outside.txt contains exact",
        "artifact $HOME/report.json exists",
        "file reports/\x07foreign.txt contains exact",
        "artifact reports/\u202ereport.json exists",
    ],
)
def test_safe_auto_rejects_unsafe_observable_path(pass_condition: str) -> None:
    # Given an artifact assertion outside the canonical repository-relative boundary
    # When policy validation runs, Then it fails closed
    with pytest.raises(verification_policy.SafeAutoPolicyError, match="observable"):
        verification_policy.validate_safe_auto("pytest -q", pass_condition)


@pytest.mark.parametrize(
    "pass_condition",
    [
        "exit code 0",
        "exit code equals 0",
        "output contains 44 passed",
        "output exactly equals ok",
        "artifact build/report.json exists",
        "file dist/app.js sha256 equals abc123",
    ],
)
def test_safe_auto_accepts_explicit_observable_pass_condition(pass_condition: str) -> None:
    # Given an explicit numeric, output, or artifact assertion
    # When policy validation runs, Then it accepts the observable
    verification_policy.validate_safe_auto("pytest -q", pass_condition)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
