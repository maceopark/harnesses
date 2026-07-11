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
# 2. Apply one bookkeeping delta and get the combined dashboards back:
#      uv run scripts/session_update.py .ultimateinterview/<session>/ --delta '<json>'
#      uv run scripts/session_update.py .ultimateinterview/<session>/ --delta-file delta.json
#      echo '<json>' | uv run scripts/session_update.py .ultimateinterview/<session>/ --delta -
# ──────────────────

# Deterministic writer for the per-round bookkeeping pass: the model composes
# ONE compact delta; this script applies it to ledger.json + protocol.json,
# recomputes residual/gap-count for the history append (never model arithmetic),
# validates everything fail-closed, and emits the session_status output.
# Nothing is written unless the whole delta validates.
#
# Typed events: pass "event" and the script computes EVERY counter increment
# (budget costing lives here, not in model memory). Pressure gate: lowering a
# weight>=3 from-user entry below score 2 on a single evidence channel requires
# an explicit pressure token. checkpoint_confirm applies checkpoint crediting
# in bulk. "transcript" appends the correctly numbered transcript section.

from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Final, assert_never, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from scripts import (
    ambiguity_ledger,
    atomic_write,
    behavior_atoms as atom_contract,
    build_contract,
    claim_evidence,
    implementation_gate,
    open_world,
    probe_policy,
    protocol_state,
    question_score,
    session_contracts,
    session_status,
)

LEDGER_SECTIONS: Final[tuple[str, ...]] = ("requirements", "gaps", "entries", "ledger")
LENSES_KEY: Final[str] = "lenses"
PROTOCOL_KEYS: Final[frozenset[str]] = frozenset(
    protocol_state.ProtocolState.model_fields,
)
PRESSURE_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(survived|second-channel|exempt:.+)$",
)
type JsonObject = dict[str, object]
type LedgerEntries = list[JsonObject]


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class Event(StrEnum):
    """Typed interaction events. The script owns the costing table (SKILL.md
    budget invariant): which events cost an interaction, count toward the
    sweep cadence, or bump a protocol counter."""

    BRAIN_DUMP = "brain-dump"
    FRAMING = "framing"
    SCORED_QUESTION = "scored-question"
    BUNDLE = "bundle"
    BATCH = "batch"
    CHECKPOINT = "checkpoint"
    SWEEP_ASKED = "sweep-asked"
    SWEEP_FREE = "sweep-free"
    CONTRARIAN_ASKED = "contrarian-asked"
    CONTRARIAN_FREE = "contrarian-free"
    PRESSURE_FOLLOWUP = "pressure-followup"


class SweepResult(StrEnum):
    DRY = "dry"
    NEW_GAPS = "new-gaps"


# Events that cost 1 interaction (one round-trip to the user).
COSTED_EVENTS: Final[frozenset[Event]] = frozenset(
    {
        Event.BRAIN_DUMP,
        Event.FRAMING,
        Event.SCORED_QUESTION,
        Event.BUNDLE,
        Event.BATCH,
        Event.CHECKPOINT,
        Event.SWEEP_ASKED,
        Event.CONTRARIAN_ASKED,
    },
)
# Events counted by answers_since_sweep (costed events except sweeps themselves).
SWEEP_COUNTED_EVENTS: Final[frozenset[Event]] = COSTED_EVENTS - {Event.SWEEP_ASKED}
SWEEP_EVENTS: Final[frozenset[Event]] = frozenset({Event.SWEEP_ASKED, Event.SWEEP_FREE})
CONTRARIAN_EVENTS: Final[frozenset[Event]] = frozenset(
    {Event.CONTRARIAN_ASKED, Event.CONTRARIAN_FREE},
)

# Transcript heading markers for costed events; free events become sub-bullets.
HEADING_MARKERS: Final[dict[Event, str]] = {
    Event.BRAIN_DUMP: "brain-dump",
    Event.FRAMING: "framing",
    Event.SCORED_QUESTION: "scored-question",
    Event.BUNDLE: "bundle",
    Event.BATCH: "batch",
    Event.CHECKPOINT: "checkpoint",
    Event.SWEEP_ASKED: "sweep",
    Event.CONTRARIAN_ASKED: "contrarian-probe",
}
SUB_BULLET_MARKERS: Final[dict[Event, str]] = {
    Event.PRESSURE_FOLLOWUP: "pressure-followup",
    Event.SWEEP_FREE: "sweep: from-ledger",
    Event.CONTRARIAN_FREE: "contrarian: self-run",
}


def managed_protocol_keys(event: Event) -> frozenset[str]:
    """Protocol fields the event computes itself; a delta may not also set them."""
    managed: set[str] = set()
    if event in COSTED_EVENTS:
        managed.add("interactions_used")
    if event in SWEEP_COUNTED_EVENTS or event in SWEEP_EVENTS:
        managed.add("answers_since_sweep")
    if event in SWEEP_EVENTS:
        managed.update({"sweeps_run", "dry_sweeps_in_row"})
    if event in CONTRARIAN_EVENTS:
        managed.add("contrarian_probes_run")
    if event is Event.CHECKPOINT:
        managed.update({"falsification_checkpoints_run", "checkpoint_since_last_material_change"})
    if event is Event.BRAIN_DUMP:
        managed.add("brain_dump_done")
    if event is Event.FRAMING:
        managed.add("framing_challenged")
    if event is Event.PRESSURE_FOLLOWUP:
        managed.add("pressure_followups_by_parent")
    return frozenset(managed)


EVENT_MANAGED_KEYS: Final[frozenset[str]] = frozenset().union(
    *(managed_protocol_keys(event) for event in Event),
    {"recent_question_tracks"},
)
BUILD_CONTRACT_MANAGED_KEYS: Final[frozenset[str]] = frozenset(
    {"build_contract_tested", "build_contract_digest", "build_contract_reviewer"},
)
HISTORY_MANAGED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "residual_history",
        "gap_count_history",
        "stagnation_escalated_at",
        "recent_question_tracks",
    },
)


def integer_value(document: JsonObject, key: str) -> int:
    value = document.get(key, 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise typer.BadParameter(f"protocol field {key!r} must be an integer")
    return value


def apply_event(
    protocol_doc: JsonObject,
    event: Event,
    sweep_result: SweepResult | None = None,
) -> None:
    def bump(key: str, amount: int = 1) -> None:
        protocol_doc[key] = integer_value(protocol_doc, key) + amount

    if event in COSTED_EVENTS:
        bump("interactions_used")
    if event in SWEEP_COUNTED_EVENTS:
        bump("answers_since_sweep")
    if event in SWEEP_EVENTS:
        protocol_doc["answers_since_sweep"] = 0
        bump("sweeps_run")
        protocol_doc["dry_sweeps_in_row"] = (
            integer_value(protocol_doc, "dry_sweeps_in_row") + 1
            if sweep_result is SweepResult.DRY
            else 0
        )
    if event in CONTRARIAN_EVENTS:
        bump("contrarian_probes_run")
    if event is Event.CHECKPOINT:
        bump("falsification_checkpoints_run")
        protocol_doc["checkpoint_since_last_material_change"] = True
        protocol_doc["framing_challenged"] = True
    if event is Event.BRAIN_DUMP:
        protocol_doc["brain_dump_done"] = True
    if event is Event.FRAMING:
        protocol_doc["framing_challenged"] = True


class SetOp(BaseModel):
    """Partial update of one existing entry; only provided fields change."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    id: str
    requirement: str | None = None
    reason: str | None = None
    append_reason: str | None = None
    origin: str | None = None
    status: str | None = None
    deferred: StrictBool | dict[str, str] | None = None
    ambiguity_score: StrictInt | None = None
    impact_weight: StrictInt | None = None
    assurance_class: atom_contract.AssuranceClass | None = None
    behavior_atoms: tuple[atom_contract.BehaviorAtom, ...] | None = None
    evidence_channels: tuple[str, ...] | None = None
    evidence_records: tuple[claim_evidence.ClaimEvidence, ...] | None = None
    add_channels: tuple[str, ...] = ()
    add_evidence_records: tuple[claim_evidence.ClaimEvidence, ...] = ()
    pressure: str | None = None
    track: ambiguity_ledger.LedgerTrack | None = None

    @field_validator("pressure")
    @classmethod
    def pressure_token_format(cls, value: str | None) -> str | None:
        if value is not None and not PRESSURE_TOKEN_PATTERN.match(value):
            message = "pressure must be 'survived', 'second-channel', or 'exempt:<reason>'"
            raise ValueError(message)
        return value


class CheckpointConfirm(BaseModel):
    """Bulk crediting for a decisive checkpoint confirmation: bumps the
    checkpoint counters (cost 1) and adds from-user corroboration to covered
    entries that sit on a single evidence channel. A fatigue-flagged
    confirmation still counts as a run but credits nothing."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    ids: tuple[str, ...] = Field(min_length=1)
    fatigue: StrictBool = False

    @field_validator("ids")
    @classmethod
    def ids_are_nonblank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(entry_id.strip() for entry_id in value)
        if any(not entry_id for entry_id in normalized):
            raise ValueError("checkpoint ids must be nonblank")
        return normalized


class TranscriptNote(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    title: str
    lines: tuple[str, ...] = ()
    # Marks the note as an in-flight question: the rendered line carries
    # [awaiting-answer], which the next answer-bearing delta auto-resolves.
    awaiting: StrictBool = False


class BuildContractTest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    reviewer: str

    @field_validator("reviewer")
    @classmethod
    def reviewer_is_named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reviewer must be non-empty")
        return value.strip()


class Delta(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    set: tuple[SetOp, ...] = ()
    add: tuple[JsonObject, ...] = ()
    protocol: JsonObject = Field(default_factory=dict)
    append_history: StrictBool = False
    event: Event | None = None
    sweep_result: SweepResult | None = None
    checkpoint_confirm: CheckpointConfirm | None = None
    transcript: TranscriptNote | None = None
    build_contract_test: BuildContractTest | None = None
    open_world_sweep: open_world.OpenWorldSweep | None = None
    probe_decision: probe_policy.ProbeDecision | None = None
    probe_attempt: probe_policy.ProbeAttempt | None = None
    questions: tuple[question_score.QuestionCandidate, ...] | None = None
    pressure_parent: str | None = None
    asked_question_id: str | None = None

    @field_validator("questions")
    @classmethod
    def question_ids_are_unique(
        cls,
        value: tuple[question_score.QuestionCandidate, ...] | None,
    ) -> tuple[question_score.QuestionCandidate, ...] | None:
        if value is None:
            return value
        ids = [candidate.id for candidate in value]
        if len(ids) != len(set(ids)):
            raise ValueError("questions replacement contains duplicate ids")
        return value

    @field_validator("asked_question_id")
    @classmethod
    def normalize_asked_question_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("asked_question_id must be nonblank")
        return normalized

    @model_validator(mode="after")
    def sweep_result_matches_event(self) -> Delta:
        if self.event is Event.CHECKPOINT and self.checkpoint_confirm is None:
            raise ValueError("checkpoint events require checkpoint_confirm with covered ids")
        is_sweep = self.event in SWEEP_EVENTS
        if is_sweep and self.sweep_result is None:
            raise ValueError("sweep_result is required for sweep events")
        if not is_sweep and self.sweep_result is not None:
            raise ValueError("sweep_result is only valid for sweep events")
        sweep_entries = tuple(entry for entry in self.add if entry.get("origin") == "sweep")
        discovered_sweep_gaps = tuple(
            entry
            for entry in sweep_entries
            if entry.get("ambiguity_score", entry.get("ambiguity", 0)) in (1, 2, 3)
        )
        if self.sweep_result is SweepResult.NEW_GAPS and not discovered_sweep_gaps:
            raise ValueError("new-gaps requires an added ambiguous ledger gap with origin 'sweep'")
        if self.sweep_result is SweepResult.DRY and sweep_entries:
            raise ValueError("a dry sweep cannot add a ledger entry with origin 'sweep'")
        if self.event is Event.PRESSURE_FOLLOWUP:
            if self.pressure_parent is None or not self.pressure_parent.strip():
                raise ValueError("pressure-followup requires a nonblank pressure_parent")
        elif self.pressure_parent is not None:
            raise ValueError("pressure_parent is only valid for pressure-followup")
        if self.event is not Event.SCORED_QUESTION and self.asked_question_id is not None:
            raise ValueError("asked_question_id is only valid for scored-question")
        if self.build_contract_test is not None and (
            self.set
            or self.add
            or self.protocol
            or self.append_history
            or self.event is not None
            or self.sweep_result is not None
            or self.checkpoint_confirm is not None
            or self.transcript is not None
            or self.questions is not None
            or self.open_world_sweep is not None
            or self.probe_decision is not None
            or self.probe_attempt is not None
        ):
            raise ValueError("build_contract_test must be recorded in a dedicated delta")
        return self


def parse_delta(raw: str) -> Delta:
    try:
        delta = Delta.model_validate_json(raw)
    except ValidationError as error:
        raise typer.BadParameter(
            f"invalid delta: {ambiguity_ledger.summarize_validation_error(error)}",
        ) from error
    if delta.event is not None and delta.checkpoint_confirm is not None:
        raise typer.BadParameter(
            "pass either event or checkpoint_confirm, not both "
            "(checkpoint_confirm IS the checkpoint event)",
        )
    return delta


def load_json(path: Path, label: str) -> object:
    if not path.is_file():
        raise typer.BadParameter(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise typer.BadParameter(f"{path}: invalid JSON ({error})") from error


def ledger_section(raw: object) -> tuple[str | None, LedgerEntries]:
    """Return (container key or None for a bare list, entry dicts)."""
    if isinstance(raw, list) and all(isinstance(entry, dict) for entry in raw):
        return None, [dict(entry) for entry in raw]
    if isinstance(raw, dict):
        populated = [key for key in LEDGER_SECTIONS if raw.get(key)]
        if len(populated) == 1:
            section = raw[populated[0]]
            if isinstance(section, list) and all(isinstance(entry, dict) for entry in section):
                return populated[0], [dict(entry) for entry in section]
    raise typer.BadParameter(
        "ledger.json must be a list or an object with exactly one populated "
        f"section among {', '.join(LEDGER_SECTIONS)}",
    )


def normalized_channels(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return ()
    normalized: list[str] = []
    for channel in raw:
        cleaned = str(channel).strip().lower()
        normalized.append(ambiguity_ledger.CHANNEL_ALIASES.get(cleaned, cleaned))
    return tuple(dict.fromkeys(normalized))


def entry_field(entry: JsonObject, name: str, alias: str) -> object:
    return entry.get(name, entry.get(alias))


def material_projection(entry: JsonObject) -> tuple[object, ...]:
    return (
        entry.get("requirement"),
        entry_field(entry, "ambiguity_score", "ambiguity"),
        entry_field(entry, "impact_weight", "weight"),
        str(entry.get("status", "")).lower(),
        entry.get("deferred", False),
        session_contracts.material_signature(entry),
    )


def evidence_only_foldback(entry: JsonObject) -> bool:
    channels = frozenset(normalized_channels(entry_field(entry, "evidence_channels", "channels")))
    real_channels = channels - ambiguity_ledger.NON_EVIDENCE_CHANNELS
    score = entry_field(entry, "ambiguity_score", "ambiguity")
    status = str(entry.get("status", "")).lower()
    return (
        entry.get("origin") == "fold-back"
        and isinstance(score, int)
        and score <= 1
        and bool(real_channels)
        and status in {"accepted", "triangulated"}
    )


def has_material_ledger_change(before: LedgerEntries, after: LedgerEntries) -> bool:
    before_by_id = {entry.get("id"): entry for entry in before}
    after_by_id = {entry.get("id"): entry for entry in after}
    for entry_id in before_by_id.keys() | after_by_id.keys():
        old = before_by_id.get(entry_id)
        new = after_by_id.get(entry_id)
        if old is None and new is not None and evidence_only_foldback(new):
            continue
        if old is None or new is None or material_projection(old) != material_projection(new):
            return True
    return False


def append_to_reason(entry: JsonObject, note: str) -> None:
    existing = str(entry.get("reason", "")).strip()
    entry["reason"] = f"{existing}; {note}" if existing else note


def pressure_gate_violation(
    entry: JsonObject,
    *,
    old_score: object,
    is_new_entry: bool,
    evidence_schema_version: int = 0,
) -> bool:
    """True when this settle needs a pressure token: a weight>=3 from-user
    entry dropping below score 2 (or created below 2) on <2 distinct
    non-assumption channels. Corroboration by a second channel satisfies the
    rule mechanically; from-code/from-docs-only settles are exempt."""
    score = entry_field(entry, "ambiguity_score", "ambiguity")
    weight = entry_field(entry, "impact_weight", "weight")
    if not isinstance(score, int) or not isinstance(weight, int):
        return False
    if score >= 2 or weight < 3:
        return False
    if not is_new_entry and (not isinstance(old_score, int) or old_score < 2):
        return False
    channels = normalized_channels(
        entry_field(entry, "evidence_channels", "channels"),
    )
    if "from-user" not in channels:
        return False
    match evidence_schema_version:
        case 1 | 2:
            parsed = ambiguity_ledger.LedgerEntry.model_validate_json(json.dumps(entry))
            return (
                len(parsed.distinct_evidence_groups) < 2
                and not parsed.is_single_source_accepted
            )
        case 0:
            distinct = frozenset(channels) - ambiguity_ledger.NON_EVIDENCE_CHANNELS
            return len(distinct) < 2
        case unexpected if unexpected < 0 or unexpected > 2:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")
        case unreachable:
            assert_never(unreachable)


def pressure_gate_message(entry_id: str) -> str:
    return (
        f"pressure gate: settling {entry_id!r} (weight>=3, from-user, single channel) "
        "below score 2 requires pressure: 'survived', 'second-channel', or "
        "'exempt:<reason>' (Answer Handling rule 1)"
    )


def apply_set(entries: LedgerEntries, op: SetOp, evidence_schema_version: int) -> None:
    match = next((entry for entry in entries if entry.get("id") == op.id), None)
    if match is None:
        raise typer.BadParameter(f"delta set: no ledger entry with id {op.id!r}")
    match evidence_schema_version:
        case 1 | 2:
            if op.add_channels:
                raise typer.BadParameter(
                    f"add_channels is legacy-only; v{evidence_schema_version} uses add_evidence_records",
                )
            if op.evidence_channels is not None and op.evidence_records is None:
                raise typer.BadParameter(
                    f"v{evidence_schema_version} channel projection requires authoritative evidence_records",
                )
        case 0:
            if op.add_evidence_records or op.evidence_records is not None:
                raise typer.BadParameter("structured evidence updates require evidence schema v1 or v2")
        case unexpected if unexpected < 0 or unexpected > 2:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")
        case unreachable:
            assert_never(unreachable)
    old_score = entry_field(match, "ambiguity_score", "ambiguity")
    provided = op.model_dump(
        exclude_none=True,
        exclude={
            "id",
            "append_reason",
            "add_channels",
            "add_evidence_records",
            "evidence_records",
            "pressure",
        },
        mode="json",
    )
    if op.ambiguity_score is not None:
        match.pop("ambiguity", None)
    if op.impact_weight is not None:
        match.pop("weight", None)
    if op.evidence_channels is not None:
        match.pop("channels", None)
    for key, value in provided.items():
        match[key] = list(value) if isinstance(value, tuple) else value
    if op.evidence_records is not None:
        session_contracts.replace_evidence_records(
            match,
            op.evidence_records,
            op.evidence_channels,
        )
    if op.append_reason is not None:
        append_to_reason(match, op.append_reason)
    if op.add_channels:
        current = normalized_channels(
            match.get("evidence_channels", match.get("channels", []))
        )
        merged = list(dict.fromkeys([*current, *op.add_channels]))
        match.pop("channels", None)
        match["evidence_channels"] = merged
    if op.add_evidence_records:
        session_contracts.merge_evidence_records(match, op.add_evidence_records)
    if op.pressure is not None:
        append_to_reason(match, f"[pressure: {op.pressure}]")
    elif op.ambiguity_score is not None and pressure_gate_violation(
        match,
        old_score=old_score,
        is_new_entry=False,
        evidence_schema_version=evidence_schema_version,
    ):
        raise typer.BadParameter(pressure_gate_message(op.id))


def apply_add(
    entries: LedgerEntries,
    entry: JsonObject,
    evidence_schema_version: int,
) -> None:
    entry_id = entry.get("id")
    if any(existing.get("id") == entry_id for existing in entries):
        raise typer.BadParameter(f"delta add: duplicate ledger entry id {entry_id!r}")
    match evidence_schema_version:
        case 1 | 2:
            if entry.get("origin") == "bundle":
                raise typer.BadParameter(
                    f"origin 'bundle' is a legacy parsing alias; v{evidence_schema_version} writes 'batch'",
                )
        case 0:
            if "evidence_records" in entry:
                raise typer.BadParameter("structured evidence updates require evidence schema v1 or v2")
        case unexpected if unexpected < 0 or unexpected > 2:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")
        case unreachable:
            assert_never(unreachable)
    pressure = entry.pop("pressure", None)
    if pressure is not None:
        if not isinstance(pressure, str) or not PRESSURE_TOKEN_PATTERN.match(pressure):
            raise typer.BadParameter(
                f"delta add {entry_id!r}: pressure must be 'survived', "
                "'second-channel', or 'exempt:<reason>'",
            )
        append_to_reason(entry, f"[pressure: {pressure}]")
    elif pressure_gate_violation(
        entry,
        old_score=None,
        is_new_entry=True,
        evidence_schema_version=evidence_schema_version,
    ):
        raise typer.BadParameter(pressure_gate_message(str(entry_id)))
    entries.append(entry)


def apply_checkpoint_confirm(
    entries: LedgerEntries,
    protocol_doc: JsonObject,
    confirm: CheckpointConfirm,
    evidence_schema_version: int,
) -> None:
    matched: list[JsonObject] = []
    for entry_id in confirm.ids:
        match = next((entry for entry in entries if entry.get("id") == entry_id), None)
        if match is None:
            raise typer.BadParameter(
                f"checkpoint_confirm: no ledger entry with id {entry_id!r}",
            )
        matched.append(match)
    apply_event(protocol_doc, Event.CHECKPOINT)
    if confirm.fatigue:
        return
    for match in matched:
        match evidence_schema_version:
            case 1 | 2:
                checkpoint = session_contracts.checkpoint_evidence(str(match["id"]))
                existing_ids = {
                    record.id for record in session_contracts.evidence_records(match)
                }
                if checkpoint.id not in existing_ids:
                    session_contracts.merge_evidence_records(match, (checkpoint,))
                append_to_reason(match, "[checkpoint-corroborated: typed user decision]")
            case 0:
                channels = normalized_channels(
                    entry_field(match, "evidence_channels", "channels"),
                )
                distinct = frozenset(channels) - ambiguity_ledger.NON_EVIDENCE_CHANNELS
                if len(distinct) <= 1 and "from-user" not in distinct:
                    merged = list(dict.fromkeys([*channels, "from-user"]))
                    match.pop("channels", None)
                    match["evidence_channels"] = merged
                    append_to_reason(match, "[checkpoint-corroborated: from-user]")
            case unexpected if unexpected < 0 or unexpected > 2:
                raise typer.BadParameter(f"unknown evidence schema version {unexpected}")
            case unreachable:
                assert_never(unreachable)


def render_transcript_section(
    delta: Delta,
    interactions_used: int,
) -> str:
    note = delta.transcript
    assert note is not None
    event = Event.CHECKPOINT if delta.checkpoint_confirm is not None else delta.event
    stamp = datetime.now().strftime("%Y-%m-%d")
    awaiting_suffix = " [awaiting-answer]" if note.awaiting else ""
    body = "".join(
        f"- {line}\n" if not line.lstrip().startswith("-") else f"{line}\n"
        for line in note.lines
    )
    if event is None:
        # Event-less 0-cost note: invitations, process feedback, lane fold-backs.
        return f"- [note] {note.title}{awaiting_suffix}\n" + body
    if event in HEADING_MARKERS:
        heading = (
            f"\n## interaction {interactions_used} "
            f"[{HEADING_MARKERS[event]}] — {note.title}{awaiting_suffix} ({stamp})\n\n"
        )
        return heading + body
    marker = SUB_BULLET_MARKERS[event]
    return f"- [{marker}] {note.title}{awaiting_suffix}\n" + body


def booked_question(
    raw_questions: object,
    asked_question_id: str,
) -> question_score.QuestionCandidate:
    try:
        questions = question_score.parse_questions(json.dumps(raw_questions))
    except (ValidationError, ValueError) as error:
        raise typer.BadParameter(
            f"questions.json is invalid: {question_score.summarize_validation_error(error)}",
        ) from error
    question = next(
        (candidate for candidate in questions if candidate.id == asked_question_id),
        None,
    )
    if question is None:
        raise typer.BadParameter(
            f"scored-question: asked_question_id {asked_question_id!r} is absent from questions.json",
        )
    if not question.target_ids:
        raise typer.BadParameter(
            f"scored-question: booked question {asked_question_id!r} has no target_ids",
        )
    return question


def derive_question_track_snapshot(
    question: question_score.QuestionCandidate,
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
) -> protocol_state.QuestionTrackSnapshot:
    entries_by_id = {entry.id: entry for entry in entries}
    missing = tuple(target_id for target_id in question.target_ids if target_id not in entries_by_id)
    if missing:
        raise typer.BadParameter(
            f"scored-question: target_ids absent from the current ledger: {list(missing)}",
        )
    keys = tuple(
        ambiguity_ledger.entry_track_keys(entries_by_id[target_id])
        for target_id in question.target_ids
    )
    return protocol_state.QuestionTrackSnapshot(
        asked_question_id=question.id,
        ledger_ids=question.target_ids,
        categories=tuple(category for key in keys for category in key["categories"]),
        domains=tuple(domain for key in keys for domain in key["domains"]),
        target_files=tuple(target for key in keys for target in key["target_files"]),
    )


def existing_question_track_snapshots(
    protocol_doc: JsonObject,
) -> list[protocol_state.QuestionTrackSnapshot]:
    raw_snapshots = protocol_doc.get("recent_question_tracks", [])
    if not isinstance(raw_snapshots, list):
        raise typer.BadParameter("protocol recent_question_tracks must be an array")
    try:
        return [
            protocol_state.QuestionTrackSnapshot.model_validate(snapshot)
            for snapshot in raw_snapshots
        ]
    except ValidationError as error:
        raise typer.BadParameter(
            f"protocol recent_question_tracks is invalid: "
            f"{protocol_state.summarize_validation_error(error)}",
        ) from error


def is_multi_track_batch(
    delta: Delta,
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
) -> bool:
    changed_ids = {op.id for op in delta.set} | {
        entry_id
        for entry in delta.add
        if isinstance((entry_id := entry.get("id")), str)
    }
    tracks: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()
    for entry in entries:
        if entry.id not in changed_ids:
            continue
        keys = ambiguity_ledger.entry_track_keys(entry)
        track = (keys["categories"], keys["domains"], keys["target_files"])
        if any(track):
            tracks.add(track)
    return len(tracks) > 1


def update_question_track_history(
    protocol_doc: JsonObject,
    delta: Delta,
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    booked: question_score.QuestionCandidate | None,
) -> None:
    snapshots = existing_question_track_snapshots(protocol_doc)
    event = Event.CHECKPOINT if delta.checkpoint_confirm is not None else delta.event
    clears_window = (
        event in SWEEP_EVENTS
        or event in CONTRARIAN_EVENTS
        or event is Event.CHECKPOINT
        or (event is Event.BATCH and is_multi_track_batch(delta, entries))
    )
    if clears_window:
        snapshots = []
    elif event is Event.SCORED_QUESTION:
        assert booked is not None
        snapshots.append(derive_question_track_snapshot(booked, entries))
    elif event is Event.PRESSURE_FOLLOWUP and snapshots:
        assert delta.pressure_parent is not None
        parent = delta.pressure_parent.strip()
        inherited = next(
            (
                snapshot
                for snapshot in reversed(snapshots)
                if snapshot.asked_question_id == parent
            ),
            snapshots[-1],
        )
        snapshots.append(inherited)
    protocol_doc["recent_question_tracks"] = [
        snapshot.model_dump(mode="json")
        for snapshot in snapshots[-protocol_state.LOCALITY_WINDOW :]
    ]


def apply_delta(
    delta: Delta,
    raw_ledger: object,
    raw_protocol: object,
    raw_questions: object | None,
    build_contract_digest: str | None = None,
) -> tuple[
    object,
    JsonObject,
    ambiguity_ledger.AmbiguitySummary,
    protocol_state.ProtocolSummary,
    tuple[ambiguity_ledger.LedgerEntry, ...],
    protocol_state.ProtocolState,
]:
    section, entries = ledger_section(raw_ledger)
    previous_entries = deepcopy(entries)
    if not isinstance(raw_protocol, dict):
        raise typer.BadParameter("protocol.json must be a JSON object")
    if not all(isinstance(key, str) for key in raw_protocol):
        raise typer.BadParameter("protocol.json keys must be strings")
    protocol_doc = cast(JsonObject, dict(raw_protocol))
    evidence_schema_version = integer_value(
        protocol_doc,
        "evidence_schema_version",
    )
    session_contracts.validate_evidence_schema_version(evidence_schema_version)
    for op in delta.set:
        apply_set(entries, op, evidence_schema_version)
    for entry in delta.add:
        apply_add(entries, dict(entry), evidence_schema_version)
    unknown = set(delta.protocol) - PROTOCOL_KEYS
    if unknown:
        raise typer.BadParameter(
            f"delta protocol: unknown field(s) {sorted(unknown)}; "
            f"use ProtocolState fields only",
        )
    managed = set(delta.protocol) & (
        EVENT_MANAGED_KEYS | BUILD_CONTRACT_MANAGED_KEYS | HISTORY_MANAGED_KEYS
    )
    if managed:
        raise typer.BadParameter(
            f"delta protocol sets event-managed field(s) {sorted(managed)}; "
            "use the corresponding typed event",
        )
    event_for_conflict = (
        Event.CHECKPOINT if delta.checkpoint_confirm is not None else delta.event
    )
    for key, value in delta.protocol.items():
        if key == LENSES_KEY:
            if not isinstance(value, dict):
                raise typer.BadParameter("delta protocol.lenses must be an object")
            current_lenses = protocol_doc.get(LENSES_KEY, {})
            if not isinstance(current_lenses, dict):
                raise typer.BadParameter("protocol.json lenses must be an object")
            lenses = dict(current_lenses)
            lenses.update(value)
            protocol_doc[LENSES_KEY] = lenses
        else:
            protocol_doc[key] = value
    if delta.open_world_sweep is not None:
        session_contracts.append_open_world_sweep(
            protocol_doc,
            delta.open_world_sweep,
        )
    match evidence_schema_version:
        case 1 | 2:
            if delta.event in SWEEP_EVENTS:
                sweep = delta.open_world_sweep
                if sweep is None or sweep.phase is not open_world.OpenWorldPhase.BREADTH:
                    raise typer.BadParameter(
                        f"v{evidence_schema_version} dry/new-gap sweeps require a fresh breadth open-world record",
                    )
            if LENSES_KEY in delta.protocol:
                records = protocol_doc.get("open_world_records", [])
                revision = integer_value(protocol_doc, "material_revision")
                has_orientation = isinstance(records, list) and any(
                    record.get("phase") == "orientation"
                    and record.get("material_revision_binding") == revision
                    for record in records
                    if isinstance(record, dict)
                )
                if not has_orientation:
                    raise typer.BadParameter(
                        "lens decisions require a fresh orientation open-world record first",
                    )
        case 0:
            pass
        case unexpected if unexpected < 0 or unexpected > 2:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")
        case unreachable:
            assert_never(unreachable)
    probe_material_change = False
    if delta.probe_decision is not None:
        session_contracts.record_probe_decision(protocol_doc, delta.probe_decision)
        probe_material_change = True
    if delta.probe_attempt is not None:
        outcome = session_contracts.append_probe_attempt(
            protocol_doc,
            delta.probe_attempt,
        )
        if outcome in {
            probe_policy.ProbeOutcome.NO_MATERIAL_DIVERGENCE,
            probe_policy.ProbeOutcome.INCONCLUSIVE,
        } and (
            delta.set or delta.add
        ):
            raise typer.BadParameter(
                "no-material-divergence and inconclusive results cannot settle, reopen, or credit a ledger entry",
            )
        if outcome is probe_policy.ProbeOutcome.MATERIAL_DIVERGENCE:
            if delta.set:
                raise typer.BadParameter(
                    "unverified material divergence may only reopen a probe-origin ledger gap",
                )
            if (
                delta.protocol
                or delta.append_history
                or delta.event is not None
                or delta.sweep_result is not None
                or delta.checkpoint_confirm is not None
                or delta.transcript is not None
                or delta.build_contract_test is not None
                or delta.open_world_sweep is not None
                or delta.probe_decision is not None
                or delta.questions is not None
                or delta.pressure_parent is not None
                or delta.asked_question_id is not None
            ):
                raise typer.BadParameter(
                    "unverified material divergence may only reopen a probe-origin ledger gap",
                )
            discovered = tuple(
                entry
                for entry in delta.add
                if entry.get("origin") == "probe"
                and entry.get("ambiguity_score", entry.get("ambiguity", 0)) in (1, 2, 3)
            )
            if (
                not discovered
                or len(discovered) != len(delta.add)
                or any(entry.get("status", "draft") != "draft" for entry in discovered)
            ):
                raise typer.BadParameter(
                    "material divergence may only reopen draft ambiguous origin 'probe' ledger entries",
                )
            probe_material_change = True
        protocol_doc["contrarian_probes_run"] = (
            integer_value(protocol_doc, "contrarian_probes_run") + 1
        )
    if delta.build_contract_test is not None:
        if build_contract_digest is None:
            raise typer.BadParameter("build_contract_test requires the current handoff.md")
        protocol_doc["build_contract_tested"] = True
        protocol_doc["build_contract_digest"] = build_contract_digest
        protocol_doc["build_contract_reviewer"] = delta.build_contract_test.reviewer
    booked: question_score.QuestionCandidate | None = None
    if delta.event is Event.SCORED_QUESTION:
        if delta.asked_question_id is None:
            raise typer.BadParameter("scored-question requires asked_question_id")
        if raw_questions is None:
            raise typer.BadParameter("questions.json not found for scored-question")
        booked = booked_question(raw_questions, delta.asked_question_id)

    material_change = (
        has_material_ledger_change(previous_entries, entries)
        or probe_material_change
    )
    checkpoint_in_delta = delta.checkpoint_confirm is not None or event_for_conflict is Event.CHECKPOINT
    if material_change:
        protocol_doc["material_revision"] = (
            integer_value(protocol_doc, "material_revision") + 1
        )
        protocol_doc["dry_sweeps_in_row"] = 0
        protocol_doc["build_contract_tested"] = False
        protocol_doc["build_contract_digest"] = ""
        protocol_doc["build_contract_reviewer"] = ""
        if not checkpoint_in_delta:
            protocol_doc["checkpoint_since_last_material_change"] = False

    if delta.checkpoint_confirm is not None:
        apply_checkpoint_confirm(
            entries,
            protocol_doc,
            delta.checkpoint_confirm,
            evidence_schema_version,
        )
    elif delta.event is not None:
        if delta.event is Event.PRESSURE_FOLLOWUP:
            assert delta.pressure_parent is not None
            raw_counts = protocol_doc.get("pressure_followups_by_parent", {})
            if not isinstance(raw_counts, dict):
                raise typer.BadParameter("protocol pressure_followups_by_parent must be an object")
            counts = dict(raw_counts)
            parent = delta.pressure_parent.strip()
            count = counts.get(parent, 0)
            if not isinstance(count, int) or isinstance(count, bool):
                raise typer.BadParameter(f"pressure count for {parent!r} must be an integer")
            if count >= 2:
                raise typer.BadParameter(
                    f"pressure-followup limit reached for {parent!r}; send the next turn as scored-question",
                )
            counts[parent] = count + 1
            protocol_doc["pressure_followups_by_parent"] = counts
        apply_event(protocol_doc, delta.event, delta.sweep_result)
    if material_change and delta.event in SWEEP_EVENTS:
        protocol_doc["dry_sweeps_in_row"] = 0

    # Validate the ledger BEFORE the history append so the appended residual
    # is computed from an already-valid ledger.
    ledger_payload = json.dumps({"entries": entries} if section else entries)
    try:
        parsed_entries = ambiguity_ledger.parse_entries(ledger_payload)
        atom_contract.validate_entries(
            parsed_entries,
            evidence_schema_version=evidence_schema_version,
        )
    except ValidationError as error:
        raise typer.BadParameter(
            f"delta produced an invalid ledger: "
            f"{ambiguity_ledger.summarize_validation_error(error)}",
        ) from error
    except atom_contract.BehaviorAtomPolicyError as error:
        raise typer.BadParameter(f"delta produced an invalid ledger: {error}") from error
    ledger_summary = ambiguity_ledger.summarize_ambiguity(
        parsed_entries,
        evidence_schema_version=evidence_schema_version,
    )
    update_question_track_history(protocol_doc, delta, parsed_entries, booked)

    if delta.append_history:
        residual_history = protocol_doc.get("residual_history", [])
        gap_count_history = protocol_doc.get("gap_count_history", [])
        if not isinstance(residual_history, list) or not isinstance(gap_count_history, list):
            raise typer.BadParameter("protocol history fields must be arrays")
        protocol_doc["residual_history"] = [
            *residual_history,
            ledger_summary.residual,
        ]
        protocol_doc["gap_count_history"] = [
            *gap_count_history,
            ledger_summary.active_count,
        ]

    try:
        parsed_protocol = protocol_state.parse_state(json.dumps(protocol_doc))
    except ValidationError as error:
        raise typer.BadParameter(
            f"delta produced an invalid protocol: "
            f"{protocol_state.summarize_validation_error(error)}",
        ) from error
    protocol_summary = protocol_state.summarize_protocol(parsed_protocol)

    if section is not None:
        assert isinstance(raw_ledger, dict)
        new_ledger: object = {**raw_ledger, section: entries}
    else:
        new_ledger = entries
    return new_ledger, protocol_doc, ledger_summary, protocol_summary, parsed_entries, parsed_protocol


@dataclass(frozen=True, slots=True)
class UpdateResult:
    ledger_summary: ambiguity_ledger.AmbiguitySummary
    protocol_summary: protocol_state.ProtocolSummary
    entries: tuple[ambiguity_ledger.LedgerEntry, ...]
    protocol: protocol_state.ProtocolState


def update_session(session_dir: Path, delta: Delta) -> UpdateResult:
    ledger_path = session_dir / "ledger.json"
    protocol_path = session_dir / "protocol.json"
    questions_path = session_dir / "questions.json"
    transcript_path = session_dir / "transcript.md"
    build_contract_path = session_dir / "build-contract.json"
    with atomic_write.session_transaction(session_dir):
        if delta.transcript is not None and not transcript_path.is_file():
            raise typer.BadParameter(f"transcript.md not found: {transcript_path}")
        raw_ledger = load_json(ledger_path, "ledger.json")
        raw_protocol = load_json(protocol_path, "protocol.json")
        raw_questions = (
            load_json(questions_path, "questions.json")
            if questions_path.is_file()
            else None
        )

        handoff_digest: str | None = None
        compiled_contract: build_contract.BuildContract | None = None
        if delta.build_contract_test is not None:
            handoff_path = session_dir / "handoff.md"
            if not handoff_path.is_file():
                raise typer.BadParameter(f"handoff.md not found: {handoff_path}")
            handoff_digest = implementation_gate.contract_digest(
                handoff_path.read_text(encoding="utf-8"),
            )
            contract_schema_version = integer_value(
                cast(JsonObject, raw_protocol),
                "contract_schema_version",
            )
            match contract_schema_version:
                case 1 | 2:
                    compiled_contract = build_contract.compile_handoff(
                        handoff_path.read_text(encoding="utf-8"),
                    )
                    if compiled_contract.schema_version != contract_schema_version:
                        raise typer.BadParameter(
                            "compiled BuildContract schema version does not match protocol",
                        )
                case 0:
                    pass
                case unexpected if unexpected < 0 or unexpected > 2:
                    raise typer.BadParameter(f"unknown BuildContract schema version {unexpected}")
                case unreachable:
                    assert_never(unreachable)

        (
            new_ledger,
            new_protocol,
            ledger_summary,
            protocol_summary,
            parsed_entries,
            parsed_protocol,
        ) = apply_delta(
            delta,
            raw_ledger,
            raw_protocol,
            raw_questions,
            handoff_digest,
        )

        answer_bearing = delta.checkpoint_confirm is not None or (
            delta.event is not None
            and (delta.event in COSTED_EVENTS or delta.event is Event.PRESSURE_FOLLOWUP)
        )
        updates = {
            ledger_path: json.dumps(new_ledger, indent=2, ensure_ascii=False) + "\n",
            protocol_path: json.dumps(new_protocol, indent=2, ensure_ascii=False) + "\n",
        }
        if compiled_contract is not None:
            updates[build_contract_path] = build_contract.canonical_json(
                compiled_contract,
            )
        if delta.questions is not None:
            updates[questions_path] = json.dumps(
                {
                    "questions": [
                        candidate.model_dump(mode="json")
                        for candidate in delta.questions
                    ]
                },
                indent=2,
                ensure_ascii=False,
            ) + "\n"
        elif questions_path.is_file() and (delta.set or delta.add):
            updates[questions_path] = json.dumps(
                {"questions": []},
                indent=2,
                ensure_ascii=False,
            ) + "\n"
        transcript_text = (
            transcript_path.read_text(encoding="utf-8")
            if transcript_path.is_file()
            else None
        )
        if answer_bearing and transcript_text is not None:
            transcript_text = transcript_text.replace("[awaiting-answer]", "[answered]")
        if delta.transcript is not None:
            section_text = render_transcript_section(
                delta,
                integer_value(new_protocol, "interactions_used"),
            )
            assert transcript_text is not None
            transcript_text += section_text
        if transcript_text is not None and (answer_bearing or delta.transcript is not None):
            updates[transcript_path] = transcript_text
        atomic_write.commit_text_files(updates, locked=True)

    return UpdateResult(
        ledger_summary=ledger_summary,
        protocol_summary=protocol_summary,
        entries=parsed_entries,
        protocol=parsed_protocol,
    )


def main(
    session_dir: Annotated[
        Path,
        typer.Argument(help="Session directory containing ledger.json and protocol.json."),
    ],
    delta: Annotated[
        str | None,
        typer.Option("--delta", help="Delta JSON (use '-' to read stdin)."),
    ] = None,
    delta_file: Annotated[
        Path | None,
        typer.Option("--delta-file", help="Path to a delta JSON file."),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
    show_next: Annotated[
        bool,
        typer.Option("--next", help="Append the deterministic next-action routing."),
    ] = False,
) -> None:
    """Apply ONE bookkeeping delta (all-or-nothing) and emit the dashboards.

    Delta JSON shape (all fields optional, extra keys rejected):

    {"event": "brain-dump|framing|scored-question|bundle|batch|
               sweep-asked|sweep-free|contrarian-asked|contrarian-free|pressure-followup",
     "pressure_parent": "required parent id for pressure-followup",
     "asked_question_id": "required pre-existing question id for scored-question",
     "sweep_result": "dry|new-gaps",
     "set": [{"id": "N1", <entry fields>, "append_reason": "...",
              "add_channels": ["from-code"],
              "pressure": "survived|second-channel|exempt:<reason>"}],
     "add": [{<full ledger entry>}],
     "protocol": {<partial protocol; "lenses" merges per-lens>},
     "append_history": true,
     "checkpoint_confirm": {"ids": ["N1"], "fatigue": false},
     "build_contract_test": {"reviewer": "critic"},
     "questions": [{<full scored question candidate>}],
     "transcript": {"title": "...", "lines": ["..."], "awaiting": false}}

    Sweep events require sweep_result. event and checkpoint_confirm are mutually exclusive. transcript WITHOUT an
    event appends a 0-cost "- [note]" sub-bullet (invitations, fold-backs);
    "awaiting": true marks it [awaiting-answer]. Any answer-bearing delta
    (costed event, pressure-followup, or checkpoint_confirm) auto-resolves
    prior [awaiting-answer] markers to [answered].
    build_contract_test is a dedicated delta that binds the reviewer and current
    handoff Part-1 digest into protocol.json.
    """
    if not session_dir.is_dir() or session_dir.is_symlink():
        raise typer.BadParameter(f"not a session directory: {session_dir}")
    if (delta is None) == (delta_file is None):
        raise typer.BadParameter("pass exactly one of --delta or --delta-file")
    if delta == "-":
        raw_delta = sys.stdin.read()
    elif delta is not None:
        raw_delta = delta
    else:
        assert delta_file is not None
        if not delta_file.is_file():
            raise typer.BadParameter(f"delta file not found: {delta_file}")
        raw_delta = delta_file.read_text(encoding="utf-8")

    parsed_delta = parse_delta(raw_delta)
    result = update_session(session_dir, parsed_delta)

    ready = session_status.is_ready(result.ledger_summary, result.protocol_summary)
    if output_format is OutputFormat.MARKDOWN:
        output = session_status.render_markdown(
            result.ledger_summary,
            result.protocol_summary,
            ready,
        )
        if show_next:
            output += "\n\n" + session_status.render_next_action(
                result.entries,
                result.protocol,
                result.ledger_summary,
                result.protocol_summary,
                ready,
            )
        typer.echo(output)
    else:
        typer.echo(
            session_status.render_json(
                result.ledger_summary,
                result.protocol_summary,
                ready,
            )
        )


if __name__ == "__main__":
    typer.run(main)
