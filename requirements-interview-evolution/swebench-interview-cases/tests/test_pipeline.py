import hashlib

from swebench_interview_cases.cache import ContentAddressedCache
from swebench_interview_cases.pipeline import build_approved_corpus
from swebench_interview_cases.schemas import artifact_digest


class Harness:
    def __init__(self, output_root):
        self.output_root = output_root
        self.calls = []
    def validate_instance(self, row):
        self.calls.append(row["instance_id"])
        return {"instance_id": row["instance_id"], "valid": True}


def row(instance_id, repo):
    return {
        "instance_id": instance_id, "repo": repo, "base_commit": "a" * 40,
        "problem_statement": "issue", "patch": "+gold", "test_patch": "+test",
        "FAIL_TO_PASS": '["f"]', "PASS_TO_PASS": '["p"]',
    }


def fake_case(*, slot, cache, record_root, repo_root):
    issue_digest = slot["sealed_inputs"]["issue"]["digest"]
    sealed = {
        "schema": "SealedSWEbenchSource.v1", "alias": slot["alias"], "inputs": slot["sealed_inputs"],
        "evidence": [{"id": "issue", "source": "issue", "knowledge_timing": "issue_time_author_knowable", "source_digest": issue_digest, "locator": "issue", "excerpt": "issue", "excerpt_digest": hashlib.sha256(b"issue").hexdigest(), "cache_required": True}],
        "material_decisions": [{"id": "d", "description": "behavior", "sources": ["issue"], "knowledge_timing": "issue_time_author_knowable", "materiality": "material", "owner_answer": "answer", "question_intent": "ask", "failure_if_missed": "failure", "evidence_ids": ["issue"]}],
        "hindsight_observations": [], "implementation_incidentals": [],
        "review_state": {"status": "approved", "dispositions_complete": True},
    }
    family = slot["repository_family"] if slot["partition"] != "holdout" else f"holdout-{slot['alias'][:12]}"
    public = {
        "schema": "InterviewerSafeCase.v1", "alias": slot["alias"], "upstream": slot["public_source"],
        "public_request": slot["sealed_inputs"]["issue"], "repository_facts": [],
        "metadata": {"context_mode": "repository", "repository_family": family, "partition": slot["partition"]},
        "sealed_source_digest": artifact_digest(sealed),
    }
    return public, sealed, {"dispositions": []}, {"dispositions": []}, {"approved": True}


def test_pipeline_fills_exact_partitions_and_registry(tmp_path, monkeypatch):
    monkeypatch.setattr("swebench_interview_cases.pipeline.derive_and_review_case", fake_case)
    monkeypatch.setattr("swebench_interview_cases.pipeline.prepare_checkout", lambda **kwargs: {"alias": kwargs["alias"]})
    partitions = ["development"] * 8 + ["validation"] * 3 + ["holdout"] * 4
    rows = []
    cases = []
    cache = ContentAddressedCache(tmp_path / "cache")
    for index, partition in enumerate(partitions):
        repo = f"org/repo{index}"
        instance_id = f"org__repo{index}-{index + 1}"
        item = row(instance_id, repo); rows.append(item)
        issue = cache.put_text("issue"); empty = cache.put_text("")
        cases.append({
            "partition": partition, "alias": hashlib.sha256(instance_id.encode()).hexdigest() if partition == "holdout" else instance_id,
            "instance_id": instance_id, "repository_family": repo, "difficulty": "short", "size_bucket": "small", "stratum_rank": 0,
            "public_source": {"dataset": "verified", "revision": "b" * 40, "instance_id_digest": hashlib.sha256(instance_id.encode()).hexdigest(), "base_commit": "a" * 40, "source_url": f"https://github.com/{repo}/pull/{index + 1}", "issue_digest": issue.sha256, "issue_cache_key": issue.key},
            "sealed_inputs": {name: {"cache_key": (issue if name == "issue" else empty).key, "digest": (issue if name == "issue" else empty).sha256} for name in ("issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass")},
            "replacement_instance_ids": [],
        })
    result = build_approved_corpus(
        harness=Harness(tmp_path), rows=rows, sealed_selection={"cases": cases}, cache=cache,
        corpus_root=tmp_path / "corpus", record_root=tmp_path / "records",
        repository_root=tmp_path / "repositories",
    )
    assert result["approved_total"] == 15
    assert result["counts"] == {"development": 8, "validation": 3, "holdout": 4}
    assert result["repository_families"] == 15

    def should_not_regenerate(**kwargs):
        raise AssertionError("approved cases must resume without model regeneration")

    monkeypatch.setattr("swebench_interview_cases.pipeline.derive_and_review_case", should_not_regenerate)
    resumed = build_approved_corpus(
        harness=Harness(tmp_path), rows=rows, sealed_selection={"cases": cases}, cache=cache,
        corpus_root=tmp_path / "corpus", record_root=tmp_path / "records",
        repository_root=tmp_path / "repositories",
    )
    assert resumed["approved_total"] == 15


def test_pipeline_resumes_an_approved_replacement_before_original(tmp_path, monkeypatch):
    """Restarting a slot must not retry an already-rejected original case."""

    monkeypatch.setattr("swebench_interview_cases.pipeline.derive_and_review_case", fake_case)
    monkeypatch.setattr("swebench_interview_cases.pipeline.prepare_checkout", lambda **kwargs: {"alias": kwargs["alias"]})
    cache = ContentAddressedCache(tmp_path / "cache")
    issue = cache.put_text("issue")
    empty = cache.put_text("")
    partitions = ["development"] * 8 + ["validation"] * 3 + ["holdout"] * 4
    rows = []
    cases = []
    for index, partition in enumerate(partitions):
        repo = f"org/repo{index}"
        original_id = f"org__repo{index}-{index + 1}"
        replacement_id = f"org__repo{index}-{index + 101}"
        rows.extend([row(original_id, repo), row(replacement_id, repo)])
        cases.append({
            "partition": partition,
            "alias": hashlib.sha256(original_id.encode()).hexdigest() if partition == "holdout" else original_id,
            "instance_id": original_id, "repository_family": repo, "difficulty": "short",
            "size_bucket": "small", "stratum_rank": 0,
            "public_source": {"dataset": "verified", "revision": "b" * 40,
                "instance_id_digest": hashlib.sha256(original_id.encode()).hexdigest(),
                "base_commit": "a" * 40, "source_url": f"https://github.com/{repo}/pull/{index + 1}",
                "issue_digest": issue.sha256, "issue_cache_key": issue.key},
            "sealed_inputs": {name: {"cache_key": (issue if name == "issue" else empty).key,
                "digest": (issue if name == "issue" else empty).sha256}
                for name in ("issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass")},
            "replacement_instance_ids": [replacement_id],
        })

    # Materialize the corpus with replacements as the selected instances.
    replacement_cases = [{**item, "instance_id": item["replacement_instance_ids"][0],
                          "replacement_instance_ids": []} for item in cases]
    first_harness = Harness(tmp_path)
    build_approved_corpus(
        harness=first_harness, rows=rows, sealed_selection={"cases": replacement_cases}, cache=cache,
        corpus_root=tmp_path / "corpus", record_root=tmp_path / "records",
        repository_root=tmp_path / "repositories",
    )

    resumed_harness = Harness(tmp_path)
    build_approved_corpus(
        harness=resumed_harness, rows=rows, sealed_selection={"cases": cases}, cache=cache,
        corpus_root=tmp_path / "corpus", record_root=tmp_path / "records",
        repository_root=tmp_path / "repositories",
    )
    assert all(instance_id.endswith(tuple(str(index + 101) for index in range(15)))
               for instance_id in resumed_harness.calls)
