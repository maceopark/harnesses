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
#      uv run scripts/test_audit_scan.py
# ──────────────────

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_scan

runner = CliRunner()

HANDOFF = """# Spec: demo

# Part 1 - Build Contract

## Target Surface

| File / module | Expected change |
| --- | --- |
| `demo/cli.py` | implement the CLI |
| `demo/tests/test_cli.py` | acceptance tests |

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | add a task | Given add, prints id | g1 |
| REQ-002 | list tasks | Given list, prints rows | g2 |
| REQ-003 | delete a task | Given delete, removes it | g3 |

## Out Of Scope / Non-Goals

- No priorities, due dates, or tags.
- No network sync or database.

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| suite | cd demo && python -m pytest | passes |

# Part 2 - Audit Trail
"""


def make_session(tmp_path: Path, *, handoff: str = HANDOFF, decisions: str = "",
                 bundle_diff: str | None = None) -> Path:
    repo = tmp_path / "repo"
    session = repo / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(handoff, encoding="utf-8")
    if decisions:
        (session / "decisions.jsonl").write_text(decisions, encoding="utf-8")
    if bundle_diff is not None:
        (session / "evidence_bundle.json").write_text(
            json.dumps({"diff": {"source": "git diff HEAD~1", "text": bundle_diff}}),
            encoding="utf-8",
        )
    return session


def scan(session: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(audit_scan.app, [str(session), *extra])
    return result.exit_code, result.output


# --- A. REQ -> test coverage ---

def test_req_test_mapping_from_tests_dir(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    tests = tmp_path / "t"
    tests.mkdir()
    (tests / "test_cli.py").write_text(
        "def test_req001_add(): ...\n"
        "def test_list_behavior():\n    '''covers REQ-002'''\n",
        encoding="utf-8",
    )
    code, out = scan(session, "--tests", str(tests))
    assert code == 0
    assert "referenced by a test: 2" in out       # REQ-001 (name) + REQ-002 (docstring)
    assert "REQ-003" in out                        # unmapped, listed
    assert "referenced by a test: 3" not in out


def test_req_test_all_mapped_reports_ok(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    tests = tmp_path / "t"
    tests.mkdir()
    (tests / "test_cli.py").write_text(
        "def test_req001(): ...\ndef test_req002(): ...\ndef test_req003(): ...\n",
        encoding="utf-8",
    )
    code, out = scan(session, "--tests", str(tests))
    assert "req_test_ok: yes" in out


# --- B. decision-shape coverage ---

DIFF_WITH_VERSION_FLOOR = """diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@
+requires-python = ">=3.12"
+dependencies = []
"""


def test_decision_shape_unlogged_version_floor_flagged(tmp_path: Path) -> None:
    session = make_session(tmp_path, decisions='{"decision": "used argparse", "reason": "stdlib"}\n')
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", DIFF_WITH_VERSION_FLOOR))
    assert "runtime version floor" in out


def test_decision_shape_logged_version_floor_not_flagged(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        decisions='{"decision": "requires-python >=3.12", "reason": "match-arm syntax needs a version floor"}\n',
    )
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", DIFF_WITH_VERSION_FLOOR))
    assert "runtime version floor" not in out


def test_decision_shape_reads_bundle_diff(tmp_path: Path) -> None:
    session = make_session(tmp_path, bundle_diff=DIFF_WITH_VERSION_FLOOR)
    code, out = scan(session)
    assert "runtime version floor" in out          # picked up from the bundle, no --diff-file


# --- C. scope-creep ---

def test_scope_creep_flags_forbidden_capability(tmp_path: Path) -> None:
    diff = (
        "diff --git a/demo/cli.py b/demo/cli.py\n--- a/demo/cli.py\n+++ b/demo/cli.py\n@@\n"
        "+    parser.add_argument('--priority', choices=['high','low'])\n"
    )
    session = make_session(tmp_path)
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", diff))
    assert "non-goal 'priorities'" in out or "non-goal 'priority'" in out


def test_scope_creep_clean_when_non_goal_absent(tmp_path: Path) -> None:
    diff = (
        "diff --git a/demo/cli.py b/demo/cli.py\n--- a/demo/cli.py\n+++ b/demo/cli.py\n@@\n"
        "+    parser.add_argument('title')\n"
    )
    session = make_session(tmp_path)
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", diff))
    assert "scope_ok: yes" in out


# --- D. promised-artifact existence ---

def test_artifact_missing_flagged(tmp_path: Path) -> None:
    session = make_session(tmp_path)  # repo has no demo/cli.py or demo/tests/test_cli.py
    code, out = scan(session)
    assert "demo/cli.py" in out
    assert "demo/tests/test_cli.py" in out


def test_artifact_present_ok(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    repo = tmp_path / "repo"
    (repo / "demo").mkdir(parents=True)
    (repo / "demo" / "cli.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "demo" / "tests").mkdir()
    (repo / "demo" / "tests" / "test_cli.py").write_text("def test(): ...\n", encoding="utf-8")
    code, out = scan(session)
    assert "artifacts_ok: yes" in out


def test_runtime_temp_paths_not_treated_as_promised(tmp_path: Path) -> None:
    handoff = HANDOFF.replace(
        "| suite | cd demo && python -m pytest | passes |",
        "| walk | HOME=/tmp/x python demo/cli.py; cat ~/.demo.json | ok |",
    )
    session = make_session(tmp_path, handoff=handoff)
    repo = tmp_path / "repo"
    (repo / "demo").mkdir(parents=True)
    (repo / "demo" / "cli.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "demo" / "tests").mkdir()
    (repo / "demo" / "tests" / "test_cli.py").write_text("def test(): ...\n", encoding="utf-8")
    code, out = scan(session)
    assert "/tmp/x" not in out
    assert "~/.demo.json" not in out
    assert "artifacts_ok: yes" in out


# --- gate + errors ---

def test_advisory_by_default_never_blocks(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    code, _ = scan(session)
    assert code == 0


def test_strict_blocks_on_findings(tmp_path: Path) -> None:
    session = make_session(tmp_path)  # missing artifacts => findings
    code, _ = scan(session, "--strict")
    assert code == 1


def test_missing_handoff_exits_two(tmp_path: Path) -> None:
    session = tmp_path / "empty"
    session.mkdir()
    code, _ = scan(session)
    assert code == 2


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
