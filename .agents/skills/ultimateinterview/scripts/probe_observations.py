#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator
from pydantic_core import PydanticCustomError

from scripts.probe_types import ContractDigest, ContractModel, NonBlank, ProbeDecision, ProbeIntent, ProbeLevel, StrictEnum


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


class ProducerLineage(ContractModel):
    producer_id: NonBlank
    independence_key: NonBlank
    kind: StrictEnum[ProducerKind]


class ProbeResult(ContractModel):
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
                valid = set(kinds) == {ProducerKind.EXECUTABLE_PROTOTYPE, ProducerKind.USER_RUNTIME_OBSERVATION}
            case ProbeLevel.L3:
                valid = set(kinds) <= {ProducerKind.STAGED_TELEMETRY, ProducerKind.PRODUCTION_TELEMETRY}
        if not valid:
            raise PydanticCustomError("probe_lineage", "producer lineage shape does not match level")
        match self.outcome:
            case ProbeOutcome.NO_MATERIAL_DIVERGENCE | ProbeOutcome.INCONCLUSIVE:
                if self.evidence_credit != 0 or self.completeness_credit != 0:
                    raise PydanticCustomError("probe_zero_credit", "no-divergence and inconclusive results must have zero credit")
                if self.reopen_required or self.gap_origin is not None:
                    raise PydanticCustomError("probe_reopen", "non-divergence cannot reopen the ledger")
            case ProbeOutcome.MATERIAL_DIVERGENCE:
                if self.level in {ProbeLevel.L2, ProbeLevel.L3} and (self.evidence_credit != 0 or self.completeness_credit != 0):
                    raise PydanticCustomError("probe_zero_credit", "declared L2/L3 material divergence must have zero credit")
                if not self.reopen_required or self.gap_origin != "origin:probe":
                    raise PydanticCustomError("probe_reopen", "material divergence must reopen with origin:probe")
        return self


class ProbeAttempt(ContractModel):
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
            raise PydanticCustomError("probe_result_binding", "result identity, target, level, intent, and digest must match decision")
        match self.decision.selected_level:
            case ProbeLevel.L3 if self.decision.staged_only:
                if {item.kind for item in self.result.producer_lineages} != {ProducerKind.STAGED_TELEMETRY}:
                    raise PydanticCustomError("probe_staged_lineage", "staged-only L3 requires staged telemetry")
            case ProbeLevel.L3 if self.decision.production_only:
                if {item.kind for item in self.result.producer_lineages} != {ProducerKind.PRODUCTION_TELEMETRY}:
                    raise PydanticCustomError("probe_production_lineage", "production-only L3 requires production telemetry")
            case ProbeLevel.L0 | ProbeLevel.L1 | ProbeLevel.L2:
                pass
            case ProbeLevel.L3:
                raise PydanticCustomError("probe_selection", "L3 requires staged-only or production-only scope")
        return self


class ProbeSequence(ContractModel):
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
            if second.decision.target_ledger_ids != first.decision.target_ledger_ids or second.decision.contract_digest != first.decision.contract_digest:
                raise PydanticCustomError("probe_sequence", "confirmation must bind the discovery target and digest")
        return self
