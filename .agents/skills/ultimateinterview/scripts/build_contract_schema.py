#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

from scripts import verification_policy

type SourceId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9._:-]*$")]


@dataclass(frozen=True, slots=True)
class ContractValidationError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class VerificationKind(StrEnum):
    TEST = "test"
    REAL_SURFACE = "real-surface"


class RunPolicy(StrEnum):
    SAFE_AUTO = "safe-auto"
    EXPENSIVE = "expensive"
    DESTRUCTIVE = "destructive"
    CREDENTIALED = "credentialed"
    MANUAL = "manual"


class TargetSurface(StrictModel):
    file_module: str = Field(min_length=1)
    expected_change: str = Field(min_length=1)


class Requirement(StrictModel):
    id: str = Field(pattern=r"^REQ-[0-9]{3,}$")
    requirement: str = Field(min_length=1)
    acceptance_criterion: str = Field(min_length=1)
    source_ids: tuple[SourceId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def stable_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ContractValidationError("duplicate source id in requirement")
        return self


class ImpactTrace(StrictModel):
    source_ids: tuple[SourceId, ...] = Field(min_length=1)
    current_evidence_behavior: str = Field(min_length=1)
    preserved_invariant: str = Field(min_length=1)
    target_difference: str = Field(min_length=1)
    code_surface: str = Field(min_length=1)
    acceptance_check: str = Field(min_length=1)
    runtime_signal: str = Field(min_length=1)


class QualityBar(StrictModel):
    attribute: str = Field(min_length=1)
    measurable_bar: str = Field(min_length=1)
    weight: Literal[1, 2, 3, 5]
    verification: str = Field(min_length=1)

    @field_validator("weight", mode="before")
    @classmethod
    def weight_is_not_boolean(cls, value: int | bool) -> int | bool:
        match value:
            case bool():
                raise ContractValidationError("quality weight must be an integer, not a boolean")
            case int():
                return value
            case unreachable:
                assert_never(unreachable)

    @model_validator(mode="after")
    def bar_is_measurable(self) -> Self:
        if re.search(r"\d", self.measurable_bar) is None:
            raise ContractValidationError("quality bar must contain a measurable number")
        return self


class DecisionBoundary(StrictModel):
    decision: str = Field(min_length=1)
    agent_may_decide: StrictBool
    boundary: str = Field(min_length=1)


class ImplementationConstraints(StrictModel):
    interfaces: str = Field(min_length=1)
    compatibility: str = Field(min_length=1)
    migration: str = Field(min_length=1)
    decision_core: str = Field(min_length=1)
    effects_boundary: str = Field(min_length=1)


class RolloutRecovery(StrictModel):
    activation: str = Field(min_length=1)
    compatibility_backfill: str = Field(min_length=1)
    rollback_trigger: str = Field(min_length=1)
    rollback_action: str = Field(min_length=1)
    observation_metric_window: str = Field(min_length=1)
    owner: str = Field(min_length=1)


class Guardrail(StrictModel):
    risk: str = Field(min_length=1)
    risk_class: str = Field(min_length=1)
    predicate_residual_owner: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class Verification(StrictModel):
    id: str = Field(pattern=r"^VER-[0-9]{3,}$")
    requirement_ids: tuple[str, ...] = Field(min_length=1)
    check: str = Field(min_length=1)
    kind: VerificationKind
    command_action: str = Field(min_length=1)
    pass_condition: str = Field(min_length=1)
    run_policy: RunPolicy

    @model_validator(mode="after")
    def safe_auto_is_safe(self) -> Self:
        match self.run_policy:
            case RunPolicy.SAFE_AUTO:
                verification_policy.validate_safe_auto(self.command_action, self.pass_condition)
            case RunPolicy.EXPENSIVE | RunPolicy.DESTRUCTIVE | RunPolicy.CREDENTIALED | RunPolicy.MANUAL:
                return self
            case unreachable:
                assert_never(unreachable)
        return self


class DeferredRisk(StrictModel):
    risk: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    decision_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    mitigation: str = Field(min_length=1)

    @field_validator("decision_date")
    @classmethod
    def decision_date_exists(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise ContractValidationError("invalid decision_date calendar date") from error
        return value


class FreshReviewEvidence(StrictModel):
    reviewer: str = Field(min_length=1)
    ask_items_found: str = Field(min_length=1)
    gameable_criteria_found: str = Field(min_length=1)
    disposition: str = Field(min_length=1)
    unresolved_after_disposition: str = Field(min_length=1)

    @model_validator(mode="after")
    def review_is_resolved(self) -> Self:
        if self.reviewer.strip().lower() in {"tbd", "todo", "pending", "unknown", "n/a", "none"}:
            raise ContractValidationError("fresh review needs a concrete reviewer")
        if self.unresolved_after_disposition.strip().lower() not in {"none", "none.", "0", "no findings", "no findings."}:
            raise ContractValidationError("fresh review contains unresolved items")
        disposition = self.disposition.lower()
        if re.search(r"(?:no fold-back required|folded back|re-?bound)", disposition) is None:
            raise ContractValidationError("fresh review lacks a fold-back/re-bind disposition")
        return self


class ContractBody(StrictModel):
    schema_version: StrictInt = Field(default=1, frozen=True, ge=1, le=1)
    goal: str = Field(min_length=1)
    target_surface: tuple[TargetSurface, ...] = Field(min_length=1)
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    change_impact_preservation: tuple[ImpactTrace, ...] = Field(min_length=1)
    quality_bars: tuple[QualityBar, ...] = ()
    quality_bars_none_reason: str | None = None
    decision_boundaries: tuple[DecisionBoundary, ...] = Field(min_length=1)
    decision_log_path: str = Field(pattern=r"^\.ultimateinterview/[^/]+/decisions\.jsonl$")
    probe_decision: str = Field(min_length=1)
    out_of_scope: tuple[str, ...] = Field(min_length=1)
    implementation_constraints: ImplementationConstraints
    rollout_recovery: tuple[RolloutRecovery, ...] = ()
    rollout_na_reason: str | None = None
    guardrails: tuple[Guardrail, ...] = ()
    guardrails_none_reason: str | None = None
    verifications: tuple[Verification, ...] = Field(min_length=1)
    deferred_risks: tuple[DeferredRisk, ...] = ()
    deferred_risks_none_reason: str | None = None
    fresh_review_evidence: tuple[FreshReviewEvidence, ...] = Field(min_length=1)
    source_part1_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("decision_log_path")
    @classmethod
    def decision_log_path_is_canonical(cls, value: str) -> str:
        path = PurePosixPath(value)
        unsafe = (
            path.is_absolute()
            or path.parts[:1] != (".ultimateinterview",)
            or path.parts[-1:] != ("decisions.jsonl",)
            or len(path.parts) != 3
            or path.parts[1] in {".", ".."}
            or "\\" in value
            or any(unicodedata.category(character).startswith("C") for character in value)
        )
        if unsafe:
            raise ContractValidationError("decision_log_path must be a canonical repository-relative session path")
        return value

    @model_validator(mode="after")
    def ids_and_coverage_are_closed(self) -> Self:
        if bool(self.quality_bars) == bool(self.quality_bars_none_reason):
            raise ContractValidationError("quality bars require rows or one none-applies reason")
        if bool(self.rollout_recovery) == bool(self.rollout_na_reason):
            raise ContractValidationError("rollout requires rows or one N/A reason")
        if bool(self.guardrails) == bool(self.guardrails_none_reason):
            raise ContractValidationError("guardrails require rows or one none-applies reason")
        if bool(self.deferred_risks) == bool(self.deferred_risks_none_reason):
            raise ContractValidationError("deferred risks require rows or one reasoned none line")
        requirement_ids = tuple(item.id for item in self.requirements)
        verification_ids = tuple(item.id for item in self.verifications)
        if len(set(requirement_ids)) != len(requirement_ids):
            raise ContractValidationError("duplicate requirement id")
        if len(set(verification_ids)) != len(verification_ids):
            raise ContractValidationError("duplicate verification id")
        known = set(requirement_ids)
        references = {item for check in self.verifications for item in check.requirement_ids}
        if unknown := sorted(references - known):
            raise ContractValidationError(
                f"verification references unknown requirement id(s): {', '.join(unknown)}",
            )
        if missing := sorted(known - references):
            raise ContractValidationError(
                f"requirement lacks verification coverage: {', '.join(missing)}",
            )
        known_verifications = set(verification_ids)
        cited_verifications = {
            match
            for text in (
                *(item.verification for item in self.quality_bars),
                *(item.evidence for item in self.guardrails),
            )
            for match in re.findall(r"\bVER-[0-9]{3,}\b", text)
        }
        if dangling_verifications := sorted(cited_verifications - known_verifications):
            raise ContractValidationError(
                f"section references unknown verification id(s): {', '.join(dangling_verifications)}",
            )
        cited_requirements = {
            match
            for item in self.change_impact_preservation
            for match in re.findall(r"\bREQ-[0-9]{3,}\b", item.acceptance_check)
        }
        if dangling_requirements := sorted(cited_requirements - known):
            raise ContractValidationError(
                f"section references unknown requirement id(s): {', '.join(dangling_requirements)}",
            )
        kinds = {item.kind for item in self.verifications}
        for required in VerificationKind:
            if required not in kinds:
                raise ContractValidationError(f"verification floor requires kind {required.value}")
        return self


def body_digest(body: ContractBody) -> str:
    payload = json.dumps(
        body.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


class BuildContract(ContractBody):
    contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def digest_is_canonical(self) -> Self:
        body = ContractBody.model_validate(self.model_dump(exclude={"contract_digest"}))
        if self.contract_digest != body_digest(body):
            raise ContractValidationError(
                "contract_digest does not match canonical self-excluding payload",
            )
        return self
