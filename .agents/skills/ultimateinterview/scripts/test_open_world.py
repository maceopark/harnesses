#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
# ]
# ///

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import open_world  # noqa: E402


def candidate(
    candidate_id: str = "OW-1",
    disposition: str = "survives",
) -> open_world.OpenWorldCandidate:
    return open_world.OpenWorldCandidate.model_validate(
        {
            "candidate_id": candidate_id,
            "applicability_question": "Could retries reorder persisted decisions?",
            "falsifier": "Replay preserves decision order under one injected retry.",
            "evidence_route": "Inspect persistence code, then run the deterministic replay fixture.",
            "disposition": disposition,
            "absent_from_current_model": True,
            "implementation_changing": True,
            "origin": "origin:open-world",
            "claim_kind": "causal-hypothesis",
            "evidence_channel": "assumption",
            "source_actor": "model",
            "provenance_mode": "model-prior",
            "epistemic_authority": "hypothesis-only",
            "decision_authority": "none",
        }
    )


def sweep(
    phase: str = "orientation",
    revision: int = 4,
    candidates: tuple[open_world.OpenWorldCandidate, ...] | None = None,
) -> open_world.OpenWorldSweep:
    return open_world.OpenWorldSweep.model_validate(
        {
            "sweep_id": f"SW-{phase}-{revision}",
            "phase": phase,
            "precedes": "lens-selection" if phase == "orientation" else "dry-sweep",
            "interaction_cost": 0,
            "material_revision_binding": revision,
            "candidates": candidates if candidates is not None else (candidate(),),
        }
    )


def test_orientation_and_breadth_records_are_replayably_ordered() -> None:
    # Given: one orientation sweep and a later breadth sweep.
    orientation = sweep()
    breadth = sweep("breadth", 5, (candidate("OW-2", "dismissed"),))

    # When: the persisted history is parsed.
    history = open_world.OpenWorldHistory(records=(orientation, breadth))

    # Then: phase boundaries preserve orientation-before-lenses and breadth-before-dry.
    assert [record.precedes.value for record in history.records] == [
        "lens-selection",
        "dry-sweep",
    ]


def test_orientation_must_precede_breadth() -> None:
    # Given: a breadth record without an orientation record.
    breadth = sweep("breadth", 5)

    # When / Then: replay validation rejects the impossible order.
    with pytest.raises(ValidationError, match="orientation"):
        open_world.OpenWorldHistory(records=(breadth,))


def test_candidate_cap_is_three() -> None:
    # Given: four candidate hypotheses in one pass.
    candidates = tuple(candidate(f"OW-{number}") for number in range(1, 5))

    # When / Then: the persisted pass rejects the fourth candidate.
    with pytest.raises(ValidationError):
        sweep(candidates=candidates)


@pytest.mark.parametrize(
    "field",
    ["applicability_question", "falsifier", "evidence_route"],
)
def test_candidate_requires_actionable_question_falsifier_and_route(field: str) -> None:
    # Given: a candidate with one blank action field.
    payload = candidate().model_dump(mode="json")
    payload[field] = "  "

    # When / Then: boundary parsing fails closed.
    with pytest.raises(ValidationError):
        open_world.OpenWorldCandidate.model_validate(payload)


def test_survivor_is_absent_implementation_changing_hypothesis_only() -> None:
    # Given: a model-only candidate that is not absent from the current model.
    survivor = candidate()
    payload = survivor.model_dump(mode="json")
    payload["absent_from_current_model"] = False

    # When / Then: it cannot survive the open-world pass.
    with pytest.raises(ValidationError, match="surviving"):
        open_world.OpenWorldCandidate.model_validate(payload)

    assert survivor.origin == "origin:open-world"
    assert survivor.claim_kind == "causal-hypothesis"
    assert survivor.provenance_mode == "model-prior"
    assert survivor.epistemic_authority == "hypothesis-only"
    assert survivor.decision_authority == "none"


def test_material_revision_change_invalidates_sweep_freshness() -> None:
    # Given: a sweep bound to material revision four.
    record = sweep(revision=4)

    # When / Then: only that exact revision is fresh.
    assert record.is_fresh(4) is True
    assert record.is_fresh(5) is False


def test_unknown_fields_and_duplicate_candidate_ids_fail_closed() -> None:
    # Given: malformed boundary input and duplicate candidate identity.
    payload = candidate().model_dump(mode="json") | {"unexpected": True}

    # When / Then: both are rejected deterministically.
    with pytest.raises(ValidationError):
        open_world.OpenWorldCandidate.model_validate(payload)
    with pytest.raises(ValidationError, match="candidate_id"):
        sweep(candidates=(candidate(), candidate()))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("absent_from_current_model", "true"),
        ("absent_from_current_model", 1),
        ("implementation_changing", "false"),
        ("implementation_changing", 0),
    ],
)
def test_candidate_boolean_scalars_reject_coercion(field: str, value: str | int) -> None:
    payload = candidate().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        open_world.OpenWorldCandidate.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interaction_cost", "0"),
        ("interaction_cost", False),
        ("material_revision_binding", "4"),
        ("material_revision_binding", True),
    ],
)
def test_sweep_integer_scalars_reject_coercion(field: str, value: str | bool) -> None:
    payload = sweep().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        open_world.OpenWorldSweep.model_validate(payload)


def test_nested_candidate_instances_are_revalidated() -> None:
    tainted = candidate().model_copy(update={"absent_from_current_model": "true"})
    payload = sweep().model_dump(mode="json") | {"candidates": [tainted]}

    with pytest.raises(ValidationError):
        open_world.OpenWorldSweep.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
