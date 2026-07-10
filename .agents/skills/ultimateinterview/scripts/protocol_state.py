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
#      uv run protocol_state.py --format markdown protocol.json
#      uv run protocol_state.py --format json < protocol.json
# 3. Or make executable and run:
#      chmod +x protocol_state.py && ./protocol_state.py protocol.json
# ──────────────────

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, ClassVar, Final

import typer
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


LENS_NAMES: Final[frozenset[str]] = frozenset(
    {
        "viewpoint",
        "domain/state",
        "goal/obstacle",
        "misuse",
        "quality",
        "controlled-language",
    },
)
SWEEP_CADENCE: Final[int] = 4
STAGNATION_ROUNDS: Final[int] = 2
RESIDUAL_LAG_THRESHOLD: Final[int] = 2


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class Depth(StrEnum):
    MINIMAL = "minimal"
    FOCUSED = "focused"
    FULL = "full"


DEPTH_BUDGET_CAPS: Final[dict[Depth, int]] = {
    Depth.MINIMAL: 3,
    Depth.FOCUSED: 12,
    Depth.FULL: 20,
}


class LensState(StrEnum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    DONE = "done"
    SKIPPED = "skipped"


class LensArtifact(StrEnum):
    VIEWPOINT_MATRIX = "ViewpointMatrix"
    STATE_MODEL = "StateModel"
    GOAL_OBSTACLE_MAP = "GoalObstacleMap"
    MISUSE_CASE_SET = "MisuseCaseSet"
    QUALITY_SCENARIO_SET = "QualityScenarioSet"
    CONTROLLED_ACCEPTANCE_CRITERIA = "ControlledAcceptanceCriteria"


EXPECTED_LENS_ARTIFACT: Final[dict[str, LensArtifact]] = {
    "viewpoint": LensArtifact.VIEWPOINT_MATRIX,
    "domain/state": LensArtifact.STATE_MODEL,
    "goal/obstacle": LensArtifact.GOAL_OBSTACLE_MAP,
    "misuse": LensArtifact.MISUSE_CASE_SET,
    "quality": LensArtifact.QUALITY_SCENARIO_SET,
    "controlled-language": LensArtifact.CONTROLLED_ACCEPTANCE_CRITERIA,
}


class LensRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    state: LensState
    reason: str = ""
    artifact: LensArtifact | None = None

    @model_validator(mode="after")
    def skipped_needs_reason(self) -> LensRecord:
        if self.state == LensState.SKIPPED and not self.reason.strip():
            message = "a skipped lens must record a skip reason"
            raise ValueError(message)
        if self.state != LensState.DONE and self.artifact is not None:
            raise ValueError("artifact is only valid for a done lens")
        return self


class ProtocolState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    depth: Depth
    question_budget: int = Field(gt=0)
    interactions_used: int = Field(ge=0)
    answers_since_sweep: int = Field(ge=0)
    sweeps_run: int = Field(ge=0)
    dry_sweeps_in_row: int = Field(default=0, ge=0)
    contrarian_probes_run: int = Field(ge=0)
    falsification_checkpoints_run: int = Field(ge=0)
    checkpoint_since_last_material_change: bool = False
    framing_challenged: bool = False
    brain_dump_done: bool = False
    brain_dump_waiver: str = ""
    build_contract_tested: bool = False
    build_contract_digest: str = ""
    build_contract_reviewer: str = ""
    implementer_scout_run: bool = False
    pressure_followups_by_parent: dict[str, int] = Field(default_factory=dict)
    lenses: dict[str, LensRecord]
    residual_history: tuple[int, ...] = ()
    gap_count_history: tuple[int, ...] = ()
    stagnation_escalated_at: int = Field(default=0, ge=0)
    budget_extension_reason: str = ""
    due_now_corrections: int = Field(default=0, ge=0)

    @field_validator("lenses")
    @classmethod
    def exactly_the_known_lenses(cls, value: dict[str, LensRecord]) -> dict[str, LensRecord]:
        recorded = frozenset(value)
        unknown = recorded - LENS_NAMES
        missing = LENS_NAMES - recorded
        if unknown:
            allowed = ", ".join(sorted(LENS_NAMES))
            message = f"unknown lens name(s) {sorted(unknown)}; use exactly: {allowed}"
            raise ValueError(message)
        if missing:
            message = (
                f"missing lens decision(s) {sorted(missing)}; "
                "record every lens as pending, triggered, done, or skipped-with-reason"
            )
            raise ValueError(message)
        return value

    @field_validator("residual_history", "gap_count_history")
    @classmethod
    def history_values_are_non_negative(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item < 0 for item in value):
            message = "history values must be >= 0"
            raise ValueError(message)
        return value

    @field_validator("pressure_followups_by_parent")
    @classmethod
    def pressure_counts_are_bounded(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not parent.strip() or count not in (1, 2) for parent, count in value.items()):
            raise ValueError("pressure follow-up counts require nonblank parents and values 1 or 2")
        return value

    @model_validator(mode="after")
    def escalation_marker_within_history(self) -> ProtocolState:
        if self.stagnation_escalated_at > len(self.residual_history):
            message = (
                f"stagnation_escalated_at ({self.stagnation_escalated_at}) exceeds "
                f"len(residual_history) ({len(self.residual_history)}); "
                "it must be set to the history length at escalation time"
            )
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def dry_streak_within_sweep_count(self) -> ProtocolState:
        if self.dry_sweeps_in_row > self.sweeps_run:
            raise ValueError("dry_sweeps_in_row cannot exceed sweeps_run")
        return self

    @model_validator(mode="after")
    def budget_within_depth_cap(self) -> ProtocolState:
        cap = DEPTH_BUDGET_CAPS[self.depth]
        if self.question_budget > cap and not self.budget_extension_reason.strip():
            message = (
                f"question_budget {self.question_budget} exceeds the {self.depth.value} "
                f"cap of {cap}; record the user's explicit extension in "
                "budget_extension_reason or lower the budget"
            )
            raise ValueError(message)
        return self


@dataclass(frozen=True, slots=True)
class ProtocolSummary:
    depth: Depth
    interactions_used: int
    question_budget: int
    interview_obligations: tuple[str, ...]
    handoff_blockers: tuple[str, ...]
    protocol_ready: bool


def parse_state(raw_json: str) -> ProtocolState:
    return ProtocolState.model_validate_json(raw_json)


def is_stagnant(
    residual_history: tuple[int, ...],
    gap_count_history: tuple[int, ...] = (),
    *,
    escalated_at: int = 0,
) -> bool:
    # Rounds already covered by a past escalation must not re-trigger it;
    # only flat stretches observed after the last escalation count.
    unhandled = residual_history[escalated_at:]
    if len(unhandled) < STAGNATION_ROUNDS + 1:
        return False
    window = unhandled[-(STAGNATION_ROUNDS + 1) :]
    residual_flat = all(
        later >= earlier for earlier, later in zip(window, window[1:], strict=False)
    )
    if not residual_flat:
        return False
    # A rising residual caused by enumeration finding new gaps is productive
    # divergence, not stagnation: any gap-count increase in the window vetoes.
    window_start = len(residual_history) - len(window)
    gap_window = gap_count_history[window_start : len(residual_history)]
    return not any(
        later > earlier for earlier, later in zip(gap_window, gap_window[1:], strict=False)
    )


def build_interview_obligations(state: ProtocolState) -> tuple[str, ...]:
    obligations: list[str] = []
    if state.interactions_used >= state.question_budget:
        obligations.append(
            "question budget exhausted: stop ordinary questioning; "
            "ask the user to defer remaining gaps or explicitly extend the budget",
        )
    if state.answers_since_sweep >= SWEEP_CADENCE:
        obligations.append(
            f"breadth sweep overdue: {state.answers_since_sweep} answers since the last sweep "
            f"(cadence is every {SWEEP_CADENCE})",
        )
    if is_stagnant(
        state.residual_history,
        state.gap_count_history,
        escalated_at=state.stagnation_escalated_at,
    ):
        obligations.append(
            f"stagnation: residual has not dropped across {STAGNATION_ROUNDS} consecutive rounds "
            "with no new gaps found; run a contrarian probe or falsification checkpoint "
            "instead of another scored question",
        )
    lag = state.interactions_used - len(state.residual_history)
    if lag >= RESIDUAL_LAG_THRESHOLD:
        obligations.append(
            f"residual_history lags interactions_used by {lag}: append the residual "
            "after every human-decision round or stagnation detection degrades",
        )
    return tuple(obligations)


def build_handoff_blockers(state: ProtocolState) -> tuple[str, ...]:
    blockers: list[str] = []
    if not state.framing_challenged:
        blockers.append("framing challenge has not run")
    if not state.brain_dump_done and not state.brain_dump_waiver.strip():
        blockers.append("brain-dump intake neither done nor explicitly waived with a reason")
    if state.sweeps_run < 1:
        blockers.append("no breadth sweep has run")
    if state.dry_sweeps_in_row < 2:
        blockers.append(
            "divergence is not saturated: two consecutive dry breadth sweeps are required",
        )
    if state.contrarian_probes_run < 1:
        blockers.append("no contrarian probe has run")
    if state.falsification_checkpoints_run < 1:
        blockers.append("no falsification checkpoint has run")
    elif not state.checkpoint_since_last_material_change:
        blockers.append("no falsification checkpoint since the last material ledger change")
    pending = tuple(
        sorted(name for name, lens in state.lenses.items() if lens.state == LensState.PENDING),
    )
    if pending:
        blockers.append(
            f"undecided lens(es): {', '.join(pending)}; "
            "decide triggered or skipped-with-reason before handoff",
        )
    triggered = tuple(
        sorted(name for name, lens in state.lenses.items() if lens.state == LensState.TRIGGERED),
    )
    if triggered:
        blockers.append(
            f"triggered lens(es) not completed: {', '.join(triggered)}",
        )
    incomplete_artifacts = tuple(
        sorted(
            f"{name} (expected {EXPECTED_LENS_ARTIFACT[name].value})"
            for name, lens in state.lenses.items()
            if lens.state == LensState.DONE
            and lens.artifact != EXPECTED_LENS_ARTIFACT[name]
        ),
    )
    if incomplete_artifacts:
        blockers.append(
            f"done lens artifact missing or mismatched: {', '.join(incomplete_artifacts)}",
        )
    if not state.build_contract_tested:
        blockers.append(
            "build contract has not passed a fresh-implementer test (agent or self-audited)",
        )
    elif not state.build_contract_digest.strip() or not state.build_contract_reviewer.strip():
        blockers.append(
            "build contract test is missing its Part-1 digest or reviewer identity",
        )
    return tuple(blockers)


def summarize_protocol(state: ProtocolState) -> ProtocolSummary:
    handoff_blockers = build_handoff_blockers(state)
    return ProtocolSummary(
        depth=state.depth,
        interactions_used=state.interactions_used,
        question_budget=state.question_budget,
        interview_obligations=build_interview_obligations(state),
        handoff_blockers=handoff_blockers,
        protocol_ready=len(handoff_blockers) == 0,
    )


def summary_as_json(summary: ProtocolSummary) -> str:
    payload = {
        "depth": summary.depth.value,
        "interactions_used": summary.interactions_used,
        "question_budget": summary.question_budget,
        "interview_obligations": list(summary.interview_obligations),
        "handoff_blockers": list(summary.handoff_blockers),
        "protocol_ready": summary.protocol_ready,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def summary_as_markdown(summary: ProtocolSummary) -> str:
    lines = [
        "## Protocol Dashboard",
        "",
        "- Protocol ready: yes (all pre-handoff protocol obligations met)"
        if summary.protocol_ready
        else "- Protocol ready: no",
        f"- Depth: {summary.depth.value}",
        f"- Question budget: {summary.interactions_used} / {summary.question_budget} interactions used",
    ]
    if summary.interview_obligations:
        lines.extend(["", "### Due Now (before the next scored question)"])
        lines.extend(f"- {obligation}" for obligation in summary.interview_obligations)
    if summary.handoff_blockers:
        lines.extend(["", "### Handoff Blockers"])
        lines.extend(f"- {blocker}" for blocker in summary.handoff_blockers)
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
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "<root>"
        suffix = "" if error.error_count() == 1 else f" (+{error.error_count() - 1} more)"
        return f"invalid protocol JSON at {location}: {first['msg']}{suffix}"
    return str(error)


def main(
    path: Annotated[Path | None, typer.Argument(help="Protocol JSON path. Reads stdin when omitted.")] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
) -> None:
    try:
        state = parse_state(read_input(path))
    except ValueError as error:
        raise typer.BadParameter(summarize_validation_error(error)) from error
    summary = summarize_protocol(state)
    renderers: dict[OutputFormat, Callable[[ProtocolSummary], str]] = {
        OutputFormat.JSON: summary_as_json,
        OutputFormat.MARKDOWN: summary_as_markdown,
    }
    typer.echo(renderers[output_format](summary))


if __name__ == "__main__":
    typer.run(main)
