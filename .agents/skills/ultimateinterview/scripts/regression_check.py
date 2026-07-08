#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

# ─── How to run ───
#      uv run scripts/regression_check.py            # check captured fixtures
#      uv run scripts/regression_check.py --live     # also check live .ultimateinterview/ sessions if present
#      uv run scripts/regression_check.py --format json
# ──────────────────
#
# TOOLING REGRESSION HARNESS (closed-loop guide, "One rule before editing the
# skill itself" — half 1).
#
# Before an interview-skill edit ships, the closed-loop guide says to rerun the
# previously measured cases and confirm nothing regressed. Discovery RATE is a
# postmortem property that needs a full human-in-the-loop cycle to remeasure
# (see signal_firing.py for the cheap static half). What CAN be automated is the
# TOOLING: every deterministic script must still run without crashing against
# every prior session, and its host-independent verdict must not move.
#
# This harness runs handoff_coverage.py, verification_lint.py, predicate_lint.py,
# and postmortem_lint.py against a captured fixture set (real prior sessions,
# minus the parts that don't affect these checks) and asserts:
#
#   1. NO CRASH  — no Python traceback, the process produced parseable output.
#   2. handoff_coverage.coverage_ok matches the recorded expectation
#      (deterministic: depends only on ledger.json + handoff.md text).
#   3. postmortem_lint verdict CLASS matches the recorded expectation — either
#      "ok" or a specific "required section missing" (old reports predate the
#      postmortem_lint report contract and legitimately fail its section checks;
#      that is EXPECTED, not a regression — the harness pins the exact section
#      so a NEW kind of failure is still caught).
#   4. verification_lint runs cleanly and emits a well-formed report. Its
#      MISSING-head set is NOT asserted: verification_lint resolves command
#      heads against THIS host's PATH, so the specific missing set is
#      host-dependent (e.g. `compare`/`mktemp` presence varies by host/CI) and
#      asserting it would make the harness flaky. We assert structure, not value.
#
# The fixtures are checked into scripts/regression_fixtures/ so this survives a
# fresh checkout — the live .ultimateinterview/ dirs are gitignored and absent
# on a clean clone. `--live` additionally sweeps any live sessions that exist.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SELF_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SELF_DIR / "regression_fixtures"
LIVE_DIR = SELF_DIR.parents[3] / ".ultimateinterview"  # repo-root/.ultimateinterview

HANDOFF_COVERAGE = SELF_DIR / "handoff_coverage.py"
VERIFICATION_LINT = SELF_DIR / "verification_lint.py"
PREDICATE_LINT = SELF_DIR / "predicate_lint.py"
POSTMORTEM_LINT = (
    SELF_DIR.parent.parent / "ultimateinterview-postmortem" / "scripts" / "postmortem_lint.py"
)

TRACEBACK_MARKER = "Traceback (most recent call last)"

# Recorded expected verdicts per fixture. Each was captured from the real
# session and cross-checked to reproduce on the fixture (see the module docstring
# for what is and is not asserted).
#   coverage_ok: expected handoff_coverage.coverage_ok (bool)
#   postmortem : "ok"                 -> report contract satisfied
#                "missing:<keyword>"  -> legitimately fails a section check (old
#                                        report predating the contract); <keyword>
#                                        is the section the report lacks
#                None                 -> session has no postmortem.md (skip)
EXPECTED: dict[str, dict] = {
    "todo-cli-app-5": {
        "coverage_ok": True,
        "postmortem": "ok",
        "why": "richest closed loop: full handoff, decisions.jsonl, bundle lessons snapshot -> report contract satisfied",
    },
    "todo-cli-app-4": {
        "coverage_ok": False,
        "postmortem": "missing:lessons fire-tracking",
        "why": "predates the postmortem report contract; lacks the lessons fire-tracking section",
    },
    "todo-cli-app": {
        "coverage_ok": False,
        "postmortem": "missing:verification execution",
        "why": "earliest report; lacks the verification-execution section",
    },
    "attribute-search-mysql": {
        "coverage_ok": False,
        "postmortem": None,
        "why": "no postmortem run; exercises handoff_coverage + verification_lint on a non-todo domain",
    },
}


class Regression(Exception):
    """A script crashed or a host-independent verdict moved."""


def _run(script: Path, session_dir: Path, extra: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["uv", "run", str(script), str(session_dir), *extra],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _no_crash(out: str, label: str) -> list[str]:
    return [f"{label}: CRASH (traceback in output)"] if TRACEBACK_MARKER in out else []


def check_session(slug: str, session_dir: Path, expected: dict) -> dict:
    """Run all applicable scripts against one session; return a result row."""
    findings: list[str] = []

    # 1. handoff_coverage — deterministic coverage_ok
    rc, out = _run(HANDOFF_COVERAGE, session_dir, ["--format", "json", "--advisory"])
    findings += _no_crash(out, "handoff_coverage")
    coverage_ok = None
    if not findings:
        try:
            coverage_ok = json.loads(out).get("coverage_ok")
        except json.JSONDecodeError:
            findings.append("handoff_coverage: output was not valid JSON")
    if coverage_ok is not None and coverage_ok != expected["coverage_ok"]:
        findings.append(
            f"handoff_coverage: coverage_ok={coverage_ok}, expected {expected['coverage_ok']}"
        )

    # 2. verification_lint — runs cleanly, well-formed report; value NOT asserted (host-dependent)
    rc, out = _run(VERIFICATION_LINT, session_dir, [])
    findings += _no_crash(out, "verification_lint")
    if rc != 0:
        findings.append(f"verification_lint: advisory run exited {rc} (expected 0)")
    if "executable_ok" not in out:
        findings.append("verification_lint: report missing 'executable_ok' line")

    # 2b. predicate_lint — runs cleanly, well-formed report. The specific
    # flagged set is a heuristic value (bare-category detection has FPs, which is
    # why it is advisory), so we assert STRUCTURE not value, exactly like
    # verification_lint's MISSING-head set. Precise fire/clean assertions live in
    # test_predicate_lint.py against the crafted regression_fixtures/predicate_cases.
    rc, out = _run(PREDICATE_LINT, session_dir, [])
    findings += _no_crash(out, "predicate_lint")
    if rc != 0:
        findings.append(f"predicate_lint: advisory run exited {rc} (expected 0)")
    if "predicate_ok" not in out:
        findings.append("predicate_lint: report missing 'predicate_ok' line")

    # 3. postmortem_lint — verdict class (only if a postmortem exists)
    pm_expected = expected["postmortem"]
    pm_verdict = None
    if pm_expected is not None:
        rc, out = _run(POSTMORTEM_LINT, session_dir, ["--advisory"])
        findings += _no_crash(out, "postmortem_lint")
        low = out.lower()
        if "postmortem_lint: ok" in low:
            pm_verdict = "ok"
        elif "required section missing" in low:
            pm_verdict = "missing"
        else:
            pm_verdict = "other"
        if pm_expected == "ok" and pm_verdict != "ok":
            findings.append(f"postmortem_lint: expected ok, got '{out.strip().splitlines()[0] if out.strip() else out}'")
        elif pm_expected.startswith("missing:"):
            want_section = pm_expected.split(":", 1)[1]
            if pm_verdict != "missing" or want_section.lower() not in low:
                findings.append(
                    f"postmortem_lint: expected missing section '{want_section}', got verdict '{pm_verdict}'"
                )

    return {
        "slug": slug,
        "coverage_ok": coverage_ok,
        "postmortem": pm_verdict if pm_expected is not None else "n/a",
        "findings": findings,
    }


def run_check(include_live: bool = False) -> list[dict]:
    """Run the regression sweep. Returns one result row per session checked."""
    rows: list[dict] = []
    for slug, expected in EXPECTED.items():
        fx = FIXTURES_DIR / slug
        if not fx.is_dir():
            rows.append({"slug": slug, "coverage_ok": None, "postmortem": None,
                         "findings": [f"fixture missing: {fx}"]})
            continue
        rows.append(check_session(slug, fx, expected))

    if include_live and LIVE_DIR.is_dir():
        for slug, expected in EXPECTED.items():
            live = LIVE_DIR / slug
            if live.is_dir():
                row = check_session(f"{slug} (live)", live, expected)
                rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Tooling regression harness for the interview closed loop.")
    ap.add_argument("--live", action="store_true", help="also sweep live .ultimateinterview/ sessions if present")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = ap.parse_args()

    rows = run_check(include_live=args.live)
    regressions = [r for r in rows if r["findings"]]

    if args.format == "json":
        print(json.dumps({"rows": rows, "regressions": len(regressions),
                          "ok": not regressions}, indent=2))
        return 1 if regressions else 0

    print("## Tooling Regression\n")
    print(f"{'session':<28} {'coverage_ok':<12} {'postmortem':<12} status")
    print("-" * 68)
    for r in rows:
        status = "OK" if not r["findings"] else "REGRESSION"
        print(f"{r['slug']:<28} {str(r['coverage_ok']):<12} {str(r['postmortem']):<12} {status}")
    if regressions:
        print("\n### Regressions")
        for r in regressions:
            for f in r["findings"]:
                print(f"- [{r['slug']}] {f}")
        print(f"\n{len(regressions)} session(s) regressed.")
        return 1
    print(f"\nAll {len(rows)} session(s) pass: no crash, host-independent verdicts stable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
