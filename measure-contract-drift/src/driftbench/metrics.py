"""Development-only weighted metrics and deterministic seeded bootstrap CIs.

These functions deliberately accept only development cases.  They expose no
holdout identifier, score, provider call, or full-v2 execution path.
"""

from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Self
from unicodedata import is_normalized

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import (
    CellRecord,
    CellStatus,
    DevelopmentArmScore,
    DevelopmentBootstrapCI,
    DevelopmentScore,
    FULL_V2_ARM_ID,
    NativeV1RuntimeReceipt,
    RunManifest,
    RunMode,
    RunState,
    RunStatus,
    Scorecard,
)
from .semantic import Assertion, AssertionComparison, ExecutableObservation, ObservationResult, compare_assertions
from .postmortem import PostmortemReport, PostmortemRequest
from .state import StateError, canonical_bytes, canonical_digest, digest_bytes, read_canonical_json
from .worker import (
    DeclaredArtifact,
    FreshRoleContext,
    LIFECYCLE_ARTIFACT_FILENAMES,
    LIFECYCLE_MANIFEST_FILENAME,
    transferred_artifacts,
)
from . import worker_launcher
SCORED_ARM_IDS = frozenset(
    {
        "direct-v1",
        "plan-v1",
        "ultimateinterview-current-v1-structural",
    }
)


def require_scored_arm_allowlist(arm_ids: Sequence[str] | Mapping[str, Any]) -> None:
    """Reject non-creditable fixtures and unknown arms before lifecycle replay."""
    values = tuple(arm_ids)
    if any(not isinstance(arm_id, str) for arm_id in values):
        raise ValueError("scored arm identifiers must be strings")
    rejected = tuple(sorted(set(values) - SCORED_ARM_IDS))
    if FULL_V2_ARM_ID in rejected:
        raise ValueError("full-v2 is a non-scored expected-fail conformance fixture")
    if rejected:
        raise ValueError(f"scored arm is not allowlisted: {', '.join(rejected)}")


class DevelopmentMetricCase(BaseModel):
    """One weighted case in the full development score denominator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    split: Literal["development"] = "development"
    weight: float
    observation_result: ObservationResult
    primary_credit: int

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("case_id must be nonblank")
        if not is_normalized("NFC", value):
            raise ValueError("case_id must be NFC-normalized")
        return value

    @field_validator("weight", mode="before")
    @classmethod
    def _reject_boolean_weight(cls, value: Any) -> float:
        if isinstance(value, bool) or type(value) not in (int, float):
            raise ValueError("weight must be a finite number, not a boolean")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError("weight must be finite and greater than zero")
        return float(value)

    @field_validator("primary_credit", mode="before")
    @classmethod
    def _reject_boolean_credit(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("primary_credit must be an integer, not a boolean")
        return value

    @field_validator("primary_credit")
    @classmethod
    def _validate_credit(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("primary_credit must be 0 or 1")
        return value

    @model_validator(mode="after")
    def _require_nonobservations_to_receive_no_credit(self) -> Self:
        if self.observation_result != "observed" and self.primary_credit != 0:
            raise ValueError("invalid or unobserved cases cannot receive primary credit")
        return self


class DevelopmentMetrics(BaseModel):
    """A weighted score whose denominator includes every development case."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope: Literal["development-only"] = "development-only"
    case_count: int = Field(ge=1)
    observed_case_count: int = Field(ge=0)
    unobserved_case_count: int = Field(ge=0)
    invalid_case_count: int = Field(ge=0)
    total_weight: float = Field(gt=0)
    weighted_primary_credit: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _require_complete_observation_denominator(self) -> Self:
        if self.case_count != (
            self.observed_case_count + self.unobserved_case_count + self.invalid_case_count
        ):
            raise ValueError("observation result counts must cover every metric case")
        return self


class BootstrapCI(BaseModel):
    """A deterministic percentile confidence interval over development cases."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope: Literal["development-only"] = "development-only"
    point_estimate: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    confidence: float = Field(gt=0, lt=1)
    seed: int
    resamples: int = Field(ge=1)

    @field_validator("seed", "resamples", mode="before")
    @classmethod
    def _reject_boolean_integer(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("integer fields must be integers, not booleans")
        return value

    @model_validator(mode="after")
    def _ordered_interval(self) -> Self:
        if not self.lower <= self.upper:
            raise ValueError("lower confidence bound must not exceed upper bound")
        return self


def _cases(
    values: Sequence[DevelopmentMetricCase | Mapping[str, Any]],
) -> list[DevelopmentMetricCase]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError("metric cases must be a sequence")
    if not values:
        raise ValueError("at least one development metric case is required")
    parsed: list[DevelopmentMetricCase] = []
    for value in values:
        if isinstance(value, DevelopmentMetricCase):
            parsed.append(value)
        elif isinstance(value, Mapping):
            parsed.append(DevelopmentMetricCase.model_validate(value))
        else:
            raise TypeError("each metric case must be a DevelopmentMetricCase or JSON object")
    case_ids = [case.case_id for case in parsed]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("metric case_id values must be unique")
    return sorted(parsed, key=lambda case: case.case_id)


def _weighted_primary_credit(cases: Sequence[DevelopmentMetricCase]) -> float:
    total_weight = math.fsum(case.weight for case in cases)
    return math.fsum(case.weight * case.primary_credit for case in cases) / total_weight


def compute_metrics(
    cases: Sequence[DevelopmentMetricCase | Mapping[str, Any]],
) -> DevelopmentMetrics:
    """Compute weighted credit with invalid and unobserved cases in the denominator."""
    parsed = _cases(cases)
    return DevelopmentMetrics(
        case_count=len(parsed),
        observed_case_count=sum(case.observation_result == "observed" for case in parsed),
        unobserved_case_count=sum(case.observation_result == "unobserved" for case in parsed),
        invalid_case_count=sum(case.observation_result == "invalid" for case in parsed),
        total_weight=math.fsum(case.weight for case in parsed),
        weighted_primary_credit=_weighted_primary_credit(parsed),
    )


def bootstrap_ci(
    cases: Sequence[DevelopmentMetricCase | Mapping[str, Any]],
    *,
    seed: int,
    resamples: int = 1_000,
    confidence: float = 0.95,
) -> BootstrapCI:
    """Return a seeded deterministic percentile CI for weighted development credit.

    Cases are sorted by ``case_id`` before sampling so equivalent case sets have
    the same result regardless of caller ordering.  Bounds use nearest-rank
    indices over the sorted bootstrap estimates.
    """
    if type(seed) is not int:
        raise TypeError("seed must be an integer, not a boolean")
    if type(resamples) is not int or resamples < 1:
        raise ValueError("resamples must be a positive integer, not a boolean")
    if isinstance(confidence, bool) or type(confidence) not in (int, float):
        raise TypeError("confidence must be a number, not a boolean")
    confidence_float = float(confidence)
    if not 0 < confidence_float < 1 or not math.isfinite(confidence_float):
        raise ValueError("confidence must be finite and strictly between zero and one")

    parsed = _cases(cases)
    generator = random.Random(seed)
    count = len(parsed)
    estimates = sorted(
        _weighted_primary_credit([parsed[generator.randrange(count)] for _ in range(count)])
        for _ in range(resamples)
    )
    tail = (1.0 - confidence_float) / 2.0
    lower_index = math.floor(tail * (resamples - 1))
    upper_index = math.ceil((1.0 - tail) * (resamples - 1))
    return BootstrapCI(
        point_estimate=_weighted_primary_credit(parsed),
        lower=estimates[lower_index],
        upper=estimates[upper_index],
        confidence=confidence_float,
        seed=seed,
        resamples=resamples,
    )
class ScorecardValidationError(ValueError):
    """Raised when a state-complete cell lacks a closed lifecycle evidence chain."""


def build_scorecard(*, run_dir: Path, state: RunState, manifest: RunManifest) -> Scorecard:
    """Score only completed fake-development cells with closed artifact evidence."""
    try:
        require_scored_arm_allowlist(manifest.arm_digests)
    except ValueError as error:
        raise ScorecardValidationError(str(error)) from error

    _require_manifest_state_closure(state, manifest)
    if manifest.mode is not RunMode.FAKE_DEV or manifest.partition != "dev":
        raise ScorecardValidationError("local scorecards require fake-development dev runs")
    if state.status is not RunStatus.COMPLETE or manifest.status is not RunStatus.COMPLETE:
        raise ScorecardValidationError("scorecard requires a complete manifest and state")
    if not state.cells:
        raise ScorecardValidationError("scorecard requires at least one completed cell")
    if any(cell.status is not CellStatus.COMPLETED for cell in state.cells):
        raise ScorecardValidationError("scorecard requires every cell to be lifecycle-completed")
    try:
        receipt_replay_context = worker_launcher.build_worker_receipt_replay_context(
            Path(__file__).resolve().parents[2]
        )
    except worker_launcher.WorkerPreflightError as error:
        raise ScorecardValidationError(
            f"pinned worker receipt replay inputs are invalid: {error}"
        ) from error


    metric_cases: list[DevelopmentMetricCase] = []
    cases_by_arm: dict[str, list[DevelopmentMetricCase]] = {}
    for cell in state.cells:
        metric_case = _validate_lifecycle_cell(
            run_dir,
            cell,
            manifest.worker_image,
            receipt_replay_context,
        )
        metric_cases.append(metric_case)
        cases_by_arm.setdefault(cell.identity.arm_id, []).append(metric_case)

    overall = compute_metrics(metric_cases)
    seed = int.from_bytes(
        sha256(f"{manifest.run_id}:{manifest.config_digest}:{manifest.corpus_digest}".encode("utf-8")).digest()[:8],
        "big",
    )
    interval = bootstrap_ci(metric_cases, seed=seed)
    arm_scores = tuple(
        DevelopmentArmScore(
            arm_id=arm_id,
            case_count=metrics.case_count,
            total_weight=metrics.total_weight,
            weighted_primary_credit=metrics.weighted_primary_credit,
        )
        for arm_id, metrics in sorted(
            ((arm_id, compute_metrics(cases)) for arm_id, cases in cases_by_arm.items()),
            key=lambda item: item[0],
        )
    )
    return Scorecard(
        run_id=state.run_id,
        mode=manifest.mode,
        scored=True,
        claim="deterministic-development-treatment",
        reason="deterministic-development-observations",
        completed_cells=len(state.cells),
        invalid_cells=0,
        manifest_digest=canonical_digest(manifest),
        state_digest=canonical_digest(state),
        development_metrics=DevelopmentScore(
            case_count=overall.case_count,
            total_weight=overall.total_weight,
            weighted_primary_credit=overall.weighted_primary_credit,
        ),
        bootstrap_ci=DevelopmentBootstrapCI(
            point_estimate=interval.point_estimate,
            lower=interval.lower,
            upper=interval.upper,
            confidence=interval.confidence,
            seed=interval.seed,
            resamples=interval.resamples,
        ),
        arm_scores=arm_scores,
    )


def _require_manifest_state_closure(state: RunState, manifest: RunManifest) -> None:
    if (
        state.run_id != manifest.run_id
        or state.config_digest != manifest.config_digest
        or state.corpus_digest != manifest.corpus_digest
        or state.arm_digests != manifest.arm_digests
        or state.worker_image != manifest.worker_image
    ):
        raise ScorecardValidationError("manifest-state input or worker image closure drift")
    for cell in state.cells:
        if cell.identity.partition != manifest.partition:
            raise ScorecardValidationError(f"cell partition drifts from manifest: {cell.cell_id}")
        if cell.identity.arm_id not in manifest.arm_digests:
            raise ScorecardValidationError(f"cell arm is absent from manifest: {cell.cell_id}")


def _validate_lifecycle_cell(
    run_dir: Path,
    cell: CellRecord,
    worker_image: str,
    receipt_replay_context: worker_launcher.WorkerReceiptReplayContext,
) -> DevelopmentMetricCase:
    cell_dir = run_dir / "cells" / cell.cell_id
    if not cell_dir.is_dir() or cell_dir.is_symlink():
        raise ScorecardValidationError(f"cell artifact directory is absent or unsafe: {cell.cell_id}")
    lifecycle_path = cell_dir / LIFECYCLE_MANIFEST_FILENAME
    lifecycle = _mapping(_read_document(lifecycle_path), "lifecycle manifest")
    schema = lifecycle.get("schema")
    if schema not in {"DevelopmentLifecycleManifest.v1", "DevelopmentLifecycleManifest.v2"} or lifecycle.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid lifecycle manifest: {cell.cell_id}")
    if schema == "DevelopmentLifecycleManifest.v2":
        return _validate_lifecycle_cell_v2(
            cell_dir,
            cell,
            lifecycle,
            worker_image,
            receipt_replay_context,
        )
    references = _references(lifecycle.get("artifacts"), set(LIFECYCLE_ARTIFACT_FILENAMES))
    documents = {
        artifact_id: _mapping(_read_document(cell_dir / reference.filename), artifact_id)
        for artifact_id, reference in references.items()
    }
    for artifact_id, reference in references.items():
        if reference.filename != LIFECYCLE_ARTIFACT_FILENAMES[artifact_id]:
            raise ScorecardValidationError(f"invalid lifecycle filename for {artifact_id}")
        if canonical_digest(documents[artifact_id]) != reference.digest:
            raise ScorecardValidationError(f"artifact digest drift for {artifact_id}")
    if references["cell-input"].digest != cell.input_digest:
        raise ScorecardValidationError(f"cell input is not bound to lifecycle: {cell.cell_id}")

    _validate_role_contexts(cell, documents)
    _validate_execution_receipts(documents)
    _validate_artifact_chains(cell, documents)
    _validate_attempt_terminal_receipts(cell_dir, cell, lifecycle, documents)
    _validate_cell_directory_closure(cell_dir, references)
    return _metric_case(cell, documents)


def _validate_role_contexts(cell: CellRecord, documents: Mapping[str, Mapping[str, Any]]) -> None:
    planner_context = _strict_model(FreshRoleContext, documents["planner-context"])
    implementer_context = _strict_model(FreshRoleContext, documents["implementer-context"])
    postmortem_context = _strict_model(FreshRoleContext, documents["postmortem-context"])
    transferred_artifacts(planner_context, {"cell-input": documents["cell-input"]})
    transferred_artifacts(
        implementer_context,
        {"handoff": documents["handoff"], "build-contract": documents["build-contract"]},
    )
    transferred_artifacts(
        postmortem_context,
        {
            "build-contract": documents["build-contract"],
            "evidence-manifest": documents["evidence-manifest"],
            "implementation": documents["implementation"],
            "observation": documents["observation"],
            "postmortem-request": documents["postmortem-request"],
        },
    )
    expected_contexts = {
        "planner-context": ("planner", f"planner-{cell.cell_id}"),
        "implementer-context": ("implementer", f"implementer-{cell.cell_id}"),
        "postmortem-context": ("postmortem", f"postmortem-{cell.cell_id}"),
    }
    for artifact_id, (role, context_id) in expected_contexts.items():
        context = _strict_model(FreshRoleContext, documents[artifact_id])
        if context.role.value != role or context.context_id != context_id:
            raise ScorecardValidationError(f"fresh context identity drift: {artifact_id}")


def _validate_execution_receipts(documents: Mapping[str, Mapping[str, Any]]) -> None:
    for role in ("planner", "implementer", "postmortem"):
        receipt = documents[f"{role}-execution"]
        context = documents[f"{role}-context"]
        if (
            receipt.get("schema") != "RoleExecutionReceipt.v1"
            or receipt.get("role") != role
            or receipt.get("context_id") != context.get("context_id")
            or receipt.get("provenance") != "deterministic-fake"
        ):
            raise ScorecardValidationError(f"invalid role execution receipt: {role}")
        session = _mapping(receipt.get("session"), f"{role} session")
        closed = _mapping(receipt.get("closed_session"), f"{role} closed session")
        if session.get("state") != "active" or closed.get("state") != "closed":
            raise ScorecardValidationError(f"role session was not opened and closed: {role}")
        if session.get("session_id") != closed.get("session_id"):
            raise ScorecardValidationError(f"role session closure drift: {role}")
        authorizations = receipt.get("authorizations")
        if not isinstance(authorizations, list) or not authorizations:
            raise ScorecardValidationError(f"role authorization evidence is absent: {role}")


def _validate_artifact_chains(cell: CellRecord, documents: Mapping[str, Mapping[str, Any]]) -> None:
    cell_input = documents["cell-input"]
    handoff = documents["handoff"]
    build_contract = documents["build-contract"]
    implementation = documents["implementation"]
    observation = documents["observation"]
    evidence_manifest = documents["evidence-manifest"]
    request = _strict_model(PostmortemRequest, documents["postmortem-request"])
    report = _strict_model(PostmortemReport, documents["postmortem-report"])

    if cell_input.get("schema") != "CellInput.v2" or cell_input.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid cell input: {cell.cell_id}")
    if handoff.get("schema") != "DevelopmentHandoff.v1" or handoff.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid handoff: {cell.cell_id}")
    if handoff.get("source_input_digest") != canonical_digest(cell_input):
        raise ScorecardValidationError(f"handoff is not bound to input: {cell.cell_id}")
    if build_contract.get("schema") != "DevelopmentBuildContract.v1" or build_contract.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid build contract: {cell.cell_id}")
    if build_contract.get("handoff_digest") != canonical_digest(handoff):
        raise ScorecardValidationError(f"build contract is not bound to handoff: {cell.cell_id}")
    if implementation.get("schema") != "DevelopmentImplementation.v1" or implementation.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid implementation artifact: {cell.cell_id}")
    if implementation.get("build_contract_digest") != canonical_digest(build_contract):
        raise ScorecardValidationError(f"implementation is not bound to build contract: {cell.cell_id}")
    if observation.get("schema") != "DevelopmentObservation.v1" or observation.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid observation artifact: {cell.cell_id}")
    if (
        observation.get("build_contract_digest") != canonical_digest(build_contract)
        or observation.get("implementation_digest") != canonical_digest(implementation)
    ):
        raise ScorecardValidationError(f"observation is not bound to implementation: {cell.cell_id}")
    evidence_references = _references(
        evidence_manifest.get("entries"),
        {"build-contract", "implementation", "observation"},
    )
    if evidence_manifest.get("schema") != "DevelopmentEvidenceManifest.v1" or evidence_manifest.get("cell_id") != cell.cell_id:
        raise ScorecardValidationError(f"invalid postmortem evidence manifest: {cell.cell_id}")
    for artifact_id, reference in evidence_references.items():
        if canonical_digest(documents[artifact_id]) != reference.digest:
            raise ScorecardValidationError(f"evidence manifest digest drift: {artifact_id}")
    if (
        request.run_id != report.run_id
        or request.cell_id != cell.cell_id
        or report.cell_id != cell.cell_id
        or request.request_id != report.request_id
        or request.fresh_context_id != report.fresh_context_id
        or request.artifact_manifest_digest != canonical_digest(evidence_manifest)
        or request.build_contract_digest != canonical_digest(build_contract)
        or request.implementation_digest != canonical_digest(implementation)
        or request.observation_digest != canonical_digest(observation)
    ):
        raise ScorecardValidationError(f"postmortem request closure drift: {cell.cell_id}")
    if (
        report.artifact_manifest_digest != request.artifact_manifest_digest
        or report.build_contract_digest != request.build_contract_digest
        or report.implementation_digest != request.implementation_digest
        or report.observation_digest != request.observation_digest
        or report.provenance != "deterministic-fake"
        or report.assurance != "none"
    ):
        raise ScorecardValidationError(f"postmortem report closure drift: {cell.cell_id}")


def _validate_attempt_terminal_receipts(
    cell_dir: Path,
    cell: CellRecord,
    lifecycle: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    *,
    recomputed_role_output_digests: Mapping[str, str] | None = None,
) -> None:
    attempt_path = cell_dir / f"attempt-{cell.attempt:06d}.json"
    terminal_path = cell_dir / _terminal_filename(cell.attempt)
    attempt = _mapping(_read_document(attempt_path), "attempt receipt")
    terminal = _mapping(_read_document(terminal_path), "terminal receipt")
    if cell.attempt_receipt_digest != digest_bytes(attempt_path.read_bytes()):
        raise ScorecardValidationError(f"attempt receipt state digest drift: {cell.cell_id}")
    if cell.terminal_receipt_digest != digest_bytes(terminal_path.read_bytes()):
        raise ScorecardValidationError(f"terminal receipt state digest drift: {cell.cell_id}")
    lifecycle_digest = canonical_digest(lifecycle)
    for receipt, schema in ((attempt, "AttemptReceipt.v2"), (terminal, "CellTerminalReceipt.v2")):
        if (
            receipt.get("schema") != schema
            or receipt.get("cell_id") != cell.cell_id
            or receipt.get("attempt") != cell.attempt
            or receipt.get("fence") != cell.fence
            or receipt.get("input_digest") != cell.input_digest
            or receipt.get("lifecycle_manifest_digest") != lifecycle_digest
            or receipt.get("provider_execution") != "oci-deterministic-worker"
            or receipt.get("claim") != "deterministic-development-treatment"
            or receipt.get("oci_receipts_required") is not True
        ):
            raise ScorecardValidationError(f"invalid terminal lifecycle receipt: {cell.cell_id}")
    if (
        terminal.get("status") != CellStatus.COMPLETED.value
        or terminal.get("semantic_result") not in {"observed", "unobserved"}
        or terminal.get("authoritative") is not True
        or terminal.get("attempt_receipt_digest") != canonical_digest(attempt)
    ):
        raise ScorecardValidationError(f"cell terminal closure is invalid: {cell.cell_id}")
    if terminal.get("observation_digest") != canonical_digest(documents["observation"]):
        raise ScorecardValidationError(f"terminal receipt observation drift: {cell.cell_id}")
    if terminal.get("comparison_digest") != canonical_digest(documents["observation"].get("comparison")):
        raise ScorecardValidationError(f"terminal receipt comparator drift: {cell.cell_id}")
    output_digests = attempt.get("role_output_digests")
    if not isinstance(output_digests, Mapping) or not output_digests:
        raise ScorecardValidationError(f"attempt lacks OCI role output closure: {cell.cell_id}")
    expected_outputs = (
        dict(recomputed_role_output_digests)
        if recomputed_role_output_digests is not None
        else {
            artifact_id: document.get("role_output_digest")
            for artifact_id, document in documents.items()
            if artifact_id.endswith("-execution")
        }
    )
    if output_digests != expected_outputs:
        raise ScorecardValidationError(f"attempt role output closure drift: {cell.cell_id}")


def _validate_cell_directory_closure(cell_dir: Path, references: Mapping[str, DeclaredArtifact]) -> None:
    expected = {LIFECYCLE_MANIFEST_FILENAME, *(reference.filename for reference in references.values())}
    for path in cell_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ScorecardValidationError(f"unsafe cell artifact closure entry: {path.name}")
        if path.name in expected:
            continue
        if _is_attempt_artifact(path.name) or _is_terminal_artifact(path.name):
            _read_document(path)
            continue
        raise ScorecardValidationError(f"undeclared cell artifact: {path.name}")


def _metric_case(cell: CellRecord, documents: Mapping[str, Mapping[str, Any]]) -> DevelopmentMetricCase:
    build_contract = documents["build-contract"]
    implementation = documents["implementation"]
    observation = documents["observation"]
    metric_case = _mapping(build_contract.get("metric_case"), "metric case")
    expected_atoms = _atom_ids(build_contract.get("acceptance_atom_ids"))
    implemented_atoms = _atom_ids(implementation.get("implemented_atom_ids"))
    observed_atoms = _atom_ids(observation.get("observed_atom_ids"))
    expected_credit = int(implemented_atoms == expected_atoms and observed_atoms == expected_atoms)
    if observation.get("primary_credit") != expected_credit:
        raise ScorecardValidationError(f"observation credit is not derived from implementation: {cell.cell_id}")
    if metric_case.get("case_id") != cell.cell_id:
        raise ScorecardValidationError(f"metric case identity drift: {cell.cell_id}")
    return DevelopmentMetricCase(
        case_id=cell.cell_id,
        weight=metric_case.get("weight"),
        primary_credit=expected_credit,
    )

def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _expected_role_artifacts(
    role: str,
    *,
    direct: bool,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if role == "planner":
        return {"cell-input": documents["cell-input"]}
    if role == "implementer":
        return (
            {"cell-input": documents["cell-input"]}
            if direct
            else {
                "build-contract": documents["build-contract"],
                "handoff": documents["handoff"],
            }
        )
    if role == "observation":
        return (
            {
                "cell-input": documents["cell-input"],
                "implementation": documents["implementation"],
            }
            if direct
            else {
                "build-contract": documents["build-contract"],
                "implementation": documents["implementation"],
            }
        )
    if role == "postmortem":
        artifacts = {
            "evidence-manifest": documents["evidence-manifest"],
            "implementation": documents["implementation"],
            "observation": documents["observation"],
            "postmortem-request": documents["postmortem-request"],
        }
        if not direct:
            artifacts["build-contract"] = documents["build-contract"]
        return artifacts
    raise ScorecardValidationError(f"unknown OCI execution role: {role}")


def _expected_role_output_ids(role: str, *, native_v1: bool) -> set[str]:
    if role == "planner":
        return {"execution", "handoff", "build-contract", *(("native-v1-runtime",) if native_v1 else ())}
    if role == "implementer":
        return {"execution", "implementation"}
    if role == "observation":
        return {"execution", "observation"}
    if role == "postmortem":
        return {"execution", "postmortem-report"}
    raise ScorecardValidationError(f"unknown OCI execution role: {role}")


def _worker_binding(cell: CellRecord, context: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "schema": "WorkerLaunchBinding.v1",
            "cell_id": cell.cell_id,
            "arm_id": cell.identity.arm_id,
            "input_digest": cell.input_digest,
            "context": context,
        }
    )


def _canonical_role_output(value: Any, role: str) -> Mapping[str, Any]:
    if not isinstance(value, str):
        raise ScorecardValidationError(f"OCI output receipt lacks retained canonical output: {role}")
    raw = value.encode("utf-8")
    try:
        output = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScorecardValidationError(f"OCI output receipt is invalid JSON: {role}") from error
    if not isinstance(output, Mapping) or canonical_bytes(output) != raw:
        raise ScorecardValidationError(f"OCI output receipt is not canonical JSON: {role}")
    return output


def _validate_native_v1_runtime(cell: CellRecord, document: Mapping[str, Any]) -> None:
    receipt = _strict_model(NativeV1RuntimeReceipt, document)
    from .native_snapshot import NativeSnapshotValidationError, validate_native_snapshot

    native_root = Path(__file__).resolve().parents[2] / "protocol" / "ultimateinterview" / "ui-native-77b0327-r4"
    fixture_path = native_root / "fixtures" / "native-v1-structural-valid.json"
    try:
        validation = validate_native_snapshot(native_root)
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes)
    except (NativeSnapshotValidationError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScorecardValidationError(f"canonical native v1 fixture cannot be replayed: {error}") from error
    invocation = _mapping(fixture.get("invocation"), "native fixture invocation")
    expected = _mapping(fixture.get("expected"), "native fixture expected")
    expected_gate = _mapping(expected.get("implementation_gate"), "native fixture implementation gate")
    runtime_gate = _mapping(
        receipt.native_runtime_receipt.get("implementation_gate"),
        "native runtime implementation gate",
    )
    if (
        fixture.get("native_snapshot_id") != validation.snapshot_id
        or fixture.get("scored_arm_id") != cell.identity.arm_id
        or receipt.cell_id != cell.cell_id
        or receipt.input_digest != cell.input_digest
        or receipt.snapshot_id != validation.snapshot_id
        or receipt.source_tree_digest != validation.source_tree_digest
        or receipt.source_record_count != validation.record_count
        or receipt.fixture_id != fixture.get("fixture_id")
        or receipt.fixture_digest != sha256(fixture_bytes).hexdigest()
        or receipt.invocation.model_dump(mode="json") != invocation
        or receipt.exit_code != expected.get("exit_code")
        or runtime_gate.get("implementation_ready") != expected_gate.get("implementation_ready")
    ):
        raise ScorecardValidationError(f"canonical native v1 runtime binding drift: {cell.cell_id}")
    native_stdout = (
        json.dumps(receipt.native_runtime_receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    if sha256(native_stdout).hexdigest() != receipt.stdout_digest:
        raise ScorecardValidationError(f"canonical native v1 runtime output digest drift: {cell.cell_id}")


def _validate_oci_role_outputs(
    cell: CellRecord,
    documents: Mapping[str, Mapping[str, Any]],
    execution_roles: Sequence[str],
    *,
    direct: bool,
    worker_image: str,
    receipt_replay_context: worker_launcher.WorkerReceiptReplayContext,
) -> dict[str, str]:
    recomputed: dict[str, str] = {}
    for role in execution_roles:
        execution_id = f"{role}-execution"
        execution = documents[execution_id]
        context = documents[f"{role}-context"]
        if (
            execution.get("schema") != "RoleExecutionReceipt.v1"
            or execution.get("role") != role
            or execution.get("context_id") != context.get("context_id")
            or execution.get("provenance") != "oci-deterministic-worker"
            or not _is_digest(execution.get("role_output_digest"))
        ):
            raise ScorecardValidationError(f"invalid OCI role execution receipt: {role}")
        binding_digest = _worker_binding(cell, context)
        native_v1 = role == "planner" and cell.identity.arm_id == "ultimateinterview-current-v1-structural"
        expected_input = {
            "schema": "RoleWorkInput.v1",
            "role": role,
            "binding_digest": binding_digest,
            "context": context,
            "artifacts": _expected_role_artifacts(role, direct=direct, documents=documents),
            "native_v1": native_v1,
        }
        output_read = _mapping(execution.get("output_read"), f"{role} output_read")
        output = _canonical_role_output(output_read.get("stdout"), role)
        try:
            worker_launcher.validate_worker_role_receipt_replay(
                receipt_replay_context,
                role=role,
                worker_image=worker_image,
                binding_digest=binding_digest,
                input_digest=canonical_digest(expected_input),
                output_read_stdout=output_read["stdout"],
                receipts={
                    receipt_name: execution.get(receipt_name)
                    for receipt_name in (
                        "isolation_launch",
                        "input_stage",
                        "output_read",
                        "workspace_cleanup",
                    )
                },
            )
        except (
            worker_launcher.WorkerPreflightError,
            worker_launcher.WorkerReceiptReplayError,
        ) as error:
            raise ScorecardValidationError(
                f"OCI receipt replay drift: {role}: {error}"
            ) from error
        expected_output_fields = {
            "schema",
            "role",
            "input_digest",
            "binding_digest",
            "context_digest",
            "documents",
            "provenance",
        }
        output_documents = output.get("documents")
        if (
            set(output) != expected_output_fields
            or output.get("schema") != "RoleWorkOutput.v1"
            or output.get("role") != role
            or output.get("input_digest") != canonical_digest(expected_input)
            or output.get("binding_digest") != binding_digest
            or output.get("context_digest") != canonical_digest(context)
            or output.get("provenance") != "oci-deterministic-worker"
            or not isinstance(output_documents, Mapping)
            or set(output_documents) != _expected_role_output_ids(role, native_v1=native_v1)
        ):
            raise ScorecardValidationError(f"OCI role output is not bound to canonical input: {role}")
        output_execution = _mapping(output_documents.get("execution"), f"{role} output execution")
        retained_execution = {
            key: value
            for key, value in execution.items()
            if key
            not in {
                "isolation_launch",
                "input_stage",
                "output_read",
                "workspace_cleanup",
                "role_output_digest",
            }
        }
        if canonical_digest(output_execution) != canonical_digest(retained_execution):
            raise ScorecardValidationError(f"OCI role execution output drift: {role}")
        for artifact_id in _expected_role_output_ids(role, native_v1=native_v1) - {"execution"}:
            artifact = _mapping(output_documents.get(artifact_id), f"{role} output {artifact_id}")
            if canonical_digest(artifact) != canonical_digest(documents[artifact_id]):
                raise ScorecardValidationError(f"OCI role output artifact drift: {role}/{artifact_id}")
        output_digest = canonical_digest(output)
        if execution.get("role_output_digest") != output_digest:
            raise ScorecardValidationError(f"OCI role output digest drift: {role}")
        recomputed[execution_id] = output_digest
    return recomputed

def _validate_lifecycle_cell_v2(
    cell_dir: Path,
    cell: CellRecord,
    lifecycle: Mapping[str, Any],
    worker_image: str,
    receipt_replay_context: worker_launcher.WorkerReceiptReplayContext,
) -> DevelopmentMetricCase:
    raw = lifecycle.get("artifacts")
    if not isinstance(raw, list) or not raw:
        raise ScorecardValidationError(f"v2 lifecycle has no artifacts: {cell.cell_id}")
    parsed = tuple(_strict_model(DeclaredArtifact, item) for item in raw)
    ids = tuple(item.artifact_id for item in parsed)
    if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
        raise ScorecardValidationError(f"v2 lifecycle artifacts are not a unique sorted closure: {cell.cell_id}")
    if set(ids) - set(LIFECYCLE_ARTIFACT_FILENAMES):
        raise ScorecardValidationError(f"v2 lifecycle contains unknown artifacts: {cell.cell_id}")
    references = {item.artifact_id: item for item in parsed}
    required = {
        "cell-input",
        "implementer-context",
        "implementer-execution",
        "implementation",
        "observation-context",
        "observation-execution",
        "observation",
        "evidence-manifest",
        "postmortem-context",
        "postmortem-request",
        "postmortem-execution",
        "postmortem-report",
    }
    if not required.issubset(references):
        raise ScorecardValidationError(f"v2 lifecycle is missing required artifacts: {cell.cell_id}")
    documents: dict[str, Mapping[str, Any]] = {}
    for artifact_id, reference in references.items():
        if reference.filename != LIFECYCLE_ARTIFACT_FILENAMES[artifact_id]:
            raise ScorecardValidationError(f"invalid lifecycle filename for {artifact_id}")
        document = _mapping(_read_document(cell_dir / reference.filename), artifact_id)
        if canonical_digest(document) != reference.digest:
            raise ScorecardValidationError(f"artifact digest drift for {artifact_id}")
        documents[artifact_id] = document
    if references["cell-input"].digest != cell.input_digest:
        raise ScorecardValidationError(f"cell input is not bound to lifecycle: {cell.cell_id}")

    direct = cell.identity.arm_id == "direct-v1"
    planner_artifacts = {"planner-context", "planner-execution", "handoff", "build-contract"}
    if direct and planner_artifacts & set(references):
        raise ScorecardValidationError(f"direct arm contains planner artifacts: {cell.cell_id}")
    if not direct and not planner_artifacts.issubset(references):
        raise ScorecardValidationError(f"planned arm lacks contract artifacts: {cell.cell_id}")
    if cell.identity.arm_id == "ultimateinterview-current-v1-structural" and "native-v1-runtime" not in references:
        raise ScorecardValidationError(f"canonical arm lacks native runtime evidence: {cell.cell_id}")
    if cell.identity.arm_id != "ultimateinterview-current-v1-structural" and "native-v1-runtime" in references:
        raise ScorecardValidationError(f"noncanonical arm contains native runtime evidence: {cell.cell_id}")

    contexts: dict[str, FreshRoleContext] = {}
    for role in ("implementer", "observation", "postmortem"):
        context = _strict_model(FreshRoleContext, documents[f"{role}-context"])
        if context.role.value != role or context.provenance != "oci-deterministic-worker":
            raise ScorecardValidationError(f"invalid OCI fresh context: {role}")
        contexts[role] = context
    transferred_artifacts(
        contexts["implementer"],
        {"cell-input": documents["cell-input"]} if direct else {
            "build-contract": documents["build-contract"],
            "handoff": documents["handoff"],
        },
    )
    transferred_artifacts(
        contexts["observation"],
        {"cell-input": documents["cell-input"], "implementation": documents["implementation"]} if direct else {
            "build-contract": documents["build-contract"],
            "implementation": documents["implementation"],
        },
    )
    postmortem_artifacts: dict[str, Mapping[str, Any]] = {
        "evidence-manifest": documents["evidence-manifest"],
        "implementation": documents["implementation"],
        "observation": documents["observation"],
        "postmortem-request": documents["postmortem-request"],
    }
    if not direct:
        planner_context = _strict_model(FreshRoleContext, documents["planner-context"])
        if planner_context.role.value != "planner" or planner_context.provenance != "oci-deterministic-worker":
            raise ScorecardValidationError("invalid OCI fresh context: planner")
        transferred_artifacts(planner_context, {"cell-input": documents["cell-input"]})
        postmortem_artifacts["build-contract"] = documents["build-contract"]
    transferred_artifacts(contexts["postmortem"], postmortem_artifacts)

    execution_roles = ("implementer", "observation", "postmortem") if direct else ("planner", "implementer", "observation", "postmortem")
    if cell.identity.arm_id == "ultimateinterview-current-v1-structural":
        _validate_native_v1_runtime(cell, documents["native-v1-runtime"])
    recomputed_role_output_digests = _validate_oci_role_outputs(
        cell,
        documents,
        execution_roles,
        direct=direct,
        worker_image=worker_image,
        receipt_replay_context=receipt_replay_context,
    )

    implementation = documents["implementation"]
    observation = documents["observation"]
    if (
        implementation.get("cell_id") != cell.cell_id
        or observation.get("schema") != "DevelopmentObservation.v2"
        or observation.get("cell_id") != cell.cell_id
    ):
        raise ScorecardValidationError(f"implementation or observation identity drift: {cell.cell_id}")
    if canonical_digest(implementation) != observation.get("implementation_digest"):
        raise ScorecardValidationError(f"observation is not bound to implementation: {cell.cell_id}")
    if direct:
        if implementation.get("input_digest") != cell.input_digest or observation.get("input_digest") != cell.input_digest:
            raise ScorecardValidationError(f"direct implementation closure drift: {cell.cell_id}")
        if implementation.get("schema") != "DirectDevelopmentImplementation.v1":
            raise ScorecardValidationError(f"invalid direct implementation: {cell.cell_id}")
        if documents["evidence-manifest"].get("schema") != "DirectDevelopmentEvidenceManifest.v2":
            raise ScorecardValidationError(f"invalid direct evidence manifest: {cell.cell_id}")
    else:
        handoff = documents["handoff"]
        build_contract = documents["build-contract"]
        if (
            handoff.get("source_input_digest") != cell.input_digest
            or build_contract.get("handoff_digest") != canonical_digest(handoff)
            or implementation.get("build_contract_digest") != canonical_digest(build_contract)
            or observation.get("build_contract_digest") != canonical_digest(build_contract)
        ):
            raise ScorecardValidationError(f"planned artifact closure drift: {cell.cell_id}")
        if documents["evidence-manifest"].get("schema") != "DevelopmentEvidenceManifest.v2":
            raise ScorecardValidationError(f"invalid planned evidence manifest: {cell.cell_id}")
    from .role_worker import replay_observation_evidence

    try:
        replayed_observation = replay_observation_evidence(
            _mapping(documents["cell-input"].get("case_contract"), "case contract"),
            _mapping(observation.get("starter_execution"), "starter execution"),
        )
    except (TypeError, ValueError) as error:
        raise ScorecardValidationError(
            f"observation predicates cannot be replayed: {cell.cell_id}"
        ) from error
    if (
        canonical_digest(observation.get("expected_assertion"))
        != canonical_digest(replayed_observation["expected_assertion"])
        or canonical_digest(observation.get("actual_assertion"))
        != canonical_digest(replayed_observation["actual_assertion"])
        or canonical_digest(observation.get("predicate_results"))
        != canonical_digest(replayed_observation["predicate_results"])
        or observation.get("observation_result") != replayed_observation["observation_result"]
    ):
        raise ScorecardValidationError(f"observation predicate replay drift: {cell.cell_id}")

    expected = _strict_model(Assertion, _mapping(observation.get("expected_assertion"), "expected assertion"))
    actual = _strict_model(Assertion, _mapping(observation.get("actual_assertion"), "actual assertion"))
    comparison = _strict_model(AssertionComparison, _mapping(observation.get("comparison"), "comparison"))
    executable = _strict_model(
        ExecutableObservation,
        {
            "result": observation.get("observation_result"),
            "assertion": observation.get("actual_assertion") if observation.get("observation_result") == "observed" else None,
        },
    )
    if comparison != compare_assertions(expected, actual):
        raise ScorecardValidationError(f"typed comparator output drift: {cell.cell_id}")
    expected_credit = comparison.primary_credit if executable.result == "observed" else 0
    if observation.get("primary_credit") != expected_credit:
        raise ScorecardValidationError(f"observation credit does not follow typed comparator: {cell.cell_id}")
    if observation.get("semantic_evidence_authoritative") != (
        executable.result == "observed" and comparison.primary_credit == 1
    ):
        raise ScorecardValidationError(
            f"observation authority does not follow predicates: {cell.cell_id}"
        )
    metric_case = _mapping(documents["cell-input"].get("metric_case"), "metric case")
    if metric_case.get("case_id") != cell.cell_id:
        raise ScorecardValidationError(f"metric case identity drift: {cell.cell_id}")
    _validate_attempt_terminal_receipts(
        cell_dir,
        cell,
        lifecycle,
        documents,
        recomputed_role_output_digests=recomputed_role_output_digests,
    )
    _validate_cell_directory_closure(cell_dir, references)
    return DevelopmentMetricCase(
        case_id=cell.cell_id,
        weight=metric_case.get("weight"),
        observation_result=executable.result,
        primary_credit=expected_credit,
    )


def _references(value: Any, expected_ids: set[str]) -> dict[str, DeclaredArtifact]:
    if not isinstance(value, list):
        raise ScorecardValidationError("artifact references must be a JSON array")
    references = tuple(_strict_model(DeclaredArtifact, item) for item in value)
    artifact_ids = tuple(item.artifact_id for item in references)
    if artifact_ids != tuple(sorted(expected_ids)) or len(references) != len(expected_ids):
        raise ScorecardValidationError("artifact references do not close over the declared lifecycle")
    return {item.artifact_id: item for item in references}


def _strict_model(model_type: type[Any], document: Mapping[str, Any]) -> Any:
    try:
        return model_type.model_validate_json(canonical_bytes(document))
    except Exception as error:
        raise ScorecardValidationError(f"strict artifact model validation failed: {error}") from error


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScorecardValidationError(f"{name} must be a JSON object")
    return value


def _read_document(path: Path) -> Any:
    try:
        return read_canonical_json(path)
    except StateError as error:
        raise ScorecardValidationError(str(error)) from error


def _atom_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ScorecardValidationError("atom identifiers must be a nonempty JSON array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ScorecardValidationError("atom identifiers must be nonblank strings")
    atom_ids = tuple(sorted(value))
    if len(set(atom_ids)) != len(atom_ids):
        raise ScorecardValidationError("atom identifiers must be unique")
    return atom_ids


def _terminal_filename(attempt: int) -> str:
    return "terminal-receipt.json" if attempt == 1 else f"terminal-receipt-{attempt:06d}.json"


def _is_attempt_artifact(filename: str) -> bool:
    return len(filename) == len("attempt-000001.json") and filename.startswith("attempt-") and filename.endswith(".json") and filename[8:14].isdigit()


def _is_terminal_artifact(filename: str) -> bool:
    return filename == "terminal-receipt.json" or (
        len(filename) == len("terminal-receipt-000001.json")
        and filename.startswith("terminal-receipt-")
        and filename.endswith(".json")
        and filename[17:23].isdigit()
    )
