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

import sys
import subprocess
from pathlib import Path

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
        return 0, '{"interview_converged": false}'

    monkeypatch.setattr(rc, "_run", status_only)

    row = rc.check_unrecorded_live("in-progress", session)

    assert calls == [rc.SESSION_STATUS]
    assert row["findings"] == []


def test_crash_detector_matches_traceback():
    assert rc._no_crash("Traceback (most recent call last):\n ...", "x")
    assert not rc._no_crash("- executable_ok: yes\n", "x")


def test_child_timeout_is_reported(monkeypatch, tmp_path):
    def time_out(*args, **kwargs):
        del args, kwargs
        raise subprocess.TimeoutExpired(["uv", "run"], rc.CHILD_TIMEOUT_SECONDS)

    monkeypatch.setattr(rc.subprocess, "run", time_out)

    code, output = rc._run(tmp_path / "script.py", tmp_path, [])

    assert code == 124
    assert "timed out" in output


def test_missing_coverage_verdict_is_flagged(tmp_path, monkeypatch):
    outputs = iter(
        [
            (0, "{}"),
            (0, "- executable_ok: yes\n"),
            (0, "- predicate_ok: yes\n"),
            (0, '{"ledger":{"handoff_ready":true},"protocol":{"protocol_ready":true},"interview_converged":true}'),
            (0, '{"implementation_gate":{"implementation_ready":true}}'),
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
    }

    row = rc.check_session("shape", tmp_path, expected)

    assert any("coverage JSON" in finding for finding in row["findings"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
