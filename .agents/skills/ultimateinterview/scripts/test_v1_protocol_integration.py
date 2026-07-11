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
from pydantic import TypeAdapter, ValidationError

from scripts import protocol_state, session_init

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def sweep(sweep_id: str, phase: str, revision: int) -> dict[str, JsonValue]:
    return {
        "sweep_id": sweep_id,
        "phase": phase,
        "precedes": "lens-selection" if phase == "orientation" else "dry-sweep",
        "interaction_cost": 0,
        "material_revision_binding": revision,
        "candidates": [],
    }


def ready_v1_protocol() -> dict[str, JsonValue]:
    payload = TypeAdapter(dict[str, JsonValue]).validate_python(
        session_init.initial_protocol(protocol_state.Depth.MINIMAL, None),
    )
    payload.update(
        {
            "framing_challenged": True,
            "brain_dump_done": True,
            "sweeps_run": 2,
            "dry_sweeps_in_row": 2,
            "contrarian_probes_run": 1,
            "falsification_checkpoints_run": 1,
            "checkpoint_since_last_material_change": True,
            "build_contract_tested": True,
            "build_contract_digest": "a" * 64,
            "build_contract_reviewer": "reviewer",
            "open_world_records": [
                sweep("OW-orient", "orientation", 0),
                sweep("OW-breadth", "breadth", 0),
            ],
            "lenses": {
                name: {"state": "skipped", "reason": "not applicable"}
                for name in sorted(protocol_state.LENS_NAMES)
            },
        },
    )
    return payload


def test_new_sessions_initialize_v1_schema_versions() -> None:
    # Given / When
    protocol = session_init.initial_protocol(protocol_state.Depth.FOCUSED, None)

    # Then
    assert protocol["evidence_schema_version"] == 1
    assert protocol["contract_schema_version"] == 1
    assert protocol["material_revision"] == 0


def test_old_protocol_defaults_both_schema_versions_to_v0() -> None:
    # Given
    fixture = Path(__file__).parent / "regression_fixtures" / "ready-minimal" / "protocol.json"

    # When
    state = protocol_state.parse_state(fixture.read_text())

    # Then
    assert state.evidence_schema_version == 0
    assert state.contract_schema_version == 0


def test_v1_requires_orientation_and_fresh_breadth_open_world_records() -> None:
    # Given
    payload = ready_v1_protocol()
    payload["open_world_records"] = [sweep("OW-orient", "orientation", 0)]

    # When
    state = protocol_state.parse_state(json.dumps(payload))
    blockers = protocol_state.build_handoff_blockers(state)

    # Then
    assert "no fresh breadth open-world pass precedes the dry sweep" in blockers


def test_material_revision_makes_open_world_records_stale() -> None:
    # Given
    payload = ready_v1_protocol()
    payload["material_revision"] = 1

    # When
    state = protocol_state.parse_state(json.dumps(payload))
    blockers = protocol_state.build_handoff_blockers(state)

    # Then
    assert "orientation open-world pass is stale after a material change" in blockers
    assert "no fresh breadth open-world pass precedes the dry sweep" in blockers


def test_protocol_rejects_sequence_decision_drift_behind_same_probe_id() -> None:
    # Given
    fixture = Path(__file__).parent / "integration_fixtures" / "v1-ready" / "protocol.json"
    payload = json.loads(fixture.read_text())
    payload["probe_sequence"]["attempts"][0]["decision"]["predicate"] = (
        "Attacker-changed predicate."
    )

    # When / Then
    with pytest.raises(ValidationError, match="exactly match"):
        protocol_state.parse_state(json.dumps(payload))
