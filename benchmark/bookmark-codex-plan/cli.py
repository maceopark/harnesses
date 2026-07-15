#!/usr/bin/env python3
"""Local bookmark tagging CLI with a machine-readable observation contract."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, NoReturn


STORE_PATH = Path(__file__).resolve().with_name("bookmarks.json")
OBSERVATION_SCHEMA = "StarterObservation.v1"


class CliFailure(Exception):
    """An expected, machine-reportable CLI failure."""

    def __init__(self, code: str, message: str, state_digest: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.state_digest = state_digest


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_store(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("the top-level JSON value must be an array")

    seen_ids: set[str] = set()
    for index, bookmark in enumerate(value):
        if not isinstance(bookmark, dict):
            raise ValueError(f"bookmark at index {index} must be an object")
        for field in ("id", "url", "title"):
            if not isinstance(bookmark.get(field), str):
                raise ValueError(
                    f"bookmark at index {index} must have a string {field!r}"
                )
        bookmark_id = bookmark["id"]
        if bookmark_id in seen_ids:
            raise ValueError(f"duplicate bookmark id {bookmark_id!r}")
        seen_ids.add(bookmark_id)

        if "tags" in bookmark:
            tags = bookmark["tags"]
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) for tag in tags
            ):
                raise ValueError(
                    f"bookmark at index {index} must have a string-array 'tags'"
                )

    return value


def load_store() -> tuple[list[dict[str, Any]], bytes, str]:
    try:
        content = STORE_PATH.read_bytes()
    except FileNotFoundError as exc:
        raise CliFailure(
            "STORE_NOT_FOUND", f"bookmark store not found: {STORE_PATH.name}"
        ) from exc
    except OSError as exc:
        raise CliFailure(
            "INVALID_STORE", f"bookmark store could not be read: {exc}"
        ) from exc

    try:
        parsed = json.loads(content)
        bookmarks = validate_store(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CliFailure("INVALID_STORE", f"invalid bookmark store: {exc}") from exc

    return bookmarks, content, digest_bytes(content)


def current_valid_digest() -> str | None:
    try:
        _, _, state_digest = load_store()
    except CliFailure:
        return None
    return state_digest


def serialize_store(bookmarks: list[dict[str, Any]]) -> bytes:
    return (json.dumps(bookmarks, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def replace_store(content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(
            prefix=".bookmarks.", suffix=".tmp", dir=STORE_PATH.parent
        )
        temporary_path = Path(raw_path)
        if STORE_PATH.exists():
            os.chmod(temporary_path, stat.S_IMODE(STORE_PATH.stat().st_mode))
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, STORE_PATH)
        temporary_path = None
    except OSError as exc:
        raise CliFailure(
            "WRITE_FAILED",
            f"bookmark store could not be written: {exc}",
            current_valid_digest(),
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def add_tag(bookmark_id: str, tag: str) -> tuple[bool, str]:
    bookmarks, _, original_digest = load_store()

    target = next(
        (bookmark for bookmark in bookmarks if bookmark["id"] == bookmark_id), None
    )
    if target is None:
        raise CliFailure(
            "UNKNOWN_BOOKMARK_ID",
            f"unknown bookmark id: {bookmark_id}",
            original_digest,
        )

    tags = target.get("tags")
    if tags is not None and tag in tags:
        return False, original_digest

    if tags is None:
        tags = []
        target["tags"] = tags
    tags.append(tag)

    serialized = serialize_store(bookmarks)
    replace_store(serialized)
    return True, digest_bytes(serialized)


def emit(observation: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(observation, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    sys.stdout.flush()


def fail(failure: CliFailure) -> NoReturn:
    emit(
        {
            "schema": OBSERVATION_SCHEMA,
            "status": "failed",
            "exit_code": 1,
            "changed": False,
            "state_digest": failure.state_digest,
            "error": {"code": failure.code, "message": failure.message},
        }
    )
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 4 or arguments[:2] != ["bookmark", "tag"]:
            raise CliFailure(
                "INVALID_COMMAND",
                "usage: python cli.py bookmark tag ID TAG",
                current_valid_digest(),
            )

        bookmark_id, tag = arguments[2:]
        if tag == "":
            raise CliFailure(
                "EMPTY_TAG", "TAG must not be empty", current_valid_digest()
            )

        changed, state_digest = add_tag(bookmark_id, tag)
    except CliFailure as failure:
        fail(failure)
    except Exception as exc:  # Keep the stdout protocol intact for unexpected failures.
        fail(
            CliFailure(
                "WRITE_FAILED",
                f"unexpected local operation failure: {exc}",
                current_valid_digest(),
            )
        )

    emit(
        {
            "schema": OBSERVATION_SCHEMA,
            "status": "completed",
            "exit_code": 0,
            "changed": changed,
            "state_digest": state_digest,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
