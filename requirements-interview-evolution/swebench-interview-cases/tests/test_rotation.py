import json

import pytest

from swebench_interview_cases.rotation import rotate_non_holdout_partitions
from swebench_interview_cases.schemas import artifact_digest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_rotation_requires_complete_8_3_assignment(tmp_path):
    sealed = tmp_path / "sealed.json"
    write_json(sealed, {"cases": [{"alias": "one", "partition": "development"}]})
    with pytest.raises(ValueError, match="8/3"):
        rotate_non_holdout_partitions(
            corpus_root=tmp_path / "corpus", sealed_approved=sealed,
            assignments={"one": "validation"},
        )


def test_rotation_refreshes_case_and_manifest_bindings(tmp_path):
    corpus = tmp_path / "corpus"
    cases = []
    assignments = {}
    for index in range(11):
        alias = f"case-{index}"
        partition = "development" if index < 8 else "validation"
        assignments[alias] = partition
        public = {
            "metadata": {"partition": "validation", "repository_family": f"family-{index}"}
        }
        write_json(corpus / "cases" / alias / "case.json", public)
        write_json(corpus / "cases" / alias / "run-manifest.json", {
            "partition": "validation", "case_sha256": "old",
        })
        cases.append({
            "alias": alias, "partition": "validation", "case_digest": "old",
            "repository_family": f"family-{index}",
        })
    holdouts = []
    for index in range(4):
        holdouts.append({
            "alias": f"holdout-{index}", "partition": "holdout",
            "case_digest": "0" * 64, "repository_family": f"holdout-family-{index}",
        })
    all_cases = cases + holdouts
    write_json(corpus / "pilot-manifest.json", {
        "registry": {"schema": "SWEbenchPartitionRegistry.v1", "entries": [{
            "id": item["alias"], "partition": item["partition"],
            "case_digest": item["case_digest"], "repository_family": item["repository_family"],
            "status": "approved",
        } for item in all_cases], "holdout_alias": {}, "registry_digest": "old"}
    })
    sealed = tmp_path / "approved.json"
    write_json(sealed, {"cases": all_cases, "public_manifest_sha256": "old"})

    result = rotate_non_holdout_partitions(
        corpus_root=corpus, sealed_approved=sealed, assignments=assignments,
    )

    public = json.loads((corpus / "cases" / "case-0" / "case.json").read_text())
    preparation = json.loads((corpus / "cases" / "case-0" / "run-manifest.json").read_text())
    approved = json.loads(sealed.read_text())
    assert result["holdout_unchanged"] is True
    assert public["metadata"]["partition"] == "development"
    assert preparation["case_sha256"] == artifact_digest(public)
    assert approved["public_manifest_sha256"] == artifact_digest(
        json.loads((corpus / "pilot-manifest.json").read_text())
    )
