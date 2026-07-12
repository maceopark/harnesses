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

from pydantic import ValidationError

from scripts import (
    build_contract,
    protocol_state,
    session_contracts,
    session_init,
    session_status,
    session_update,
)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
ARTIFACT_NAMES = (
    "ledger.json",
    "protocol.json",
    "questions.json",
    "transcript.md",
    "build-contract.json",
)


def snapshot_session(session_dir: Path) -> dict[str, bytes | None]:
    return {
        name: (session_dir / name).read_bytes() if (session_dir / name).is_file() else None
        for name in ARTIFACT_NAMES
    }


def probe_attempt(outcome: str) -> dict[str, JsonValue]:
    material = outcome == "material-divergence"
    return {
        "decision": {
            "probe_id": "PROBE-L0",
            "intent": "discovery",
            "selected_level": "L0",
            "target_ledger_ids": ["R1"],
            "predicate": "Observed behavior differs.",
            "contract_digest": "a" * 64,
            "sandboxable_observable": False,
            "requires_runtime_observation": False,
            "production_only": False,
            "previous_level_insufficiency": None,
            "skipped_level_reason": None,
            "execution_scope": None,
            "authorization": None,
        },
        "result": {
            "result_id": f"RESULT-{outcome}",
            "decision_id": "PROBE-L0",
            "intent": "discovery",
            "level": "L0",
            "target_ledger_ids": ["R1"],
            "contract_digest": "a" * 64,
            "producer_lineages": [
                {"producer_id": "repo", "independence_key": "repo", "kind": "repo-docs"},
                {"producer_id": "reviewer", "independence_key": "reviewer", "kind": "fresh-implementer"},
            ],
            "artifact_refs": ["artifacts/probe.json"],
            "outcome": outcome,
            "evidence_credit": 1 if material else 0,
            "completeness_credit": 0,
            "reopen_required": material,
            "gap_origin": "origin:probe" if material else None,
        },
    }
def probe_delta(
    outcome: str,
    *,
    event: str | None = None,
    additions: list[dict[str, JsonValue]] | None = None,
) -> dict[str, JsonValue]:
    attempt = probe_attempt(outcome)
    payload: dict[str, JsonValue] = {
        "probe_decision": attempt["decision"],
        "probe_attempt": attempt,
    }
    if event is not None:
        payload["event"] = event
    if additions is not None:
        payload["add"] = additions
    return payload


def build_contract_delta() -> session_update.Delta:
    return session_update.parse_delta(
        json.dumps({"build_contract_test": {"reviewer": "critic"}})
    )


def cli_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_update.main)
    return app


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
def test_duplicate_evidence_ids_raise_named_error_in_source_order() -> None:
    entry = {"evidence_records": [evidence("E1", "repo-a")]}
    additions = (
        session_contracts.claim_evidence.ClaimEvidence.model_validate_json(
            json.dumps(evidence("E2", "repo-b"))
        ),
        session_contracts.claim_evidence.ClaimEvidence.model_validate_json(
            json.dumps(evidence("E1", "repo-c"))
        ),
        session_contracts.claim_evidence.ClaimEvidence.model_validate_json(
            json.dumps(evidence("E2", "repo-d"))
        ),
    )

    with pytest.raises(session_contracts.DuplicateEvidenceIdError) as caught:
        session_contracts.merge_evidence_records(entry, additions)

    error = caught.value
    assert type(error) is session_contracts.DuplicateEvidenceIdError
    assert isinstance(error, ValueError)
    assert error.evidence_id == "E1"
    assert str(error) == "duplicate evidence record id 'E1'"

    with pytest.raises(AttributeError):
        error.evidence_id = "E3"  # type: ignore[misc]
def test_update_session_preserves_duplicate_exception_identity(tmp_path: Path) -> None:
    session_dir = create_session(tmp_path)
    delta = session_update.parse_delta(
        json.dumps({"set": [{"id": "R1", "add_evidence_records": [evidence("E1", "other")]}]})
    )
    with pytest.raises(session_contracts.DuplicateEvidenceIdError) as caught:
        session_update.update_session(session_dir, delta)
    assert caught.value.evidence_id == "E1"

@pytest.mark.parametrize(
    ("payload", "expected_cost", "expected_revision"),
    (
        ({"event": "contrarian-asked"}, 1, 0),
        (probe_delta("no-material-divergence"), 0, 0),
        (
            probe_delta(
                "material-divergence",
                additions=[
                    {
                        "id": "P1",
                        "requirement": "Probe gap",
                        "origin": "probe",
                        "status": "draft",
                        "ambiguity_score": 3,
                        "impact_weight": 5,
                        "evidence_records": [],
                    }
                ],
            ),
            0,
            1,
        ),
        (
            probe_delta(
                "no-material-divergence",
                event="contrarian-free",
            ),
            0,
            0,
        ),
    ),
)
def test_contrarian_probe_counter_is_exactly_once(
    tmp_path: Path,
    payload: dict[str, JsonValue],
    expected_cost: int,
    expected_revision: int,
) -> None:
    session_dir = create_session(tmp_path)
    payload = json.loads(json.dumps(payload))
    if "probe_attempt" in payload:
        decision = payload.pop("probe_decision")
        session_update.update_session(
            session_dir,
            session_update.parse_delta(json.dumps({"probe_decision": decision})),
        )
    before_protocol = json.loads((session_dir / "protocol.json").read_text())
    result = session_update.update_session(
        session_dir,
        session_update.parse_delta(json.dumps(payload)),
    )
    serialized_protocol = json.loads((session_dir / "protocol.json").read_text())
    assert result.protocol.contrarian_probes_run == 1
    assert serialized_protocol["contrarian_probes_run"] == 1
    assert result.protocol.interactions_used == expected_cost
    assert result.protocol.material_revision == before_protocol["material_revision"] + expected_revision


def test_duplicate_merge_preserves_nonduplicate_pydantic_validation() -> None:
    entry = {"evidence_records": [{"id": "not-a-record"}]}
    with pytest.raises(ValidationError):
        session_contracts.merge_evidence_records(entry, ())


@pytest.mark.parametrize(
    ("error_factory", "expected"),
    (
        (
            lambda: build_contract.BuildContractCompileError(
                "Build Contract",
                "unresolved placeholder",
            ),
            "cannot compile Build Contract: unresolved placeholder",
        ),
        (
            lambda: ValidationError.from_exception_data(
                "BuildContract",
                [{"type": "missing", "loc": ("schema_version",), "input": {}}],
            ),
            "cannot compile Build Contract: compiled schema validation failed",
        ),
    ),
)
def test_update_session_preserves_compiler_exception_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_factory,
    expected: str,
) -> None:
    session_dir = create_session(tmp_path)
    (session_dir / "handoff.md").write_text("# Handoff\n")
    error = error_factory()
    monkeypatch.setattr(session_update.build_contract, "compile_handoff", lambda _: (_ for _ in ()).throw(error))
    with pytest.raises(type(error)) as caught:
        session_update.update_session(session_dir, build_contract_delta())
    assert caught.value is error
    if isinstance(error, build_contract.BuildContractCompileError):
        assert str(caught.value) == expected


@pytest.mark.parametrize(
    ("error_factory", "expected"),
    (
        (
            lambda: build_contract.BuildContractCompileError(
                "Build Contract",
                "unresolved placeholder",
            ),
            "cannot compile Build Contract: unresolved placeholder",
        ),
        (
            lambda: ValidationError.from_exception_data(
                "BuildContract",
                [{"type": "missing", "loc": ("schema_version",), "input": {}}],
            ),
            "cannot compile Build Contract: compiled schema validation failed",
        ),
    ),
)
def test_cli_compiler_errors_are_exact_and_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_factory,
    expected: str,
) -> None:
    session_dir = create_session(tmp_path)
    (session_dir / "handoff.md").write_text("# Handoff\n")
    before = snapshot_session(session_dir)
    error = error_factory()
    monkeypatch.setattr(session_update.build_contract, "compile_handoff", lambda _: (_ for _ in ()).throw(error))
    result = CliRunner().invoke(
        cli_app(),
        [str(session_dir), "--delta", json.dumps({"build_contract_test": {"reviewer": "critic"}})],
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == f"error: {expected}\n"
    assert "Traceback" not in result.stderr
    assert snapshot_session(session_dir) == before


def test_snapshot_session_tracks_present_and_absent_artifacts(tmp_path: Path) -> None:
    session_dir = create_session(tmp_path)
    (session_dir / "build-contract.json").write_bytes(b"contract")
    before = snapshot_session(session_dir)
    (session_dir / "build-contract.json").unlink()
    after = snapshot_session(session_dir)
    assert before["build-contract.json"] == b"contract"
    assert after["build-contract.json"] is None


def test_cli_duplicate_rejection_is_exact_and_atomic(tmp_path: Path) -> None:
    session_dir = create_session(tmp_path)
    before = snapshot_session(session_dir)
    payload = {"set": [{"id": "R1", "add_evidence_records": [evidence("E1", "other")]}]}
    result = CliRunner().invoke(cli_app(), [str(session_dir), "--delta", json.dumps(payload)])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "error: invalid delta: duplicate evidence record id 'E1'\n"
    assert "Traceback" not in result.stderr
    assert snapshot_session(session_dir) == before


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
