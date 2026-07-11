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
from verification_contract import (
    CAPTURED_OUTPUT_MARKER,
    CapturedOutput,
    canonical_command_digest,
    effective_heads,
    parse_verification_rows,
)

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
def write_postmortem(session: Path, rows: list[str]) -> None:
    table = "\n".join(rows)
    (session / "postmortem.md").write_text(
        "# Postmortem\n\n"
        "## Divergence Table\n\n"
        "| Requirement | Class | Supporting diff paths |\n"
        "| --- | --- | --- |\n"
        f"{table}\n",
        encoding="utf-8",
    )


TEST_ONLY_DIFF = """diff --git a/demo/tests/test_cli.py b/demo/tests/test_cli.py
--- a/demo/tests/test_cli.py
+++ b/demo/tests/test_cli.py
@@
+def test_req001_add(): ...
"""


PRODUCTION_DIFF = """diff --git a/demo/cli.py b/demo/cli.py
--- a/demo/cli.py
+++ b/demo/cli.py
@@
+def add_task(): ...
"""



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
# --- F. cooperation-free intent signals + session process-gap candidate ---

CAPTURE_INTENT_PART1 = """# Part 1 - Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | run surface | command succeeds | g1 |

## Verification Commands

| Check | Kind | Command / action | Pass condition |
| --- | --- | --- | --- |
| REQ-001 surface | real-surface | `okcmd --run` | exits 0 |
"""


def _matching_capture_bundle(*, spawned: bool = True) -> tuple[str, dict[str, object]]:
    row = parse_verification_rows(CAPTURE_INTENT_PART1)[0]
    assert row.effective_heads == effective_heads(row.raw_command)
    capture = CapturedOutput(
        marker=CAPTURED_OUTPUT_MARKER,
        spec_row_number=row.row_number,
        check=row.check,
        kind=row.kind,
        exact_command=row.raw_command,
        command_digest=canonical_command_digest(row.raw_command),
        effective_heads=row.effective_heads,
        cwd="/repo",
        started_at="2026-07-10T00:00:00Z",
        ended_at="2026-07-10T00:00:01Z",
        spawned=spawned,
        timed_out=False,
        timeout_seconds=30,
        exit_code=0,
        stdout="",
        stderr="",
        stdout_full_bytes=0,
        stderr_full_bytes=0,
        stdout_sha256="0" * 64,
        stderr_sha256="0" * 64,
    )
    projection = json.loads(capture.model_dump_json())
    projection.update({"artifact_id": "cap-req001", "file_sha256": "x"})
    return CAPTURE_INTENT_PART1, {
        "schema_version": 4,
        "artifacts": {"captured_outputs": [projection]},
    }


def test_matching_capture_lifts_owned_intent_signal() -> None:
    part1, bundle_data = _matching_capture_bundle()

    lines = audit_scan.scan_intent_signals(
        part1, tests_text="", decisions_text="", bundle_data=bundle_data
    )

    req001 = next(line for line in lines if line.startswith("REQ-001:"))
    assert "owned_intent_signal=true" in req001
    assert "capture:cap-req001" in req001


def test_capture_with_wrong_digest_stays_run_blind() -> None:
    part1, bundle_data = _matching_capture_bundle()
    artifacts = bundle_data["artifacts"]
    assert isinstance(artifacts, dict)
    projections = artifacts["captured_outputs"]
    assert isinstance(projections, list)
    projections[0]["command_digest"] = "f" * 64

    lines = audit_scan.scan_intent_signals(
        part1, tests_text="", decisions_text="", bundle_data=bundle_data
    )

    req001 = next(line for line in lines if line.startswith("REQ-001:"))
    assert "owned_intent_signal=false" in req001


def test_capture_not_spawned_stays_run_blind() -> None:
    part1, bundle_data = _matching_capture_bundle(spawned=False)

    lines = audit_scan.scan_intent_signals(
        part1, tests_text="", decisions_text="", bundle_data=bundle_data
    )

    req001 = next(line for line in lines if line.startswith("REQ-001:"))
    assert "owned_intent_signal=false" in req001

def test_intent_signals_are_presence_only_and_tests_do_not_lift_run_blind(
    tmp_path: Path,
) -> None:
    session = make_session(
        tmp_path,
        decisions=(
            '{"decision":"choose storage predicate","reason":"required rule",'
            '"spec_citation":"REQ-001"}\n'
        ),
    )
    tests = tmp_path / "t"
    tests.mkdir()
    (tests / "test_cli.py").write_text(
        "def test_req002_list(): ...\n", encoding="utf-8"
    )

    code, out = scan(session, "--tests", str(tests))

    assert code == 0
    assert "### F. cooperation-free intent signals (advisory)" in out
    assert "REQ-001: req_named_test=false" in out
    assert "owned_intent_signal=true (provenance: decision#1)" in out
    assert "REQ-002: req_named_test=true (provenance: tests source); owned_intent_signal=false" in out
    assert "intent =" not in out


def test_process_gap_candidate_requires_section_b_hit(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    diff_file = _write(tmp_path, "d.patch", DIFF_WITH_VERSION_FLOOR)

    code, out = scan(session, "--diff-file", diff_file)

    assert code == 0
    assert "execution_process_gap candidate: 1 decision-shaped hunk(s)" in out

    clean_session = make_session(tmp_path / "clean")
    code, out = scan(clean_session)

    assert code == 0
    assert "execution_process_gap candidate" not in out


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
# --- E. reward-hacking support candidates ---


def test_changed_path_classification_is_component_anchored() -> None:
    assert audit_scan.classify_changed_path("demo/tests/test_cli.py") == "test"
    assert audit_scan.classify_changed_path("docs/guide.rst") == "doc"
    assert audit_scan.classify_changed_path("src/contest.py") == "production"
    assert audit_scan.classify_changed_path("src/docs_adapter.py") == "production"


def test_test_only_diff_is_advisory_global_req_candidate(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", TEST_ONLY_DIFF))
    assert code == 0
    assert "### E. reward-hacking support candidates" in out
    assert "global candidate: every changed diff path is test/doc-only" in out
    assert "REQ-001, REQ-002, REQ-003" in out


def test_production_support_removes_fulfilled_req_candidate(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    write_postmortem(
        session, ["| REQ-001 | fulfilled | `demo/tests/test_cli.py` |"]
    )
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", TEST_ONLY_DIFF))
    assert code == 0
    assert "REQ-001: fulfilled row cites only test/doc supporting paths" in out

    write_postmortem(
        session,
        ["| REQ-001 | fulfilled | `demo/tests/test_cli.py`, `demo/cli.py` |"],
    )
    code, out = scan(
        session,
        "--diff-file",
        _write(tmp_path, "d.patch", TEST_ONLY_DIFF + PRODUCTION_DIFF),
    )
    assert code == 0
    assert "REQ-001: fulfilled row cites only test/doc supporting paths" not in out


def test_doc_only_fulfilled_req_is_advisory_candidate(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    write_postmortem(session, ["| REQ-002 | fulfilled | `docs/README.md` |"])
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", TEST_ONLY_DIFF))
    assert code == 0
    assert "REQ-002: fulfilled row cites only test/doc supporting paths" in out


def test_draft_support_mapping_drives_per_req_candidates(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    write_postmortem(
        session,
        [
            "| REQ-001 | fulfilled | `demo/tests/test_cli.py` |",
            "| REQ-002 | fulfilled | `demo/cli.py` |",
            "| REQ-003 | escaped-requirement | `demo/tests/test_cli.py` |",
        ],
    )
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", TEST_ONLY_DIFF))
    assert code == 0
    assert "REQ-001: fulfilled row cites only test/doc supporting paths" in out
    assert "REQ-002: fulfilled row cites only test/doc supporting paths" not in out
    assert "global candidate" not in out


def test_missing_support_ref_is_insufficient_mapping_not_gaming(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    write_postmortem(session, ["| REQ-003 | fulfilled | not recorded |"])
    code, out = scan(session, "--diff-file", _write(tmp_path, "d.patch", TEST_ONLY_DIFF))
    assert code == 0
    assert "insufficient mapping: REQ-003: fulfilled row has insufficient" in out
    assert "REQ-003: fulfilled row cites only test/doc supporting paths" not in out



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
