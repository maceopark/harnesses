#!/usr/bin/env python3
"""Fail closed when material decisions are lost during compiler projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import authority_compiler


LEGACY_MANIFEST_SCHEMA = "ultimateinterview.material-decisions.v1"
MANIFEST_SCHEMA = "ultimateinterview.material-decisions.v2"
SUPPORTED_MANIFEST_SCHEMAS = frozenset({LEGACY_MANIFEST_SCHEMA, MANIFEST_SCHEMA})
BLOCK_PATTERN = re.compile(
    r"^```ultimateinterview-material-decisions[ \t]*\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
DECISIONS_SECTION_PATTERN = re.compile(
    r"^## Decisions & Defaults[ \t]*\n(?P<body>.*?)(?=^## Acceptance[ \t]*$)",
    re.MULTILINE | re.DOTALL,
)
DECISION_ID_PATTERN = re.compile(r"DEC-[0-9]{3,}\Z")
DECISION_FIELDS = frozenset(
    {
        "id",
        "statement",
        "choice",
        "authority_ref",
        "requirement_ref",
        "applicable_boundary",
        "acceptance_refs",
        "verification_refs",
    }
)


class ProjectionError(ValueError):
    """A stable diagnostic for an incomplete or inconsistent projection."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}: {path}: {detail}")


def _fail(code: str, path: str, detail: str) -> None:
    raise ProjectionError(code, path, detail)


def _strict_json_loads(text: str, path: str) -> Any:
    def reject_constant(token: str) -> None:
        _fail("INVALID_JSON", path, f"non-finite JSON value {token} is not allowed")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY", path, f"duplicate object key {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        _fail(
            "INVALID_JSON",
            path,
            f"malformed JSON at line {error.lineno}, column {error.colno}",
        )


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
        _fail("INVALID_TYPE", path, "must be a non-empty string")
    return value


def _string_array(
    value: Any, path: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    values = _array(value, path)
    result = tuple(_text(item, f"{path}[{index}]") for index, item in enumerate(values))
    if not result and not allow_empty:
        _fail("INVALID_VALUE", path, "must not be empty")
    if len(result) != len(set(result)):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return result


def _closed_fields(value: Any, path: str, fields: frozenset[str]) -> dict[str, Any]:
    result = _object(value, path)
    unknown = sorted(set(result) - fields)
    missing = sorted(fields - set(result))
    if unknown:
        _fail("UNKNOWN_FIELD", path, f"unknown field {unknown[0]}")
    if missing:
        _fail("MISSING_FIELD", path, f"missing field {missing[0]}")
    return result


def parse_execution_contract(text: str) -> dict[str, Any]:
    """Extract and validate the single material-decision manifest."""

    section_matches = tuple(DECISIONS_SECTION_PATTERN.finditer(text))
    if len(section_matches) != 1:
        _fail(
            "INVALID_DECISIONS_SECTION",
            "execution-contract.md",
            "needs exactly one Decisions & Defaults section immediately followed by Acceptance",
        )
    section_body = section_matches[0].group("body")
    matches = tuple(BLOCK_PATTERN.finditer(section_body))
    if not matches:
        _fail(
            "MISSING_DECISION_MANIFEST",
            "execution-contract.md",
            "needs one ultimateinterview-material-decisions fenced block",
        )
    if len(matches) != 1:
        _fail(
            "DUPLICATE_DECISION_MANIFEST",
            "execution-contract.md",
            "must contain exactly one material-decision manifest",
        )
    if BLOCK_PATTERN.sub("", section_body).strip():
        _fail(
            "UNSTRUCTURED_MATERIAL_DECISION",
            "execution-contract.md",
            "Decisions & Defaults may contain only the closed material-decision manifest",
        )
    manifest = _closed_fields(
        _strict_json_loads(matches[0].group("body"), "$.material_decisions"),
        "$.material_decisions",
        frozenset({"schema", "decisions"}),
    )
    schema = _text(manifest["schema"], "$.material_decisions.schema")
    if schema not in SUPPORTED_MANIFEST_SCHEMAS:
        _fail(
            "INVALID_SCHEMA",
            "$.material_decisions.schema",
            f"must be one of: {', '.join(sorted(SUPPORTED_MANIFEST_SCHEMAS))}",
        )
    decisions = _array(manifest["decisions"], "$.material_decisions.decisions")
    if not decisions:
        _fail("INVALID_VALUE", "$.material_decisions.decisions", "must not be empty")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_projection_keys: set[tuple[str, str, str]] = set()
    seen_requirement_refs: set[str] = set()
    for index, value in enumerate(decisions):
        path = f"$.material_decisions.decisions[{index}]"
        decision = _closed_fields(value, path, DECISION_FIELDS)
        identifier = _text(decision["id"], f"{path}.id")
        if not DECISION_ID_PATTERN.fullmatch(identifier):
            _fail("INVALID_DECISION_ID", f"{path}.id", "must match DEC-NNN")
        if identifier in seen_ids:
            _fail("DUPLICATE_ID", f"{path}.id", f"duplicate decision ID {identifier}")
        seen_ids.add(identifier)
        choice = _text(decision["choice"], f"{path}.choice")
        if choice not in {"explicit", "delegated-default"}:
            _fail("INVALID_VALUE", f"{path}.choice", "must be explicit or delegated-default")
        statement = _text(decision["statement"], f"{path}.statement")
        authority_ref = _text(decision["authority_ref"], f"{path}.authority_ref")
        requirement_ref = _text(decision["requirement_ref"], f"{path}.requirement_ref")
        if schema == MANIFEST_SCHEMA and requirement_ref in seen_requirement_refs:
            _fail(
                "NON_ATOMIC_REQUIREMENT",
                f"{path}.requirement_ref",
                f"{requirement_ref} is already assigned to another material decision",
            )
        seen_requirement_refs.add(requirement_ref)
        projection_key = (statement, authority_ref, requirement_ref)
        if projection_key in seen_projection_keys:
            _fail("DUPLICATE_PROJECTION", path, "duplicates an existing decision projection")
        seen_projection_keys.add(projection_key)
        normalized.append(
            {
                "id": identifier,
                "statement": statement,
                "choice": choice,
                "authority_ref": authority_ref,
                "requirement_ref": requirement_ref,
                "applicable_boundary": _string_array(
                    decision["applicable_boundary"], f"{path}.applicable_boundary"
                ),
                "acceptance_refs": _string_array(
                    decision["acceptance_refs"], f"{path}.acceptance_refs"
                ),
                "verification_refs": _string_array(
                    decision["verification_refs"], f"{path}.verification_refs"
                ),
            }
        )
    return {"schema": schema, "decisions": normalized}


def _id_map(value: Mapping[str, Any], field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(_array(value.get(field), f"$.{field}")):
        path = f"$.{field}[{index}]"
        row = _object(item, path)
        identifier = _text(row.get("id"), f"{path}.id")
        if identifier in result:
            _fail("DUPLICATE_ID", f"{path}.id", f"duplicate ID {identifier}")
        result[identifier] = row
    return result


def _obligations(row: Mapping[str, Any], path: str) -> frozenset[str]:
    constraints = _string_array(
        row.get("constraints"), f"{path}.constraints", allow_empty=True
    )
    preserved = _string_array(
        row.get("preserved_behaviors"),
        f"{path}.preserved_behaviors",
        allow_empty=True,
    )
    result = frozenset((*constraints, *preserved))
    if not result:
        _fail("INVALID_VALUE", path, "must contain at least one obligation")
    return result


def validate_projection(
    execution_contract_text: str,
    discovery: Mapping[str, Any],
    authority_register: Mapping[str, Any],
    build_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate DEC -> authority -> requirement -> acceptance -> verification lineage."""

    manifest = parse_execution_contract(execution_contract_text)
    try:
        sealed_register = authority_compiler.validate_authority_register(authority_register)
        rebuilt = authority_compiler.compile_discovery_record(discovery, sealed_register)
    except authority_compiler.CompilerError as error:
        _fail("INVALID_COMPILER_INPUT", error.path, f"{error.code}: {error.detail}")
    if rebuilt != build_contract:
        _fail(
            "BUILD_CONTRACT_DRIFT",
            "build-contract.json",
            "differs from a fresh compile of discovery-record.json",
        )

    authorities = _id_map(build_contract, "authorities")
    requirements = _id_map(build_contract, "requirements")
    acceptances = _id_map(build_contract, "acceptance_predicates")
    verifications = _id_map(build_contract, "verifications")
    trace_rows = {
        (
            row.get("authority_ref"),
            row.get("requirement_ref"),
            row.get("acceptance_ref"),
            row.get("verification_ref"),
        )
        for row in _array(build_contract.get("trace"), "$.trace")
        if isinstance(row, dict)
    }

    covered_pairs: set[tuple[str, str]] = set()
    for index, decision in enumerate(manifest["decisions"]):
        path = f"$.material_decisions.decisions[{index}]"
        authority_ref = decision["authority_ref"]
        requirement_ref = decision["requirement_ref"]
        authority = authorities.get(authority_ref)
        if authority is None:
            _fail("UNKNOWN_REFERENCE", f"{path}.authority_ref", authority_ref)
        requirement = requirements.get(requirement_ref)
        if requirement is None:
            _fail("UNKNOWN_REFERENCE", f"{path}.requirement_ref", requirement_ref)
        if authority.get("status") != "active":
            _fail("INACTIVE_AUTHORITY", f"{path}.authority_ref", authority_ref)
        expected_kind = (
            "bounded-delegation" if decision["choice"] == "delegated-default" else None
        )
        if expected_kind is not None and authority.get("kind") != expected_kind:
            _fail(
                "CHOICE_AUTHORITY_MISMATCH",
                f"{path}.choice",
                "delegated-default requires bounded-delegation authority",
            )
        if decision["choice"] == "explicit" and authority.get("kind") not in {
            "owner-decision",
            "canonical-contract",
        }:
            _fail(
                "CHOICE_AUTHORITY_MISMATCH",
                f"{path}.choice",
                "explicit requires owner-decision or canonical-contract authority",
            )
        if authority_ref not in _string_array(
            requirement.get("authority_refs"), f"$.requirements[{requirement_ref}].authority_refs"
        ):
            _fail(
                "MISSING_AUTHORITY_PROJECTION",
                path,
                f"{requirement_ref} does not reference {authority_ref}",
            )
        if set(decision["applicable_boundary"]) != set(
            _string_array(requirement.get("scope"), f"$.requirements[{requirement_ref}].scope")
        ):
            _fail(
                "BOUNDARY_PROJECTION_MISMATCH",
                f"{path}.applicable_boundary",
                f"must exactly match {requirement_ref} scope",
            )
        statement = decision["statement"]
        if statement not in _obligations(authority, f"$.authorities[{authority_ref}]"):
            _fail(
                "DECISION_LOST_FROM_AUTHORITY",
                f"{path}.statement",
                f"is not an exact authority constraint or preserved behavior in {authority_ref}",
            )
        if statement not in _obligations(requirement, f"$.requirements[{requirement_ref}]"):
            _fail(
                "DECISION_LOST_FROM_REQUIREMENT",
                f"{path}.statement",
                f"is not an exact requirement constraint or preserved behavior in {requirement_ref}",
            )
        if manifest["schema"] == MANIFEST_SCHEMA:
            requirement_obligations = _obligations(
                requirement, f"$.requirements[{requirement_ref}]"
            )
            if requirement_obligations != {statement}:
                _fail(
                    "NON_ATOMIC_REQUIREMENT",
                    f"$.requirements[{requirement_ref}]",
                    "must contain exactly the one obligation named by its material decision",
                )
            if set(requirement.get("authority_refs", [])) != {authority_ref}:
                _fail(
                    "NON_ATOMIC_REQUIREMENT",
                    f"$.requirements[{requirement_ref}].authority_refs",
                    "must contain exactly the authority named by its material decision",
                )

        expected_acceptances = {
            identifier
            for identifier, acceptance in acceptances.items()
            if acceptance.get("requirement_ref") == requirement_ref
        }
        if set(decision["acceptance_refs"]) != expected_acceptances:
            _fail(
                "ACCEPTANCE_PROJECTION_MISMATCH",
                f"{path}.acceptance_refs",
                f"must cover every and only acceptance for {requirement_ref}",
            )
        expected_verifications = {
            identifier
            for identifier, verification in verifications.items()
            if verification.get("requirement_ref") == requirement_ref
            and set(verification.get("acceptance_refs", [])) & expected_acceptances
        }
        if set(decision["verification_refs"]) != expected_verifications:
            _fail(
                "VERIFICATION_PROJECTION_MISMATCH",
                f"{path}.verification_refs",
                f"must cover every and only verification for {requirement_ref}",
            )
        for acceptance_ref in decision["acceptance_refs"]:
            for verification_ref in decision["verification_refs"]:
                verification_acceptances = set(
                    verifications[verification_ref].get("acceptance_refs", [])
                )
                if acceptance_ref not in verification_acceptances:
                    continue
                row = (authority_ref, requirement_ref, acceptance_ref, verification_ref)
                if row not in trace_rows:
                    _fail(
                        "DECISION_TRACE_INCOMPLETE",
                        path,
                        "missing " + " -> ".join(row),
                    )
        covered_pairs.add((authority_ref, requirement_ref))

    required_pairs = {
        (authority_ref, requirement_ref)
        for requirement_ref, requirement in requirements.items()
        for authority_ref in requirement.get("authority_refs", [])
    }
    missing_pairs = sorted(required_pairs - covered_pairs)
    if missing_pairs:
        authority_ref, requirement_ref = missing_pairs[0]
        _fail(
            "UNMAPPED_MATERIAL_DECISION",
            "$.material_decisions.decisions",
            f"missing DEC mapping for {authority_ref} -> {requirement_ref}",
        )
    extra_pairs = sorted(covered_pairs - required_pairs)
    if extra_pairs:
        authority_ref, requirement_ref = extra_pairs[0]
        _fail(
            "INVENTED_MATERIAL_DECISION",
            "$.material_decisions.decisions",
            f"DEC mapping has no compiler projection for {authority_ref} -> {requirement_ref}",
        )

    manifest_digest = hashlib.sha256(
        authority_compiler.canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    decision_requirements = {
        decision["id"]: decision["requirement_ref"]
        for decision in sorted(manifest["decisions"], key=lambda item: item["id"])
    }
    requirement_decision_counts: dict[str, int] = {}
    for requirement_ref in decision_requirements.values():
        requirement_decision_counts[requirement_ref] = (
            requirement_decision_counts.get(requirement_ref, 0) + 1
        )
    return {
        "schema": manifest["schema"],
        "manifest_digest": manifest_digest,
        "contract_digest": build_contract.get("contract_digest"),
        "decision_ids": sorted(decision["id"] for decision in manifest["decisions"]),
        "decision_requirements": decision_requirements,
        "legacy_shared_requirements": sorted(
            requirement_ref
            for requirement_ref, count in requirement_decision_counts.items()
            if count > 1
        ),
    }


def _read_text(path: Path, label: str) -> str:
    if not path.is_file():
        _fail("INPUT_ERROR", label, "input is not a file")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        _fail("INPUT_ERROR", label, f"could not read UTF-8 input: {error}")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    value = _strict_json_loads(_read_text(path, label), label)
    return _object(value, label)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="projection_check.py",
        description="Validate deterministic material-decision projection into a Build Contract.",
    )
    parser.add_argument("execution_contract", type=Path)
    parser.add_argument("--discovery", required=True, type=Path)
    parser.add_argument("--authority-register", required=True, type=Path)
    parser.add_argument("--build-contract", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = validate_projection(
            _read_text(arguments.execution_contract, "execution-contract.md"),
            _read_object(arguments.discovery, "discovery-record.json"),
            _read_object(arguments.authority_register, "authority-register.json"),
            _read_object(arguments.build_contract, "build-contract.json"),
        )
        print(
            "projection valid: "
            f"{result['manifest_digest']} | decisions {len(result['decision_ids'])} | "
            f"contract {result['contract_digest']}"
        )
        return 0
    except ProjectionError as error:
        print(f"projection-check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
