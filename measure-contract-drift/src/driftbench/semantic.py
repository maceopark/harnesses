"""Canonical semantic atoms and strict assertion comparison.

Every contract, observation, and score input represents behavior with the same
five fields: guard, effect, polarity, boundary, and temporal. Primary credit is
awarded only when those complete atom sets are exactly equivalent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self
from unicodedata import is_normalized

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AtomPolarity = Literal["must", "must-not"]
ComparisonRelation = Literal[
    "exact",
    "broader",
    "narrower",
    "overlap",
    "contradiction",
    "disjoint",
]
ObservationResult = Literal["observed", "unobserved", "invalid"]


def _canonical_text(value: str, field_name: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be nonblank and trimmed")
    if not is_normalized("NFC", value):
        raise ValueError(f"{field_name} must be NFC-normalized")
    return value


class Atom(BaseModel):
    """One complete, polarity-qualified behavioral requirement.

    ``boundary`` and ``temporal`` are nullable rather than omitted so absence is
    itself part of the identity. This prevents a scorer from silently dropping
    either semantic dimension.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    guard: str = Field(min_length=1)
    effect: str = Field(min_length=1)
    polarity: AtomPolarity
    boundary: str | None = None
    temporal: str | None = None

    @field_validator("guard", "effect")
    @classmethod
    def _require_nonblank_nfc(cls, value: str, info: object) -> str:
        return _canonical_text(value, getattr(info, "field_name", "atom field"))

    @field_validator("boundary", "temporal")
    @classmethod
    def _require_optional_nonblank_nfc(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _canonical_text(value, getattr(info, "field_name", "atom field"))

    @property
    def key(self) -> tuple[str, str, AtomPolarity, str | None, str | None]:
        """Stable complete identity used for exact assertion comparison."""
        return (self.guard, self.effect, self.polarity, self.boundary, self.temporal)

    @property
    def unsigned_key(self) -> tuple[str, str, str | None, str | None]:
        """Complete identity excluding only polarity, used for contradiction."""
        return (self.guard, self.effect, self.boundary, self.temporal)


SemanticAtom = Atom


class Assertion(BaseModel):
    """A nonempty conjunction of coherent, unique canonical atoms."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    atoms: tuple[Atom, ...] = Field(min_length=1)
    @field_validator("atoms", mode="before")
    @classmethod
    def _accept_json_atom_array(cls, value: Any) -> tuple[Any, ...]:
        if type(value) is list:
            return tuple(value)
        if type(value) is tuple:
            return value
        raise TypeError("assertion atoms must be a JSON array or tuple")

    @model_validator(mode="after")
    def _require_unique_atoms(self) -> Self:
        if len({atom.key for atom in self.atoms}) != len(self.atoms):
            raise ValueError("assertion atoms must be unique")
        if len({atom.unsigned_key for atom in self.atoms}) != len(self.atoms):
            raise ValueError("assertion cannot contain both polarities of one atom")
        return self

class ExecutableObservation(BaseModel):
    """The outcome of an independent executable observation.

    ``observed`` is the sole result that may carry a behavioral assertion.
    ``unobserved`` records that no executable observation was produced, while
    ``invalid`` records evidence that cannot be trusted. Neither can receive
    primary credit, and neither may smuggle an assertion into a score.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    result: ObservationResult
    assertion: Assertion | None = None

    @model_validator(mode="after")
    def _require_assertion_only_for_observed_result(self) -> Self:
        if (self.result == "observed") != (self.assertion is not None):
            raise ValueError("only observed results require a semantic assertion")
        return self


class PrivateDevelopmentAnnotation(BaseModel):
    """Private development oracle material expressed as a typed assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    case_id: str = Field(min_length=1)
    assertion: Assertion

    @field_validator("case_id")
    @classmethod
    def _require_canonical_case_id(cls, value: str) -> str:
        return _canonical_text(value, "case_id")

def private_development_assertion(
    value: PrivateDevelopmentAnnotation | Mapping[str, Any],
) -> Assertion:
    """Extract a private development assertion without accepting opaque IDs.

    Legacy annotation objects may carry their atoms at top level. They are
    accepted only when every entry is a complete ``Atom``; legacy ``atom_id``
    records therefore fail closed instead of becoming scoreable identifiers.
    """

    if isinstance(value, PrivateDevelopmentAnnotation):
        return value.assertion
    if not isinstance(value, Mapping):
        raise TypeError("private development annotation must be a JSON object")
    if "assertion" in value:
        return PrivateDevelopmentAnnotation.model_validate(value, strict=True).assertion
    return PrivateDevelopmentAnnotation.model_validate(
        {"case_id": value.get("case_id"), "assertion": {"atoms": value.get("atoms")}},
        strict=True,
    ).assertion


class AssertionComparison(BaseModel):
    """Classification and primary-credit result for an assertion comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relation: ComparisonRelation
    primary_credit: int

    @field_validator("primary_credit", mode="before")
    @classmethod
    def _reject_boolean_credit(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("primary_credit must be an integer, not a boolean")
        return value

    @field_validator("primary_credit")
    @classmethod
    def _require_binary_credit(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("primary_credit must be 0 or 1")
        return value

    @model_validator(mode="after")
    def _credit_matches_relation(self) -> Self:
        if self.primary_credit != (1 if self.relation == "exact" else 0):
            raise ValueError("only exact equivalence receives primary credit")
        return self

    @property
    def exact_equivalent(self) -> bool:
        """Whether the compared assertion atom sets are exactly equivalent."""
        return self.relation == "exact"


def _assertion(value: Assertion | Mapping[str, Any]) -> Assertion:
    if isinstance(value, Assertion):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("assertion must be an Assertion or JSON object")
    return Assertion.model_validate(value, strict=True)


def compare_assertions(
    expected: Assertion | Mapping[str, Any],
    actual: Assertion | Mapping[str, Any],
) -> AssertionComparison:
    """Compare complete behavioral atom sets without partial primary credit.

    Atom order is immaterial. An ``actual`` set missing expected complete atoms
    is ``broader``; one adding complete atoms is ``narrower``. A polarity flip
    is a contradiction only when guard, effect, boundary, and temporal all
    match exactly.
    """
    expected_assertion = _assertion(expected)
    actual_assertion = _assertion(actual)
    expected_keys = {atom.key for atom in expected_assertion.atoms}
    actual_keys = {atom.key for atom in actual_assertion.atoms}

    if expected_keys == actual_keys:
        relation: ComparisonRelation = "exact"
    else:
        expected_unsigned = {atom.unsigned_key: atom.polarity for atom in expected_assertion.atoms}
        actual_unsigned = {atom.unsigned_key: atom.polarity for atom in actual_assertion.atoms}
        has_contradiction = any(
            actual_unsigned.get(key) != polarity
            for key, polarity in expected_unsigned.items()
            if key in actual_unsigned
        )
        if has_contradiction:
            relation = "contradiction"
        elif actual_keys < expected_keys:
            relation = "broader"
        elif expected_keys < actual_keys:
            relation = "narrower"
        elif expected_keys & actual_keys:
            relation = "overlap"
        else:
            relation = "disjoint"

    return AssertionComparison(
        relation=relation,
        primary_credit=1 if relation == "exact" else 0,
    )


__all__ = [
    "Assertion",
    "AssertionComparison",
    "Atom",
    "AtomPolarity",
    "ComparisonRelation",
    "SemanticAtom",
    "ExecutableObservation",
    "ObservationResult",
    "PrivateDevelopmentAnnotation",
    "compare_assertions",
    "private_development_assertion",
]
