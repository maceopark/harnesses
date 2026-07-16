"""Strict primitives for the generation-zero interview discovery experiment."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class InterviewOptionV2(ClosedModel):
    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    normative_statement: str = Field(min_length=1)
    compatible: bool


class InterviewDecisionV2(ClosedModel):
    decision_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: tuple[InterviewOptionV2, ...] = Field(min_length=2, max_length=4)
    recommended_option_id: str = Field(min_length=1)
    recommendation_rationale: str = Field(min_length=1)
    impact_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_options(self) -> "InterviewDecisionV2":
        ids = [option.option_id for option in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError("interview option IDs must be unique")
        compatible = [option for option in self.options if option.compatible]
        if len(compatible) < 2:
            raise ValueError("each decision requires at least two compatible options")
        recommended = [
            option for option in compatible
            if option.option_id == self.recommended_option_id
        ]
        if len(recommended) != 1:
            raise ValueError("recommendation must identify exactly one compatible option")
        return self


class StructuredInterviewTurnV2(ClosedModel):
    schema_: Literal["StructuredInterviewTurn.v2"] = Field(
        default="StructuredInterviewTurn.v2", alias="schema", serialization_alias="schema"
    )
    action: Literal["ask", "complete"]
    decisions: tuple[InterviewDecisionV2, ...] = ()
    contract_draft: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "StructuredInterviewTurnV2":
        ids = [decision.decision_id for decision in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("interview decision IDs must be unique")
        if self.action == "ask":
            if not self.decisions or self.contract_draft is not None:
                raise ValueError("ask requires decisions and forbids a contract draft")
        elif self.decisions or not self.contract_draft:
            raise ValueError("complete requires a non-empty contract draft and forbids decisions")
        return self


def validate_turn_sequence(
    turns: Sequence[StructuredInterviewTurnV2 | Mapping[str, Any]], *, maximum_decisions: int = 6
) -> tuple[StructuredInterviewTurnV2, ...]:
    """Validate a complete multi-turn interview and its cell-wide decision budget."""

    parsed = tuple(
        turn if isinstance(turn, StructuredInterviewTurnV2)
        else StructuredInterviewTurnV2.model_validate(turn)
        for turn in turns
    )
    if not parsed or parsed[-1].action != "complete":
        raise ValueError("interview must end with a completion turn")
    if any(turn.action == "complete" for turn in parsed[:-1]):
        raise ValueError("completion must be the final turn")
    decisions = [decision for turn in parsed for decision in turn.decisions]
    if len(decisions) > maximum_decisions:
        raise ValueError("material decision limit exceeded")
    ids = [decision.decision_id for decision in decisions]
    if len(ids) != len(set(ids)):
        raise ValueError("decision IDs must be stable and unique across the cell")
    return parsed


class SeededSelection(ClosedModel):
    decision_id: str
    option_id: str
    normative_statement: str
    authority_id: str


def select_option(
    manifest_seed: str, candidate_id: str, case_id: str, repetition: int,
    decision: InterviewDecisionV2,
) -> SeededSelection:
    """Select a compatible option reproducibly across retries and resume."""

    if repetition < 1:
        raise ValueError("repetition must be positive")
    bound = "\x1f".join(
        (manifest_seed, candidate_id, case_id, str(repetition), decision.decision_id)
    ).encode("utf-8")
    digest = hashlib.sha256(bound).digest()
    compatible = tuple(option for option in decision.options if option.compatible)
    selected = compatible[int.from_bytes(digest, "big") % len(compatible)]
    authority_id = "OWNER-" + hashlib.sha256(b"authority\0" + bound).hexdigest()[:16]
    return SeededSelection(
        decision_id=decision.decision_id, option_id=selected.option_id,
        normative_statement=selected.normative_statement, authority_id=authority_id,
    )


class AuthorityEntry(ClosedModel):
    authority_id: str
    authority_type: Literal["owner-decision"] = "owner-decision"
    decision_id: str
    option_id: str
    normative_statement: str


def authority_register(selections: Iterable[SeededSelection]) -> tuple[AuthorityEntry, ...]:
    entries = tuple(
        AuthorityEntry(
            authority_id=row.authority_id, decision_id=row.decision_id,
            option_id=row.option_id, normative_statement=row.normative_statement,
        )
        for row in selections
    )
    if len({row.authority_id for row in entries}) != len(entries):
        raise ValueError("authority IDs conflict")
    if len({row.decision_id for row in entries}) != len(entries):
        raise ValueError("decision selections conflict")
    return entries


def verify_authority_projection(
    register: Sequence[AuthorityEntry], requirements: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed unless every dynamic authority is projected exactly once, verbatim."""

    for entry in register:
        matches = [row for row in requirements if row.get("authority_id") == entry.authority_id]
        if len(matches) != 1 or matches[0].get("statement") != entry.normative_statement:
            raise ValueError(f"dynamic authority projection is invalid: {entry.authority_id}")


class CellSpec(ClosedModel):
    candidate_id: str
    partition: Literal["train", "validation"]
    case_id: str
    repetition: int = Field(ge=1)

    @property
    def cell_id(self) -> str:
        return f"{self.candidate_id}--{self.partition}--{self.case_id}--r{self.repetition}"


def schedule_cells(
    candidates: Sequence[str], partitions: Sequence[tuple[str, Sequence[str]]], repetitions: int,
) -> tuple[CellSpec, ...]:
    """Order cells by partition, repetition, case, then candidate round-robin."""

    if repetitions < 1 or len(set(candidates)) != len(candidates) or not candidates:
        raise ValueError("candidate inventory and repetitions must be valid")
    return tuple(
        CellSpec(candidate_id=candidate, partition=partition, case_id=case, repetition=rep)
        for partition, cases in partitions
        for rep in range(1, repetitions + 1)
        for case in cases
        for candidate in candidates
    )


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CellReceipt(ClosedModel):
    schema_: Literal["DiscoveryCellReceipt.v1"] = Field(
        default="DiscoveryCellReceipt.v1", alias="schema", serialization_alias="schema"
    )
    cell_id: str
    input_digest: str = Field(pattern=r"[0-9a-f]{64}")
    status: Literal["completed", "invalid"]
    attempts: int = Field(ge=1, le=2)
    artifact_hashes: dict[str, str]

    @field_validator("artifact_hashes")
    @classmethod
    def validate_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("artifact hashes must not be empty")
        for path, digest in value.items():
            if not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("artifact hash paths must be safe relative paths")
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError("artifact hashes must be lowercase SHA-256 digests")
        return value


class CoordinatorState(ClosedModel):
    schema_: Literal["DiscoveryCoordinatorState.v1"] = Field(
        default="DiscoveryCoordinatorState.v1", alias="schema", serialization_alias="schema"
    )
    manifest_digest: str = Field(pattern=r"[0-9a-f]{64}")
    cells: dict[str, CellReceipt]

    def reusable(self, cell_id: str, input_digest: str) -> bool:
        receipt = self.cells.get(cell_id)
        return receipt is not None and receipt.input_digest == input_digest


def write_coordinator_state(path: Path, state: CoordinatorState) -> None:
    """Atomic coordinator-only persistence primitive; workers return receipts instead."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(state.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def merge_receipt(state: CoordinatorState, receipt: CellReceipt) -> CoordinatorState:
    cells = dict(state.cells)
    existing = cells.get(receipt.cell_id)
    if existing is not None and existing.input_digest != receipt.input_digest:
        raise ValueError("completed cell input binding changed")
    cells[receipt.cell_id] = receipt
    return state.model_copy(update={"cells": cells})


def fidelity(fulfilled: int, contract_requirements: int, escaped_requirements: int, *,
             invalid: bool = False, authority_expansion: bool = False,
             lineage_valid: bool = True) -> float:
    denominator = contract_requirements + escaped_requirements
    if min(fulfilled, contract_requirements, escaped_requirements) < 0 or denominator == 0:
        raise ValueError("requirement counts must be non-negative with a positive denominator")
    if fulfilled > denominator:
        raise ValueError("fulfilled count exceeds requirements")
    return 0.0 if invalid or authority_expansion or not lineage_valid else fulfilled / denominator


def wilson_interval(values: Sequence[float], z: float = 1.959963984540054) -> tuple[float, float]:
    if not values or any(value < 0 or value > 1 for value in values):
        raise ValueError("fidelity observations must be non-empty and in [0,1]")
    n = len(values)
    proportion = sum(values) / n
    denominator = 1 + z * z / n
    centre = proportion + z * z / (2 * n)
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denominator), min(1.0, (centre + margin) / denominator)


class DiscoveryCandidateSummary(ClosedModel):
    candidate_id: str
    fidelity_lcb: float = Field(ge=0, le=1)
    fidelity_ucb: float = Field(ge=0, le=1)
    median_material_decisions: float = Field(ge=0)
    skill_bytes: int = Field(ge=1)
    total_tokens: int = Field(ge=0)
    wall_clock_ms: int = Field(ge=0)


def summarize_candidate(candidate_id: str, fidelities: Sequence[float], decisions: Sequence[int],
                        *, skill_bytes: int, total_tokens: int = 0,
                        wall_clock_ms: int = 0) -> DiscoveryCandidateSummary:
    if len(fidelities) != len(decisions) or not fidelities:
        raise ValueError("candidate observations must be non-empty and aligned")
    lower, upper = wilson_interval(fidelities)
    return DiscoveryCandidateSummary(
        candidate_id=candidate_id, fidelity_lcb=lower, fidelity_ucb=upper,
        median_material_decisions=float(median(decisions)), skill_bytes=skill_bytes,
        total_tokens=total_tokens, wall_clock_ms=wall_clock_ms,
    )


def dominates(left: DiscoveryCandidateSummary, right: DiscoveryCandidateSummary) -> bool:
    no_worse = (
        left.fidelity_lcb >= right.fidelity_lcb
        and left.median_material_decisions <= right.median_material_decisions
        and left.skill_bytes <= right.skill_bytes
    )
    strict = (
        left.fidelity_lcb > right.fidelity_lcb
        or left.median_material_decisions < right.median_material_decisions
        or left.skill_bytes < right.skill_bytes
    )
    return no_worse and strict


def pareto_archive(
    candidates: Sequence[DiscoveryCandidateSummary],
) -> tuple[DiscoveryCandidateSummary, ...]:
    return tuple(sorted(
        (candidate for candidate in candidates if not any(
            dominates(other, candidate) for other in candidates if other != candidate
        )),
        key=lambda row: (-row.fidelity_lcb, row.median_material_decisions, row.skill_bytes,
                         row.total_tokens, row.wall_clock_ms, row.candidate_id),
    ))
