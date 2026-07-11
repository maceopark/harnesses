#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pydantic import BaseModel, ValidationError

from scripts import ambiguity_ledger, protocol_state, question_score, session_update

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def ledger_payload() -> dict[str, JsonValue]:
    return {
        "id": "REQ-001",
        "requirement": "Scalar boundaries are strict",
        "ambiguity_score": 1,
        "impact_weight": 3,
    }


def protocol_payload() -> dict[str, JsonValue]:
    return {
        "depth": "minimal",
        "question_budget": 3,
        "interactions_used": 0,
        "answers_since_sweep": 0,
        "sweeps_run": 0,
        "contrarian_probes_run": 0,
        "falsification_checkpoints_run": 0,
        "lenses": {
            name: {"state": "pending"}
            for name in (
                "viewpoint",
                "domain/state",
                "goal/obstacle",
                "misuse",
                "quality",
                "controlled-language",
            )
        },
    }


def question_payload() -> dict[str, JsonValue]:
    return {
        "id": "Q-001",
        "question": "Which boundary matters?",
        "impact": 1,
        "branch_split": 1.5,
        "uncertainty_reduction": 2,
        "coverage": 2.5,
        "user_cost": 1,
        "redundancy": 0,
        "target_ids": ["REQ-001"],
    }


@pytest.mark.parametrize("field", ["ambiguity_score", "impact_weight"])
@pytest.mark.parametrize("invalid", ["1", 1.0, True])
def test_ledger_integer_fields_reject_coercion(field: str, invalid: JsonValue) -> None:
    # Given
    payload = ledger_payload()
    payload[field] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        ambiguity_ledger.LedgerEntry.model_validate(payload)


@pytest.mark.parametrize("invalid", ["true", "false", 1, 0])
def test_ledger_deferred_rejects_boolean_coercion(invalid: JsonValue) -> None:
    # Given
    payload = ledger_payload()
    payload["deferred"] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        ambiguity_ledger.LedgerEntry.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "evidence_schema_version",
        "contract_schema_version",
        "material_revision",
        "question_budget",
        "interactions_used",
        "answers_since_sweep",
        "sweeps_run",
        "dry_sweeps_in_row",
        "contrarian_probes_run",
        "falsification_checkpoints_run",
        "stagnation_escalated_at",
        "due_now_corrections",
    ],
)
@pytest.mark.parametrize("invalid", ["1", 1.0, True])
def test_protocol_integer_fields_reject_coercion(field: str, invalid: JsonValue) -> None:
    # Given
    payload = protocol_payload()
    if field == "dry_sweeps_in_row":
        payload["sweeps_run"] = 1
    if field == "stagnation_escalated_at":
        payload["residual_history"] = [1]
    payload[field] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        protocol_state.ProtocolState.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "checkpoint_since_last_material_change",
        "framing_challenged",
        "brain_dump_done",
        "build_contract_tested",
        "implementer_scout_run",
    ],
)
@pytest.mark.parametrize("invalid", ["true", "false", 1, 0])
def test_protocol_boolean_fields_reject_coercion(field: str, invalid: JsonValue) -> None:
    # Given
    payload = protocol_payload()
    payload[field] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        protocol_state.ProtocolState.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("residual_history", ["1"]),
        ("gap_count_history", ["1"]),
        ("pressure_followups_by_parent", {"REQ-001": "1"}),
    ],
)
def test_protocol_collection_scalars_reject_coercion(
    field: str,
    invalid: JsonValue,
) -> None:
    # Given
    payload = protocol_payload()
    payload[field] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        protocol_state.ProtocolState.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "impact",
        "branch_split",
        "uncertainty_reduction",
        "coverage",
        "user_cost",
        "redundancy",
    ],
)
@pytest.mark.parametrize("invalid", ["1", True, float("nan"), float("inf")])
def test_question_score_fields_reject_coercion_and_nonfinite_values(
    field: str,
    invalid: JsonValue,
) -> None:
    # Given
    payload = question_payload()
    payload[field] = invalid

    # When / Then
    with pytest.raises(ValidationError):
        question_score.QuestionCandidate.model_validate(payload)


@pytest.mark.parametrize("field", ["ambiguity_score", "impact_weight"])
@pytest.mark.parametrize("invalid", ["1", 1.0, True])
def test_set_operation_integer_fields_reject_coercion(field: str, invalid: JsonValue) -> None:
    # Given
    payload: dict[str, JsonValue] = {"id": "REQ-001", field: invalid}

    # When / Then
    with pytest.raises(ValidationError):
        session_update.SetOp.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (session_update.SetOp, {"id": "REQ-001", "deferred": "false"}),
        (session_update.CheckpointConfirm, {"ids": ["REQ-001"], "fatigue": "false"}),
        (session_update.TranscriptNote, {"title": "Question", "awaiting": "false"}),
        (session_update.Delta, {"append_history": "false"}),
    ],
)
def test_session_boolean_fields_reject_coercion(
    model: type[BaseModel],
    payload: dict[str, JsonValue],
) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_question_scores_accept_finite_integers_and_floats() -> None:
    # Given
    payload = question_payload()

    # When
    candidate = question_score.QuestionCandidate.model_validate(payload)

    # Then
    assert candidate.impact == 1.0
    assert candidate.branch_split == 1.5


def test_json_arrays_remain_compatible_with_tuple_fields() -> None:
    # Given
    protocol = protocol_payload()
    protocol["residual_history"] = [3, 1]

    # When
    entry = ambiguity_ledger.LedgerEntry.model_validate(
        {**ledger_payload(), "evidence_channels": ["from-code"]},
    )
    state = protocol_state.ProtocolState.model_validate(protocol)
    candidate = question_score.QuestionCandidate.model_validate(question_payload())
    delta = session_update.Delta.model_validate({"set": [{"id": "REQ-001"}]})

    # Then
    assert entry.evidence_channels == ("from-code",)
    assert state.residual_history == (3, 1)
    assert candidate.target_ids == ("REQ-001",)
    assert delta.set == (session_update.SetOp(id="REQ-001"),)
