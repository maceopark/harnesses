#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Final, Literal, Protocol, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

from scripts import build_contract_schema, probe_policy

POLICY_VERSION: Final[Literal["v2-receipt-policy-1"]] = "v2-receipt-policy-1"
RECEIPT_SCHEMA_VERSION: Final[int] = 2
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


@dataclass(frozen=True, slots=True)
class ReceiptContractError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class ReceiptKind(StrEnum):
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    VERIFICATION = "verification"
    PROBE = "probe"


class ReceiptOutcome(StrEnum):
    SUCCESS = "success"
    NONZERO = "nonzero"
    TIMEOUT = "timeout"
    FAILURE = "failure"


class TrustLevel(StrEnum):
    UNTRUSTED = "untrusted"
    SIMULATED = "simulated"
    TEST_ONLY = "test-only"


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ReceiptContractError("timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise ReceiptContractError("timestamp must include an offset")
    return parsed.astimezone(UTC)


class ReceiptEnvelope(StrictModel):
    schema_version: StrictInt = Field(default=RECEIPT_SCHEMA_VERSION, frozen=True)
    receipt_id: NonBlank
    kind: ReceiptKind
    session_id: NonBlank
    manifest_digest: Digest
    contract_digest: Digest
    policy_version: Literal["v2-receipt-policy-1"]
    issuer_id: NonBlank
    key_epoch: NonBlank
    issued_at: NonBlank
    expires_at: NonBlank
    nonce: NonBlank
    subject_digest: Digest
    action_digest: Digest | None
    claim_digest: Digest | None
    artifact_digest: Digest
    stdout_digest: Digest
    stderr_digest: Digest
    verification_id: NonBlank | None
    probe_id: NonBlank | None
    observation_spec_digest: Digest | None
    outcome: ReceiptOutcome
    impact_weight: Literal[1, 2, 3, 5]
    declared_trust: TrustLevel

    @model_validator(mode="after")
    def is_strictly_bound(self) -> Self:
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            raise ReceiptContractError("unknown receipt schema version")
        if parse_timestamp(self.issued_at) >= parse_timestamp(self.expires_at):
            raise ReceiptContractError("receipt expires_at must follow issued_at")
        if (self.action_digest is None) == (self.claim_digest is None):
            raise ReceiptContractError("receipt requires exactly one action_digest or claim_digest")
        match self.kind:
            case ReceiptKind.EVIDENCE | ReceiptKind.AUTHORITY:
                if (
                    self.claim_digest is None
                    or self.verification_id is not None
                    or self.probe_id is not None
                    or self.observation_spec_digest is not None
                ):
                    raise ReceiptContractError("evidence and authority receipts require only a claim digest")
            case ReceiptKind.VERIFICATION:
                if (
                    self.action_digest is None
                    or self.verification_id is None
                    or self.probe_id is not None
                    or self.observation_spec_digest is not None
                ):
                    raise ReceiptContractError("verification receipt requires verification_id and action_digest")
            case ReceiptKind.PROBE:
                if (
                    self.action_digest is None
                    or self.verification_id is not None
                    or self.probe_id is None
                    or self.observation_spec_digest is None
                    or self.action_digest != self.observation_spec_digest
                ):
                    raise ReceiptContractError("probe receipt requires its canonical observation_spec_digest")
            case unreachable:
                assert_never(unreachable)
        return self


class StoredReceipt(StrictModel):
    envelope: ReceiptEnvelope
    receipt_digest: Digest
    trust_level: TrustLevel
    settlement_credit: StrictInt = Field(ge=0, le=0)

    @model_validator(mode="after")
    def digest_is_canonical(self) -> Self:
        if self.receipt_digest != receipt_digest(self.envelope):
            raise ReceiptContractError("stored receipt digest does not match the envelope")
        return self


@dataclass(frozen=True, slots=True)
class IssuerRecord:
    issuer_id: str
    key_epoch: str
    trust_level: TrustLevel
    revoked: bool


class TrustRegistry(Protocol):
    def issuer_record(self, issuer_id: str) -> IssuerRecord | None: ...

    def nonce_is_revoked(self, nonce: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProviderFreeRegistry:
    def issuer_record(self, issuer_id: str) -> IssuerRecord | None:
        return None

    def nonce_is_revoked(self, nonce: str) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class StaticTrustRegistry:
    issuers: tuple[IssuerRecord, ...]
    revoked_nonces: tuple[str, ...]

    def issuer_record(self, issuer_id: str) -> IssuerRecord | None:
        matches = tuple(record for record in self.issuers if record.issuer_id == issuer_id)
        if len(matches) > 1:
            raise ReceiptContractError("trust registry has duplicate issuer records")
        if matches:
            return matches[0]
        return None

    def nonce_is_revoked(self, nonce: str) -> bool:
        return nonce in self.revoked_nonces


def canonical_digest(payload: dict[str, str | list[str] | None]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verification_action_digest(
    contract: build_contract_schema.BuildContract,
    verification_id: str,
) -> str:
    matches = tuple(item for item in contract.verifications if item.id == verification_id)
    if len(matches) != 1:
        raise ReceiptContractError("verification_id must exist exactly once in BuildContract")
    verification = matches[0]
    return canonical_digest(
        {
            "verification_id": verification.id,
            "command_action": verification.command_action,
            "pass_condition": verification.pass_condition,
            "run_policy": verification.run_policy.value,
        },
    )


def observation_spec_digest(decision: probe_policy.ProbeDecision) -> str:
    return canonical_digest(
        {
            "probe_id": decision.probe_id,
            "target_ledger_ids": list(decision.target_ledger_ids),
            "predicate": decision.predicate,
            "selected_level": decision.selected_level.value,
            "execution_scope": (
                decision.execution_scope.value
                if decision.execution_scope is not None
                else None
            ),
        },
    )


def receipt_digest(envelope: ReceiptEnvelope) -> str:
    return hashlib.sha256(
        json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
    ).hexdigest()


def resolve_trust(envelope: ReceiptEnvelope, registry: TrustRegistry) -> TrustLevel:
    if registry.nonce_is_revoked(envelope.nonce):
        raise ReceiptContractError("receipt nonce is revoked")
    record = registry.issuer_record(envelope.issuer_id)
    if record is not None:
        if record.revoked:
            raise ReceiptContractError("receipt issuer is revoked")
        if record.key_epoch != envelope.key_epoch:
            raise ReceiptContractError("receipt key epoch does not match the issuer record")
        return record.trust_level
    match envelope.declared_trust:
        case TrustLevel.SIMULATED:
            return TrustLevel.SIMULATED
        case TrustLevel.UNTRUSTED | TrustLevel.TEST_ONLY:
            return TrustLevel.UNTRUSTED
        case unreachable:
            assert_never(unreachable)


def settlement_credit(trust_level: TrustLevel, impact_weight: int) -> int:
    match trust_level:
        case TrustLevel.UNTRUSTED | TrustLevel.SIMULATED | TrustLevel.TEST_ONLY:
            return 0
        case unreachable:
            assert_never(unreachable)
