"""Local interfaces for the opaque-token simulator service.

The controller supplies an opaque case token to the trusted simulator and receives
only a response to its own request.  This module deliberately has no endpoint,
credential, or network implementation: the default client blocks live work.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import re
from typing import Annotated, Literal, NoReturn, Protocol
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
_OPAQUE_TOKEN_RE = re.compile(r"[a-z0-9]{8,32}\Z")

Identifier = Annotated[StrictStr, Field(min_length=3, max_length=64)]
OpaqueCaseToken = Annotated[StrictStr, Field(min_length=8, max_length=32)]
SimulatorText = Annotated[StrictStr, Field(min_length=1, max_length=16_384)]


class SimulatorServiceUnavailable(RuntimeError):
    """Raised when the intentionally absent live simulator is requested."""


ServiceUnavailableError = SimulatorServiceUnavailable


class SimulatorResponseClass(StrEnum):
    """The bounded response shapes exposed by the simulator."""

    CLARIFICATION = "clarification"
    BOUNDARY = "boundary"
    ACKNOWLEDGEMENT = "acknowledgement"


class _StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class SimulatorRequest(_StrictServiceModel):
    """One simulator turn addressed only by an opaque case token."""

    schema_: Literal["SimulatorRequest.v1"] = Field(
        default="SimulatorRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    case_token: OpaqueCaseToken
    turn: StrictInt = Field(ge=1, le=1_024)
    message: SimulatorText

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        return _identifier(value, "request_id")

    @field_validator("case_token")
    @classmethod
    def validate_case_token(cls, value: str) -> str:
        if not _OPAQUE_TOKEN_RE.fullmatch(value):
            raise ValueError("case_token must be an opaque lowercase token")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _text(value, "message")


class SimulatorAnswer(_StrictServiceModel):
    """A simulator answer that never echoes the opaque case token."""

    schema_: Literal["SimulatorAnswer.v1"] = Field(
        default="SimulatorAnswer.v1", alias="schema", serialization_alias="schema"
    )
    answer_id: Identifier
    request_id: Identifier
    turn: StrictInt = Field(ge=1, le=1_024)
    response_class: SimulatorResponseClass
    message: SimulatorText
    provenance: Literal["trusted-service", "deterministic-fake"]
    assurance: Literal["none"] = "none"

    @field_validator("answer_id", "request_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _text(value, "message")


class SimulatorClient(Protocol):
    """Trusted simulator interface; implementations must not use controller data as an oracle."""

    def answer(self, request: SimulatorRequest) -> SimulatorAnswer:
        """Return the answer for exactly one validated simulator request."""


class UnavailableSimulatorClient:
    """Fail-closed default used unless a separately provisioned adapter is injected."""

    def answer(self, request: SimulatorRequest) -> NoReturn:
        del request
        raise SimulatorServiceUnavailable(
            "live simulator endpoint is unavailable; provide a trusted adapter explicitly"
        )


class FakeSimulatorClient:
    """Hermetic deterministic adapter for orchestration tests, never live evidence."""

    _classes = (
        SimulatorResponseClass.CLARIFICATION,
        SimulatorResponseClass.BOUNDARY,
        SimulatorResponseClass.ACKNOWLEDGEMENT,
    )

    def answer(self, request: SimulatorRequest) -> SimulatorAnswer:
        digest = sha256(request.request_id.encode("utf-8")).hexdigest()
        response_class = self._classes[int(digest[:2], 16) % len(self._classes)]
        return SimulatorAnswer(
            answer_id=f"simans-{digest[:24]}",
            request_id=request.request_id,
            turn=request.turn,
            response_class=response_class,
            message="Deterministic fake simulator response.",
            provenance="deterministic-fake",
        )


def _identifier(value: str, field_name: str) -> str:
    if normalize("NFC", value) != value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase opaque identifier")
    return value


def _text(value: str, field_name: str) -> str:
    if normalize("NFC", value) != value or value != value.strip() or not value:
        raise ValueError(f"{field_name} must be nonblank, trimmed NFC text")
    if "\x00" in value:
        raise ValueError(f"{field_name} must not contain NUL")
    return value
