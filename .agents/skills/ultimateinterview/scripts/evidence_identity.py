#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, ClassVar, Final, Protocol, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator

POLICY_VERSION: Final[str] = "v2-evidence-identity-1"
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


@dataclass(frozen=True, slots=True)
class EvidenceIdentityError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class VerifierTrust(StrEnum):
    UNTRUSTED = "untrusted"
    SIMULATED = "simulated"
    AUTHENTICATED = "authenticated"


class ClaimantAssertion(StrictModel):
    locator: NonBlank
    revision: NonBlank
    artifact_digest: Digest
    observer: NonBlank
    method: NonBlank
    environment: NonBlank
    as_of: datetime
    ttl_seconds: StrictInt = Field(ge=0)
    dependency_roots: tuple[NonBlank, ...] = Field(min_length=1)
    authority_scope: tuple[NonBlank, ...] = ()
    issuer_id: NonBlank
    key_epoch: NonBlank
    revocation_epoch: NonBlank

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise EvidenceIdentityError("claimant assertion as_of must include a timezone")
        return value

    @field_validator("dependency_roots", "authority_scope")
    @classmethod
    def require_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise EvidenceIdentityError("claimant assertion values must be unique")
        return values


class VerificationRequest(StrictModel):
    canonical_claim: NonBlank
    assertion: ClaimantAssertion

    @property
    def binding_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        ).hexdigest()

    @property
    def expires_at(self) -> datetime:
        return self.assertion.as_of + timedelta(seconds=self.assertion.ttl_seconds)


class VerifierResult(StrictModel):
    trust: VerifierTrust
    binding_digest: Digest
    dependency_roots: tuple[NonBlank, ...] = ()
    authority_scope: tuple[NonBlank, ...] = ()
    issuer_id: NonBlank | None = None
    key_epoch: NonBlank | None = None
    revocation_epoch: NonBlank | None = None
    revoked: StrictBool

    @field_validator("dependency_roots", "authority_scope")
    @classmethod
    def require_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise EvidenceIdentityError("verifier result values must be unique")
        return values

    @model_validator(mode="after")
    def trusted_results_require_identity_coordinates(self) -> VerifierResult:
        match self.trust:
            case VerifierTrust.UNTRUSTED:
                return self
            case VerifierTrust.SIMULATED | VerifierTrust.AUTHENTICATED:
                if None in (self.issuer_id, self.key_epoch, self.revocation_epoch):
                    raise EvidenceIdentityError("trusted verifier result requires identity coordinates")
                return self
            case unreachable:
                assert_never(unreachable)


class VerifierAdapter(Protocol):
    def verify(self, request: VerificationRequest) -> VerifierResult: ...


@dataclass(frozen=True, slots=True)
class ProviderFreeVerifierAdapter:
    def verify(self, request: VerificationRequest) -> VerifierResult:
        return VerifierResult(
            trust=VerifierTrust.UNTRUSTED,
            binding_digest=request.binding_digest,
            dependency_roots=(),
            authority_scope=(),
            issuer_id=None,
            key_epoch=None,
            revocation_epoch=None,
            revoked=False,
        )


@dataclass(frozen=True, slots=True)
class StaticVerifierAdapter:
    result: VerifierResult

    def __post_init__(self) -> None:
        if self.result.trust is VerifierTrust.AUTHENTICATED:
            raise EvidenceIdentityError("static verifier adapter cannot represent authenticated provenance")

    def verify(self, request: VerificationRequest) -> VerifierResult:
        return self.result


class EvidenceAssessment(StrictModel):
    policy_version: str = Field(default=POLICY_VERSION, frozen=True)
    trust: VerifierTrust
    binding_valid: StrictBool
    current: StrictBool
    dependency_roots: tuple[NonBlank, ...]
    settlement_credit: StrictInt = Field(ge=0, le=1)


class ClaimRecord(Protocol):
    @property
    def warrant(self) -> str: ...

    @property
    def identity_assertion(self) -> ClaimantAssertion | None: ...


def verification_request(record: ClaimRecord) -> VerificationRequest:
    if record.identity_assertion is None:
        raise EvidenceIdentityError("claim has no verifier identity assertion")
    return VerificationRequest(canonical_claim=record.warrant, assertion=record.identity_assertion)


def assess(
    request: VerificationRequest,
    *,
    adapter: VerifierAdapter,
    now: datetime,
    impact_weight: int,
) -> EvidenceAssessment:
    if now.tzinfo is None or now.utcoffset() is None:
        raise EvidenceIdentityError("policy clock must include a timezone")
    result = adapter.verify(request)
    if result.trust is VerifierTrust.AUTHENTICATED:
        raise EvidenceIdentityError(
            "authenticated verifier results require a future provider policy version",
        )
    if result.revoked:
        raise EvidenceIdentityError("verifier result is revoked")
    binding_valid = result.binding_digest == request.binding_digest and (
        result.trust is VerifierTrust.UNTRUSTED
        or (
            result.issuer_id == request.assertion.issuer_id
            and result.key_epoch == request.assertion.key_epoch
            and result.revocation_epoch == request.assertion.revocation_epoch
        )
    )
    current = request.assertion.as_of <= now < request.expires_at
    roots = result.dependency_roots if binding_valid and current and result.trust is VerifierTrust.AUTHENTICATED else ()
    has_high_scope = "high-settlement" in result.authority_scope
    credit = int(
        impact_weight >= 3
        and binding_valid
        and current
        and bool(roots)
        and has_high_scope
        and result.trust is VerifierTrust.AUTHENTICATED,
    )
    return EvidenceAssessment(
        trust=result.trust,
        binding_valid=binding_valid,
        current=current,
        dependency_roots=roots,
        settlement_credit=credit,
    )


@dataclass(frozen=True, slots=True)
class VerifierCredit:
    roots: frozenset[str]
    settlement_credit: int


def verifier_credit(
    records: Iterable[ClaimRecord],
    *,
    adapter: VerifierAdapter,
    now: datetime,
    impact_weight: int,
) -> VerifierCredit:
    assessments = tuple(
        assess(verification_request(record), adapter=adapter, now=now, impact_weight=impact_weight)
        for record in records
        if record.identity_assertion is not None
    )
    return VerifierCredit(
        roots=frozenset(root for assessment in assessments for root in assessment.dependency_roots),
        settlement_credit=max((assessment.settlement_credit for assessment in assessments), default=0),
    )


def verifier_roots(
    records: Iterable[ClaimRecord],
    *,
    adapter: VerifierAdapter,
    now: datetime,
) -> frozenset[str]:
    return verifier_credit(records, adapter=adapter, now=now, impact_weight=5).roots
