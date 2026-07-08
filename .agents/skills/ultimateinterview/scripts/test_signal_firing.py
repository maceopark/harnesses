#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pytest>=8.0",
# ]
# ///

# ─── How to run ───
#      uv run scripts/test_signal_firing.py
# ──────────────────
#
# Locks the signal-firing oracle to canonical cases AND proves its core property:
# because triggers are parsed from orientation.md / lessons.md at runtime,
# removing a trigger makes the case that depended on it stop firing. That is the
# regression signal the closed-loop guide asks for.

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import signal_firing as sf  # noqa: E402

ORIENTATION = sf.DEFAULT_ORIENTATION
LESSONS = [sf.DEFAULT_LESSONS]


def _fire(request: str, touched: str = ""):
    triggers, lessons = sf.load(ORIENTATION, LESSONS)
    return sf.fire(request, triggers, lessons, touched)


# (request, lenses that MUST fire). Other lenses may also fire; these are the
# floor. The first two guard the 2026-07 "experimental" triggers directly.
CANONICAL = [
    ("show me today's tasks with a daily morning rollover", {"domain/state"}),
    ("the command must reject invalid or malformed input", {"controlled-language"}),
    ("it must be fast, reliable and scalable", {"quality"}),
    ("delete user data; handle security and privacy for unauthorized access", {"misuse"}),
    ("the CLI accepts free-text and user-supplied values", {"misuse"}),
    ("add a validation rule for the JSON store; reject oversized input on load", {"domain/state"}),
    ("minimal 3-command personal todo CLI, one JSON store, morning-check flow", {"domain/state"}),
]


@pytest.mark.parametrize("request_text,must_fire", CANONICAL)
def test_canonical_cases_fire(request_text, must_fire):
    fired = set(_fire(request_text))
    missing = must_fire - fired
    assert not missing, f"{request_text!r} failed to fire {missing} (fired: {fired})"


def test_negative_case_fires_nothing():
    assert _fire("rename a helper function in the parser module") == {}


def test_triggers_parse_at_all():
    triggers, lessons = sf.load(ORIENTATION, LESSONS)
    assert set(triggers) == set(sf.LENSES), "every lens must parse a trigger row"
    # the experimental word-lists must be present in the parsed triggers
    assert "today" in triggers["domain/state"]["words"], "temporal trigger not parsed"
    assert "invalid" in triggers["controlled-language"]["words"], "reject-category trigger not parsed"
    assert {"fast", "reliable", "safe"} <= triggers["quality"]["words"], "quality words not parsed"
    assert lessons, "no active lessons rows parsed"
    assert all(r["lens"] == "domain/state" for r in lessons)  # current store rows


def test_removing_temporal_trigger_regresses(tmp_path):
    # THE regression demonstration: strip the temporal word-list from a copy of
    # orientation.md; the real todo-cli-app goal must then stop firing domain/state.
    text = ORIENTATION.read_text(encoding="utf-8")
    stripped = text.replace("today, daily, morning, weekly, due, per-day", "")
    fake = tmp_path / "orientation.md"
    fake.write_text(stripped, encoding="utf-8")

    triggers, lessons = sf.load(fake, LESSONS)
    goal = "minimal 3-command personal todo CLI, one JSON store, morning-check flow"
    # baseline (real triggers) fires domain/state; stripped triggers must not.
    assert "domain/state" in _fire(goal)
    assert "domain/state" not in sf.fire(goal, triggers, lessons)


def test_removing_reject_category_regresses(tmp_path):
    text = ORIENTATION.read_text(encoding="utf-8")
    stripped = text.replace("invalid, malformed, corrupt", "")
    fake = tmp_path / "orientation.md"
    fake.write_text(stripped, encoding="utf-8")
    triggers, lessons = sf.load(fake, LESSONS)
    req = "reject malformed values"  # only the reject category drives controlled-language here
    assert "controlled-language" in _fire(req)
    assert "controlled-language" not in sf.fire(req, triggers, lessons)


def test_retired_lessons_rows_not_parsed():
    # A signal only in the Retired table must not create an active row.
    rows = sf.parse_lessons(LESSONS)
    joined = " ".join(r["signal"].lower() for r in rows)
    # "temporal word in goal" is a RETIRED row (absorbed into orientation) — must be absent.
    assert "temporal word in goal" not in joined


def test_heuristic_anchors_still_in_orientation():
    # Each curated synonym is justified by trigger language still in orientation.md.
    body = ORIENTATION.read_text(encoding="utf-8").lower()
    assert "destructive actions" in body   # justifies misuse delete/remove/destroy/wipe/overwrite
    assert "unauthorized access" in body
    assert "lifecycle states" in body or "legal/illegal transitions" in body  # justifies state-machine synonyms


def test_touched_code_terms_are_searched():
    # A trigger word present only in touched-code should still fire.
    assert "quality" in _fire("update the module", touched="latency reliable throughput")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
