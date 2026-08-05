"""Pure orchestration boundary for gold-informed case generation.

The concrete LLM client belongs to the CLI/infrastructure layer.  Keeping the
request and response JSON-shaped makes it possible to record and digest the
exact payload outside this module without coupling the domain logic to an SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, TypeAlias

JsonObject: TypeAlias = Mapping[str, Any]


class GenerationModel(Protocol):
    """External model boundary used by the case generator."""

    def generate(self, *, role: str, payload: JsonObject) -> JsonObject:
        """Return one JSON object for ``role`` and ``payload``."""


@dataclass(frozen=True)
class GenerationRequest:
    role: str
    payload: JsonObject

    def __post_init__(self) -> None:
        if not self.role.strip():
            raise ValueError("role must not be empty")


def generate_case(model: GenerationModel, request: GenerationRequest) -> dict[str, Any]:
    """Generate a detached mutable JSON object through the model boundary."""

    result = model.generate(role=request.role, payload=request.payload)
    if not isinstance(result, Mapping):
        raise TypeError("generation result must be a JSON object")
    return dict(result)
