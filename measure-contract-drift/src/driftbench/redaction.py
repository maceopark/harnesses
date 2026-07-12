"""Recursive public-output redaction and sentinel-leak detection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from typing import Any, TypeAlias


REDACTION_MARKER = "<redacted>"
"""The replacement used for every secret occurrence, including mapping keys."""

JsonPathPart: TypeAlias = str | int


class RedactionError(ValueError):
    """Raised when a value cannot be safely redacted or scanned."""


@dataclass(frozen=True, slots=True)
class SentinelLeak:
    """One sentinel occurrence and its JSON-like location."""

    path: tuple[JsonPathPart, ...]
    sentinel: str


def _normalize_tokens(tokens: Iterable[str] | str, *, noun: str) -> tuple[str, ...]:
    if isinstance(tokens, str):
        candidates = (tokens,)
    else:
        try:
            candidates = tuple(tokens)
        except TypeError as error:
            raise RedactionError(f"{noun} must be a string or iterable of strings") from error
    if any(not isinstance(token, str) or not token for token in candidates):
        raise RedactionError(f"{noun} must contain only non-empty strings")
    return tuple(sorted(set(candidates), key=lambda token: (-len(token), token)))


def _replace_text(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        value = value.replace(secret, REDACTION_MARKER)
    return value


def _replace_bytes(value: bytes, secrets: tuple[str, ...]) -> bytes:
    for secret in secrets:
        value = value.replace(secret.encode("utf-8"), REDACTION_MARKER.encode("ascii"))
    return value


def redact(value: Any, secrets: Iterable[str] | str) -> Any:
    """Recursively replace every exact secret substring in JSON-like data.

    Mapping keys are redacted as well as values.  This is intentional: a public
    serializer can expose a key just as readily as a leaf value.  Ambiguous key
    collisions and non-JSON-like values fail closed instead of being stringified.
    """

    normalized_secrets = _normalize_tokens(secrets, noun="secrets")
    active: set[int] = set()

    def visit(current: Any) -> Any:
        if isinstance(current, str):
            return _replace_text(current, normalized_secrets)
        if isinstance(current, bytes):
            return _replace_bytes(current, normalized_secrets)
        if current is None or isinstance(current, bool | int):
            return current
        if isinstance(current, float):
            if not math.isfinite(current):
                raise RedactionError("non-finite float is not public-safe")
            return current
        if isinstance(current, Mapping):
            object_id = id(current)
            if object_id in active:
                raise RedactionError("cyclic mapping cannot be redacted")
            active.add(object_id)
            try:
                redacted: dict[str, Any] = {}
                for key, item in current.items():
                    if not isinstance(key, str):
                        raise RedactionError("mapping keys must be strings")
                    replacement_key = _replace_text(key, normalized_secrets)
                    if replacement_key in redacted:
                        raise RedactionError("redaction would create duplicate mapping keys")
                    redacted[replacement_key] = visit(item)
                return redacted
            finally:
                active.remove(object_id)
        if isinstance(current, list):
            object_id = id(current)
            if object_id in active:
                raise RedactionError("cyclic list cannot be redacted")
            active.add(object_id)
            try:
                return [visit(item) for item in current]
            finally:
                active.remove(object_id)
        if isinstance(current, tuple):
            object_id = id(current)
            if object_id in active:
                raise RedactionError("cyclic tuple cannot be redacted")
            active.add(object_id)
            try:
                return tuple(visit(item) for item in current)
            finally:
                active.remove(object_id)
        raise RedactionError(f"unsupported public value type: {type(current).__name__}")

    return visit(value)


def scan_sentinels(value: Any, sentinels: Iterable[str] | str) -> tuple[SentinelLeak, ...]:
    """Return every supplied sentinel that remains in a JSON-like value.

    The function deliberately does not redact.  Callers can scan before export to
    block leaks and scan a redacted copy to prove that redaction removed them.
    """

    normalized_sentinels = _normalize_tokens(sentinels, noun="sentinels")
    leaks: list[SentinelLeak] = []
    active: set[int] = set()

    def scan_text(text: str, path: tuple[JsonPathPart, ...]) -> None:
        for sentinel in normalized_sentinels:
            if sentinel in text:
                leaks.append(SentinelLeak(path=path, sentinel=sentinel))

    def visit(current: Any, path: tuple[JsonPathPart, ...]) -> None:
        if isinstance(current, str):
            scan_text(current, path)
            return
        if isinstance(current, bytes):
            for sentinel in normalized_sentinels:
                if sentinel.encode("utf-8") in current:
                    leaks.append(SentinelLeak(path=path, sentinel=sentinel))
            return
        if current is None or isinstance(current, bool | int | float):
            return
        if isinstance(current, Mapping):
            object_id = id(current)
            if object_id in active:
                raise RedactionError("cyclic mapping cannot be scanned")
            active.add(object_id)
            try:
                for key, item in current.items():
                    if not isinstance(key, str):
                        raise RedactionError("mapping keys must be strings")
                    scan_text(key, path + ("<key>",))
                    visit(item, path + (key,))
            finally:
                active.remove(object_id)
            return
        if isinstance(current, list | tuple):
            object_id = id(current)
            if object_id in active:
                raise RedactionError("cyclic sequence cannot be scanned")
            active.add(object_id)
            try:
                for index, item in enumerate(current):
                    visit(item, path + (index,))
            finally:
                active.remove(object_id)
            return
        raise RedactionError(f"unsupported public value type: {type(current).__name__}")

    visit(value, ())
    return tuple(leaks)
