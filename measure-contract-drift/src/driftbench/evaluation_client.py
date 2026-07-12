"""Fail-closed, status-only interface to the private evaluator.

The evaluator may score private material behind its own trust boundary.  Its
controller-facing receipt intentionally has no score, metric, verdict, result
reference, or free-text field that could carry a raw holdout value.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import re
from typing import Annotated, Literal, NoReturn, Protocol
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

Identifier = Annotated[StrictStr, Field(min_length=3, max_length=64)]
Digest = Annotated[StrictStr, Field(min_length=64, max_length=64)]


class EvaluationServiceUnavailable(RuntimeError):
    """Raised when no trusted evaluator adapter has been provisioned."""


ServiceUnavailableError = EvaluationServiceUnavailable


class EvaluationStatus(StrEnum):
    """The only evaluation state visible outside the evaluator boundary."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class _StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class EvaluationRequest(_StrictServiceModel):
    """A reference to a sealed submission; it contains neither score nor oracle data."""

    schema_: Literal["EvaluationRequest.v1"] = Field(
        default="EvaluationRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    run_id: Identifier
    partition: Literal["dev", "holdout"]
    submission_manifest_digest: Digest

    @field_validator("request_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("submission_manifest_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("submission_manifest_digest must be lowercase SHA-256 hexadecimal")
        return value


class EvaluationStatusReceipt(_StrictServiceModel):
    """Metadata-only receipt; absence of score-bearing fields is contractual."""

    schema_: Literal["EvaluationStatusReceipt.v2"] = Field(
        default="EvaluationStatusReceipt.v2", alias="schema", serialization_alias="schema"
    )
    receipt_id: Identifier
    request_id: Identifier
    run_id: Identifier
    partition: Literal["dev", "holdout"]
    status: EvaluationStatus
    provenance: Literal["trusted-service", "deterministic-fake"]
    assurance: Literal["none"] = "none"

    @field_validator("receipt_id", "request_id", "run_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class EvaluationClient(Protocol):
    """Private evaluator contract with a deliberately status-only response."""

    def evaluate(self, request: EvaluationRequest) -> EvaluationStatusReceipt:
        """Submit a sealed manifest for evaluation without returning a score."""


class UnavailableEvaluationClient:
    """Fail-closed default; it performs no connection attempt or network call."""

    def evaluate(self, request: EvaluationRequest) -> NoReturn:
        del request
        raise EvaluationServiceUnavailable(
            "live evaluator endpoint is unavailable; provide a trusted adapter explicitly"
        )


class FakeEvaluationClient:
    """Deterministic adapter for tests, marked as fake and never as live evidence."""

    def evaluate(self, request: EvaluationRequest) -> EvaluationStatusReceipt:
        digest = sha256(
            f"{request.request_id}:{request.run_id}:{request.submission_manifest_digest}".encode("utf-8")
        ).hexdigest()
        return EvaluationStatusReceipt(
            receipt_id=f"evalrcpt-{digest[:23]}",
            request_id=request.request_id,
            run_id=request.run_id,
            partition=request.partition,
            status=EvaluationStatus.COMPLETED,
            provenance="deterministic-fake",
        )


def is_status_only_receipt(receipt: EvaluationStatusReceipt) -> bool:
    """Return whether a receipt has exactly the safe, score-free wire fields."""

    return set(receipt.model_dump(mode="json", by_alias=True)) == {
        "schema",
        "receipt_id",
        "request_id",
        "run_id",
        "partition",
        "status",
        "provenance",
        "assurance",
    }


def _identifier(value: str, field_name: str) -> str:
    if normalize("NFC", value) != value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase opaque identifier")
    return value
