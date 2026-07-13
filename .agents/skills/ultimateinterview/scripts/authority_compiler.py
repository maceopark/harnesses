#!/usr/bin/env python3
"""Fail-closed compiler from an Ultimateinterview Discovery Record to a Build Contract.

The input schema is intentionally closed.  A Discovery Record is a JSON object with
these required keys:

* ``schema``: ``ultimateinterview.discovery-record.v1``
* ``goal``: a normative clause (without an ``id``)
* ``scope`` and ``non_goals``: lists of normative clauses
* ``authorities`` and ``evidence``: the authority register and non-authoritative facts
* ``requirements``, ``acceptance_predicates``, ``verifications``, and ``trace``
* ``unresolved_decisions`` and ``conflicts``

A normative clause has ``text``, ``decision_class``, ``scope``, ``constraints``,
``preserved_behaviors``, ``authority_refs``, and ``evidence_refs``.  Scope and
non-goal clauses additionally have an ``id``; requirements additionally have closed
``acceptance_bindings``.  An acceptance predicate has the complete precondition/input
-> action -> observable result -> failure result shape.

This module deliberately has no repository, agent-runtime, or orchestration
coupling.  It accepts JSON-compatible values, returns JSON-compatible values, and
uses only the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


DISCOVERY_SCHEMA = "ultimateinterview.discovery-record.v1"
BUILD_CONTRACT_SCHEMA = "ultimateinterview.build-contract.v1"
_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._:-]*\Z")
_SCOPE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")
_DELEGATION_WILDCARD_PATTERN = re.compile(r"[*?\[\]]")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class AuthorityKind(StrEnum):
    OWNER_DECISION = "owner-decision"
    CANONICAL_CONTRACT = "canonical-contract"
    BOUNDED_DELEGATION = "bounded-delegation"
class DelegationBoundaryKind(StrEnum):
    REPOSITORY_PATHS = "repository-paths"
    NAMED_COMPONENT = "named-component"




class AuthorityStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


class EvidenceKind(StrEnum):
    REPOSITORY = "repository-evidence"
    PROPOSAL = "proposal"
    ASSUMPTION = "assumption"
    REVIEWER_CONSENSUS = "reviewer-consensus"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    TEST = "test"
    CONFIGURATION = "configuration"
    HISTORY = "history"
    PROTOTYPE = "prototype"
    USER_STATEMENT = "user-statement"


class DecisionClass(StrEnum):
    GOAL = "goal"
    OBSERVABLE_BEHAVIOR = "observable-behavior"
    SCOPE = "scope"
    NON_GOALS = "non-goals"
    ACTOR_AUTHORIZATION_OWNERSHIP = "actor-authorization-ownership"
    RETENTION_DELETION_LIFECYCLE = "retention-deletion-lifecycle"
    FAILURE_RETRY_RECOVERY = "failure-retry-recovery"
    IRREVERSIBLE_MIGRATION_DATA_LOSS = "irreversible-migration-data-loss"
    COMPATIBILITY_FLOOR = "compatibility-floor"
    NUMERIC_QUALITY_THRESHOLD = "numeric-quality-threshold"
    INTERNAL_ARCHITECTURE = "internal-architecture"
    FILE_MODULE_STRUCTURE = "file-module-structure"
    ALGORITHM = "algorithm"
    TEST_ORGANIZATION = "test-organization"


class VerificationMethod(StrEnum):
    COMMAND = "command"
    SCENARIO = "scenario"
    INSPECTION = "inspection"


OWNER_ONLY_DECISION_CLASSES = frozenset(
    {
        DecisionClass.GOAL,
        DecisionClass.OBSERVABLE_BEHAVIOR,
        DecisionClass.SCOPE,
        DecisionClass.NON_GOALS,
        DecisionClass.ACTOR_AUTHORIZATION_OWNERSHIP,
        DecisionClass.RETENTION_DELETION_LIFECYCLE,
        DecisionClass.FAILURE_RETRY_RECOVERY,
        DecisionClass.IRREVERSIBLE_MIGRATION_DATA_LOSS,
        DecisionClass.COMPATIBILITY_FLOOR,
        DecisionClass.NUMERIC_QUALITY_THRESHOLD,
    }
)
IMPLEMENTER_DECISION_CLASSES = frozenset(
    {
        DecisionClass.INTERNAL_ARCHITECTURE,
        DecisionClass.FILE_MODULE_STRUCTURE,
        DecisionClass.ALGORITHM,
        DecisionClass.TEST_ORGANIZATION,
    }
)


class CompilerError(ValueError):
    """A stable, safe diagnostic for malformed or unauthorized input."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}: {path}: {detail}")


@dataclass(frozen=True, slots=True)
class SourceRef:
    uri: str
    version: str
@dataclass(frozen=True, slots=True)
class DelegationBoundary:
    kind: DelegationBoundaryKind
    includes: tuple[str, ...]
    excludes: tuple[str, ...]




@dataclass(frozen=True, slots=True)
class Authority:
    id: str
    kind: AuthorityKind
    status: AuthorityStatus
    source: SourceRef
    scope: tuple[str, ...]
    constraints: tuple[str, ...]
    preserved_behaviors: tuple[str, ...]
    decision_classes: tuple[DecisionClass, ...]
    statement: str
    supersedes: tuple[str, ...]
    conflicts_with: tuple[str, ...]
    applicability: tuple[str, ...] | None = None
    precedence: int | None = None
    owner: str | None = None
    canonical_artifact: str | None = None
    delegate: str | None = None
    delegation_boundary: DelegationBoundary | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    kind: EvidenceKind
    source: SourceRef
    summary: str


@dataclass(frozen=True, slots=True)
class AcceptanceBinding:
    acceptance_ref: str
    digest: str


@dataclass(frozen=True, slots=True)
class Clause:
    id: str | None
    text: str
    decision_class: DecisionClass
    scope: tuple[str, ...]
    constraints: tuple[str, ...]
    authority_refs: tuple[str, ...]
    preserved_behaviors: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    acceptance_bindings: tuple[AcceptanceBinding, ...] = ()


@dataclass(frozen=True, slots=True)
class AcceptancePredicate:
    id: str
    requirement_ref: str
    precondition: str
    input: str
    action: str
    observable_result: str
    failure_result: str


@dataclass(frozen=True, slots=True)
class Verification:
    id: str
    requirement_ref: str
    acceptance_refs: tuple[str, ...]
    method: VerificationMethod
    procedure: str
    expected_result: str


@dataclass(frozen=True, slots=True)
class TraceRow:
    authority_ref: str
    requirement_ref: str
    acceptance_ref: str
    verification_ref: str


@dataclass(frozen=True, slots=True)
class UnresolvedDecision:
    id: str
    question: str
    owner: str


@dataclass(frozen=True, slots=True)
class Conflict:
    id: str
    authority_refs: tuple[str, ...]
    status: str
    scope: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    preserved_behaviors: tuple[str, ...] = ()
    decision_class: DecisionClass | None = None
    winning_authority_ref: str | None = None
    resolution_authority_ref: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    goal: Clause
    scope: tuple[Clause, ...]
    non_goals: tuple[Clause, ...]
    authorities: tuple[Authority, ...]
    evidence: tuple[Evidence, ...]
    requirements: tuple[Clause, ...]
    acceptance_predicates: tuple[AcceptancePredicate, ...]
    verifications: tuple[Verification, ...]
    trace: tuple[TraceRow, ...]
    unresolved_decisions: tuple[UnresolvedDecision, ...]
    conflicts: tuple[Conflict, ...]


def canonical_json(value: Any) -> str:
    """Return the single canonical UTF-8 JSON serialization, including one newline."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise CompilerError("NON_CANONICAL_VALUE", "$", "value is not finite JSON") from error
    return f"{payload}\n"


def pretty_json(value: Any) -> str:
    """Return deterministic, human-readable UTF-8 JSON with one trailing newline."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise CompilerError("NON_CANONICAL_VALUE", "$", "value is not finite JSON") from error
    return f"{payload}\n"


def sha256_canonical_json(value: Any) -> str:
    """Hash canonical JSON bytes, including the required trailing newline."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
_ACCEPTANCE_BINDING_DOMAIN = "ultimateinterview.acceptance-binding.v1"


def acceptance_binding_digest(
    requirement_payload: Mapping[str, Any],
    acceptance_payload: Mapping[str, Any],
) -> str:
    """Hash a requirement core and complete acceptance predicate for one binding."""

    requirement_core = {
        "id": requirement_payload["id"],
        "text": requirement_payload["text"],
        "decision_class": requirement_payload["decision_class"],
        "scope": sorted(requirement_payload["scope"]),
        "constraints": sorted(requirement_payload["constraints"]),
        "preserved_behaviors": sorted(requirement_payload["preserved_behaviors"]),
        "authority_refs": sorted(requirement_payload["authority_refs"]),
        "evidence_refs": sorted(requirement_payload["evidence_refs"]),
    }
    return sha256_canonical_json(
        {
            "domain": _ACCEPTANCE_BINDING_DOMAIN,
            "requirement": requirement_core,
            "acceptance": dict(acceptance_payload),
        }
    )


def contract_digest(contract: Mapping[str, Any]) -> str:
    """Compute a Build Contract digest without trusting its claimed digest field."""

    if not isinstance(contract, Mapping):
        raise CompilerError("INVALID_TYPE", "$", "contract must be an object")
    payload = dict(contract)
    payload.pop("contract_digest", None)
    return sha256_canonical_json(payload)


def _fail(code: str, path: str, detail: str) -> None:
    raise CompilerError(code, path, detail)


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail("INVALID_TYPE", path, "must be an object")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_TYPE", path, "must be an array")
    return value


def _fields(value: Any, path: str, required: Iterable[str], *, missing_code: str = "MISSING_FIELD") -> Mapping[str, Any]:
    object_value = _object(value, path)
    required_set = frozenset(required)
    unknown = sorted(set(object_value) - required_set)
    if unknown:
        _fail("UNKNOWN_FIELD", path, f"unknown field(s): {', '.join(unknown)}")
    missing = sorted(required_set - set(object_value))
    if missing:
        _fail(missing_code, path, f"missing field(s): {', '.join(missing)}")
    return object_value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INVALID_VALUE", path, "must be a non-empty string")
    return value


def _identifier(value: Any, path: str) -> str:
    text = _text(value, path)
    if not _ID_PATTERN.fullmatch(text):
        _fail("INVALID_VALUE", path, "must be a stable identifier")
    return text


def _digest(value: Any, path: str) -> str:
    text = _text(value, path)
    if not _DIGEST_PATTERN.fullmatch(text):
        _fail("INVALID_VALUE", path, "must be a lowercase SHA-256 digest")
    return text


def _nonnegative_integer(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        _fail("INVALID_VALUE", path, "must be an integer greater than or equal to zero")
    return value



def _enum(value: Any, enum_type: type[StrEnum], path: str) -> StrEnum:
    text = _text(value, path)
    try:
        return enum_type(text)
    except ValueError as error:
        allowed = ", ".join(member.value for member in enum_type)
        raise CompilerError("INVALID_VALUE", path, f"must be one of: {allowed}") from error


def _unique_texts(value: Any, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    values = _array(value, path)
    if not values and not allow_empty:
        _fail("INVALID_VALUE", path, "must not be empty")
    parsed = tuple(_text(item, f"{path}[{index}]") for index, item in enumerate(values))
    if len(set(parsed)) != len(parsed):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return parsed


def _unique_identifiers(value: Any, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    values = _array(value, path)
    if not values and not allow_empty:
        _fail("INVALID_VALUE", path, "must not be empty")
    parsed = tuple(_identifier(item, f"{path}[{index}]") for index, item in enumerate(values))
    if len(set(parsed)) != len(parsed):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return parsed


def _scope(value: Any, path: str) -> tuple[str, ...]:
    values = _unique_texts(value, path)
    for token in values:
        if not _SCOPE_PATTERN.fullmatch(token):
            _fail("INVALID_VALUE", path, "scope entries must be stable scope tokens")
    return values
def _repository_path(value: Any, path: str) -> str:
    text = _text(value, path)
    parsed = PurePosixPath(text)
    if (
        text.startswith("/")
        or "\\" in text
        or _DELEGATION_WILDCARD_PATTERN.search(text)
        or text == "."
        or any(part in {".", ".."} for part in parsed.parts)
        or str(parsed) != text
    ):
        _fail(
            "INVALID_DELEGATION",
            path,
            "repository paths must be normalized relative paths without wildcard, dot, absolute, or traversal values",
        )
    return text


def _delegation_boundary_entries(
    value: Any,
    path: str,
    kind: DelegationBoundaryKind,
) -> tuple[str, ...]:
    values = _array(value, path)
    if not values:
        _fail("INVALID_DELEGATION", path, "must not be empty")
    parser = _repository_path if kind is DelegationBoundaryKind.REPOSITORY_PATHS else _identifier
    parsed = tuple(parser(item, f"{path}[{index}]") for index, item in enumerate(values))
    if len(set(parsed)) != len(parsed):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return parsed


def _parse_delegation_boundary(value: Any, path: str) -> DelegationBoundary:
    object_value = _fields(value, path, {"kind", "includes", "excludes"})
    kind = DelegationBoundaryKind(_enum(object_value["kind"], DelegationBoundaryKind, f"{path}.kind"))
    includes = _delegation_boundary_entries(object_value["includes"], f"{path}.includes", kind)
    excludes = _delegation_boundary_entries(object_value["excludes"], f"{path}.excludes", kind)
    if set(includes) & set(excludes):
        _fail("INVALID_DELEGATION", path, "includes and excludes must be disjoint")
    return DelegationBoundary(kind=kind, includes=includes, excludes=excludes)




def _decision_classes(value: Any, path: str) -> tuple[DecisionClass, ...]:
    values = _array(value, path)
    if not values:
        _fail("INVALID_VALUE", path, "must not be empty")
    parsed = tuple(
        _enum(item, DecisionClass, f"{path}[{index}]")
        for index, item in enumerate(values)
    )
    if len(set(parsed)) != len(parsed):
        _fail("DUPLICATE_REFERENCE", path, "must not contain duplicates")
    return tuple(DecisionClass(item) for item in parsed)


def _source(value: Any, path: str) -> SourceRef:
    object_value = _fields(value, path, {"uri", "version"})
    return SourceRef(
        uri=_text(object_value["uri"], f"{path}.uri"),
        version=_text(object_value["version"], f"{path}.version"),
    )


def _parse_authority(value: Any, path: str) -> Authority:
    raw = _object(value, path)
    if "kind" not in raw:
        _fail("MISSING_FIELD", path, "missing field(s): kind")
    kind = AuthorityKind(_enum(raw["kind"], AuthorityKind, f"{path}.kind"))
    common = {
        "id",
        "kind",
        "status",
        "source",
        "scope",
        "constraints",
        "preserved_behaviors",
        "decision_classes",
        "statement",
        "supersedes",
        "conflicts_with",
    }
    kind_fields = {
        AuthorityKind.OWNER_DECISION: {"owner"},
        AuthorityKind.CANONICAL_CONTRACT: {"canonical_artifact", "applicability", "precedence"},
        AuthorityKind.BOUNDED_DELEGATION: {"delegate", "delegation_boundary"},
    }[kind]
    object_value = _fields(raw, path, common | kind_fields)
    scope = _scope(object_value["scope"], f"{path}.scope")
    delegation_boundary = (
        _parse_delegation_boundary(object_value["delegation_boundary"], f"{path}.delegation_boundary")
        if kind is AuthorityKind.BOUNDED_DELEGATION
        else None
    )
    if delegation_boundary is not None and not set(scope) <= set(delegation_boundary.includes):
        _fail(
            "INVALID_DELEGATION",
            f"{path}.scope",
            "every delegation scope item must be explicitly included by its delegation boundary",
        )
    return Authority(
        id=_identifier(object_value["id"], f"{path}.id"),
        kind=kind,
        status=AuthorityStatus(_enum(object_value["status"], AuthorityStatus, f"{path}.status")),
        source=_source(object_value["source"], f"{path}.source"),
        scope=scope,
        constraints=_unique_texts(object_value["constraints"], f"{path}.constraints"),
        preserved_behaviors=_unique_texts(object_value["preserved_behaviors"], f"{path}.preserved_behaviors"),
        decision_classes=_decision_classes(object_value["decision_classes"], f"{path}.decision_classes"),
        statement=_text(object_value["statement"], f"{path}.statement"),
        supersedes=_unique_identifiers(object_value["supersedes"], f"{path}.supersedes", allow_empty=True),
        conflicts_with=_unique_identifiers(object_value["conflicts_with"], f"{path}.conflicts_with", allow_empty=True),
        applicability=(
            _scope(object_value["applicability"], f"{path}.applicability")
            if kind is AuthorityKind.CANONICAL_CONTRACT
            else None
        ),
        precedence=(
            _nonnegative_integer(object_value["precedence"], f"{path}.precedence")
            if kind is AuthorityKind.CANONICAL_CONTRACT
            else None
        ),
        owner=(
            _identifier(object_value["owner"], f"{path}.owner")
            if kind is AuthorityKind.OWNER_DECISION
            else None
        ),
        canonical_artifact=(
            _text(object_value["canonical_artifact"], f"{path}.canonical_artifact")
            if kind is AuthorityKind.CANONICAL_CONTRACT
            else None
        ),
        delegate=(
            _identifier(object_value["delegate"], f"{path}.delegate")
            if kind is AuthorityKind.BOUNDED_DELEGATION
            else None
        ),
        delegation_boundary=delegation_boundary,
    )


def _parse_evidence(value: Any, path: str) -> Evidence:
    object_value = _fields(value, path, {"id", "kind", "source", "summary"})
    return Evidence(
        id=_identifier(object_value["id"], f"{path}.id"),
        kind=EvidenceKind(_enum(object_value["kind"], EvidenceKind, f"{path}.kind")),
        source=_source(object_value["source"], f"{path}.source"),
        summary=_text(object_value["summary"], f"{path}.summary"),
    )


def _parse_acceptance_binding(value: Any, path: str) -> AcceptanceBinding:
    object_value = _fields(value, path, {"acceptance_ref", "digest"})
    return AcceptanceBinding(
        acceptance_ref=_identifier(object_value["acceptance_ref"], f"{path}.acceptance_ref"),
        digest=_digest(object_value["digest"], f"{path}.digest"),
    )


def _parse_clause(
    value: Any,
    path: str,
    *,
    has_id: bool,
    required_class: DecisionClass | None = None,
    require_acceptance_bindings: bool = False,
) -> Clause:
    fields = {"text", "decision_class", "scope", "constraints", "preserved_behaviors", "authority_refs", "evidence_refs"}
    if has_id:
        fields.add("id")
    if require_acceptance_bindings:
        fields.add("acceptance_bindings")
    object_value = _fields(value, path, fields)
    decision_class = DecisionClass(_enum(object_value["decision_class"], DecisionClass, f"{path}.decision_class"))
    if required_class is not None and decision_class is not required_class:
        _fail("INVALID_VALUE", f"{path}.decision_class", f"must be {required_class.value}")
    bindings = (
        tuple(
            _parse_acceptance_binding(item, f"{path}.acceptance_bindings[{index}]")
            for index, item in enumerate(_array(object_value["acceptance_bindings"], f"{path}.acceptance_bindings"))
        )
        if require_acceptance_bindings
        else ()
    )
    if len({binding.acceptance_ref for binding in bindings}) != len(bindings):
        _fail("DUPLICATE_REFERENCE", f"{path}.acceptance_bindings", "must not contain duplicate acceptance references")
    return Clause(
        id=_identifier(object_value["id"], f"{path}.id") if has_id else None,
        text=_text(object_value["text"], f"{path}.text"),
        decision_class=decision_class,
        scope=_scope(object_value["scope"], f"{path}.scope"),
        constraints=_unique_texts(object_value["constraints"], f"{path}.constraints"),
        preserved_behaviors=_unique_texts(object_value["preserved_behaviors"], f"{path}.preserved_behaviors"),
        authority_refs=_unique_identifiers(object_value["authority_refs"], f"{path}.authority_refs", allow_empty=True),
        evidence_refs=_unique_identifiers(object_value["evidence_refs"], f"{path}.evidence_refs", allow_empty=True),
        acceptance_bindings=bindings,
    )


def _parse_acceptance(value: Any, path: str) -> AcceptancePredicate:
    fields = {
        "id",
        "requirement_ref",
        "precondition",
        "input",
        "action",
        "observable_result",
        "failure_result",
    }
    object_value = _fields(value, path, fields, missing_code="ACCEPTANCE_INCOMPLETE")
    try:
        return AcceptancePredicate(
            id=_identifier(object_value["id"], f"{path}.id"),
            requirement_ref=_identifier(object_value["requirement_ref"], f"{path}.requirement_ref"),
            precondition=_text(object_value["precondition"], f"{path}.precondition"),
            input=_text(object_value["input"], f"{path}.input"),
            action=_text(object_value["action"], f"{path}.action"),
            observable_result=_text(object_value["observable_result"], f"{path}.observable_result"),
            failure_result=_text(object_value["failure_result"], f"{path}.failure_result"),
        )
    except CompilerError as error:
        if error.path.startswith(path) and error.code == "INVALID_VALUE":
            raise CompilerError("ACCEPTANCE_INCOMPLETE", error.path, error.detail) from error
        raise


def _parse_verification(value: Any, path: str) -> Verification:
    object_value = _fields(
        value,
        path,
        {"id", "requirement_ref", "acceptance_refs", "method", "procedure", "expected_result"},
    )
    return Verification(
        id=_identifier(object_value["id"], f"{path}.id"),
        requirement_ref=_identifier(object_value["requirement_ref"], f"{path}.requirement_ref"),
        acceptance_refs=_unique_identifiers(object_value["acceptance_refs"], f"{path}.acceptance_refs"),
        method=VerificationMethod(_enum(object_value["method"], VerificationMethod, f"{path}.method")),
        procedure=_text(object_value["procedure"], f"{path}.procedure"),
        expected_result=_text(object_value["expected_result"], f"{path}.expected_result"),
    )


def _parse_trace(value: Any, path: str) -> TraceRow:
    object_value = _fields(value, path, {"authority_ref", "requirement_ref", "acceptance_ref", "verification_ref"})
    return TraceRow(
        authority_ref=_identifier(object_value["authority_ref"], f"{path}.authority_ref"),
        requirement_ref=_identifier(object_value["requirement_ref"], f"{path}.requirement_ref"),
        acceptance_ref=_identifier(object_value["acceptance_ref"], f"{path}.acceptance_ref"),
        verification_ref=_identifier(object_value["verification_ref"], f"{path}.verification_ref"),
    )


def _parse_unresolved_decision(value: Any, path: str) -> UnresolvedDecision:
    object_value = _fields(value, path, {"id", "question", "owner"})
    return UnresolvedDecision(
        id=_identifier(object_value["id"], f"{path}.id"),
        question=_text(object_value["question"], f"{path}.question"),
        owner=_text(object_value["owner"], f"{path}.owner"),
    )


def _parse_conflict(value: Any, path: str) -> Conflict:
    raw = _object(value, path)
    if "status" not in raw:
        _fail("MISSING_FIELD", path, "missing field(s): status")
    status = _text(raw["status"], f"{path}.status")
    if status not in {"resolved", "unresolved"}:
        _fail("INVALID_VALUE", f"{path}.status", "must be one of: resolved, unresolved")
    fields = {"id", "authority_refs", "status"}
    if status == "resolved":
        fields |= {
            "scope",
            "constraints",
            "preserved_behaviors",
            "decision_class",
            "winning_authority_ref",
            "resolution_authority_ref",
        }
    object_value = _fields(raw, path, fields)
    refs = _unique_identifiers(object_value["authority_refs"], f"{path}.authority_refs")
    if len(refs) < 2:
        _fail("INVALID_VALUE", f"{path}.authority_refs", "must name at least two authorities")
    return Conflict(
        id=_identifier(object_value["id"], f"{path}.id"),
        authority_refs=refs,
        status=status,
        scope=_scope(object_value["scope"], f"{path}.scope") if status == "resolved" else (),
        constraints=_unique_texts(object_value["constraints"], f"{path}.constraints") if status == "resolved" else (),
        preserved_behaviors=(
            _unique_texts(object_value["preserved_behaviors"], f"{path}.preserved_behaviors")
            if status == "resolved"
            else ()
        ),
        decision_class=(
            DecisionClass(_enum(object_value["decision_class"], DecisionClass, f"{path}.decision_class"))
            if status == "resolved"
            else None
        ),
        winning_authority_ref=(
            _identifier(object_value["winning_authority_ref"], f"{path}.winning_authority_ref")
            if status == "resolved"
            else None
        ),
        resolution_authority_ref=(
            _identifier(object_value["resolution_authority_ref"], f"{path}.resolution_authority_ref")
            if status == "resolved"
            else None
        ),
    )


def _parse_record(value: Any) -> DiscoveryRecord:
    object_value = _fields(
        value,
        "$",
        {
            "schema",
            "goal",
            "scope",
            "non_goals",
            "authorities",
            "evidence",
            "requirements",
            "acceptance_predicates",
            "verifications",
            "trace",
            "unresolved_decisions",
            "conflicts",
        },
    )
    if _text(object_value["schema"], "$.schema") != DISCOVERY_SCHEMA:
        _fail("INVALID_SCHEMA", "$.schema", f"must be {DISCOVERY_SCHEMA}")

    scope_values = _array(object_value["scope"], "$.scope")
    non_goal_values = _array(object_value["non_goals"], "$.non_goals")
    authority_values = _array(object_value["authorities"], "$.authorities")
    evidence_values = _array(object_value["evidence"], "$.evidence")
    requirement_values = _array(object_value["requirements"], "$.requirements")
    acceptance_values = _array(object_value["acceptance_predicates"], "$.acceptance_predicates")
    verification_values = _array(object_value["verifications"], "$.verifications")
    trace_values = _array(object_value["trace"], "$.trace")
    unresolved_values = _array(object_value["unresolved_decisions"], "$.unresolved_decisions")
    conflict_values = _array(object_value["conflicts"], "$.conflicts")

    if not requirement_values:
        _fail("INVALID_VALUE", "$.requirements", "must contain at least one normative requirement")

    return DiscoveryRecord(
        goal=_parse_clause(object_value["goal"], "$.goal", has_id=False, required_class=DecisionClass.GOAL),
        scope=tuple(
            _parse_clause(item, f"$.scope[{index}]", has_id=True, required_class=DecisionClass.SCOPE)
            for index, item in enumerate(scope_values)
        ),
        non_goals=tuple(
            _parse_clause(item, f"$.non_goals[{index}]", has_id=True, required_class=DecisionClass.NON_GOALS)
            for index, item in enumerate(non_goal_values)
        ),
        authorities=tuple(_parse_authority(item, f"$.authorities[{index}]") for index, item in enumerate(authority_values)),
        evidence=tuple(_parse_evidence(item, f"$.evidence[{index}]") for index, item in enumerate(evidence_values)),
        requirements=tuple(
            _parse_clause(item, f"$.requirements[{index}]", has_id=True, require_acceptance_bindings=True)
            for index, item in enumerate(requirement_values)
        ),
        acceptance_predicates=tuple(
            _parse_acceptance(item, f"$.acceptance_predicates[{index}]")
            for index, item in enumerate(acceptance_values)
        ),
        verifications=tuple(
            _parse_verification(item, f"$.verifications[{index}]")
            for index, item in enumerate(verification_values)
        ),
        trace=tuple(_parse_trace(item, f"$.trace[{index}]") for index, item in enumerate(trace_values)),
        unresolved_decisions=tuple(
            _parse_unresolved_decision(item, f"$.unresolved_decisions[{index}]")
            for index, item in enumerate(unresolved_values)
        ),
        conflicts=tuple(_parse_conflict(item, f"$.conflicts[{index}]") for index, item in enumerate(conflict_values)),
    )


def _reject_duplicate_ids(record: DiscoveryRecord) -> None:
    seen: dict[str, str] = {}
    groups: tuple[tuple[str, Sequence[Any]], ...] = (
        ("scope", record.scope),
        ("non_goals", record.non_goals),
        ("authorities", record.authorities),
        ("evidence", record.evidence),
        ("requirements", record.requirements),
        ("acceptance_predicates", record.acceptance_predicates),
        ("verifications", record.verifications),
        ("unresolved_decisions", record.unresolved_decisions),
        ("conflicts", record.conflicts),
    )
    for group_name, entries in groups:
        for index, entry in enumerate(entries):
            entry_id = entry.id
            previous = seen.get(entry_id)
            if previous is not None:
                _fail("DUPLICATE_ID", f"$.{group_name}[{index}].id", f"duplicates {previous}")
            seen[entry_id] = f"$.{group_name}[{index}].id"


def _validate_evidence_refs(clause: Clause, path: str, evidence_ids: frozenset[str], authority_ids: frozenset[str]) -> None:
    for evidence_ref in clause.evidence_refs:
        if evidence_ref in authority_ids:
            _fail("AUTHORITY_IS_NOT_EVIDENCE", path, f"{evidence_ref} is an authority, not evidence")
        if evidence_ref not in evidence_ids:
            _fail("UNKNOWN_REFERENCE", path, f"unknown evidence reference {evidence_ref}")


def _authority_covers(
    authority: Authority,
    decision_class: DecisionClass,
    scope: Iterable[str],
) -> bool:
    scope_values = set(scope)
    if decision_class not in authority.decision_classes or not scope_values <= set(authority.scope):
        return False
    return authority.kind is not AuthorityKind.CANONICAL_CONTRACT or scope_values <= set(authority.applicability or ())


def _mandatory_obligations(authorities: Iterable[Authority]) -> tuple[frozenset[str], frozenset[str]]:
    constraints: set[str] = set()
    preserved_behaviors: set[str] = set()
    for authority in authorities:
        constraints.update(authority.constraints)
        preserved_behaviors.update(authority.preserved_behaviors)
    return frozenset(constraints), frozenset(preserved_behaviors)


def _shared_applicable_dimensions(
    left: Authority,
    right: Authority,
) -> tuple[tuple[DecisionClass, str], ...]:
    return tuple(
        (decision_class, scope)
        for decision_class in sorted(
            set(left.decision_classes) & set(right.decision_classes),
            key=lambda value: value.value,
        )
        for scope in sorted(set(left.scope) & set(right.scope))
        if _authority_covers(left, decision_class, (scope,))
        and _authority_covers(right, decision_class, (scope,))
    )

def _validate_authority_register(record: DiscoveryRecord) -> dict[str, Authority]:
    authorities = {authority.id: authority for authority in record.authorities}
    for authority in record.authorities:
        for reference in (*authority.supersedes, *authority.conflicts_with):
            if reference not in authorities:
                _fail("UNKNOWN_REFERENCE", f"$.authorities[{authority.id}]", f"unknown authority reference {reference}")
        if authority.kind is AuthorityKind.BOUNDED_DELEGATION and authority.status is AuthorityStatus.ACTIVE:
            if not set(authority.decision_classes) <= IMPLEMENTER_DECISION_CLASSES:
                _fail("INVALID_DELEGATION", f"$.authorities[{authority.id}].decision_classes", "cannot delegate owner-only product decisions")
        for reference in authority.supersedes:
            target = authorities[reference]
            if target.status is not AuthorityStatus.SUPERSEDED:
                _fail(
                    "INVALID_SUPERSESSION",
                    f"$.authorities[{authority.id}].supersedes",
                    f"{reference} must have superseded status",
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(authority_id: str) -> None:
        if authority_id in visiting:
            _fail("SUPERSESSION_CYCLE", f"$.authorities[{authority_id}].supersedes", "supersession graph must be acyclic")
        if authority_id in visited:
            return
        visiting.add(authority_id)
        for target_id in authorities[authority_id].supersedes:
            visit(target_id)
        visiting.remove(authority_id)
        visited.add(authority_id)

    for authority_id in authorities:
        visit(authority_id)
    return authorities


def _validate_conflicts(record: DiscoveryRecord, authorities: Mapping[str, Authority]) -> None:
    resolution_coverage: set[
        tuple[frozenset[str], DecisionClass, str, tuple[str, ...], tuple[str, ...]]
    ] = set()
    for conflict in record.conflicts:
        path = f"$.conflicts[{conflict.id}]"
        conflict_authorities: list[Authority] = []
        for authority_ref in conflict.authority_refs:
            authority = authorities.get(authority_ref)
            if authority is None:
                _fail("UNKNOWN_REFERENCE", f"{path}.authority_refs", f"unknown authority reference {authority_ref}")
            conflict_authorities.append(authority)
        if conflict.status == "unresolved":
            _fail("UNRESOLVED_CONFLICT", path, "authority conflict requires an owner-authorized resolution")

        assert conflict.decision_class is not None
        assert conflict.winning_authority_ref is not None
        assert conflict.resolution_authority_ref is not None
        if conflict.winning_authority_ref not in conflict.authority_refs:
            _fail(
                "INVALID_CONFLICT_RESOLUTION",
                f"{path}.winning_authority_ref",
                "winner must be among conflicted authorities",
            )
        winner = authorities[conflict.winning_authority_ref]
        if winner.status is not AuthorityStatus.ACTIVE:
            _fail(
                "INACTIVE_AUTHORITY",
                f"{path}.winning_authority_ref",
                f"{winner.id} is {winner.status.value}",
            )
        resolution = authorities.get(conflict.resolution_authority_ref)
        if resolution is None:
            _fail("UNKNOWN_REFERENCE", f"{path}.resolution_authority_ref", "unknown resolution authority")
        if resolution.status is not AuthorityStatus.ACTIVE:
            _fail(
                "INACTIVE_AUTHORITY",
                f"{path}.resolution_authority_ref",
                f"{resolution.id} is {resolution.status.value}",
            )
        if resolution.kind is AuthorityKind.BOUNDED_DELEGATION:
            _fail(
                "OWNER_DECISION_REQUIRED",
                f"{path}.resolution_authority_ref",
                "a delegation cannot resolve an authority conflict",
            )

        mandatory_constraints, mandatory_behaviors = _mandatory_obligations(conflict_authorities)
        if set(conflict.constraints) != mandatory_constraints or set(conflict.preserved_behaviors) != mandatory_behaviors:
            _fail(
                "INVALID_CONFLICT_RESOLUTION",
                path,
                "conflict constraints and preserved behaviors must exactly cover every conflicted authority obligation",
            )
        for authority in conflict_authorities:
            if not _authority_covers(authority, conflict.decision_class, conflict.scope):
                _fail(
                    "AUTHORITY_SCOPE_MISMATCH",
                    f"{path}.authority_refs",
                    f"{authority.id} does not cover the conflict class and scope",
                )
        for authority, field in (
            (winner, "winning_authority_ref"),
            (resolution, "resolution_authority_ref"),
        ):
            if (
                not _authority_covers(authority, conflict.decision_class, conflict.scope)
                or set(authority.constraints) != mandatory_constraints
                or set(authority.preserved_behaviors) != mandatory_behaviors
            ):
                _fail(
                    "AUTHORITY_SCOPE_MISMATCH",
                    f"{path}.{field}",
                    f"{authority.id} does not preserve the complete conflict obligations",
                )

        constraints_key = tuple(sorted(mandatory_constraints))
        behaviors_key = tuple(sorted(mandatory_behaviors))
        for left_index, left in enumerate(conflict.authority_refs):
            for right in conflict.authority_refs[left_index + 1 :]:
                pair = frozenset((left, right))
                for scope in conflict.scope:
                    resolution_coverage.add(
                        (pair, conflict.decision_class, scope, constraints_key, behaviors_key)
                    )

    checked_pairs: set[frozenset[str]] = set()
    for authority in record.authorities:
        for reference in authority.conflicts_with:
            pair = frozenset((authority.id, reference))
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            other = authorities[reference]
            mandatory_constraints, mandatory_behaviors = _mandatory_obligations((authority, other))
            constraints_key = tuple(sorted(mandatory_constraints))
            behaviors_key = tuple(sorted(mandatory_behaviors))
            for decision_class, scope in _shared_applicable_dimensions(authority, other):
                key = (pair, decision_class, scope, constraints_key, behaviors_key)
                if key not in resolution_coverage:
                    _fail(
                        "UNRESOLVED_CONFLICT",
                        f"$.authorities[{authority.id}].conflicts_with",
                        f"conflict with {reference} is unresolved for {decision_class.value}/{scope}",
                    )


def _validate_canonical_precedence(
    record: DiscoveryRecord,
    authorities: Mapping[str, Authority],
) -> None:
    canonical_authorities = [
        authority
        for authority in record.authorities
        if authority.kind is AuthorityKind.CANONICAL_CONTRACT and authority.status is AuthorityStatus.ACTIVE
    ]
    for left_index, left in enumerate(canonical_authorities):
        assert left.precedence is not None
        for right in canonical_authorities[left_index + 1 :]:
            assert right.precedence is not None
            if left.precedence != right.precedence:
                continue
            shared_scope = set(left.scope) & set(left.applicability or ()) & set(right.scope) & set(right.applicability or ())
            shared_classes = set(left.decision_classes) & set(right.decision_classes)
            for decision_class in shared_classes:
                for scope in shared_scope:
                    owner_resolution_exists = any(
                        conflict.status == "resolved"
                        and left.id in conflict.authority_refs
                        and right.id in conflict.authority_refs
                        and conflict.decision_class is decision_class
                        and scope in conflict.scope
                        and authorities[conflict.resolution_authority_ref].kind is AuthorityKind.OWNER_DECISION
                        and authorities[conflict.resolution_authority_ref].status is AuthorityStatus.ACTIVE
                        and _authority_covers(left, decision_class, (scope,))
                        and _authority_covers(right, decision_class, (scope,))
                        for conflict in record.conflicts
                    )
                    if not owner_resolution_exists:
                        _fail(
                            "AMBIGUOUS_PRECEDENCE",
                            "$.authorities",
                            f"{left.id} and {right.id} have equal applicable precedence for {decision_class.value}/{scope}",
                        )


def _validate_clause_authority(
    clause: Clause,
    path: str,
    authorities: Mapping[str, Authority],
    evidence_ids: frozenset[str],
    conflicts: Sequence[Conflict],
) -> None:
    if not clause.authority_refs:
        _fail("MISSING_AUTHORITY", path, "normative clause has no authority reference")
    authority_ids = frozenset(authorities)
    _validate_evidence_refs(clause, path, evidence_ids, authority_ids)
    referenced_authorities: list[Authority] = []
    for authority_ref in clause.authority_refs:
        if authority_ref in evidence_ids:
            _fail("EVIDENCE_IS_NOT_AUTHORITY", path, f"{authority_ref} is evidence, not authority")
        authority = authorities.get(authority_ref)
        if authority is None:
            _fail("UNKNOWN_REFERENCE", path, f"unknown authority reference {authority_ref}")
        if authority.status is not AuthorityStatus.ACTIVE:
            _fail("INACTIVE_AUTHORITY", path, f"{authority_ref} is {authority.status.value}")
        referenced_authorities.append(authority)
        if clause.decision_class in OWNER_ONLY_DECISION_CLASSES and authority.kind is AuthorityKind.BOUNDED_DELEGATION:
            _fail("OWNER_DECISION_REQUIRED", path, f"{clause.decision_class.value} cannot be delegated")
        if not _authority_covers(authority, clause.decision_class, clause.scope):
            _fail(
                "AUTHORITY_SCOPE_MISMATCH",
                path,
                f"{authority_ref} does not cover the clause class and scope",
            )
        for conflict in conflicts:
            if (
                conflict.status == "resolved"
                and authority_ref in conflict.authority_refs
                and conflict.winning_authority_ref != authority_ref
                and conflict.decision_class is clause.decision_class
                and set(clause.scope) <= set(conflict.scope)
                and set(clause.constraints) <= set(conflict.constraints)
                and set(clause.preserved_behaviors) <= set(conflict.preserved_behaviors)
            ):
                _fail("STALE_AUTHORITY", path, f"{authority_ref} lost the applicable conflict resolution")
        if authority.kind is AuthorityKind.CANONICAL_CONTRACT:
            assert authority.precedence is not None
            for candidate in authorities.values():
                if (
                    candidate.kind is AuthorityKind.CANONICAL_CONTRACT
                    and candidate.status is AuthorityStatus.ACTIVE
                    and candidate.precedence is not None
                    and candidate.precedence > authority.precedence
                    and _authority_covers(candidate, clause.decision_class, clause.scope)
                ):
                    _fail("STALE_AUTHORITY", path, f"{authority_ref} is lower precedence than {candidate.id}")

    mandatory_constraints, mandatory_behaviors = _mandatory_obligations(referenced_authorities)
    if set(clause.constraints) != mandatory_constraints or set(clause.preserved_behaviors) != mandatory_behaviors:
        _fail(
            "AUTHORITY_SCOPE_MISMATCH",
            path,
            "clause constraints and preserved behaviors must exactly retain all referenced authority obligations",
        )


def _validate_acceptance_and_verification(record: DiscoveryRecord) -> None:
    requirements = {requirement.id: requirement for requirement in record.requirements}
    acceptances = {acceptance.id: acceptance for acceptance in record.acceptance_predicates}
    verifications = {verification.id: verification for verification in record.verifications}

    for acceptance in record.acceptance_predicates:
        if acceptance.requirement_ref not in requirements:
            _fail("UNKNOWN_REFERENCE", f"$.acceptance_predicates[{acceptance.id}].requirement_ref", "unknown requirement reference")
    for verification in record.verifications:
        if verification.requirement_ref not in requirements:
            _fail("UNKNOWN_REFERENCE", f"$.verifications[{verification.id}].requirement_ref", "unknown requirement reference")
        for acceptance_ref in verification.acceptance_refs:
            acceptance = acceptances.get(acceptance_ref)
            if acceptance is None:
                _fail("UNKNOWN_REFERENCE", f"$.verifications[{verification.id}].acceptance_refs", f"unknown acceptance reference {acceptance_ref}")
            if acceptance.requirement_ref != verification.requirement_ref:
                _fail("UNVERIFIABLE_REQUIREMENT", f"$.verifications[{verification.id}]", "verification crosses requirement boundaries")
            if verification.expected_result not in {acceptance.observable_result, acceptance.failure_result}:
                _fail(
                    "UNAUTHORIZED_EXPECTED_RESULT",
                    f"$.verifications[{verification.id}].expected_result",
                    f"must equal an authorized result from {acceptance_ref}",
                )

    for requirement in record.requirements:
        requirement_id = requirement.id
        assert requirement_id is not None
        path = f"$.requirements[{requirement_id}]"
        requirement_acceptances = [
            acceptance for acceptance in record.acceptance_predicates if acceptance.requirement_ref == requirement_id
        ]
        if not requirement_acceptances:
            _fail("ACCEPTANCE_INCOMPLETE", path, "requirement has no acceptance predicate")
        bound_acceptances: dict[str, AcceptanceBinding] = {}
        for binding in requirement.acceptance_bindings:
            acceptance = acceptances.get(binding.acceptance_ref)
            if acceptance is None:
                _fail("UNKNOWN_REFERENCE", f"{path}.acceptance_bindings", f"unknown acceptance reference {binding.acceptance_ref}")
            if acceptance.requirement_ref != requirement_id:
                _fail(
                    "ACCEPTANCE_BINDING_MISMATCH",
                    f"{path}.acceptance_bindings",
                    f"{binding.acceptance_ref} belongs to {acceptance.requirement_ref}",
                )
            bound_acceptances[binding.acceptance_ref] = binding
        expected_acceptance_ids = {acceptance.id for acceptance in requirement_acceptances}
        if set(bound_acceptances) != expected_acceptance_ids:
            _fail(
                "ACCEPTANCE_BINDING_MISMATCH",
                f"{path}.acceptance_bindings",
                "must bind every and only this requirement's acceptance predicates",
            )
        for acceptance in requirement_acceptances:
            binding = bound_acceptances[acceptance.id]
            expected_digest = acceptance_binding_digest(
                _clause_payload(requirement, include_id=True, include_acceptance_bindings=False),
                _acceptance_payload(acceptance),
            )
            if binding.digest != expected_digest:
                _fail(
                    "ACCEPTANCE_DIGEST_MISMATCH",
                    f"{path}.acceptance_bindings",
                    f"{acceptance.id} digest does not bind the normalized requirement core and complete predicate payload",
                )
            matching_verifications = [
                verification
                for verification in record.verifications
                if verification.requirement_ref == requirement_id and acceptance.id in verification.acceptance_refs
            ]
            if not matching_verifications:
                _fail("UNVERIFIABLE_REQUIREMENT", path, f"acceptance {acceptance.id} has no verification")
    authority_ids = frozenset(authority.id for authority in record.authorities)
    evidence_ids = frozenset(evidence.id for evidence in record.evidence)
    for index, row in enumerate(record.trace):
        path = f"$.trace[{index}]"
        if row.authority_ref in evidence_ids:
            _fail("EVIDENCE_IS_NOT_AUTHORITY", f"{path}.authority_ref", "evidence cannot be an authority trace reference")
        if row.authority_ref not in authority_ids:
            _fail("UNKNOWN_REFERENCE", f"{path}.authority_ref", "unknown authority reference")
        if row.requirement_ref not in requirements:
            _fail("UNKNOWN_REFERENCE", f"{path}.requirement_ref", "unknown requirement reference")
        if row.acceptance_ref not in acceptances:
            _fail("UNKNOWN_REFERENCE", f"{path}.acceptance_ref", "unknown acceptance reference")
        if row.verification_ref not in verifications:
            _fail("UNKNOWN_REFERENCE", f"{path}.verification_ref", "unknown verification reference")

    trace_rows = {
        (row.authority_ref, row.requirement_ref, row.acceptance_ref, row.verification_ref)
        for row in record.trace
    }
    if len(trace_rows) != len(record.trace):
        _fail("DUPLICATE_TRACE", "$.trace", "must not contain duplicate trace rows")

    expected_rows: set[tuple[str, str, str, str]] = set()
    for requirement in record.requirements:
        requirement_id = requirement.id
        assert requirement_id is not None
        for acceptance in record.acceptance_predicates:
            if acceptance.requirement_ref != requirement_id:
                continue
            for verification in record.verifications:
                if verification.requirement_ref != requirement_id or acceptance.id not in verification.acceptance_refs:
                    continue
                for authority_ref in requirement.authority_refs:
                    expected_rows.add((authority_ref, requirement_id, acceptance.id, verification.id))
    for row in trace_rows:
        if row not in expected_rows:
            _fail("TRACE_INVALID", "$.trace", "trace row does not bind an authorized requirement, acceptance, and verification")
    missing_rows = sorted(expected_rows - trace_rows)
    if missing_rows:
        authority_ref, requirement_ref, acceptance_ref, verification_ref = missing_rows[0]
        _fail(
            "TRACE_INCOMPLETE",
            "$.trace",
            f"missing {authority_ref} -> {requirement_ref} -> {acceptance_ref} -> {verification_ref}",
        )


def _source_payload(source: SourceRef) -> dict[str, str]:
    return {"uri": source.uri, "version": source.version}
def _delegation_boundary_payload(boundary: DelegationBoundary) -> dict[str, Any]:
    return {
        "kind": boundary.kind.value,
        "includes": sorted(boundary.includes),
        "excludes": sorted(boundary.excludes),
    }




def _authority_payload(authority: Authority) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": authority.id,
        "kind": authority.kind.value,
        "status": authority.status.value,
        "source": _source_payload(authority.source),
        "scope": sorted(authority.scope),
        "constraints": sorted(authority.constraints),
        "preserved_behaviors": sorted(authority.preserved_behaviors),
        "decision_classes": sorted(value.value for value in authority.decision_classes),
        "statement": authority.statement,
        "supersedes": sorted(authority.supersedes),
        "conflicts_with": sorted(authority.conflicts_with),
    }
    if authority.owner is not None:
        payload["owner"] = authority.owner
    if authority.canonical_artifact is not None:
        payload["canonical_artifact"] = authority.canonical_artifact
        assert authority.applicability is not None
        assert authority.precedence is not None
        payload["applicability"] = sorted(authority.applicability)
        payload["precedence"] = authority.precedence
    if authority.delegate is not None:
        payload["delegate"] = authority.delegate
        assert authority.delegation_boundary is not None
        payload["delegation_boundary"] = _delegation_boundary_payload(authority.delegation_boundary)
        payload["non_transferable"] = True
    return payload


def _clause_payload(
    clause: Clause,
    *,
    include_id: bool,
    include_acceptance_bindings: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": clause.text,
        "decision_class": clause.decision_class.value,
        "scope": sorted(clause.scope),
        "constraints": sorted(clause.constraints),
        "preserved_behaviors": sorted(clause.preserved_behaviors),
        "authority_refs": sorted(clause.authority_refs),
        "evidence_refs": sorted(clause.evidence_refs),
    }
    if include_id:
        assert clause.id is not None
        payload["id"] = clause.id
    if include_acceptance_bindings:
        payload["acceptance_bindings"] = [
            {"acceptance_ref": binding.acceptance_ref, "digest": binding.digest}
            for binding in sorted(clause.acceptance_bindings, key=lambda binding: binding.acceptance_ref)
        ]
    return payload


def _acceptance_payload(acceptance: AcceptancePredicate) -> dict[str, str]:
    return asdict(acceptance)


def _verification_payload(verification: Verification) -> dict[str, Any]:
    return {
        "id": verification.id,
        "requirement_ref": verification.requirement_ref,
        "acceptance_refs": sorted(verification.acceptance_refs),
        "method": verification.method.value,
        "procedure": verification.procedure,
        "expected_result": verification.expected_result,
    }


def _trace_payload(trace: TraceRow) -> dict[str, str]:
    return asdict(trace)


def _delegation_payload(authority: Authority) -> dict[str, Any]:
    assert authority.delegate is not None
    assert authority.delegation_boundary is not None
    return {
        "id": authority.id,
        "authority_ref": authority.id,
        "delegate": authority.delegate,
        "non_transferable": True,
        "delegation_boundary": _delegation_boundary_payload(authority.delegation_boundary),
        "decision_classes": sorted(value.value for value in authority.decision_classes),
        "scope": sorted(authority.scope),
        "constraints": sorted(authority.constraints),
        "preserved_behaviors": sorted(authority.preserved_behaviors),
        "statement": authority.statement,
        "source": _source_payload(authority.source),
    }


def compile_discovery_record(value: Any) -> dict[str, Any]:
    """Validate and seal a Discovery Record, or raise :class:`CompilerError`.

    The function does not read files, write files, inspect a repository, or infer
    decisions.  It is consequently safe to call in tests and from any coding agent.
    """

    record = _parse_record(value)
    _reject_duplicate_ids(record)
    authorities = _validate_authority_register(record)
    if record.unresolved_decisions:
        first = record.unresolved_decisions[0]
        _fail("UNRESOLVED_DECISION", f"$.unresolved_decisions[{first.id}]", "owner decision remains open")
    _validate_conflicts(record, authorities)
    _validate_canonical_precedence(record, authorities)

    evidence_ids = frozenset(evidence.id for evidence in record.evidence)
    for clause, path in ((record.goal, "$.goal"),):
        _validate_clause_authority(clause, path, authorities, evidence_ids, record.conflicts)
    for index, clause in enumerate(record.scope):
        _validate_clause_authority(clause, f"$.scope[{index}]", authorities, evidence_ids, record.conflicts)
    for index, clause in enumerate(record.non_goals):
        _validate_clause_authority(clause, f"$.non_goals[{index}]", authorities, evidence_ids, record.conflicts)
    for index, clause in enumerate(record.requirements):
        _validate_clause_authority(clause, f"$.requirements[{index}]", authorities, evidence_ids, record.conflicts)

    _validate_acceptance_and_verification(record)


    implementation_decision_policy = {
        "log_path": ".ultimateinterview/<session>/decision.jsonl",
        "instruction": (
            "When the Build Contract is insufficient and implementation would otherwise require "
            "an arbitrary decision, append one JSON object per decision to decision.jsonl before acting."
        ),
        "required_fields": [
            "contract_digest",
            "requirement_refs",
            "gap",
            "decision",
            "rationale",
            "alternatives",
            "affected_paths",
            "observable_impact",
        ],
        "authority_boundary": (
            "The log is evidence, not authority. A user-visible, policy, scope, lifecycle, failure, "
            "compatibility, data-loss, or out-of-delegation decision must stop implementation and "
            "return to the owner for authority and a newly compiled contract."
        ),
    }
    contract: dict[str, Any] = {
        "implementation_decision_policy": implementation_decision_policy,
        "schema": BUILD_CONTRACT_SCHEMA,
        "source_discovery_digest": sha256_canonical_json(value),
        "goal": _clause_payload(record.goal, include_id=False),
        "scope": sorted((_clause_payload(clause, include_id=True) for clause in record.scope), key=lambda item: item["id"]),
        "non_goals": sorted(
            (_clause_payload(clause, include_id=True) for clause in record.non_goals),
            key=lambda item: item["id"],
        ),
        "authorities": sorted((_authority_payload(authority) for authority in record.authorities), key=lambda item: item["id"]),
        "requirements": sorted(
            (
                _clause_payload(requirement, include_id=True, include_acceptance_bindings=True)
                for requirement in record.requirements
            ),
            key=lambda item: item["id"],
        ),
        "bounded_implementation_delegations": sorted(
            (
                _delegation_payload(authority)
                for authority in record.authorities
                if authority.kind is AuthorityKind.BOUNDED_DELEGATION and authority.status is AuthorityStatus.ACTIVE
            ),
            key=lambda item: item["id"],
        ),
        "acceptance_predicates": sorted(
            (_acceptance_payload(acceptance) for acceptance in record.acceptance_predicates),
            key=lambda item: item["id"],
        ),
        "verifications": sorted(
            (_verification_payload(verification) for verification in record.verifications),
            key=lambda item: item["id"],
        ),
        "trace": sorted(
            (_trace_payload(trace) for trace in record.trace),
            key=lambda item: (
                item["authority_ref"],
                item["requirement_ref"],
                item["acceptance_ref"],
                item["verification_ref"],
            ),
        ),
        "unresolved_decisions": [],
    }
    contract["contract_digest"] = contract_digest(contract)
    return contract


def _strict_json_loads(text: str) -> Any:
    def reject_constant(token: str) -> None:
        raise CompilerError("INVALID_JSON", "$", f"non-finite JSON value {token} is not allowed")

    def reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                _fail("DUPLICATE_JSON_KEY", "$", f"duplicate object key {key}")
            result[key] = item
        return result

    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_object_keys,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise CompilerError("INVALID_JSON", "$", f"malformed JSON at line {error.lineno}, column {error.colno}") from error


def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    if not parent.is_dir():
        _fail("OUTPUT_ERROR", str(path), "output parent directory does not exist")
    if path.exists() and path.is_dir():
        _fail("OUTPUT_ERROR", str(path), "output path is a directory")

    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    except OSError as error:
        _fail("OUTPUT_ERROR", str(path), f"could not create temporary output: {error.strerror or error}")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        _fail("OUTPUT_ERROR", str(path), f"atomic write failed: {error.strerror or error}")
    finally:
        try:
            temporary_path.unlink()
        except OSError:
            pass

    # Durability confirmation is best-effort.  Once replace succeeded, reporting
    # a later directory-sync failure would falsely claim failure after changing
    # the output path.
    try:
        directory_descriptor = os.open(parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(directory_descriptor)
        except OSError:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="authority_compiler.py",
        description="Compile a Discovery Record into a sealed Build Contract.",
    )
    parser.add_argument("discovery", type=Path, help="Discovery Record JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Build Contract JSON output file")
    arguments = parser.parse_args(argv)

    try:
        if not arguments.discovery.is_file():
            _fail("INPUT_ERROR", str(arguments.discovery), "input is not a file")
        try:
            input_text = arguments.discovery.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            _fail("INPUT_ERROR", str(arguments.discovery), f"could not read input: {error}")
        contract = compile_discovery_record(_strict_json_loads(input_text))
        _atomic_write(arguments.output, pretty_json(contract))
    except CompilerError as error:
        print(f"authority-compiler: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
