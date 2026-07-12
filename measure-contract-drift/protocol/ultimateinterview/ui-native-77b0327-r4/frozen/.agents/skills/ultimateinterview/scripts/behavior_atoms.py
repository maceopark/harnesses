#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, ClassVar, Final, Iterable, Literal, Protocol, assert_never

from pydantic import BaseModel, ConfigDict, StringConstraints

type AtomId = Annotated[str, StringConstraints(strict=True, pattern=r"^ATOM-[0-9]{3,}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]

ATOM_SCHEMA_VERSION: Final[int] = 1


class BehaviorAtomPolicyError(ValueError):
    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class AssuranceClass(StrEnum):
    STANDARD = "standard"
    HIGH = "high"


class AtomPolarity(StrEnum):
    MUST = "must"
    MUST_NOT = "must-not"


class BehaviorAtom(StrictModel):
    id: AtomId
    condition: NonBlank
    polarity: AtomPolarity
    observable_response: NonBlank
    boundary_context: NonBlank | None = None
    temporal_context: NonBlank | None = None
    coercion_context: NonBlank | None = None


class AtomPolicyEntry(Protocol):
    id: str
    impact_weight: int
    assurance_class: AssuranceClass | None
    behavior_atoms: tuple[BehaviorAtom, ...]


def atom_digest(atom: BehaviorAtom) -> Digest:
    payload = {
        "schema_version": ATOM_SCHEMA_VERSION,
        "id": atom.id,
        "condition": atom.condition,
        "polarity": atom.polarity.value,
        "observable_response": atom.observable_response,
        "boundary_context": atom.boundary_context,
        "temporal_context": atom.temporal_context,
        "coercion_context": atom.coercion_context,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"),
    ).hexdigest()


def validate_entries(
    entries: Iterable[AtomPolicyEntry],
    *,
    evidence_schema_version: Literal[0, 1, 2],
) -> None:
    match evidence_schema_version:
        case 0 | 1:
            return
        case 2:
            pass
        case unreachable:
            assert_never(unreachable)
    seen_ids: set[str] = set()
    for entry in entries:
        _validate_entry(entry)
        for atom in entry.behavior_atoms:
            if atom.id in seen_ids:
                raise BehaviorAtomPolicyError(f"duplicate behavior atom id {atom.id}")
            seen_ids.add(atom.id)


def _validate_entry(entry: AtomPolicyEntry) -> None:
    if entry.assurance_class is None:
        raise BehaviorAtomPolicyError(f"v2 entry {entry.id} requires an assurance class")
    match entry.assurance_class:
        case None:
            return
        case AssuranceClass.STANDARD:
            if entry.impact_weight >= 3:
                raise BehaviorAtomPolicyError(
                    f"v2 entry {entry.id} with impact_weight >= 3 requires assurance class high",
                )
        case AssuranceClass.HIGH:
            if not entry.behavior_atoms:
                raise BehaviorAtomPolicyError(f"high v2 entry {entry.id} requires at least one behavior atom")
        case unreachable:
            assert_never(unreachable)
