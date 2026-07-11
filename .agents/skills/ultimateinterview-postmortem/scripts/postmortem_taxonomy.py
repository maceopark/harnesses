#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv or pip install needed):
#      uv run postmortem_taxonomy.py --help
# 3. Or make executable and run:
#      chmod +x postmortem_taxonomy.py && ./postmortem_taxonomy.py --help
# ─────────────────

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Annotated, Final, Literal, NewType, Self, assert_never

import typer
import pydantic as pd

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type ReportSchema = Literal[1, 2]

CanonicalStructure = NewType("CanonicalStructure", str)
NonBlankText = Annotated[str, pd.StringConstraints(strip_whitespace=True, min_length=1)]
ReportText = Annotated[str, typer.Option("--report-text", help="Marked report text")]

KNOWN_BASES: Final = frozenset({"item", "boundary", "interaction", "system"})
MODIFIER_ORDER: Final[tuple[str, ...]] = ("negative-space", "runtime-only")
KNOWN_MODIFIERS: Final[frozenset[str]] = frozenset(MODIFIER_ORDER)
NOVEL_BASE: Final[re.Pattern[str]] = re.compile(r"novel:[a-z0-9]+(?:-[a-z0-9]+)*")
REPORT_MARKER: Final = re.compile(r"^[ \t]*postmortem_schema[ \t]*:(.*)$", re.MULTILINE)
LEGACY_ID: Final[re.Pattern[str]] = re.compile(r"REQ-\d+")
STABLE_ESCAPE_ID: Final[re.Pattern[str]] = re.compile(r"ESC-\d{3}")


@dataclass(frozen=True, slots=True)
class TaxonomyError(ValueError):
    """A report value does not satisfy the taxonomy grammar."""

    detail: str

    def __str__(self) -> str:
        return self.detail


@unique
class RequirementBase(StrEnum):
    ITEM = "item"
    BOUNDARY = "boundary"
    INTERACTION = "interaction"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class NovelBase:
    slug: str


@unique
class RequirementModifier(StrEnum):
    NEGATIVE_SPACE = "negative-space"
    RUNTIME_ONLY = "runtime-only"


@dataclass(frozen=True, slots=True)
class RequirementStructure:
    base: RequirementBase | NovelBase
    modifiers: tuple[RequirementModifier, ...]

    @property
    def canonical(self) -> CanonicalStructure:
        match self.base:
            case RequirementBase() as base:
                base_text = base.value
            case NovelBase(slug=slug):
                base_text = f"novel:{slug}"
            case unreachable:
                assert_never(unreachable)
        suffix = "".join(f"+{modifier.value}" for modifier in self.modifiers)
        return CanonicalStructure(base_text + suffix)


def parse_requirement_structure(raw: str) -> RequirementStructure:
    """Parse one base plus unique modifiers and return their canonical order."""
    tokens = raw.split("+")
    if len(tokens) != len(set(tokens)):
        raise TaxonomyError(detail="requirement structure repeats a token")
    bases = [token for token in tokens if token in KNOWN_BASES or NOVEL_BASE.fullmatch(token)]
    unknown = [
        token
        for token in tokens
        if token not in KNOWN_MODIFIERS
        and token not in KNOWN_BASES
        and NOVEL_BASE.fullmatch(token) is None
    ]
    if unknown:
        raise TaxonomyError(detail=f"unknown requirement structure token: {unknown[0]}")
    if len(bases) != 1:
        raise TaxonomyError(detail="requirement structure must contain exactly one base")
    base_token = bases[0]
    if base_token.startswith("novel:"):
        base: RequirementBase | NovelBase = NovelBase(slug=base_token.removeprefix("novel:"))
    else:
        base = RequirementBase(base_token)
    modifiers = tuple(
        RequirementModifier(value) for value in MODIFIER_ORDER if value in tokens
    )
    return RequirementStructure(base=base, modifiers=modifiers)


def detect_report_schema(report_text: str) -> ReportSchema:
    """Treat an unmarked historical report as v1; accept only one v2 marker."""
    markers = [match.group(1).strip() for match in REPORT_MARKER.finditer(report_text)]
    if not markers:
        return 1
    if markers == ["2"]:
        return 2
    raise TaxonomyError(detail="report must contain exactly one postmortem_schema: 2 marker")


@unique
class FailureMode(StrEnum):
    TRIGGER_TOO_NARROW = "trigger-too-narrow"
    ENUMERATION_MISS = "enumeration-miss"
    SCORING_STARVED = "scoring-starved"
    ANSWER_UNPRESSURED = "answer-unpressured"
    SYNTHESIS_LOSS = "synthesis-loss"
    ONTOLOGY_MISS = "ontology-miss"


@unique
class OwningFrame(StrEnum):
    VIEWPOINT = "viewpoint"
    DOMAIN_STATE = "domain/state"
    GOAL_OBSTACLE = "goal/obstacle"
    MISUSE = "misuse"
    QUALITY = "quality"
    CONTROLLED_LANGUAGE = "controlled-language"
    CORE_PATH = "core-path"
    NONE = "none"


@unique
class Disposition(StrEnum):
    NEW = "new"
    STRENGTHENED = "strengthened"
    DEDUPED = "deduped"
    SYNTHESIS_NONROUTING = "not-routing/synthesis-loss"
    ONTOLOGY_NONROUTING = "not-routing/ontology-miss"


def _canonicalize_structure(value: JsonValue) -> CanonicalStructure:
    match value:
        case str() as raw:
            return parse_requirement_structure(raw).canonical
        case None | bool() | int() | float() | list() | dict():
            raise TaxonomyError(detail="requirement structure must be a string")
        case unreachable:
            assert_never(unreachable)


class EscapeFields(pd.BaseModel):
    """Strict external fields shared by legacy and v2 escape rows."""

    model_config = pd.ConfigDict(extra="forbid", frozen=True)

    escape_id: NonBlankText
    failure_mode: FailureMode
    requirement_structure: CanonicalStructure
    owning_frame: OwningFrame
    disposition: Disposition
    lesson_store: NonBlankText | None

    @pd.field_validator("requirement_structure", mode="before")
    @classmethod
    def canonicalize_structure(cls, value: JsonValue) -> CanonicalStructure:
        return _canonicalize_structure(value)

    @pd.model_validator(mode="after")
    def enforce_nonrouting(self) -> Self:
        ontology = self.failure_mode is FailureMode.ONTOLOGY_MISS
        if ontology != (self.owning_frame is OwningFrame.NONE):
            raise TaxonomyError(detail="ontology-miss and owning frame none require each other")
        if ontology != (self.disposition is Disposition.ONTOLOGY_NONROUTING):
            raise TaxonomyError(detail="ontology-miss requires not-routing/ontology-miss")
        if ontology and not self.requirement_structure.startswith("novel:"):
            raise TaxonomyError(detail="ontology-miss requires a novel structure base")
        if ontology and self.lesson_store is not None:
            raise TaxonomyError(detail="ontology-miss cannot target a lesson store")
        synthesis = self.failure_mode is FailureMode.SYNTHESIS_LOSS
        if synthesis != (self.disposition is Disposition.SYNTHESIS_NONROUTING):
            raise TaxonomyError(detail="synthesis-loss requires not-routing/synthesis-loss")
        return self


class EscapeClassification(EscapeFields):
    """A canonical escape row bound to its report schema."""

    report_schema: ReportSchema

    @pd.model_validator(mode="after")
    def enforce_schema_compatibility(self) -> Self:
        match self.report_schema:
            case 1:
                valid_id = LEGACY_ID.fullmatch(self.escape_id) is not None
                taxonomy_supported = self.failure_mode is not FailureMode.ONTOLOGY_MISS
            case 2:
                valid_id = STABLE_ESCAPE_ID.fullmatch(self.escape_id) is not None
                taxonomy_supported = True
            case unreachable:
                assert_never(unreachable)
        if not valid_id:
            raise TaxonomyError(detail="escape ID is incompatible with report schema")
        if not taxonomy_supported:
            raise TaxonomyError(detail="ontology-miss requires postmortem schema v2")
        return self

    @classmethod
    def from_report(cls, report_text: str, fields: EscapeFields) -> Self:
        """Bind already parsed fields to the marker detected in report text."""
        return cls(
            escape_id=fields.escape_id,
            failure_mode=fields.failure_mode,
            requirement_structure=fields.requirement_structure,
            owning_frame=fields.owning_frame,
            disposition=fields.disposition,
            lesson_store=fields.lesson_store,
            report_schema=detect_report_schema(report_text),
        )

    def canonical_json(self) -> str:
        """Return a byte-stable JSON representation for evidence and sidecars."""
        return self.model_dump_json()


def main(
    payload: Annotated[str, typer.Argument(help="EscapeFields JSON object")],
    report_text: ReportText = "",
) -> None:
    """Parse a row, bind its report version, and emit canonical JSON."""
    try:
        fields = EscapeFields.model_validate_json(payload)
        result = EscapeClassification.from_report(report_text, fields)
    except (TaxonomyError, pd.ValidationError) as error:
        typer.echo(f"postmortem_taxonomy: error: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(result.canonical_json())


if __name__ == "__main__":
    typer.run(main)
