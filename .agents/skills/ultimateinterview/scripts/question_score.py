#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run question_score.py --format markdown questions.json
#      uv run question_score.py --format json < questions.json
# 3. Or make executable and run:
#      chmod +x question_score.py && ./question_score.py questions.json
# ──────────────────

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, ClassVar, Final

import typer
from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class _InvalidScoreError(ValueError):
    pass


def finite_score(value: JsonValue) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _InvalidScoreError("question score dimensions must be finite JSON numbers")
    if isinstance(value, float) and not math.isfinite(value):
        raise _InvalidScoreError("question score dimensions must be finite JSON numbers")
    return value


type ScoreDimension = Annotated[
    float,
    BeforeValidator(finite_score),
    Field(ge=0, le=5),
]


class QuestionCandidate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    id: str
    question: str
    impact: ScoreDimension
    branch_split: ScoreDimension
    uncertainty_reduction: ScoreDimension
    coverage: ScoreDimension
    user_cost: ScoreDimension
    redundancy: ScoreDimension
    target_ids: tuple[str, ...] = ()


class QuestionDocument(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    questions: tuple[QuestionCandidate, ...] = ()
    candidates: tuple[QuestionCandidate, ...] = ()

    def normalized_questions(self) -> tuple[QuestionCandidate, ...]:
        for group in (self.questions, self.candidates):
            if len(group) > 0:
                return group
        return ()


type QuestionPayload = tuple[QuestionCandidate, ...] | QuestionDocument
QUESTION_PAYLOAD_ADAPTER: Final[TypeAdapter[QuestionPayload]] = TypeAdapter(QuestionPayload)


@dataclass(frozen=True, slots=True)
class RankedQuestion:
    rank: int
    id: str
    question: str
    score: float
    impact: float
    branch_split: float
    uncertainty_reduction: float
    coverage: float
    user_cost: float
    redundancy: float
    target_ids: tuple[str, ...] = ()


def parse_questions(raw_json: str) -> tuple[QuestionCandidate, ...]:
    payload: QuestionPayload = QUESTION_PAYLOAD_ADAPTER.validate_json(raw_json)
    match payload:
        case QuestionDocument() as document:
            if len(document.questions) > 0 and len(document.candidates) > 0:
                message = (
                    "question document has both 'questions' and 'candidates' populated; "
                    "keep every candidate in exactly one section so nothing is silently dropped"
                )
                raise ValueError(message)
            questions = document.normalized_questions()
        case tuple() as questions:
            pass
    if len(questions) == 0:
        message = (
            "no question candidates found; an empty ranking cannot drive question "
            "selection - populate the document (check for a typo'd section key)"
        )
        raise ValueError(message)
    seen: set[str] = set()
    duplicates: list[str] = []
    for question in questions:
        if question.id in seen and question.id not in duplicates:
            duplicates.append(question.id)
        seen.add(question.id)
    if duplicates:
        message = f"duplicate question id(s) {duplicates}; every candidate needs a unique id"
        raise ValueError(message)
    return questions


def score_candidate(candidate: QuestionCandidate) -> float:
    numerator = (
        candidate.impact
        * candidate.branch_split
        * candidate.uncertainty_reduction
        * candidate.coverage
    )
    return numerator / (1 + candidate.user_cost + candidate.redundancy)


def rank_questions(
    candidates: tuple[QuestionCandidate, ...],
    *,
    top: int,
) -> tuple[RankedQuestion, ...]:
    scored = tuple(
        sorted(
            candidates,
            key=lambda candidate: (-score_candidate(candidate), candidate.id),
        )[:top],
    )
    return tuple(
        RankedQuestion(
            rank=index + 1,
            id=candidate.id,
            question=candidate.question,
            score=score_candidate(candidate),
            impact=candidate.impact,
            branch_split=candidate.branch_split,
            uncertainty_reduction=candidate.uncertainty_reduction,
            coverage=candidate.coverage,
            user_cost=candidate.user_cost,
            redundancy=candidate.redundancy,
            target_ids=candidate.target_ids,
        )
        for index, candidate in enumerate(scored)
    )


def rankings_as_json(rankings: tuple[RankedQuestion, ...]) -> str:
    payload = {
        "ranked_questions": [
            {
                "rank": item.rank,
                "id": item.id,
                "question": item.question,
                "score": round(item.score, 4),
                "impact": item.impact,
                "branch_split": item.branch_split,
                "uncertainty_reduction": item.uncertainty_reduction,
                "coverage": item.coverage,
                "user_cost": item.user_cost,
                "redundancy": item.redundancy,
                "target_ids": list(item.target_ids),
            }
            for item in rankings
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def rankings_as_markdown(rankings: tuple[RankedQuestion, ...]) -> str:
    lines = [
        "## Question Scores",
        "",
        "| Rank | ID | Score | Target IDs | Question |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {item.rank} | {item.id} | {item.score:.2f} | {', '.join(item.target_ids)} | {item.question} |"
        for item in rankings
    )
    return "\n".join(lines)


def read_input(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    if not path.exists():
        raise typer.BadParameter(f"input file not found: {path}")
    if not path.is_file():
        raise typer.BadParameter(f"input path is not a file: {path}")
    return path.read_text(encoding="utf-8")


def summarize_validation_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        errors = error.errors()
        for item in errors:
            if item["type"] == "extra_forbidden":
                key = item["loc"][-1]
                return (
                    f"invalid question JSON: unknown key {key!r}; "
                    "use 'questions' or 'candidates' (or a bare list)"
                )
        # Prefer the deepest error: union-branch mismatches have shallow locs
        # and mask the actionable one.
        deepest = max(errors, key=lambda item: len(item["loc"]))
        location = ".".join(str(part) for part in deepest["loc"]) or "<root>"
        suffix = "" if len(errors) == 1 else f" (+{len(errors) - 1} more)"
        return f"invalid question JSON at {location}: {deepest['msg']}{suffix}"
    return str(error)


def main(
    path: Annotated[
        Path | None,
        typer.Argument(help="Question candidate JSON path. Reads stdin when omitted."),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
    top: Annotated[int, typer.Option("--top", min=1, help="Number of questions.")] = 5,
) -> None:
    try:
        questions = parse_questions(read_input(path))
    except ValueError as error:
        raise typer.BadParameter(summarize_validation_error(error)) from error
    rankings = rank_questions(questions, top=top)
    renderers: dict[OutputFormat, Callable[[tuple[RankedQuestion, ...]], str]] = {
        OutputFormat.JSON: rankings_as_json,
        OutputFormat.MARKDOWN: rankings_as_markdown,
    }
    typer.echo(renderers[output_format](rankings))


if __name__ == "__main__":
    typer.run(main)
