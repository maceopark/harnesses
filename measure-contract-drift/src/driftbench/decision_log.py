"""DecisionLog.v1 parsing and canonical JSONL serialization.

Each line is one strict ``DecisionLog.v1`` record.  The canonical form is UTF-8,
NFC, sorted-key compact JSON, ordered by contiguous ``decision#N`` identifier,
and ends with exactly one LF.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, Self
from unicodedata import is_normalized

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DECISION_ID = re.compile(r"^decision#([1-9][0-9]*)$")


def _nonblank_nfc(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must be nonblank")
    if not is_normalized("NFC", value):
        raise ValueError(f"{field_name} must be NFC-normalized")
    return value


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class DecisionRecord(BaseModel):
    """The only permitted JSON object shape for a DecisionLog.v1 line."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = "DecisionLog.v1"
    id: str = Field(min_length=1)
    decision: str = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _require_version(cls, value: str) -> str:
        if value != "DecisionLog.v1":
            raise ValueError("schema_version must be DecisionLog.v1")
        return value

    @field_validator("id")
    @classmethod
    def _require_decision_id(cls, value: str) -> str:
        _nonblank_nfc(value, "id")
        if _DECISION_ID.fullmatch(value) is None:
            raise ValueError("id must match decision#N for positive integer N")
        return value

    @field_validator("decision")
    @classmethod
    def _require_decision(cls, value: str) -> str:
        return _nonblank_nfc(value, "decision")

    @property
    def ordinal(self) -> int:
        """Positive integer N extracted from the required ``decision#N`` id."""
        match = _DECISION_ID.fullmatch(self.id)
        assert match is not None
        return int(match.group(1))


class DecisionLog(BaseModel):
    """A strictly ordered, contiguous collection of DecisionLog.v1 records."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entries: list[DecisionRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_canonical_ordinals(self) -> Self:
        ordinals = [entry.ordinal for entry in self.entries]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("decision ids must be ordered, unique, and contiguous from decision#1")
        return self

    def to_jsonl(self) -> bytes:
        """Return this log's strict canonical UTF-8 JSONL bytes."""
        return b"".join(
            _canonical_json_bytes(entry.model_dump(mode="json")) + b"\n"
            for entry in self.entries
        )


def _parse_jsonl(raw: bytes) -> list[Mapping[str, Any]]:
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("DecisionLog JSONL must be nonempty and end with LF")
    lines = raw[:-1].split(b"\n")
    if any(not line for line in lines):
        raise ValueError("DecisionLog JSONL must not contain blank lines")

    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            decoded = line.decode("utf-8")
            parsed = json.loads(
                decoded,
                object_pairs_hook=_no_duplicate_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"invalid DecisionLog JSON at line {line_number}") from error
        if not isinstance(parsed, dict):
            raise ValueError(f"DecisionLog line {line_number} must be a JSON object")
        records.append(parsed)
    return records


def validate_decision_log(
    source: DecisionLog | str | bytes | Sequence[Mapping[str, Any]],
) -> DecisionLog:
    """Validate a DecisionLog.v1 source and return its strict model.

    Raw text/bytes are accepted only when they are already canonical JSONL.
    A JSON-compatible sequence is validated structurally and can be rendered via
    :meth:`DecisionLog.to_jsonl`.
    """
    if isinstance(source, DecisionLog):
        return source
    if isinstance(source, str):
        raw = source.encode("utf-8")
        records = _parse_jsonl(raw)
        log = DecisionLog(entries=list(records))
        if log.to_jsonl() != raw:
            raise ValueError("DecisionLog JSONL is not canonical")
        return log
    if isinstance(source, bytes):
        records = _parse_jsonl(source)
        log = DecisionLog(entries=list(records))
        if log.to_jsonl() != source:
            raise ValueError("DecisionLog JSONL is not canonical")
        return log
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        if any(not isinstance(record, Mapping) for record in source):
            raise TypeError("DecisionLog records must be JSON objects")
        return DecisionLog(entries=list(source))
    raise TypeError("DecisionLog source must be canonical JSONL or a record sequence")


def canonical_decision_jsonl(
    source: DecisionLog | str | bytes | Sequence[Mapping[str, Any]],
) -> bytes:
    """Validate ``source`` and return its canonical DecisionLog.v1 JSONL bytes."""
    return validate_decision_log(source).to_jsonl()
