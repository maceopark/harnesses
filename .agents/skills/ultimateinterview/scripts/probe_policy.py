#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
# ]
# ///

"""Standalone probe selection and result contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, assert_never

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
type ContractDigest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def _strict_enum(value: str | StrEnum) -> str | StrEnum:
    if not isinstance(value, str):
        raise PydanticCustomError("strict_enum", "enum input must be a string")
    return value


type StrictEnum[T: StrEnum] = Annotated[T, BeforeValidator(_strict_enum)]


class ProbeLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class ProbeIntent(StrEnum):
    DISCOVERY = "discovery"
    TARGETED_CONFIRMATION = "targeted-confirmation"


class AuthorizationScope(StrEnum):
    L2_PROTOTYPE_OBSERVATION = "l2:prototype+runtime-observation"
    L3_STAGED_TELEMETRY = "l3:staged-telemetry"
    L3_PRODUCTION_TELEMETRY = "l3:production-telemetry"


class ProducerKind(StrEnum):
    REPO_DOCS = "repo-docs"
    FRESH_IMPLEMENTER = "fresh-implementer"
    BEHAVIORAL_STUB = "behavioral-stub"
    EXECUTABLE_PROTOTYPE = "executable-prototype"
    USER_RUNTIME_OBSERVATION = "user-runtime-observation"
    STAGED_TELEMETRY = "staged-telemetry"
    PRODUCTION_TELEMETRY = "production-telemetry"


class ProbeOutcome(StrEnum):
    NO_MATERIAL_DIVERGENCE = "no-material-divergence"
    MATERIAL_DIVERGENCE = "material-divergence"
    INCONCLUSIVE = "inconclusive"


def select_probe_level(
    *,
    sandboxable_observable: bool | str | int,
    requires_runtime_observation: bool | str | int,
    production_only: bool | str | int,
) -> ProbeLevel:
    signals = (sandboxable_observable, requires_runtime_observation, production_only)
    if any(not isinstance(value, bool) for value in signals) or sum(value is True for value in signals) > 1:
        raise PydanticCustomError("probe_selection", "probe signals must be distinct strict booleans")
    if production_only:
        return ProbeLevel.L3
    if requires_runtime_observation:
        return ProbeLevel.L2
    if sandboxable_observable:
        return ProbeLevel.L1
    return ProbeLevel.L0


class _ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")


class ProbeAuthorization(_ContractModel):
    authorization_id: NonBlank
    level: StrictEnum[ProbeLevel]
    scope: StrictEnum[AuthorizationScope]
    approved_by: NonBlank
    target_ledger_ids: tuple[NonBlank, ...] = Field(min_length=1)
    contract_digest: ContractDigest

    @model_validator(mode="after")
    def level_matches_scope(self) -> ProbeAuthorization:
        if not self.scope.value.startswith(f"{self.level.value.lower()}:"):
            raise PydanticCustomError("probe_authorization", "authorization level/scope mismatch")
        return self


class ProbeDecision(_ContractModel):
    """Deterministic, immutable selection of a probe obligation."""

    probe_id: NonBlank
    intent: StrictEnum[ProbeIntent]
    discovery_probe_id: NonBlank | None = None
    selected_level: StrictEnum[ProbeLevel]
    target_ledger_ids: tuple[NonBlank, ...] = Field(min_length=1)
    predicate: NonBlank
    contract_digest: ContractDigest
    sandboxable_observable: StrictBool
    requires_runtime_observation: StrictBool
    production_only: StrictBool
    previous_level_insufficiency: NonBlank | None
    skipped_level_reason: NonBlank | None
    execution_scope: StrictEnum[AuthorizationScope] | None
    authorization: ProbeAuthorization | None

    @model_validator(mode="after")
    def selection_and_authority_are_consistent(self) -> ProbeDecision:
        expected = select_probe_level(
            sandboxable_observable=self.sandboxable_observable,
            requires_runtime_observation=self.requires_runtime_observation,
            production_only=self.production_only,
        )
        if self.selected_level is not expected:
            raise PydanticCustomError("probe_selected_level", "selected_level must equal deterministic selection")
        if len(self.target_ledger_ids) != len(set(self.target_ledger_ids)):
            raise PydanticCustomError("probe_targets", "target ledger IDs must be unique")
        match self.intent:
            case ProbeIntent.DISCOVERY:
                if self.discovery_probe_id is not None:
                    raise PydanticCustomError("probe_discovery_reference", "discovery cannot reference discovery")
            case ProbeIntent.TARGETED_CONFIRMATION:
                if self.discovery_probe_id is None:
                    raise PydanticCustomError("probe_discovery_reference", "confirmation requires discovery")
            case unreachable:
                assert_never(unreachable)
        match self.selected_level:
            case ProbeLevel.L0:
                self._require_local(previous_required=False, skipped_required=False)
            case ProbeLevel.L1:
                self._require_local(previous_required=True, skipped_required=False)
            case ProbeLevel.L2:
                self._require_authorized({AuthorizationScope.L2_PROTOTYPE_OBSERVATION})
            case ProbeLevel.L3:
                self._require_authorized({AuthorizationScope.L3_PRODUCTION_TELEMETRY})
            case unreachable:
                assert_never(unreachable)
        return self

    def _require_local(self, *, previous_required: bool, skipped_required: bool) -> None:
        if previous_required != (self.previous_level_insufficiency is not None):
            raise PydanticCustomError("probe_insufficiency", "previous-level insufficiency mismatch")
        if skipped_required != (self.skipped_level_reason is not None):
            raise PydanticCustomError("probe_skip", "skipped-level reason mismatch")
        if self.execution_scope is not None or self.authorization is not None:
            raise PydanticCustomError("probe_authorization", "L0/L1 cannot carry authorization")

    def _require_authorized(self, allowed_scopes: set[AuthorizationScope]) -> None:
        if self.previous_level_insufficiency is None or self.skipped_level_reason is None:
            raise PydanticCustomError("probe_insufficiency", "L2/L3 require insufficiency and skip reasons")
        if self.execution_scope not in allowed_scopes or self.authorization is None:
            message = "exact authorization required; production-only requires production scope"
            raise PydanticCustomError("probe_authorization", message)
        authority = self.authorization
        if (
            authority.level is not self.selected_level
            or authority.scope is not self.execution_scope
            or authority.target_ledger_ids != self.target_ledger_ids
            or authority.contract_digest != self.contract_digest
        ):
            raise PydanticCustomError("probe_authorization", "authorization binding mismatch")


class ProducerLineage(_ContractModel):
    producer_id: NonBlank
    independence_key: NonBlank
    kind: StrictEnum[ProducerKind]


class ProbeResult(_ContractModel):
    """Immutable observation metadata; it never performs the probe."""

    result_id: NonBlank
    decision_id: NonBlank
    intent: StrictEnum[ProbeIntent]
    level: StrictEnum[ProbeLevel]
    target_ledger_ids: tuple[NonBlank, ...] = Field(min_length=1)
    contract_digest: ContractDigest
    producer_lineages: tuple[ProducerLineage, ...] = Field(min_length=1)
    artifact_refs: tuple[NonBlank, ...] = Field(min_length=1)
    outcome: StrictEnum[ProbeOutcome]
    evidence_credit: StrictInt = Field(ge=0)
    completeness_credit: StrictInt = Field(ge=0)
    reopen_required: StrictBool
    gap_origin: Literal["origin:probe"] | None

    @model_validator(mode="after")
    def lineage_and_effect_match_level_and_outcome(self) -> ProbeResult:
        independence = tuple(item.independence_key for item in self.producer_lineages)
        if len(independence) != len(set(independence)):
            raise PydanticCustomError("probe_lineage", "producer lineages must be independent")
        kinds = tuple(item.kind for item in self.producer_lineages)
        match self.level:
            case ProbeLevel.L0:
                valid = set(kinds) == {ProducerKind.REPO_DOCS, ProducerKind.FRESH_IMPLEMENTER}
            case ProbeLevel.L1:
                valid = len(kinds) == 2 and set(kinds) == {ProducerKind.BEHAVIORAL_STUB}
            case ProbeLevel.L2:
                valid = set(kinds) == {
                    ProducerKind.EXECUTABLE_PROTOTYPE,
                    ProducerKind.USER_RUNTIME_OBSERVATION,
                }
            case ProbeLevel.L3:
                valid = set(kinds) <= {
                    ProducerKind.STAGED_TELEMETRY,
                    ProducerKind.PRODUCTION_TELEMETRY,
                }
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise PydanticCustomError("probe_lineage", "producer lineage shape does not match level")
        match self.outcome:
            case ProbeOutcome.NO_MATERIAL_DIVERGENCE | ProbeOutcome.INCONCLUSIVE:
                if self.evidence_credit != 0 or self.completeness_credit != 0:
                    raise PydanticCustomError(
                        "probe_zero_credit",
                        "no-divergence and inconclusive results must have zero credit",
                    )
                if self.reopen_required or self.gap_origin is not None:
                    raise PydanticCustomError("probe_reopen", "non-divergence cannot reopen the ledger")
            case ProbeOutcome.MATERIAL_DIVERGENCE:
                if not self.reopen_required or self.gap_origin != "origin:probe":
                    raise PydanticCustomError(
                        "probe_reopen",
                        "material divergence must reopen with origin:probe",
                    )
            case unreachable:
                assert_never(unreachable)
        return self


class ProbeAttempt(_ContractModel):
    decision: ProbeDecision
    result: ProbeResult

    @model_validator(mode="after")
    def result_matches_decision(self) -> ProbeAttempt:
        if (
            self.result.decision_id != self.decision.probe_id
            or self.result.intent is not self.decision.intent
            or self.result.level is not self.decision.selected_level
            or self.result.target_ledger_ids != self.decision.target_ledger_ids
            or self.result.contract_digest != self.decision.contract_digest
        ):
            raise PydanticCustomError(
                "probe_result_binding",
                "result identity, target, level, intent, and digest must match decision",
            )
        if self.decision.production_only and {
            item.kind for item in self.result.producer_lineages
        } != {ProducerKind.PRODUCTION_TELEMETRY}:
            raise PydanticCustomError("probe_production_lineage", "production-only L3 requires production telemetry")
        return self


class ProbeSequence(_ContractModel):
    """At most one discovery followed by one targeted confirmation."""

    attempts: tuple[ProbeAttempt, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def discovery_then_optional_confirmation(self) -> ProbeSequence:
        probe_ids = tuple(attempt.decision.probe_id for attempt in self.attempts)
        if len(probe_ids) != len(set(probe_ids)):
            raise PydanticCustomError("probe_id", "probe_id values must be unique")
        result_ids = tuple(attempt.result.result_id for attempt in self.attempts)
        if len(result_ids) != len(set(result_ids)):
            raise PydanticCustomError("result_id", "result_id values must be unique")
        if self.attempts[0].decision.intent is not ProbeIntent.DISCOVERY:
            raise PydanticCustomError("probe_sequence", "sequence must start with discovery")
        if len(self.attempts) == 2:
            first, second = self.attempts
            if second.decision.intent is not ProbeIntent.TARGETED_CONFIRMATION:
                raise PydanticCustomError("probe_sequence", "second attempt must be confirmation")
            if second.decision.discovery_probe_id != first.decision.probe_id:
                raise PydanticCustomError("probe_discovery_reference", "confirmation must reference discovery")
            if second.decision.predicate != first.decision.predicate:
                raise PydanticCustomError("probe_predicate", "confirmation predicate must match discovery")
            if (
                second.decision.target_ledger_ids != first.decision.target_ledger_ids
                or second.decision.contract_digest != first.decision.contract_digest
            ):
                raise PydanticCustomError(
                    "probe_sequence",
                    "confirmation must bind the discovery target and digest",
                )
        return self
