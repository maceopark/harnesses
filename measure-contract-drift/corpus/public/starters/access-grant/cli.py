#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

CASE_ID = "access-grant"
STATE_FILE = "access.json"
TARGET = ("access", "grant")
TARGET_ARGC = 4


def emit(argv: Sequence[str], status: str, exit_code: int, changed: bool) -> None:
    path = Path(__file__).with_name(STATE_FILE)
    print(json.dumps({"argv": list(argv), "case_id": CASE_ID, "changed": changed,
        "exit_code": exit_code, "schema": "StarterObservation.v1", "state_file": STATE_FILE,
        "state_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "status": status}, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args == ["state", "show"]:
        emit(args, "observed", 0, False)
        return 0
    if len(args) == TARGET_ARGC and tuple(args[:2]) == TARGET:
        emit(args, "operation_unimplemented", 3, False)
        return 3
    emit(args, "invalid_invocation", 64, False)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
