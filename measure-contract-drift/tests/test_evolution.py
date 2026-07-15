from __future__ import annotations

import json
from pathlib import Path

import pytest

from driftbench.evolution import (
    CandidateSummary,
    DecisionLogRow,
    EvolutionRunner,
    FIXED_PARTITIONS,
    GeneratorContext,
    assess_governance,
    choose_champion,
    load_decision_log,
    load_study,
    next_repetition_candidates,
    pareto_frontier,
    reconstruct_cell_score,
    should_stop_for_stagnation,
    submit_recommendations,
    validate_generator_output,
)


PROJECT = Path(__file__).resolve().parents[1]
STUDY = PROJECT / "configs/evolution-study.json"


def _question() -> dict[str, object]:
    return {
        "schema": "StructuredInterviewTurn.v1",
        "decisions": [{
            "decision_id": "position-base", "question": "Which position base?",
            "options": [
                {"option_id": "one", "label": "One based", "compatible": True},
                {"option_id": "zero", "label": "Zero based", "compatible": True},
            ],
            "recommended_option_id": "one", "preselected_option_id": "one",
            "recommendation_rationale": "CLI users normally count from one",
            "impact_boundary": "Only POSITION parsing",
        }],
    }


def test_study_binds_exactly_twelve_public_cases_and_fixed_split() -> None:
    study, cases = load_study(STUDY)
    assert len(cases) == 12
    assert {case.case_id for case in cases} == set().union(*map(set, FIXED_PARTITIONS.values()))
    assert study.partitions.train == FIXED_PARTITIONS["train"]
    assert study.partitions.validation == FIXED_PARTITIONS["validation"]
    assert study.partitions.final_test == FIXED_PARTITIONS["final-test"]


def test_study_rejects_digest_drift(tmp_path: Path) -> None:
    document = json.loads(STUDY.read_text())
    document["partitions"]["train"][0] = "todo"
    path = tmp_path / "study.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="invalid evolution study manifest"):
        load_study(path)


def test_simulator_submits_every_recommendation_verbatim_and_rejects_conflict() -> None:
    submission = submit_recommendations(_question())
    assert [(row.decision_id, row.option_id) for row in submission.selections] == [
        ("position-base", "one")
    ]
    conflicting = _question()
    conflicting["decisions"][0]["preselected_option_id"] = "zero"  # type: ignore[index]
    with pytest.raises(ValueError, match="malformed or conflicting"):
        submit_recommendations(conflicting)


def _row(**updates: object) -> DecisionLogRow:
    value = {
        "schema": "ImplementationDecision.v1", "decision_id": "d1",
        "decision": "Use a helper", "trigger": "Repeated serialization",
        "impact_scope": "Internal implementation", "observable": False,
        "reversible": True, "contract_reference": None,
        "rationale": "Keeps writes centralized", "alternatives_considered": ["inline"],
        "affected_files": ["cli.py"],
    }
    value.update(updates)
    return DecisionLogRow.model_validate(value)


def test_decision_log_is_required_strict_and_allows_empty_file(tmp_path: Path) -> None:
    missing = tmp_path / "decision.jsonl"
    with pytest.raises(ValueError, match="required"):
        load_decision_log(missing)
    missing.write_text("")
    assert load_decision_log(missing) == ()
    missing.write_text("{}\n")
    with pytest.raises(ValueError, match="malformed"):
        load_decision_log(missing)


def test_governance_distinguishes_contract_internal_drift_and_missing() -> None:
    rows = (
        _row(decision_id="mapped", contract_reference="REQ-1"),
        _row(decision_id="internal"),
        _row(decision_id="visible", observable=True),
    )
    result = assess_governance(rows, contract_references={"REQ-1"},
                               material_decision_ids={"mapped", "missing"})
    assert result.classifications == {
        "mapped": "contract-mapped", "internal": "internal-reversible",
        "visible": "contract-drift",
    }
    assert result.missing_material_decisions == ("missing",)
    assert result.critical_failure is True
    assert result.score == 0


def test_score_is_rebuilt_from_independent_inputs_and_ignores_self_score() -> None:
    checks = {name: True for name in (
        "schema_valid", "digest_valid", "lineage_valid", "changed_path_scope_valid",
        "traceability_valid", "verification_executed", "decision_log_complete",
    )}
    judge = {
        "contract_coverage": .9, "recommendation_integrity": .8,
        "implementation_conformance": .7, "verification_credibility": .6,
        "decision_governance": .5,
    }
    score = reconstruct_cell_score(checks, judge, copied_self_score={"effectiveness": 1})
    assert score.effectiveness == .5
    judge["unlogged_material_decision_ids"] = ["missing"]
    assert reconstruct_cell_score(checks, judge).effectiveness == 0
    checks["digest_valid"] = False
    assert reconstruct_cell_score(checks, judge).invalid_evidence is True


def _summary(identity: str, low: float, high: float, burden: float,
             tokens: int = 0, wall: int = 0, diff: int = 0) -> CandidateSummary:
    return CandidateSummary(candidate_id=identity, effectiveness_lcb=low,
                            effectiveness_ucb=high, median_material_decisions=burden,
                            total_tokens=tokens, wall_clock_ms=wall, skill_diff_bytes=diff)


def test_pareto_adaptive_repetition_tie_break_and_stagnation_are_deterministic() -> None:
    strong = _summary("strong", .8, .9, 1)
    weak = _summary("weak", .2, .3, 2)
    lean = _summary("lean", .7, .85, 0)
    frontier = pareto_frontier((weak, strong, lean))
    assert [candidate.candidate_id for candidate in frontier] == ["strong", "lean"]
    assert next_repetition_candidates((weak, strong, lean),
                                      {"weak": 2, "strong": 2, "lean": 2}) == (
                                          "lean", "strong")
    tied = (_summary("more", .8, .9, 1, 20, 10, 5),
            _summary("less", .8, .9, 1, 10, 20, 5))
    assert choose_champion(tied).candidate_id == "less"
    assert should_stop_for_stagnation((.1, .2, .2, .2, .2)) is True


def test_generator_output_is_skill_only_and_suggestions_are_bounded() -> None:
    assert validate_generator_output({"SKILL.md": "# Skill"}) == "# Skill"
    with pytest.raises(ValueError, match="exactly one"):
        validate_generator_output({"SKILL.md": "x", "judge.py": "changed"})
    with pytest.raises(ValueError):
        GeneratorContext(parent_skill="x", train_failure_taxonomy=(),
                         improvement_suggestions=("1", "2", "3", "4"))


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.generator_contexts: list[GeneratorContext] = []

    def make_rubric(self, case: object, starter: Path) -> dict[str, object]:
        assert starter.is_dir()
        self.events.append(f"rubric:{getattr(case, 'case_id')}")
        return {"requirements": ["observable contract"], "decision_points": []}

    def generate(self, context: GeneratorContext, count: int) -> list[dict[str, str]]:
        assert len(self.events) == 12 or any(event.startswith("evaluate:") for event in self.events)
        self.events.append("generate")
        self.generator_contexts.append(context)
        return [{"SKILL.md": context.parent_skill + f"\n# variant {index}\n"}
                for index in range(count)]

    def evaluate(self, **values: object) -> dict[str, object]:
        candidate_id = str(values["candidate_id"])
        self.events.append(f"evaluate:{candidate_id}")
        effectiveness = .9 if candidate_id.endswith("c01") or candidate_id == "final-champion" else .6
        checks = {name: True for name in (
            "schema_valid", "digest_valid", "lineage_valid", "changed_path_scope_valid",
            "traceability_valid", "verification_executed", "decision_log_complete",
        )}
        judge = {name: effectiveness for name in (
            "contract_coverage", "recommendation_integrity", "implementation_conformance",
            "verification_credibility", "decision_governance",
        )}
        return {"checks": checks, "judge": judge,
                "material_decisions": 1 if effectiveness == .9 else 2,
                "tokens": 10, "wall_clock_ms": 5,
                "self_score": {"effectiveness": 1},
                "evidence": {"failure_taxonomy": ["train-only"],
                             "improvement_suggestions": ["one", "two", "three", "four"]}}


def test_fake_full_lifecycle_freezes_rubrics_repeats_and_final_test(tmp_path: Path) -> None:
    backend = FakeBackend()
    run_dir = tmp_path / "run"
    result = EvolutionRunner(STUDY, run_dir, backend).run(
        maximum_generations=1, maximum_candidates=2)
    state = json.loads((result / "state.json").read_text())
    assert backend.events[:12] == [f"rubric:{case_id}" for case_id in sorted(
        set().union(*map(set, FIXED_PARTITIONS.values())))]
    assert state["champion_id"] == "g00-c01"
    assert state["final_test_published"] is True
    final = json.loads((result / "final-test.json").read_text())
    assert final["private_holdout_claim"] is False
    assert len(final["cells"]) == 30
    assert {cell["repetition"] for cell in final["cells"]} == {1, 2, 3, 4, 5}
    assert all("validation" not in context.model_dump_json()
               and "final-test" not in context.model_dump_json()
               for context in backend.generator_contexts)

    class NoCalls(FakeBackend):
        def make_rubric(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise AssertionError("completed rubric must be reused")
        def generate(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
            raise AssertionError("finalized run must not mutate")
        def evaluate(self, **values: object) -> dict[str, object]:
            raise AssertionError("completed cell must be reused")

    assert EvolutionRunner(STUDY, run_dir, NoCalls()).run() == run_dir


def test_resume_rejects_completed_cell_tamper(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    EvolutionRunner(STUDY, run_dir, FakeBackend()).run(
        maximum_generations=1, maximum_candidates=1)
    cell = next((run_dir / "cells").glob("*.json"))
    cell.write_text(cell.read_text() + " ")
    with pytest.raises(ValueError, match="completed cell binding"):
        EvolutionRunner(STUDY, run_dir, FakeBackend()).run()


def test_live_smoke_is_one_train_case_one_candidate_and_no_claim(tmp_path: Path) -> None:
    backend = FakeBackend()
    run_dir = tmp_path / "smoke"
    EvolutionRunner(STUDY, run_dir, backend).run(smoke=True)
    state = json.loads((run_dir / "state.json").read_text())
    receipt = json.loads((run_dir / "receipt.json").read_text())
    assert list(state["rubric_digests"]) == ["bookmarks"]
    assert len(state["cells"]) == 2
    assert {cell["candidate_id"] for cell in state["cells"].values()} == {"g00-c00"}
    assert {cell["case_id"] for cell in state["cells"].values()} == {"bookmarks"}
    assert receipt["effectiveness_claim"] is False
    assert receipt["mode"] == "train-smoke"
    assert "generate" not in backend.events
