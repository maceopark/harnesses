"""Deterministic, append-only GjcEpisode.v1 JSONL records.

The module only serializes and validates supplied data.  It never opens paths or
executes tools; callers provide a text stream when they need to persist an
episode.
"""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


EPISODE_SCHEMA = "GjcEpisode.v1"
MAX_LINE_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_KIND = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")


class EpisodeError(ValueError):
    """Raised when a JSONL episode is not canonical or causally valid."""


class _TextSink(Protocol):
    def write(self, text: str, /) -> object: ...


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _json_value(value: Any, *, depth: int = 0) -> Any:
    """Reject non-JSON values that would make a digest implementation-dependent."""
    if depth > MAX_JSON_DEPTH:
        raise EpisodeError(f"JSON value exceeds maximum depth {MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise EpisodeError("floating-point payload values are not canonical")
    if isinstance(value, list):
        return [_json_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EpisodeError("JSON object keys must be strings")
            normalized[key] = _json_value(item, depth=depth + 1)
        return normalized
    raise EpisodeError(f"unsupported JSON value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return the sole JSON representation used by GjcEpisode.v1."""
    try:
        return json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise EpisodeError("value cannot be represented as canonical JSON") from error


def _digest_record(record_without_digest: dict[str, Any]) -> str:
    return sha256(canonical_json(record_without_digest).encode("utf-8")).hexdigest()


class GjcEpisodeEvent(_StrictModel):
    """One causally ordered event, including its digest-chain link."""

    schema: str = EPISODE_SCHEMA
    seq: int = Field(ge=1)
    parent_seq: int | None = None
    kind: str
    payload: Any
    prev_digest: str | None = None
    digest: str

    @field_validator("schema")
    @classmethod
    def _schema_is_v1(cls, value: str) -> str:
        if value != EPISODE_SCHEMA:
            raise ValueError(f"schema must be {EPISODE_SCHEMA}")
        return value

    @field_validator("kind")
    @classmethod
    def _kind_is_safe(cls, value: str) -> str:
        if not _KIND.fullmatch(value):
            raise ValueError("kind must be lowercase ASCII and 1-128 characters")
        return value

    @field_validator("payload")
    @classmethod
    def _payload_is_canonical_json(cls, value: Any) -> Any:
        return _json_value(value)

    @field_validator("prev_digest", "digest")
    @classmethod
    def _digest_is_lowercase_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _HEX_DIGEST.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def _self_consistent_digest(self) -> "GjcEpisodeEvent":
        if self.parent_seq is not None and self.parent_seq >= self.seq:
            raise ValueError("parent_seq must precede seq")
        expected = _digest_record(self.record_without_digest())
        if self.digest != expected:
            raise ValueError("digest does not match the canonical event record")
        return self

    def record_without_digest(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "seq": self.seq,
            "parent_seq": self.parent_seq,
            "kind": self.kind,
            "payload": self.payload,
            "prev_digest": self.prev_digest,
        }

    def record(self) -> dict[str, Any]:
        record = self.record_without_digest()
        record["digest"] = self.digest
        return record

    def jsonl_line(self) -> str:
        return canonical_json(self.record())


class GjcEpisode(_StrictModel):
    """A fully validated in-memory GjcEpisode.v1 transcript."""

    events: tuple[GjcEpisodeEvent, ...] = ()

    @model_validator(mode="after")
    def _validate_event_chain(self) -> "GjcEpisode":
        previous_digest: str | None = None
        seen_sequences: set[int] = set()
        for expected_seq, event in enumerate(self.events, start=1):
            if event.seq != expected_seq:
                raise ValueError("seq values must start at 1 and increase by exactly one")
            if event.prev_digest != previous_digest:
                raise ValueError("prev_digest does not match the preceding event")
            if event.parent_seq is not None and event.parent_seq not in seen_sequences:
                raise ValueError("parent_seq must reference an earlier event")
            seen_sequences.add(event.seq)
            previous_digest = event.digest
        return self

    @property
    def last_digest(self) -> str | None:
        return self.events[-1].digest if self.events else None

    def to_jsonl(self) -> str:
        return "".join(f"{event.jsonl_line()}\n" for event in self.events)

    @classmethod
    def from_jsonl(cls, text: str, *, max_line_bytes: int = MAX_LINE_BYTES) -> "GjcEpisode":
        if not isinstance(text, str):
            raise EpisodeError("JSONL input must be text")
        if not text:
            return cls()
        if not text.endswith("\n"):
            raise EpisodeError("canonical JSONL must end every event with LF")
        if "\r" in text:
            raise EpisodeError("canonical JSONL uses LF, not CRLF")
        return cls.from_lines(text.splitlines(), max_line_bytes=max_line_bytes)

    @classmethod
    def from_lines(
        cls, lines: Iterable[str], *, max_line_bytes: int = MAX_LINE_BYTES
    ) -> "GjcEpisode":
        if not isinstance(max_line_bytes, int) or max_line_bytes < 1:
            raise EpisodeError("max_line_bytes must be a positive integer")
        events: list[GjcEpisodeEvent] = []
        for line_number, raw_line in enumerate(lines, start=1):
            if not isinstance(raw_line, str):
                raise EpisodeError(f"line {line_number} is not text")
            line = raw_line[:-1] if raw_line.endswith("\n") else raw_line
            if line.endswith("\r"):
                raise EpisodeError(f"line {line_number} uses CRLF")
            if not line:
                raise EpisodeError(f"line {line_number} is blank")
            if len(line.encode("utf-8")) > max_line_bytes:
                raise EpisodeError(f"line {line_number} exceeds the byte cap")
            parsed = _load_json_object(line, line_number)
            try:
                event = GjcEpisodeEvent.model_validate(parsed)
            except ValidationError as error:
                raise EpisodeError(f"line {line_number} is not a valid event") from error
            if event.jsonl_line() != line:
                raise EpisodeError(f"line {line_number} is not canonical JSON")
            events.append(event)
        try:
            return cls(events=tuple(events))
        except ValidationError as error:
            raise EpisodeError("episode chain is invalid") from error


def _load_json_object(line: str, line_number: int) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EpisodeError(f"line {line_number} has duplicate key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(token: str) -> None:
        raise EpisodeError(f"line {line_number} contains non-finite number {token!r}")

    try:
        parsed = json.loads(
            line,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, EpisodeError) as error:
        raise EpisodeError(f"line {line_number} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise EpisodeError(f"line {line_number} must be a JSON object")
    return parsed


class GjcEpisodeWriter:
    """Append canonical, causally valid events to a caller-owned text stream."""

    def __init__(self, sink: _TextSink, *, max_line_bytes: int = MAX_LINE_BYTES) -> None:
        if not callable(getattr(sink, "write", None)):
            raise TypeError("sink must provide write(text)")
        if not isinstance(max_line_bytes, int) or max_line_bytes < 1:
            raise ValueError("max_line_bytes must be a positive integer")
        self._sink = sink
        self._max_line_bytes = max_line_bytes
        self._episode = GjcEpisode()

    @property
    def episode(self) -> GjcEpisode:
        return self._episode

    def append(self, kind: str, payload: Any, *, parent_seq: int | None = None) -> GjcEpisodeEvent:
        seq = len(self._episode.events) + 1
        if parent_seq is not None and parent_seq not in {event.seq for event in self._episode.events}:
            raise EpisodeError("parent_seq must reference an already appended event")
        record = {
            "schema": EPISODE_SCHEMA,
            "seq": seq,
            "parent_seq": parent_seq,
            "kind": kind,
            "payload": payload,
            "prev_digest": self._episode.last_digest,
        }
        record["digest"] = _digest_record(record)
        try:
            event = GjcEpisodeEvent.model_validate(record)
        except ValidationError as error:
            raise EpisodeError("cannot append an invalid event") from error
        line = event.jsonl_line()
        if len(line.encode("utf-8")) > self._max_line_bytes:
            raise EpisodeError("event exceeds the JSONL byte cap")
        self._sink.write(f"{line}\n")
        self._episode = GjcEpisode(events=(*self._episode.events, event))
        return event
