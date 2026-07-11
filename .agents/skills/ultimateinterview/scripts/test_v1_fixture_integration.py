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

import pytest
import typer

from scripts import (
    ambiguity_ledger,
    build_contract,
    build_contract_schema,
    implementation_gate,
    protocol_state,
    session_update,
)

FIXTURES = Path(__file__).parent / "integration_fixtures"


def test_v1_ready_fixture_passes_the_composite_gate() -> None:
    # Given
    fixture = FIXTURES / "v1-ready"
    raw_ledger = (fixture / "ledger.json").read_text()
    entries = ambiguity_ledger.parse_entries(raw_ledger)
    state = protocol_state.parse_state((fixture / "protocol.json").read_text())
    handoff = (fixture / "handoff.md").read_text()
    contract = build_contract_schema.BuildContract.model_validate_json(
        (fixture / "build-contract.json").read_text(),
    )
    assert build_contract.canonical_json(contract) == (
        fixture / "build-contract.json"
    ).read_text()

    # When
    ledger_summary = ambiguity_ledger.summarize_ambiguity(
        entries,
        evidence_schema_version=1,
    )
    result = implementation_gate.evaluate(
        entries,
        ledger_summary,
        protocol_state.summarize_protocol(state),
        handoff,
        protocol=state,
        contract_sidecar=contract,
        raw_ledger_text=raw_ledger,
    )

    # Then
    assert result.implementation_ready


def test_v1_negative_fixtures_fail_closed() -> None:
    # Given
    cases = json.loads((FIXTURES / "v1-negative" / "cases.json").read_text())

    # When
    channel_entries = ambiguity_ledger.parse_entries(
        json.dumps(cases["channel_only_settlement"]),
    )
    model_entries = ambiguity_ledger.parse_entries(
        json.dumps(cases["model_prior_settlement"]),
    )

    # Then
    assert not ambiguity_ledger.summarize_ambiguity(
        channel_entries,
        evidence_schema_version=1,
    ).handoff_ready
    assert ambiguity_ledger.gate_failures(
        model_entries,
        evidence_schema_version=1,
    )
    with pytest.raises(typer.BadParameter, match="authorization"):
        session_update.parse_delta(json.dumps(cases["unauthorized_l3_delta"]))
    assert not implementation_gate.has_decision_log_instruction(
        cases["malicious_negated_decision_instruction"],
        schema_version=1,
    )


def test_v1_stale_sidecar_and_inventory_only_sweep_fail_closed() -> None:
    # Given
    fixture = FIXTURES / "v1-ready"
    state_payload = json.loads((fixture / "protocol.json").read_text())
    state_payload["open_world_records"] = state_payload["open_world_records"][:1]
    state = protocol_state.parse_state(json.dumps(state_payload))
    contract = build_contract_schema.BuildContract.model_validate_json(
        (fixture / "build-contract.json").read_text(),
    )
    entries = ambiguity_ledger.parse_entries((fixture / "ledger.json").read_text())
    handoff = (fixture / "handoff.md").read_text().replace(
        "Preserve an executable",
        "Preserve the executable",
        1,
    )

    # When
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1),
        protocol_state.summarize_protocol(state),
        handoff,
        protocol=state,
        contract_sidecar=contract,
    )

    # Then
    assert "no fresh breadth open-world pass precedes the dry sweep" in result.failures
    assert "BuildContract v1 sidecar is stale for the current Part 1" in result.failures


def test_v1_composite_gate_rejects_raw_legacy_bundle_origin() -> None:
    # Given
    fixture = FIXTURES / "v1-ready"
    raw_payload = json.loads((fixture / "ledger.json").read_text())
    raw_payload["entries"][0]["origin"] = "bundle"
    raw_ledger = json.dumps(raw_payload)
    entries = ambiguity_ledger.parse_entries(raw_ledger)
    state = protocol_state.parse_state((fixture / "protocol.json").read_text())
    handoff = (fixture / "handoff.md").read_text()
    contract = build_contract_schema.BuildContract.model_validate_json(
        (fixture / "build-contract.json").read_text(),
    )

    # When
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1),
        protocol_state.summarize_protocol(state),
        handoff,
        protocol=state,
        contract_sidecar=contract,
        raw_ledger_text=raw_ledger,
    )

    # Then
    assert entries[0].origin == "batch"
    assert "v1 ledger uses legacy-only raw origin 'bundle': REQ-001" in result.failures


def test_v1_composite_gate_recompiles_part1_before_accepting_sidecar() -> None:
    # Given
    fixture = FIXTURES / "v1-ready"
    raw_ledger = (fixture / "ledger.json").read_text()
    entries = ambiguity_ledger.parse_entries(raw_ledger)
    state = protocol_state.parse_state((fixture / "protocol.json").read_text())
    handoff = (fixture / "handoff.md").read_text()
    payload = json.loads((fixture / "build-contract.json").read_text())
    payload["goal"] = "Attacker-controlled goal with a valid self-digest."
    body = build_contract_schema.ContractBody.model_validate(
        {key: value for key, value in payload.items() if key != "contract_digest"},
    )
    payload["contract_digest"] = build_contract_schema.body_digest(body)
    tampered = build_contract_schema.BuildContract.model_validate(payload)

    # When
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1),
        protocol_state.summarize_protocol(state),
        handoff,
        protocol=state,
        contract_sidecar=tampered,
        raw_ledger_text=raw_ledger,
    )

    # Then
    assert tampered.source_part1_sha256 == implementation_gate.contract_digest(handoff)
    assert "BuildContract v1 sidecar does not exactly match compiled Part 1" in result.failures
