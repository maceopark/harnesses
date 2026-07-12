#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
type ContractDigest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def _strict_enum(value: object) -> str | StrEnum:
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


def select_probe_level(
    *,
    staged_only: bool | str | int = False,
    sandboxable_observable: bool | str | int,
    requires_runtime_observation: bool | str | int,
    production_only: bool | str | int,
) -> ProbeLevel:
    signals = (
        staged_only,
        production_only,
        requires_runtime_observation,
        sandboxable_observable,
    )
    if any(not isinstance(value, bool) for value in signals) or sum(value is True for value in signals) > 1:
        raise PydanticCustomError("probe_selection", "probe signals must be distinct strict booleans")
    if staged_only or production_only:
        return ProbeLevel.L3
    if requires_runtime_observation:
        return ProbeLevel.L2
    if sandboxable_observable:
        return ProbeLevel.L1
    return ProbeLevel.L0


class ContractModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
    )


class ProbeAuthorization(ContractModel):
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


class ProbeDecision(ContractModel):
    probe_id: NonBlank
    intent: StrictEnum[ProbeIntent]
    discovery_probe_id: NonBlank | None = None
    selected_level: StrictEnum[ProbeLevel]
    target_ledger_ids: tuple[NonBlank, ...] = Field(min_length=1)
    predicate: NonBlank
    contract_digest: ContractDigest
    staged_only: StrictBool = False
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
            staged_only=self.staged_only,
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
        match self.selected_level:
            case ProbeLevel.L0:
                self._require_local(previous_required=False, skipped_required=False)
            case ProbeLevel.L1:
                self._require_local(previous_required=True, skipped_required=False)
            case ProbeLevel.L2:
                self._require_authorized(AuthorizationScope.L2_PROTOTYPE_OBSERVATION)
            case ProbeLevel.L3:
                self._require_authorized(self._required_l3_scope())
        return self

    def _required_l3_scope(self) -> AuthorizationScope:
        match (self.staged_only, self.production_only):
            case (True, False):
                return AuthorizationScope.L3_STAGED_TELEMETRY
            case (False, True):
                return AuthorizationScope.L3_PRODUCTION_TELEMETRY
            case _:
                raise PydanticCustomError("probe_selection", "invalid L3 selector state")

    def _require_local(self, *, previous_required: bool, skipped_required: bool) -> None:
        if previous_required != (self.previous_level_insufficiency is not None):
            raise PydanticCustomError("probe_insufficiency", "previous-level insufficiency mismatch")
        if skipped_required != (self.skipped_level_reason is not None):
            raise PydanticCustomError("probe_skip", "skipped-level reason mismatch")
        if self.execution_scope is not None or self.authorization is not None:
            raise PydanticCustomError("probe_authorization", "L0/L1 cannot carry authorization")

    def _require_authorized(self, required_scope: AuthorizationScope) -> None:
        if self.previous_level_insufficiency is None or self.skipped_level_reason is None:
            raise PydanticCustomError("probe_insufficiency", "L2/L3 require insufficiency and skip reasons")
        if self.execution_scope is not required_scope or self.authorization is None:
            raise PydanticCustomError("probe_authorization", f"exact authorization requires {required_scope.value}")
        authority = self.authorization
        if (
            authority.level is not self.selected_level
            or authority.scope is not self.execution_scope
            or authority.target_ledger_ids != self.target_ledger_ids
            or authority.contract_digest != self.contract_digest
        ):
            raise PydanticCustomError("probe_authorization", "authorization binding mismatch")
