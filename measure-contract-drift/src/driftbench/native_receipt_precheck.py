"""Fail-closed, local validation of coordinate-bound receipt claims.

This module validates supplied JSON only.  It performs no provider/native ABI
calls and cannot manufacture a live, native, or full-v2 assurance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from unicodedata import is_normalized

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionCoordinates(BaseModel):
    """All coordinates that must agree exactly before a receipt is accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    session: str = Field(min_length=1)
    manifest: str = Field(min_length=1)
    contract: str = Field(min_length=1)
    source_part1: str = Field(min_length=1)
    path: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    action: str = Field(min_length=1)

    @field_validator(
        "session", "manifest", "contract", "source_part1", "path", "digest", "subject", "action"
    )
    @classmethod
    def _require_nonblank_nfc(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("coordinate values must be nonblank")
        if not is_normalized("NFC", value):
            raise ValueError("coordinate values must be NFC-normalized")
        return value


class NativeReceipt(BaseModel):
    """A supplied receipt whose policy fields must both indicate success."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["NativeReceipt.v1"] = "NativeReceipt.v1"
    coordinates: ExecutionCoordinates
    verification: Literal["verified"]
    outcome: Literal["success"]


class ReceiptPrecheck(BaseModel):
    """The non-authoritative result of local receipt policy and coordinate checks."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    accepted: bool
    reason: Literal["accepted", "coordinate_mismatch"]


def _coordinates(value: ExecutionCoordinates | Mapping[str, Any]) -> ExecutionCoordinates:
    if isinstance(value, ExecutionCoordinates):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("coordinates must be an ExecutionCoordinates or JSON object")
    return ExecutionCoordinates.model_validate(value, strict=True)


def _receipt(value: NativeReceipt | Mapping[str, Any]) -> NativeReceipt:
    if isinstance(value, NativeReceipt):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("receipt must be a NativeReceipt or JSON object")
    return NativeReceipt.model_validate(value, strict=True)


def precheck_receipt(
    expected: ExecutionCoordinates | Mapping[str, Any],
    receipt: NativeReceipt | Mapping[str, Any],
) -> ReceiptPrecheck:
    """Fail closed unless all eight coordinates and receipt policy fields match.

    Unknown or malformed JSON is rejected by the strict models.  A well-formed
    receipt with any mismatched coordinate returns ``accepted=False`` rather
    than implying an alternate coordinate is acceptable.
    """
    expected_coordinates = _coordinates(expected)
    candidate = _receipt(receipt)
    if candidate.coordinates != expected_coordinates:
        return ReceiptPrecheck(accepted=False, reason="coordinate_mismatch")
    return ReceiptPrecheck(accepted=True, reason="accepted")
