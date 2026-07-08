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
#      uv run scripts/test_postmortem_lint.py
# ──────────────────

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import postmortem_lint

runner = CliRunner()

HANDOFF = """# Spec: demo

# Part 1 - Build Contract

| ID | Requirement |
| --- | --- |
| REQ-001 | a |
| REQ-002 | b |
| REQ-003 | c |

# Part 2 - Audit Trail

REQ-004 appears only in the audit trail and must not be required.
"""

LESSONS = """# Lessons

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
| free-text input | misuse | enumeration-miss | e | 2026-07-01 | 1/1 |
| temporal word | domain/state | trigger-too-narrow | e | 2026-07-01 | 2/2 |

## Retired

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
"""


def conforming_report() -> str:
    return """# Postmortem: demo

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| working tree | demo | a..b |

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | h | i | |
| REQ-002 | fulfilled | h | i | |
| REQ-003 | fulfilled (after review fix) | h | i | |
| temp cleanup | escaped-requirement | absent | todo.py:294 | |
| dropped case | escaped-requirement | ledger g9 | todo.py:120 | |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Weight | Evidence |
| --- | --- | --- | --- | --- |
| temp cleanup | misuse | enumeration-miss | 1 | diff hunk |
| dropped case | core-path | synthesis-loss | 2 | ledger vs Part 1 |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

All Verification Commands ran and passed.

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

### Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md | 1 | free-text input | fired | caught |
| lessons.md | 2 | temporal word | no-signal | - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 3 |
| escaped-requirement | 2 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

Rates: interview-discovery 75.0% (synthesis-loss excluded), handoff-fidelity 60.0%.
Weighted (escape weights in denominator): interview-discovery 75.0%, handoff-fidelity 50.0%.
"""


def make_session(tmp_path: Path, report: str) -> Path:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    (session / "postmortem.md").write_text(report, encoding="utf-8")
    return session


def write_bundle(session: Path, stores: list[dict]) -> None:
    """Minimal evidence_bundle.json holding the audit-start lessons snapshot."""
    (session / "evidence_bundle.json").write_text(
        json.dumps({"lessons": {"stores": stores}}), encoding="utf-8"
    )


TWO_ROW_SNAPSHOT = [{"name": "lessons.md", "active_count": 2}]


def lint(session: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(postmortem_lint.app, [str(session), *extra])
    return result.exit_code, result.output


def test_conforming_report_passes(tmp_path: Path) -> None:
    session = make_session(tmp_path, conforming_report())
    write_bundle(session, TWO_ROW_SNAPSHOT)
    code, output = lint(session)
    assert code == 0, output
    assert "ok" in output


def test_missing_section_fails(tmp_path: Path) -> None:
    report = conforming_report().replace("## Verification Execution", "## Something Else")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "verification execution" in output


def test_req_range_aggregation_fails(tmp_path: Path) -> None:
    report = conforming_report().replace(
        "| REQ-001 | fulfilled | h | i | |", "| REQ-001 through REQ-003 | fulfilled | h | i | |"
    ).replace("| REQ-002 | fulfilled | h | i | |\n", "")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "aggregates a REQ range" in output
    # the range endpoints stay visible but the interior id vanishes untraced
    assert "absent from the Divergence Table: REQ-002" in output


def test_missing_req_row_fails(tmp_path: Path) -> None:
    report = conforming_report().replace("| REQ-003 | fulfilled (after review fix) | h | i | |\n", "")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "absent from the Divergence Table: REQ-003" in output


def test_part2_only_req_is_not_required(tmp_path: Path) -> None:
    session = make_session(tmp_path, conforming_report())
    code, output = lint(session)
    assert code == 0, output


def test_unknown_divergence_class_fails(tmp_path: Path) -> None:
    report = conforming_report().replace("| REQ-002 | fulfilled |", "| REQ-002 | mostly-done |")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "unknown class" in output


def test_calibration_count_mismatch_fails(tmp_path: Path) -> None:
    report = conforming_report().replace("| fulfilled | 3 |", "| fulfilled | 17 |")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "declares fulfilled" in output


def test_wrong_rate_fails(tmp_path: Path) -> None:
    report = conforming_report().replace("handoff-fidelity 60.0%", "handoff-fidelity 89.0%")
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "handoff-fidelity" in output


def test_escape_table_row_count_must_match_divergence(tmp_path: Path) -> None:
    report = conforming_report().replace(
        "| dropped case | core-path | synthesis-loss | 2 | ledger vs Part 1 |\n", ""
    )
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "must match 1:1" in output


def test_bad_escape_weight_fails(tmp_path: Path) -> None:
    report = conforming_report().replace(
        "| temp cleanup | misuse | enumeration-miss | 1 |",
        "| temp cleanup | misuse | enumeration-miss | 4 |",
    )
    session = make_session(tmp_path, report)
    code, output = lint(session)
    assert code == 1
    assert "not one of 1/2/3/5" in output


def test_missing_fire_tracking_row_fails(tmp_path: Path) -> None:
    report = conforming_report().replace(
        "| lessons.md | 2 | temporal word | no-signal | - |\n", ""
    )
    session = make_session(tmp_path, report)
    write_bundle(session, TWO_ROW_SNAPSHOT)
    code, output = lint(session)
    assert code == 1
    assert "active lesson #2" in output


def test_empty_snapshot_requires_nothing(tmp_path: Path) -> None:
    session = make_session(tmp_path, conforming_report())
    write_bundle(session, [{"name": "lessons.md", "active_count": 0}])
    code, output = lint(session)
    assert code == 0, output


def test_bundle_snapshot_anchors_when_live_store_emptied(tmp_path: Path) -> None:
    """The blind-spot fix: even when the LIVE store is empty, the audit-start
    snapshot (2 rows) is enforced, so a report missing a fire-tracking row fails."""
    report = conforming_report().replace(
        "| lessons.md | 2 | temporal word | no-signal | - |\n", ""
    )
    session = make_session(tmp_path, report)
    write_bundle(session, TWO_ROW_SNAPSHOT)  # audit-start = 2
    emptied = tmp_path / "lessons.md"  # live store now has 0 active rows
    emptied.write_text(
        "# Lessons\n\n| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |\n"
        "| --- | --- | --- | --- | --- | --- |\n\n## Retired\n\n"
        "| Signal | Lens to trigger | Retired date | Reason |\n| --- | --- | --- | --- |\n",
        encoding="utf-8",
    )
    code, output = lint(session, "--lessons", str(emptied))
    assert code == 1  # snapshot wins over the emptied live store
    assert "active lesson #2" in output


def test_no_bundle_fallback_warns_about_live_store(tmp_path: Path) -> None:
    session = make_session(tmp_path, conforming_report())  # no bundle written
    lessons = tmp_path / "lessons.md"
    lessons.write_text(LESSONS, encoding="utf-8")
    code, output = lint(session, "--lessons", str(lessons))
    assert code == 1  # fallback anchor is unreliable -> flagged
    assert "LIVE lessons store" in output


def test_bolded_divergence_class_is_accepted(tmp_path: Path) -> None:
    report = conforming_report().replace(
        "| REQ-001 | fulfilled | h | i | |", "| REQ-001 | **fulfilled** | h | i | |"
    )
    session = make_session(tmp_path, report)
    write_bundle(session, TWO_ROW_SNAPSHOT)
    code, output = lint(session)
    assert code == 0, output


def test_advisory_never_blocks(tmp_path: Path) -> None:
    report = conforming_report().replace("## Verification Execution", "## Something Else")
    session = make_session(tmp_path, report)
    code, output = lint(session, "--advisory")
    assert code == 0
    assert "violation" in output


def test_missing_report_exits_two(tmp_path: Path) -> None:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    code, output = lint(session)
    assert code == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
