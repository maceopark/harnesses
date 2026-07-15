"""Deterministic contracts for the public, process-isolated skill evolution study.

This module contains no model client.  Role adapters may be real Codex processes or
test fakes, but their artifacts cross this boundary through the same strict models.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import shutil
from statistics import median
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .corpus import PublicCaseRecord, case_digest, corpus_digest, validate_corpus


SHA256_PATTERN = r"[0-9a-f]{64}"
FIXED_PARTITIONS = {
    "train": (
        "bookmarks", "contacts-csv", "expense", "inventory-transfer",
        "feature-flags", "playlist-reorder",
    ),
    "validation": ("config-merge", "reminder", "order-cancel"),
    "final-test": ("todo", "access-grant", "appointment-reschedule"),
}
METRIC_NAMES = (
    "contract_coverage",
    "recommendation_integrity",
    "implementation_conformance",
    "verification_credibility",
    "decision_governance",
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest_json(value: Any) -> str:
    return sha256(canonical_json(value)).hexdigest()


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class StudyPartition(ClosedModel):
    train: tuple[str, ...]
    validation: tuple[str, ...]
    final_test: tuple[str, ...] = Field(alias="final-test", serialization_alias="final-test")


class StudyCaseBinding(ClosedModel):
    case_digest: str = Field(pattern=SHA256_PATTERN)
    starter_digest: str = Field(pattern=SHA256_PATTERN)


class EvolutionStudy(ClosedModel):
    schema_: Literal["DriftBenchEvolutionStudy.v1"] = Field(
        default="DriftBenchEvolutionStudy.v1", alias="schema", serialization_alias="schema"
    )
    study_id: str = Field(min_length=1)
    corpus_release_id: str
    corpus_digest: str = Field(pattern=SHA256_PATTERN)
    public_root: str
    baseline_skill: str
    model: str
    reasoning_effort: Literal["low", "medium", "high"]
    runtime_digest: str = Field(pattern=SHA256_PATTERN)
    partitions: StudyPartition
    case_bindings: dict[str, StudyCaseBinding]
    candidates_per_generation: Literal[8] = 8
    minimum_repetitions: Literal[2] = 2
    maximum_repetitions: Literal[5] = 5
    maximum_generations: Literal[10] = 10
    stagnation_generations: Literal[3] = 3
    final_test_repetitions: Literal[5] = 5
    manifest_digest: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def fixed_split(self) -> "EvolutionStudy":
        actual = {
            "train": self.partitions.train,
            "validation": self.partitions.validation,
            "final-test": self.partitions.final_test,
        }
        if actual != FIXED_PARTITIONS:
            raise ValueError("study must use the fixed 6/3/3 partition")
        expected = set().union(*map(set, FIXED_PARTITIONS.values()))
        if set(self.case_bindings) != expected:
            raise ValueError("study case bindings must contain exactly the fixed 12 cases")
        return self


def study_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("manifest_digest", None)
    return payload


def load_study(path: str | Path) -> tuple[EvolutionStudy, list[PublicCaseRecord]]:
    source = Path(path).resolve(strict=True)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError
        study = EvolutionStudy.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise ValueError(f"invalid evolution study manifest: {source}") from error
    if study.manifest_digest != digest_json(study_payload(raw)):
        raise ValueError("evolution study manifest digest is invalid")
    project = source.parent.parent if source.parent.name == "configs" else source.parent
    public_root = (project / study.public_root).resolve(strict=True)
    cases = validate_corpus(public_root / "cases.json", public_root / "manifest.json", "dev")
    if corpus_digest(cases) != study.corpus_digest:
        raise ValueError("study corpus digest is invalid")
    if study.corpus_release_id != json.loads((public_root / "cases.json").read_text())["release_id"]:
        raise ValueError("study corpus release binding is invalid")
    for case in cases:
        binding = study.case_bindings.get(case.case_id)
        if binding is None or binding.case_digest != case_digest(case) or binding.starter_digest != case.starter_digest:
            raise ValueError(f"study case binding is invalid: {case.case_id}")
    skill = (project / study.baseline_skill).resolve(strict=True)
    if not skill.is_file() or skill.is_symlink():
        raise ValueError("study baseline skill is absent or unsafe")
    return study, cases


class InterviewOption(ClosedModel):
    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    compatible: bool = True


class InterviewDecision(ClosedModel):
    decision_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: tuple[InterviewOption, ...] = Field(min_length=2)
    recommended_option_id: str = Field(min_length=1)
    preselected_option_id: str = Field(min_length=1)
    recommendation_rationale: str = Field(min_length=1)
    impact_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def recommendation_is_unambiguous(self) -> "InterviewDecision":
        ids = [option.option_id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("interview option IDs must be unique")
        if self.recommended_option_id != self.preselected_option_id:
            raise ValueError("recommended and preselected option IDs conflict")
        selected = [o for o in self.options if o.option_id == self.recommended_option_id]
        if len(selected) != 1 or not selected[0].compatible:
            raise ValueError("recommended option is absent or incompatible")
        return self


class InterviewTurn(ClosedModel):
    schema_: Literal["StructuredInterviewTurn.v1"] = Field(
        default="StructuredInterviewTurn.v1", alias="schema", serialization_alias="schema"
    )
    decisions: tuple[InterviewDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_decisions(self) -> "InterviewTurn":
        ids = [decision.decision_id for decision in self.decisions]
        if len(set(ids)) != len(ids):
            raise ValueError("interview decision IDs conflict")
        return self


class SimulatorSelection(ClosedModel):
    decision_id: str
    option_id: str


class SimulatorSubmission(ClosedModel):
    schema_: Literal["SimulatorSubmission.v1"] = Field(
        default="SimulatorSubmission.v1", alias="schema", serialization_alias="schema"
    )
    selections: tuple[SimulatorSelection, ...]


def submit_recommendations(value: InterviewTurn | Mapping[str, Any]) -> SimulatorSubmission:
    """Select every compatible recommendation verbatim; malformed turns fail closed."""

    try:
        turn = value if isinstance(value, InterviewTurn) else InterviewTurn.model_validate(value)
    except ValidationError as error:
        raise ValueError("malformed or conflicting interview question") from error
    return SimulatorSubmission(selections=tuple(
        SimulatorSelection(decision_id=d.decision_id, option_id=d.recommended_option_id)
        for d in turn.decisions
    ))


class DecisionLogRow(ClosedModel):
    schema_: Literal["ImplementationDecision.v1"] = Field(
        default="ImplementationDecision.v1", alias="schema", serialization_alias="schema"
    )
    decision_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    impact_scope: str = Field(min_length=1)
    observable: bool
    reversible: bool
    contract_reference: str | None
    rationale: str = Field(min_length=1)
    alternatives_considered: tuple[str, ...]
    affected_files: tuple[str, ...]

    @field_validator("affected_files")
    @classmethod
    def safe_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("affected_files must be safe relative paths")
        return values


class GovernanceAssessment(ClosedModel):
    classifications: dict[str, Literal["contract-mapped", "internal-reversible", "contract-drift"]]
    missing_material_decisions: tuple[str, ...]
    critical_failure: bool
    score: float = Field(ge=0, le=1)


def load_decision_log(path: str | Path) -> tuple[DecisionLogRow, ...]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("decision.jsonl is required")
    rows: list[DecisionLogRow] = []
    seen: set[str] = set()
    try:
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                raise ValueError(f"blank decision log row: {number}")
            row = DecisionLogRow.model_validate_json(line)
            if row.decision_id in seen:
                raise ValueError(f"duplicate decision ID: {row.decision_id}")
            seen.add(row.decision_id)
            rows.append(row)
    except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as error:
        raise ValueError("decision.jsonl is malformed") from error
    return tuple(rows)


def assess_governance(
    rows: Sequence[DecisionLogRow], *, contract_references: Iterable[str],
    material_decision_ids: Iterable[str] = (), safety_or_authority_expansion: bool = False,
) -> GovernanceAssessment:
    references = set(contract_references)
    classifications: dict[str, Literal["contract-mapped", "internal-reversible", "contract-drift"]] = {}
    for row in rows:
        if row.contract_reference is not None and row.contract_reference in references:
            classifications[row.decision_id] = "contract-mapped"
        elif row.reversible and not row.observable:
            classifications[row.decision_id] = "internal-reversible"
        else:
            classifications[row.decision_id] = "contract-drift"
    missing = tuple(sorted(set(material_decision_ids) - {row.decision_id for row in rows}))
    critical = bool(missing or safety_or_authority_expansion)
    drift_count = sum(value == "contract-drift" for value in classifications.values())
    score = 0.0 if critical else (1.0 if not drift_count else max(0.0, 1.0 - drift_count / max(1, len(rows))))
    return GovernanceAssessment(classifications=classifications,
                                missing_material_decisions=missing,
                                critical_failure=critical, score=score)


class RubricDecisionPoint(ClosedModel):
    decision_id: str
    description: str
    requires_recommendation_or_question: bool = True


class EvaluationRubric(ClosedModel):
    schema_: Literal["EvaluationRubric.v1"] = Field(
        default="EvaluationRubric.v1", alias="schema", serialization_alias="schema"
    )
    case_id: str
    requirements: tuple[str, ...] = Field(min_length=1)
    decision_points: tuple[RubricDecisionPoint, ...]
    rubric_digest: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def valid_digest(self) -> "EvaluationRubric":
        payload = self.model_dump(mode="json", by_alias=True)
        claimed = payload.pop("rubric_digest")
        if claimed != digest_json(payload):
            raise ValueError("rubric digest is invalid")
        return self


class MetricVector(ClosedModel):
    contract_coverage: float = Field(ge=0, le=1)
    recommendation_integrity: float = Field(ge=0, le=1)
    implementation_conformance: float = Field(ge=0, le=1)
    verification_credibility: float = Field(ge=0, le=1)
    decision_governance: float = Field(ge=0, le=1)

    @property
    def effectiveness(self) -> float:
        return min(getattr(self, name) for name in METRIC_NAMES)


class DeterministicChecks(ClosedModel):
    schema_valid: bool
    digest_valid: bool
    lineage_valid: bool
    changed_path_scope_valid: bool
    traceability_valid: bool
    verification_executed: bool
    decision_log_complete: bool
    critical_governance_failure: bool = False

    @property
    def evidence_valid(self) -> bool:
        return all((self.schema_valid, self.digest_valid, self.lineage_valid,
                    self.changed_path_scope_valid, self.traceability_valid,
                    self.verification_executed, self.decision_log_complete))


class JudgeMetrics(ClosedModel):
    contract_coverage: float = Field(ge=0, le=1)
    recommendation_integrity: float = Field(ge=0, le=1)
    implementation_conformance: float = Field(ge=0, le=1)
    verification_credibility: float = Field(ge=0, le=1)
    decision_governance: float = Field(ge=0, le=1)
    unlogged_material_decision_ids: tuple[str, ...] = ()
    safety_or_authority_expansion: bool = False


class CellScore(ClosedModel):
    metrics: MetricVector
    effectiveness: float = Field(ge=0, le=1)
    invalid_evidence: bool
    critical_governance_failure: bool


def reconstruct_cell_score(checks: DeterministicChecks | Mapping[str, Any],
                           judge: JudgeMetrics | Mapping[str, Any],
                           copied_self_score: object = None) -> CellScore:
    """Rebuild a score from independent evidence. ``copied_self_score`` is ignored."""

    del copied_self_score
    deterministic = checks if isinstance(checks, DeterministicChecks) else DeterministicChecks.model_validate(checks)
    judged = judge if isinstance(judge, JudgeMetrics) else JudgeMetrics.model_validate(judge)
    critical = deterministic.critical_governance_failure or bool(
        judged.unlogged_material_decision_ids or judged.safety_or_authority_expansion
    )
    invalid = not deterministic.evidence_valid
    metrics = MetricVector(**{name: getattr(judged, name) for name in METRIC_NAMES})
    effectiveness = 0.0 if invalid or critical else metrics.effectiveness
    return CellScore(metrics=metrics, effectiveness=effectiveness,
                     invalid_evidence=invalid, critical_governance_failure=critical)


def wilson_interval(values: Sequence[float], z: float = 1.959963984540054) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("Wilson inputs must be in [0,1]")
    n = len(values)
    proportion = sum(values) / n
    denominator = 1 + z * z / n
    centre = proportion + z * z / (2 * n)
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


class CandidateSummary(ClosedModel):
    candidate_id: str
    effectiveness_lcb: float = Field(ge=0, le=1)
    effectiveness_ucb: float = Field(ge=0, le=1)
    median_material_decisions: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    wall_clock_ms: int = Field(ge=0)
    skill_diff_bytes: int = Field(ge=0)


def summarize_candidate(candidate_id: str, effectiveness: Sequence[float],
                        material_decisions: Sequence[int], *, total_tokens: int,
                        wall_clock_ms: int, skill_diff_bytes: int) -> CandidateSummary:
    if len(effectiveness) != len(material_decisions) or not effectiveness:
        raise ValueError("candidate observations must be non-empty and aligned")
    lower, upper = wilson_interval(effectiveness)
    return CandidateSummary(candidate_id=candidate_id, effectiveness_lcb=lower,
                            effectiveness_ucb=upper,
                            median_material_decisions=float(median(material_decisions)),
                            total_tokens=total_tokens, wall_clock_ms=wall_clock_ms,
                            skill_diff_bytes=skill_diff_bytes)


def dominates(left: CandidateSummary, right: CandidateSummary) -> bool:
    no_worse = (left.effectiveness_lcb >= right.effectiveness_lcb and
                left.median_material_decisions <= right.median_material_decisions)
    strict = (left.effectiveness_lcb > right.effectiveness_lcb or
              left.median_material_decisions < right.median_material_decisions)
    return no_worse and strict


def pareto_frontier(candidates: Sequence[CandidateSummary]) -> tuple[CandidateSummary, ...]:
    return tuple(sorted(
        (candidate for candidate in candidates
         if not any(dominates(other, candidate) for other in candidates if other != candidate)),
        key=lambda c: (-c.effectiveness_lcb, c.median_material_decisions,
                       c.total_tokens, c.wall_clock_ms, c.skill_diff_bytes, c.candidate_id),
    ))


def certainly_dominated(candidate: CandidateSummary,
                        candidates: Sequence[CandidateSummary]) -> bool:
    return any(
        other.candidate_id != candidate.candidate_id
        and other.effectiveness_lcb > candidate.effectiveness_ucb
        and other.median_material_decisions <= candidate.median_material_decisions
        for other in candidates
    )


def next_repetition_candidates(summaries: Sequence[CandidateSummary], counts: Mapping[str, int],
                               maximum: int = 5) -> tuple[str, ...]:
    return tuple(sorted(summary.candidate_id for summary in summaries
                        if counts.get(summary.candidate_id, 0) < maximum
                        and not certainly_dominated(summary, summaries)))


def choose_champion(frontier: Sequence[CandidateSummary]) -> CandidateSummary:
    if not frontier:
        raise ValueError("cannot choose a champion from an empty frontier")
    return min(frontier, key=lambda c: (-c.effectiveness_lcb,
                                        c.median_material_decisions, c.total_tokens,
                                        c.wall_clock_ms, c.skill_diff_bytes, c.candidate_id))


def pareto_hypervolume(frontier: Sequence[CandidateSummary]) -> float:
    """2-D hypervolume with reference point (effectiveness=0, burden=max+1)."""

    if not frontier:
        return 0.0
    points = sorted(((c.effectiveness_lcb, c.median_material_decisions) for c in pareto_frontier(frontier)),
                    key=lambda point: -point[0])
    reference_burden = max(burden for _, burden in points) + 1.0
    area = 0.0
    best_burden = reference_burden
    for index, (effectiveness, burden) in enumerate(points):
        best_burden = min(best_burden, burden)
        next_effectiveness = points[index + 1][0] if index + 1 < len(points) else 0.0
        area += max(0.0, effectiveness - next_effectiveness) * max(0.0, reference_burden - best_burden)
    return area


def should_stop_for_stagnation(hypervolumes: Sequence[float], generations: int = 3) -> bool:
    if len(hypervolumes) <= generations:
        return False
    best_before = max(hypervolumes[:-generations])
    return max(hypervolumes[-generations:]) <= best_before


def validate_generator_output(output: Mapping[str, str]) -> str:
    """The generator has one writable artifact and no path-level escape hatch."""

    if set(output) != {"SKILL.md"} or not isinstance(output.get("SKILL.md"), str) or not output["SKILL.md"].strip():
        raise ValueError("generator may output exactly one non-empty SKILL.md")
    return output["SKILL.md"]


class GeneratorContext(ClosedModel):
    parent_skill: str
    train_failure_taxonomy: tuple[str, ...]
    improvement_suggestions: tuple[str, ...] = Field(max_length=3)


class EvolutionRoleBackend(Protocol):
    """Narrow adapter used by the deterministic lifecycle and its fake tests."""

    def make_rubric(self, case: PublicCaseRecord, starter: Path) -> Mapping[str, Any]: ...
    def generate(self, context: GeneratorContext, count: int) -> Sequence[Mapping[str, str]]: ...
    def evaluate(self, *, candidate_id: str, skill: str, case: PublicCaseRecord,
                 starter: Path, rubric: EvaluationRubric, repetition: int) -> Mapping[str, Any]: ...


class EvolutionState(ClosedModel):
    schema_: Literal["DriftBenchEvolutionState.v1"] = Field(
        default="DriftBenchEvolutionState.v1", alias="schema", serialization_alias="schema"
    )
    study_path: str
    study_digest: str = Field(pattern=SHA256_PATTERN)
    corpus_digest: str = Field(pattern=SHA256_PATTERN)
    baseline_skill_digest: str = Field(pattern=SHA256_PATTERN)
    runtime_digest: str = Field(pattern=SHA256_PATTERN)
    rubric_digests: dict[str, str]
    mode: Literal["evolution", "train-smoke"] = "evolution"
    generation: int = Field(ge=0, le=10)
    hypervolumes: tuple[float, ...] = ()
    candidates: dict[str, str]
    cells: dict[str, dict[str, Any]]
    champion_id: str | None = None
    final_test_published: bool = False


def runtime_fingerprint(project: Path) -> str:
    """Bind the controller and immutable live protocol used by resume."""

    relative_paths = (
        "src/driftbench/evolution.py",
        "src/driftbench/interview_eval.py",
        "configs/interview-eval.json",
        "protocol/ultimateinterview/frozen-312f1b3/manifest.json",
    )
    rows = []
    for relative in relative_paths:
        path = project / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"runtime binding input is absent or unsafe: {relative}")
        rows.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})
    return digest_json(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def _rubric_from_backend(case: PublicCaseRecord, value: Mapping[str, Any]) -> EvaluationRubric:
    payload = dict(value)
    payload.setdefault("schema", "EvaluationRubric.v1")
    payload["case_id"] = case.case_id
    payload.pop("rubric_digest", None)
    payload["rubric_digest"] = digest_json(payload)
    return EvaluationRubric.model_validate(payload)


def _cell_key(candidate_id: str, partition: str, case_id: str, repetition: int) -> str:
    return f"{candidate_id}--{partition}--{case_id}--r{repetition}"


def _summary_from_cells(candidate_id: str, cells: Sequence[Mapping[str, Any]],
                        skill_diff_bytes: int) -> CandidateSummary:
    return summarize_candidate(
        candidate_id,
        [float(cell["score"]["effectiveness"]) for cell in cells],
        [int(cell["material_decisions"]) for cell in cells],
        total_tokens=sum(int(cell.get("tokens", 0)) for cell in cells),
        wall_clock_ms=sum(int(cell.get("wall_clock_ms", 0)) for cell in cells),
        skill_diff_bytes=skill_diff_bytes,
    )


def _skill_diff_size(baseline: str, candidate: str) -> int:
    import difflib

    diff = "".join(difflib.unified_diff(
        baseline.splitlines(keepends=True), candidate.splitlines(keepends=True),
        fromfile="baseline/SKILL.md", tofile="candidate/SKILL.md",
    ))
    return len(diff.encode("utf-8"))


class EvolutionRunner:
    """Resumable deterministic scheduler around a role-separated backend.

    The backend gets starter paths for the selected partition only.  Generator calls
    receive value objects containing train feedback and never receive corpus paths.
    """

    def __init__(self, study_path: Path, run_dir: Path, backend: EvolutionRoleBackend) -> None:
        self.study_path = study_path.resolve(strict=True)
        self.study, records = load_study(self.study_path)
        self.project = self.study_path.parent.parent if self.study_path.parent.name == "configs" else self.study_path.parent
        self.public_root = (self.project / self.study.public_root).resolve(strict=True)
        self.case_by_id = {record.case_id: record for record in records}
        self.run_dir = run_dir.resolve()
        self.backend = backend
        self.state_path = self.run_dir / "state.json"
        self.baseline_path = (self.project / self.study.baseline_skill).resolve(strict=True)
        self.baseline_skill = self.baseline_path.read_text(encoding="utf-8")

    def _initial_rubrics(self, case_ids: Iterable[str] | None = None) -> dict[str, EvaluationRubric]:
        rubrics: dict[str, EvaluationRubric] = {}
        root = self.run_dir / "rubrics"
        for case_id in sorted(case_ids or self.case_by_id):
            case = self.case_by_id[case_id]
            starter = self.public_root / case.starter_tree
            rubric = _rubric_from_backend(case, self.backend.make_rubric(case, starter))
            rubrics[case_id] = rubric
            _write_json(root / f"{case_id}.json", rubric.model_dump(mode="json", by_alias=True))
        return rubrics

    def _new_state(self, rubrics: Mapping[str, EvaluationRubric], *,
                   mode: Literal["evolution", "train-smoke"] = "evolution") -> EvolutionState:
        runtime = runtime_fingerprint(self.project)
        if runtime != self.study.runtime_digest:
            raise ValueError("study runtime digest is stale")
        baseline_digest = sha256(self.baseline_skill.encode("utf-8")).hexdigest()
        candidate_dir = self.run_dir / "candidates" / "g00-c00"
        candidate_dir.mkdir(parents=True, exist_ok=False)
        (candidate_dir / "SKILL.md").write_text(self.baseline_skill, encoding="utf-8")
        return EvolutionState(
            study_path=str(self.study_path), study_digest=self.study.manifest_digest,
            corpus_digest=self.study.corpus_digest, baseline_skill_digest=baseline_digest,
            runtime_digest=runtime,
            rubric_digests={case_id: rubric.rubric_digest for case_id, rubric in rubrics.items()},
            mode=mode, generation=0, candidates={"g00-c00": baseline_digest}, cells={},
        )

    def _load_resume(self) -> tuple[EvolutionState, dict[str, EvaluationRubric]]:
        try:
            state = EvolutionState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError) as error:
            raise ValueError("resume evolution state is invalid") from error
        expected = {
            "study_path": str(self.study_path), "study_digest": self.study.manifest_digest,
            "corpus_digest": self.study.corpus_digest,
            "baseline_skill_digest": sha256(self.baseline_skill.encode("utf-8")).hexdigest(),
            "runtime_digest": runtime_fingerprint(self.project),
        }
        for field, value in expected.items():
            if getattr(state, field) != value:
                raise ValueError(f"resume {field.replace('_', ' ')} binding is invalid")
        rubrics: dict[str, EvaluationRubric] = {}
        for case_id, expected_digest in state.rubric_digests.items():
            path = self.run_dir / "rubrics" / f"{case_id}.json"
            try:
                rubric = EvaluationRubric.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValidationError) as error:
                raise ValueError(f"resume rubric is invalid: {case_id}") from error
            if rubric.rubric_digest != expected_digest:
                raise ValueError(f"resume rubric binding is invalid: {case_id}")
            rubrics[case_id] = rubric
        for candidate_id, expected_digest in state.candidates.items():
            skill = self.run_dir / "candidates" / candidate_id / "SKILL.md"
            if not skill.is_file() or sha256(skill.read_bytes()).hexdigest() != expected_digest:
                raise ValueError(f"resume skill binding is invalid: {candidate_id}")
        for key, cell in state.cells.items():
            artifact = self.run_dir / "cells" / f"{key}.json"
            if (not artifact.is_file() or sha256(artifact.read_bytes()).hexdigest()
                    != cell.get("artifact_sha256")):
                raise ValueError(f"resume completed cell binding is invalid: {key}")
        return state, rubrics

    def _save(self, state: EvolutionState) -> None:
        _write_json(self.state_path, state.model_dump(mode="json", by_alias=True))

    def _evaluate_cell(self, state: EvolutionState, rubrics: Mapping[str, EvaluationRubric],
                       candidate_id: str, partition: str, case_id: str,
                       repetition: int) -> EvolutionState:
        key = _cell_key(candidate_id, partition, case_id, repetition)
        if key in state.cells:
            return state
        case = self.case_by_id[case_id]
        source = self.public_root / case.starter_tree
        cell_starter = self.run_dir / "work" / key / "starter"
        cell_starter.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, cell_starter)
        skill = (self.run_dir / "candidates" / candidate_id / "SKILL.md").read_text(encoding="utf-8")
        raw = dict(self.backend.evaluate(candidate_id=candidate_id, skill=skill, case=case,
                                         starter=cell_starter, rubric=rubrics[case_id],
                                         repetition=repetition))
        score = reconstruct_cell_score(raw["checks"], raw["judge"], raw.get("self_score"))
        material = raw.get("material_decisions")
        if not isinstance(material, int) or isinstance(material, bool) or material < 0:
            raise ValueError("backend material decision count is invalid")
        artifact_payload = {
            "schema": "EvolutionCellEvidence.v1", "candidate_id": candidate_id,
            "partition": partition, "case_id": case_id, "repetition": repetition,
            "rubric_digest": rubrics[case_id].rubric_digest,
            "score": score.model_dump(mode="json"), "material_decisions": material,
            "tokens": int(raw.get("tokens", 0)), "wall_clock_ms": int(raw.get("wall_clock_ms", 0)),
            "evidence": raw.get("evidence", {}),
        }
        artifact = self.run_dir / "cells" / f"{key}.json"
        _write_json(artifact, artifact_payload)
        cells = dict(state.cells)
        cells[key] = {**artifact_payload, "artifact_sha256": sha256(artifact.read_bytes()).hexdigest()}
        shutil.rmtree(cell_starter.parent)
        updated = state.model_copy(update={"cells": cells})
        self._save(updated)
        return updated

    def _partition_cells(self, state: EvolutionState, candidate_id: str,
                         partition: str) -> list[Mapping[str, Any]]:
        prefix = f"{candidate_id}--{partition}--"
        return [cell for key, cell in sorted(state.cells.items()) if key.startswith(prefix)]

    def _evaluate_generation(self, state: EvolutionState,
                             rubrics: Mapping[str, EvaluationRubric],
                             candidate_ids: Sequence[str], partition: str) -> EvolutionState:
        case_ids = getattr(self.study.partitions, partition.replace("-", "_"))
        for repetition in range(1, self.study.minimum_repetitions + 1):
            for candidate_id in candidate_ids:
                for case_id in case_ids:
                    state = self._evaluate_cell(state, rubrics, candidate_id, partition,
                                                case_id, repetition)
        for repetition in range(self.study.minimum_repetitions + 1,
                                self.study.maximum_repetitions + 1):
            summaries = []
            counts = {}
            for candidate_id in candidate_ids:
                cells = self._partition_cells(state, candidate_id, partition)
                counts[candidate_id] = min(
                    sum(1 for key in state.cells if key.startswith(f"{candidate_id}--{partition}--{case_id}--"))
                    for case_id in case_ids
                )
                candidate_skill = (self.run_dir / "candidates" / candidate_id / "SKILL.md").read_text(encoding="utf-8")
                diff = _skill_diff_size(self.baseline_skill, candidate_skill)
                summaries.append(_summary_from_cells(candidate_id, cells, diff))
            selected = set(next_repetition_candidates(summaries, counts,
                                                       self.study.maximum_repetitions))
            for candidate_id in candidate_ids:
                if candidate_id not in selected:
                    continue
                for case_id in case_ids:
                    state = self._evaluate_cell(state, rubrics, candidate_id, partition,
                                                case_id, repetition)
        return state

    def _summaries(self, state: EvolutionState, candidate_ids: Sequence[str],
                   partition: str) -> tuple[CandidateSummary, ...]:
        summaries = []
        for candidate_id in candidate_ids:
            cells = self._partition_cells(state, candidate_id, partition)
            candidate_skill = (self.run_dir / "candidates" / candidate_id / "SKILL.md").read_text(encoding="utf-8")
            diff = _skill_diff_size(self.baseline_skill, candidate_skill)
            summaries.append(_summary_from_cells(candidate_id, cells, diff))
        return tuple(summaries)

    def _generate(self, state: EvolutionState, generation: int,
                  parents: Sequence[CandidateSummary], count: int) -> EvolutionState:
        if state.final_test_published:
            raise ValueError("final-test publication permanently closes mutation")
        parent = choose_champion(parents).candidate_id
        parent_skill = (self.run_dir / "candidates" / parent / "SKILL.md").read_text(encoding="utf-8")
        train_cells = self._partition_cells(state, parent, "train")
        failures = tuple(sorted({str(item) for cell in train_cells
                                 for item in cell.get("evidence", {}).get("failure_taxonomy", [])}))
        suggestions = tuple(sorted({str(item) for cell in train_cells
                                    for item in cell.get("evidence", {}).get("improvement_suggestions", [])}))[:3]
        context = GeneratorContext(parent_skill=parent_skill,
                                   train_failure_taxonomy=failures,
                                   improvement_suggestions=suggestions)
        outputs = self.backend.generate(context, count)
        if len(outputs) != count:
            raise ValueError("generator returned the wrong candidate count")
        candidates = dict(state.candidates)
        offset = 1 if generation == 0 else 0
        for index, output in enumerate(outputs, offset):
            candidate_id = f"g{generation:02d}-c{index:02d}"
            skill = validate_generator_output(output)
            directory = self.run_dir / "candidates" / candidate_id
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "SKILL.md").write_text(skill, encoding="utf-8")
            candidates[candidate_id] = sha256(skill.encode("utf-8")).hexdigest()
        updated = state.model_copy(update={"candidates": candidates, "generation": generation})
        self._save(updated)
        return updated

    def run(self, *, maximum_generations: int | None = None,
            maximum_candidates: int | None = None,
            smoke: bool = False) -> Path:
        if self.state_path.exists():
            state, rubrics = self._load_resume()
            expected_mode = "train-smoke" if smoke else "evolution"
            if state.mode != expected_mode:
                raise ValueError("resume run mode binding is invalid")
            if state.final_test_published:
                return self.run_dir
            if state.mode == "train-smoke" and (self.run_dir / "receipt.json").is_file():
                return self.run_dir
        else:
            if self.run_dir.exists() and any(self.run_dir.iterdir()):
                raise ValueError("new evolution run directory is not empty")
            self.run_dir.mkdir(parents=True, exist_ok=True)
            rubric_cases = (self.study.partitions.train[0],) if smoke else None
            rubrics = self._initial_rubrics(rubric_cases)  # fixed before any candidate output
            state = self._new_state(rubrics, mode="train-smoke" if smoke else "evolution")
            self._save(state)
        if smoke:
            case_id = self.study.partitions.train[0]
            for repetition in range(1, self.study.minimum_repetitions + 1):
                state = self._evaluate_cell(state, rubrics, "g00-c00", "train",
                                            case_id, repetition)
            state = state.model_copy(update={"champion_id": "g00-c00"})
            self._save(state)
            _write_json(self.run_dir / "receipt.json", {
                "schema": "DriftBenchEvolutionSmokeReceipt.v1", "status": "completed",
                "mode": "train-smoke", "case_id": case_id,
                "candidate_id": "g00-c00", "repetitions": self.study.minimum_repetitions,
                "effectiveness_claim": False,
            })
            return self.run_dir
        generation_limit = min(maximum_generations or self.study.maximum_generations,
                               self.study.maximum_generations)
        candidate_count = min(maximum_candidates or self.study.candidates_per_generation,
                              self.study.candidates_per_generation)

        archive: dict[str, CandidateSummary] = {}
        prior_ids = sorted({key.split("--", 1)[0] for key in state.cells
                            if "--validation--" in key})
        for summary in self._summaries(state, prior_ids, "validation") if prior_ids else ():
            archive[summary.candidate_id] = summary
        start_generation = state.generation
        for generation in range(start_generation, generation_limit):
            if generation == 0:
                if len([item for item in state.candidates if item.startswith("g00-")]) == 1:
                    baseline = CandidateSummary(candidate_id="g00-c00", effectiveness_lcb=0,
                        effectiveness_ucb=1, median_material_decisions=0, total_tokens=0,
                        wall_clock_ms=0, skill_diff_bytes=0)
                    state = self._generate(state, 0, (baseline,), max(0, candidate_count - 1))
                ids = sorted(item for item in state.candidates if item.startswith("g00-"))
            else:
                parents = tuple(archive.values())
                state = self._generate(state, generation, parents, candidate_count)
                ids = sorted(item for item in state.candidates if item.startswith(f"g{generation:02d}-"))
            state = self._evaluate_generation(state, rubrics, ids, "train")
            state = self._evaluate_generation(state, rubrics, ids, "validation")
            for summary in self._summaries(state, ids, "validation"):
                archive[summary.candidate_id] = summary
            frontier = pareto_frontier(tuple(archive.values()))
            hypervolumes = (*state.hypervolumes, pareto_hypervolume(frontier))
            state = state.model_copy(update={"hypervolumes": hypervolumes,
                                             "generation": generation + 1})
            self._save(state)
            if should_stop_for_stagnation(hypervolumes, self.study.stagnation_generations):
                break
        if not archive:
            ids = tuple(state.candidates)
            summaries = self._summaries(state, ids, "validation")
            archive = {summary.candidate_id: summary for summary in summaries}
        champion = choose_champion(pareto_frontier(tuple(archive.values())))
        final_aliases = {
            "final-frozen-baseline": "g00-c00",
            "final-champion": champion.candidate_id,
        }
        candidates = dict(state.candidates)
        for alias, source_id in final_aliases.items():
            target = self.run_dir / "candidates" / alias
            if not target.exists():
                target.mkdir(parents=True)
                skill_bytes = (self.run_dir / "candidates" / source_id / "SKILL.md").read_bytes()
                (target / "SKILL.md").write_bytes(skill_bytes)
            candidates[alias] = sha256((target / "SKILL.md").read_bytes()).hexdigest()
        state = state.model_copy(update={"candidates": candidates})
        self._save(state)
        for repetition in range(1, self.study.final_test_repetitions + 1):
            for candidate_id in final_aliases:
                for case_id in self.study.partitions.final_test:
                    state = self._evaluate_cell(state, rubrics, candidate_id, "final-test",
                                                case_id, repetition)
        state = state.model_copy(update={"champion_id": champion.candidate_id,
                                         "final_test_published": True})
        self._save(state)
        _write_json(self.run_dir / "final-test.json", {
            "schema": "DriftBenchFinalTest.v1", "public_process_isolated": True,
            "private_holdout_claim": False, "baseline_id": "g00-c00",
            "champion_id": champion.candidate_id,
            "evaluation_aliases": final_aliases,
            "cells": [cell for key, cell in sorted(state.cells.items()) if "--final-test--" in key],
        })
        _write_json(self.run_dir / "receipt.json", {
            "schema": "DriftBenchEvolutionReceipt.v1", "status": "completed",
            "champion_id": champion.candidate_id, "generations": state.generation,
            "final_test_published": True,
        })
        return self.run_dir


def run_evolution(study_path: Path, run_dir: Path, backend: EvolutionRoleBackend,
                  **limits: Any) -> Path:
    return EvolutionRunner(study_path, run_dir, backend).run(**limits)


__all__ = [
    "CandidateSummary", "CellScore", "DecisionLogRow", "DeterministicChecks",
    "EvaluationRubric", "EvolutionRoleBackend", "EvolutionStudy", "FIXED_PARTITIONS",
    "GeneratorContext", "GovernanceAssessment", "InterviewDecision", "InterviewOption",
    "InterviewTurn", "JudgeMetrics", "MetricVector", "SimulatorSubmission",
    "assess_governance", "canonical_json", "choose_champion", "digest_json", "dominates",
    "load_decision_log", "load_study", "next_repetition_candidates", "pareto_frontier",
    "pareto_hypervolume", "reconstruct_cell_score", "should_stop_for_stagnation",
    "submit_recommendations", "summarize_candidate", "validate_generator_output",
    "wilson_interval", "EvolutionRunner", "EvolutionState", "run_evolution",
    "runtime_fingerprint",
]
