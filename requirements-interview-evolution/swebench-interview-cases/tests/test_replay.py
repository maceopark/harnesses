from __future__ import annotations

import hashlib
import json

import pytest

from swebench_interview_cases.replay import (
    ReplayStudyError,
    _non_regresses,
    _ordered_runs,
    snapshot_recorded_development_corpus,
)
from swebench_interview_cases.schemas import artifact_digest


def test_non_regression_is_fieldwise_not_lexicographic() -> None:
    assert _non_regresses((0, 0, 1), (0, 1, 1))
    assert not _non_regresses((0, 0, 2), (1, 1, 1))


def test_replay_arm_rejects_mixed_skill_identities(tmp_path) -> None:
    runs = []
    for index in range(8):
        run = tmp_path / str(index)
        run.mkdir()
        (run / "run-manifest.json").write_text(json.dumps({
            "alias": f"case-{index}", "partition": "development",
            "skill_sha256": "a" * 64 if index < 7 else "b" * 64,
        }))
        runs.append(run)
    with pytest.raises(ReplayStudyError, match="one authenticated skill"):
        _ordered_runs(runs)


def test_recorded_corpus_reconstructs_exact_public_digest(tmp_path) -> None:
    runs = []
    sealed_root = tmp_path / "sealed"
    for index in range(8):
        alias = f"case-{index}"
        sealed = {"schema": "sealed", "alias": alias}
        upstream = {
            "issue_cache_key": f"sha256:{'a' * 64}", "issue_digest": "a" * 64,
        }
        public = {
            "schema": "InterviewerSafeCase.v1", "alias": alias, "upstream": upstream,
            "public_request": {"cache_key": upstream["issue_cache_key"], "digest": "a" * 64},
            "repository_facts": [],
            "metadata": {"partition": "development", "repository_family": f"org/{index}"},
            "sealed_source_digest": artifact_digest(sealed),
        }
        run = tmp_path / "runs" / alias
        (run / "calls").mkdir(parents=True)
        manifest = {
            "alias": alias, "partition": "development", "case_sha256": artifact_digest(public),
            "sealed_source_sha256": artifact_digest(sealed),
        }
        (run / "run-manifest.json").write_text(json.dumps(manifest))
        payload = {
            "alias": alias, "upstream": upstream, "repository_facts": [],
            "metadata": public["metadata"],
        }
        (run / "calls" / "001-judge.json").write_text(
            json.dumps({"role": "judge", "input": payload})
        )
        target = sealed_root / "cases" / alias
        target.mkdir(parents=True)
        (target / "sealed-source.json").write_text(json.dumps(sealed))
        runs.append(run)

    result = snapshot_recorded_development_corpus(
        source_runs=runs, sealed_corpus_root=sealed_root, output_root=tmp_path / "snapshot",
    )
    assert len(result["cases"]) == 8
    reconstructed = json.loads(
        (tmp_path / "snapshot" / "cases" / "case-0" / "case.json").read_text()
    )
    assert artifact_digest(reconstructed) == result["cases"][0]["case_sha256"]

    broken = json.loads((runs[0] / "run-manifest.json").read_text())
    broken["case_sha256"] = hashlib.sha256(b"drift").hexdigest()
    (runs[0] / "run-manifest.json").write_text(json.dumps(broken))
    with pytest.raises(ReplayStudyError, match="cannot reproduce"):
        snapshot_recorded_development_corpus(
            source_runs=runs, sealed_corpus_root=sealed_root, output_root=tmp_path / "broken",
        )
