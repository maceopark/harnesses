#!/usr/bin/env python3
"""Tests for the deterministic material-decision projection gate."""

from __future__ import annotations

import copy
import json

import pytest

from authority_compiler import (
    acceptance_binding_digest,
    compile_discovery_record,
    reconcile_authority_register,
)
from projection_check import (
    LEGACY_MANIFEST_SCHEMA,
    MANIFEST_SCHEMA,
    ProjectionError,
    parse_execution_contract,
    validate_projection,
)
from test_authority_compiler import authority_reconciliation, valid_record


def _compile(record: dict) -> tuple[dict, dict]:
    register = reconcile_authority_register(authority_reconciliation(record))
    record["authority_register_digest"] = register["authority_register_digest"]
    return register, compile_discovery_record(record, register)


def _decision(
    *,
    identifier: str = "DEC-001",
    statement: str = "no-network",
    authority_ref: str = "A-owner",
    requirement_ref: str = "R-list",
    choice: str = "explicit",
) -> dict:
    return {
        "id": identifier,
        "statement": statement,
        "choice": choice,
        "authority_ref": authority_ref,
        "requirement_ref": requirement_ref,
        "applicable_boundary": ["todo-cli"],
        "acceptance_refs": ["P-list"],
        "verification_refs": ["V-list"],
    }


def _contract(*decisions: dict, schema: str = LEGACY_MANIFEST_SCHEMA) -> str:
    manifest = {
        "schema": schema,
        "decisions": list(decisions or (_decision(),)),
    }
    return (
        "# Execution Contract\n\n"
        "## Outcome & Boundaries\n\nLocal task CLI.\n\n"
        "## Decisions & Defaults\n\n"
        "```ultimateinterview-material-decisions\n"
        + json.dumps(manifest, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "## Acceptance\n\nP-list.\n\n"
        "## Verification\n\nV-list.\n"
    )


def _fixture() -> tuple[str, dict, dict, dict]:
    record = valid_record()
    register, build = _compile(record)
    return _contract(), record, register, build


def test_projection_gate_accepts_complete_material_lineage() -> None:
    execution_contract, discovery, register, build = _fixture()

    result = validate_projection(execution_contract, discovery, register, build)

    assert result["decision_ids"] == ["DEC-001"]
    assert result["decision_requirements"] == {"DEC-001": "R-list"}
    assert result["legacy_shared_requirements"] == []
    assert result["contract_digest"] == build["contract_digest"]
    assert len(result["manifest_digest"]) == 64


def test_v2_accepts_one_atomic_decision_per_requirement() -> None:
    record = valid_record()
    record["authorities"][0]["preserved_behaviors"] = ["no-network"]
    for clause in (
        record["goal"],
        *record["scope"],
        *record["non_goals"],
        *record["requirements"],
    ):
        clause["preserved_behaviors"] = ["no-network"]
    record["requirements"][0]["acceptance_bindings"][0]["digest"] = (
        acceptance_binding_digest(
            record["requirements"][0], record["acceptance_predicates"][0]
        )
    )
    register, build = _compile(record)

    result = validate_projection(
        _contract(schema=MANIFEST_SCHEMA), record, register, build
    )

    assert result["schema"] == MANIFEST_SCHEMA


def test_v2_rejects_multiple_decisions_for_one_requirement() -> None:
    second = _decision(
        identifier="DEC-002",
        statement="Existing local task data remains local.",
    )

    with pytest.raises(ProjectionError, match="NON_ATOMIC_REQUIREMENT"):
        parse_execution_contract(
            _contract(_decision(), second, schema=MANIFEST_SCHEMA)
        )


def test_v2_rejects_hidden_requirement_obligation() -> None:
    execution_contract, discovery, register, build = _fixture()

    with pytest.raises(ProjectionError, match="NON_ATOMIC_REQUIREMENT"):
        validate_projection(
            execution_contract.replace(LEGACY_MANIFEST_SCHEMA, MANIFEST_SCHEMA),
            discovery,
            register,
            build,
        )


def test_v1_preserves_legacy_many_decisions_one_requirement() -> None:
    execution_contract, discovery, register, build = _fixture()
    second = _decision(
        identifier="DEC-002",
        statement="Existing local task data remains local.",
    )

    result = validate_projection(
        _contract(_decision(), second), discovery, register, build
    )

    assert result["schema"] == LEGACY_MANIFEST_SCHEMA
    assert result["decision_ids"] == ["DEC-001", "DEC-002"]
    assert result["legacy_shared_requirements"] == ["R-list"]


def test_projection_gate_rejects_decision_lost_from_compiler_inputs() -> None:
    execution_contract, discovery, _, _ = _fixture()
    discovery["authorities"][0]["constraints"] = ["local-only"]
    discovery["goal"]["constraints"] = ["local-only"]
    discovery["scope"][0]["constraints"] = ["local-only"]
    discovery["non_goals"][0]["constraints"] = ["local-only"]
    discovery["requirements"][0]["constraints"] = ["local-only"]
    discovery["requirements"][0]["acceptance_bindings"][0]["digest"] = (
        acceptance_binding_digest(
            discovery["requirements"][0], discovery["acceptance_predicates"][0]
        )
    )
    register, build = _compile(discovery)

    with pytest.raises(ProjectionError, match="DECISION_LOST_FROM_AUTHORITY"):
        validate_projection(execution_contract, discovery, register, build)


def test_projection_gate_rejects_unmapped_requirement_authority_pair() -> None:
    execution_contract, discovery, register, build = _fixture()
    manifest = parse_execution_contract(execution_contract)
    manifest["decisions"] = [_decision(authority_ref="A-implementer", choice="delegated-default")]
    execution_contract = _contract(*manifest["decisions"])

    with pytest.raises(ProjectionError, match="MISSING_AUTHORITY_PROJECTION|UNMAPPED_MATERIAL_DECISION"):
        validate_projection(execution_contract, discovery, register, build)


def test_projection_gate_rejects_acceptance_or_boundary_drift() -> None:
    execution_contract, discovery, register, build = _fixture()
    bad_acceptance = _decision()
    bad_acceptance["acceptance_refs"] = ["P-other"]
    with pytest.raises(ProjectionError, match="ACCEPTANCE_PROJECTION_MISMATCH"):
        validate_projection(_contract(bad_acceptance), discovery, register, build)

    bad_boundary = _decision()
    bad_boundary["applicable_boundary"] = ["other-cli"]
    with pytest.raises(ProjectionError, match="BOUNDARY_PROJECTION_MISMATCH"):
        validate_projection(_contract(bad_boundary), discovery, register, build)


def test_projection_gate_rejects_choice_authority_mismatch_and_contract_drift() -> None:
    execution_contract, discovery, register, build = _fixture()
    delegated = _decision(choice="delegated-default")
    with pytest.raises(ProjectionError, match="CHOICE_AUTHORITY_MISMATCH"):
        validate_projection(_contract(delegated), discovery, register, build)

    tampered = copy.deepcopy(build)
    tampered["goal"]["text"] = "Tampered goal."
    with pytest.raises(ProjectionError, match="BUILD_CONTRACT_DRIFT"):
        validate_projection(execution_contract, discovery, register, tampered)


def test_manifest_parser_is_closed_and_requires_one_stable_decision_block() -> None:
    duplicate = _contract(_decision(), _decision())
    with pytest.raises(ProjectionError, match="DUPLICATE_ID"):
        parse_execution_contract(duplicate)

    unknown = _decision()
    unknown["comment"] = "not allowed"
    with pytest.raises(ProjectionError, match="UNKNOWN_FIELD"):
        parse_execution_contract(_contract(unknown))

    with pytest.raises(ProjectionError, match="MISSING_DECISION_MANIFEST"):
        parse_execution_contract("## Decisions & Defaults\n\n## Acceptance\n")

    with pytest.raises(ProjectionError, match="UNSTRUCTURED_MATERIAL_DECISION"):
        parse_execution_contract(
            _contract().replace(
                "## Decisions & Defaults\n\n",
                "## Decisions & Defaults\n\nAn extra prose decision.\n\n",
            )
        )
