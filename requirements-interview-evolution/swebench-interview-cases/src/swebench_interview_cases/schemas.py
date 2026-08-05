"""Closed, versioned artifact validation for the SWE-bench interview pilot."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

SOURCE_VALUES = frozenset({"issue", "repository", "test", "patch", "inferred"})
KNOWLEDGE_TIMING_VALUES = frozenset(
    {
        "issue_time_author_knowable",
        "repository_discoverable",
        "implementation_time",
        "hindsight_only",
    }
)
PARTITION_VALUES = frozenset({"development", "validation", "holdout"})
STATUS_VALUES = frozenset(
    {"draft", "approved", "excluded", "human_review_required", "invalidated"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SchemaError(ValueError):
    """Raised when an artifact violates a closed schema."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def artifact_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _object(
    value: Any, path: str, required: set[str], optional: set[str] | None = None
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{path} must be an object")
    keys = set(value)
    missing = required - keys
    unknown = keys - required - (optional or set())
    if missing:
        raise SchemaError(f"{path} is missing fields: {sorted(missing)}")
    if unknown:
        raise SchemaError(f"{path} has unknown fields: {sorted(unknown)}")
    return value


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise SchemaError(f"{path} must be a non-empty string")
    return value


def _digest(value: Any, path: str) -> str:
    text = _string(value, path)
    if not SHA256_RE.fullmatch(text):
        raise SchemaError(f"{path} must be a lowercase SHA-256 digest")
    return text


def _list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{path} must be an array")
    return value


def _evidence(value: Any, path: str) -> None:
    item = _object(
        value,
        path,
        {"id", "source", "knowledge_timing", "source_digest", "locator", "excerpt", "excerpt_digest", "cache_required"},
    )
    _string(item["id"], f"{path}.id")
    if item["source"] not in SOURCE_VALUES:
        raise SchemaError(f"{path}.source is invalid")
    if item["knowledge_timing"] not in KNOWLEDGE_TIMING_VALUES:
        raise SchemaError(f"{path}.knowledge_timing is invalid")
    _digest(item["source_digest"], f"{path}.source_digest")
    _string(item["locator"], f"{path}.locator")
    excerpt = _string(item["excerpt"], f"{path}.excerpt", nonempty=False)
    if len(excerpt.encode("utf-8")) > 2048 or len(excerpt.splitlines()) > 20:
        raise SchemaError(f"{path}.excerpt exceeds the committed evidence limit")
    if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != item["excerpt_digest"]:
        raise SchemaError(f"{path}.excerpt_digest does not match excerpt")
    if not isinstance(item["cache_required"], bool):
        raise SchemaError(f"{path}.cache_required must be boolean")


def validate_public_case(value: Any) -> None:
    case = _object(
        value,
        "$",
        {"schema", "alias", "upstream", "public_request", "repository_facts", "metadata", "sealed_source_digest"},
    )
    if case["schema"] != "InterviewerSafeCase.v1":
        raise SchemaError("$.schema is invalid")
    _string(case["alias"], "$.alias")
    upstream = _object(case["upstream"], "$.upstream", {"dataset", "revision", "instance_id_digest", "base_commit", "source_url", "issue_digest", "issue_cache_key"})
    for name in ("dataset", "revision", "base_commit", "source_url", "issue_cache_key"):
        _string(upstream[name], f"$.upstream.{name}")
    for name in ("instance_id_digest", "issue_digest"):
        _digest(upstream[name], f"$.upstream.{name}")
    request = _object(case["public_request"], "$.public_request", {"cache_key", "digest"})
    _string(request["cache_key"], "$.public_request.cache_key")
    _digest(request["digest"], "$.public_request.digest")
    if request["cache_key"] != f"sha256:{request['digest']}":
        raise SchemaError("$.public_request cache key and digest differ")
    for index, fact in enumerate(_list(case["repository_facts"], "$.repository_facts")):
        entry = _object(fact, f"$.repository_facts[{index}]", {"id", "statement", "evidence"})
        _string(entry["id"], f"$.repository_facts[{index}].id")
        _string(entry["statement"], f"$.repository_facts[{index}].statement")
        for evidence_index, evidence in enumerate(_list(entry["evidence"], f"$.repository_facts[{index}].evidence")):
            _evidence(evidence, f"$.repository_facts[{index}].evidence[{evidence_index}]")
    metadata = _object(case["metadata"], "$.metadata", {"context_mode", "repository_family", "partition"})
    _string(metadata["context_mode"], "$.metadata.context_mode")
    _string(metadata["repository_family"], "$.metadata.repository_family")
    if metadata["partition"] not in PARTITION_VALUES:
        raise SchemaError("$.metadata.partition is invalid")
    _digest(case["sealed_source_digest"], "$.sealed_source_digest")


def validate_sealed_source(value: Any) -> None:
    sealed = _object(
        value,
        "$",
        {"schema", "alias", "inputs", "evidence", "material_decisions", "hindsight_observations", "implementation_incidentals", "review_state"},
    )
    if sealed["schema"] != "SealedSWEbenchSource.v1":
        raise SchemaError("$.schema is invalid")
    _string(sealed["alias"], "$.alias")
    inputs = _object(sealed["inputs"], "$.inputs", {"issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass"})
    for name, descriptor in inputs.items():
        item = _object(descriptor, f"$.inputs.{name}", {"cache_key", "digest"})
        _string(item["cache_key"], f"$.inputs.{name}.cache_key")
        _digest(item["digest"], f"$.inputs.{name}.digest")
        if item["cache_key"] != f"sha256:{item['digest']}":
            raise SchemaError(f"$.inputs.{name} cache key and digest differ")
    evidence_ids: set[str] = set()
    evidence_sources: dict[str, str] = {}
    evidence_timing: dict[str, str] = {}
    for index, evidence in enumerate(_list(sealed["evidence"], "$.evidence")):
        _evidence(evidence, f"$.evidence[{index}]")
        evidence_id = str(evidence["id"])
        if evidence_id in evidence_ids:
            raise SchemaError("$.evidence contains duplicate IDs")
        evidence_ids.add(evidence_id)
        evidence_sources[evidence_id] = str(evidence["source"])
        evidence_timing[evidence_id] = str(evidence["knowledge_timing"])
    decisions = _list(sealed["material_decisions"], "$.material_decisions")
    for index, decision in enumerate(decisions):
        path = f"$.material_decisions[{index}]"
        item = _object(decision, path, {"id", "description", "sources", "knowledge_timing", "materiality", "owner_answer", "question_intent", "failure_if_missed", "evidence_ids"})
        for name in ("id", "description", "materiality", "owner_answer", "question_intent", "failure_if_missed"):
            _string(item[name], f"{path}.{name}")
        sources = _list(item["sources"], f"{path}.sources")
        if not sources or any(source not in SOURCE_VALUES for source in sources):
            raise SchemaError(f"{path}.sources contains invalid provenance")
        if item["knowledge_timing"] not in KNOWLEDGE_TIMING_VALUES:
            raise SchemaError(f"{path}.knowledge_timing is invalid")
        cited_ids = _list(item["evidence_ids"], f"{path}.evidence_ids")
        if not cited_ids:
            raise SchemaError(f"{path}.evidence_ids must not be empty")
        for evidence_id in cited_ids:
            _string(evidence_id, f"{path}.evidence_ids[]")
            if evidence_id not in evidence_ids:
                raise SchemaError(f"{path} cites unknown evidence: {evidence_id}")
        if not set(item["sources"]).issubset({evidence_sources[str(value)] for value in cited_ids} | {"inferred"}):
            raise SchemaError(f"{path}.sources are not supported by cited evidence")
        timing_order = {
            "issue_time_author_knowable": 0, "repository_discoverable": 1,
            "implementation_time": 2, "hindsight_only": 3,
        }
        latest_evidence = max(timing_order[evidence_timing[str(value)]] for value in cited_ids)
        if timing_order[str(item["knowledge_timing"])] < latest_evidence:
            raise SchemaError(f"{path}.knowledge_timing predates its cited evidence")
    for field in ("hindsight_observations", "implementation_incidentals"):
        for index, item in enumerate(_list(sealed[field], f"$.{field}")):
            entry = _object(item, f"$.{field}[{index}]", {"id", "description", "evidence_ids"})
            _string(entry["id"], f"$.{field}[{index}].id")
            _string(entry["description"], f"$.{field}[{index}].description")
            cited = _list(entry["evidence_ids"], f"$.{field}[{index}].evidence_ids")
            if not cited or any(value not in evidence_ids for value in cited):
                raise SchemaError(f"$.{field}[{index}] has missing or unknown evidence")
    review = _object(sealed["review_state"], "$.review_state", {"status", "dispositions_complete"})
    if review["status"] not in STATUS_VALUES:
        raise SchemaError("$.review_state.status is invalid")
    if not isinstance(review["dispositions_complete"], bool):
        raise SchemaError("$.review_state.dispositions_complete must be boolean")
    if review["status"] == "approved" and not review["dispositions_complete"]:
        raise SchemaError("approved sealed source must have complete dispositions")


def validate_partition_index(value: Any) -> None:
    index = _object(value, "$", {"schema", "partition", "cases"})
    if index["schema"] != "SWEbenchPartitionIndex.v1":
        raise SchemaError("$.schema is invalid")
    if index["partition"] not in PARTITION_VALUES:
        raise SchemaError("$.partition is invalid")
    families: set[str] = set()
    for offset, case in enumerate(_list(index["cases"], "$.cases")):
        item = _object(case, f"$.cases[{offset}]", {"alias", "repository_family", "case_digest", "status"})
        _string(item["alias"], f"$.cases[{offset}].alias")
        family = _string(item["repository_family"], f"$.cases[{offset}].repository_family")
        families.add(family)
        _digest(item["case_digest"], f"$.cases[{offset}].case_digest")
        if item["status"] not in STATUS_VALUES:
            raise SchemaError(f"$.cases[{offset}].status is invalid")


def validate_no_cross_partition_family_overlap(indexes: Sequence[Mapping[str, Any]]) -> None:
    owner: dict[str, str] = {}
    for index in indexes:
        validate_partition_index(index)
        partition = str(index["partition"])
        for case in index["cases"]:
            family = str(case["repository_family"])
            previous = owner.setdefault(family, partition)
            if previous != partition:
                raise SchemaError(
                    f"repository family {family!r} occurs in both {previous} and {partition}"
                )


def validate_case_pair(public_case: Any, sealed_source: Any) -> None:
    """Validate both layers and their immutable lineage binding."""

    validate_public_case(public_case)
    validate_sealed_source(sealed_source)
    if public_case["alias"] != sealed_source["alias"]:
        raise SchemaError("public and sealed aliases differ")
    actual = artifact_digest(sealed_source)
    if public_case["sealed_source_digest"] != actual:
        raise SchemaError("sealed source digest drift detected")


VALIDATORS = {
    "public_case": validate_public_case,
    "sealed_source": validate_sealed_source,
    "partition_index": validate_partition_index,
}


def validate_artifact(kind: str, value: Any) -> None:
    try:
        validator = VALIDATORS[kind]
    except KeyError as exc:
        raise SchemaError(f"unknown artifact kind: {kind}") from exc
    validator(value)
