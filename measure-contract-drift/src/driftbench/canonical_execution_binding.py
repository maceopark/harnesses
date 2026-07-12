"""Canonical JSON and content-bound execution bindings.

The canonical representation is compact, sorted-key UTF-8 JSON with every
string normalized to NFC.  Binding digests are SHA-256 hex digests of exactly
those canonical bytes; no ambient state or provider data participates.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, Literal, TypeAlias
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _canonicalize(value: Any, path: str = "$") -> JsonValue:
    """Return a JSON-only, NFC-normalized copy or raise for an invalid value."""
    if value is None or isinstance(value, bool):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain a non-finite float")
        return value
    if type(value) is str:
        return normalize("NFC", value)
    if isinstance(value, list):
        return [_canonicalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{path} object keys must be strings")
            canonical_key = normalize("NFC", key)
            if canonical_key in result:
                raise ValueError(f"{path} contains duplicate keys after NFC normalization")
            result[canonical_key] = _canonicalize(item, f"{path}.{canonical_key}")
        return result
    raise TypeError(f"{path} must contain only JSON-compatible values")


def canonical_json_bytes(value: JsonValue | Mapping[str, Any] | list[Any]) -> bytes:
    """Serialize a JSON-compatible value as deterministic canonical UTF-8 JSON."""
    canonical = _canonicalize(value)
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def binding_digest(value: JsonValue | Mapping[str, Any] | list[Any]) -> str:
    """Return the lowercase SHA-256 digest for ``canonical_json_bytes(value)``."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class ExecutionBinding(BaseModel):
    """A self-verifying canonical object binding used by receipt prechecks."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["CanonicalExecutionBinding.v1"] = "CanonicalExecutionBinding.v1"
    payload: dict[str, Any]
    digest: str = Field(min_length=64, max_length=64)

    @field_validator("payload")
    @classmethod
    def _validate_payload(cls, value: dict[str, Any]) -> dict[str, JsonValue]:
        canonical = _canonicalize(value)
        assert isinstance(canonical, dict)
        return canonical

    @field_validator("digest")
    @classmethod
    def _validate_digest_shape(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("digest must be a lowercase SHA-256 hexadecimal digest")
        return value

    @model_validator(mode="after")
    def _verify_digest(self) -> "ExecutionBinding":
        if self.digest != binding_digest(self.payload):
            raise ValueError("digest does not bind the canonical payload")
        return self

    @property
    def canonical_payload(self) -> bytes:
        """The exact bytes covered by :attr:`digest`."""
        return canonical_json_bytes(self.payload)


def build_execution_binding(payload: Mapping[str, Any]) -> ExecutionBinding:
    """Build a verified binding from a JSON-object payload.

    The input must be a mapping; its canonical NFC-normalized copy is retained
    in the returned model and is the sole digest input.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("execution binding payload must be a JSON object")
    canonical = _canonicalize(payload)
    assert isinstance(canonical, dict)
    return ExecutionBinding(payload=canonical, digest=binding_digest(canonical))
