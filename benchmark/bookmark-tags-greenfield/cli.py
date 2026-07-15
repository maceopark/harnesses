#!/usr/bin/env python3
"""Deterministic, local-only bookmark tagging command."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, NoReturn


STORE_PATH = Path(__file__).resolve().with_name("bookmarks.json")
OBSERVATION_SCHEMA = "StarterObservation.v1"
OBSERVATION_KEYS = {
    "schema",
    "status",
    "exit_code",
    "changed",
    "state_digest",
}


class OperationFailure(Exception):
    """A failure that can be represented by StarterObservation.v1."""

    def __init__(self, state_digest: str | None = None):
        super().__init__()
        self.state_digest = state_digest


def canonical_bytes(state: Any) -> bytes:
    """Serialize parsed state exactly as required by the digest contract."""
    return json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def state_digest(state: Any) -> str:
    return hashlib.sha256(canonical_bytes(state)).hexdigest()


def reject_nonstandard_number(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON number: {value}")


def validate_state(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("bookmark state must be an array")

    seen_ids: set[str] = set()
    for bookmark in value:
        if not isinstance(bookmark, dict):
            raise ValueError("each bookmark must be an object")
        if not isinstance(bookmark.get("id"), str):
            raise ValueError("each bookmark must have a string id")
        if bookmark["id"] in seen_ids:
            raise ValueError("bookmark ids must be unique")
        seen_ids.add(bookmark["id"])

        if "tags" in bookmark:
            tags = bookmark["tags"]
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) for tag in tags
            ):
                raise ValueError("tags must be an array of strings")

    # json.loads returns the input list, but this annotation narrows the validated shape.
    return value


def load_state() -> tuple[list[dict[str, Any]], str]:
    try:
        text = STORE_PATH.read_text(encoding="utf-8")
        parsed = json.loads(text, parse_constant=reject_nonstandard_number)
        state = validate_state(parsed)
        digest = state_digest(state)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise OperationFailure() from exc
    return state, digest


def current_digest() -> str | None:
    try:
        _, digest = load_state()
    except OperationFailure:
        return None
    return digest


def persisted_bytes(state: list[dict[str, Any]]) -> bytes:
    """Keep the store readable; its formatting is intentionally not digest input."""
    return (json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def persist_state(state: list[dict[str, Any]], original_digest: str) -> None:
    temporary_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            dir=STORE_PATH.parent,
            prefix=".bookmarks.",
            suffix=".tmp",
        )
        temporary_path = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(persisted_bytes(state))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, STORE_PATH)
        temporary_path = None
    except (OSError, TypeError, ValueError) as exc:
        raise OperationFailure(original_digest) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def add_tag(bookmark_id: str, tag: str) -> str:
    state, original_digest = load_state()

    if tag == "":
        raise OperationFailure(original_digest)

    target = next(
        (bookmark for bookmark in state if bookmark["id"] == bookmark_id),
        None,
    )
    if target is None:
        raise OperationFailure(original_digest)

    tags = target.get("tags")
    if tags is not None and tag in tags:
        raise OperationFailure(original_digest)

    if tags is None:
        tags = []
        target["tags"] = tags
    tags.append(tag)

    resulting_digest = state_digest(state)
    persist_state(state, original_digest)
    return resulting_digest


def observation(
    *, status: str, exit_code: int, changed: bool, digest: str | None
) -> dict[str, Any]:
    value = {
        "schema": OBSERVATION_SCHEMA,
        "status": status,
        "exit_code": exit_code,
        "changed": changed,
        "state_digest": digest,
    }
    assert set(value) == OBSERVATION_KEYS
    return value


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 4 or arguments[:2] != ["bookmark", "tag"]:
            raise OperationFailure(current_digest())
        digest = add_tag(arguments[2], arguments[3])
    except OperationFailure as failure:
        emit(
            observation(
                status="failed",
                exit_code=1,
                changed=False,
                digest=failure.state_digest,
            )
        )
        return 1
    except Exception:
        # Preserve the one-object protocol even for an unexpected local failure.
        emit(
            observation(
                status="failed",
                exit_code=1,
                changed=False,
                digest=current_digest(),
            )
        )
        return 1

    emit(
        observation(
            status="completed",
            exit_code=0,
            changed=True,
            digest=digest,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
