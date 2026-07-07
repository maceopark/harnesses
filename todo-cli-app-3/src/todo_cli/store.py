"""Single-JSON-file store: ~/.todo/todos.json.

Store shape: {"items": [item, ...]} where item = {
    "title": str, "pri": "high"|"mid"|"low", "due": "YYYY-MM-DD"|None,
    "memo": str|None, "seq": int, "done_on": "YYYY-MM-DD"|None,
}
Anything that exists but does not parse into this shape is corrupt: refuse, never touch the file
(REQ-010). Missing dir/file is auto-created empty on first run (REQ-009).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

VALID_PRI = ("high", "mid", "low")


class StoreError(Exception):
    """Corrupt store or store I/O failure - caller reports and exits 1."""


def store_path() -> Path:
    return Path.home() / ".todo" / "todos.json"


def _validate(data: Any, path: Path) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise StoreError(f"corrupt store (unexpected shape): {path}")
    for item in data["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("title"), str)
            or item.get("pri") not in VALID_PRI
            or not isinstance(item.get("seq"), int)
        ):
            raise StoreError(f"corrupt store (unexpected item shape): {path}")
    return data


def load() -> dict:
    """Load the store, creating an empty one on first run."""
    path = store_path()
    try:
        if not path.exists():
            data = {"items": []}
            save(data)
            return data
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot access store {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise StoreError(f"corrupt store (invalid JSON): {path}") from exc
    return _validate(data, path)


def save(data: dict) -> None:
    """Atomic write: temp file + rename, so failures never corrupt the store."""
    path = store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".todos-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
    except OSError as exc:
        raise StoreError(f"cannot write store {path}: {exc}") from exc


def next_seq(data: dict) -> int:
    return 1 + max((item["seq"] for item in data["items"]), default=0)
