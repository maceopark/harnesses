from dataclasses import replace

from swebench_interview_cases.study import (
    HoldoutMetrics,
    ValidationMetrics,
    passes_strict_holdout_gate,
    passes_absolute_zero_validation_gate,
    select_validation_winner,
)


def test_validation_is_lexicographic_and_tie_keeps_baseline():
    baseline = ValidationMetrics(implementation_ready=2, owner_recall=0.8)
    assert select_validation_winner(baseline, baseline) == "baseline"
    unsafe_but_otherwise_better = ValidationMetrics(
        leakage=1, implementation_ready=3, owner_recall=1.0, repository_fidelity=1.0
    )
    assert select_validation_winner(baseline, unsafe_but_otherwise_better) == "baseline"
    candidate = replace(baseline, implementation_ready=3)
    assert select_validation_winner(baseline, candidate) == "candidate"


def test_validation_rejects_even_an_improved_candidate_with_one_known_error():
    baseline = ValidationMetrics(invented_requirements=1, compatibility_regressions=1)
    candidate = ValidationMetrics(invented_requirements=0, compatibility_regressions=1)
    assert select_validation_winner(baseline, candidate) == "baseline"


def test_validation_allows_minor_implementation_decisions():
    baseline = ValidationMetrics(
        invented_requirements=1, implementation_decisions=0, implementation_ready=3,
    )
    candidate = ValidationMetrics(
        invented_requirements=0, implementation_decisions=1, implementation_ready=3,
    )
    assert select_validation_winner(baseline, candidate) == "candidate"


def test_validation_rejects_a_ready_candidate_with_a_material_implementation_decision():
    baseline = ValidationMetrics(implementation_decisions=0, implementation_ready=2)
    candidate = ValidationMetrics(
        implementation_decisions=1, material_implementation_decisions=1,
        implementation_ready=3,
    )
    assert select_validation_winner(baseline, candidate) == "baseline"


def test_validation_admits_only_absolute_zero_candidate():
    baseline = ValidationMetrics(invented_requirements=9)
    candidate = ValidationMetrics(implementation_ready=3)
    assert select_validation_winner(baseline, candidate) == "candidate"


def test_absolute_zero_validation_gate_rejects_every_defect_field():
    passing = ValidationMetrics(implementation_ready=3)
    assert passes_absolute_zero_validation_gate(passing)
    for field in (
        "contamination", "leakage", "invented_requirements",
        "compatibility_regressions", "material_implementation_decisions",
        "approved_material_blockers",
    ):
        assert not passes_absolute_zero_validation_gate(replace(passing, **{field: 1}))
    assert not passes_absolute_zero_validation_gate(replace(passing, implementation_ready=2))


def test_validation_ignores_raw_decision_count_after_contract_errors_and_readiness_tie():
    baseline = ValidationMetrics(implementation_decisions=0, implementation_ready=3)
    candidate = ValidationMetrics(implementation_decisions=1, implementation_ready=3)
    assert select_validation_winner(baseline, candidate) == "candidate"


def test_strict_holdout_gate_requires_every_absolute_condition():
    passing = HoldoutMetrics(
        completed_cases=4,
        implementation_ready=4,
        contamination=0,
        leakage=0,
        invented_requirements=0,
        compatibility_regressions=0,
        implementation_decisions=0,
        material_implementation_decisions=0,
        approved_material_blockers=0,
    )
    assert passes_strict_holdout_gate(passing)
    for field in passing.__dict__:
        if field == "implementation_decisions":
            assert passes_strict_holdout_gate(replace(passing, **{field: 3}))
            continue
        value = 3 if field in {"completed_cases", "implementation_ready"} else 1
        assert not passes_strict_holdout_gate(replace(passing, **{field: value}))
