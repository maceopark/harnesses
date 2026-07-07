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
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from scripts import ambiguity_ledger, protocol_state, session_status

LEDGER_SECTIONS: Final[tuple[str, ...]] = ("requirements", "gaps", "entries", "ledger")
LENSES_KEY: Final[str] = "lenses"
PROTOCOL_KEYS: Final[frozenset[str]] = frozenset(
    protocol_state.ProtocolState.model_fields,
)
PRESSURE_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(survived|second-channel|exempt:.+)$",
)


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
        managed.add("sweeps_run")
    if event in CONTRARIAN_EVENTS:
        managed.add("contrarian_probes_run")
    if event is Event.CHECKPOINT:
        managed.update({"falsification_checkpoints_run", "checkpoint_since_last_material_change"})
    if event is Event.BRAIN_DUMP:
        managed.add("brain_dump_done")
    if event is Event.FRAMING:
        managed.add("framing_challenged")
    return frozenset(managed)


def apply_event(protocol_doc: dict, event: Event) -> None:
    def bump(key: str, amount: int = 1) -> None:
        protocol_doc[key] = int(protocol_doc.get(key, 0)) + amount

    if event in COSTED_EVENTS:
        bump("interactions_used")
    if event in SWEEP_COUNTED_EVENTS:
        bump("answers_since_sweep")
    if event in SWEEP_EVENTS:
        protocol_doc["answers_since_sweep"] = 0
        bump("sweeps_run")
    if event in CONTRARIAN_EVENTS:
        bump("contrarian_probes_run")
    if event is Event.CHECKPOINT:
        bump("falsification_checkpoints_run")
        protocol_doc["checkpoint_since_last_material_change"] = True
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
    deferred: bool | dict | None = None
    ambiguity_score: int | None = None
    impact_weight: int | None = None
    evidence_channels: tuple[str, ...] | None = None
    add_channels: tuple[str, ...] = ()
    pressure: str | None = None

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

    ids: tuple[str, ...]
    fatigue: bool = False


class TranscriptNote(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    title: str
    lines: tuple[str, ...] = ()
    # Marks the note as an in-flight question: the rendered line carries
    # [awaiting-answer], which the next answer-bearing delta auto-resolves.
    awaiting: bool = False


class Delta(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    set: tuple[SetOp, ...] = ()
    add: tuple[dict, ...] = ()
    protocol: dict = {}
    append_history: bool = False
    event: Event | None = None
    checkpoint_confirm: CheckpointConfirm | None = None
    transcript: TranscriptNote | None = None


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


def ledger_section(raw: object) -> tuple[str | None, list[dict]]:
    """Return (container key or None for a bare list, entry dicts)."""
    if isinstance(raw, list):
        return None, list(raw)
    if isinstance(raw, dict):
        populated = [key for key in LEDGER_SECTIONS if raw.get(key)]
        if len(populated) == 1:
            return populated[0], list(raw[populated[0]])
    raise typer.BadParameter(
        "ledger.json must be a list or an object with exactly one populated "
        f"section among {', '.join(LEDGER_SECTIONS)}",
    )


def normalized_channels(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    normalized = []
    for channel in raw:
        cleaned = str(channel).strip().lower()
        normalized.append(ambiguity_ledger.CHANNEL_ALIASES.get(cleaned, cleaned))
    return tuple(dict.fromkeys(normalized))


def entry_field(entry: dict, name: str, alias: str) -> object:
    return entry.get(name, entry.get(alias))


def append_to_reason(entry: dict, note: str) -> None:
    existing = str(entry.get("reason", "")).strip()
    entry["reason"] = f"{existing}; {note}" if existing else note


def pressure_gate_violation(
    entry: dict,
    *,
    old_score: object,
    is_new_entry: bool,
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
    distinct = frozenset(channels) - ambiguity_ledger.NON_EVIDENCE_CHANNELS
    return len(distinct) < 2


def pressure_gate_message(entry_id: str) -> str:
    return (
        f"pressure gate: settling {entry_id!r} (weight>=3, from-user, single channel) "
        "below score 2 requires pressure: 'survived', 'second-channel', or "
        "'exempt:<reason>' (Answer Handling rule 1)"
    )


def apply_set(entries: list[dict], op: SetOp) -> None:
    match = next((entry for entry in entries if entry.get("id") == op.id), None)
    if match is None:
        raise typer.BadParameter(f"delta set: no ledger entry with id {op.id!r}")
    old_score = entry_field(match, "ambiguity_score", "ambiguity")
    provided = op.model_dump(
        exclude_none=True,
        exclude={"id", "append_reason", "add_channels", "pressure"},
    )
    for key, value in provided.items():
        match[key] = list(value) if isinstance(value, tuple) else value
    if op.append_reason is not None:
        append_to_reason(match, op.append_reason)
    if op.add_channels:
        current = match.get("evidence_channels", match.get("channels", []))
        if isinstance(current, str):
            current = [part.strip() for part in current.split(",") if part.strip()]
        merged = list(dict.fromkeys([*current, *op.add_channels]))
        match.pop("channels", None)
        match["evidence_channels"] = merged
    if op.pressure is not None:
        append_to_reason(match, f"[pressure: {op.pressure}]")
    elif op.ambiguity_score is not None and pressure_gate_violation(
        match,
        old_score=old_score,
        is_new_entry=False,
    ):
        raise typer.BadParameter(pressure_gate_message(op.id))


def apply_add(entries: list[dict], entry: dict) -> None:
    entry_id = entry.get("id")
    if any(existing.get("id") == entry_id for existing in entries):
        raise typer.BadParameter(f"delta add: duplicate ledger entry id {entry_id!r}")
    pressure = entry.pop("pressure", None)
    if pressure is not None:
        if not isinstance(pressure, str) or not PRESSURE_TOKEN_PATTERN.match(pressure):
            raise typer.BadParameter(
                f"delta add {entry_id!r}: pressure must be 'survived', "
                "'second-channel', or 'exempt:<reason>'",
            )
        append_to_reason(entry, f"[pressure: {pressure}]")
    elif pressure_gate_violation(entry, old_score=None, is_new_entry=True):
        raise typer.BadParameter(pressure_gate_message(str(entry_id)))
    entries.append(entry)


def apply_checkpoint_confirm(
    entries: list[dict],
    protocol_doc: dict,
    confirm: CheckpointConfirm,
) -> None:
    apply_event(protocol_doc, Event.CHECKPOINT)
    if confirm.fatigue:
        return
    for entry_id in confirm.ids:
        match = next((entry for entry in entries if entry.get("id") == entry_id), None)
        if match is None:
            raise typer.BadParameter(
                f"checkpoint_confirm: no ledger entry with id {entry_id!r}",
            )
        channels = normalized_channels(
            entry_field(match, "evidence_channels", "channels"),
        )
        distinct = frozenset(channels) - ambiguity_ledger.NON_EVIDENCE_CHANNELS
        if len(distinct) <= 1 and "from-user" not in distinct:
            merged = list(dict.fromkeys([*channels, "from-user"]))
            match.pop("channels", None)
            match["evidence_channels"] = merged
            append_to_reason(match, "[checkpoint-corroborated: from-user]")


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


def apply_delta(
    delta: Delta,
    raw_ledger: object,
    raw_protocol: object,
) -> tuple[
    object,
    dict,
    ambiguity_ledger.AmbiguitySummary,
    protocol_state.ProtocolSummary,
    tuple[ambiguity_ledger.LedgerEntry, ...],
    protocol_state.ProtocolState,
]:
    section, entries = ledger_section(raw_ledger)
    for op in delta.set:
        apply_set(entries, op)
    for entry in delta.add:
        apply_add(entries, dict(entry))

    if not isinstance(raw_protocol, dict):
        raise typer.BadParameter("protocol.json must be a JSON object")
    protocol_doc = dict(raw_protocol)
    unknown = set(delta.protocol) - PROTOCOL_KEYS
    if unknown:
        raise typer.BadParameter(
            f"delta protocol: unknown field(s) {sorted(unknown)}; "
            f"use ProtocolState fields only",
        )
    event_for_conflict = (
        Event.CHECKPOINT if delta.checkpoint_confirm is not None else delta.event
    )
    if event_for_conflict is not None:
        conflicts = set(delta.protocol) & managed_protocol_keys(event_for_conflict)
        if conflicts:
            raise typer.BadParameter(
                f"delta protocol sets {sorted(conflicts)} but event "
                f"{event_for_conflict.value!r} computes them; drop the manual values",
            )
    for key, value in delta.protocol.items():
        if key == LENSES_KEY:
            if not isinstance(value, dict):
                raise typer.BadParameter("delta protocol.lenses must be an object")
            lenses = dict(protocol_doc.get(LENSES_KEY, {}))
            lenses.update(value)
            protocol_doc[LENSES_KEY] = lenses
        else:
            protocol_doc[key] = value

    if delta.checkpoint_confirm is not None:
        apply_checkpoint_confirm(entries, protocol_doc, delta.checkpoint_confirm)
    elif delta.event is not None:
        apply_event(protocol_doc, delta.event)

    # Validate the ledger BEFORE the history append so the appended residual
    # is computed from an already-valid ledger.
    ledger_payload = json.dumps({"entries": entries} if section else entries)
    try:
        parsed_entries = ambiguity_ledger.parse_entries(ledger_payload)
    except ValidationError as error:
        raise typer.BadParameter(
            f"delta produced an invalid ledger: "
            f"{ambiguity_ledger.summarize_validation_error(error)}",
        ) from error
    ledger_summary = ambiguity_ledger.summarize_ambiguity(parsed_entries)

    if delta.append_history:
        protocol_doc["residual_history"] = [
            *protocol_doc.get("residual_history", []),
            ledger_summary.residual,
        ]
        protocol_doc["gap_count_history"] = [
            *protocol_doc.get("gap_count_history", []),
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

    new_ledger: object = {**raw_ledger, section: entries} if section else entries
    return new_ledger, protocol_doc, ledger_summary, protocol_summary, parsed_entries, parsed_protocol


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
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

    {"event": "brain-dump|framing|scored-question|bundle|batch|checkpoint|
               sweep-asked|sweep-free|contrarian-asked|contrarian-free|pressure-followup",
     "set": [{"id": "N1", <entry fields>, "append_reason": "...",
              "add_channels": ["from-code"],
              "pressure": "survived|second-channel|exempt:<reason>"}],
     "add": [{<full ledger entry>}],
     "protocol": {<partial protocol; "lenses" merges per-lens>},
     "append_history": true,
     "checkpoint_confirm": {"ids": ["N1"], "fatigue": false},
     "transcript": {"title": "...", "lines": ["..."], "awaiting": false}}

    event and checkpoint_confirm are mutually exclusive. transcript WITHOUT an
    event appends a 0-cost "- [note]" sub-bullet (invitations, fold-backs);
    "awaiting": true marks it [awaiting-answer]. Any answer-bearing delta
    (costed event, pressure-followup, or checkpoint_confirm) auto-resolves
    prior [awaiting-answer] markers to [answered].
    """
    if not session_dir.is_dir():
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
    ledger_path = session_dir / "ledger.json"
    protocol_path = session_dir / "protocol.json"
    transcript_path = session_dir / "transcript.md"
    if parsed_delta.transcript is not None and not transcript_path.is_file():
        raise typer.BadParameter(f"transcript.md not found: {transcript_path}")
    raw_ledger = load_json(ledger_path, "ledger.json")
    raw_protocol = load_json(protocol_path, "protocol.json")

    new_ledger, new_protocol, ledger_summary, protocol_summary, parsed_entries, parsed_protocol = (
        apply_delta(parsed_delta, raw_ledger, raw_protocol)
    )

    # All-or-nothing: both documents validated above; only now touch disk.
    write_json(ledger_path, new_ledger)
    write_json(protocol_path, new_protocol)
    answer_bearing = parsed_delta.checkpoint_confirm is not None or (
        parsed_delta.event is not None
        and (parsed_delta.event in COSTED_EVENTS or parsed_delta.event is Event.PRESSURE_FOLLOWUP)
    )
    if answer_bearing and transcript_path.is_file():
        # The answer just landed: resolve any in-flight question marker so
        # transcript_check never sees a stale [awaiting-answer].
        text = transcript_path.read_text(encoding="utf-8")
        if "[awaiting-answer]" in text:
            transcript_path.write_text(
                text.replace("[awaiting-answer]", "[answered]"),
                encoding="utf-8",
            )
    if parsed_delta.transcript is not None:
        section_text = render_transcript_section(
            parsed_delta,
            int(new_protocol.get("interactions_used", 0)),
        )
        with transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(section_text)

    ready = session_status.is_ready(ledger_summary, protocol_summary)
    if output_format is OutputFormat.MARKDOWN:
        output = session_status.render_markdown(ledger_summary, protocol_summary, ready)
        if show_next:
            output += "\n\n" + session_status.render_next_action(
                parsed_entries,
                parsed_protocol,
                ledger_summary,
                protocol_summary,
                ready,
            )
        typer.echo(output)
    else:
        typer.echo(session_status.render_json(ledger_summary, protocol_summary, ready))


if __name__ == "__main__":
    typer.run(main)
