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

from scripts import session_update
from scripts.test_v1_session_integration import create_session

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def probe_decision(level: str = "L0") -> dict[str, JsonValue]:
    return {
        "probe_id": f"PROBE-{level}",
        "intent": "discovery",
        "selected_level": level,
        "target_ledger_ids": ["R1"],
        "predicate": "Observed behavior differs from the reviewed requirement.",
        "contract_digest": "a" * 64,
        "sandboxable_observable": False,
        "requires_runtime_observation": False,
        "production_only": level == "L3",
        "previous_level_insufficiency": None if level == "L0" else "L0 is insufficient.",
        "skipped_level_reason": None if level == "L0" else "Lower levels cannot observe production.",
        "execution_scope": None,
        "authorization": None,
    }


def probe_attempt(outcome: str) -> dict[str, JsonValue]:
    decision = probe_decision()
    material = outcome == "material-divergence"
    return {
        "decision": decision,
        "result": {
            "result_id": f"RESULT-{outcome}",
            "decision_id": "PROBE-L0",
            "intent": "discovery",
            "level": "L0",
            "target_ledger_ids": ["R1"],
            "contract_digest": "a" * 64,
            "producer_lineages": [
                {"producer_id": "repo", "independence_key": "repo", "kind": "repo-docs"},
                {
                    "producer_id": "reviewer",
                    "independence_key": "reviewer",
                    "kind": "fresh-implementer",
                },
            ],
            "artifact_refs": ["artifacts/probe.json"],
            "outcome": outcome,
            "evidence_credit": 1 if material else 0,
            "completeness_credit": 0,
            "reopen_required": material,
            "gap_origin": "origin:probe" if material else None,
        },
    }


def test_no_divergence_cannot_settle_or_credit_a_ledger_entry(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    session_update.update_session(
        session_dir,
        session_update.parse_delta(json.dumps({"probe_decision": probe_decision()})),
    )
    delta = session_update.parse_delta(
        json.dumps(
            {
                "probe_attempt": probe_attempt("no-material-divergence"),
                "set": [{"id": "R1", "status": "accepted"}],
            },
        ),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="cannot settle"):
        session_update.update_session(session_dir, delta)


def test_material_probe_divergence_reopens_and_resets_protocol(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    session_update.update_session(
        session_dir,
        session_update.parse_delta(json.dumps({"probe_decision": probe_decision()})),
    )
    gap = {
        "id": "P1",
        "requirement": "Probe-discovered behavior needs a decision",
        "origin": "probe",
        "status": "draft",
        "ambiguity_score": 3,
        "impact_weight": 5,
        "evidence_records": [],
    }
    delta = session_update.parse_delta(
        json.dumps(
            {
                "probe_attempt": probe_attempt("material-divergence"),
                "add": [gap],
            },
        ),
    )

    # When
    result = session_update.update_session(session_dir, delta)

    # Then
    assert result.entries[-1].origin == "probe"
    assert result.entries[-1].ambiguity_score == 3
    assert result.protocol.material_revision == 2
    assert result.protocol.dry_sweeps_in_row == 0
    assert not result.protocol.checkpoint_since_last_material_change
    assert not result.protocol.build_contract_tested


def test_unauthorized_l3_decision_fails_before_session_writes(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    before = (session_dir / "protocol.json").read_bytes()

    # When / Then
    with pytest.raises(typer.BadParameter, match="authorization"):
        session_update.parse_delta(
            json.dumps({"probe_decision": probe_decision("L3")}),
        )
    assert (session_dir / "protocol.json").read_bytes() == before


def test_probe_attempt_must_exactly_match_persisted_decision_atomically(
    tmp_path: Path,
) -> None:
    # Given
    session_dir = create_session(tmp_path)
    session_update.update_session(
        session_dir,
        session_update.parse_delta(json.dumps({"probe_decision": probe_decision()})),
    )
    protocol_path = session_dir / "protocol.json"
    before = protocol_path.read_bytes()
    attacker_attempt = probe_attempt("no-material-divergence")
    attacker_attempt["decision"] = probe_decision() | {
        "predicate": "Attacker-changed predicate.",
    }
    delta = session_update.parse_delta(
        json.dumps({"probe_attempt": attacker_attempt}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="exactly match"):
        session_update.update_session(session_dir, delta)
    assert protocol_path.read_bytes() == before
