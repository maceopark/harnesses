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

import postmortem_lint
from test_postmortem_lint import HANDOFF, conforming_report

RUNNER = CliRunner()


def _report() -> str:
    report = conforming_report()
    report = report.replace(
        "# Postmortem: demo\n",
        "# Postmortem: demo\n\npostmortem_schema: 2\n",
    ).replace(
        "| temp cleanup | escaped-requirement | absent | todo.py:294 | |",
        "| ESC-001 | escaped-requirement | absent | todo.py:294 | |",
    ).replace(
        "| dropped case | escaped-requirement | ledger g9 | todo.py:120 | |",
        "| ESC-002 | escaped-requirement | ledger g9 | todo.py:120 | |",
    )
    legacy_escapes = """| REQ-ID | Behavior found in code | Owning lens | Failure class | Weight | Intent attribution | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | temp cleanup | misuse | enumeration-miss | 1 | run-blind | diff hunk |
| REQ-002 | dropped case | core-path | synthesis-loss | 2 | owned-signal:decision#7 | ledger vs Part 1 |"""
    v2_escapes = """| ESC-ID | Behavior found in code | Failure mode | Requirement structure | Owning frame | Weight | Intent attribution | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ESC-001 | temp cleanup | enumeration-miss | interaction+runtime-only | misuse | 1 | run-blind | deduped | lessons.md | diff hunk |
| ESC-002 | dropped ontology | ontology-miss | novel:feedback-loop+negative-space | none | 2 | run-blind | not-routing/ontology-miss | n/a | artifact-generic |"""
    report = report.replace(legacy_escapes, v2_escapes)
    legacy_wonder = """| Escape REQ-ID | Unknown class | Interview-time observable signal | Lens | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | cleanup boundary | request touches temporary files | misuse | deduped | lessons.md | existing signal |
| REQ-002 | handoff transport | settled ledger behavior omitted from Part 1 | core-path | not-routing/synthesis-loss | n/a | not an unknown: handoff transport loss |"""
    v2_wonder = """| Escape ID | Unknown class | Interview-time observable signal | Owning frame | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| ESC-001 | cleanup boundary | request touches temporary files | misuse | deduped | lessons.md | existing signal |
| ESC-002 | feedback loop | external artifact exposed a missing category | none | not-routing/ontology-miss | n/a | artifact-generic |"""
    report = report.replace(legacy_wonder, v2_wonder)
    return report.replace(
        "Rates: interview-discovery",
        """| Failure mode | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 1 |
| scoring-starved | 0 |
| answer-unpressured | 0 |
| synthesis-loss | 0 |
| ontology-miss | 1 |

| Structure / modifier / owner | Count |
| --- | --- |
| item | 0 |
| boundary | 0 |
| interaction | 1 |
| system | 0 |
| novel:feedback-loop | 1 |
| modifier:negative-space | 1 |
| modifier:runtime-only | 1 |
| owning-frame:none | 1 |

Rates: interview-discovery""",
    ).replace(
        "interview-discovery 75.0% (synthesis-loss excluded), handoff-fidelity 60.0%.",
        "interview-discovery 60.0% (no synthesis loss), handoff-fidelity 60.0%.",
    ).replace(
        "interview-discovery 75.0%, handoff-fidelity 50.0%.",
        "interview-discovery 50.0%, handoff-fidelity 50.0%.",
    )


def _session(tmp_path: Path, report: str) -> Path:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    (session / "postmortem.md").write_text(report, encoding="utf-8")
    (session / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "artifacts": {
                    "files": [{"id": "artifact-generic", "kind": "data"}],
                    "captured_outputs": [],
                },
                "lessons": {"stores": []},
            }
        ),
        encoding="utf-8",
    )
    return session


def _lint(session: Path) -> tuple[int, str]:
    result = RUNNER.invoke(postmortem_lint.app, [str(session)])
    return result.exit_code, result.output


def test_schema_v2_uses_exact_esc_joins_and_generic_negative_space_evidence(
    tmp_path: Path,
) -> None:
    # Given a v2 report with two exactly joined ESC identities
    session = _session(tmp_path, _report())

    # When the report is linted, Then the taxonomy and generic artifact evidence pass
    code, output = _lint(session)
    assert code == 0, output


def test_schema_v2_rejects_fulfilled_req_masquerading_as_escape(tmp_path: Path) -> None:
    # Given a Part-1 REQ row mislabeled as an escape
    report = _report().replace(
        "| REQ-001 | fulfilled | h | i | |",
        "| REQ-001 | escaped-requirement | h | i | |",
    )

    # When linted, Then only stable ESC identities may represent escapes
    code, output = _lint(_session(tmp_path, report))
    assert code == 1
    assert "REQ-001" in output and "ESC" in output


def test_schema_v2_rejects_missing_structure_and_routed_ontology(tmp_path: Path) -> None:
    # Given independently malformed structure and ontology ownership rows
    reports = (
        _report().replace("novel:feedback-loop+negative-space | none", " | none"),
        _report().replace("novel:feedback-loop+negative-space | none", "novel:feedback-loop+negative-space | misuse"),
    )

    # When linted, Then both taxonomy violations fail closed
    outputs = [_lint(_session(tmp_path / str(index), report)) for index, report in enumerate(reports)]
    assert all(code == 1 for code, _output in outputs)
    assert "structure" in outputs[0][1].lower()
    assert "ontology" in outputs[1][1].lower()


def test_schema_v2_rejects_ontology_routing_or_lesson_write(tmp_path: Path) -> None:
    # Given an ontology miss routed as a new lesson
    report = _report().replace(
        "none | not-routing/ontology-miss | n/a | artifact-generic |",
        "none | new | lessons.md | artifact-generic |",
    )

    # When linted, Then ontology misses remain non-routing and write no lesson
    code, output = _lint(_session(tmp_path, report))
    assert code == 1
    assert "not-routing/ontology-miss" in output


def test_schema_v2_calibration_is_derived_from_escape_rows(tmp_path: Path) -> None:
    # Given a declared structure count that disagrees with the escape rows
    report = _report().replace("| modifier:runtime-only | 1 |", "| modifier:runtime-only | 0 |")

    # When linted, Then the declared calibration cannot drift from the table
    code, output = _lint(_session(tmp_path, report))
    assert code == 1
    assert "modifier:runtime-only" in output
