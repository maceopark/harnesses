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

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import typer

from scripts import ambiguity_ledger, protocol_state, session_status, session_update

FIXTURES = Path(__file__).parent / "regression_fixtures"


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
