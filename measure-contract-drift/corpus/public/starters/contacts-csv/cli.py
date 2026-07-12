#!/usr/bin/env python3
"""Runnable baseline for a public development case.

The target operation is recognized but deliberately unimplemented so a fresh
implementation has a stable executable seam and observable failure contract.
A completed implementation emits ``status="completed"``, ``exit_code=0``,
``changed=true``, and the digest of its resulting state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


OPERATIONS = {
    "bookmarks.json": ("bookmarks", ("bookmark", "tag"), 4),
    "config.json": ("config-merge", ("config", "merge"), 3),
    "contacts.json": ("contacts-csv", ("contacts", "import"), 3),
    "expenses.json": ("expense", ("expense", "add"), 4),
    "reminders.json": ("reminder", ("reminder", "add"), 4),
    "todos.json": ("todo", ("todo", "complete"), 3),
}


def _state_file(root: Path) -> tuple[str, Path, tuple[str, ...], int]:
    matches = [
        (case_id, root / name, command, argc)
        for name, (case_id, command, argc) in OPERATIONS.items()
        if (root / name).is_file()
    ]
    if len(matches) != 1:
        raise RuntimeError("starter must contain exactly one known state file")
    return matches[0]


def _emit(
    *,
    case_id: str,
    argv: Sequence[str],
    status: str,
    exit_code: int,
    changed: bool,
    state_file: Path,
) -> None:
    state = state_file.read_bytes()
    print(
        json.dumps(
            {
                "argv": list(argv),
                "case_id": case_id,
                "changed": changed,
                "exit_code": exit_code,
                "schema": "StarterObservation.v1",
                "state_file": state_file.name,
                "state_sha256": hashlib.sha256(state).hexdigest(),
                "status": status,
            },
            sort_keys=True,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    try:
        case_id, state_file, command, argc = _state_file(Path(__file__).resolve().parent)
    except RuntimeError as error:
        print(json.dumps({"error": str(error), "exit_code": 70, "schema": "StarterObservation.v1", "status": "invalid_starter"}, sort_keys=True))
        return 70
    if len(args) != argc or tuple(args[:2]) != command:
        _emit(
            case_id=case_id,
            argv=args,
            status="invalid_invocation",
            exit_code=64,
            changed=False,
            state_file=state_file,
        )
        return 64
    _emit(
        case_id=case_id,
        argv=args,
        status="operation_unimplemented",
        exit_code=3,
        changed=False,
        state_file=state_file,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
