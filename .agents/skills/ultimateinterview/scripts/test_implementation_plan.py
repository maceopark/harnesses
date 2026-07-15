#!/usr/bin/env python3
"""Tests for contract-bound implementation plan compilation."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from implementation_plan import (
    PlanError,
    compile_implementation_plan,
    plan_digest,
    validate_implementation_plan,
)
from test_authority_compiler import compile_record, valid_record


SCRIPT = Path(__file__).with_name("implementation_plan.py")


def _contract() -> dict:
    return compile_record(valid_record())


def _draft(contract: dict) -> dict:
    return {
        "schema": "ultimateinterview.implementation-plan-draft.v1",
        "contract_digest": contract["contract_digest"],
        "approach": {
            "summary": "Add a local command handler and repository-backed scenario test.",
            "rationale": "It realizes the local-only contract with the smallest repository change.",
        },
        "decisions": [
            {
                "id": "IMP-001",
                "statement": "Keep the command and storage changes inside the todo CLI component.",
                "delegation_ref": "A-implementer",
                "requirement_refs": ["R-list"],
                "acceptance_refs": ["P-list"],
                "verification_refs": ["V-list"],
                "affected_surfaces": ["todo-cli", "tests/test_todo.py"],
                "rationale": "The active delegation permits local module and test organization.",
                "alternatives": ["Split persistence into another local module."],
                "observable_impact": "none beyond the Build Contract",
            }
        ],
        "steps": [
            {
                "id": "STEP-001",
                "summary": "Implement and verify local task listing.",
                "depends_on": [],
                "decision_refs": ["IMP-001"],
                "requirement_refs": ["R-list"],
                "acceptance_refs": ["P-list"],
                "verification_refs": ["V-list"],
                "affected_surfaces": ["todo-cli", "tests/test_todo.py"],
            }
        ],
        "test_realization": [
            {
                "verification_ref": "V-list",
                "working_directory": "repository root",
                "target": "tests/test_todo.py",
                "procedure": "Run the isolated create-then-list scenario against a temporary store.",
                "expected_result": "The command shows alpha exactly once.",
            }
        ],
        "return_to_owner_conditions": [
            "observable behavior not authorized by the Build Contract",
            "required work outside an applicable bounded delegation",
            "a verification cannot objectively determine its acceptance predicate",
            "the recommended approach is infeasible without changing the Build Contract",
        ],
    }


def test_compiles_complete_agent_agnostic_plan() -> None:
    contract = _contract()

    plan = compile_implementation_plan(_draft(contract), contract)

    assert plan["schema"] == "ultimateinterview.implementation-plan.v1"
    assert plan["contract_digest"] == contract["contract_digest"]
    assert plan["plan_digest"] == plan_digest(plan)
    assert [row["id"] for row in plan["decisions"]] == ["IMP-001"]
    assert [row["id"] for row in plan["steps"]] == ["STEP-001"]
    assert validate_implementation_plan(plan, contract) == plan


def test_compiled_plan_rejects_digest_tampering() -> None:
    contract = _contract()
    plan = compile_implementation_plan(_draft(contract), contract)
    plan["approach"]["summary"] = "Tampered approach."

    with pytest.raises(PlanError) as raised:
        validate_implementation_plan(plan, contract)

    assert raised.value.code == "PLAN_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda draft: draft.update(contract_digest="0" * 64),
            "CONTRACT_DIGEST_MISMATCH",
        ),
        (
            lambda draft: draft["decisions"][0].update(delegation_ref="A-owner"),
            "UNKNOWN_DELEGATION",
        ),
        (
            lambda draft: draft["decisions"][0].update(
                observable_impact="new retry behavior"
            ),
            "UNAUTHORIZED_OBSERVABLE_IMPACT",
        ),
        (
            lambda draft: draft["steps"][0].update(requirement_refs=["R-unknown"]),
            "UNKNOWN_REFERENCE",
        ),
        (
            lambda draft: draft["test_realization"][0].update(
                expected_result="Something else."
            ),
            "EXPECTED_RESULT_MISMATCH",
        ),
        (
            lambda draft: draft.update(return_to_owner_conditions=["continue anyway"]),
            "RETURN_BOUNDARY_MISMATCH",
        ),
    ],
)
def test_rejects_unbound_invented_or_incomplete_plan(mutate, code: str) -> None:
    contract = _contract()
    draft = _draft(contract)
    mutate(draft)

    with pytest.raises(PlanError) as raised:
        compile_implementation_plan(draft, contract)

    assert raised.value.code == code


def test_rejects_uncovered_decision_and_cyclic_steps() -> None:
    contract = _contract()
    draft = _draft(contract)
    second = copy.deepcopy(draft["decisions"][0])
    second["id"] = "IMP-002"
    draft["decisions"].append(second)
    with pytest.raises(PlanError) as raised:
        compile_implementation_plan(draft, contract)
    assert raised.value.code == "PLAN_COVERAGE_MISMATCH"

    draft = _draft(contract)
    draft["steps"][0]["depends_on"] = ["STEP-002"]
    second_step = copy.deepcopy(draft["steps"][0])
    second_step["id"] = "STEP-002"
    second_step["depends_on"] = ["STEP-001"]
    draft["steps"].append(second_step)
    with pytest.raises(PlanError) as raised:
        compile_implementation_plan(draft, contract)
    assert raised.value.code == "CYCLIC_DEPENDENCY"


def test_cli_writes_nothing_when_validation_fails() -> None:
    contract = _contract()
    draft = _draft(contract)
    draft["contract_digest"] = "f" * 64
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        draft_path = root / "implementation-plan-draft.json"
        contract_path = root / "build-contract.json"
        output_path = root / "implementation-plan.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(draft_path),
                "--build-contract",
                str(contract_path),
                "--output",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 1
        assert "CONTRACT_DIGEST_MISMATCH" in result.stderr
        assert not output_path.exists()


def test_cli_compiles_and_rechecks_plan() -> None:
    contract = _contract()
    draft = _draft(contract)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        draft_path = root / "implementation-plan-draft.json"
        contract_path = root / "build-contract.json"
        output_path = root / "implementation-plan.json"
        draft_path.write_text(json.dumps(draft), encoding="utf-8")
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        compiled = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(draft_path),
                "--build-contract",
                str(contract_path),
                "--output",
                str(output_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        checked = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(output_path),
                "--build-contract",
                str(contract_path),
                "--check",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        assert compiled.returncode == 0
        assert checked.returncode == 0
        assert "implementation plan valid" in checked.stdout
