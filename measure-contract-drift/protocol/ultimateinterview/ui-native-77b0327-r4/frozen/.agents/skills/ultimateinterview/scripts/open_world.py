#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
# ]
# ///

"""Standalone open-world sweep contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, ClassVar, Literal, assert_never

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


def _strict_enum(value: str | StrEnum) -> str | StrEnum:
    if not isinstance(value, str):
        raise PydanticCustomError("strict_enum", "enum input must be a string")
    return value


type StrictEnum[T: StrEnum] = Annotated[T, BeforeValidator(_strict_enum)]


class OpenWorldPhase(StrEnum):
    """Zero-cost points at which the open-world model is challenged."""

    ORIENTATION = "orientation"
    BREADTH = "breadth"


class SweepBoundary(StrEnum):
    """The protocol boundary that a recorded pass must precede."""

    LENS_SELECTION = "lens-selection"
    DRY_SWEEP = "dry-sweep"


class CandidateDisposition(StrEnum):
    """Whether a candidate remains live after the pass."""

    SURVIVES = "survives"
    DISMISSED = "dismissed"


class OpenWorldCandidate(BaseModel):
    """One falsifiable implementation-changing possibility from model knowledge."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    candidate_id: NonBlank
    applicability_question: NonBlank
    falsifier: NonBlank
    evidence_route: NonBlank
    disposition: StrictEnum[CandidateDisposition]
    absent_from_current_model: StrictBool
    implementation_changing: StrictBool
    origin: Literal["origin:open-world"]
    claim_kind: Literal["causal-hypothesis"]
    evidence_channel: Literal["assumption"]
    source_actor: Literal["model"]
    provenance_mode: Literal["model-prior"]
    epistemic_authority: Literal["hypothesis-only"]
    decision_authority: Literal["none"]

    @model_validator(mode="after")
    def survivor_is_an_absent_material_hypothesis(self) -> OpenWorldCandidate:
        match self.disposition:
            case CandidateDisposition.SURVIVES:
                if not self.absent_from_current_model or not self.implementation_changing:
                    raise PydanticCustomError(
                        "open_world_survivor",
                        "surviving candidates must be absent and implementation-changing",
                    )
            case CandidateDisposition.DISMISSED:
                pass
            case unreachable:
                assert_never(unreachable)
        return self


class OpenWorldSweep(BaseModel):
    """A replayable zero-cost pass bound to one material ledger revision."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    sweep_id: NonBlank
    phase: StrictEnum[OpenWorldPhase]
    precedes: StrictEnum[SweepBoundary]
    interaction_cost: StrictInt = Field(ge=0, le=0)
    material_revision_binding: StrictInt = Field(ge=0)
    candidates: tuple[OpenWorldCandidate, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def boundary_and_candidate_identity_are_replayable(self) -> OpenWorldSweep:
        match self.phase:
            case OpenWorldPhase.ORIENTATION:
                expected = SweepBoundary.LENS_SELECTION
            case OpenWorldPhase.BREADTH:
                expected = SweepBoundary.DRY_SWEEP
            case unreachable:
                assert_never(unreachable)
        if self.precedes is not expected:
            raise PydanticCustomError(
                "open_world_boundary",
                "phase must bind to its canonical protocol boundary",
            )
        ids = tuple(item.candidate_id for item in self.candidates)
        if len(ids) != len(set(ids)):
            raise PydanticCustomError(
                "open_world_candidate_id",
                "candidate_id values must be unique within a sweep",
            )
        return self

    def is_fresh(self, current_material_revision: int) -> bool:
        """Return whether this observation still describes the material model."""
        return self.material_revision_binding == current_material_revision


class OpenWorldHistory(BaseModel):
    """Ordered sweep records sufficient to replay when novelty was checked."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    records: tuple[OpenWorldSweep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def orientation_precedes_breadth(self) -> OpenWorldHistory:
        phases = tuple(record.phase for record in self.records)
        if phases[0] is not OpenWorldPhase.ORIENTATION:
            raise PydanticCustomError(
                "open_world_order",
                "orientation must be the first open-world record",
            )
        if phases.count(OpenWorldPhase.ORIENTATION) != 1:
            raise PydanticCustomError(
                "open_world_order",
                "history must contain exactly one orientation record",
            )
        sweep_ids = tuple(record.sweep_id for record in self.records)
        if len(sweep_ids) != len(set(sweep_ids)):
            raise PydanticCustomError(
                "open_world_sweep_id",
                "sweep_id values must be unique",
            )
        return self
