"""Reporter-owned authorization and status-only holdout aggregation interface.

Only the reporter service may issue an aggregation authorization.  Controllers can
hold an opaque authorization record but receive no holdout aggregate or raw score
from this API.  Real reporter provisioning is deliberately absent from this local
package and therefore blocks rather than attempting a network call.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import re
from typing import Annotated, Literal, NoReturn, Protocol
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")

Identifier = Annotated[StrictStr, Field(min_length=3, max_length=64)]


class ReporterServiceUnavailable(RuntimeError):
    """Raised when a live reporter adapter has not been separately provisioned."""


class ReporterAuthorizationError(ValueError):
    """Raised when an aggregation request lacks reporter-issued authority."""


ServiceUnavailableError = ReporterServiceUnavailable


class AggregationStatus(StrEnum):
    """Publication state only; it carries no metric or score."""

    PUBLISHED = "published"
    SIMULATED = "simulated"
    BLOCKED = "blocked"
    FAILED = "failed"


class _StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class ReporterAuthorizationRequest(_StrictServiceModel):
    """A request made to the reporter to issue its own scoped authority."""

    schema_: Literal["ReporterAuthorizationRequest.v1"] = Field(
        default="ReporterAuthorizationRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    run_id: Identifier
    requester_role: Literal["reporter"] = "reporter"

    @field_validator("request_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class HoldoutAggregationAuthorization(_StrictServiceModel):
    """Opaque, reporter-issued authority limited to a single holdout run."""

    schema_: Literal["HoldoutAggregationAuthorization.v1"] = Field(
        default="HoldoutAggregationAuthorization.v1", alias="schema", serialization_alias="schema"
    )
    authorization_id: Identifier
    run_id: Identifier
    subject_role: Literal["reporter"] = "reporter"
    scope: Literal["holdout-aggregation"] = "holdout-aggregation"
    provenance: Literal["trusted-reporter", "deterministic-fake"]

    @field_validator("authorization_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class HoldoutAggregationRequest(_StrictServiceModel):
    """A score-free request to let the reporter aggregate inside its boundary."""

    schema_: Literal["HoldoutAggregationRequest.v1"] = Field(
        default="HoldoutAggregationRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    run_id: Identifier
    evaluator_receipt_id: Identifier
    authorization: HoldoutAggregationAuthorization

    @field_validator("request_id", "run_id", "evaluator_receipt_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @model_validator(mode="after")
    def require_reporter_scope_for_same_run(self) -> "HoldoutAggregationRequest":
        if self.authorization.run_id != self.run_id:
            raise ValueError("holdout aggregation authorization is bound to a different run")
        if self.authorization.subject_role != "reporter":
            raise ValueError("holdout aggregation requires reporter-only authorization")
        if self.authorization.scope != "holdout-aggregation":
            raise ValueError("holdout aggregation authorization has the wrong scope")
        return self


class HoldoutAggregationReceipt(_StrictServiceModel):
    """A status receipt; the aggregate remains private to the reporter."""

    schema_: Literal["HoldoutAggregationReceipt.v1"] = Field(
        default="HoldoutAggregationReceipt.v1", alias="schema", serialization_alias="schema"
    )
    receipt_id: Identifier
    request_id: Identifier
    run_id: Identifier
    status: AggregationStatus
    provenance: Literal["trusted-reporter", "deterministic-fake"]
    assurance: Literal["none"] = "none"

    @field_validator("receipt_id", "request_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class ReporterClient(Protocol):
    """The reporter is the sole authority for holdout aggregation."""

    def authorize_holdout(
        self, request: ReporterAuthorizationRequest
    ) -> HoldoutAggregationAuthorization:
        """Issue reporter-owned, run-bound authority."""

    def aggregate_holdout(self, request: HoldoutAggregationRequest) -> HoldoutAggregationReceipt:
        """Aggregate privately and return only a publication status."""


class UnavailableReporterClient:
    """Fail-closed default that cannot issue authority or aggregate any holdout."""

    def authorize_holdout(self, request: ReporterAuthorizationRequest) -> NoReturn:
        del request
        raise ReporterServiceUnavailable(
            "live reporter endpoint is unavailable; provide a trusted adapter explicitly"
        )

    def aggregate_holdout(self, request: HoldoutAggregationRequest) -> NoReturn:
        del request
        raise ReporterServiceUnavailable(
            "live reporter endpoint is unavailable; provide a trusted adapter explicitly"
        )


class FakeReporterClient:
    """Hermetic test adapter that marks authorization and output as simulated."""

    def authorize_holdout(
        self, request: ReporterAuthorizationRequest
    ) -> HoldoutAggregationAuthorization:
        digest = sha256(f"authorization:{request.request_id}:{request.run_id}".encode("utf-8")).hexdigest()
        return HoldoutAggregationAuthorization(
            authorization_id=f"auth-{digest[:24]}",
            run_id=request.run_id,
            provenance="deterministic-fake",
        )

    def issue_authorization(self, request: ReporterAuthorizationRequest) -> HoldoutAggregationAuthorization:
        """Compatibility spelling for tests; authority still originates in this reporter."""

        return self.authorize_holdout(request)

    def aggregate_holdout(self, request: HoldoutAggregationRequest) -> HoldoutAggregationReceipt:
        if request.authorization.provenance != "deterministic-fake":
            raise ReporterAuthorizationError("fake reporter rejects non-fake reporter authorization")
        digest = sha256(
            f"aggregate:{request.request_id}:{request.run_id}:{request.evaluator_receipt_id}".encode("utf-8")
        ).hexdigest()
        return HoldoutAggregationReceipt(
            receipt_id=f"report-{digest[:24]}",
            request_id=request.request_id,
            run_id=request.run_id,
            status=AggregationStatus.SIMULATED,
            provenance="deterministic-fake",
        )
