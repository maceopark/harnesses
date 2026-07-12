"""Fresh-context postmortem attribution models and fail-closed adapters.

Attribution is intentionally separated from both implementation and evaluation.
Reports carry category labels and digests of sealed evidence, never a private score
or raw holdout evidence.  A fake adapter is useful for mechanics tests only.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import re
from typing import Annotated, Literal, NoReturn, Protocol
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

Identifier = Annotated[StrictStr, Field(min_length=3, max_length=64)]
Digest = Annotated[StrictStr, Field(min_length=64, max_length=64)]


class PostmortemServiceUnavailable(RuntimeError):
    """Raised when a separate, fresh postmortem adapter is not configured."""


ServiceUnavailableError = PostmortemServiceUnavailable


class AttributionCategory(StrEnum):
    """The five mutually distinct sources used for fresh postmortem attribution."""

    SPEC_GAP = "spec_gap"
    IMPLEMENTATION_DEVIATION = "implementation_deviation"
    EVALUATION_UNCERTAINTY = "evaluation_uncertainty"
    EXECUTION_PROCESS_GAP = "execution_process_gap"
    LEGITIMATE_SPEC_EVOLUTION = "legitimate_spec_evolution"


PostmortemAttributionCategory = AttributionCategory


class _StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class PostmortemRequest(_StrictServiceModel):
    """References needed for an independent, fresh-context attribution pass."""

    schema_: Literal["PostmortemRequest.v1"] = Field(
        default="PostmortemRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    run_id: Identifier
    cell_id: Identifier
    artifact_manifest_digest: Digest
    build_contract_digest: Digest
    implementation_digest: Digest
    observation_digest: Digest
    evaluation_receipt_id: Identifier
    fresh_context_id: Identifier

    @field_validator("request_id", "run_id", "cell_id", "evaluation_receipt_id", "fresh_context_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator(
        "artifact_manifest_digest",
        "build_contract_digest",
        "implementation_digest",
        "observation_digest",
    )
    @classmethod
    def validate_digest(cls, value: str, info: object) -> str:
        return _digest(value, getattr(info, "field_name", "digest"))

    @model_validator(mode="after")
    def require_independent_context_name(self) -> "PostmortemRequest":
        if self.fresh_context_id in {self.run_id, self.cell_id, self.evaluation_receipt_id}:
            raise ValueError("fresh_context_id must identify a context independent of the run and receipt")
        return self


class PostmortemAttribution(_StrictServiceModel):
    """One finding with a source category and digest-only evidence references."""

    schema_: Literal["PostmortemAttribution.v1"] = Field(
        default="PostmortemAttribution.v1", alias="schema", serialization_alias="schema"
    )
    attribution_id: Identifier
    criterion_id: Identifier
    category: AttributionCategory
    evidence_digests: tuple[Digest, ...] = Field(min_length=1, max_length=16)

    @field_validator("attribution_id", "criterion_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("evidence_digests")
    @classmethod
    def validate_evidence_digests(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_digest(digest, "evidence_digest") for digest in value)
        if normalized != tuple(sorted(normalized)) or len(set(normalized)) != len(normalized):
            raise ValueError("evidence_digests must be unique and sorted")
        return normalized


class PostmortemReport(_StrictServiceModel):
    """An independently attributed report without raw evaluation evidence."""

    schema_: Literal["PostmortemReport.v1"] = Field(
        default="PostmortemReport.v1", alias="schema", serialization_alias="schema"
    )
    report_id: Identifier
    request_id: Identifier
    run_id: Identifier
    cell_id: Identifier
    fresh_context_id: Identifier
    artifact_manifest_digest: Digest
    build_contract_digest: Digest
    implementation_digest: Digest
    observation_digest: Digest
    independent: Literal[True] = True
    attributions: tuple[PostmortemAttribution, ...] = Field(max_length=64)
    provenance: Literal["trusted-service", "deterministic-fake", "oci-deterministic-worker"]
    assurance: Literal["none"] = "none"

    @field_validator("report_id", "request_id", "run_id", "cell_id", "fresh_context_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))
    @field_validator(
        "artifact_manifest_digest",
        "build_contract_digest",
        "implementation_digest",
        "observation_digest",
    )
    @classmethod
    def validate_digests(cls, value: str, info: object) -> str:
        return _digest(value, getattr(info, "field_name", "digest"))

    @model_validator(mode="after")
    def require_attribution_evidence_closure(self) -> "PostmortemReport":
        expected = tuple(
            sorted(
                {
                    self.artifact_manifest_digest,
                    self.build_contract_digest,
                    self.implementation_digest,
                    self.observation_digest,
                }
            )
        )
        observed = {
            digest
            for attribution in self.attributions
            for digest in attribution.evidence_digests
        }
        if not set(expected).issubset(observed):
            raise ValueError("postmortem attributions must cover the declared evidence closure")
        return self

    @field_validator("attributions")
    @classmethod
    def validate_attributions(
        cls, value: tuple[PostmortemAttribution, ...]
    ) -> tuple[PostmortemAttribution, ...]:
        identifiers = tuple(attribution.attribution_id for attribution in value)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("postmortem attribution_id values must be unique")
        return value


FreshPostmortemReport = PostmortemReport


class PostmortemClient(Protocol):
    """Interface for a separately provisioned, fresh-context attribution service."""

    def attribute(self, request: PostmortemRequest) -> PostmortemReport:
        """Return categories and sealed-evidence digests, never a holdout score."""


class UnavailablePostmortemClient:
    """Fail-closed default; no local code attempts to recreate a fresh review."""

    def attribute(self, request: PostmortemRequest) -> NoReturn:
        del request
        raise PostmortemServiceUnavailable(
            "live postmortem endpoint is unavailable; provide a trusted adapter explicitly"
        )


class FakePostmortemClient:
    """Deterministic mechanics adapter, explicitly not independent live evidence."""

    _categories = tuple(AttributionCategory)

    def __init__(
        self,
        *,
        provenance: Literal["deterministic-fake", "oci-deterministic-worker"] = "deterministic-fake",
    ) -> None:
        self._provenance = provenance

    def attribute(self, request: PostmortemRequest) -> PostmortemReport:
        digest = sha256(
            f"{request.request_id}:{request.run_id}:{request.cell_id}:{request.fresh_context_id}".encode(
                "utf-8"
            )
        ).hexdigest()
        category = self._categories[int(digest[:2], 16) % len(self._categories)]
        evidence_digests = tuple(
            sorted(
                {
                    request.artifact_manifest_digest,
                    request.build_contract_digest,
                    request.implementation_digest,
                    request.observation_digest,
                }
            )
        )
        attribution = PostmortemAttribution(
            attribution_id=f"attrib-{digest[:23]}",
            criterion_id="criterion-fake",
            category=category,
            evidence_digests=evidence_digests,
        )
        return PostmortemReport(
            report_id=f"postmortem-{digest[:19]}",
            request_id=request.request_id,
            run_id=request.run_id,
            cell_id=request.cell_id,
            fresh_context_id=request.fresh_context_id,
            artifact_manifest_digest=request.artifact_manifest_digest,
            build_contract_digest=request.build_contract_digest,
            implementation_digest=request.implementation_digest,
            observation_digest=request.observation_digest,
            attributions=(attribution,),
            provenance=self._provenance,
        )


def _identifier(value: str, field_name: str) -> str:
    if normalize("NFC", value) != value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase opaque identifier")
    return value


def _digest(value: str, field_name: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be lowercase SHA-256 hexadecimal")
    return value
