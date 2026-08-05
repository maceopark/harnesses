"""Pure study selection, comparison, and promotion rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationMetrics:
    contamination: int = 0
    leakage: int = 0
    invented_requirements: int = 0
    compatibility_regressions: int = 0
    implementation_decisions: int = 0
    material_implementation_decisions: int = 0
    approved_material_blockers: int = 0
    implementation_ready: int = 0
    owner_recall: float = 0.0
    repository_fidelity: float = 0.0
    redundant_questions: int = 0

    def __post_init__(self) -> None:
        numeric = self.__dict__
        if any(value < 0 for value in numeric.values()):
            raise ValueError("validation metrics cannot be negative")


def _validation_rank(metrics: ValidationMetrics) -> tuple[float, ...]:
    safe = metrics.contamination == 0 and metrics.leakage == 0
    return (
        int(safe),
        -(metrics.invented_requirements + metrics.compatibility_regressions),
        metrics.implementation_ready,
        -metrics.material_implementation_decisions,
        -metrics.approved_material_blockers,
        metrics.owner_recall,
        metrics.repository_fidelity,
        -metrics.redundant_questions,
    )


def select_validation_winner(
    baseline: ValidationMetrics, candidate: ValidationMetrics
) -> str:
    """Admit only a defect-free, fully ready candidate; otherwise keep baseline."""

    del baseline  # Validation is an absolute admission gate, not a relative contest.
    return "candidate" if passes_absolute_zero_validation_gate(candidate) else "baseline"


def passes_absolute_zero_validation_gate(metrics: ValidationMetrics) -> bool:
    """Require all three validation cases and zero tolerance for known defects."""

    return (
        metrics.implementation_ready == 3
        and metrics.contamination == 0
        and metrics.leakage == 0
        and metrics.invented_requirements == 0
        and metrics.compatibility_regressions == 0
        and metrics.material_implementation_decisions == 0
        and metrics.approved_material_blockers == 0
    )


def development_non_regression_rank(metrics: ValidationMetrics) -> tuple[float, ...]:
    """Rank development candidates after enforcing contract-error non-regression."""

    return _validation_rank(metrics)


def development_candidate_is_eligible(
    baseline: ValidationMetrics, candidate: ValidationMetrics,
) -> bool:
    """Reject any candidate that adds a known defect on development."""

    defect_fields = (
        "contamination", "leakage", "invented_requirements",
        "compatibility_regressions", "material_implementation_decisions",
        "approved_material_blockers", "redundant_questions",
    )
    return (
        all(getattr(candidate, field) <= getattr(baseline, field) for field in defect_fields)
        and candidate.implementation_ready >= baseline.implementation_ready
        and development_non_regression_rank(candidate) > development_non_regression_rank(baseline)
    )


@dataclass(frozen=True)
class HoldoutMetrics:
    completed_cases: int
    implementation_ready: int
    contamination: int
    leakage: int
    invented_requirements: int
    compatibility_regressions: int
    implementation_decisions: int
    material_implementation_decisions: int
    approved_material_blockers: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.__dict__.values()):
            raise ValueError("holdout metrics cannot be negative")


def passes_strict_holdout_gate(metrics: HoldoutMetrics) -> bool:
    """Require all four completed cases and zero tolerance for every defect."""

    return (
        metrics.completed_cases == 4
        and metrics.implementation_ready == 4
        and metrics.contamination == 0
        and metrics.leakage == 0
        and metrics.invented_requirements == 0
        and metrics.compatibility_regressions == 0
        and metrics.material_implementation_decisions == 0
        and metrics.approved_material_blockers == 0
    )
