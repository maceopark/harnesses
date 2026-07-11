#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run --python 3.14 claim_evidence.py < evidence.json
# 3. Or make executable and run:
#      chmod +x claim_evidence.py && ./claim_evidence.py < evidence.json
# ─────────────────

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Final, Never, assert_never

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator, model_validator

type NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvidenceChannel(StrEnum):
    FROM_CODE = "from-code"
    FROM_DOCS = "from-docs"
    FROM_USER = "from-user"
    FROM_RESEARCH = "from-research"
    FROM_SCENARIO = "from-scenario"
    ASSUMPTION = "assumption"


class ClaimKind(StrEnum):
    OBSERVED_FACT = "observed-fact"
    CAUSAL_HYPOTHESIS = "causal-hypothesis"
    INTERPRETATION = "interpretation"
    NORMATIVE_DECISION = "normative-decision"
    PREFERENCE = "preference"
    FORECAST = "forecast"


class SourceActor(StrEnum):
    USER = "user"
    REPOSITORY = "repository"
    DOCUMENTATION = "documentation"
    RESEARCHER = "researcher"
    SCENARIO = "scenario"
    RUNTIME = "runtime"
    MODEL = "model"


class ProvenanceMode(StrEnum):
    FIRSTHAND = "firsthand"
    DERIVED = "derived"
    MODEL_PRIOR = "model-prior"
    ASSUMPTION = "assumption"


class Freshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class EpistemicAuthority(StrEnum):
    HYPOTHESIS_ONLY = "hypothesis-only"
    CORROBORATES = "corroborates"
    ESTABLISHES = "establishes"


class DecisionAuthority(StrEnum):
    NONE = "none"
    OWNER = "owner"
    DELEGATED = "delegated"


CHANNEL_ALIASES: Final[dict[str, EvidenceChannel]] = {
    "assumption": EvidenceChannel.ASSUMPTION,
    "code": EvidenceChannel.FROM_CODE,
    "doc": EvidenceChannel.FROM_DOCS,
    "docs": EvidenceChannel.FROM_DOCS,
    "from-code": EvidenceChannel.FROM_CODE,
    "from-docs": EvidenceChannel.FROM_DOCS,
    "from-research": EvidenceChannel.FROM_RESEARCH,
    "from-scenario": EvidenceChannel.FROM_SCENARIO,
    "from-user": EvidenceChannel.FROM_USER,
    "research": EvidenceChannel.FROM_RESEARCH,
    "scenario": EvidenceChannel.FROM_SCENARIO,
    "user": EvidenceChannel.FROM_USER,
}


@dataclass(frozen=True, slots=True)
class EvidenceContractError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


class _StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


def _reject(detail: str) -> Never:
    raise ValueError(detail)


class Derivation(_StrictModel):
    derived_from: tuple[NonBlank, ...] = Field(min_length=1)
    method: NonBlank

    @field_validator("derived_from")
    @classmethod
    def require_parent_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            _reject("derived_from evidence ids must be unique")
        return values


class ClaimEvidence(_StrictModel):
    id: NonBlank
    channel: EvidenceChannel
    claim_kind: ClaimKind
    source_actor: SourceActor
    provenance_mode: ProvenanceMode
    derivation: Derivation | None = None
    independence_group: NonBlank
    observed_at: datetime | None = None
    environment: NonBlank | None = None
    freshness: Freshness
    warrant: NonBlank
    counterevidence: tuple[NonBlank, ...] = ()
    epistemic_authority: EpistemicAuthority
    decision_authority: DecisionAuthority = DecisionAuthority.NONE

    @field_validator("counterevidence")
    @classmethod
    def normalize_counterevidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_provenance(self) -> ClaimEvidence:
        if self.channel is EvidenceChannel.ASSUMPTION:
            valid_hypothesis = (
                self.claim_kind is ClaimKind.CAUSAL_HYPOTHESIS
                and self.epistemic_authority is EpistemicAuthority.HYPOTHESIS_ONLY
            )
            if not valid_hypothesis:
                _reject("assumption channel is hypothesis-only")

        match self.provenance_mode:
            case ProvenanceMode.DERIVED:
                if self.derivation is None:
                    _reject("derived evidence requires derivation")
            case ProvenanceMode.FIRSTHAND | ProvenanceMode.MODEL_PRIOR | ProvenanceMode.ASSUMPTION:
                if self.derivation is not None:
                    _reject("only derived evidence may declare derivation")
            case unreachable:
                assert_never(unreachable)

        if self.source_actor is SourceActor.RUNTIME:
            if self.observed_at is None or self.environment is None:
                _reject("runtime observation requires observed_at and environment")
            if self.observed_at.utcoffset() is None:
                _reject("runtime observation requires a timezone-aware observed_at")

        if self.provenance_mode in {ProvenanceMode.MODEL_PRIOR, ProvenanceMode.ASSUMPTION}:
            valid_hypothesis = (
                self.claim_kind is ClaimKind.CAUSAL_HYPOTHESIS
                and self.epistemic_authority is EpistemicAuthority.HYPOTHESIS_ONLY
            )
            if not valid_hypothesis:
                _reject("model-prior and assumption provenance are hypothesis-only")
        return self


class ClaimEvidenceSet(_StrictModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    evidence_records: tuple[ClaimEvidence, ...] = ()
    evidence_channels: tuple[EvidenceChannel, ...] | None = None

    @model_validator(mode="after")
    def validate_collection(self) -> ClaimEvidenceSet:
        by_id = {record.id: record for record in self.evidence_records}
        if len(by_id) != len(self.evidence_records):
            _reject("duplicate evidence id")
        for record in self.evidence_records:
            if record.derivation is not None and any(
                parent not in by_id for parent in record.derivation.derived_from
            ):
                _reject("derived evidence references an unknown evidence id")

        resolved: dict[str, tuple[frozenset[str], bool]] = {}
        active: set[str] = set()

        def lineage(evidence_id: str) -> tuple[frozenset[str], bool]:
            if evidence_id in resolved:
                return resolved[evidence_id]
            if evidence_id in active:
                _reject("evidence derivation cycle is not allowed")
            active.add(evidence_id)
            record = by_id[evidence_id]
            if record.derivation is None:
                result = (frozenset({record.independence_group}), record.epistemic_authority is EpistemicAuthority.HYPOTHESIS_ONLY)
            else:
                parents = tuple(lineage(parent) for parent in record.derivation.derived_from)
                groups = frozenset(group for parent_groups, _ in parents for group in parent_groups)
                if len(groups) > 1:
                    _reject("derived evidence has multiple root independence groups")
                if groups != frozenset({record.independence_group}):
                    _reject("derived evidence must keep its root independence group")
                tainted = any(parent_tainted for _, parent_tainted in parents)
                if tainted and not (
                    record.claim_kind is ClaimKind.CAUSAL_HYPOTHESIS
                    and record.epistemic_authority is EpistemicAuthority.HYPOTHESIS_ONLY
                ):
                    _reject("derived evidence with hypothesis-only lineage must remain hypothesis-only")
                result = (groups, tainted or record.epistemic_authority is EpistemicAuthority.HYPOTHESIS_ONLY)
            active.remove(evidence_id)
            resolved[evidence_id] = result
            return result

        for record in self.evidence_records:
            lineage(record.id)
        if self.evidence_channels is not None:
            if frozenset(self.evidence_channels) != frozenset(self.projected_channels):
                _reject("supplied projected channels must exactly match evidence records")
        return self

    @property
    def projected_channels(self) -> tuple[EvidenceChannel, ...]:
        return tuple(sorted({record.channel for record in self.evidence_records}, key=str))


class EvidenceDelta(_StrictModel):
    schema_version: StrictInt = Field(ge=0, le=1)
    add_channels: tuple[EvidenceChannel, ...] = ()
    add_evidence_records: tuple[ClaimEvidence, ...] = ()

    @model_validator(mode="after")
    def enforce_versioned_surface(self) -> EvidenceDelta:
        if self.schema_version == 0:
            if self.add_evidence_records:
                _reject("add_evidence_records requires evidence schema v1")
        elif self.add_channels:
            _reject("add_channels is legacy-only; v1 uses add_evidence_records")
        return self


def compatibility_independence_groups(
    channels: Iterable[str | EvidenceChannel],
) -> frozenset[str]:
    normalized: set[EvidenceChannel] = set()
    for channel in channels:
        key = str(channel).strip().lower()
        if key not in CHANNEL_ALIASES:
            raise EvidenceContractError(detail=f"unknown evidence channel {channel!r}")
        normalized.add(CHANNEL_ALIASES[key])
    return frozenset(
        f"compat:{channel.value}"
        for channel in normalized
        if channel is not EvidenceChannel.ASSUMPTION
    )


def eligible_independence_groups(records: Iterable[ClaimEvidence]) -> frozenset[str]:
    materialized = ClaimEvidenceSet(evidence_records=tuple(records)).evidence_records
    return frozenset(
        record.independence_group
        for record in materialized
        if record.channel is not EvidenceChannel.ASSUMPTION
        and record.freshness is Freshness.CURRENT
        and record.epistemic_authority is EpistemicAuthority.ESTABLISHES
        and record.provenance_mode is ProvenanceMode.FIRSTHAND
    )


def accepts_explicit_single_source(records: Iterable[ClaimEvidence]) -> bool:
    materialized = tuple(records)
    groups = eligible_independence_groups(materialized)
    if len(groups) != 1:
        return False
    (eligible_group,) = groups
    return any(
        record.independence_group == eligible_group
        and record.decision_authority in {DecisionAuthority.OWNER, DecisionAuthority.DELEGATED}
        and record.independence_group in eligible_independence_groups((record,))
        for record in materialized
    )


def main() -> None:
    record = ClaimEvidence.model_validate_json(sys.stdin.read())
    sys.stdout.write(record.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
