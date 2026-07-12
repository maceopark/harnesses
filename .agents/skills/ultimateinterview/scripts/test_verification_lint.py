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


def test_explicit_path_heads_resolve_against_repo_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    script = root / "scripts" / "check.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `./scripts/check.sh --strict` |\n"
    )
    assert verification_lint.command_head_status(part1, workdir=root) == {
        "./scripts/check.sh": True,
    }


def test_env_wrapper_checks_effective_command(tmp_path: Path) -> None:
    bindir = make_host(tmp_path, ["env"])
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `env X=1 definitely_missing_cmd --version` |\n"
    )
    status = verification_lint.command_head_status(part1, str(bindir), tmp_path)
    assert status == {"env": True, "definitely_missing_cmd": False}


def test_unbalanced_command_is_reported_as_malformed() -> None:
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `python3 -c 'unterminated` |\n"
    )
    assert verification_lint.command_parse_findings(part1)


def test_four_backtick_fence_is_not_closed_by_three_backticks() -> None:
    text = (
        "````markdown\n"
        "```\n"
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| fake | `missing --version` |\n"
        "````\n"
    )

    assert verification_lint.tables(text) == []


def test_escaped_pipeline_checks_every_effective_head(tmp_path: Path) -> None:
    bindir = make_host(tmp_path, ["okcmd"])
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `okcmd --version \\| missingcmd --version` |\n"
    )

    assert verification_lint.command_head_status(part1, str(bindir), tmp_path) == {
        "okcmd": True,
        "missingcmd": False,
    }


def test_static_wrappers_are_unwrapped_and_eval_is_rejected(tmp_path: Path) -> None:
    bindir = make_host(tmp_path, ["command", "exec"])
    command_part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `command missingcmd --version` |\n"
    )
    eval_part1 = command_part1.replace("command missingcmd", "eval missingcmd")

    assert verification_lint.command_head_status(command_part1, str(bindir), tmp_path) == {
        "missingcmd": False,
    }
    assert any("eval" in finding for finding in verification_lint.command_parse_findings(eval_part1))


@pytest.mark.parametrize("wrapper", ["command eval", "exec eval", "command exec eval"])
def test_nested_eval_wrapper_is_rejected(wrapper: str) -> None:
    cell = f"`{wrapper} missingcmd --version`"
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        f"| surface | {cell} |\n"
    )

    assert any("eval" in finding for finding in verification_lint.command_parse_findings(part1))
    assert "missingcmd" not in verification_lint.command_heads(cell)


@pytest.mark.parametrize("cell", ["`npm test`", "`pytest`"])
def test_explicit_bare_commands_are_parsed(cell: str) -> None:
    assert verification_lint.command_heads(cell) == [cell.strip("`").split()[0]]


def test_prose_action_with_apostrophe_is_not_parsed_as_shell() -> None:
    part1 = (
        "## Verification Commands\n"
        "| Check | Command / action |\n"
        "| --- | --- |\n"
        "| visual | Inspect user's rendered result |\n"
    )

    assert verification_lint.command_parse_findings(part1) == ()


def test_uv_is_the_only_host_checked_head_for_project_commands(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        HANDOFF.replace(
            "| Unit suite | cd app && python -m pytest | passes |",
            "| Unit suite | `uv run --project app pytest tests -q` | passes |",
        ),
    )
    bindir = make_host(tmp_path, ["uv", "mktemp", "python", "python3"])
    code, output = lint(session, bindir, "--strict")
    assert code == 0, output
    assert "uv: ok" in output
    assert "uv nested command 'pytest' (project 'app'): project-managed; not host-PATH checked" in output
    assert "pytest: ok" not in output
    assert "policy-approved" not in output


def test_missing_uv_is_advisory_or_strict(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        HANDOFF.replace(
            "| Unit suite | cd app && python -m pytest | passes |",
            "| Unit suite | `uv run pytest tests -q` | passes |",
        ),
    )
    bindir = make_host(tmp_path, ["python3", "mktemp"])
    advisory_code, advisory_output = lint(session, bindir)
    assert advisory_code == 0
    assert "uv: MISSING on this host" in advisory_output
    assert "project-managed; not host-PATH checked" in advisory_output

    strict_code, strict_output = lint(session, bindir, "--strict")
    assert strict_code == 1
    assert "uv: MISSING on this host" in strict_output


def test_non_uv_command_status_remains_host_path_only(tmp_path: Path) -> None:
    part1 = (
        "## Verification Commands\n"
        "| Check | Command |\n"
        "| --- | --- |\n"
        "| surface | `pytest tests -q` |\n"
    )
    bindir = make_host(tmp_path, ["pytest"])
    assert verification_lint.command_head_status(part1, str(bindir), tmp_path) == {
        "pytest": True,
    }
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
