#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import implementation_gate


def test_v1_decision_log_instruction_requires_affirmative_semantics() -> None:
    # Given
    valid = "Append every unforced decision to `.ultimateinterview/demo/decisions.jsonl`."
    negated = "Do not append decisions to `.ultimateinterview/demo/decisions.jsonl`."
    filename_only = "Decision log: `.ultimateinterview/demo/decisions.jsonl`."

    # When / Then
    assert implementation_gate.has_decision_log_instruction(valid, schema_version=1)
    assert not implementation_gate.has_decision_log_instruction(negated, schema_version=1)
    assert not implementation_gate.has_decision_log_instruction(filename_only, schema_version=1)


def test_v0_decision_log_instruction_remains_filename_compatible() -> None:
    # Given
    legacy = "Decision log is decisions.jsonl."

    # When / Then
    assert implementation_gate.has_decision_log_instruction(legacy, schema_version=0)
