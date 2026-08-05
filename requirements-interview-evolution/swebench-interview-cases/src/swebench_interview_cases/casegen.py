"""Gold-informed case derivation and independent two-reviewer approval."""

from __future__ import annotations

import hashlib
import copy
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .cache import ContentAddressedCache
from .leakage import audit_public_payload, patch_only_sentinels
from .model import CodexJsonModel
from .review import DecisionDisposition, ReviewDecision, unanimous_disposition
from .schemas import artifact_digest, validate_case_pair


DECISION = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "description", "sources", "knowledge_timing", "materiality", "owner_answer", "question_intent", "failure_if_missed", "evidence_ids"],
    "properties": {
        "id": {"type": "string"}, "description": {"type": "string"},
        "sources": {"type": "array", "minItems": 1, "items": {"enum": ["issue", "repository", "test", "patch", "inferred"]}},
        "knowledge_timing": {"enum": ["issue_time_author_knowable", "repository_discoverable", "implementation_time", "hindsight_only"]},
        "materiality": {"type": "string"}, "owner_answer": {"type": "string"},
        "question_intent": {"type": "string"}, "failure_if_missed": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
}

OBSERVATION = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "description", "evidence_ids"],
    "properties": {"id": {"type": "string"}, "description": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
}

DERIVATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["material_decisions", "hindsight_observations", "implementation_incidentals"],
    "properties": {
        "material_decisions": {"type": "array", "minItems": 0, "items": DECISION},
        "hindsight_observations": {"type": "array", "items": OBSERVATION},
        "implementation_incidentals": {"type": "array", "items": OBSERVATION},
    },
}

REVIEW_ITEM = {
    "type": "object", "additionalProperties": False,
    "required": ["decision_id", "material", "issue_time_knowable", "implementation_independent", "separated_from_repository_fact", "leakage_free", "reason"],
    "properties": {
        "decision_id": {"type": "string"},
        **{name: {"enum": ["approve", "reject", "uncertain"]} for name in ("material", "issue_time_knowable", "implementation_independent", "separated_from_repository_fact", "leakage_free")},
        "reason": {"type": "string"},
    },
}

REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["dispositions", "classified_items", "semantic_leakage_free", "alternative_implementation_satisfied", "summary"],
    "properties": {
        "dispositions": {"type": "array", "minItems": 0, "items": REVIEW_ITEM},
        "classified_items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["item_id", "classification", "provenance_supported", "classification_correct", "leakage_free", "reason"],
            "properties": {
                "item_id": {"type": "string"},
                "classification": {"enum": ["hindsight_observation", "implementation_incidental"]},
                "provenance_supported": {"type": "boolean"}, "classification_correct": {"type": "boolean"},
                "leakage_free": {"type": "boolean"}, "reason": {"type": "string"},
            },
        }},
        "semantic_leakage_free": {"type": "boolean"},
        "alternative_implementation_satisfied": {"type": "boolean"},
        "summary": {"type": "string"},
    },
}


def _read(cache: ContentAddressedCache, descriptor: Mapping[str, str]) -> str:
    return cache.get_text(descriptor["cache_key"], descriptor["digest"])


def _excerpt(text: str) -> str:
    lines = text.splitlines()[:20]
    value = "\n".join(lines)
    encoded = value.encode("utf-8")[:2048]
    while True:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]


def _evidence(
    evidence_id: str, source: str, timing: str, digest: str, locator: str, text: str,
    *, cache_required: bool = True,
) -> dict[str, Any]:
    excerpt = _excerpt(text)
    return {
        "id": evidence_id, "source": source, "knowledge_timing": timing,
        "source_digest": digest, "locator": locator, "excerpt": excerpt,
        "excerpt_digest": hashlib.sha256(excerpt.encode()).hexdigest(),
        "cache_required": cache_required,
    }


def _repository_context(
    *, issue: str, repo_root: Path, record_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from .imported_native import AUDIT_SCHEMA, DISCOVERY_SCHEMA, _audited_evidence, _validate_discovery

    discovery_model = CodexJsonModel(record_root / "repository-discovery")
    discovery = discovery_model.generate(
        role="case-repository-discovery",
        instructions=(
            "Inspect the base-commit repository for existing facts material to the issue. Cite exact "
            "repository-relative paths and inclusive line ranges of at most 20 lines. Do not infer future "
            "requirements or owner choices."
        ),
        payload={"issue": issue, "repository_root": str(repo_root.resolve())},
        schema=DISCOVERY_SCHEMA, readable_directories=(repo_root,),
    )
    _validate_discovery(repo_root, discovery)
    audit_model = CodexJsonModel(record_root / "repository-auditor")
    audit = audit_model.generate(
        role="case-repository-auditor",
        instructions="Re-open and independently disposition every cited fact. Accept only directly supported repository facts.",
        payload={"issue": issue, "discovery": discovery}, schema=AUDIT_SCHEMA,
        readable_directories=(repo_root,),
    )
    accepted = _audited_evidence(discovery, audit)
    public_facts: list[dict[str, Any]] = []
    sealed_evidence: list[dict[str, Any]] = []
    for fact in accepted["facts"]:
        path = repo_root / fact["path"]
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        cited = "\n".join(lines[fact["line_start"] - 1:fact["line_end"]])
        evidence_id = f"repository:{fact['id']}"
        evidence = _evidence(
            evidence_id, "repository", "repository_discoverable",
            hashlib.sha256(path.read_bytes()).hexdigest(),
            f"{fact['path']}:L{fact['line_start']}-L{fact['line_end']}", cited,
        )
        public_facts.append({"id": fact["id"], "statement": fact["statement"], "evidence": [evidence]})
        sealed_evidence.append(evidence)
    return public_facts, sealed_evidence


def derive_and_review_case(
    *, slot: Mapping[str, Any], cache: ContentAddressedCache, record_root: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    inputs = slot["sealed_inputs"]
    issue = _read(cache, inputs["issue"])
    sources = {name: _read(cache, descriptor) for name, descriptor in inputs.items()}
    repository_facts, repository_evidence = _repository_context(
        issue=issue, repo_root=repo_root, record_root=record_root
    )
    evidence = [
        _evidence("issue", "issue", "issue_time_author_knowable", inputs["issue"]["digest"], inputs["issue"]["cache_key"], issue),
        _evidence("gold-patch", "patch", "hindsight_only", inputs["gold_patch"]["digest"], inputs["gold_patch"]["cache_key"], sources["gold_patch"]),
        _evidence("test-patch", "test", "hindsight_only", inputs["test_patch"]["digest"], inputs["test_patch"]["cache_key"], sources["test_patch"]),
        _evidence("fail-to-pass", "test", "hindsight_only", inputs["fail_to_pass"]["digest"], inputs["fail_to_pass"]["cache_key"], sources["fail_to_pass"]),
        _evidence("pass-to-pass", "test", "hindsight_only", inputs["pass_to_pass"]["digest"], inputs["pass_to_pass"]["cache_key"], sources["pass_to_pass"]),
        *repository_evidence,
    ]
    evidence_ids = [item["id"] for item in evidence]
    derivation_schema = copy.deepcopy(DERIVATION_SCHEMA)
    derivation_schema["properties"]["material_decisions"]["items"]["properties"]["evidence_ids"] = {
        "type": "array", "minItems": 1, "items": {"enum": evidence_ids}
    }
    for name in ("hindsight_observations", "implementation_incidentals"):
        derivation_schema["properties"][name]["items"]["properties"]["evidence_ids"] = {
            "type": "array", "minItems": 1, "items": {"enum": evidence_ids}
        }
    generator = CodexJsonModel(record_root / "generator")
    derived = generator.generate(
        role="gold-informed-case-generator",
        instructions=(
            "Use the issue-time request plus gold patch and tests only as hindsight evidence. "
            "Separate latent owner decisions from repository-discoverable facts, hindsight diagnostics, "
            "and implementation incidentals. Never treat the gold implementation as the only valid design. "
            "Material decisions must be behaviorally meaningful questions an interviewer could ask. "
            "Do not promote behavior already fully determined by the issue-time repository into a material "
            "decision merely by phrasing it as a preservation or non-regression question; keep it as a "
            "repository fact unless an unresolved owner choice remains. A material decision's knowledge_timing "
            "must be no earlier than the latest knowledge_timing of every cited evidence_id: any decision citing "
            "repository evidence must be repository_discoverable or later, and any decision citing hindsight-only "
            "evidence is invalid as a public material decision. If the issue and repository already determine all "
            "material behavior and no unresolved owner choice remains, return an empty material_decisions array; "
            "never invent a question merely to make the array non-empty."
        ),
        payload={"issue": issue, "repository_facts": repository_facts, "evidence_inventory": evidence, "gold_patch": sources["gold_patch"], "test_patch": sources["test_patch"], "fail_to_pass": sources["fail_to_pass"], "pass_to_pass": sources["pass_to_pass"]},
        schema=derivation_schema,
    )
    ids = [item["id"] for item in derived["material_decisions"]]
    if len(ids) != len(set(ids)):
        raise ValueError("generated material decision IDs are not unique")
    alias = str(slot["alias"])
    sealed = {
        "schema": "SealedSWEbenchSource.v1", "alias": alias, "inputs": inputs, "evidence": evidence,
        **derived, "review_state": {"status": "draft", "dispositions_complete": False},
    }
    reviews = []
    for reviewer_id in ("a", "b"):
        reviewer = CodexJsonModel(record_root / f"reviewer-{reviewer_id}")
        reviews.append(reviewer.generate(
            role=f"independent-reviewer-{reviewer_id}",
            instructions=(
                "Independently disposition every proposed material decision. Approve only when it is material, "
                "knowable to the issue-time owner, implementation-independent, not a repository fact, and free "
                "of lexical or semantic gold-patch leakage. Uncertainty is not approval. Also require that multiple "
                "normal implementations could satisfy every public behavioral statement."
                " An empty material-decision set is valid when no unresolved owner choice exists; in that case "
                "return an empty dispositions array and still review every sealed observation and incidental."
                " Explicitly disposition every hindsight observation and implementation incidental for provenance, "
                "classification correctness, and leakage. Hindsight observations and implementation incidentals "
                "are intentionally sealed and are expected to describe gold or test evidence. For their "
                "leakage_free field, approve when the item is confined to sealed artifacts, correctly classified, "
                "and not copied or smuggled into a public material decision; do not reject merely because the "
                "sealed item accurately describes gold evidence. semantic_leakage_free evaluates only the proposed "
                "public behavioral material, not the existence of protected details in the sealed payload."
            ),
            payload={
                "issue": issue,
                "repository_facts": repository_facts,
                "evidence_inventory": evidence,
                "derived": derived,
                "gold_patch": sources["gold_patch"],
                "test_patch": sources["test_patch"],
                # Reviewers are a sealed, gold-informed gate. Give them the
                # complete test-set provenance used by the generator rather
                # than forcing provenance decisions from the bounded excerpts
                # that are retained in committed evidence artifacts.
                "fail_to_pass": sources["fail_to_pass"],
                "pass_to_pass": sources["pass_to_pass"],
            },
            schema=REVIEW_SCHEMA,
        ))
    dispositions_by_decision: dict[str, list[DecisionDisposition]] = {item: [] for item in ids}
    expected_classified = {
        item["id"]: "hindsight_observation" for item in derived["hindsight_observations"]
    } | {
        item["id"]: "implementation_incidental" for item in derived["implementation_incidentals"]
    }
    for reviewer_id, review in zip(("a", "b"), reviews, strict=True):
        seen: set[str] = set()
        for item in review["dispositions"]:
            decision_id = item["decision_id"]
            if decision_id not in dispositions_by_decision or decision_id in seen:
                raise ValueError("reviewer omitted or duplicated a decision disposition")
            seen.add(decision_id)
            dispositions_by_decision[decision_id].append(DecisionDisposition(
                decision_id=decision_id, reviewer_id=reviewer_id,
                material=ReviewDecision(item["material"]), issue_time_knowable=ReviewDecision(item["issue_time_knowable"]),
                implementation_independent=ReviewDecision(item["implementation_independent"]),
                separated_from_repository_fact=ReviewDecision(item["separated_from_repository_fact"]), leakage_free=ReviewDecision(item["leakage_free"]),
            ))
        if seen != set(ids):
            raise ValueError("reviewer did not disposition every decision")
        classified = review["classified_items"]
        classified_ids = [item["item_id"] for item in classified]
        if len(classified_ids) != len(set(classified_ids)) or set(classified_ids) != set(expected_classified):
            raise ValueError("reviewer did not disposition every observation/incidental")
        for item in classified:
            if item["classification"] != expected_classified[item["item_id"]] or not (
                item["provenance_supported"] and item["classification_correct"] and item["leakage_free"]
            ):
                raise ValueError("reviewer rejected or misclassified an observation/incidental")
    approved = all(unanimous_disposition(item, dispositions_by_decision[item]).approved for item in ids)
    approved = approved and all(review["semantic_leakage_free"] and review["alternative_implementation_satisfied"] for review in reviews)
    sealed["review_state"] = {"status": "approved" if approved else "human_review_required", "dispositions_complete": True}
    public_family = str(slot["repository_family"]) if slot["partition"] != "holdout" else f"holdout-{alias[:12]}"
    public = {
        "schema": "InterviewerSafeCase.v1", "alias": alias,
        "upstream": slot["public_source"],
        "public_request": inputs["issue"], "repository_facts": repository_facts,
        "metadata": {"context_mode": "repository", "repository_family": public_family, "partition": slot["partition"]},
        "sealed_source_digest": artifact_digest(sealed),
    }
    raw_sentinels = patch_only_sentinels(sources["gold_patch"], public_issue_text=issue)
    sentinels = {
        kind: {
            value for value in values
            if subprocess.run(
                ["git", "grep", "-I", "-F", "-q", "--", value], cwd=repo_root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            ).returncode != 0
        }
        for kind, values in raw_sentinels.items()
    }
    leakage = audit_public_payload(public, sentinels)
    if leakage:
        sealed["review_state"] = {"status": "human_review_required", "dispositions_complete": True}
        public["sealed_source_digest"] = artifact_digest(sealed)
    validate_case_pair(public, sealed)
    audit = {
        "schema": "SWEbenchCaseAudit.v1", "approved": approved and not leakage,
        "lexical_leakage": [
            {"kind": item.kind, "sentinel": item.sentinel, "location": item.location}
            for item in leakage
        ],
        "semantic_leakage_approved_by_both": all(item["semantic_leakage_free"] for item in reviews),
        "public_case_sha256": artifact_digest(public), "sealed_source_sha256": artifact_digest(sealed),
    }
    return public, sealed, reviews[0], reviews[1], audit
