from __future__ import annotations

import copy
import unittest

from swebench_interview_cases.schemas import (
    SchemaError,
    artifact_digest,
    validate_case_pair,
    validate_no_cross_partition_family_overlap,
    validate_public_case,
    validate_sealed_source,
)


DIGEST = "a" * 64


def public_case() -> dict:
    return {
        "schema": "InterviewerSafeCase.v1",
        "alias": "case-a",
        "upstream": {
            "dataset": "princeton-nlp/SWE-bench_Verified",
            "revision": "b" * 40,
            "instance_id_digest": DIGEST,
            "base_commit": "deadbeef",
            "source_url": "https://example.invalid/pull/1",
            "issue_digest": DIGEST,
            "issue_cache_key": f"sha256:{DIGEST}",
        },
        "public_request": {"cache_key": f"sha256:{DIGEST}", "digest": DIGEST},
        "repository_facts": [],
        "metadata": {"context_mode": "repository", "repository_family": "owner/repo", "partition": "development"},
        "sealed_source_digest": DIGEST,
    }


def sealed_source() -> dict:
    descriptor = {"cache_key": f"sha256:{DIGEST}", "digest": DIGEST}
    return {
        "schema": "SealedSWEbenchSource.v1",
        "alias": "case-a",
        "inputs": {name: dict(descriptor) for name in ("issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass")},
        "evidence": [{"id": "e1", "source": "issue", "knowledge_timing": "issue_time_author_knowable", "source_digest": DIGEST, "locator": "issue", "excerpt": "", "excerpt_digest": __import__("hashlib").sha256(b"").hexdigest(), "cache_required": True}],
        "material_decisions": [{"id": "d1", "description": "behavior", "sources": ["issue"], "knowledge_timing": "issue_time_author_knowable", "materiality": "changes output", "owner_answer": "answer", "question_intent": "resolve output", "failure_if_missed": "omission", "evidence_ids": ["e1"]}],
        "hindsight_observations": [],
        "implementation_incidentals": [],
        "review_state": {"status": "draft", "dispositions_complete": False},
    }


class SchemaTests(unittest.TestCase):
    def test_valid_minimal_artifacts(self) -> None:
        validate_public_case(public_case())
        validate_sealed_source(sealed_source())

    def test_no_unresolved_material_decisions_is_valid(self) -> None:
        value = sealed_source()
        value["material_decisions"] = []
        validate_sealed_source(value)

    def test_unknown_public_field_is_rejected(self) -> None:
        value = public_case()
        value["owner_answer"] = "leak"
        with self.assertRaises(SchemaError):
            validate_public_case(value)

    def test_invalid_provenance_and_timing_are_rejected(self) -> None:
        value = sealed_source()
        value["material_decisions"] = [{
            "id": "d1", "description": "behavior", "sources": ["gold"],
            "knowledge_timing": "omniscient", "materiality": "changes output",
            "owner_answer": "answer", "question_intent": "resolve output",
            "failure_if_missed": "omission", "evidence_ids": [],
        }]
        with self.assertRaises(SchemaError):
            validate_sealed_source(value)

    def test_approved_artifact_requires_complete_dispositions(self) -> None:
        value = sealed_source()
        value["review_state"]["status"] = "approved"
        with self.assertRaises(SchemaError):
            validate_sealed_source(value)

    def test_hindsight_evidence_cannot_be_promoted_to_owner_knowable(self) -> None:
        value = sealed_source()
        value["evidence"].append({"id": "patch", "source": "patch", "knowledge_timing": "hindsight_only", "source_digest": DIGEST, "locator": "patch", "excerpt": "", "excerpt_digest": __import__("hashlib").sha256(b"").hexdigest(), "cache_required": True})
        value["material_decisions"][0].update({
            "sources": ["patch"], "knowledge_timing": "issue_time_author_knowable",
            "evidence_ids": ["patch"],
        })
        with self.assertRaisesRegex(SchemaError, "predates"):
            validate_sealed_source(value)

    def test_cross_partition_repository_family_is_rejected(self) -> None:
        def index(partition: str) -> dict:
            return {"schema": "SWEbenchPartitionIndex.v1", "partition": partition, "cases": [{"alias": partition, "repository_family": "same/repo", "case_digest": DIGEST, "status": "approved"}]}
        with self.assertRaises(SchemaError):
            validate_no_cross_partition_family_overlap([index("development"), index("holdout")])

    def test_case_pair_rejects_digest_drift(self) -> None:
        public = public_case()
        sealed = sealed_source()
        public["sealed_source_digest"] = artifact_digest(sealed)
        validate_case_pair(public, sealed)
        sealed["hindsight_observations"].append(
            {"id": "h1", "description": "new observation", "evidence_ids": ["e1"]}
        )
        with self.assertRaises(SchemaError):
            validate_case_pair(public, sealed)


if __name__ == "__main__":
    unittest.main()
