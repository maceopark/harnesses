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

# ─── How to run ───
#      uv run scripts/test_verification_lint.py
# ──────────────────

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verification_lint

runner = CliRunner()

HANDOFF = """# Spec: demo

# Part 1 - Build Contract

## Quality Bars

| Attribute | Bar | Weight | Verification |
| --- | --- | --- | --- |
| Dependency footprint | stdlib only | 2 | `python - <<'PY'\\nimport modulefinder\\nPY` |

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Unit suite | cd app && python -m pytest | passes |
| Walkthrough | tmp=$(mktemp -d); HOME="$tmp" python3 todo.py list | prints No tasks. |
| Error matrix | Run malformed id, nonexistent id, extra args. | each exits 2 |
| Op matrix | Exercise each op against absent store, valid store; exercise unknown operation once. | no undefined branch |
| Prose semicolon | store state {absent, valid}; assert exit code and raw bytes | no mutation |
| Prose verb | checksum store file before and after each failure case | zero drift |
| Corrupt store | printf '{bad json' > "$tmp/store.json" | exit 3 |

# Part 2 - Audit Trail

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Part 2 table | not-a-real-binary --version | must be ignored |
"""


def make_host(tmp_path: Path, binaries: list[str]) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in binaries:
        target = bindir / name
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
    return bindir


def make_session(tmp_path: Path, handoff: str = HANDOFF) -> Path:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(handoff, encoding="utf-8")
    return session


def lint(session: Path, bindir: Path, *extra: str) -> tuple[int, str]:
    old_path = os.environ["PATH"]
    os.environ["PATH"] = str(bindir)
    try:
        result = runner.invoke(verification_lint.app, [str(session), *extra])
    finally:
        os.environ["PATH"] = old_path
    return result.exit_code, result.output


def test_missing_interpreter_reported_but_advisory_by_default(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python3", "mktemp", "uv"])
    code, output = lint(session, bindir)
    assert code == 0  # advisory by default: report, do not block
    assert "python: MISSING" in output
    assert "python3: ok" in output


def test_strict_blocks_on_missing(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python3", "mktemp", "uv"])
    code, output = lint(session, bindir, "--strict")
    assert code == 1
    assert "python: MISSING" in output


def test_all_present_passes(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python", "python3", "mktemp"])
    code, output = lint(session, bindir, "--strict")
    assert code == 0, output
    assert "executable_ok: yes" in output


def test_prose_fragments_are_not_flagged_as_commands(tmp_path: Path) -> None:
    """The false-positive class the app-2/app-4 handoffs hit: prose fragments
    whose head is a lowercase English word (assert/checksum/user) with no
    flag/path/redirection/assignment signal."""
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python", "python3", "mktemp"])
    code, output = lint(session, bindir, "--strict")
    assert code == 0, output  # nothing missing => the prose heads were NOT treated as commands
    for prose_head in ("assert", "checksum", "user", "exercise", "run", "store"):
        assert f"{prose_head}:" not in output
    assert "printf" not in output  # shell builtin still skipped


def test_own_interpreter_venv_shim_is_not_the_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path)
    venv = tmp_path / "venv"
    venv_bin = venv / "bin"
    venv_bin.mkdir(parents=True)
    shim = venv_bin / "python"
    shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    shim.chmod(0o755)
    real_bin = make_host(tmp_path, ["python3", "mktemp"])
    monkeypatch.setattr(sys, "prefix", str(venv))
    old_path = os.environ["PATH"]
    os.environ["PATH"] = f"{venv_bin}{os.pathsep}{real_bin}"
    try:
        result = runner.invoke(verification_lint.app, [str(session), "--strict"])
    finally:
        os.environ["PATH"] = old_path
    assert result.exit_code == 1
    assert "python: MISSING" in result.output


def test_subshell_heads_are_checked(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python", "python3"])  # no mktemp
    code, output = lint(session, bindir, "--strict")
    assert code == 1
    assert "mktemp: MISSING" in output


def test_part2_tables_are_ignored(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python", "python3", "mktemp"])
    code, output = lint(session, bindir, "--strict")
    assert code == 0, output
    assert "not-a-real-binary" not in output


def test_default_advisory_never_blocks(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    bindir = make_host(tmp_path, ["python3"])
    code, output = lint(session, bindir)
    assert code == 0
    assert "MISSING" in output


def test_missing_handoff_exits_two(tmp_path: Path) -> None:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    bindir = make_host(tmp_path, ["python3"])
    code, _ = lint(session, bindir)
    assert code == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
