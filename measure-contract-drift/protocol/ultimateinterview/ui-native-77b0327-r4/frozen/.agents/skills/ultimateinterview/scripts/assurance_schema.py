#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


@dataclass(frozen=True, slots=True)
class AssuranceValidationError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class AbiVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class TraceVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class PropertyVerdict(StrEnum):
    NOT_RUN = "not-run"
    RECEIPT_INVALID = "receipt-invalid"
    OBSERVED_PASS = "observed-pass"
    OBSERVED_FAIL = "observed-fail"


class AdequacyVerdict(StrEnum):
    NOT_ASSESSED = "not-assessed"
    CHALLENGE_PASSED = "challenge-passed"
    CHALLENGE_FOUND_GAP = "challenge-found-gap"


class StakeholderVerdict(StrEnum):
    NOT_SOUGHT = "not-sought"
    ATTESTATION_INVALID = "attestation-invalid"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ArtifactState(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"


class ReceiptState(StrEnum):
    ABSENT = "absent"
    NON_CREDITABLE = "non-creditable"
    MALFORMED = "malformed"
    STALE = "stale"
    REPLAYED = "replayed"
    BOUND_SUCCESS = "bound-success"
    BOUND_NONZERO = "bound-nonzero"
    BOUND_TIMEOUT = "bound-timeout"
    BOUND_FAILURE = "bound-failure"


class AssuranceInputs(StrictModel):
    manifest: ArtifactState
    sidecar: ArtifactState
    requirements_covered: StrictBool
    atoms_covered: StrictBool
    receipt: ReceiptState
    adequacy: AdequacyVerdict = AdequacyVerdict.NOT_ASSESSED
    stakeholder: StakeholderVerdict = StakeholderVerdict.NOT_SOUGHT


class AssuranceResult(StrictModel):
    schema_version: StrictInt = Field(default=2, frozen=True)
    abi: AbiVerdict
    trace: TraceVerdict
    property: PropertyVerdict
    adequacy: AdequacyVerdict
    stakeholder: StakeholderVerdict

    @model_validator(mode="after")
    def schema_version_is_v2(self) -> Self:
        if self.schema_version != 2:
            raise AssuranceValidationError("AssuranceResult requires schema_version 2")
        match (self.abi, self.property):
            case (
                AbiVerdict.FAIL,
                PropertyVerdict.OBSERVED_PASS | PropertyVerdict.OBSERVED_FAIL,
            ):
                raise AssuranceValidationError(
                    "an observed property verdict requires abi=pass",
                )
            case (
                AbiVerdict.PASS,
                _,
            ) | (
                AbiVerdict.FAIL,
                PropertyVerdict.NOT_RUN | PropertyVerdict.RECEIPT_INVALID,
            ):
                pass
            case unreachable:
                assert_never(unreachable)
        return self


def abi_verdict(inputs: AssuranceInputs) -> AbiVerdict:
    match inputs.manifest:
        case ArtifactState.VALID:
            match inputs.sidecar:
                case ArtifactState.VALID:
                    return AbiVerdict.PASS
                case ArtifactState.MISSING | ArtifactState.INVALID | ArtifactState.STALE:
                    return AbiVerdict.FAIL
                case unreachable:
                    assert_never(unreachable)
        case ArtifactState.MISSING | ArtifactState.INVALID | ArtifactState.STALE:
            return AbiVerdict.FAIL
        case unreachable:
            assert_never(unreachable)


def trace_verdict(inputs: AssuranceInputs) -> TraceVerdict:
    if inputs.requirements_covered and inputs.atoms_covered:
        return TraceVerdict.PASS
    return TraceVerdict.FAIL


def property_verdict(inputs: AssuranceInputs, abi: AbiVerdict) -> PropertyVerdict:
    match inputs.receipt:
        case ReceiptState.ABSENT | ReceiptState.NON_CREDITABLE:
            return PropertyVerdict.NOT_RUN
        case ReceiptState.MALFORMED | ReceiptState.STALE | ReceiptState.REPLAYED:
            return PropertyVerdict.RECEIPT_INVALID
        case ReceiptState.BOUND_SUCCESS:
            match abi:
                case AbiVerdict.PASS:
                    return PropertyVerdict.OBSERVED_PASS
                case AbiVerdict.FAIL:
                    return PropertyVerdict.RECEIPT_INVALID
                case unreachable:
                    assert_never(unreachable)
        case ReceiptState.BOUND_NONZERO | ReceiptState.BOUND_TIMEOUT | ReceiptState.BOUND_FAILURE:
            match abi:
                case AbiVerdict.PASS:
                    return PropertyVerdict.OBSERVED_FAIL
                case AbiVerdict.FAIL:
                    return PropertyVerdict.RECEIPT_INVALID
                case unreachable:
                    assert_never(unreachable)
        case unreachable:
            assert_never(unreachable)


def derive_assurance_result(inputs: AssuranceInputs) -> AssuranceResult:
    abi = abi_verdict(inputs)
    return AssuranceResult(
        abi=abi,
        trace=trace_verdict(inputs),
        property=property_verdict(inputs, abi),
        adequacy=inputs.adequacy,
        stakeholder=inputs.stakeholder,
    )


def validate_protocol_assurance_result(result: AssuranceResult) -> None:
    match result.property:
        case PropertyVerdict.NOT_RUN | PropertyVerdict.RECEIPT_INVALID:
            return
        case PropertyVerdict.OBSERVED_PASS | PropertyVerdict.OBSERVED_FAIL:
            raise AssuranceValidationError(
                "schema v2 protocol cannot assert an observed property without a receipt-backed import",
            )
        case unreachable:
            assert_never(unreachable)
