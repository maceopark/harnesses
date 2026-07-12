#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

"""Strict ExecutionReturn v1 boundary schema."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal, Self, assert_never

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic import model_validator
from pydantic_core import PydanticCustomError


def _canonical_decision_log_path(path: str) -> str:
    if (slug := path.split("/")[1]) in {".", ".."} or "\\" in slug or any(unicodedata.category(character) in {"Cc", "Cf"} for character in slug):
        raise PydanticCustomError("execution_return_decision_log_path", "decision_log_path must contain one canonical visible slug")
    return path


Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StableId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")]
RequirementId = Annotated[str, StringConstraints(pattern=r"^REQ-[0-9]{3,}$")]
VerificationId = Annotated[str, StringConstraints(pattern=r"^VER-[0-9]{3,}$")]
DecisionRecordRef = Annotated[str, StringConstraints(pattern=r"^decision#[1-9][0-9]*$")]
DecisionLogPath = Annotated[str, StringConstraints(pattern=r"^\.ultimateinterview/[^/]+/decisions\.jsonl$"), AfterValidator(_canonical_decision_log_path)]


class StrictModel(BaseModel):
    """Frozen, unknown-field-forbidden JSON boundary model."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class ExactPass(StrictModel):
    """An expected command executed without adaptation and produced a capture."""

    subject_id: StableId
    result: Literal["exact-pass"]
    actual_command: NonBlank
    capture_artifact_id: StableId
    evidence_artifact_ids: tuple[StableId, ...] = ()


class AdaptedPass(StrictModel):
    """A changed command passed with explicit capture and decision provenance."""

    subject_id: StableId
    result: Literal["adapted-pass"]
    actual_command: NonBlank
    capture_artifact_id: StableId
    evidence_artifact_ids: tuple[StableId, ...] = ()
    adaptation_reason: NonBlank
    decision_record_ref: DecisionRecordRef


class Failed(StrictModel):
    """An actual command ran and produced executor-owned failure evidence."""

    subject_id: StableId
    result: Literal["fail"]
    actual_command: NonBlank
    capture_artifact_id: StableId
    evidence_artifact_ids: tuple[StableId, ...] = ()
    failure_reason: NonBlank


class NotRun(StrictModel):
    """An expected outcome was not executed for the stated reason."""

    subject_id: StableId
    result: Literal["not-run"]
    reason: NonBlank


type Outcome = Annotated[ExactPass | AdaptedPass | Failed | NotRun, Field(discriminator="result")]


class DecisionLogReference(StrictModel):
    """Content-addressed decision-log provenance without duplicated decisions."""

    path: DecisionLogPath
    sha256: Digest


class ExpectedVerification(StrictModel):
    """One BuildContract VER identity bound to its exact command or action."""

    id: VerificationId
    command_action: NonBlank


class ExecutionExpectation(StrictModel):
    """BuildContract coordinates supplied by the validating consumer."""

    contract_digest: Digest
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    verifications: tuple[ExpectedVerification, ...] = Field(min_length=1)
    decision_log_path: DecisionLogPath
    decision_log_digest: Digest
    decision_record_refs: tuple[DecisionRecordRef, ...] = ()

    @model_validator(mode="after")
    def ids_are_unique(self) -> Self:
        _require_unique("requirement_ids", self.requirement_ids)
        _require_unique("verification_ids", tuple(item.id for item in self.verifications))
        _require_unique("decision_record_refs", self.decision_record_refs)
        return self


class ExecutionReturn(StrictModel):
    """Final executor-owned evidence envelope bound to BuildContract v1."""

    marker: Literal["EXECUTION-RETURN"]
    schema_version: Literal[1]
    contract_digest: Digest
    status: Literal["completed", "blocked", "failed"]
    changed_paths: tuple[NonBlank, ...]
    requirement_outcomes: tuple[Outcome, ...]
    verification_outcomes: tuple[Outcome, ...]
    decision_log: DecisionLogReference
    blocker_reasons: tuple[NonBlank, ...]
    deviations: tuple[DecisionRecordRef, ...]
    capture_artifact_ids: tuple[StableId, ...]
    evidence_artifact_ids: tuple[StableId, ...]

    @field_validator("changed_paths")
    @classmethod
    def changed_paths_are_repo_relative(cls, paths: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique("changed_paths", paths)
        for path in paths:
            parsed = PurePosixPath(path)
            if (
                parsed.is_absolute()
                or "\\" in path
                or ".." in parsed.parts
                or parsed.as_posix() != path
                or path == "."
                or any(unicodedata.category(character) in {"Cc", "Cf"} for character in path)
            ):
                raise PydanticCustomError("execution_return_path", "changed_paths must contain canonical repository-relative paths")
        return paths

    @model_validator(mode="after")
    def envelope_invariants_hold(self) -> Self:
        _require_unique("blocker_reasons", self.blocker_reasons)
        _require_unique("deviations", self.deviations)
        _require_unique("capture_artifact_ids", self.capture_artifact_ids)
        _require_unique("evidence_artifact_ids", self.evidence_artifact_ids)
        has_fail = False
        has_not_run = False
        inventory = ArtifactInventory(
            captures=frozenset(self.capture_artifact_ids),
            evidence=frozenset(self.evidence_artifact_ids),
        )
        for outcome in (*self.requirement_outcomes, *self.verification_outcomes):
            match outcome:
                case ExactPass(
                    capture_artifact_id=capture_id,
                    evidence_artifact_ids=evidence_ids,
                ) | AdaptedPass(
                    capture_artifact_id=capture_id,
                    evidence_artifact_ids=evidence_ids,
                ):
                    _require_declared_artifacts(capture_id, evidence_ids, inventory)
                case Failed(
                    capture_artifact_id=capture_id,
                    evidence_artifact_ids=evidence_ids,
                ):
                    has_fail = True
                    _require_declared_artifacts(capture_id, evidence_ids, inventory)
                case NotRun():
                    has_not_run = True
                case unreachable:
                    assert_never(unreachable)
        match self.status:
            case "completed":
                if self.blocker_reasons or has_fail or has_not_run:
                    raise PydanticCustomError(
                        "execution_return_completed",
                        "completed status forbids blockers, fail, and not-run outcomes",
                    )
            case "blocked":
                if not self.blocker_reasons or not has_not_run:
                    raise PydanticCustomError(
                        "execution_return_blocked",
                        "blocked status requires a blocker and a not-run outcome",
                    )
            case "failed":
                if not has_fail:
                    raise PydanticCustomError(
                        "execution_return_failed",
                        "failed status requires at least one fail outcome",
                    )
            case unreachable:
                assert_never(unreachable)
        return self


@dataclass(frozen=True, slots=True)
class ExecutionReturnContractError(Exception):
    """A parsed return does not match its supplied BuildContract coordinates."""

    coordinate: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.coordinate} mismatch: expected {self.expected}; found {self.actual}"


@dataclass(frozen=True, slots=True)
class ArtifactInventory:
    captures: frozenset[str]
    evidence: frozenset[str]


def _require_unique(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise PydanticCustomError(
            "execution_return_duplicate", "{label} must contain unique values", {"label": label}
        )


def _require_declared_artifacts(
    capture_id: str,
    evidence_ids: tuple[str, ...],
    inventory: ArtifactInventory,
) -> None:
    _require_unique("outcome evidence_artifact_ids", evidence_ids)
    if capture_id not in inventory.captures:
        raise PydanticCustomError(
            "execution_return_capture", "outcome capture must be declared in capture_artifact_ids"
        )
    if not set(evidence_ids).issubset(inventory.evidence):
        raise PydanticCustomError(
            "execution_return_evidence", "outcome evidence must be declared in evidence_artifact_ids"
        )


def _require_exact_coverage(key: str, actual: tuple[str, ...], expected: tuple[str, ...]) -> None:
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ExecutionReturnContractError(
            coordinate=key,
            expected=repr(tuple(sorted(expected))),
            actual=repr(tuple(sorted(actual))),
        )


def validate_execution_return(raw: str | bytes, expected: ExecutionExpectation) -> ExecutionReturn:
    """Parse a present owned return and bind it to expected BuildContract facts."""
    parsed = ExecutionReturn.model_validate_json(raw)
    if parsed.contract_digest != expected.contract_digest:
        raise ExecutionReturnContractError(
            "contract_digest", expected.contract_digest, parsed.contract_digest
        )
    _require_exact_coverage(
        "requirement_outcomes",
        tuple(outcome.subject_id for outcome in parsed.requirement_outcomes),
        expected.requirement_ids,
    )
    _require_exact_coverage(
        "verification_outcomes",
        tuple(outcome.subject_id for outcome in parsed.verification_outcomes),
        tuple(item.id for item in expected.verifications),
    )
    commands = {item.id: item.command_action for item in expected.verifications}
    cited_decisions = list(parsed.deviations)
    for outcome in (*parsed.requirement_outcomes, *parsed.verification_outcomes):
        match outcome:
            case ExactPass(subject_id=subject_id, actual_command=actual_command):
                if subject_id in commands and actual_command != commands[subject_id]:
                    raise ExecutionReturnContractError(f"verification_exact_command[{subject_id}]", commands[subject_id], actual_command)
            case AdaptedPass(
                subject_id=subject_id,
                actual_command=actual_command,
                decision_record_ref=decision_record_ref,
            ):
                if subject_id in commands and actual_command == commands[subject_id]:
                    raise ExecutionReturnContractError(f"verification_adapted_command[{subject_id}]", "a command different from the exact BuildContract command", actual_command)
                cited_decisions.append(decision_record_ref)
            case Failed() | NotRun():
                pass
            case unreachable:
                assert_never(unreachable)
    unknown_decisions = set(cited_decisions) - set(expected.decision_record_refs)
    if unknown_decisions:
        raise ExecutionReturnContractError(
            "decision_record_refs",
            repr(tuple(sorted(expected.decision_record_refs))),
            repr(tuple(sorted(unknown_decisions))),
        )
    if parsed.decision_log.path != expected.decision_log_path:
        raise ExecutionReturnContractError(
            "decision_log_path", expected.decision_log_path, parsed.decision_log.path
        )
    if parsed.decision_log.sha256 != expected.decision_log_digest:
        raise ExecutionReturnContractError(
            "decision_log_digest", expected.decision_log_digest, parsed.decision_log.sha256
        )
    return parsed
