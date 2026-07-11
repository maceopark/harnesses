#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import typer
from typer.testing import CliRunner

from scripts import ambiguity_ledger, protocol_state, session_status, session_update

FIXTURES = Path(__file__).parent / "regression_fixtures"
INTEGRATION_FIXTURES = Path(__file__).parent / "integration_fixtures"


@pytest.mark.parametrize(
    ("fixture", "output_format", "expected_sha256"),
    (
        (FIXTURES / "ready-minimal", "markdown", "7facf057544666142d4a710e081302ea3128c63c1a58f76d71e3b0e590b70422"),
        (FIXTURES / "ready-minimal", "json", "a5585acd9b43aa5dc467def16a76de66391cf1b6487e2b2d76b5689efabb4357"),
        (INTEGRATION_FIXTURES / "v1-ready", "markdown", "2692c62301e557cd0cee3c254960d91eb3c4754b16b3cca35068e2e83384c956"),
        (INTEGRATION_FIXTURES / "v1-ready", "json", "5642ab245fe603cb28f228f40147126a9b1b9bd1dc4043f191fa95153eaa6a9d"),
    ),
)
def test_legacy_session_status_output_bytes_remain_stable(
    tmp_path: Path,
    fixture: Path,
    output_format: str,
    expected_sha256: str,
) -> None:
    # Given
    session = tmp_path / fixture.name
    shutil.copytree(fixture, session)
    app = typer.Typer()
    app.command()(session_status.main)

    # When
    result = CliRunner().invoke(app, ["--format", output_format, str(session)])

    # Then
    assert result.exit_code == 0
    assert hashlib.sha256(result.output.encode("utf-8")).hexdigest() == expected_sha256


def test_v0_ready_fixture_remains_channel_compatible() -> None:
    # Given
    fixture = FIXTURES / "ready-minimal"
    entries = ambiguity_ledger.parse_entries((fixture / "ledger.json").read_text())
    state = protocol_state.parse_state((fixture / "protocol.json").read_text())

    # When
    ledger_summary = ambiguity_ledger.summarize_ambiguity(entries)
    protocol_summary = protocol_state.summarize_protocol(state)

    # Then
    assert session_status.is_ready(ledger_summary, protocol_summary)
    assert entries[0].evidence_channels == ("from-code",)
    assert entries[0].is_single_source_accepted


def test_v0_session_update_is_atomic_when_delta_is_invalid(tmp_path: Path) -> None:
    # Given
    session_dir = tmp_path / "ready-minimal"
    shutil.copytree(FIXTURES / "ready-minimal", session_dir)
    paths = tuple(
        session_dir / name
        for name in ("ledger.json", "protocol.json", "questions.json", "transcript.md")
    )
    before = {path: path.read_bytes() for path in paths}
    delta = session_update.parse_delta(
        json.dumps({"set": [{"id": "missing", "ambiguity_score": 0}]}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="no ledger entry"):
        session_update.update_session(session_dir, delta)
    assert {path: path.read_bytes() for path in paths} == before
