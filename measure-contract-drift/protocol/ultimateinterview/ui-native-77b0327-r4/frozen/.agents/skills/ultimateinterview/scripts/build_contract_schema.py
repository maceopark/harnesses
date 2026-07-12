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
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Final, Literal, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

from scripts import behavior_atoms, verification_policy

type SourceId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9._:-]*$")]
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
CONSUMER_VERIFICATION_HEADERS: Final[tuple[str, ...]] = (
    "grant kind",
    "receipt kind",
    "required id",
    "target",
    "environment / scope",
    "outcome",
    "expected exit",
    "run policy",
    "auto execute",
)


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


class ConsumerGrantKind(StrEnum):
    IMPLEMENTATION_READINESS = "implementation-readiness"
    PROBE = "probe"


class ConsumerReceiptKind(StrEnum):
    VERIFICATION = "verification"
    PROBE = "probe"


class ConsumerOutcome(StrEnum):
    SUCCESS = "success"
    NONZERO = "nonzero"
    TIMEOUT = "timeout"
    FAILURE = "failure"


class TargetSurface(StrictModel):
    file_module: str = Field(min_length=1)
    expected_change: str = Field(min_length=1)


class Requirement(StrictModel):
    id: str = Field(pattern=r"^REQ-[0-9]{3,}$")
    requirement: str = Field(min_length=1)
    acceptance_criterion: str = Field(min_length=1)
    source_ids: tuple[SourceId, ...] = Field(min_length=1)
    assurance_class: behavior_atoms.AssuranceClass | None = None
    atom_ids: tuple[behavior_atoms.AtomId, ...] = ()

    @model_validator(mode="after")
    def stable_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ContractValidationError("duplicate source id in requirement")
        if len(set(self.atom_ids)) != len(self.atom_ids):
            raise ContractValidationError("duplicate behavior atom id in requirement")
        match self.assurance_class:
            case None:
                if self.atom_ids:
                    raise ContractValidationError("behavior atom ids require an assurance class")
            case behavior_atoms.AssuranceClass.STANDARD:
                pass
            case behavior_atoms.AssuranceClass.HIGH:
                if not self.atom_ids:
                    raise ContractValidationError("high requirement requires at least one behavior atom id")
            case unreachable:
                assert_never(unreachable)
        return self


class BehaviorAtomBinding(StrictModel):
    source_id: SourceId
    assurance_class: behavior_atoms.AssuranceClass
    atom: behavior_atoms.BehaviorAtom
    atom_digest: behavior_atoms.Digest

    @model_validator(mode="after")
    def atom_digest_is_canonical(self) -> Self:
        if self.atom_digest != behavior_atoms.atom_digest(self.atom):
            raise ContractValidationError("behavior atom digest does not match its canonical atom")
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


class ConsumerVerification(StrictModel):
    grant_kind: ConsumerGrantKind
    receipt_kind: ConsumerReceiptKind
    required_id: str = Field(min_length=1)
    target_ids: tuple[SourceId, ...] = Field(min_length=1)
    environment_scope: str = Field(min_length=1)
    outcome: ConsumerOutcome
    expected_exit: StrictInt = Field(ge=0)
    run_policy: RunPolicy
    auto_execute: StrictBool

    @model_validator(mode="after")
    def grant_shape_is_exact_and_auto_execution_is_allowlisted(self) -> Self:
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ContractValidationError("consumer verification target IDs must be unique")
        match self.grant_kind:
            case ConsumerGrantKind.IMPLEMENTATION_READINESS:
                if self.receipt_kind is not ConsumerReceiptKind.VERIFICATION or re.fullmatch(r"VER-[0-9]{3,}", self.required_id) is None:
                    raise ContractValidationError("implementation-readiness grant requires a verification receipt and VER-* ID")
            case ConsumerGrantKind.PROBE:
                if self.receipt_kind is not ConsumerReceiptKind.PROBE or re.fullmatch(r"PROBE-[A-Za-z0-9._:-]+", self.required_id) is None:
                    raise ContractValidationError("probe grant requires a probe receipt and PROBE-* ID")
            case unreachable:
                assert_never(unreachable)
        match self.run_policy:
            case RunPolicy.SAFE_AUTO:
                pass
            case RunPolicy.EXPENSIVE | RunPolicy.DESTRUCTIVE | RunPolicy.CREDENTIALED | RunPolicy.MANUAL:
                if self.auto_execute:
                    raise ContractValidationError("only safe-auto consumer verification rows may be auto-executable")
            case unreachable:
                assert_never(unreachable)
        match self.outcome:
            case ConsumerOutcome.SUCCESS:
                if self.expected_exit != 0:
                    raise ContractValidationError("success consumer verification requires expected exit 0")
            case ConsumerOutcome.NONZERO | ConsumerOutcome.TIMEOUT | ConsumerOutcome.FAILURE:
                if self.expected_exit == 0:
                    raise ContractValidationError("non-success consumer verification requires a nonzero expected exit")
            case unreachable:
                assert_never(unreachable)
        return self


def _parse_grant_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractValidationError("grant timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ContractValidationError("grant timestamp must include an offset")
    return parsed.astimezone(UTC)


class ConsumerGrantBinding(StrictModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)

    session_id: NonBlank
    manifest_digest: Digest
    source_part1_sha256: Digest
    contract_digest: Digest
    policy_version: Literal["v2-receipt-policy-1"]
    target_ids: tuple[SourceId, ...] = Field(min_length=1)
    environment_scope: NonBlank
    issuer_id: NonBlank
    subject_digest: Digest
    issued_at: NonBlank
    expires_at: NonBlank
    nonce: NonBlank
    outcome: ConsumerOutcome
    exit_code: StrictInt = Field(ge=0)
    artifact_digest: Digest
    stdout_digest: Digest
    stderr_digest: Digest

    @model_validator(mode="after")
    def timestamps_and_targets_are_valid(self) -> Self:
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ContractValidationError("grant target IDs must be unique")
        if _parse_grant_timestamp(self.issued_at) >= _parse_grant_timestamp(self.expires_at):
            raise ContractValidationError("grant expires_at must follow issued_at")
        return self


class ImplementationReadinessGrant(ConsumerGrantBinding):
    verification_id: Annotated[str, StringConstraints(strict=True, pattern=r"^VER-[0-9]{3,}$")]
    action_digest: Digest


class ProbeGrant(ConsumerGrantBinding):
    probe_id: Annotated[str, StringConstraints(strict=True, pattern=r"^PROBE-[A-Za-z0-9._:-]+$")]
    action_digest: Digest
    observation_spec_digest: Digest

    @model_validator(mode="after")
    def action_is_the_observation_spec(self) -> Self:
        if self.action_digest != self.observation_spec_digest:
            raise ContractValidationError("probe grant action_digest must equal observation_spec_digest")
        return self


type ConsumerGrant = ImplementationReadinessGrant | ProbeGrant


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
    schema_version: StrictInt = Field(default=1, frozen=True, ge=1)
    goal: str = Field(min_length=1)
    target_surface: tuple[TargetSurface, ...] = Field(min_length=1)
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    behavior_atoms: tuple[BehaviorAtomBinding, ...] = ()
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
    consumer_verifications: tuple[ConsumerVerification, ...] = ()
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
        match self.schema_version:
            case 1:
                if self.behavior_atoms or self.consumer_verifications or any(
                    item.assurance_class is not None or item.atom_ids
                    for item in self.requirements
                ):
                    raise ContractValidationError("BuildContract v1 cannot contain v2 assurance fields")
            case 2:
                self._validate_v2_atoms()
                self._validate_v2_consumer_verifications()
            case unexpected if unexpected not in (1, 2):
                raise ContractValidationError(
                    f"unknown BuildContract schema version {unexpected}",
                )
            case unreachable:
                assert_never(unreachable)
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

    def _validate_v2_atoms(self) -> None:
        if any(item.assurance_class is None for item in self.requirements):
            raise ContractValidationError("v2 requirements require an assurance class")
        if not self.behavior_atoms:
            if any(item.atom_ids for item in self.requirements):
                raise ContractValidationError("v2 behavior atom citations require a behavior atom catalog")
            return
        atom_ids = tuple(item.atom.id for item in self.behavior_atoms)
        if len(set(atom_ids)) != len(atom_ids):
            raise ContractValidationError("duplicate behavior atom id in catalog")
        bindings = {item.atom.id: item for item in self.behavior_atoms}
        cited: set[str] = set()
        for requirement in self.requirements:
            assurance_class = requirement.assurance_class
            if assurance_class is None:
                raise ContractValidationError("v2 requirements require an assurance class")
            for atom_id in requirement.atom_ids:
                binding = bindings.get(atom_id)
                if binding is None:
                    raise ContractValidationError(f"requirement cites unknown behavior atom id {atom_id}")
                if binding.source_id not in requirement.source_ids:
                    raise ContractValidationError(
                        f"requirement {requirement.id} cites unbound behavior atom {atom_id}",
                    )
                if binding.assurance_class is not assurance_class:
                    raise ContractValidationError(
                        f"requirement {requirement.id} assurance class does not match behavior atom {atom_id}",
                    )
                cited.add(atom_id)
        if unbound := sorted(set(bindings) - cited):
            raise ContractValidationError(
                f"normative behavior atom(s) are not cited by a requirement: {', '.join(unbound)}",
            )

    def _validate_v2_consumer_verifications(self) -> None:
        if not self.consumer_verifications:
            raise ContractValidationError("BuildContract v2 requires Consumer Verification rows")
        duplicate_keys = tuple(
            (item.grant_kind, item.required_id)
            for item in self.consumer_verifications
        )
        if len(duplicate_keys) != len(set(duplicate_keys)):
            raise ContractValidationError("duplicate Consumer Verification grant requirement")
        verifications = {item.id: item for item in self.verifications}
        implementation_rows = {
            item.required_id: item
            for item in self.consumer_verifications
            if item.grant_kind is ConsumerGrantKind.IMPLEMENTATION_READINESS
        }
        if missing := sorted(set(verifications) - set(implementation_rows)):
            raise ContractValidationError(
                f"verification(s) lack implementation-readiness consumer requirements: {', '.join(missing)}",
            )
        if unknown := sorted(set(implementation_rows) - set(verifications)):
            raise ContractValidationError(
                f"Consumer Verification references unknown VER-* ID(s): {', '.join(unknown)}",
            )
        for verification_id, row in implementation_rows.items():
            verification = verifications[verification_id]
            if row.target_ids != verification.requirement_ids:
                raise ContractValidationError(
                    f"Consumer Verification target does not match {verification_id}",
                )
            if row.run_policy is not verification.run_policy:
                raise ContractValidationError(
                    f"Consumer Verification run policy does not match {verification_id}",
                )
        if not any(
            item.grant_kind is ConsumerGrantKind.PROBE
            for item in self.consumer_verifications
        ):
            raise ContractValidationError("BuildContract v2 requires a ProbeGrant consumer requirement")


def canonical_body_payload(body: ContractBody) -> dict[str, JsonValue]:
    payload = body.model_dump(mode="json")
    match body.schema_version:
        case 1:
            payload.pop("behavior_atoms")
            payload.pop("consumer_verifications")
            for requirement in payload["requirements"]:
                requirement.pop("assurance_class")
                requirement.pop("atom_ids")
        case 2:
            pass
        case unexpected if unexpected not in (1, 2):
            raise ContractValidationError(f"unknown BuildContract schema version {unexpected}")
        case unreachable:
            assert_never(unreachable)
    return payload


def body_digest(body: ContractBody) -> str:
    payload = json.dumps(
        canonical_body_payload(body),
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


def _verification_action_digest(contract: BuildContract, verification_id: str) -> str:
    matches = tuple(item for item in contract.verifications if item.id == verification_id)
    if len(matches) != 1:
        raise ContractValidationError("consumer grant verification_id must exist exactly once")
    verification = matches[0]
    payload = {
        "verification_id": verification.id,
        "command_action": verification.command_action,
        "pass_condition": verification.pass_condition,
        "run_policy": verification.run_policy.value,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_consumer_grant(
    grant: ConsumerGrant,
    consumer: ConsumerVerification,
    *,
    session_id: str,
    manifest_digest: Digest,
    contract: BuildContract,
    now: datetime,
    consumed_nonces: frozenset[str],
    expected_probe_observation_spec_digest: Digest | None = None,
) -> None:
    if consumer not in contract.consumer_verifications:
        raise ContractValidationError("consumer grant requirement is not allowlisted by BuildContract")
    if grant.session_id != session_id:
        raise ContractValidationError("grant session_id does not match the current session")
    if grant.manifest_digest != manifest_digest:
        raise ContractValidationError("grant manifest_digest does not match the current manifest")
    if grant.source_part1_sha256 != contract.source_part1_sha256:
        raise ContractValidationError("grant source_part1_sha256 does not match BuildContract")
    if grant.contract_digest != contract.contract_digest:
        raise ContractValidationError("grant contract_digest does not match BuildContract")
    if grant.nonce in consumed_nonces:
        raise ContractValidationError("grant nonce is replayed")
    issued = _parse_grant_timestamp(grant.issued_at)
    expires = _parse_grant_timestamp(grant.expires_at)
    if issued > now:
        raise ContractValidationError("grant issued_at is in the future")
    if expires <= now:
        raise ContractValidationError("grant is expired")
    if grant.target_ids != consumer.target_ids:
        raise ContractValidationError("grant target IDs do not match Consumer Verification")
    if grant.environment_scope != consumer.environment_scope:
        raise ContractValidationError("grant environment_scope does not match Consumer Verification")
    if grant.outcome is not consumer.outcome or grant.exit_code != consumer.expected_exit:
        raise ContractValidationError("grant outcome or exit code does not match Consumer Verification")
    match grant:
        case ImplementationReadinessGrant():
            if consumer.grant_kind is not ConsumerGrantKind.IMPLEMENTATION_READINESS:
                raise ContractValidationError("implementation grant does not match Consumer Verification kind")
            if grant.verification_id != consumer.required_id:
                raise ContractValidationError("grant verification_id does not match Consumer Verification")
            if grant.action_digest != _verification_action_digest(contract, grant.verification_id):
                raise ContractValidationError("grant action_digest does not match BuildContract verification")
        case ProbeGrant():
            if consumer.grant_kind is not ConsumerGrantKind.PROBE:
                raise ContractValidationError("probe grant does not match Consumer Verification kind")
            if grant.probe_id != consumer.required_id:
                raise ContractValidationError("grant probe_id does not match Consumer Verification")
            if expected_probe_observation_spec_digest is None:
                raise ContractValidationError("probe grant requires a Task4 observation spec digest")
            if grant.observation_spec_digest != expected_probe_observation_spec_digest:
                raise ContractValidationError("probe observation_spec_digest does not match Task4")
        case unreachable:
            assert_never(unreachable)
