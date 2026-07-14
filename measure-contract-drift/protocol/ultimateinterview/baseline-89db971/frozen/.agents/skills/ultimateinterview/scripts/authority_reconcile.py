#!/usr/bin/env python3
"""Seal an owner-approved Ultimateinterview Authority Register."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from authority_compiler import (
    CompilerError,
    _atomic_write,
    _strict_json_loads,
    pretty_json,
    reconcile_authority_register,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="authority_reconcile.py",
        description="Reconcile an owner-approved Authority Register before Discovery.",
    )
    parser.add_argument("reconciliation", type=Path, help="Authority reconciliation input JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Authority Register JSON output file")
    arguments = parser.parse_args(argv)

    try:
        if not arguments.reconciliation.is_file():
            raise CompilerError("INPUT_ERROR", str(arguments.reconciliation), "input is not a file")
        try:
            input_text = arguments.reconciliation.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise CompilerError("INPUT_ERROR", str(arguments.reconciliation), f"could not read input: {error}") from error
        register = reconcile_authority_register(_strict_json_loads(input_text))
        _atomic_write(arguments.output, pretty_json(register))
    except CompilerError as error:
        print(f"authority-reconcile: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
