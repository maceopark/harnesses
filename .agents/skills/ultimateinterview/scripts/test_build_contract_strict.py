#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_contract
from scripts.build_contract_schema import BuildContract, ContractBody, DecisionBoundary, QualityBar
from scripts.test_build_contract import handoff


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (QualityBar, {"attribute": "latency", "measurable_bar": "100 ms", "weight": True, "verification": "VER-001"}),
        (DecisionBoundary, {"decision": "naming", "agent_may_decide": "false", "boundary": "public API"}),
    ],
)
def test_nested_models_reject_python_coercion(model: type[QualityBar] | type[DecisionBoundary], payload: dict[str, str | bool]) -> None:
    # Given a coercible but incorrectly typed Python payload
    # When a public nested model parses it, Then strict validation rejects it
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_contract_body_rejects_boolean_schema_version() -> None:
    # Given a valid body payload with bool substituted for integer schema version
    payload = build_contract.compile_handoff(handoff()).model_dump(exclude={"contract_digest"})
    payload["schema_version"] = True

    # When the public contract boundary parses it, Then strict validation rejects it
    with pytest.raises(ValidationError):
        ContractBody.model_validate(payload)


@pytest.mark.parametrize(
    "decision_log_path",
    [
        ".ultimateinterview/../decisions.jsonl",
        ".ultimateinterview/bad\\slug/decisions.jsonl",
        ".ultimateinterview/\u202eslug/decisions.jsonl",
    ],
)
def test_contract_body_rejects_unsafe_decision_log_path(decision_log_path: str) -> None:
    # Given an escaping or control-bearing decision-log path
    payload = build_contract.compile_handoff(handoff()).model_dump(exclude={"contract_digest"})
    payload["decision_log_path"] = decision_log_path

    # When the public contract boundary parses it, Then path validation rejects it
    with pytest.raises(ValidationError):
        ContractBody.model_validate(payload)


def test_strict_contract_still_round_trips_valid_json_types() -> None:
    # Given a canonical contract containing JSON strings, numbers, and booleans
    contract = build_contract.compile_handoff(handoff())

    # When parsed from its real JSON representation, Then valid typed data survives
    assert BuildContract.model_validate_json(build_contract.canonical_json(contract)) == contract


def test_json_loaded_lists_normalize_to_contract_tuples() -> None:
    # Given canonical JSON loaded into ordinary Python lists and scalar values
    contract = build_contract.compile_handoff(handoff())
    payload = json.loads(build_contract.canonical_json(contract))

    # When parsed through the Python mapping boundary, Then lists normalize without scalar coercion
    assert BuildContract.model_validate(payload) == contract


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
