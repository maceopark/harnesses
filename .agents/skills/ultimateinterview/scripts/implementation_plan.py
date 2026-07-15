#!/usr/bin/env python3
"""Compile a contract-bound, non-normative implementation plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import authority_compiler


DRAFT_SCHEMA = "ultimateinterview.implementation-plan-draft.v1"
PLAN_SCHEMA = "ultimateinterview.implementation-plan.v1"
NO_OBSERVABLE_IMPACT = "none beyond the Build Contract"
RETURN_TO_OWNER_CONDITIONS = (
    "observable behavior not authorized by the Build Contract",
    "required work outside an applicable bounded delegation",
    "a verification cannot objectively determine its acceptance predicate",
    "the recommended approach is infeasible without changing the Build Contract",
)
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_DECISION_ID_PATTERN = re.compile(r"IMP-[0-9]{3}\Z")
_STEP_ID_PATTERN = re.compile(r"STEP-[0-9]{3}\Z")
_SURFACE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
_WILDCARD_PATTERN = re.compile(r"[*?\[\]]")


class PlanError(ValueError):
    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


def _fail(code: str, path: str, detail: str) -> None:
    raise PlanError(code, path, detail)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("INVALID_TYPE", path, "must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_TYPE", path, "must be an array")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INVALID_TEXT", path, "must be a nonempty string")
    return value


def _closed(value: Any, path: str, fields: frozenset[str]) -> dict[str, Any]:
    result = _object(value, path)
    unknown = sorted(set(result) - fields)
    missing = sorted(fields - set(result))
    if unknown:
        _fail("UNKNOWN_FIELD", path, f"unknown field {unknown[0]}")
    if missing:
        _fail("MISSING_FIELD", path, f"missing field {missing[0]}")
    return result


def _strings(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    result = [
        _text(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    ]
    if not allow_empty and not result:
        _fail("INVALID_VALUE", path, "must not be empty")
    if len(set(result)) != len(result):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return result


def _surface(value: Any, path: str) -> str:
    surface = _text(value, path)
    if (
        not _SURFACE_PATTERN.fullmatch(surface)
        or surface.startswith("/")
        or "\\" in surface
        or _WILDCARD_PATTERN.search(surface)
        or any(part in {"", ".", ".."} for part in surface.split("/"))
    ):
        _fail(
            "INVALID_SURFACE",
            path,
            "must be a normalized repository-relative path or stable named component",
        )
    return surface


def _surfaces(value: Any, path: str) -> list[str]:
    result = [
        _surface(item, f"{path}[{index}]")
        for index, item in enumerate(_array(value, path))
    ]
    if not result:
        _fail("INVALID_VALUE", path, "must not be empty")
    if len(set(result)) != len(result):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return result


def _id_map(contract: Mapping[str, Any], field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(_array(contract.get(field), f"contract.{field}")):
        row = _object(value, f"contract.{field}[{index}]")
        identifier = _text(row.get("id"), f"contract.{field}[{index}].id")
        if identifier in result:
            _fail("DUPLICATE_ID", f"contract.{field}", identifier)
        result[identifier] = row
    return result


def _references(value: Any, path: str, known: Mapping[str, Any]) -> list[str]:
    references = _strings(value, path)
    for reference in references:
        if reference not in known:
            _fail("UNKNOWN_REFERENCE", path, reference)
    return references


def _validate_reference_consistency(
    requirement_refs: Sequence[str],
    acceptance_refs: Sequence[str],
    verification_refs: Sequence[str],
    acceptances: Mapping[str, Mapping[str, Any]],
    verifications: Mapping[str, Mapping[str, Any]],
    path: str,
) -> None:
    requirements = set(requirement_refs)
    accepted = set(acceptance_refs)
    for reference in acceptance_refs:
        if acceptances[reference].get("requirement_ref") not in requirements:
            _fail("REFERENCE_MISMATCH", f"{path}.acceptance_refs", reference)
    for reference in verification_refs:
        verification = verifications[reference]
        if verification.get("requirement_ref") not in requirements:
            _fail("REFERENCE_MISMATCH", f"{path}.verification_refs", reference)
        if not set(verification.get("acceptance_refs", [])) <= accepted:
            _fail(
                "REFERENCE_MISMATCH",
                f"{path}.verification_refs",
                f"{reference} cites acceptance outside this row",
            )


def _validate_dag(steps: Sequence[Mapping[str, Any]]) -> None:
    dependencies = {step["id"]: set(step["depends_on"]) for step in steps}
    identifiers = set(dependencies)
    for identifier, refs in dependencies.items():
        unknown = sorted(refs - identifiers)
        if unknown:
            _fail("UNKNOWN_REFERENCE", f"steps.{identifier}.depends_on", unknown[0])
        if identifier in refs:
            _fail("CYCLIC_DEPENDENCY", f"steps.{identifier}.depends_on", identifier)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            _fail("CYCLIC_DEPENDENCY", "$.steps", identifier)
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in dependencies[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in dependencies:
        visit(identifier)


def _validate_contract(contract: Mapping[str, Any]) -> str:
    if contract.get("schema") != authority_compiler.BUILD_CONTRACT_SCHEMA:
        _fail(
            "INVALID_CONTRACT",
            "build-contract.json.schema",
            "invalid Build Contract schema",
        )
    claimed = contract.get("contract_digest")
    if not isinstance(claimed, str) or not _DIGEST_PATTERN.fullmatch(claimed):
        _fail(
            "INVALID_CONTRACT", "build-contract.json.contract_digest", "invalid digest"
        )
    if authority_compiler.contract_digest(contract) != claimed:
        _fail(
            "CONTRACT_DIGEST_MISMATCH",
            "build-contract.json.contract_digest",
            "digest mismatch",
        )
    if contract.get("unresolved_decisions") != []:
        _fail(
            "INVALID_CONTRACT",
            "build-contract.json.unresolved_decisions",
            "must be empty",
        )
    return claimed


def compile_implementation_plan(
    value: Any, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate and compile a derived implementation plan."""

    contract_digest = _validate_contract(contract)
    requirements = _id_map(contract, "requirements")
    acceptances = _id_map(contract, "acceptance_predicates")
    verifications = _id_map(contract, "verifications")
    delegations = _id_map(contract, "bounded_implementation_delegations")
    draft = _closed(
        value,
        "$",
        frozenset(
            {
                "schema",
                "contract_digest",
                "approach",
                "decisions",
                "steps",
                "test_realization",
                "return_to_owner_conditions",
            }
        ),
    )
    if _text(draft["schema"], "$.schema") != DRAFT_SCHEMA:
        _fail("INVALID_SCHEMA", "$.schema", f"must be {DRAFT_SCHEMA}")
    if _text(draft["contract_digest"], "$.contract_digest") != contract_digest:
        _fail(
            "CONTRACT_DIGEST_MISMATCH",
            "$.contract_digest",
            "does not match Build Contract",
        )
    approach = _closed(
        draft["approach"], "$.approach", frozenset({"summary", "rationale"})
    )
    normalized_approach = {
        "summary": _text(approach["summary"], "$.approach.summary"),
        "rationale": _text(approach["rationale"], "$.approach.rationale"),
    }

    decision_fields = frozenset(
        {
            "id",
            "statement",
            "delegation_ref",
            "requirement_refs",
            "acceptance_refs",
            "verification_refs",
            "affected_surfaces",
            "rationale",
            "alternatives",
            "observable_impact",
        }
    )
    decisions: list[dict[str, Any]] = []
    decision_ids: set[str] = set()
    for index, value in enumerate(_array(draft["decisions"], "$.decisions")):
        path = f"$.decisions[{index}]"
        row = _closed(value, path, decision_fields)
        identifier = _text(row["id"], f"{path}.id")
        if not _DECISION_ID_PATTERN.fullmatch(identifier):
            _fail("INVALID_DECISION_ID", f"{path}.id", "must match IMP-NNN")
        if identifier in decision_ids:
            _fail("DUPLICATE_ID", f"{path}.id", identifier)
        decision_ids.add(identifier)
        delegation_ref = _text(row["delegation_ref"], f"{path}.delegation_ref")
        if delegation_ref not in delegations:
            _fail("UNKNOWN_DELEGATION", f"{path}.delegation_ref", delegation_ref)
        requirement_refs = _references(
            row["requirement_refs"], f"{path}.requirement_refs", requirements
        )
        acceptance_refs = _references(
            row["acceptance_refs"], f"{path}.acceptance_refs", acceptances
        )
        verification_refs = _references(
            row["verification_refs"], f"{path}.verification_refs", verifications
        )
        _validate_reference_consistency(
            requirement_refs,
            acceptance_refs,
            verification_refs,
            acceptances,
            verifications,
            path,
        )
        observable_impact = _text(row["observable_impact"], f"{path}.observable_impact")
        if observable_impact != NO_OBSERVABLE_IMPACT:
            _fail(
                "UNAUTHORIZED_OBSERVABLE_IMPACT",
                f"{path}.observable_impact",
                observable_impact,
            )
        decisions.append(
            {
                "id": identifier,
                "statement": _text(row["statement"], f"{path}.statement"),
                "delegation_ref": delegation_ref,
                "requirement_refs": sorted(requirement_refs),
                "acceptance_refs": sorted(acceptance_refs),
                "verification_refs": sorted(verification_refs),
                "affected_surfaces": sorted(
                    _surfaces(row["affected_surfaces"], f"{path}.affected_surfaces")
                ),
                "rationale": _text(row["rationale"], f"{path}.rationale"),
                "alternatives": _strings(
                    row["alternatives"], f"{path}.alternatives", allow_empty=True
                ),
                "observable_impact": observable_impact,
            }
        )
    if not decisions:
        _fail("INVALID_VALUE", "$.decisions", "must not be empty")

    step_fields = frozenset(
        {
            "id",
            "summary",
            "depends_on",
            "decision_refs",
            "requirement_refs",
            "acceptance_refs",
            "verification_refs",
            "affected_surfaces",
        }
    )
    steps: list[dict[str, Any]] = []
    step_ids: set[str] = set()
    for index, value in enumerate(_array(draft["steps"], "$.steps")):
        path = f"$.steps[{index}]"
        row = _closed(value, path, step_fields)
        identifier = _text(row["id"], f"{path}.id")
        if not _STEP_ID_PATTERN.fullmatch(identifier):
            _fail("INVALID_STEP_ID", f"{path}.id", "must match STEP-NNN")
        if identifier in step_ids:
            _fail("DUPLICATE_ID", f"{path}.id", identifier)
        step_ids.add(identifier)
        decision_refs = _strings(row["decision_refs"], f"{path}.decision_refs")
        for reference in decision_refs:
            if reference not in decision_ids:
                _fail("UNKNOWN_REFERENCE", f"{path}.decision_refs", reference)
        requirement_refs = _references(
            row["requirement_refs"], f"{path}.requirement_refs", requirements
        )
        acceptance_refs = _references(
            row["acceptance_refs"], f"{path}.acceptance_refs", acceptances
        )
        verification_refs = _references(
            row["verification_refs"], f"{path}.verification_refs", verifications
        )
        _validate_reference_consistency(
            requirement_refs,
            acceptance_refs,
            verification_refs,
            acceptances,
            verifications,
            path,
        )
        steps.append(
            {
                "id": identifier,
                "summary": _text(row["summary"], f"{path}.summary"),
                "depends_on": _strings(
                    row["depends_on"], f"{path}.depends_on", allow_empty=True
                ),
                "decision_refs": sorted(decision_refs),
                "requirement_refs": sorted(requirement_refs),
                "acceptance_refs": sorted(acceptance_refs),
                "verification_refs": sorted(verification_refs),
                "affected_surfaces": sorted(
                    _surfaces(row["affected_surfaces"], f"{path}.affected_surfaces")
                ),
            }
        )
    if not steps:
        _fail("INVALID_VALUE", "$.steps", "must not be empty")
    _validate_dag(steps)

    def covered(field: str) -> set[str]:
        return {reference for step in steps for reference in step[field]}

    for field, known in (
        ("decision_refs", decision_ids),
        ("requirement_refs", set(requirements)),
        ("acceptance_refs", set(acceptances)),
        ("verification_refs", set(verifications)),
    ):
        actual = covered(field)
        if actual != known:
            missing = sorted(known - actual)
            extra = sorted(actual - known)
            detail = f"missing {missing[0]}" if missing else f"invented {extra[0]}"
            _fail("PLAN_COVERAGE_MISMATCH", f"$.steps.{field}", detail)

    realization_fields = frozenset(
        {
            "verification_ref",
            "working_directory",
            "target",
            "procedure",
            "expected_result",
        }
    )
    realization: list[dict[str, str]] = []
    realized: set[str] = set()
    for index, value in enumerate(
        _array(draft["test_realization"], "$.test_realization")
    ):
        path = f"$.test_realization[{index}]"
        row = _closed(value, path, realization_fields)
        reference = _text(row["verification_ref"], f"{path}.verification_ref")
        if reference not in verifications:
            _fail("UNKNOWN_REFERENCE", f"{path}.verification_ref", reference)
        if reference in realized:
            _fail("DUPLICATE_REFERENCE", f"{path}.verification_ref", reference)
        realized.add(reference)
        expected_result = _text(row["expected_result"], f"{path}.expected_result")
        if expected_result != verifications[reference].get("expected_result"):
            _fail("EXPECTED_RESULT_MISMATCH", f"{path}.expected_result", reference)
        realization.append(
            {
                "verification_ref": reference,
                "working_directory": _text(
                    row["working_directory"], f"{path}.working_directory"
                ),
                "target": _text(row["target"], f"{path}.target"),
                "procedure": _text(row["procedure"], f"{path}.procedure"),
                "expected_result": expected_result,
            }
        )
    if realized != set(verifications):
        missing = sorted(set(verifications) - realized)
        extra = sorted(realized - set(verifications))
        detail = f"missing {missing[0]}" if missing else f"invented {extra[0]}"
        _fail("TEST_COVERAGE_MISMATCH", "$.test_realization", detail)

    conditions = _strings(
        draft["return_to_owner_conditions"], "$.return_to_owner_conditions"
    )
    if set(conditions) != set(RETURN_TO_OWNER_CONDITIONS) or len(conditions) != len(
        RETURN_TO_OWNER_CONDITIONS
    ):
        _fail(
            "RETURN_BOUNDARY_MISMATCH",
            "$.return_to_owner_conditions",
            "must contain every and only fixed return-to-owner condition",
        )

    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "contract_digest": contract_digest,
        "approach": normalized_approach,
        "decisions": sorted(decisions, key=lambda row: row["id"]),
        "steps": steps,
        "test_realization": sorted(
            realization, key=lambda row: row["verification_ref"]
        ),
        "return_to_owner_conditions": list(RETURN_TO_OWNER_CONDITIONS),
    }
    plan["plan_digest"] = plan_digest(plan)
    return plan


def plan_digest(plan: Mapping[str, Any]) -> str:
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    return hashlib.sha256(
        authority_compiler.canonical_json(unsigned).encode("utf-8")
    ).hexdigest()


def validate_implementation_plan(
    value: Any, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a compiled plan by rebuilding it from its closed payload."""

    plan = _closed(
        value,
        "$",
        frozenset(
            {
                "schema",
                "contract_digest",
                "approach",
                "decisions",
                "steps",
                "test_realization",
                "return_to_owner_conditions",
                "plan_digest",
            }
        ),
    )
    if _text(plan["schema"], "$.schema") != PLAN_SCHEMA:
        _fail("INVALID_SCHEMA", "$.schema", f"must be {PLAN_SCHEMA}")
    claimed_digest = _text(plan["plan_digest"], "$.plan_digest")
    if (
        not _DIGEST_PATTERN.fullmatch(claimed_digest)
        or plan_digest(plan) != claimed_digest
    ):
        _fail(
            "PLAN_DIGEST_MISMATCH",
            "$.plan_digest",
            "does not match implementation plan",
        )
    draft = dict(plan)
    draft.pop("plan_digest")
    draft["schema"] = DRAFT_SCHEMA
    rebuilt = compile_implementation_plan(draft, contract)
    if rebuilt != plan:
        _fail("PLAN_DRIFT", "$", "differs from a fresh compile")
    return rebuilt


def _strict_json_loads(text: str, path: str) -> Any:
    def reject_constant(token: str) -> None:
        _fail("INVALID_JSON", path, f"non-finite value {token}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY", path, key)
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except json.JSONDecodeError as error:
        _fail("INVALID_JSON", path, str(error))


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        return _object(
            _strict_json_loads(path.read_text(encoding="utf-8"), label), label
        )
    except (OSError, UnicodeError) as error:
        _fail("INPUT_ERROR", label, str(error))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="implementation_plan.py",
        description="Compile a Build Contract-bound implementation plan.",
    )
    parser.add_argument("draft", type=Path)
    parser.add_argument("--build-contract", required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        contract = _read(arguments.build_contract, "build-contract.json")
        if arguments.check:
            plan = validate_implementation_plan(
                _read(arguments.draft, "implementation-plan.json"), contract
            )
        else:
            plan = compile_implementation_plan(
                _read(arguments.draft, "implementation-plan-draft.json"), contract
            )
            assert arguments.output is not None
            _write(arguments.output, plan)
        print(
            "implementation plan valid: "
            f"{plan['plan_digest']} | decisions {len(plan['decisions'])} | "
            f"steps {len(plan['steps'])} | contract {plan['contract_digest']}"
        )
        return 0
    except PlanError as error:
        print(f"implementation-plan: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
