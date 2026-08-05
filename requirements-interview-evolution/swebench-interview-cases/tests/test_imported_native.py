import hashlib
import json

from swebench_interview_cases.cache import ContentAddressedCache
import pytest

from swebench_interview_cases.imported_native import (
    FINDING,
    _validate_adjudication,
    replay_imported_judge,
    replay_recorded_judge,
    run_imported_case,
)


def test_review_citation_value_uses_structured_output_compatible_json_schema() -> None:
    quoted = FINDING["properties"]["citations"]["items"]["properties"]["quoted_value"]
    assert set(quoted["type"]) == {
        "boolean", "null", "number", "string",
    }


def test_adjudication_approval_must_equal_all_required_gates() -> None:
    finding = {"id": "F-1", "material": True}
    verdict = {
        "finding_id": "F-1", "approved": True, "evidence_supported": True,
        "material": True, "repository_independent": True,
        "implementation_independent": False, "oracle_conflict": False,
        "reason": "contradictory",
    }
    with pytest.raises(ValueError, match="approval contradicts"):
        _validate_adjudication(
            {"verdicts": [verdict], "summary": "invalid"}, findings=[finding],
        )

    verdict["approved"] = False
    _validate_adjudication(
        {"verdicts": [verdict], "summary": "valid"}, findings=[finding],
    )
from swebench_interview_cases.schemas import artifact_digest


class FakeModel:
    def __init__(self, *args, **kwargs):
        pass

    def generate(self, *, role, **kwargs):
        if role == "repository-discovery":
            return {"scope_summary": "base commit", "facts": [], "unknowns": []}
        if role == "evidence-auditor":
            return {"accepted_fact_ids": [], "rejected": [], "summary": "none"}
        if role == "interviewer":
            return {
                "action": "complete", "reason": "ready", "open_material_decisions": [],
                "question": None, "contract": {
                    "summary": "contract", "implementation_ready": True,
                    "confirmed_decisions": ["behavior"], "open_material_decisions": [],
                    "acceptance_checks": ["works"],
                },
            }
        if role == "adversarial-reviewer":
            return {"findings": [], "summary": "clear"}
        if role == "judge":
            return {
                "implementation_ready": True, "repository_fidelity": 1.0, "owner_recall": 1.0,
                "invented_requirements": [], "compatibility_regressions": [],
                "redundant_questions": [], "material_blockers": [], "summary": "ready",
            }
        if role == "adjudicator":
            return {"verdicts": [], "summary": "none"}
        raise AssertionError(role)


def test_imported_run_skips_per_case_mutator(tmp_path, monkeypatch):
    monkeypatch.setattr("swebench_interview_cases.imported_native.CodexJsonModel", FakeModel)
    cache = ContentAddressedCache(tmp_path / "cache")
    issue = cache.put_text("Please define behavior")
    empty = cache.put_text("")
    inputs = {
        "issue": {"cache_key": issue.key, "digest": issue.sha256},
        **{name: {"cache_key": empty.key, "digest": empty.sha256} for name in ("gold_patch", "test_patch", "fail_to_pass", "pass_to_pass")},
    }
    sealed = {
        "schema": "SealedSWEbenchSource.v1", "alias": "case-1", "inputs": inputs,
        "evidence": [{"id": "issue", "source": "issue", "knowledge_timing": "issue_time_author_knowable", "source_digest": issue.sha256, "locator": issue.key, "excerpt": "Please define behavior", "excerpt_digest": hashlib.sha256(b"Please define behavior").hexdigest(), "cache_required": True}],
        "material_decisions": [{
            "id": "decision-1", "description": "behavior", "sources": ["issue"],
            "knowledge_timing": "issue_time_author_knowable", "materiality": "blocks behavior",
            "owner_answer": "chosen", "question_intent": "clarify", "failure_if_missed": "wrong behavior",
            "evidence_ids": ["issue"],
        }],
        "hindsight_observations": [], "implementation_incidentals": [],
        "review_state": {"status": "approved", "dispositions_complete": True},
    }
    public = {
        "schema": "InterviewerSafeCase.v1", "alias": "case-1",
        "upstream": {
            "dataset": "verified", "revision": "a" * 40,
            "instance_id_digest": hashlib.sha256(b"id").hexdigest(), "base_commit": "abcdef0",
            "source_url": "https://example.invalid/pull/1", "issue_digest": issue.sha256,
            "issue_cache_key": issue.key,
        },
        "public_request": {"cache_key": issue.key, "digest": issue.sha256},
        "repository_facts": [],
        "metadata": {"context_mode": "repository", "repository_family": "org/repo", "partition": "development"},
        "sealed_source_digest": artifact_digest(sealed),
    }
    repo = tmp_path / "repo"
    repo.mkdir()
    result = run_imported_case(
        public_case=public, sealed_source=sealed, cache=cache, repo_root=repo,
        skill_md="skill", run_dir=tmp_path / "run",
    )
    assert result["manifest"]["per_case_mutator_invoked"] is False
    assert "development-mutator" not in result["manifest"]["roles"]
    assert not (tmp_path / "run" / "candidate-SKILL.md").exists()

    rubric = "Prefer evidence-bound observable outcomes."
    replay = replay_imported_judge(
        source_run=tmp_path / "run", public_case=public, sealed_source=sealed, cache=cache,
        evaluator_rubric=rubric, evaluator_sha256=hashlib.sha256(rubric.encode()).hexdigest(),
        output_dir=tmp_path / "replay",
    )
    assert replay["manifest"]["source_skill_sha256"] == result["manifest"]["skill_sha256"]
    assert replay["manifest"]["raw_artifact_sha256"]["contract.json"] == result["manifest"][
        "artifact_sha256"
    ]["contract.json"]
    assert (tmp_path / "run" / "judge.json").is_file()
    assert (tmp_path / "replay" / "judge.json").is_file()

    calls = tmp_path / "run" / "calls"
    calls.mkdir(exist_ok=True)
    recorded_payload = {
        "alias": public["alias"],
        "upstream": public["upstream"],
        "repository_facts": public["repository_facts"],
        "metadata": public["metadata"],
        "sealed_inputs": sealed["inputs"],
        "sealed_evidence": sealed["evidence"],
        "material_decisions": sealed["material_decisions"],
        "hindsight_observations": sealed["hindsight_observations"],
        "implementation_incidentals": sealed["implementation_incidentals"],
        "review_state": sealed["review_state"],
        "transcript": json.loads((tmp_path / "run" / "transcript.json").read_text()),
        "contract": json.loads((tmp_path / "run" / "contract.json").read_text()),
        "audited_repository_evidence": json.loads(
            (tmp_path / "run" / "evidence.json").read_text()
        ),
    }
    (calls / "001-judge.json").write_text(
        json.dumps({"role": "judge", "input": recorded_payload}), encoding="utf-8",
    )
    recorded = replay_recorded_judge(
        source_run=tmp_path / "run", evaluator_rubric=rubric,
        evaluator_sha256=hashlib.sha256(rubric.encode()).hexdigest(),
        output_dir=tmp_path / "recorded-replay",
    )
    assert recorded["manifest"]["source_judge_call_sha256"]

    tampered_payload = dict(recorded_payload)
    tampered_payload["material_decisions"] = []
    (calls / "001-judge.json").write_text(
        json.dumps({"role": "judge", "input": tampered_payload}), encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sealed source identity drifted"):
        replay_recorded_judge(
            source_run=tmp_path / "run", evaluator_rubric=rubric,
            evaluator_sha256=hashlib.sha256(rubric.encode()).hexdigest(),
            output_dir=tmp_path / "tampered-recorded-replay",
        )

    (tmp_path / "run" / "evidence.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact digest drifted"):
        replay_imported_judge(
            source_run=tmp_path / "run", public_case=public, sealed_source=sealed, cache=cache,
            evaluator_rubric=rubric,
            evaluator_sha256=hashlib.sha256(rubric.encode()).hexdigest(),
            output_dir=tmp_path / "tampered-replay",
        )
