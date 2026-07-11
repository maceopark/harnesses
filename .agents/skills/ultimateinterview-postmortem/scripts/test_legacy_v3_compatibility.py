#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import postmortem_lint  # noqa: E402
import verification_execution_lint  # noqa: E402
from test_postmortem_lint import HANDOFF, conforming_report  # noqa: E402

RUNNER = CliRunner()
LEGACY_VERIFICATION = """| Verification command / check | Ran? | Result |
| --- | --- | --- |
| Unit suite | adapted: uv run pytest | pass - 3 tests |
| Real-surface walkthrough | yes | pass - observed output |"""


def _legacy_report() -> str:
    report = conforming_report()
    wonder_start = report.index("## Wonder Generalization")
    wonder_end = report.index("## Deferred Outcomes")
    report = report[:wonder_start] + report[wonder_end:]
    reward_start = report.index("## Reward-Hacking Review")
    reward_end = report.index("## Scope Drift")
    report = report[:reward_start] + report[reward_end:]
    report = report.replace(
        "| REQ-ID | Behavior found in code | Owning lens | Failure class | Weight | Intent attribution | Evidence |\n"
        "| --- | --- | --- | --- | --- | --- | --- |",
        "| Behavior found in code | Owning lens | Failure class | Weight | Evidence |\n"
        "| --- | --- | --- | --- | --- |",
    ).replace(
        "| REQ-001 | temp cleanup | misuse | enumeration-miss | 1 | run-blind | diff hunk |",
        "| temp cleanup | misuse | enumeration-miss | 1 | diff hunk |",
    ).replace(
        "| REQ-002 | dropped case | core-path | synthesis-loss | 2 | owned-signal:decision#7 | ledger vs Part 1 |",
        "| dropped case | core-path | synthesis-loss | 2 | ledger vs Part 1 |",
    )
    old = "| Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect |\n| --- | --- | --- | --- | --- | --- | --- |"
    return report.replace(old, LEGACY_VERIFICATION)


def _session(tmp_path: Path) -> Path:
    session = tmp_path / ".ultimateinterview" / "legacy-v3"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    (session / "postmortem.md").write_text(_legacy_report(), encoding="utf-8")
    (session / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "artifacts": {"files": []},
                "lessons": {"stores": []},
            }
        ),
        encoding="utf-8",
    )
    return session


def test_schema_v3_three_column_verification_is_explicit_legacy_read(tmp_path: Path) -> None:
    # Given a copied live-shaped schema-v3 report with the historical three-column table
    session = _session(tmp_path)

    # When verification provenance is evaluated
    violations = verification_execution_lint.evaluate(session)

    # Then the adapter reads it without claiming v5 capture proof
    assert violations == []


def test_schema_v3_postmortem_omits_only_later_required_sections(tmp_path: Path) -> None:
    # Given the historical report before Wonder, Reward-Hacking, and intent attribution existed
    session = _session(tmp_path)

    # When the complete postmortem lint CLI runs
    result = RUNNER.invoke(postmortem_lint.app, [str(session)])

    # Then explicit schema-v3 compatibility accepts its weaker historical audit contract
    assert result.exit_code == 0, result.output
