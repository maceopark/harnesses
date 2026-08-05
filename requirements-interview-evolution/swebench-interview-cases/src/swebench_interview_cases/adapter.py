"""Role-scoped projections for imported SWE-bench interview cases."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
from typing import Any

from .schemas import validate_case_pair, validate_public_case


class ProjectionError(ValueError):
    """Raised when a role projection would cross an information boundary."""


PUBLIC_ROLES = frozenset(
    {"repository-discovery", "evidence-auditor", "interviewer", "adversarial-reviewer"}
)
SEALED_ROLES = frozenset({"owner", "judge", "adjudicator"})
MUTATOR_ROLE = "development-mutator"
ROLES = PUBLIC_ROLES | SEALED_ROLES | {MUTATOR_ROLE}
BLIND_FAILURE_TAXONOMY = (
    "omission",
    "invention",
    "repository-delegation",
    "synthesis-loss",
    "unverifiable-acceptance",
    "compatibility-regression",
    "implementation-leakage",
    "redundant-question",
)

FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "sealed_source",
        "sealed-source",
        "gold_patch",
        "patch",
        "test_patch",
        "fail_to_pass",
        "pass_to_pass",
        "owner_answer",
        "owner_oracle",
        "material_decisions",
        "hindsight_observations",
        "implementation_incidentals",
        "expected_omission",
        "expected_failure",
        "failure_trap",
    }
)


def _assert_no_forbidden_keys(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            forbidden = {item.replace("-", "_") for item in FORBIDDEN_PUBLIC_KEYS}
            if normalized in forbidden:
                raise ProjectionError(f"forbidden sealed key at {path}.{key}")
            _assert_no_forbidden_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_keys(child, path=f"{path}[{index}]")


def _public_base(public_case: Mapping[str, Any], public_request_text: str) -> dict[str, Any]:
    if not public_request_text:
        raise ProjectionError("public_request_text is required from the verified cache")
    actual_digest = hashlib.sha256(public_request_text.encode("utf-8")).hexdigest()
    if actual_digest != public_case["public_request"]["digest"]:
        raise ProjectionError("public request text digest does not match public case")
    return {
        "alias": public_case["alias"],
        "public_request": public_request_text,
        "upstream": deepcopy(public_case["upstream"]),
        "repository_facts": deepcopy(public_case["repository_facts"]),
        "metadata": deepcopy(public_case["metadata"]),
    }


def project_role_payload(
    role: str,
    *,
    public_case: Mapping[str, Any],
    public_request_text: str,
    runtime: Mapping[str, Any] | None = None,
    sealed_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fresh role payload from explicit allowlists.

    The caller must resolve and digest-check ``public_request_text`` from cache.
    A sealed source is mandatory only for Owner/Judge/Adjudicator and is never
    copied wholesale into any payload.
    """

    if role not in ROLES:
        raise ProjectionError(f"unknown imported-case role: {role}")
    validate_public_case(public_case)
    runtime = runtime or {}
    base = _public_base(public_case, public_request_text)

    if role in SEALED_ROLES:
        if sealed_source is None:
            raise ProjectionError(f"{role} requires sealed_source")
        try:
            validate_case_pair(public_case, sealed_source)
        except ValueError as exc:
            raise ProjectionError(str(exc)) from exc

    if role == "repository-discovery":
        payload = {
            **{key: base[key] for key in ("alias", "public_request", "upstream", "metadata")},
            "repository_root": deepcopy(runtime.get("repository_root")),
        }
    elif role == "evidence-auditor":
        payload = {**base, "discovery": deepcopy(runtime.get("discovery", {}))}
    elif role == "interviewer":
        payload = {
            **base, "candidate_skill": deepcopy(runtime.get("candidate_skill", {})),
            "audited_repository_evidence": deepcopy(runtime.get("audited_repository_evidence", {})),
            "transcript": deepcopy(runtime.get("transcript", [])),
        }
    elif role == "adversarial-reviewer":
        payload = {
            **base,
            "transcript": deepcopy(runtime.get("transcript", [])),
            "contract": deepcopy(runtime.get("contract", {})),
            "audited_repository_evidence": deepcopy(runtime.get("audited_repository_evidence", {})),
            "failure_taxonomy": list(BLIND_FAILURE_TAXONOMY),
        }
    elif role == "owner":
        decisions = [
            deepcopy(item)
            for item in sealed_source["material_decisions"]  # type: ignore[index]
            if item["knowledge_timing"] == "issue_time_author_knowable"
        ]
        payload = {"alias": base["alias"], "question": deepcopy(runtime.get("question")), "owner_oracle": decisions}
    elif role in {"judge", "adjudicator"}:
        payload = {
            **base,
            "transcript": deepcopy(runtime.get("transcript", [])),
            "contract": deepcopy(runtime.get("contract", {})),
            "sealed_inputs": deepcopy(sealed_source["inputs"]),  # type: ignore[index]
            "sealed_evidence": deepcopy(sealed_source["evidence"]),  # type: ignore[index]
            "material_decisions": deepcopy(sealed_source["material_decisions"]),  # type: ignore[index]
            "hindsight_observations": deepcopy(sealed_source["hindsight_observations"]),  # type: ignore[index]
            "implementation_incidentals": deepcopy(sealed_source["implementation_incidentals"]),  # type: ignore[index]
            "review_state": deepcopy(sealed_source["review_state"]),  # type: ignore[index]
        }
        if role == "adjudicator":
            payload["findings"] = deepcopy(runtime.get("findings", []))
    else:
        # Mutator receives only already-approved generalized readiness summaries.
        summaries = deepcopy(runtime.get("approved_failure_summaries", []))
        payload = {"candidate_skill": deepcopy(runtime.get("candidate_skill", {})), "approved_failure_summaries": summaries}

    if role in PUBLIC_ROLES or role == MUTATOR_ROLE:
        _assert_no_forbidden_keys(payload)
    return payload
