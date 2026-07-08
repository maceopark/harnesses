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
    assert rows["todo-cli-app-5"]["coverage_ok"] is True
    assert rows["todo-cli-app-5"]["postmortem"] == "ok"
    assert rows["todo-cli-app-4"]["coverage_ok"] is False
    assert rows["todo-cli-app-4"]["postmortem"] == "missing"
    assert rows["attribute-search-mysql"]["postmortem"] == "n/a"


def test_wrong_coverage_expectation_is_flagged():
    # Flip the expected coverage_ok -> the harness must complain (not vacuously pass).
    fx = rc.FIXTURES_DIR / "todo-cli-app-5"
    bad = {"coverage_ok": False, "postmortem": "ok"}  # real value is True
    row = rc.check_session("todo-cli-app-5", fx, bad)
    assert any("coverage_ok" in f for f in row["findings"]), row["findings"]


def test_wrong_postmortem_section_is_flagged():
    # Pin a section the report does NOT lack -> flagged.
    fx = rc.FIXTURES_DIR / "todo-cli-app-4"
    bad = {"coverage_ok": False, "postmortem": "missing:a section that does not exist"}
    row = rc.check_session("todo-cli-app-4", fx, bad)
    assert any("postmortem_lint" in f for f in row["findings"]), row["findings"]


def test_ok_required_when_expected_ok():
    # If we expect "ok" but the report only had a missing-section, flag it.
    fx = rc.FIXTURES_DIR / "todo-cli-app-4"  # this one is missing-section, not ok
    bad = {"coverage_ok": False, "postmortem": "ok"}
    row = rc.check_session("todo-cli-app-4", fx, bad)
    assert any("postmortem_lint" in f for f in row["findings"]), row["findings"]


def test_missing_fixture_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "FIXTURES_DIR", tmp_path)  # empty -> every fixture missing
    rows = rc.run_check(include_live=False)
    assert rows and all(r["findings"] for r in rows)


def test_crash_detector_matches_traceback():
    assert rc._no_crash("Traceback (most recent call last):\n ...", "x")
    assert not rc._no_crash("- executable_ok: yes\n", "x")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
