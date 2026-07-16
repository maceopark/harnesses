from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from driftbench.discovery import (
    AuthorityEntry, CellReceipt, CoordinatorState, InterviewDecisionV2,
    StructuredInterviewTurnV2, authority_register, fidelity, merge_receipt,
    pareto_archive, schedule_cells, select_option, summarize_candidate,
    validate_turn_sequence, verify_authority_projection, write_coordinator_state,
)


def _decision(identity: str = "DEC-1") -> dict[str, object]:
    return {
        "decision_id": identity, "question": "Which boundary?",
        "options": [
            {"option_id": "a", "label": "A", "normative_statement": "Use A.",
             "compatible": True},
            {"option_id": "b", "label": "B", "normative_statement": "Use B.",
             "compatible": True},
        ],
        "recommended_option_id": "a", "recommendation_rationale": "Least surprise",
        "impact_boundary": "CLI behavior",
    }


def test_turn_v2_supports_zero_question_completion_and_enforces_shape() -> None:
    complete = StructuredInterviewTurnV2.model_validate({
        "schema": "StructuredInterviewTurn.v2", "action": "complete", "decisions": [],
        "contract_draft": {"requirements": ["REQ-1"]},
    })
    assert validate_turn_sequence((complete,)) == (complete,)
    with pytest.raises(ValidationError, match="at least two compatible"):
        value = _decision()
        value["options"][1]["compatible"] = False  # type: ignore[index]
        InterviewDecisionV2.model_validate(value)
    with pytest.raises(ValidationError):
        value = _decision()
        value["options"].extend([value["options"][0], value["options"][0], value["options"][0]])  # type: ignore[union-attr,index]
        InterviewDecisionV2.model_validate(value)


def test_sequence_limits_total_decisions_and_requires_completion() -> None:
    asks = [StructuredInterviewTurnV2.model_validate({
        "schema": "StructuredInterviewTurn.v2", "action": "ask",
        "decisions": [_decision(f"DEC-{index}")],
    }) for index in range(7)]
    complete = StructuredInterviewTurnV2(action="complete", contract_draft={"x": 1})
    with pytest.raises(ValueError, match="limit"):
        validate_turn_sequence((*asks, complete))


def test_seeded_selection_is_stable_and_authority_projection_is_tamper_evident() -> None:
    decision = InterviewDecisionV2.model_validate(_decision())
    first = select_option("seed", "g00-c00", "bookmarks", 1, decision)
    assert first == select_option("seed", "g00-c00", "bookmarks", 1, decision)
    assert first.option_id != select_option(
        "seed", "g00-c00", "bookmarks", 2, decision
    ).option_id
    register = authority_register((first,))
    verify_authority_projection(register, ({
        "authority_id": first.authority_id, "statement": first.normative_statement,
    },))
    with pytest.raises(ValueError, match="projection"):
        verify_authority_projection(register, ({
            "authority_id": first.authority_id, "statement": "tampered",
        },))


def test_scheduler_is_repetition_case_candidate_round_robin_and_complete() -> None:
    cells = schedule_cells(("c0", "c1"), (("train", ("a", "b")),
                                                  ("validation", ("v",))), 2)
    assert [(row.repetition, row.case_id, row.candidate_id) for row in cells[:4]] == [
        (1, "a", "c0"), (1, "a", "c1"), (1, "b", "c0"), (1, "b", "c1")]
    assert len(cells) == 12
    assert len({row.cell_id for row in cells}) == 12
    assert [row.partition for row in cells[:8]] == ["train"] * 8


def test_coordinator_state_merges_atomic_receipts_and_binds_resume(tmp_path) -> None:
    state = CoordinatorState(manifest_digest="a" * 64, cells={})
    receipt = CellReceipt(cell_id="cell", input_digest="b" * 64, status="completed",
                          attempts=1, artifact_hashes={"postmortem.md": "c" * 64})
    state = merge_receipt(state, receipt)
    assert state.reusable("cell", "b" * 64)
    assert not state.reusable("cell", "d" * 64)
    path = tmp_path / "state.json"
    write_coordinator_state(path, state)
    assert json.loads(path.read_text())["cells"]["cell"]["status"] == "completed"


def test_fidelity_and_three_axis_pareto() -> None:
    assert fidelity(4, 3, 2) == .8
    assert fidelity(4, 3, 2, authority_expansion=True) == 0
    strong_large = summarize_candidate("strong", (1, 1), (2, 2), skill_bytes=200)
    lean = summarize_candidate("lean", (.8, .8), (1, 1), skill_bytes=100)
    dominated = summarize_candidate("dominated", (.5, .5), (3, 3), skill_bytes=300)
    assert [row.candidate_id for row in pareto_archive((dominated, strong_large, lean))] == [
        "strong", "lean"]
