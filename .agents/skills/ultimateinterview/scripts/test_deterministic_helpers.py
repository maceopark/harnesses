#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/test_deterministic_helpers.py
# 3. Or make executable and run:
#      chmod +x test_deterministic_helpers.py && ./test_deterministic_helpers.py
# ──────────────────

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import typer
from pydantic import ValidationError
from typer.testing import CliRunner

from scripts import atomic_write, ambiguity_ledger, implementation_gate, protocol_state, question_score, session_status, session_update, verification_lint
from scripts.ambiguity_ledger import parse_entries, summarize_ambiguity
from scripts.protocol_state import parse_state, summarize_protocol
from scripts.question_score import parse_questions, rank_questions


def test_deferred_gaps_are_excluded_from_ambiguity() -> None:
    raw = json.dumps(
        {
            "requirements": [
                {
                    "id": "REQ-1",
                    "requirement": "Settled behavior",
                    "ambiguity_score": 0,
                    "impact_weight": 5,
                    "status": "accepted",
                    "evidence_channels": ["from-user"],
                },
                {
                    "id": "REQ-2",
                    "requirement": "Deferred migration choice",
                    "ambiguity_score": 3,
                    "impact_weight": 5,
                    "status": "deferred",
                },
            ],
        },
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.ambiguity_percent == 0
    assert summary.active_count == 1
    assert summary.deferred_count == 1
    assert summary.handoff_ready


def test_score_two_blocks_handoff_even_when_aggregate_is_low() -> None:
    settled = [
        {
            "id": f"REQ-{index}",
            "requirement": "Settled low-risk detail",
            "ambiguity_score": 0,
            "impact_weight": 5,
            "status": "accepted",
        }
        for index in range(1, 20)
    ]
    raw = json.dumps(
        {
            "requirements": [
                *settled,
                {
                    "id": "REQ-risk",
                    "requirement": "Implementation branch remains",
                    "ambiguity_score": 2,
                    "impact_weight": 1,
                    "status": "blocked",
                },
            ],
        },
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.ambiguity_percent < 5
    assert not summary.handoff_ready
    assert "active score 2 gaps remain: REQ-risk" in summary.blockers


def test_weight_five_score_one_draft_blocks_even_when_no_score_two_or_three_exists() -> None:
    lone_gap = {
        "id": "REQ-lone",
        "requirement": "Accepted assumption, no settled entries around it",
        "ambiguity_score": 1,
        "impact_weight": 5,
        "status": "draft",
    }

    summary = summarize_ambiguity(parse_entries(json.dumps([lone_gap])))

    assert summary.ambiguity_percent > 30
    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-lone",)
    assert summary.residual == 5


def test_untriangulated_critical_settlement_blocks_handoff() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "requirement": "Critical requirement settled on one channel",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "triangulated",
                "evidence_channels": ["from-user"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-crit",)
    assert any("without triangulation" in blocker for blocker in summary.blockers)


def test_two_distinct_channels_triangulate_critical_settlement() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "triangulated",
                "channels": "code, from-user",
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.handoff_ready
    assert summary.triangulation_violations == ()


def test_assumption_channel_does_not_count_toward_triangulation() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "draft",
                "evidence_channels": ["from-user", "assumption"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-crit",)


def test_duplicate_channel_spellings_count_once() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "draft",
                "evidence_channels": ["code", "from-code"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-crit",)


def test_explicit_accepted_status_allows_single_source_critical() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "accepted",
                "evidence_channels": ["from-user"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.handoff_ready
    assert summary.triangulation_violations == ()


def test_explicit_accepted_status_allows_single_source_score_one_critical() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 1,
                "impact_weight": 5,
                "status": "accepted",
                "evidence_channels": ["from-user"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.handoff_ready
    assert summary.triangulation_violations == ()


def test_unknown_evidence_channel_is_rejected() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "draft",
                "evidence_channels": ["from-user", "vibes"],
            },
        ],
    )

    with pytest.raises(ValidationError, match="unknown evidence channel"):
        parse_entries(raw)


def test_misspelled_assumption_channel_is_rejected_not_counted() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "draft",
                "evidence_channels": ["from-user", "assumptions"],
            },
        ],
    )

    with pytest.raises(ValidationError, match="unknown evidence channel"):
        parse_entries(raw)


def test_non_critical_settlement_needs_no_triangulation() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-minor",
                "ambiguity_score": 0,
                "impact_weight": 3,
                "status": "draft",
                "evidence_channels": ["from-user"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.handoff_ready
    assert summary.triangulation_violations == ()


def test_top_drivers_sort_by_weighted_contribution() -> None:
    raw = json.dumps(
        [
            {"id": "B", "ambiguity_score": 1, "impact_weight": 5},
            {"id": "A", "ambiguity_score": 3, "impact_weight": 2},
            {"id": "C", "ambiguity_score": 2, "impact_weight": 3},
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw), top=2)

    assert [driver.id for driver in summary.top_drivers] == ["A", "C"]


def test_question_score_formula_and_ranking() -> None:
    raw = json.dumps(
        {
            "questions": [
                {
                    "id": "Q-low",
                    "question": "Low value?",
                    "impact": 2,
                    "branch_split": 2,
                    "uncertainty_reduction": 2,
                    "coverage": 2,
                    "user_cost": 3,
                    "redundancy": 1,
                },
                {
                    "id": "Q-high",
                    "question": "High value?",
                    "impact": 5,
                    "branch_split": 4,
                    "uncertainty_reduction": 5,
                    "coverage": 3,
                    "user_cost": 1,
                    "redundancy": 0,
                },
            ],
        },
    )

    ranked = rank_questions(parse_questions(raw), top=1)

    assert ranked[0].id == "Q-high"
    assert ranked[0].score == 150


def make_protocol(**overrides: object) -> str:
    lenses = {
        "viewpoint": {"state": "done", "artifact": "ViewpointMatrix"},
        "domain/state": {"state": "skipped", "reason": "no lifecycle or vocabulary drift"},
        "goal/obstacle": {"state": "done", "artifact": "GoalObstacleMap"},
        "misuse": {"state": "skipped", "reason": "no destructive or security-sensitive flow"},
        "quality": {"state": "done", "artifact": "QualityScenarioSet"},
        "controlled-language": {"state": "done", "artifact": "ControlledAcceptanceCriteria"},
    }
    payload: dict[str, object] = {
        "depth": "focused",
        "question_budget": 12,
        "interactions_used": 3,
        "answers_since_sweep": 1,
        "sweeps_run": 2,
        "dry_sweeps_in_row": 2,
        "contrarian_probes_run": 1,
        "falsification_checkpoints_run": 1,
        "checkpoint_since_last_material_change": True,
        "framing_challenged": True,
        "brain_dump_done": True,
        "build_contract_tested": True,
        "build_contract_digest": "test-digest",
        "build_contract_reviewer": "critic",
        "lenses": lenses,
        "residual_history": [20, 12, 6],
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_protocol_ready_when_all_obligations_met() -> None:
    summary = summarize_protocol(parse_state(make_protocol()))

    assert summary.protocol_ready
    assert summary.handoff_blockers == ()
    assert summary.interview_obligations == ()


def test_tested_contract_requires_digest_and_reviewer() -> None:
    summary = summarize_protocol(
        parse_state(make_protocol(build_contract_digest="", build_contract_reviewer="")),
    )
    assert not summary.protocol_ready
    assert any("digest" in blocker for blocker in summary.handoff_blockers)


def test_missing_contrarian_probe_blocks_protocol() -> None:
    summary = summarize_protocol(parse_state(make_protocol(contrarian_probes_run=0)))

    assert not summary.protocol_ready
    assert any("contrarian" in blocker for blocker in summary.handoff_blockers)


def test_stale_checkpoint_blocks_protocol() -> None:
    summary = summarize_protocol(
        parse_state(make_protocol(checkpoint_since_last_material_change=False)),
    )

    assert not summary.protocol_ready
    assert any("material ledger change" in blocker for blocker in summary.handoff_blockers)


def test_untested_build_contract_blocks_protocol() -> None:
    summary = summarize_protocol(parse_state(make_protocol(build_contract_tested=False)))

    assert not summary.protocol_ready
    assert any("fresh-implementer" in blocker for blocker in summary.handoff_blockers)


def test_triggered_but_incomplete_lens_blocks_protocol() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["misuse"] = {"state": "triggered"}

    summary = summarize_protocol(parse_state(make_protocol(lenses=lenses)))

    assert not summary.protocol_ready
    assert any("misuse" in blocker for blocker in summary.handoff_blockers)


def test_done_lens_without_typed_artifact_blocks_protocol() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["quality"] = {"state": "done"}

    summary = summarize_protocol(parse_state(make_protocol(lenses=lenses)))

    assert not summary.protocol_ready
    assert any("quality" in blocker and "QualityScenarioSet" in blocker for blocker in summary.handoff_blockers)


def test_done_lens_with_wrong_typed_artifact_blocks_protocol() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["quality"] = {"state": "done", "artifact": "ViewpointMatrix"}

    summary = summarize_protocol(parse_state(make_protocol(lenses=lenses)))

    assert not summary.protocol_ready
    assert any("quality" in blocker and "QualityScenarioSet" in blocker for blocker in summary.handoff_blockers)


def test_non_done_lens_rejects_stale_artifact() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["quality"] = {
        "state": "skipped",
        "reason": "not applicable",
        "artifact": "QualityScenarioSet",
    }

    with pytest.raises(ValidationError, match="artifact is only valid for a done lens"):
        parse_state(make_protocol(lenses=lenses))


def test_two_consecutive_dry_sweeps_are_required_for_handoff() -> None:
    summary = summarize_protocol(parse_state(make_protocol(dry_sweeps_in_row=1)))

    assert not summary.protocol_ready
    assert any("two consecutive dry" in blocker for blocker in summary.handoff_blockers)


def test_dry_sweep_streak_cannot_exceed_total_sweeps() -> None:
    with pytest.raises(ValidationError, match="cannot exceed sweeps_run"):
        parse_state(make_protocol(sweeps_run=1, dry_sweeps_in_row=2))


def test_pending_lens_parses_without_reason_but_blocks_handoff() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["misuse"] = {"state": "pending"}

    summary = summarize_protocol(parse_state(make_protocol(lenses=lenses)))

    assert not summary.protocol_ready
    assert any(
        "undecided" in blocker and "misuse" in blocker for blocker in summary.handoff_blockers
    )


def test_pending_and_triggered_lenses_block_separately() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["misuse"] = {"state": "pending"}
    lenses["quality"] = {"state": "triggered"}

    summary = summarize_protocol(parse_state(make_protocol(lenses=lenses)))

    assert any("undecided" in blocker and "misuse" in blocker for blocker in summary.handoff_blockers)
    assert any("not completed" in blocker and "quality" in blocker for blocker in summary.handoff_blockers)


def test_nested_channel_error_surfaces_over_union_noise() -> None:
    from scripts.ambiguity_ledger import summarize_validation_error

    raw = json.dumps(
        {"entries": [
            {"id": "R1", "ambiguity_score": 0, "impact_weight": 5,
             "status": "Triangulated", "channels": ["gut-feeling"]},
        ]},
    )

    with pytest.raises(ValidationError) as excinfo:
        parse_entries(raw)
    message = summarize_validation_error(excinfo.value)

    assert "gut-feeling" in message
    assert "should be a valid array" not in message


def test_protocol_ready_no_has_no_false_parenthetical() -> None:
    from scripts.protocol_state import summary_as_markdown

    summary = summarize_protocol(parse_state(make_protocol(build_contract_tested=False)))
    rendered = summary_as_markdown(summary)

    assert "- Protocol ready: no" in rendered
    assert "no (all pre-handoff protocol obligations met)" not in rendered


def test_entry_origin_field_is_accepted_and_optional() -> None:
    raw = json.dumps(
        [
            {"id": "R1", "ambiguity_score": 0, "impact_weight": 3,
             "status": "Accepted", "channels": "from-user", "origin": "checkpoint"},
            {"id": "R2", "ambiguity_score": 1, "impact_weight": 1,
             "status": "Draft", "channels": "from-code"},
        ],
    )

    entries = parse_entries(raw)

    assert entries[0].origin == "checkpoint"
    assert entries[1].origin == ""


def test_due_now_corrections_field_accepted_and_bounded() -> None:
    summary = summarize_protocol(parse_state(make_protocol(due_now_corrections=2)))
    assert summary.protocol_ready

    with pytest.raises(ValidationError):
        parse_state(make_protocol(due_now_corrections=-1))


def test_unknown_lens_state_is_rejected() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["misuse"] = {"state": "maybe"}

    with pytest.raises(ValidationError):
        parse_state(make_protocol(lenses=lenses))


def test_budget_exhaustion_is_an_interview_obligation_not_a_blocker() -> None:
    summary = summarize_protocol(parse_state(make_protocol(interactions_used=12)))

    assert summary.protocol_ready
    assert any("budget exhausted" in obligation for obligation in summary.interview_obligations)


def test_sweep_overdue_after_four_answers() -> None:
    summary = summarize_protocol(parse_state(make_protocol(answers_since_sweep=4)))

    assert any("sweep overdue" in obligation for obligation in summary.interview_obligations)


def test_stagnation_flagged_after_two_flat_rounds() -> None:
    summary = summarize_protocol(parse_state(make_protocol(residual_history=[9, 9, 9])))

    assert any("stagnation" in obligation for obligation in summary.interview_obligations)


def test_dropping_residual_is_not_stagnation() -> None:
    summary = summarize_protocol(parse_state(make_protocol(residual_history=[9, 9, 8])))

    assert summary.interview_obligations == ()


def test_brain_dump_waiver_substitutes_for_brain_dump() -> None:
    summary = summarize_protocol(
        parse_state(
            make_protocol(
                brain_dump_done=False,
                brain_dump_waiver="request already contained a complete narrative",
            ),
        ),
    )

    assert summary.protocol_ready


def test_missing_brain_dump_without_waiver_blocks_protocol() -> None:
    summary = summarize_protocol(parse_state(make_protocol(brain_dump_done=False)))

    assert not summary.protocol_ready
    assert any("brain-dump" in blocker for blocker in summary.handoff_blockers)


def test_stagnation_does_not_refire_after_escalation() -> None:
    summary = summarize_protocol(
        parse_state(make_protocol(residual_history=[9, 9, 9], stagnation_escalated_at=3)),
    )

    assert summary.interview_obligations == ()


def test_stagnation_refires_on_new_flat_rounds_after_escalation() -> None:
    summary = summarize_protocol(
        parse_state(
            make_protocol(residual_history=[9, 9, 9, 8, 8, 8], stagnation_escalated_at=3),
        ),
    )

    assert any("stagnation" in obligation for obligation in summary.interview_obligations)


def test_unknown_top_level_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_state(make_protocol(residual_hist0ry=[9, 9, 9]))


def test_unknown_lens_record_field_is_rejected() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["quality"] = {"state": "done", "vibes": "good"}

    with pytest.raises(ValidationError):
        parse_state(make_protocol(lenses=lenses))


def test_unknown_lens_name_is_rejected() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["vibes"] = {"state": "done"}

    with pytest.raises(ValidationError, match="unknown lens name"):
        parse_state(make_protocol(lenses=lenses))


def test_missing_lens_decision_is_rejected() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    del lenses["quality"]

    with pytest.raises(ValidationError, match="missing lens decision"):
        parse_state(make_protocol(lenses=lenses))


def test_skipped_lens_without_reason_is_rejected() -> None:
    lenses = json.loads(make_protocol())["lenses"]
    lenses["misuse"] = {"state": "skipped"}

    with pytest.raises(ValidationError, match="skip reason"):
        parse_state(make_protocol(lenses=lenses))


# ─── Fail-closed document parsing (REQ-1..3, REQ-12) ───


def test_unknown_top_level_ledger_key_is_rejected() -> None:
    raw = json.dumps({"items": [{"id": "G", "ambiguity_score": 3, "impact_weight": 5}]})

    with pytest.raises(ValidationError):
        parse_entries(raw)


def test_empty_ledger_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="no entries"):
        parse_entries("[]")


def test_all_sections_empty_is_a_zero_entry_error() -> None:
    raw = json.dumps({"requirements": [], "gaps": [], "entries": [], "ledger": []})

    with pytest.raises(ValueError, match="no entries"):
        parse_entries(raw)


def test_multiple_populated_ledger_sections_are_rejected() -> None:
    entry = {"id": "A", "ambiguity_score": 0, "impact_weight": 2}
    gap = {"id": "B", "ambiguity_score": 3, "impact_weight": 5}
    raw = json.dumps({"requirements": [entry], "gaps": [gap]})

    with pytest.raises(ValueError, match="multiple populated sections"):
        parse_entries(raw)


def test_duplicate_ledger_ids_are_rejected() -> None:
    raw = json.dumps(
        [
            {"id": "REQ-1", "ambiguity_score": 0, "impact_weight": 2},
            {"id": "REQ-1", "ambiguity_score": 2, "impact_weight": 3},
        ],
    )

    with pytest.raises(ValueError, match="duplicate entry id"):
        parse_entries(raw)


def test_unknown_question_document_key_is_rejected() -> None:
    candidate = {
        "id": "Q1",
        "question": "?",
        "impact": 3,
        "branch_split": 3,
        "uncertainty_reduction": 3,
        "coverage": 3,
        "user_cost": 1,
        "redundancy": 0,
    }

    with pytest.raises(ValidationError):
        parse_questions(json.dumps({"question": [candidate]}))


def test_empty_question_document_is_rejected() -> None:
    with pytest.raises(ValueError, match="no question candidates"):
        parse_questions(json.dumps({"questions": []}))


def test_dual_populated_question_sections_are_rejected() -> None:
    candidate = {
        "id": "Q1",
        "question": "?",
        "impact": 3,
        "branch_split": 3,
        "uncertainty_reduction": 3,
        "coverage": 3,
        "user_cost": 1,
        "redundancy": 0,
    }
    other = {**candidate, "id": "Q2"}
    raw = json.dumps({"questions": [candidate], "candidates": [other]})

    with pytest.raises(ValueError, match="both 'questions' and 'candidates'"):
        parse_questions(raw)


def test_duplicate_question_ids_are_rejected() -> None:
    candidate = {
        "id": "Q1",
        "question": "?",
        "impact": 3,
        "branch_split": 3,
        "uncertainty_reduction": 3,
        "coverage": 3,
        "user_cost": 1,
        "redundancy": 0,
    }

    with pytest.raises(ValueError, match="duplicate question id"):
        parse_questions(json.dumps([candidate, candidate]))


# ─── Status vocabulary and waiver boundaries (REQ-4..6) ───


def test_unknown_status_is_rejected() -> None:
    raw = json.dumps(
        [{"id": "R", "ambiguity_score": 0, "impact_weight": 2, "status": "wontfix-lol"}],
    )

    with pytest.raises(ValidationError, match="unknown status"):
        parse_entries(raw)


def test_accepted_critical_with_zero_channels_blocks_handoff() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "accepted",
                "evidence_channels": [],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-crit",)


def test_accepted_critical_with_assumption_only_blocks_handoff() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-crit",
                "ambiguity_score": 0,
                "impact_weight": 5,
                "status": "accepted",
                "evidence_channels": ["assumption"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-crit",)


def test_contested_entries_are_surfaced_before_composite_gate() -> None:
    raw = json.dumps(
        [
            {
                "id": "REQ-fight",
                "ambiguity_score": 1,
                "impact_weight": 3,
                "status": "Contested",
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.contested == ("REQ-fight",)
    assert summary.handoff_ready


# ─── Protocol cross-field guards (REQ-7, REQ-8, REQ-13) ───


def test_escalation_marker_beyond_history_is_rejected() -> None:
    with pytest.raises(ValidationError, match="stagnation_escalated_at"):
        parse_state(make_protocol(residual_history=[9, 9, 9], stagnation_escalated_at=99))


def test_budget_over_depth_cap_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exceeds the minimal"):
        parse_state(make_protocol(depth="minimal", question_budget=999))


def test_budget_over_cap_with_extension_reason_is_accepted() -> None:
    summary = summarize_protocol(
        parse_state(
            make_protocol(
                question_budget=15,
                budget_extension_reason="user extended after budget-exhaustion prompt",
            ),
        ),
    )

    assert summary.question_budget == 15


def test_budget_exactly_at_cap_is_accepted() -> None:
    summary = summarize_protocol(parse_state(make_protocol(depth="full", question_budget=20)))

    assert summary.question_budget == 20


def test_residual_history_lag_is_an_obligation() -> None:
    summary = summarize_protocol(
        parse_state(make_protocol(interactions_used=5, residual_history=[20, 12, 6])),
    )

    assert any("residual_history lags" in item for item in summary.interview_obligations)


def test_residual_history_lag_of_one_is_tolerated() -> None:
    summary = summarize_protocol(
        parse_state(make_protocol(interactions_used=4, residual_history=[20, 12, 6])),
    )

    assert not any("residual_history lags" in item for item in summary.interview_obligations)


# ─── Stagnation vs productive divergence (REQ-10) ───


def test_rising_residual_with_new_gaps_is_not_stagnation() -> None:
    summary = summarize_protocol(
        parse_state(
            make_protocol(residual_history=[5, 9, 14], gap_count_history=[4, 6, 9]),
        ),
    )

    assert not any("stagnation" in item for item in summary.interview_obligations)


def test_flat_residual_with_flat_gap_count_is_stagnation() -> None:
    summary = summarize_protocol(
        parse_state(
            make_protocol(residual_history=[9, 9, 9], gap_count_history=[4, 4, 4]),
        ),
    )

    assert any("stagnation" in item for item in summary.interview_obligations)


def test_flat_residual_without_gap_history_still_fires_stagnation() -> None:
    summary = summarize_protocol(parse_state(make_protocol(residual_history=[9, 9, 9])))

    assert any("stagnation" in item for item in summary.interview_obligations)


# ─── CLI layer (REQ-9) ───


def make_app(command: object) -> typer.Typer:
    app = typer.Typer()
    app.command()(command)
    return app


CLI_RUNNER = CliRunner()


def test_cli_malformed_json_is_a_one_line_actionable_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    result = CLI_RUNNER.invoke(make_app(ambiguity_ledger.main), [str(bad)])

    assert result.exit_code != 0
    assert "invalid ledger JSON" in result.output
    assert "Traceback" not in result.output


def test_cli_unknown_status_is_actionable(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps([{"id": "R", "ambiguity_score": 0, "impact_weight": 2, "status": "vibes"}]),
        encoding="utf-8",
    )

    result = CLI_RUNNER.invoke(make_app(ambiguity_ledger.main), [str(ledger)])

    assert result.exit_code != 0
    assert "unknown status" in result.output


def test_cli_directory_path_is_rejected(tmp_path: Path) -> None:
    for command in (ambiguity_ledger.main, protocol_state.main, question_score.main):
        result = CLI_RUNNER.invoke(make_app(command), [str(tmp_path)])

        assert result.exit_code != 0
        assert "not a file" in result.output


def test_cli_empty_question_document_is_actionable(tmp_path: Path) -> None:
    doc = tmp_path / "questions.json"
    doc.write_text(json.dumps({"questions": []}), encoding="utf-8")

    result = CLI_RUNNER.invoke(make_app(question_score.main), [str(doc)])

    assert result.exit_code != 0
    assert "no question candidates" in result.output


def test_cli_protocol_budget_cap_violation_is_actionable(tmp_path: Path) -> None:
    doc = tmp_path / "protocol.json"
    doc.write_text(make_protocol(depth="minimal", question_budget=999), encoding="utf-8")

    result = CLI_RUNNER.invoke(make_app(protocol_state.main), [str(doc)])

    assert result.exit_code != 0
    assert "invalid protocol JSON" in result.output


def test_cli_valid_ledger_still_renders(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps([{"id": "R", "ambiguity_score": 1, "impact_weight": 3, "status": "draft"}]),
        encoding="utf-8",
    )

    result = CLI_RUNNER.invoke(
        make_app(ambiguity_ledger.main),
        [str(ledger), "--format", "json"],
    )

    assert result.exit_code == 0
    assert '"handoff_ready": true' in result.output


def test_triangulation_warning_fires_on_thin_weight5_score1_draft() -> None:
    # The exact g15 shape from the first real interview: weight-5 hard
    # constraint parked at score 1 on one channel, status Draft.
    raw = json.dumps(
        [
            {
                "id": "g15",
                "ambiguity_score": 1,
                "impact_weight": 5,
                "status": "Draft",
                "evidence_channels": ["from-code"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert len(summary.triangulation_warnings) == 1
    assert "g15" in summary.triangulation_warnings[0]
    assert "from-code" in summary.triangulation_warnings[0]
    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("g15",)
    assert summary.residual == 5


def test_triangulation_warning_does_not_fire_outside_the_exact_shape() -> None:
    raw = json.dumps(
        [
            {"id": "ok-accepted", "ambiguity_score": 1, "impact_weight": 5,
             "status": "Accepted", "evidence_channels": ["from-user"]},
            {"id": "ok-deferred", "ambiguity_score": 1, "impact_weight": 5,
             "status": "Deferred", "deferred": True, "evidence_channels": ["from-code"]},
            {"id": "ok-two-channels", "ambiguity_score": 1, "impact_weight": 5,
             "status": "Draft", "evidence_channels": ["from-code", "from-user"]},
            {"id": "ok-score-zero", "ambiguity_score": 0, "impact_weight": 5,
             "status": "Accepted", "evidence_channels": ["from-user"]},
            {"id": "ok-weight-three", "ambiguity_score": 1, "impact_weight": 3,
             "status": "Draft", "evidence_channels": ["from-code"]},
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.triangulation_warnings == ()


def test_triangulation_warning_ignores_assumption_channel() -> None:
    raw = json.dumps(
        [
            {
                "id": "g-thin",
                "ambiguity_score": 1,
                "impact_weight": 5,
                "status": "Draft",
                "evidence_channels": ["assumption"],
            },
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert len(summary.triangulation_warnings) == 1
    assert "no non-assumption evidence channel" in summary.triangulation_warnings[0]


def test_triangulation_warnings_render_in_both_formats() -> None:
    raw = json.dumps(
        [
            {"id": "g15", "ambiguity_score": 1, "impact_weight": 5,
             "status": "Draft", "evidence_channels": ["from-code"]},
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))
    markdown = ambiguity_ledger.summary_as_markdown(summary)
    payload = json.loads(ambiguity_ledger.summary_as_json(summary))

    assert "### Critical Triangulation Findings" in markdown
    assert any("g15" in line for line in markdown.splitlines() if line.startswith("- "))
    assert any("g15" in warning for warning in payload["triangulation_warnings"])


def test_triangulation_warnings_absent_when_clean() -> None:
    raw = json.dumps(
        [
            {"id": "R1", "ambiguity_score": 0, "impact_weight": 3,
             "status": "Accepted", "evidence_channels": ["from-user"]},
        ],
    )

    summary = summarize_ambiguity(parse_entries(raw))

    assert summary.triangulation_warnings == ()
    assert "Triangulation" not in ambiguity_ledger.summary_as_markdown(summary)
    assert "triangulation_warnings" not in json.loads(ambiguity_ledger.summary_as_json(summary))


# ─── Combined status runner (L2: session_status.py) ───


def make_ready_ledger() -> str:
    return json.dumps(
        [
            {"id": "R1", "ambiguity_score": 0, "impact_weight": 5,
             "status": "accepted", "evidence_channels": ["from-user"]},
        ],
    )


def write_session(
    tmp_path: Path,
    *,
    ledger: str | None = None,
    protocol: str | None = None,
) -> Path:
    (tmp_path / "ledger.json").write_text(
        ledger if ledger is not None else make_ready_ledger(), encoding="utf-8",
    )
    (tmp_path / "protocol.json").write_text(
        protocol if protocol is not None else make_protocol(), encoding="utf-8",
    )
    return tmp_path


def combined_ready_line(output: str) -> str:
    # The dedicated combined line; distinct from "- Handoff ready:" and
    # "- Protocol ready:" so substring assertions cannot false-pass.
    return next(line for line in output.splitlines() if line.startswith("- interview_converged:"))


def test_session_status_happy_path_renders_combined_dashboard(tmp_path: Path) -> None:
    session = write_session(tmp_path)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code == 0
    assert "## Ambiguity Dashboard" in result.output
    assert "## Protocol Dashboard" in result.output
    assert combined_ready_line(result.output).startswith("- interview_converged: yes")


def test_session_status_invalid_ledger_names_the_file(tmp_path: Path) -> None:
    session = write_session(tmp_path, ledger="{not json")

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code != 0
    assert "ledger.json" in result.output
    assert "Traceback" not in result.output


def test_session_status_invalid_protocol_names_the_file(tmp_path: Path) -> None:
    session = write_session(
        tmp_path, protocol=make_protocol(depth="minimal", question_budget=999),
    )

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code != 0
    assert "protocol.json" in result.output
    assert "Traceback" not in result.output


def test_session_status_missing_ledger_file_is_actionable(tmp_path: Path) -> None:
    (tmp_path / "protocol.json").write_text(make_protocol(), encoding="utf-8")

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(tmp_path)])

    assert result.exit_code != 0
    assert "ledger.json" in result.output


def test_session_status_missing_directory_is_actionable(tmp_path: Path) -> None:
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(tmp_path / "nope")])

    assert result.exit_code != 0
    assert "session directory" in result.output


def test_session_status_requires_directory_or_both_flags(tmp_path: Path) -> None:
    session = write_session(tmp_path)

    result = CLI_RUNNER.invoke(
        make_app(session_status.main), ["--ledger", str(session / "ledger.json")],
    )

    assert result.exit_code != 0
    assert "--protocol" in result.output


def test_session_status_explicit_flags_without_directory(tmp_path: Path) -> None:
    ledger = tmp_path / "my-ledger.json"
    protocol = tmp_path / "my-protocol.json"
    ledger.write_text(make_ready_ledger(), encoding="utf-8")
    protocol.write_text(make_protocol(), encoding="utf-8")

    result = CLI_RUNNER.invoke(
        make_app(session_status.main),
        ["--ledger", str(ledger), "--protocol", str(protocol)],
    )

    assert result.exit_code == 0
    assert combined_ready_line(result.output).startswith("- interview_converged: yes")


def test_session_status_ready_with_only_build_contract_blocker(tmp_path: Path) -> None:
    # Mirrors the documented stop condition: the Build Contract is drafted
    # and tested inside the Handoff sequence, so it alone does not veto.
    session = write_session(tmp_path, protocol=make_protocol(build_contract_tested=False))

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code == 0
    assert combined_ready_line(result.output).startswith("- interview_converged: yes")


def test_session_status_not_ready_with_other_protocol_blocker(tmp_path: Path) -> None:
    session = write_session(
        tmp_path,
        protocol=make_protocol(build_contract_tested=False, contrarian_probes_run=0),
    )

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code == 0
    assert combined_ready_line(result.output).startswith("- interview_converged: no")


def test_session_status_not_ready_when_ledger_blocks(tmp_path: Path) -> None:
    blocked = json.dumps([{"id": "R1", "ambiguity_score": 3, "impact_weight": 5}])
    session = write_session(tmp_path, ledger=blocked)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code == 0
    assert combined_ready_line(result.output).startswith("- interview_converged: no")


def test_session_status_json_format_combines_both_payloads(tmp_path: Path) -> None:
    session = write_session(tmp_path)

    result = CLI_RUNNER.invoke(
        make_app(session_status.main), [str(session), "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["interview_converged"] is True
    assert payload["ledger"]["handoff_ready"] is True
    assert payload["protocol"]["protocol_ready"] is True


def test_session_status_surfaces_critical_triangulation_findings(tmp_path: Path) -> None:
    thin = json.dumps(
        [
            {"id": "g15", "ambiguity_score": 1, "impact_weight": 5,
             "status": "Draft", "evidence_channels": ["from-code"]},
        ],
    )
    session = write_session(tmp_path, ledger=thin)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session)])

    assert result.exit_code == 0
    assert "### Critical Triangulation Findings" in result.output
    assert "g15" in result.output


# ─── session_update.py (L2: one-call bookkeeping delta writer) ───


def make_session(tmp_path: Path, **protocol_overrides: object) -> Path:
    session = tmp_path / "session"
    session.mkdir()
    ledger = {
        "entries": [
            {
                "id": "g1",
                "requirement": "open gap",
                "ambiguity_score": 2,
                "impact_weight": 3,
                "status": "draft",
                "evidence_channels": [],
                "track": {
                    "category": "scope",
                    "domain": "test-session",
                    "target_surfaces": ["src/g1.py"],
                },
            },
            {"id": "g2", "requirement": "settled fact", "ambiguity_score": 0, "impact_weight": 2, "status": "draft", "evidence_channels": ["from-code"]},
        ]
    }
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "protocol.json").write_text(make_protocol(**protocol_overrides), encoding="utf-8")
    (session / "questions.json").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "id": "Q1",
                        "question": "Resolve the open gap?",
                        "impact": 3,
                        "branch_split": 3,
                        "uncertainty_reduction": 3,
                        "coverage": 3,
                        "user_cost": 1,
                        "redundancy": 0,
                        "target_ids": ["g1"],
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    return session


def test_session_update_applies_settle_add_and_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "set": [{"id": "g1", "ambiguity_score": 0, "add_channels": ["from-user"], "append_reason": "pressure survived", "pressure": "survived"}],
        "add": [{"id": "g3", "requirement": "new sweep find", "ambiguity_score": 1, "impact_weight": 2, "status": "draft", "evidence_channels": ["assumption"], "origin": "sweep"}],
        "append_history": True,
    }

    result = CLI_RUNNER.invoke(
        make_app(session_update.main), [str(session), "--delta", json.dumps(delta)]
    )

    assert result.exit_code == 0, result.output
    written_ledger = json.loads((session / "ledger.json").read_text(encoding="utf-8"))
    g1 = next(entry for entry in written_ledger["entries"] if entry["id"] == "g1")
    assert g1["ambiguity_score"] == 0
    assert g1["evidence_channels"] == ["from-user"]
    assert "pressure survived" in g1["reason"]
    assert any(entry["id"] == "g3" for entry in written_ledger["entries"])
    written_protocol = json.loads((session / "protocol.json").read_text(encoding="utf-8"))
    assert written_protocol["interactions_used"] == 3
    # history appended from the UPDATED ledger: residual = g3 only (1*2) = 2, 3 active entries
    assert written_protocol["residual_history"] == [20, 12, 6, 2]
    assert written_protocol["gap_count_history"][-1] == 3
    assert "Residual ambiguity: 2" in result.output


def test_session_update_is_all_or_nothing_on_invalid_delta(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before_ledger = (session / "ledger.json").read_text(encoding="utf-8")
    before_protocol = (session / "protocol.json").read_text(encoding="utf-8")
    delta = {
        "set": [{"id": "g1", "ambiguity_score": 0}],
        "protocol": {"interactions_used": -1},
    }

    result = CLI_RUNNER.invoke(
        make_app(session_update.main), [str(session), "--delta", json.dumps(delta)]
    )

    assert result.exit_code != 0
    assert (session / "ledger.json").read_text(encoding="utf-8") == before_ledger
    assert (session / "protocol.json").read_text(encoding="utf-8") == before_protocol


def test_session_update_rejects_unknown_entry_and_duplicate_add(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    missing = CLI_RUNNER.invoke(
        make_app(session_update.main),
        [str(session), "--delta", json.dumps({"set": [{"id": "ghost", "ambiguity_score": 0}]})],
    )
    duplicate = CLI_RUNNER.invoke(
        make_app(session_update.main),
        [str(session), "--delta", json.dumps({"add": [{"id": "g1", "ambiguity_score": 1, "impact_weight": 1, "status": "draft"}]})],
    )

    assert missing.exit_code != 0
    assert "no ledger entry with id 'ghost'" in missing.output
    assert duplicate.exit_code != 0
    assert "duplicate ledger entry id 'g1'" in duplicate.output


def test_session_update_rejects_unknown_delta_and_protocol_fields(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    unknown_top = CLI_RUNNER.invoke(
        make_app(session_update.main), [str(session), "--delta", json.dumps({"settle": []})]
    )
    unknown_protocol = CLI_RUNNER.invoke(
        make_app(session_update.main),
        [str(session), "--delta", json.dumps({"protocol": {"interactions": 4}})],
    )

    assert unknown_top.exit_code != 0
    assert "invalid delta" in unknown_top.output
    assert unknown_protocol.exit_code != 0
    assert "unknown field(s)" in unknown_protocol.output


def test_session_update_lens_merge_is_partial(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {"protocol": {"lenses": {"quality": {"state": "triggered", "reason": "vague word surfaced"}}}}

    result = CLI_RUNNER.invoke(
        make_app(session_update.main), [str(session), "--delta", json.dumps(delta)]
    )

    assert result.exit_code == 0, result.output
    written = json.loads((session / "protocol.json").read_text(encoding="utf-8"))
    assert written["lenses"]["quality"]["state"] == "triggered"
    assert written["lenses"]["viewpoint"]["state"] == "done"  # untouched lenses survive


# ─── typed-event bookkeeping (A) ───


def run_update(session: Path, delta: dict) -> object:
    return CLI_RUNNER.invoke(
        make_app(session_update.main), [str(session), "--delta", json.dumps(delta)]
    )


def read_protocol(session: Path) -> dict:
    return json.loads((session / "protocol.json").read_text(encoding="utf-8"))


def read_ledger_entries(session: Path) -> list[dict]:
    return json.loads((session / "ledger.json").read_text(encoding="utf-8"))["entries"]


def test_event_scored_question_computes_costing(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {"event": "scored-question", "asked_question_id": "Q1"},
    )
    assert result.exit_code == 0, result.output
    written = read_protocol(session)
    assert written["interactions_used"] == 4
    assert written["answers_since_sweep"] == 2


def test_event_sweep_asked_costs_and_resets_cadence(tmp_path: Path) -> None:
    session = make_session(tmp_path, answers_since_sweep=4)
    result = run_update(session, {"event": "sweep-asked", "sweep_result": "dry"})
    assert result.exit_code == 0, result.output
    written = read_protocol(session)
    assert written["interactions_used"] == 4
    assert written["answers_since_sweep"] == 0
    assert written["sweeps_run"] == 3
    assert written["dry_sweeps_in_row"] == 3


def test_event_sweep_free_is_not_budgeted(tmp_path: Path) -> None:
    session = make_session(tmp_path, answers_since_sweep=4)
    result = run_update(
        session,
        {
            "event": "sweep-free",
            "sweep_result": "new-gaps",
            "add": [
                {
                    "id": "sweep-gap",
                    "requirement": "newly discovered branch",
                    "ambiguity_score": 2,
                    "impact_weight": 2,
                    "status": "draft",
                    "evidence_channels": ["from-code"],
                    "origin": "sweep",
                },
            ],
        },
    )
    assert result.exit_code == 0, result.output
    written = read_protocol(session)
    assert written["interactions_used"] == 3
    assert written["answers_since_sweep"] == 0
    assert written["sweeps_run"] == 3
    assert written["dry_sweeps_in_row"] == 0


def test_sweep_event_requires_an_explicit_result(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = run_update(session, {"event": "sweep-free"})

    assert result.exit_code != 0
    assert "sweep_result" in result.output


def test_sweep_result_is_rejected_for_non_sweep_event(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = run_update(session, {"event": "scored-question", "sweep_result": "dry"})

    assert result.exit_code != 0
    assert "sweep_result" in result.output


def test_new_gaps_sweep_requires_a_sweep_origin_entry(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = run_update(session, {"event": "sweep-free", "sweep_result": "new-gaps"})

    assert result.exit_code != 0
    assert "origin" in result.output


def test_new_gaps_sweep_requires_an_ambiguous_gap(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "event": "sweep-free",
        "sweep_result": "new-gaps",
        "add": [
            {
                "id": "settled-sweep-fact",
                "ambiguity_score": 0,
                "impact_weight": 2,
                "status": "accepted",
                "evidence_channels": ["from-code"],
                "origin": "sweep",
            },
        ],
    }

    result = run_update(session, delta)

    assert result.exit_code != 0
    assert "ambiguous" in result.output


def test_new_gaps_sweep_accepts_an_immediately_deferred_risk(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "event": "sweep-free",
        "sweep_result": "new-gaps",
        "add": [
            {
                "id": "deferred-sweep-risk",
                "requirement": "bulk operation policy remains deferred",
                "ambiguity_score": 2,
                "impact_weight": 2,
                "status": "deferred",
                "deferred": {"owner": "service-owner", "decision_date": "2026-10-01"},
                "evidence_channels": ["from-user"],
                "origin": "sweep",
            },
        ],
    }

    result = run_update(session, delta)

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["dry_sweeps_in_row"] == 0


def test_dry_sweep_rejects_a_sweep_origin_entry(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "event": "sweep-free",
        "sweep_result": "dry",
        "add": [
            {
                "id": "sweep-gap",
                "ambiguity_score": 2,
                "impact_weight": 2,
                "status": "draft",
                "evidence_channels": ["from-code"],
                "origin": "sweep",
            },
        ],
    }

    result = run_update(session, delta)

    assert result.exit_code != 0
    assert "dry" in result.output


def test_bare_checkpoint_event_is_rejected(tmp_path: Path) -> None:
    session = make_session(tmp_path, checkpoint_since_last_material_change=False)
    result = run_update(session, {"event": "checkpoint"})
    assert result.exit_code != 0
    assert "checkpoint_confirm" in result.output


def test_event_contrarian_free_costs_nothing(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(session, {"event": "contrarian-free"})
    assert result.exit_code == 0, result.output
    written = read_protocol(session)
    assert written["contrarian_probes_run"] == 2
    assert written["interactions_used"] == 3


def test_event_brain_dump_and_framing_set_flags(tmp_path: Path) -> None:
    session = make_session(tmp_path, brain_dump_done=False, framing_challenged=False)
    assert run_update(session, {"event": "brain-dump"}).exit_code == 0
    assert read_protocol(session)["brain_dump_done"] is True
    assert run_update(session, {"event": "framing"}).exit_code == 0
    written = read_protocol(session)
    assert written["framing_challenged"] is True
    assert written["interactions_used"] == 5


def test_checkpoint_can_carry_the_minimal_depth_framing_challenge(tmp_path: Path) -> None:
    session = make_session(tmp_path, framing_challenged=False)

    result = run_update(
        session,
        {"checkpoint_confirm": {"ids": ["g1"], "fatigue": False}},
    )

    assert result.exit_code == 0, result.output
    protocol = read_protocol(session)
    assert protocol["framing_challenged"] is True


def test_event_pressure_followup_changes_no_counter(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before = read_protocol(session)
    result = run_update(
        session,
        {"event": "pressure-followup", "pressure_parent": "thread-1"},
    )
    assert result.exit_code == 0, result.output
    after = read_protocol(session)
    assert after["interactions_used"] == before["interactions_used"]
    assert after["answers_since_sweep"] == before["answers_since_sweep"]
    assert after["pressure_followups_by_parent"] == {"thread-1": 1}


def test_pressure_followup_rejects_third_turn_per_parent(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {"event": "pressure-followup", "pressure_parent": "thread-1"}

    assert run_update(session, delta).exit_code == 0
    assert run_update(session, delta).exit_code == 0
    third = run_update(session, delta)
    new_parent = run_update(
        session,
        {"event": "pressure-followup", "pressure_parent": "thread-2"},
    )

    assert third.exit_code != 0
    assert "scored-question" in third.output
    assert new_parent.exit_code == 0, new_parent.output


def test_event_conflicts_with_manual_counter(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {"event": "scored-question", "protocol": {"interactions_used": 9}},
    )
    assert result.exit_code != 0
    assert "event-managed" in result.output
    assert read_protocol(session)["interactions_used"] == 3


def test_eventless_delta_cannot_forge_managed_readiness_counters(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {"protocol": {"dry_sweeps_in_row": 99, "checkpoint_since_last_material_change": True}},
    )
    assert result.exit_code != 0
    assert "managed" in result.output


def test_material_ledger_change_rearms_checkpoint(tmp_path: Path) -> None:
    session = make_session(tmp_path, checkpoint_since_last_material_change=True)
    result = run_update(
        session,
        {
            "event": "scored-question",
            "asked_question_id": "Q1",
            "set": [{"id": "g1", "ambiguity_score": 0, "add_channels": ["from-code"]}],
        },
    )
    assert result.exit_code == 0, result.output
    assert read_protocol(session)["checkpoint_since_last_material_change"] is False


def test_evidence_only_foldback_does_not_rearm_checkpoint(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        checkpoint_since_last_material_change=True,
        dry_sweeps_in_row=2,
        sweeps_run=2,
    )
    result = run_update(
        session,
        {
            "add": [{
                "id": "folded-evidence",
                "requirement": "repo-confirmed existing behavior",
                "ambiguity_score": 0,
                "impact_weight": 2,
                "status": "accepted",
                "evidence_channels": ["from-code"],
                "origin": "fold-back",
            }],
        },
    )
    assert result.exit_code == 0, result.output
    assert read_protocol(session)["checkpoint_since_last_material_change"] is True
    assert read_protocol(session)["dry_sweeps_in_row"] == 2


def test_unknown_event_rejected(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(session, {"event": "vibe-check"})
    assert result.exit_code != 0


# ─── transcript generation (A) ───


def make_session_with_transcript(tmp_path: Path, **overrides: object) -> Path:
    session = make_session(tmp_path, **overrides)
    (session / "transcript.md").write_text("# Interview Transcript — test\n", encoding="utf-8")
    return session


def test_transcript_heading_uses_computed_interaction_number(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    delta = {
        "event": "scored-question",
        "asked_question_id": "Q1",
        "transcript": {"title": "store scope", "lines": ["Verbatim answer: single machine"]},
    }
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "## interaction 4 [scored-question] — store scope (" in text
    assert "- Verbatim answer: single machine" in text


def test_transcript_free_event_appends_sub_bullet(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    delta = {
        "event": "pressure-followup",
        "pressure_parent": "thread-1",
        "transcript": {"title": "day boundary probe"},
    }
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "- [pressure-followup] day boundary probe" in text
    assert "## interaction" not in text.replace("# Interview Transcript", "")


def test_transcript_eventless_note_is_zero_cost_sub_bullet(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    before = read_protocol(session)
    result = run_update(session, {"transcript": {"title": "lane fold-back", "lines": ["claim x"]}})
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "- [note] lane fold-back" in text
    assert read_protocol(session)["interactions_used"] == before["interactions_used"]


def test_transcript_note_awaiting_marker_renders(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    delta = {"transcript": {"title": "brain-dump invitation", "awaiting": True}}
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "- [note] brain-dump invitation [awaiting-answer]" in text


def test_answer_bearing_event_resolves_awaiting_marker(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    run_update(session, {"transcript": {"title": "question sent", "awaiting": True}})
    delta = {
        "event": "scored-question",
        "asked_question_id": "Q1",
        "transcript": {"title": "answer landed"},
    }
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "[awaiting-answer]" not in text
    assert "question sent [answered]" in text


def test_pressure_followup_resolves_awaiting_marker(tmp_path: Path) -> None:
    session = make_session_with_transcript(tmp_path)
    run_update(session, {"transcript": {"title": "probe sent", "awaiting": True}})
    result = run_update(
        session,
        {"event": "pressure-followup", "pressure_parent": "thread-1"},
    )
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "[awaiting-answer]" not in text


def test_repo_only_event_keeps_awaiting_marker(tmp_path: Path) -> None:
    # sweep-free / contrarian-free are not user answers; an in-flight question stays open.
    session = make_session_with_transcript(tmp_path)
    run_update(session, {"transcript": {"title": "question sent", "awaiting": True}})
    result = run_update(session, {"event": "sweep-free", "sweep_result": "dry"})
    assert result.exit_code == 0, result.output
    text = (session / "transcript.md").read_text(encoding="utf-8")
    assert "question sent [awaiting-answer]" in text


def test_transcript_missing_file_fails_before_writes(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before = read_protocol(session)
    delta = {"event": "scored-question", "transcript": {"title": "x"}}
    result = run_update(session, delta)
    assert result.exit_code != 0
    assert read_protocol(session) == before


# ─── pressure gate (D) ───


def test_pressure_gate_blocks_unpressured_weighty_settle(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before = read_ledger_entries(session)
    delta = {"set": [{"id": "g1", "ambiguity_score": 1, "add_channels": ["from-user"]}]}
    result = run_update(session, delta)
    assert result.exit_code != 0
    assert "pressure gate" in result.output
    assert read_ledger_entries(session) == before


def test_pressure_gate_records_token(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "set": [
            {"id": "g1", "ambiguity_score": 0, "add_channels": ["from-user"], "pressure": "survived"}
        ]
    }
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    g1 = next(entry for entry in read_ledger_entries(session) if entry["id"] == "g1")
    assert "[pressure: survived]" in g1["reason"]


def test_pressure_gate_second_channel_passes_mechanically(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {
        "set": [
            {"id": "g1", "ambiguity_score": 0, "add_channels": ["from-user", "from-code"]}
        ]
    }
    assert run_update(session, delta).exit_code == 0


def test_pressure_gate_exempts_non_user_settles(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {"set": [{"id": "g1", "ambiguity_score": 0, "add_channels": ["from-code"]}]}
    assert run_update(session, delta).exit_code == 0


def test_pressure_gate_applies_to_new_entries(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    entry = {
        "id": "g9",
        "requirement": "settled at birth",
        "ambiguity_score": 0,
        "impact_weight": 3,
        "status": "accepted",
        "evidence_channels": ["from-user"],
    }
    blocked = run_update(session, {"add": [entry]})
    assert blocked.exit_code != 0
    allowed = run_update(session, {"add": [{**entry, "pressure": "exempt:protocol decision, no second channel possible"}]})
    assert allowed.exit_code == 0, allowed.output
    g9 = next(item for item in read_ledger_entries(session) if item["id"] == "g9")
    assert "pressure" not in g9
    assert "[pressure: exempt:" in g9["reason"]


def test_pressure_token_format_is_validated(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {"set": [{"id": "g1", "ambiguity_score": 0, "pressure": "trust me"}]}
    result = run_update(session, delta)
    assert result.exit_code != 0


# ─── checkpoint_confirm (F) ───


def test_checkpoint_confirm_credits_single_channel_entries(tmp_path: Path) -> None:
    session = make_session(tmp_path, checkpoint_since_last_material_change=False)
    delta = {"checkpoint_confirm": {"ids": ["g2"]}}
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    g2 = next(entry for entry in read_ledger_entries(session) if entry["id"] == "g2")
    assert g2["evidence_channels"] == ["from-code", "from-user"]
    assert "[checkpoint-corroborated: from-user]" in g2["reason"]
    written = read_protocol(session)
    assert written["falsification_checkpoints_run"] == 2
    assert written["checkpoint_since_last_material_change"] is True
    assert written["interactions_used"] == 4


def test_checkpoint_confirm_never_double_credits_from_user(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    run_update(session, {"set": [{"id": "g2", "evidence_channels": ["from-user"]}]})
    delta = {"checkpoint_confirm": {"ids": ["g2"]}}
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    g2 = next(entry for entry in read_ledger_entries(session) if entry["id"] == "g2")
    assert g2["evidence_channels"] == ["from-user"]


def test_checkpoint_confirm_fatigue_credits_nothing(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    delta = {"checkpoint_confirm": {"ids": ["g2"], "fatigue": True}}
    result = run_update(session, delta)
    assert result.exit_code == 0, result.output
    g2 = next(entry for entry in read_ledger_entries(session) if entry["id"] == "g2")
    assert g2["evidence_channels"] == ["from-code"]
    assert read_protocol(session)["falsification_checkpoints_run"] == 2


def test_checkpoint_confirm_unknown_id_fails_closed(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before_protocol = read_protocol(session)
    result = run_update(session, {"checkpoint_confirm": {"ids": ["nope"]}})
    assert result.exit_code != 0
    assert read_protocol(session) == before_protocol


def test_checkpoint_confirm_conflicts_with_event(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {"event": "checkpoint", "checkpoint_confirm": {"ids": ["g2"]}},
    )
    assert result.exit_code != 0
    assert "not both" in result.output


# ─── deferred structure + gate mode (H) ───


def test_deferred_record_is_deferred_and_excluded() -> None:
    raw = json.dumps(
        [
            {
                "id": "d1",
                "requirement": "deferred with owner",
                "ambiguity_score": 3,
                "impact_weight": 5,
                "status": "draft",
                "deferred": {"owner": "jpark", "decision_date": "2026-08-01"},
            },
            {"id": "ok", "requirement": "settled", "ambiguity_score": 0, "impact_weight": 1, "status": "accepted", "evidence_channels": ["from-code"]},
        ]
    )
    summary = summarize_ambiguity(parse_entries(raw))
    assert summary.deferred_count == 1
    assert summary.handoff_ready


def test_deferred_record_rejects_empty_owner() -> None:
    raw = json.dumps(
        [
            {
                "id": "d1",
                "requirement": "bad deferral",
                "ambiguity_score": 1,
                "impact_weight": 2,
                "deferred": {"owner": " ", "decision_date": "2026-08-01"},
            }
        ]
    )
    with pytest.raises(ValidationError):
        parse_entries(raw)


def test_gate_failures_flag_contested_and_unowned_deferrals() -> None:
    raw = json.dumps(
        [
            {"id": "c1", "requirement": "conflict", "ambiguity_score": 2, "impact_weight": 3, "status": "contested", "evidence_channels": ["from-code", "from-user"]},
            {"id": "d1", "requirement": "boolean deferral", "ambiguity_score": 1, "impact_weight": 2, "deferred": True},
        ]
    )
    failures = ambiguity_ledger.gate_failures(parse_entries(raw))
    assert any("contested entries unresolved: c1" in failure for failure in failures)
    assert any("d1" in failure and "owner/decision_date" in failure for failure in failures)


def test_gate_failures_reject_blocked_and_unevidenced_settlements() -> None:
    entries = parse_entries(
        json.dumps(
            [
                {
                    "id": "blocked",
                    "requirement": "cannot proceed",
                    "ambiguity_score": 0,
                    "impact_weight": 1,
                    "status": "blocked",
                    "evidence_channels": ["assumption"],
                },
                {
                    "id": "unevidenced",
                    "requirement": "claimed settlement",
                    "ambiguity_score": 1,
                    "impact_weight": 1,
                    "status": "accepted",
                },
            ],
        ),
    )

    failures = ambiguity_ledger.gate_failures(entries)

    assert any("blocked entries" in failure for failure in failures)
    assert any("without a recorded channel" in failure for failure in failures)


def make_gate_handoff(
    source_id: str,
    *,
    command: str = "okcmd --version",
    behavior: str = "identifier must be a non-empty decimal string",
) -> str:
    return f"""# Part 1 — Build Contract
## Goal
Ship the settled behavior. (source: {source_id})
## Target Surface
| File / module | Expected change |
| --- | --- |
| command module | add identifier validation |
## Behavior Contract
| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 | validate identifiers | {behavior} | {source_id} |
## Change Impact & Preservation
| Source | Current evidence | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |
| --- | --- | --- | --- | --- | --- | --- |
| {source_id} | current tests | existing data remains readable | add the settled behavior | command module | REQ-001 | command exit status |
## Quality Bars
No measurable quality bar applies - this local validation has no runtime quality target.
## Decision Boundaries
No implementation choice may change REQ-001. Standing instruction: append every unforced decision to `.ultimateinterview/<slug>/decisions.jsonl` as you make it (the execution substrate does not auto-log).
## Out Of Scope / Non-Goals
No unrelated command changes.
## Implementation Constraints
Keep the existing runtime and dependencies.
Decision core: pure identifier validation input to acceptance result.
Effects boundary: command exit status only; no DB, API, message, or retry effect.
## Rollout & Recovery
| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |
| --- | --- | --- | --- | --- | --- |
| next local build | no backfill | REQ-001 fails | revert the change | command exit status for one test run | implementer |
## Guardrail Compile
No stop-time or pre-action guardrail applies - validation has no external or destructive effects.
## Verification Commands
| Check | Kind | Command / action | Pass condition |
| --- | --- | --- | --- |
| REQ-001 unit | test | `okcmd --version` | exits 0 |
| REQ-001 surface | real-surface | `{command}` | exits 0 on the shipped command surface |
## Deferred Risks
None.
## Fresh-Implementer Test
| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? | Unresolved after disposition |
| --- | --- | --- | --- | --- |
| critic | none | none | no fold-back required | none |
# Part 2 — Audit Trail
No additional decisions.
"""


def write_gate_handoff(session: Path, handoff: str) -> None:
    (session / "handoff.md").write_text(handoff, encoding="utf-8")
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["build_contract_digest"] = implementation_gate.contract_digest(handoff)
    protocol["build_contract_reviewer"] = "critic"
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")


def install_gate_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    command = tmp_path / "okcmd"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))


def test_session_status_gate_mode_exits_nonzero_on_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    ledger = [
        {"id": "d1", "requirement": "boolean deferral", "ambiguity_score": 1, "impact_weight": 2, "deferred": True},
        {"id": "ok", "requirement": "settled", "ambiguity_score": 0, "impact_weight": 1, "status": "accepted", "evidence_channels": ["from-code"]},
    ]
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "protocol.json").write_text(make_protocol(), encoding="utf-8")
    write_gate_handoff(session, make_gate_handoff("ok"))
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert "FAIL" in result.output
    fixed = [
        {**ledger[0], "deferred": {"owner": "jpark", "decision_date": "2026-08-01"}},
        ledger[1],
    ]
    (session / "ledger.json").write_text(json.dumps(fixed), encoding="utf-8")
    handoff = (session / "handoff.md").read_text(encoding="utf-8").replace(
        "## Deferred Risks\nNone.",
        "## Deferred Risks\n| Risk | Owner | Decision date | Mitigation |\n"
        "| --- | --- | --- | --- |\n"
        "| d1 | jpark | 2026-08-01 | keep visible to implementer |",
    )
    write_gate_handoff(session, handoff)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 0
    assert "implementation_ready: yes" in result.output


def test_gate_blocks_predicate_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1", behavior="invalid identifier"))

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "implementation_ready: no" in result.output
    assert "reject-category" in result.output


def test_gate_blocks_missing_verification_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1", command="missingcmd --version"))

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "missingcmd" in result.output


def test_gate_blocks_missing_change_trace_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1").replace(
        "| R1 | current tests | existing data remains readable | add the settled behavior | command module | REQ-001 | command exit status |",
        "",
    )
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "Change Impact & Preservation" in result.output


def test_gate_blocks_empty_required_section_and_incomplete_behavior_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1", behavior="")
    target_start = handoff.index("## Target Surface")
    behavior_start = handoff.index("## Behavior Contract", target_start)
    handoff = handoff[:target_start] + "## Target Surface\n" + handoff[behavior_start:]
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "empty Build Contract section(s): Target Surface" in result.output
    assert "Behavior Contract needs at least one complete requirement row" in result.output


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |",
            "| Source | Acceptance criterion (EARS or Given/When/Then) |",
            "Behavior Contract",
        ),
        (
            "| Source | Current evidence | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |",
            "| Source | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |",
            "Change Impact & Preservation",
        ),
    ],
)
def test_gate_blocks_reduced_required_table_schemas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
    message: str,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1").replace(old, new))
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert message in result.output


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "## Rollout & Recovery\n| Activation",
            "## Rollout & Recovery\nN/A -\n\n| Activation",
            "Rollout & Recovery",
        ),
        (
            "Decision core: pure identifier validation input to acceptance result.",
            "Decision core:",
            "Decision core",
        ),
        (
            "No measurable quality bar applies - this local validation has no runtime quality target.",
            "No material quality constraint beyond REQ-001.",
            "Quality Bars",
        ),
        (
            "No stop-time or pre-action guardrail applies - validation has no external or destructive effects.",
            "REQ-001 preserves compatibility.",
            "Guardrail Compile",
        ),
        (
            "| REQ-001 surface | real-surface | `okcmd --version` | exits 0 on the shipped command surface |",
            "| REQ-001 surface | test | `okcmd --version` | exits 0 |",
            "real-surface",
        ),
    ],
)
def test_gate_blocks_blank_or_weak_semantic_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old: str,
    new: str,
    message: str,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1").replace(old, new))
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert message in result.output


def test_gate_ignores_contract_content_inside_fences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    fenced = "# Part 1 — Build Contract\n```markdown\n" + make_gate_handoff("R1") + "\n```\n# Part 2\n"
    write_gate_handoff(session, fenced)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert "missing Build Contract section" in result.output


def test_gate_rejects_malformed_verification_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1").replace("okcmd --version`,", "okcmd --version`,")
    handoff = handoff.replace("`okcmd --version` | exits 0 on the shipped command surface", "`okcmd -c 'unterminated` | exits 0 on the shipped command surface")
    write_gate_handoff(session, handoff)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert "malformed verification command" in result.output


def test_json_gate_executes_and_reports_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1", command="missingcmd --version"))

    result = CLI_RUNNER.invoke(
        make_app(session_status.main), [str(session), "--gate", "--format", "json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.output)["implementation_gate"]["implementation_ready"] is False


def test_gate_requires_session_directory(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    protocol = tmp_path / "protocol.json"
    ledger.write_text(make_ready_ledger(), encoding="utf-8")
    protocol.write_text(make_protocol(), encoding="utf-8")

    result = CLI_RUNNER.invoke(
        make_app(session_status.main),
        ["--ledger", str(ledger), "--protocol", str(protocol), "--gate"],
    )

    assert result.exit_code != 0
    assert "session directory" in result.output


def test_gate_rejects_external_state_overrides(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1"))
    result = CLI_RUNNER.invoke(
        make_app(session_status.main),
        [str(session), "--gate", "--ledger", str(session / "ledger.json")],
    )
    assert result.exit_code != 0
    assert "does not accept" in result.output


def test_gate_rejects_handoff_changed_after_fresh_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    write_gate_handoff(session, make_gate_handoff("R1"))
    handoff_path = session / "handoff.md"
    handoff_path.write_text(
        handoff_path.read_text(encoding="utf-8").replace("Ship the settled behavior", "Ship changed behavior"),
        encoding="utf-8",
    )
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert "digest" in result.output


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            "| Attribute | Bar (a number an implementer can verify) | Weight | Verification |\n"
            "| --- | --- | --- | --- |\n"
            "| speed | fast | high | eyeball it |",
            "measurable",
        ),
        (
            "| Risk | Class | Predicate / residual / substrate owner | Evidence |\n"
            "| --- | --- | --- | --- |\n"
            "| data loss | Stop-time predicate | be careful | trust the implementer |",
            "Guardrail Compile",
        ),
    ],
)
def test_gate_rejects_semantically_empty_quality_or_guardrail_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
    message: str,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1")
    if "Attribute" in replacement:
        handoff = handoff.replace(
            "No measurable quality bar applies - this local validation has no runtime quality target.",
            replacement,
        )
    else:
        handoff = handoff.replace(
            "No stop-time or pre-action guardrail applies - validation has no external or destructive effects.",
            replacement,
        )
    write_gate_handoff(session, handoff)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert message in result.output


def test_gate_requires_structured_fresh_implementer_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1")
    start = handoff.index("## Fresh-Implementer Test")
    end = handoff.index("# Part 2", start)
    handoff = handoff[:start] + "## Fresh-Implementer Test\nPassed.\n" + handoff[end:]
    write_gate_handoff(session, handoff)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])
    assert result.exit_code == 1
    assert "Fresh-Implementer Test" in result.output


def test_session_update_records_fresh_review_evidence(tmp_path: Path) -> None:
    session = make_session(tmp_path, build_contract_tested=False, build_contract_digest="", build_contract_reviewer="")
    handoff = make_gate_handoff("g2")
    (session / "handoff.md").write_text(handoff, encoding="utf-8")
    result = run_update(session, {"build_contract_test": {"reviewer": "critic"}})
    assert result.exit_code == 0, result.output
    protocol = read_protocol(session)
    assert protocol["build_contract_tested"] is True
    assert protocol["build_contract_reviewer"] == "critic"
    assert protocol["build_contract_digest"] == implementation_gate.contract_digest(handoff)


# ─── next-action router (B) ───


def status_next(session: Path) -> object:
    return CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--next"])


def test_next_prioritizes_bookkeeping_lag_over_sweep(tmp_path: Path) -> None:
    session = make_session(tmp_path, interactions_used=6, answers_since_sweep=5, residual_history=[20])
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "- next: bookkeeping: residual_history lags" in result.output
    assert "- then: breadth sweep" in result.output


def test_next_routes_to_critical_path_question(tmp_path: Path) -> None:
    session = make_session(tmp_path)  # g1 is score 2, weight 3
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "- next: scored-question targeting a critical-path gap (g1)" in result.output


def test_next_routes_to_batch_flush_when_no_critical_path(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    ledger = [
        {"id": "b1", "requirement": "low-risk", "ambiguity_score": 2, "impact_weight": 2, "status": "draft", "evidence_channels": ["assumption"]},
        {"id": "b2", "requirement": "low-risk too", "ambiguity_score": 2, "impact_weight": 1, "status": "draft", "evidence_channels": ["assumption"]},
    ]
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "protocol.json").write_text(make_protocol(), encoding="utf-8")
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "- next: smart-default batch flush (b1, b2)" in result.output


def test_next_routes_to_endgame_when_ready(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    ledger = [
        {"id": "ok", "requirement": "settled", "ambiguity_score": 0, "impact_weight": 3, "status": "accepted", "evidence_channels": ["from-code", "from-user"]},
    ]
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "protocol.json").write_text(make_protocol(), encoding="utf-8")
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "- next: ENDGAME" in result.output


def test_next_pre_handoff_step_orders_checkpoint(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    ledger = [
        {"id": "ok", "requirement": "settled", "ambiguity_score": 0, "impact_weight": 3, "status": "accepted", "evidence_channels": ["from-code", "from-user"]},
    ]
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "protocol.json").write_text(
        make_protocol(checkpoint_since_last_material_change=False, build_contract_tested=False),
        encoding="utf-8",
    )
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "- next: mandatory pre-handoff falsification checkpoint" in result.output


def test_next_arms_implementer_scout_once(tmp_path: Path) -> None:
    session = make_session(tmp_path, build_contract_tested=False)  # g1 score 2: no score-3, not ready
    result = status_next(session)
    assert result.exit_code == 0, result.output
    assert "implementer-scout lane armed" in result.output
    second_root = tmp_path / "second"
    second_root.mkdir()
    session2 = make_session(second_root, build_contract_tested=False, implementer_scout_run=True)
    result2 = status_next(session2)
    assert "implementer-scout" not in result2.output

LOCALITY_TRACKS = [
    {
        "asked_question_id": f"Q{number}",
        "ledger_ids": ["g1"],
        "categories": ["scope"],
        "domains": ["test-session"],
        "target_files": ["src/g1.py"],
    }
    for number in range(1, protocol_state.LOCALITY_WINDOW + 1)
]


def add_locality_sibling(session: Path) -> None:
    ledger = json.loads((session / "ledger.json").read_text(encoding="utf-8"))
    ledger["entries"].append(
        {
            "id": "g-sibling",
            "requirement": "unresolved sibling track",
            "ambiguity_score": 1,
            "impact_weight": 1,
            "status": "draft",
            "track": {
                "category": "behavior",
                "domain": "other-domain",
                "target_surfaces": ["src/sibling.py"],
            },
        },
    )
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")


def test_next_locality_zoom_out_preempts_scored_routing(tmp_path: Path) -> None:
    session = make_session(tmp_path, recent_question_tracks=LOCALITY_TRACKS)
    add_locality_sibling(session)

    result = status_next(session)

    assert result.exit_code == 0, result.output
    assert "- next: locality zoom-out:" in result.output
    assert "categories=scope" in result.output
    assert "domains=test-session" in result.output
    assert "target_files=src/g1.py" in result.output
    assert "unresolved sibling ledger ids: g-sibling" in result.output
    assert "scored-question targeting a critical-path gap" not in result.output
    assert "smart-default batch flush" not in result.output


def test_next_locality_does_not_fire_before_full_window(tmp_path: Path) -> None:
    session = make_session(tmp_path, recent_question_tracks=LOCALITY_TRACKS[:2])
    add_locality_sibling(session)

    result = status_next(session)

    assert result.exit_code == 0, result.output
    assert "locality zoom-out:" not in result.output
    assert "scored-question targeting a critical-path gap (g1)" in result.output


def test_next_locality_does_not_fire_without_common_key(tmp_path: Path) -> None:
    tracks = [
        {
            **LOCALITY_TRACKS[index],
            "categories": [category],
            "domains": [f"domain-{index}"],
            "target_files": [f"src/{index}.py"],
        }
        for index, category in enumerate(("scope", "behavior", "verification"))
    ]
    session = make_session(tmp_path, recent_question_tracks=tracks)
    add_locality_sibling(session)

    result = status_next(session)

    assert result.exit_code == 0, result.output
    assert "locality zoom-out:" not in result.output
    assert "scored-question targeting a critical-path gap (g1)" in result.output


def test_next_locality_stays_deep_without_an_unresolved_sibling(tmp_path: Path) -> None:
    session = make_session(tmp_path, recent_question_tracks=LOCALITY_TRACKS)

    result = status_next(session)

    assert result.exit_code == 0, result.output
    assert "locality zoom-out:" not in result.output
    assert "scored-question targeting a critical-path gap (g1)" in result.output


def test_next_locality_does_not_refire_after_sweep_clears_window(tmp_path: Path) -> None:
    session = make_session(tmp_path, recent_question_tracks=LOCALITY_TRACKS)
    add_locality_sibling(session)
    assert "locality zoom-out:" in status_next(session).output

    result = run_update(session, {"event": "sweep-free", "sweep_result": "dry"})
    assert result.exit_code == 0, result.output

    next_result = status_next(session)
    assert next_result.exit_code == 0, next_result.output
    assert "locality zoom-out:" not in next_result.output
    assert "scored-question targeting a critical-path gap (g1)" in next_result.output


# ─── session_init (C) ───

from scripts import handoff_coverage, lessons, session_init, transcript_check  # noqa: E402


INIT_ENTRIES = json.dumps(
    [
        {
            "id": "N1",
            "requirement": "purpose unknown",
            "ambiguity_score": 3,
            "impact_weight": 5,
            "status": "draft",
            "evidence_channels": ["assumption"],
            "origin": "orientation",
        }
    ]
)


def run_init(root: Path, slug: str, *extra: str) -> object:
    return CLI_RUNNER.invoke(
        make_app(session_init.main),
        [str(root), slug, "--entries", INIT_ENTRIES, *extra],
    )


def test_session_init_creates_valid_session(tmp_path: Path) -> None:
    result = run_init(tmp_path, "new-feature")
    assert result.exit_code == 0, result.output
    session = tmp_path / ".ultimateinterview" / "new-feature"
    for name in ("ledger.json", "protocol.json", "questions.json", "transcript.md"):
        assert (session / name).exists()
    assert "Protocol ready: no" in result.output
    assert ".gitignore" in result.output
    assert ".ultimateinterview" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    written = json.loads((session / "protocol.json").read_text(encoding="utf-8"))
    assert written["question_budget"] == 12
    assert written["dry_sweeps_in_row"] == 0
    assert written["lenses"]["misuse"] == {"state": "pending", "reason": ""}


def test_session_init_suffixes_completed_slug(tmp_path: Path) -> None:
    assert run_init(tmp_path, "feature").exit_code == 0
    (tmp_path / ".ultimateinterview" / "feature" / "handoff.md").write_text("done", encoding="utf-8")
    result = run_init(tmp_path, "feature")
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".ultimateinterview" / "feature-2").is_dir()


def test_session_init_refuses_unfinished_session(tmp_path: Path) -> None:
    assert run_init(tmp_path, "feature").exit_code == 0
    result = run_init(tmp_path, "feature")
    assert result.exit_code != 0
    assert "resume" in result.output


def test_session_init_rejects_empty_entries(tmp_path: Path) -> None:
    result = CLI_RUNNER.invoke(
        make_app(session_init.main), [str(tmp_path), "slug", "--entries", "[]"]
    )
    assert result.exit_code != 0


@pytest.mark.parametrize("slug", ["../escape", "/tmp/escape", "not_ok"])
def test_session_init_rejects_unsafe_slug(tmp_path: Path, slug: str) -> None:
    result = run_init(tmp_path, slug)
    assert result.exit_code != 0
    assert "kebab-case" in result.output


# ─── lessons.py (E) ───


LESSONS_SKELETON = """# Lessons

Intro prose.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
| free-text input on CLI | misuse | enumeration-miss | some postmortem | 2026-07-05 | 2/0 |
| temporal word in goal | domain/state | trigger-too-narrow | experiment | 2026-07-06 | 0/0 |
| request names a persisted field invalid without a deciding predicate | controlled-language | enumeration-miss | Wonder candidate | 2026-07-10 | 0/0 |

## Retired

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
"""


def make_lessons(tmp_path: Path) -> Path:
    path = tmp_path / "lessons.md"
    path.write_text(LESSONS_SKELETON, encoding="utf-8")
    return path


def test_lessons_validate_and_list(tmp_path: Path) -> None:
    path = make_lessons(tmp_path)
    assert CLI_RUNNER.invoke(lessons.app, ["validate", str(path)]).exit_code == 0
    listing = CLI_RUNNER.invoke(lessons.app, ["list", str(path)])
    assert listing.exit_code == 0
    assert "1. [misuse] 2/0" in listing.output


def test_lessons_fire_increments_and_caught(tmp_path: Path) -> None:
    path = make_lessons(tmp_path)
    result = CLI_RUNNER.invoke(lessons.app, ["fire", str(path), "temporal", "--caught"])
    assert result.exit_code == 0, result.output
    assert "| 1/1 |" in path.read_text(encoding="utf-8")


def test_lessons_third_dry_fire_retires_row(tmp_path: Path) -> None:
    path = make_lessons(tmp_path)
    result = CLI_RUNNER.invoke(lessons.app, ["fire", str(path), "free-text"])
    assert result.exit_code == 0, result.output
    assert "RETIRED" in result.output
    text = path.read_text(encoding="utf-8")
    assert "auto-retired by lessons.py: 3 fires, 0 catches" in text
    reparsed = CLI_RUNNER.invoke(lessons.app, ["list", str(path)])
    assert "free-text" not in reparsed.output

def test_wonder_new_lesson_validates_fires_and_retires_after_three_dry_fires(
    tmp_path: Path,
) -> None:
    path = make_lessons(tmp_path)
    assert CLI_RUNNER.invoke(lessons.app, ["validate", str(path)]).exit_code == 0

    for expected_fired in (1, 2):
        result = CLI_RUNNER.invoke(lessons.app, ["fire", str(path), "persisted field"])
        assert result.exit_code == 0, result.output
        assert f"| {expected_fired}/0 |" in path.read_text(encoding="utf-8")

    result = CLI_RUNNER.invoke(lessons.app, ["fire", str(path), "persisted field"])
    assert result.exit_code == 0, result.output
    text = path.read_text(encoding="utf-8")
    assert "auto-retired by lessons.py: 3 fires, 0 catches" in text
    assert "persisted field invalid without a deciding predicate" in text

def test_lessons_ambiguous_selector_fails(tmp_path: Path) -> None:
    path = make_lessons(tmp_path)
    result = CLI_RUNNER.invoke(lessons.app, ["fire", str(path), "e"])
    assert result.exit_code != 0


# ─── transcript_check.py (G) ───


def make_checked_session(tmp_path: Path, transcript: str, **overrides: object) -> Path:
    session = tmp_path / "session"
    session.mkdir()
    (session / "protocol.json").write_text(make_protocol(**overrides), encoding="utf-8")
    (session / "transcript.md").write_text(transcript, encoding="utf-8")
    return session


GOOD_TRANSCRIPT = """# Interview Transcript — test

- [repo-work] orientation scan.

## interaction 1 [brain-dump] — intake (2026-07-06)

- Verbatim answer: something.

## interaction 2 [framing] — reframe (2026-07-06)

- [decomposition] split into parts.

## interaction 3 [scored-question] — core gap (2026-07-06)

- [pressure-followup] boundary probe — answered inline.
"""


def test_transcript_check_passes_consistent_session(tmp_path: Path) -> None:
    session = make_checked_session(tmp_path, GOOD_TRANSCRIPT)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 0, result.output
    assert "consistent" in result.output


def test_transcript_check_fails_on_counter_mismatch(tmp_path: Path) -> None:
    session = make_checked_session(tmp_path, GOOD_TRANSCRIPT, interactions_used=5)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 1
    assert "counter is wrong" in result.output


def test_transcript_check_fails_on_out_of_order_numbering(tmp_path: Path) -> None:
    broken = GOOD_TRANSCRIPT.replace("## interaction 2 [framing]", "## interaction 7 [framing]")
    session = make_checked_session(tmp_path, broken)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 1
    assert "out of order" in result.output


def test_transcript_check_fails_on_stale_awaiting_answer(tmp_path: Path) -> None:
    stale = GOOD_TRANSCRIPT.replace(
        "- Verbatim answer: something.",
        "- question sent [awaiting-answer]",
    )
    session = make_checked_session(tmp_path, stale)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 1
    assert "already-answered" in result.output


def test_transcript_check_warns_on_unknown_marker_without_failing(tmp_path: Path) -> None:
    odd = GOOD_TRANSCRIPT + "- [vibes] unclassified note.\n"
    session = make_checked_session(tmp_path, odd)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 0, result.output
    assert "unrecognized sub-bullet marker [vibes]" in result.output


def test_transcript_check_recognizes_note_marker(tmp_path: Path) -> None:
    noted = GOOD_TRANSCRIPT + "- [note] process feedback folded.\n"
    session = make_checked_session(tmp_path, noted)
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 0, result.output
    assert "unrecognized sub-bullet marker" not in result.output


def test_transcript_check_warns_on_missing_exit_check_with_handoff(tmp_path: Path) -> None:
    session = make_checked_session(tmp_path, GOOD_TRANSCRIPT)
    (session / "handoff.md").write_text("# Spec", encoding="utf-8")
    result = CLI_RUNNER.invoke(make_app(transcript_check.main), [str(session)])
    assert result.exit_code == 0, result.output
    assert "exit-check" in result.output


def _coverage_session(tmp_path: Path, ledger: object, handoff: str) -> Path:
    session = tmp_path / "cov"
    session.mkdir()
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (session / "handoff.md").write_text(handoff, encoding="utf-8")
    return session


def test_handoff_coverage_flags_settled_entry_absent_from_part1(tmp_path: Path) -> None:
    ledger = {
        "entries": [
            {"id": "g1", "requirement": "cited behavior", "ambiguity_score": 1, "impact_weight": 3, "status": "accepted", "evidence_channels": ["from-user"]},
            {"id": "g2", "requirement": "dropped behavior", "ambiguity_score": 1, "impact_weight": 2, "status": "accepted", "evidence_channels": ["from-user"]},
        ]
    }
    handoff = "# Part 1 — Build Contract\n| REQ-001 | do it | crit | g1 |\n# Part 2 — Audit Trail\ng2 lives only here\n"
    session = _coverage_session(tmp_path, ledger, handoff)
    result = CLI_RUNNER.invoke(make_app(handoff_coverage.main), [str(session), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert '"uncovered"' in result.output
    assert "g2" in result.output
    assert '"coverage_ok": false' in result.output


def test_handoff_coverage_passes_when_every_settled_entry_cited(tmp_path: Path) -> None:
    ledger = {
        "entries": [
            {"id": "g1", "requirement": "a", "ambiguity_score": 0, "impact_weight": 3, "status": "accepted", "evidence_channels": ["from-user"]},
            {"id": "g2", "requirement": "b", "ambiguity_score": 1, "impact_weight": 2, "status": "accepted", "evidence_channels": ["from-user"]},
        ]
    }
    handoff = "# Part 1 — Build Contract\nGoal (source: g1). Quality bar (source: g2).\n# Part 2\n"
    session = _coverage_session(tmp_path, ledger, handoff)
    result = CLI_RUNNER.invoke(make_app(handoff_coverage.main), [str(session)])
    assert result.exit_code == 0, result.output
    assert "coverage_ok: yes" in result.output


def test_part1_extraction_ignores_part_markers_inside_fenced_examples() -> None:
    handoff = """# Part 1 — Build Contract
```markdown
# Part 2 — example only
```
## Goal
actual contract content
# Part 2 — Audit Trail
audit content
"""

    part1 = handoff_coverage.extract_part1(handoff)

    assert "actual contract content" in part1
    assert "audit content" not in part1


def test_handoff_coverage_exempts_deferred_and_low_weight_and_avoids_substring_match(tmp_path: Path) -> None:
    ledger = {
        "entries": [
            {"id": "g1", "requirement": "cited", "ambiguity_score": 0, "impact_weight": 3, "status": "accepted", "evidence_channels": ["from-user"]},
            {"id": "n1", "requirement": "low weight non-goal", "ambiguity_score": 0, "impact_weight": 1, "status": "accepted", "evidence_channels": ["from-user"]},
            {"id": "g9", "requirement": "deferred", "ambiguity_score": 2, "impact_weight": 3, "status": "deferred", "evidence_channels": ["assumption"], "deferred": {"owner": "u", "decision_date": "2026-07-06"}},
        ]
    }
    # Part 1 cites g1 only inside g11 -> must NOT count as covering g1 via substring.
    handoff = "# Part 1\nSee g11 elsewhere and (source: g1) here.\n# Part 2\n"
    session = _coverage_session(tmp_path, ledger, handoff)
    result = CLI_RUNNER.invoke(make_app(handoff_coverage.main), [str(session), "--format", "json"])
    # g1 cited, n1 excluded (weight 1), g9 excluded (deferred) -> clean.
    assert result.exit_code == 0, result.output
    assert '"coverage_ok": true' in result.output


def test_handoff_coverage_advisory_never_exits_nonzero(tmp_path: Path) -> None:
    ledger = {"entries": [{"id": "g2", "requirement": "dropped", "ambiguity_score": 1, "impact_weight": 2, "status": "accepted", "evidence_channels": ["from-user"]}]}
    handoff = "# Part 1\nnothing cited\n# Part 2\n"
    session = _coverage_session(tmp_path, ledger, handoff)
    result = CLI_RUNNER.invoke(make_app(handoff_coverage.main), [str(session), "--advisory"])
    assert result.exit_code == 0, result.output
    assert "coverage_ok: no" in result.output


def test_contract_digest_binds_fenced_part1_content() -> None:
    original = make_gate_handoff("R1").replace(
        "## Change Impact & Preservation",
        "```json\n{\"schema_version\": 1}\n```\n## Change Impact & Preservation",
    )
    changed = original.replace('"schema_version": 1', '"schema_version": 2')

    assert implementation_gate.contract_digest(original) != implementation_gate.contract_digest(changed)


def test_ledger_entry_rejects_unknown_keys_and_conflicting_aliases() -> None:
    with pytest.raises(ValidationError):
        parse_entries(
            json.dumps(
                [
                    {
                        "id": "R1",
                        "ambiguity_score": 0,
                        "impact_weight": 1,
                        "statuz": "accepted",
                    }
                ]
            )
        )
    with pytest.raises(ValidationError):
        parse_entries(
            json.dumps(
                [
                    {
                        "id": "R1",
                        "ambiguity_score": 0,
                        "ambiguity": 3,
                        "impact_weight": 1,
                    }
                ]
            )
        )


def test_session_update_rejects_unknown_add_key(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {
            "add": [
                {
                    "id": "bad",
                    "requirement": "typo must fail",
                    "ambiguity_score": 1,
                    "impact_weight": 1,
                    "statuz": "accepted",
                }
            ]
        },
    )

    assert result.exit_code != 0
    assert "statuz" in result.output


@pytest.mark.parametrize("origin", ["lens:quality", "contrarian", "fold-back", "scored-question"])
def test_material_change_resets_dry_sweep_saturation(tmp_path: Path, origin: str) -> None:
    session = make_session(tmp_path, dry_sweeps_in_row=2, sweeps_run=2)
    result = run_update(
        session,
        {
            "add": [
                {
                    "id": "quality-gap",
                    "requirement": "latency target unknown",
                    "ambiguity_score": 2,
                    "impact_weight": 2,
                    "status": "draft",
                    "evidence_channels": ["assumption"],
                    "origin": origin,
                }
            ]
        },
    )

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["dry_sweeps_in_row"] == 0


def test_material_change_in_dry_sweep_delta_does_not_count_as_dry(tmp_path: Path) -> None:
    session = make_session(tmp_path, dry_sweeps_in_row=2, sweeps_run=2)
    result = run_update(
        session,
        {
            "set": [{"id": "g1", "requirement": "materially changed requirement"}],
            "event": "sweep-free",
            "sweep_result": "dry",
        },
    )

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["dry_sweeps_in_row"] == 0


def test_material_change_invalidates_bound_build_contract_review(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        build_contract_tested=True,
        build_contract_digest="reviewed-digest",
        build_contract_reviewer="critic",
    )

    result = run_update(
        session,
        {"set": [{"id": "g1", "requirement": "materially changed requirement"}]},
    )

    assert result.exit_code == 0, result.output
    protocol = read_protocol(session)
    assert protocol["build_contract_tested"] is False
    assert protocol["build_contract_digest"] == ""
    assert protocol["build_contract_reviewer"] == ""


def test_checkpoint_requires_at_least_one_covered_id(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(session, {"checkpoint_confirm": {"ids": [], "fatigue": False}})

    assert result.exit_code != 0
    assert "at least 1" in result.output


def test_fatigue_checkpoint_rejects_blank_id(tmp_path: Path) -> None:
    session = make_session(tmp_path, checkpoint_since_last_material_change=False)

    result = run_update(
        session,
        {"checkpoint_confirm": {"ids": ["  "], "fatigue": True}},
    )

    assert result.exit_code != 0
    assert read_protocol(session)["checkpoint_since_last_material_change"] is False


def test_fatigue_checkpoint_rejects_unknown_id_before_counting(tmp_path: Path) -> None:
    session = make_session(tmp_path, checkpoint_since_last_material_change=False)

    result = run_update(
        session,
        {"checkpoint_confirm": {"ids": ["missing"], "fatigue": True}},
    )

    assert result.exit_code != 0
    protocol = read_protocol(session)
    assert protocol["falsification_checkpoints_run"] == 1
    assert protocol["checkpoint_since_last_material_change"] is False


def test_set_normalizes_legacy_ledger_aliases(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    ledger = json.loads((session / "ledger.json").read_text(encoding="utf-8"))
    entry = ledger["entries"][0]
    entry["ambiguity"] = entry.pop("ambiguity_score")
    entry["weight"] = entry.pop("impact_weight")
    entry["channels"] = entry.pop("evidence_channels")
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    result = run_update(
        session,
        {
            "set": [
                {
                    "id": "g1",
                    "ambiguity_score": 1,
                    "impact_weight": 3,
                    "evidence_channels": ["from-user", "from-code"],
                },
            ],
        },
    )

    assert result.exit_code == 0, result.output
    written = json.loads((session / "ledger.json").read_text(encoding="utf-8"))["entries"][0]
    assert "ambiguity" not in written
    assert "weight" not in written
    assert "channels" not in written


def test_session_update_rejects_direct_history_forgery(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = run_update(
        session,
        {
            "protocol": {
                "residual_history": [1, 1, 1],
                "gap_count_history": [1, 1, 1],
                "stagnation_escalated_at": 3,
            }
        },
    )

    assert result.exit_code != 0
    assert "event-managed" in result.output


def test_session_update_replaces_questions_in_same_commit(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    (session / "questions.json").write_text('{"questions": []}\n', encoding="utf-8")
    candidate = {
        "id": "Q1",
        "question": "Which identifier form is valid?",
        "impact": 3,
        "branch_split": 3,
        "uncertainty_reduction": 3,
        "coverage": 3,
        "user_cost": 1,
        "redundancy": 0,
    }
    result = run_update(session, {"questions": [candidate]})

    assert result.exit_code == 0, result.output
    written = json.loads((session / "questions.json").read_text(encoding="utf-8"))
    assert written == {"questions": [{**candidate, "target_ids": []}]}


def test_material_ledger_change_clears_unreplaced_question_queue(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    (session / "questions.json").write_text(
        json.dumps({"questions": [{"id": "stale"}]}),
        encoding="utf-8",
    )

    result = run_update(
        session,
        {"set": [{"id": "g1", "requirement": "changed requirement"}]},
    )

    assert result.exit_code == 0, result.output
    assert json.loads((session / "questions.json").read_text(encoding="utf-8")) == {
        "questions": [],
    }


def test_non_ledger_event_preserves_existing_question_queue(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    queue = {"questions": []}
    (session / "questions.json").write_text(json.dumps(queue), encoding="utf-8")

    result = run_update(
        session,
        {"checkpoint_confirm": {"ids": ["g1"], "fatigue": True}},
    )

    assert result.exit_code == 0, result.output
    assert json.loads((session / "questions.json").read_text(encoding="utf-8")) == queue


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda text: text.replace(
                "| REQ-001 unit | test | `okcmd --version` | exits 0 |\n",
                "",
            ),
            "Kind=test",
        ),
        (
            lambda text: text.replace(
                "| critic | none | none | no fold-back required | none |",
                "| critic | unresolved API choice | vague success criterion | no | API choice; criterion |",
            ),
            "unresolved",
        ),
        (
            lambda text: text.replace("Ship the settled behavior.", "<One sentence.>"),
            "placeholder",
        ),
    ],
)
def test_gate_rejects_missing_test_unresolved_review_and_placeholders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutator: Callable[[str], str],
    expected: str,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "gate-session"
    session.mkdir()
    write_session(session)
    handoff = mutator(make_gate_handoff("R1"))
    write_gate_handoff(session, handoff)
    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert expected in result.output


def test_gate_accepts_fresh_review_findings_that_were_resolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "gate-session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1").replace(
        "| critic | none | none | no fold-back required | none |",
        "| critic | password reset semantics | test-double escape | "
        "folded back into REQ-001; verification rebound to live surface | none |",
    )
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 0, result.output
    assert "implementation_ready: yes" in result.output


def test_gate_rejects_negated_fresh_review_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "gate-session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1").replace(
        "| critic | none | none | no fold-back required | none |",
        "| critic | API ambiguity | none | not folded back; ignored | none |",
    )
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "disposition" in result.output


def test_gate_allows_literal_html_and_inline_code_markup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "gate-session"
    session.mkdir()
    write_session(session)
    handoff = (
        make_gate_handoff("R1")
        .replace(
            "Ship the settled behavior.",
            "Render <button>Save</button> and preserve literal `<identifier>` documentation.",
        )
        .replace(
            "| command module | add identifier validation |",
            "| command module | render <input> and <br> markup |",
        )
    )
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 0, result.output


def test_worked_example_passes_the_composite_gate() -> None:
    example_path = Path(__file__).resolve().parent.parent / "references" / "example-session.md"
    example = example_path.read_text(encoding="utf-8")

    def embedded_json(heading: str) -> str:
        match = re.search(
            rf"^## {re.escape(heading)}.*?^```json\n(.*?)^```$",
            example,
            re.MULTILINE | re.DOTALL,
        )
        assert match is not None
        return match.group(1)

    entries = ambiguity_ledger.parse_entries(embedded_json("ledger.json (final)"))
    protocol = protocol_state.parse_state(embedded_json("protocol.json (final)"))
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries),
        protocol_state.summarize_protocol(protocol),
        example,
        search_path=verification_lint.host_search_path(),
        workdir=Path.cwd(),
        protocol=protocol,
    )

    assert result.implementation_ready, result.failures


def test_gate_requires_decision_log_instruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_gate_command(tmp_path, monkeypatch)
    session = tmp_path / "gate-session"
    session.mkdir()
    write_session(session)
    handoff = make_gate_handoff("R1").replace(
        " Standing instruction: append every unforced decision to "
        "`.ultimateinterview/<slug>/decisions.jsonl` as you make it "
        "(the execution substrate does not auto-log).",
        "",
    )
    write_gate_handoff(session, handoff)

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--gate"])

    assert result.exit_code == 1
    assert "decisions.jsonl" in result.output


def test_session_init_rejects_symlinked_state_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".ultimateinterview").symlink_to(outside, target_is_directory=True)

    result = run_init(tmp_path, "escaped")

    assert result.exit_code != 0
    assert "symlink" in result.output.lower()
    assert not (outside / "escaped").exists()


def test_session_init_failure_removes_partial_session_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commit(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("injected init failure")

    monkeypatch.setattr(atomic_write, "commit_text_files", fail_commit)

    result = run_init(tmp_path, "retryable")

    assert result.exit_code != 0
    assert not (tmp_path / ".ultimateinterview" / "retryable").exists()


def test_session_init_ignores_orphaned_hidden_staging_directory(tmp_path: Path) -> None:
    state_root = tmp_path / ".ultimateinterview"
    orphan = state_root / ".retryable.init-interrupted"
    orphan.mkdir(parents=True)
    (orphan / "ledger.json").write_text("partial", encoding="utf-8")

    result = run_init(tmp_path, "retryable")

    assert result.exit_code == 0, result.output
    assert (state_root / "retryable" / "ledger.json").is_file()


def test_session_status_recovers_interrupted_generation_before_read(tmp_path: Path) -> None:
    session = write_session(tmp_path)
    ledger_path = session / "ledger.json"
    protocol_path = session / "protocol.json"
    original_ledger = ledger_path.read_text(encoding="utf-8")
    original_protocol = protocol_path.read_text(encoding="utf-8")
    atomic_write.write_recovery_journal(
        {ledger_path: original_ledger, protocol_path: original_protocol},
        root=session,
    )
    ledger_path.write_text("[]", encoding="utf-8")

    result = CLI_RUNNER.invoke(make_app(session_status.main), [str(session), "--format", "json"])

    assert result.exit_code == 0, result.output
    assert ledger_path.read_text(encoding="utf-8") == original_ledger
    assert not (session / atomic_write.JOURNAL_NAME).exists()


def test_explicit_status_paths_recover_interrupted_generation_before_read(
    tmp_path: Path,
) -> None:
    session = write_session(tmp_path)
    ledger_path = session / "ledger.json"
    protocol_path = session / "protocol.json"
    original_ledger = ledger_path.read_text(encoding="utf-8")
    original_protocol = protocol_path.read_text(encoding="utf-8")
    atomic_write.write_recovery_journal(
        {ledger_path: original_ledger, protocol_path: original_protocol},
        root=session,
    )
    ledger_path.write_text("[]", encoding="utf-8")

    result = CLI_RUNNER.invoke(
        make_app(session_status.main),
        ["--ledger", str(ledger_path), "--protocol", str(protocol_path), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    assert ledger_path.read_text(encoding="utf-8") == original_ledger
    assert not (session / atomic_write.JOURNAL_NAME).exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_ledger_track_validates_and_normalizes_locality_keys() -> None:
    track = ambiguity_ledger.LedgerTrack.model_validate(
        {
            "category": "scope",
            "domain": " Checkout-Flow ",
            "target_surfaces": ["./SRC/Checkout.py", "src/checkout.py"],
        },
    )
    assert track.category is ambiguity_ledger.TrackCategory.SCOPE
    assert track.domain == "checkout-flow"
    assert track.target_surfaces == ("src/checkout.py",)

    with pytest.raises(ValidationError, match="track must include"):
        ambiguity_ledger.LedgerTrack()
    for surface in ("/private/checkout.py", "../checkout.py"):
        with pytest.raises(ValidationError):
            ambiguity_ledger.LedgerTrack(target_surfaces=(surface,))


def test_question_target_ids_preserve_io_without_changing_rank_or_score() -> None:
    payload = {
        "id": "Q-track",
        "question": "Which surface is in scope?",
        "impact": 3,
        "branch_split": 4,
        "uncertainty_reduction": 3,
        "coverage": 2,
        "user_cost": 1,
        "redundancy": 0,
        "target_ids": ["g2", "g1"],
    }
    with_targets = parse_questions(json.dumps({"questions": [payload]}))
    without_targets = parse_questions(
        json.dumps({"questions": [{key: value for key, value in payload.items() if key != "target_ids"}]}),
    )

    ranked_with_targets = rank_questions(with_targets, top=1)
    ranked_without_targets = rank_questions(without_targets, top=1)
    assert ranked_with_targets[0].target_ids == ("g2", "g1")
    assert (
        ranked_with_targets[0].rank,
        ranked_with_targets[0].id,
        ranked_with_targets[0].score,
    ) == (
        ranked_without_targets[0].rank,
        ranked_without_targets[0].id,
        ranked_without_targets[0].score,
    )
    assert json.loads(question_score.rankings_as_json(ranked_with_targets))["ranked_questions"][0][
        "target_ids"
    ] == ["g2", "g1"]
    assert "g2, g1" in question_score.rankings_as_markdown(ranked_with_targets)


def test_scored_question_derives_and_caps_question_track_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    for _ in range(protocol_state.LOCALITY_WINDOW + 1):
        result = run_update(
            session,
            {"event": "scored-question", "asked_question_id": "Q1"},
        )
        assert result.exit_code == 0, result.output

    snapshots = read_protocol(session)["recent_question_tracks"]
    assert len(snapshots) == protocol_state.LOCALITY_WINDOW
    assert snapshots == [
        {
            "asked_question_id": "Q1",
            "ledger_ids": ["g1"],
            "categories": ["scope"],
            "domains": ["test-session"],
            "target_files": ["src/g1.py"],
        },
    ] * protocol_state.LOCALITY_WINDOW
    assert protocol_state.locality_repeated_keys(
        parse_state(json.dumps(read_protocol(session))).recent_question_tracks,
    ) == {
        "categories": ("scope",),
        "domains": ("test-session",),
        "target_files": ("src/g1.py",),
    }


@pytest.mark.parametrize(
    ("asked_question_id", "target_ids", "message"),
    [
        ("missing", None, "absent"),
        ("Q1", [], "has no target_ids"),
        ("Q1", ["missing-ledger"], "absent from the current ledger"),
    ],
)
def test_scored_question_rejects_invalid_booking(
    tmp_path: Path,
    asked_question_id: str,
    target_ids: list[str] | None,
    message: str,
) -> None:
    session = make_session(tmp_path)
    if target_ids is not None:
        questions = json.loads((session / "questions.json").read_text(encoding="utf-8"))
        questions["questions"][0]["target_ids"] = target_ids
        (session / "questions.json").write_text(json.dumps(questions), encoding="utf-8")

    result = run_update(
        session,
        {"event": "scored-question", "asked_question_id": asked_question_id},
    )

    assert result.exit_code != 0
    assert message in result.output


def test_pressure_followup_inherits_most_recent_question_track(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    assert run_update(
        session,
        {"event": "scored-question", "asked_question_id": "Q1"},
    ).exit_code == 0
    before = read_protocol(session)["recent_question_tracks"]
    result = run_update(
        session,
        {"event": "pressure-followup", "pressure_parent": "Q1"},
    )

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["recent_question_tracks"] == [before[0], before[0]]


@pytest.mark.parametrize(
    "delta",
    [
        {"event": "sweep-free", "sweep_result": "dry"},
        {"checkpoint_confirm": {"ids": ["g1"], "fatigue": True}},
        {"event": "contrarian-free"},
    ],
)
def test_boundary_events_clear_question_track_history(tmp_path: Path, delta: dict) -> None:
    session = make_session(tmp_path)
    assert run_update(
        session,
        {"event": "scored-question", "asked_question_id": "Q1"},
    ).exit_code == 0

    result = run_update(session, delta)

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["recent_question_tracks"] == []


def test_session_update_rejects_direct_question_track_history_patch(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = run_update(
        session,
        {
            "protocol": {
                "recent_question_tracks": [
                    {
                        "asked_question_id": "forged",
                        "ledger_ids": ["g1"],
                        "categories": ["scope"],
                        "domains": [],
                        "target_files": [],
                    },
                ],
            },
        },
    )

    assert result.exit_code != 0
    assert "event-managed" in result.output


def test_legacy_protocol_without_question_track_history_parses_empty() -> None:
    assert parse_state(make_protocol()).recent_question_tracks == ()


def test_locality_updates_do_not_change_readiness_material_state(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    before_entries = parse_entries((session / "ledger.json").read_text(encoding="utf-8"))
    before_protocol = parse_state((session / "protocol.json").read_text(encoding="utf-8"))
    before_ledger_summary = summarize_ambiguity(before_entries)
    before_protocol_summary = summarize_protocol(before_protocol)
    before_gate_failures = ambiguity_ledger.gate_failures(before_entries)
    before_gate_ready = implementation_gate.evaluate(
        before_entries,
        before_ledger_summary,
        before_protocol_summary,
        "",
        protocol=before_protocol,
    ).implementation_ready
    tracked_state = (
        "build_contract_tested",
        "build_contract_digest",
        "build_contract_reviewer",
        "checkpoint_since_last_material_change",
        "dry_sweeps_in_row",
    )
    before_values = tuple(getattr(before_protocol, field) for field in tracked_state)
    before_ready = session_status.is_ready(before_ledger_summary, before_protocol_summary)

    result = run_update(
        session,
        {
            "event": "scored-question",
            "asked_question_id": "Q1",
            "set": [
                {
                    "id": "g1",
                    "track": {
                        "category": "behavior",
                        "domain": "checkout-flow",
                        "target_surfaces": ["./SRC/Checkout.py"],
                    },
                },
            ],
        },
    )

    assert result.exit_code == 0, result.output
    after_entries = parse_entries((session / "ledger.json").read_text(encoding="utf-8"))
    after_protocol = parse_state((session / "protocol.json").read_text(encoding="utf-8"))
    after_ledger_summary = summarize_ambiguity(after_entries)
    after_protocol_summary = summarize_protocol(after_protocol)
    assert tuple(getattr(after_protocol, field) for field in tracked_state) == before_values
    assert ambiguity_ledger.gate_failures(after_entries) == before_gate_failures
    assert session_status.is_ready(after_ledger_summary, after_protocol_summary) is before_ready
    assert implementation_gate.evaluate(
        after_entries,
        after_ledger_summary,
        after_protocol_summary,
        "",
        protocol=after_protocol,
    ).implementation_ready is before_gate_ready
    assert after_protocol.recent_question_tracks


def test_question_track_snapshot_normalizes_sets() -> None:
    snapshot = protocol_state.QuestionTrackSnapshot(
        asked_question_id=" Q1 ",
        ledger_ids=("g2", "g1", "g1"),
        categories=("Scope", "scope"),
        domains=("Checkout", "checkout"),
        target_files=("SRC/Checkout.py", "src/checkout.py"),
    )

    assert snapshot == protocol_state.QuestionTrackSnapshot(
        asked_question_id="Q1",
        ledger_ids=("g1", "g2"),
        categories=("scope",),
        domains=("checkout",),
        target_files=("src/checkout.py",),
    )


def test_multi_track_batch_clears_question_track_history(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    assert run_update(
        session,
        {"event": "scored-question", "asked_question_id": "Q1"},
    ).exit_code == 0
    result = run_update(
        session,
        {
            "event": "batch",
            "add": [
                {
                    "id": "b1",
                    "ambiguity_score": 1,
                    "impact_weight": 1,
                    "track": {"category": "scope"},
                },
                {
                    "id": "b2",
                    "ambiguity_score": 1,
                    "impact_weight": 1,
                    "track": {"category": "quality"},
                },
            ],
        },
    )

    assert result.exit_code == 0, result.output
    assert read_protocol(session)["recent_question_tracks"] == []
