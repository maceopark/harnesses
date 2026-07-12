"""Fact-free deterministic routing for the public fake simulator."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .corpus import SimulatorLexicon, SimulatorRule


class SimulatorInputError(ValueError):
    """Raised when a simulator interaction cannot be safely normalized."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def normalize_tokens(text: str) -> tuple[str, ...]:
    """Use UTF-8 validation, NFC, casefold, whitespace and punctuation splitting."""

    if not isinstance(text, str):
        raise SimulatorInputError("question must be text")
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise SimulatorInputError("question must be UTF-8 encodable") from error
    parts: list[str] = []
    current: list[str] = []
    for character in normalize("NFC", text).casefold():
        if character.isspace() or category(character).startswith("P"):
            if current:
                parts.append("".join(current))
                current.clear()
        else:
            current.append(character)
    if current:
        parts.append("".join(current))
    return tuple(parts)


def token_multiset(text: str) -> Counter[str]:
    """Return the punctuation-insensitive token multiset used for all matching."""

    return Counter(normalize_tokens(text))


class SimulatorInteraction(_StrictModel):
    question: str = Field(min_length=1)
    unmatched_count: int = Field(default=0, ge=0, le=2)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        normalize_tokens(value)
        return value


class RouteEnvelope(_StrictModel):
    schema: Literal["SimulatorRoute.v1"] = "SimulatorRoute.v1"
    status: Literal["matched", "ambiguous", "fallback", "termination-required", "rejected"]
    tier: Literal["choice", "intent", "lexical"] | None = None
    rule_id: str | None = None
    candidate_rule_ids: tuple[str, ...] = ()
    specificity: int = Field(default=0, ge=0)
    unmatched_count: int = Field(ge=0, le=3)
    fact_free: Literal[True] = True
    message: str


def _matches(rule: SimulatorRule, question_tokens: Counter[str]) -> bool:
    return not (rule.token_multiset - question_tokens)


def _envelope_for_unmatched(count: int) -> RouteEnvelope:
    if count == 1:
        return RouteEnvelope(
            status="fallback",
            unmatched_count=count,
            message="No public simulator rule matched. State the intended command boundary without supplying facts.",
        )
    if count == 2:
        return RouteEnvelope(
            status="termination-required",
            unmatched_count=count,
            message="A second unmatched question requires termination or an external, recorded decision; no fact is supplied.",
        )
    return RouteEnvelope(
        status="rejected",
        unmatched_count=count,
        message="Further unmatched questions are rejected after the required termination boundary.",
    )


def route_questions(
    lexicon: SimulatorLexicon,
    interaction: SimulatorInteraction | Mapping[str, Any],
) -> RouteEnvelope:
    """Route one question with strict precedence and no corpus facts in the reply.

    A matching tier is selected in ``choice > intent > lexical`` order.  Within
    that tier, the sole highest multiset specificity wins; an equal top score is
    an explicitly fact-free ambiguity rather than an arbitrary rule selection.
    """

    try:
        request = (
            interaction
            if isinstance(interaction, SimulatorInteraction)
            else SimulatorInteraction.model_validate(interaction)
        )
    except Exception as error:
        raise SimulatorInputError("interaction must be a valid simulator interaction") from error
    question_tokens = token_multiset(request.question)
    for tier in ("choice", "intent", "lexical"):
        matched = [rule for rule in lexicon.rules if rule.tier == tier and _matches(rule, question_tokens)]
        if not matched:
            continue
        highest = max(rule.specificity for rule in matched)
        finalists = sorted(rule.rule_id for rule in matched if rule.specificity == highest)
        if len(finalists) != 1:
            return RouteEnvelope(
                status="ambiguous",
                tier=tier,
                candidate_rule_ids=tuple(finalists),
                specificity=highest,
                unmatched_count=request.unmatched_count,
                message="Multiple equally specific public rules matched; clarify the boundary without supplying facts.",
            )
        return RouteEnvelope(
            status="matched",
            tier=tier,
            rule_id=finalists[0],
            candidate_rule_ids=tuple(finalists),
            specificity=highest,
            unmatched_count=request.unmatched_count,
            message="A public simulator rule matched. The fake simulator supplies no domain fact or private-oracle result.",
        )
    return _envelope_for_unmatched(request.unmatched_count + 1)


__all__ = [
    "RouteEnvelope",
    "SimulatorInputError",
    "SimulatorInteraction",
    "normalize_tokens",
    "route_questions",
    "token_multiset",
]
