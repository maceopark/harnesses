#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import (
    ambiguity_ledger,
    build_contract,
    build_contract_schema,
    implementation_gate,
    protocol_state,
    session_update,
)
from scripts.test_build_contract import handoff
from scripts.test_v1_session_integration import create_session


def v1_handoff() -> str:
    return handoff().replace(
        "Decision log: `.ultimateinterview/minimal/decisions.jsonl`",
        "Append every unforced decision to `.ultimateinterview/minimal/decisions.jsonl`.\n"
        "Decision log: `.ultimateinterview/minimal/decisions.jsonl`",
    )


def test_fresh_review_compiles_build_contract_sidecar_atomically(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    (session_dir / "handoff.md").write_text(v1_handoff())
    delta = session_update.parse_delta(
        json.dumps({"build_contract_test": {"reviewer": "reviewer-1"}}),
    )

    # When
    result = session_update.update_session(session_dir, delta)

    # Then
    sidecar = build_contract_schema.BuildContract.model_validate_json(
        (session_dir / "build-contract.json").read_text(),
    )
    assert build_contract.is_current(sidecar, v1_handoff())
    assert result.protocol.build_contract_tested
    assert result.protocol.build_contract_reviewer == "reviewer-1"


def test_v1_gate_requires_present_current_sidecar(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    source = v1_handoff()
    entries = ambiguity_ledger.parse_entries((session_dir / "ledger.json").read_text())
    state = protocol_state.parse_state((session_dir / "protocol.json").read_text())
    ledger_summary = ambiguity_ledger.summarize_ambiguity(
        entries,
        evidence_schema_version=1,
    )
    protocol_summary = protocol_state.summarize_protocol(state)

    # When
    missing = implementation_gate.evaluate(
        entries,
        ledger_summary,
        protocol_summary,
        source,
        protocol=state,
    )
    contract = build_contract.compile_handoff(source)
    stale = implementation_gate.evaluate(
        entries,
        ledger_summary,
        protocol_summary,
        source.replace("Ship deterministic", "Ship changed", 1),
        protocol=state,
        contract_sidecar=contract,
    )

    # Then
    assert "BuildContract v1 sidecar is missing or invalid" in missing.failures
    assert "BuildContract v1 sidecar is stale for the current Part 1" in stale.failures
