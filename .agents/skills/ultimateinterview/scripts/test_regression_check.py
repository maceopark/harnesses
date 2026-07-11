#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pytest>=8.0",
# ]
# ///

# ─── How to run ───
#      uv run scripts/test_regression_check.py
# ──────────────────
#
# Proves the tooling-regression harness has teeth: it passes on the captured
# fixtures AND flags a moved verdict / missing fixture. A harness that always
# passes would be worse than none.

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import regression_check as rc  # noqa: E402


def test_all_fixtures_present():
    for slug in rc.EXPECTED:
        assert (rc.FIXTURES_DIR / slug).is_dir(), f"fixture {slug} missing from tree"


def test_all_fixtures_pass():
    rows = rc.run_check(include_live=False)
    assert len(rows) == len(rc.EXPECTED)
    for row in rows:
        assert not row["findings"], f"{row['slug']}: {row['findings']}"


def test_recorded_verdicts_are_the_observed_ones():
    # The clean closed loop must read clean; the older reports must read as
    # section-fail-by-design. Pins the shape so a future edit that quietly
    # flips one is caught.
    rows = {r["slug"]: r for r in rc.run_check(include_live=False)}
    assert rows["ready-minimal"]["coverage_ok"] is True
    assert rows["ready-minimal"]["postmortem"] == "n/a"
    assert rows["todo-cli-app-5"]["coverage_ok"] is True
    assert rows["todo-cli-app-5"]["postmortem"] == "ok"
    assert rows["todo-cli-app-5"]["verification_execution"] == "ok"
    assert rows["todo-cli-app-4"]["coverage_ok"] is False
    assert rows["todo-cli-app-4"]["postmortem"] == "missing"
    assert rows["attribute-search-mysql"]["postmortem"] == "n/a"


def test_wrong_coverage_expectation_is_flagged():
    # Flip the expected coverage_ok -> the harness must complain (not vacuously pass).
    fx = rc.FIXTURES_DIR / "todo-cli-app-5"
    bad = {**rc.EXPECTED["todo-cli-app-5"], "coverage_ok": False}
    row = rc.check_session("todo-cli-app-5", fx, bad)
    assert any("coverage_ok" in f for f in row["findings"]), row["findings"]


def test_wrong_postmortem_section_is_flagged():
    # Pin a section the report does NOT lack -> flagged.
    fx = rc.FIXTURES_DIR / "todo-cli-app-4"
    bad = {
        **rc.EXPECTED["todo-cli-app-4"],
        "postmortem": "missing:a section that does not exist",
    }
    row = rc.check_session("todo-cli-app-4", fx, bad)
    assert any("postmortem_lint" in f for f in row["findings"]), row["findings"]


def test_ok_required_when_expected_ok():
    # If we expect "ok" but the report only had a missing-section, flag it.
    fx = rc.FIXTURES_DIR / "todo-cli-app-4"  # this one is missing-section, not ok
    bad = {**rc.EXPECTED["todo-cli-app-4"], "postmortem": "ok"}
    row = rc.check_session("todo-cli-app-4", fx, bad)
    assert any("postmortem_lint" in f for f in row["findings"]), row["findings"]


def test_missing_fixture_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "FIXTURES_DIR", tmp_path)  # empty -> every fixture missing
    rows = rc.run_check(include_live=False)
    assert rows and all(r["findings"] for r in rows)


def test_live_sweep_includes_unrecorded_sessions(tmp_path, monkeypatch):
    live = tmp_path / "unexpected-session"
    live.mkdir()
    (tmp_path / ".retryable.init-orphan").mkdir()
    monkeypatch.setattr(rc, "LIVE_DIR", tmp_path)
    monkeypatch.setattr(rc, "EXPECTED", {})
    monkeypatch.setattr(
        rc,
        "check_unrecorded_live",
        lambda slug, _path: {
            "slug": f"{slug} (live-unrecorded)",
            "coverage_ok": True,
            "postmortem": "n/a",
            "findings": [],
        },
    )

    rows = rc.run_check(include_live=True)

    assert [row["slug"] for row in rows] == ["unexpected-session (live-unrecorded)"]


def test_unrecorded_in_progress_session_skips_handoff_only_checks(tmp_path, monkeypatch):
    session = tmp_path / "in-progress"
    session.mkdir()
    calls = []

    def status_only(script, _session, _extra):
        calls.append(script)
        return 0, '{"interview_converged": false}', ""

    monkeypatch.setattr(rc, "_run", status_only)

    row = rc.check_unrecorded_live("in-progress", session)

    assert calls == [rc.SESSION_STATUS]
    assert row["findings"] == []


def test_crash_detector_matches_traceback():
    assert rc._no_crash("Traceback (most recent call last):\n ...", "x")
    assert not rc._no_crash("- executable_ok: yes\n", "x")


def test_run_returns_valid_stdout_when_stderr_is_empty(tmp_path):
    # Given: a child that emits valid JSON only on stdout.
    script = tmp_path / "valid_stdout.py"
    script.write_text(
        "print('{\"coverage_ok\": true}')\n",
        encoding="utf-8",
    )

    # When: the regression harness runs the child.
    code, stdout, stderr = rc._run(script, tmp_path, [])

    # Then: the current parseable stdout contract is preserved.
    assert code == 0
    assert stdout.strip() == '{"coverage_ok": true}'
    assert stderr == ""


def test_valid_child_json_is_parseable_when_stderr_has_install_warning(
    monkeypatch,
    tmp_path,
):
    # Given: JSON-producing children keep stdout valid while uv warns on stderr.
    outputs = iter(
        [
            (0, '{"coverage_ok": true}', "warning: installing cold-cache dependencies\n"),
            (0, "- executable_ok: yes\n", ""),
            (0, "- predicate_ok: yes\n", ""),
            (0, '{"ledger":{"handoff_ready":true},"protocol":{"protocol_ready":true},"interview_converged":true}', "warning: reusing cold-cache environment\n"),
            (0, '{"implementation_gate":{"implementation_ready":true}}', "warning: reusing cold-cache environment\n"),
        ]
    )
    monkeypatch.setattr(rc, "_run", lambda *_args, **_kwargs: next(outputs))
    expected = {
        "coverage_ok": True,
        "handoff_ready": True,
        "protocol_ready": True,
        "interview_converged": True,
        "implementation_ready": True,
        "postmortem": None,
        "verification_execution": None,
    }

    # When: the harness checks the session.
    row = rc.check_session("cold-cache", tmp_path, expected)

    # Then: stderr diagnostics do not corrupt stdout JSON parsing.
    assert row["findings"] == []


def test_child_timeout_is_reported(monkeypatch, tmp_path):
    process = Mock(pid=999_999)
    process.communicate.side_effect = [
        subprocess.TimeoutExpired(["uv", "run"], rc.CHILD_TIMEOUT_SECONDS),
        ("partial-out", "partial-err"),
    ]
    monkeypatch.setattr(rc.subprocess, "Popen", lambda *_args, **_kwargs: process)
    if os.name == "posix":
        monkeypatch.setattr(rc.os, "killpg", lambda *_args: None)

    code, stdout, stderr = rc._run(tmp_path / "script.py", tmp_path, [])

    assert code == 124
    assert stdout == "partial-out"
    assert "partial-err" in stderr
    assert "timed out" in stderr


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup is POSIX-only")
def test_timeout_terminates_and_reaps_real_child_group(monkeypatch, tmp_path):
    # Given: a real Python child that emits both streams, records its PID, and hangs.
    script = tmp_path / "hung_child.py"
    marker = tmp_path / "hung-child.json"
    script.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import signal\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "marker = Path(sys.argv[1]) / 'hung-child.json'\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "marker.write_text(json.dumps({'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgid(0)}), encoding='utf-8')\n"
        "print('started-out', flush=True)\n"
        "print('started-err', file=sys.stderr, flush=True)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rc, "CHILD_TIMEOUT_SECONDS", 1)

    # When: the regression subprocess boundary times out.
    code, stdout, stderr = rc._run(script, tmp_path, [])
    child = json.loads(marker.read_text(encoding="utf-8"))
    child_pid = child["pid"]
    process_row = subprocess.run(
        ["ps", "-o", "pid=,ppid=,pgid=,stat=,command=", "-p", str(child_pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    try:
        # Then: the entire child group is gone, the wrapper is reaped, and output survives.
        assert code == 124
        assert process_row == "", f"orphaned child after timeout: {process_row}"
        assert "started-out" in stdout
        assert "started-err" in stderr
        assert "timed out" in stderr
    finally:
        if process_row:
            os.kill(child_pid, signal.SIGKILL)


def test_missing_coverage_verdict_is_flagged(tmp_path, monkeypatch):
    outputs = iter(
        [
            (0, "{}", ""),
            (0, "- executable_ok: yes\n", ""),
            (0, "- predicate_ok: yes\n", ""),
            (0, '{"ledger":{"handoff_ready":true},"protocol":{"protocol_ready":true},"interview_converged":true}', ""),
            (0, '{"implementation_gate":{"implementation_ready":true}}', ""),
        ]
    )
    monkeypatch.setattr(rc, "_run", lambda *_args, **_kwargs: next(outputs))
    expected = {
        "coverage_ok": True,
        "handoff_ready": True,
        "protocol_ready": True,
        "interview_converged": True,
        "implementation_ready": True,
        "postmortem": None,
        "verification_execution": None,
    }

    row = rc.check_session("shape", tmp_path, expected)

    assert any("coverage JSON" in finding for finding in row["findings"])


def test_malformed_child_json_reports_stderr_diagnostic(tmp_path, monkeypatch):
    # Given: a malformed JSON child result with useful stderr context.
    outputs = iter(
        [
            (0, "not-json", "warning: cold-cache install failed\n"),
            (0, "- executable_ok: yes\n", ""),
            (0, "- predicate_ok: yes\n", ""),
            (0, '{"ledger":{"handoff_ready":true},"protocol":{"protocol_ready":true},"interview_converged":true}', ""),
            (0, '{"implementation_gate":{"implementation_ready":true}}', ""),
        ]
    )
    monkeypatch.setattr(rc, "_run", lambda *_args, **_kwargs: next(outputs))
    expected = {
        "coverage_ok": True,
        "handoff_ready": True,
        "protocol_ready": True,
        "interview_converged": True,
        "implementation_ready": True,
        "postmortem": None,
        "verification_execution": None,
    }

    # When: the harness parses the malformed stdout.
    row = rc.check_session("malformed", tmp_path, expected)

    # Then: the parse failure retains stderr as diagnostic context.
    assert any(
        "coverage JSON" in finding and "cold-cache install failed" in finding
        for finding in row["findings"]
    )


def test_nonzero_child_exit_is_still_reported(tmp_path, monkeypatch):
    # Given: valid JSON from a child that exits nonzero.
    outputs = iter(
        [
            (7, '{"coverage_ok": true}', ""),
            (0, "- executable_ok: yes\n", ""),
            (0, "- predicate_ok: yes\n", ""),
            (0, '{"ledger":{"handoff_ready":true},"protocol":{"protocol_ready":true},"interview_converged":true}', ""),
            (0, '{"implementation_gate":{"implementation_ready":true}}', ""),
        ]
    )
    monkeypatch.setattr(rc, "_run", lambda *_args, **_kwargs: next(outputs))
    expected = {
        "coverage_ok": True,
        "handoff_ready": True,
        "protocol_ready": True,
        "interview_converged": True,
        "implementation_ready": True,
        "postmortem": None,
        "verification_execution": None,
    }

    # When: the harness evaluates the child result.
    row = rc.check_session("nonzero", tmp_path, expected)

    # Then: the existing exit-code failure semantics remain intact.
    assert "handoff_coverage: advisory run exited 7 (expected 0)" in row["findings"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
