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
from typer.testing import CliRunner

from scripts import protocol_state, session_init, session_status, session_update

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def evidence(evidence_id: str, group: str) -> dict[str, JsonValue]:
    return {
        "id": evidence_id,
        "channel": "from-code",
        "claim_kind": "observed-fact",
        "source_actor": "repository",
        "provenance_mode": "firsthand",
        "independence_group": group,
        "freshness": "current",
        "warrant": f"Observed {evidence_id}",
        "epistemic_authority": "establishes",
        "decision_authority": "none",
    }


def create_session(tmp_path: Path) -> Path:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    protocol = session_init.initial_protocol(protocol_state.Depth.MINIMAL, None)
    protocol.update(
        {
            "dry_sweeps_in_row": 2,
            "sweeps_run": 2,
            "checkpoint_since_last_material_change": True,
            "build_contract_tested": True,
            "build_contract_digest": "a" * 64,
            "build_contract_reviewer": "reviewer",
        },
    )
    ledger = {
        "entries": [
            {
                "id": "R1",
                "requirement": "Behavior is known",
                "origin": "orientation",
                "status": "triangulated",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "evidence_records": [evidence("E1", "repo-a"), evidence("E2", "repo-b")],
            },
        ],
    }
    (session_dir / "ledger.json").write_text(json.dumps(ledger))
    (session_dir / "protocol.json").write_text(json.dumps(protocol))
    (session_dir / "questions.json").write_text('{"questions": []}')
    (session_dir / "transcript.md").write_text("# Transcript\n")
    return session_dir


@pytest.mark.parametrize(
    ("slug", "evidence_channels"),
    (("v2-init-with-channel", ("from-user",)), ("v2-init-without-channel", ())),
)
def test_v2_session_init_is_immediately_status_readable(
    tmp_path: Path,
    slug: str,
    evidence_channels: tuple[str, ...],
) -> None:
    # Given
    repo = tmp_path / "repo"
    repo.mkdir()
    entry = {
        "id": "REQ-001",
        "requirement": "A bounded behavior",
        "origin": "orientation",
        "status": "draft",
        "ambiguity_score": 3,
        "impact_weight": 5,
        "assurance_class": "high",
        "behavior_atoms": [
            {
                "id": "ATOM-001",
                "condition": "The bounded behavior is invoked.",
                "polarity": "must",
                "observable_response": "The bounded behavior is observable.",
                "boundary_context": None,
                "temporal_context": None,
                "coercion_context": None,
            },
        ],
    }
    if evidence_channels:
        entry["evidence_channels"] = list(evidence_channels)
    init_app = typer.Typer()
    init_app.command()(session_init.main)
    status_app = typer.Typer()
    status_app.command()(session_status.main)

    # When
    init_result = CliRunner().invoke(
        init_app,
        [str(repo), slug, "--entries", json.dumps([entry]), "--schema-version", "2"],
    )
    session = repo / ".ultimateinterview" / slug
    status_result = CliRunner().invoke(status_app, ["--format", "json", str(session)])

    # Then
    assert init_result.exit_code == 0, init_result.output
    assert status_result.exit_code == 0, status_result.output


def test_v1_add_evidence_records_projects_channels_and_invalidates_freshness(
    tmp_path: Path,
) -> None:
    # Given
    session_dir = create_session(tmp_path)
    delta = session_update.parse_delta(
        json.dumps(
            {
                "set": [
                    {
                        "id": "R1",
                        "add_evidence_records": [evidence("E3", "repo-c")],
                    },
                ],
            },
        ),
    )

    # When
    result = session_update.update_session(session_dir, delta)

    # Then
    assert result.entries[0].evidence_channels == ("from-code",)
    assert len(result.entries[0].evidence_records) == 3
    assert result.protocol.material_revision == 1
    assert result.protocol.dry_sweeps_in_row == 0
    assert not result.protocol.checkpoint_since_last_material_change
    assert not result.protocol.build_contract_tested


def test_v1_add_channels_is_rejected_without_writes(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    paths = (session_dir / "ledger.json", session_dir / "protocol.json")
    before = tuple(path.read_bytes() for path in paths)
    delta = session_update.parse_delta(
        json.dumps({"set": [{"id": "R1", "add_channels": ["from-user"]}]}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="legacy-only"):
        session_update.update_session(session_dir, delta)
    assert tuple(path.read_bytes() for path in paths) == before


def test_checkpoint_uses_one_stable_user_dependency_group(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    delta = session_update.parse_delta(
        json.dumps({"checkpoint_confirm": {"ids": ["R1"], "fatigue": False}}),
    )

    # When
    first = session_update.update_session(session_dir, delta)
    second = session_update.update_session(session_dir, delta)

    # Then
    records = second.entries[0].evidence_records
    checkpoint = tuple(record for record in records if record.id == "checkpoint:user:R1")
    assert len(checkpoint) == 1
    assert checkpoint[0].independence_group == "user-dependency:R1"
    assert checkpoint[0].decision_authority == "owner"
    assert len(first.entries[0].distinct_evidence_groups) == len(second.entries[0].distinct_evidence_groups)


def test_breadth_open_world_record_is_required_for_a_dry_sweep(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    delta = session_update.parse_delta(
        json.dumps({"event": "sweep-free", "sweep_result": "dry"}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="breadth open-world"):
        session_update.update_session(session_dir, delta)


def test_stale_orientation_can_be_replaced_at_the_current_revision(tmp_path: Path) -> None:
    # Given
    session_dir = create_session(tmp_path)
    protocol_path = session_dir / "protocol.json"
    protocol = json.loads(protocol_path.read_text())
    protocol["material_revision"] = 2
    protocol["open_world_records"] = [
        {
            "sweep_id": "OW-old",
            "phase": "orientation",
            "precedes": "lens-selection",
            "interaction_cost": 0,
            "material_revision_binding": 0,
            "candidates": [],
        },
    ]
    protocol_path.write_text(json.dumps(protocol))
    replacement = {
        "sweep_id": "OW-current",
        "phase": "orientation",
        "precedes": "lens-selection",
        "interaction_cost": 0,
        "material_revision_binding": 2,
        "candidates": [],
    }

    # When
    result = session_update.update_session(
        session_dir,
        session_update.parse_delta(json.dumps({"open_world_sweep": replacement})),
    )

    # Then
    orientation = result.protocol.open_world_records[0]
    assert orientation.sweep_id == "OW-current"
    assert orientation.is_fresh(result.protocol.material_revision)
