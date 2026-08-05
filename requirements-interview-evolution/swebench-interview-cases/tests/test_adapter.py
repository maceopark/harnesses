from copy import deepcopy
import hashlib

import pytest

from swebench_interview_cases.adapter import ProjectionError, project_role_payload
from swebench_interview_cases.schemas import artifact_digest


def fixtures():
    digests = {name: (character * 64) for name, character in zip(("issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass"), "abcde", strict=True)}
    digests["issue"] = hashlib.sha256(b"issue").hexdigest()
    sealed = {
        "schema": "SealedSWEbenchSource.v1",
        "alias": "case-a",
        "inputs": {name: {"cache_key": f"sha256:{digest}", "digest": digest} for name, digest in digests.items()},
        "evidence": [
            {"id": "e1", "source": "issue", "knowledge_timing": "issue_time_author_knowable", "source_digest": digests["issue"], "locator": "issue", "excerpt": "issue", "excerpt_digest": hashlib.sha256(b"issue").hexdigest(), "cache_required": True},
            {"id": "e2", "source": "patch", "knowledge_timing": "hindsight_only", "source_digest": digests["gold_patch"], "locator": "patch", "excerpt": "", "excerpt_digest": hashlib.sha256(b"").hexdigest(), "cache_required": True},
        ],
        "material_decisions": [
            {"id": "d1", "description": "behavior", "sources": ["issue"], "knowledge_timing": "issue_time_author_knowable", "materiality": "changes output", "owner_answer": "yes", "question_intent": "resolve behavior", "failure_if_missed": "omission", "evidence_ids": ["e1"]},
            {"id": "d2", "description": "internal", "sources": ["patch"], "knowledge_timing": "hindsight_only", "materiality": "none", "owner_answer": "unknown", "question_intent": "none", "failure_if_missed": "none", "evidence_ids": ["e2"]},
        ],
        "hindsight_observations": [{"id": "h1", "description": "later", "evidence_ids": ["e2"]}],
        "implementation_incidentals": [],
        "review_state": {"status": "approved", "dispositions_complete": True},
    }
    public = {
        "schema": "InterviewerSafeCase.v1",
        "alias": "case-a",
        "upstream": {"dataset": "verified", "revision": "rev", "instance_id_digest": "b" * 64, "base_commit": "abc1234", "source_url": "https://example.test/1", "issue_digest": digests["issue"], "issue_cache_key": f"sha256:{digests['issue']}"},
        "public_request": {"cache_key": f"sha256:{digests['issue']}", "digest": digests["issue"]},
        "repository_facts": [],
        "metadata": {"context_mode": "repository", "repository_family": "o/r", "partition": "development"},
        "sealed_source_digest": artifact_digest(sealed),
    }
    return public, sealed


def test_interviewer_and_mutator_never_receive_sealed_material():
    public, sealed = fixtures()
    interviewer = project_role_payload("interviewer", public_case=public, public_request_text="issue", runtime={"transcript": []}, sealed_source=sealed)
    assert "material_decisions" not in interviewer
    assert "gold_patch" not in repr(interviewer)
    mutator = project_role_payload("development-mutator", public_case=public, public_request_text="issue", runtime={"approved_failure_summaries": [{"class": "omission"}]}, sealed_source=sealed)
    assert set(mutator) == {"candidate_skill", "approved_failure_summaries"}


def test_owner_gets_only_issue_time_knowable_decisions():
    public, sealed = fixtures()
    owner = project_role_payload("owner", public_case=public, public_request_text="issue", runtime={"question": "What?"}, sealed_source=sealed)
    assert [item["id"] for item in owner["owner_oracle"]] == ["d1"]


def test_judge_gets_explicit_sealed_allowlist_and_blind_reviewer_gets_fixed_taxonomy():
    public, sealed = fixtures()
    judge = project_role_payload("judge", public_case=public, public_request_text="issue", sealed_source=sealed)
    assert set(sealed["inputs"]) == set(judge["sealed_inputs"])
    blind = project_role_payload("adversarial-reviewer", public_case=public, public_request_text="issue", runtime={"failure_taxonomy": ["gold-specific"]})
    assert "gold-specific" not in blind["failure_taxonomy"]
    assert "omission" in blind["failure_taxonomy"]


def test_public_role_runtime_with_sealed_key_fails_closed():
    public, _ = fixtures()
    with pytest.raises(ProjectionError, match="forbidden sealed key"):
        project_role_payload("interviewer", public_case=public, public_request_text="issue", runtime={"transcript": [{"gold_patch": "secret"}]})


def test_sealed_digest_drift_is_rejected():
    public, sealed = fixtures()
    drifted = deepcopy(sealed)
    drifted["material_decisions"][0]["owner_answer"] = "no"
    with pytest.raises(ProjectionError, match="digest"):
        project_role_payload("judge", public_case=public, public_request_text="issue", sealed_source=drifted)


def test_public_request_cache_content_must_match_digest():
    public, _ = fixtures()
    with pytest.raises(ProjectionError, match="request text digest"):
        project_role_payload("interviewer", public_case=public, public_request_text="tampered")
