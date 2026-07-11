#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verification_contract


PART1 = """# Part 1 - Build Contract

## Verification Commands

| Check | Kind | Command / action | Pass condition |
| --- | --- | --- | --- |
| Unit suite | test | `python -m pytest` | passes |
| Live walkthrough | real-surface | `tmp=$(mktemp -d) && python todo.py` | renders output |
| Error matrix | prose | Run malformed id, nonexistent id, and extra args. | each exits 2 |
| Chain | other | `alpha --check && beta --check` | both run |
"""


def test_parse_rows_preserves_kind_heads_and_table_order() -> None:
    rows = verification_contract.parse_verification_rows(PART1)

    assert [row.row_number for row in rows] == [1, 2, 3, 4]
    assert rows[0].kind == "test"
    assert rows[0].effective_heads == ("python",)
    assert rows[0].is_command_row is True
    assert rows[1].kind == "real-surface"
    assert rows[1].effective_heads == ("mktemp", "python")
    assert rows[1].is_command_row is True
    assert rows[2].kind == "prose"
    assert rows[2].effective_heads == ()
    assert rows[2].is_command_row is False
    assert rows[3].effective_heads == ("alpha", "beta")


def test_command_digest_normalizes_formatting_but_not_commands() -> None:
    digest = verification_contract.canonical_command_digest(
        " `python   -m pytest`   (source: g1) "
    )

    assert digest == verification_contract.canonical_command_digest("python -m pytest")
    assert digest != verification_contract.canonical_command_digest("python -m unittest")


def test_row_identity_uses_one_based_row_and_displayed_check() -> None:
    row = verification_contract.parse_verification_rows(PART1)[1]

    assert verification_contract.row_identity(row) == (2, "Live walkthrough")


def test_effective_heads_returns_sorted_unique_heads() -> None:
    assert verification_contract.effective_heads("`beta --check && alpha --check && beta --again`") == (
        "alpha",
        "beta",
    )
