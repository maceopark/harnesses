#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from typer.testing import CliRunner

from scripts import handoff_coverage
from scripts.test_v2_session_manifest import v2_session

ATOM_BASE = Path(__file__).parent / "integration_fixtures" / "v2-negative" / "atom-base"
CONDITION = "The request declares corrupt, permission, and write modes."


def coverage_app():
    app = handoff_coverage.typer.Typer()
    app.command()(handoff_coverage.main)
    return app


@pytest.mark.parametrize(
    ("name", "transform"),
    (
        ("unrelated-section", lambda catalog: "## Informative Example\n\n" + catalog),
        ("html-comment", lambda catalog: "<!--\n" + catalog + "-->\n"),
        ("hidden-html", lambda catalog: '<div style="display:none">\n' + catalog + "</div>\n"),
        ("collapsed-html", lambda catalog: "<details>\n" + catalog + "</details>\n"),
    ),
)
def test_v2_atom_coverage_rejects_catalogs_outside_visible_behavior_contract(tmp_path: Path, name: str, transform) -> None:
    session = tmp_path / name
    shutil.copytree(ATOM_BASE, session)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    catalog_start = handoff.index("Behavior atom catalog:")
    catalog_end = handoff.index("# Part 2", catalog_start)
    handoff_path.write_text(handoff[:catalog_start] + transform(handoff[catalog_start:catalog_end]) + handoff[catalog_end:], encoding="utf-8")

    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    assert result.exit_code == 1, result.output
    assert payload["coverage_ok"] is True
    assert payload["atom_coverage_ok"] is False
    assert "<catalog> catalog mismatch" in "\n".join(payload["atom_mismatches"])


@pytest.mark.parametrize(
    ("name", "replacement", "expected_exit"),
    (
        ("hidden-html-cell", '<span style="display:none">{condition}</span>', 1),
        ("bare-html-cell", "{condition}<br>", 1),
        ("atom-autolink", "{condition} See <https://example.test/status>.", 0),
    ),
)
def test_v2_atom_coverage_handles_visible_and_hidden_atom_cell_markup(
    tmp_path: Path,
    name: str,
    replacement: str,
    expected_exit: int,
) -> None:
    session = tmp_path / name
    shutil.copytree(ATOM_BASE, session)
    replacement = replacement.format(condition=CONDITION)
    ledger_path = session / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["entries"][0]["behavior_atoms"][0]["condition"] = replacement
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    handoff_path = session / "handoff.md"
    handoff_path.write_text(handoff_path.read_text(encoding="utf-8").replace(CONDITION, replacement, 1), encoding="utf-8")

    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    assert result.exit_code == expected_exit, result.output
    assert payload["atom_coverage_ok"] is (expected_exit == 0)
    if expected_exit:
        assert "<catalog> catalog mismatch" in "\n".join(payload["atom_mismatches"])


def test_v2_atom_coverage_ignores_raw_html_after_behavior_contract(tmp_path: Path) -> None:
    session = v2_session(tmp_path)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    handoff_path.write_text(handoff.replace("## Deferred Risks", "## Deferred Risks\n\n<div>informative note</div>", 1), encoding="utf-8")

    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    assert result.exit_code == 0, result.output
    assert payload["atom_coverage_ok"] is True
