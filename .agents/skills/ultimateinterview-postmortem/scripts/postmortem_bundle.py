#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

import json
from pathlib import Path
from typing import assert_never

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _read(path: Path) -> dict[str, JsonValue] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def artifact_ids(path: Path) -> frozenset[str]:
    return _artifact_values(path, "id")


def _artifact_values(path: Path, field: str) -> frozenset[str]:
    data = _read(path)
    if data is None:
        return frozenset()
    match data.get("artifacts"):
        case dict() as artifacts:
            match artifacts.get("files"):
                case list() as files:
                    values: set[str] = set()
                    for item in files:
                        match item:
                            case dict() as record:
                                match record.get(field):
                                    case str() as value:
                                        values.add(value)
                                    case None | bool() | int() | float() | list() | dict():
                                        continue
                                    case unreachable:
                                        assert_never(unreachable)
                            case None | bool() | int() | float() | str() | list():
                                continue
                            case unreachable:
                                assert_never(unreachable)
                    return frozenset(values)
                case None | bool() | int() | float() | str() | dict():
                    return frozenset()
                case unreachable:
                    assert_never(unreachable)
        case None | bool() | int() | float() | str() | list():
            return frozenset()
        case unreachable:
            assert_never(unreachable)


def missing_evidence(path: Path) -> tuple[str, ...]:
    data = _read(path)
    if data is None:
        return ()
    match data.get("missing_evidence"):
        case list() as values:
            missing: list[str] = []
            for value in values:
                match value:
                    case str() as item:
                        missing.append(item)
                    case None | bool() | int() | float() | list() | dict():
                        continue
                    case unreachable:
                        assert_never(unreachable)
            return tuple(missing)
        case None | bool() | int() | float() | str() | dict():
            return ()
        case unreachable:
            assert_never(unreachable)


def artifact_kinds(path: Path) -> frozenset[str]:
    return _artifact_values(path, "kind")
