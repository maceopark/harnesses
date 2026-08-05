from __future__ import annotations

import hashlib
import json
import threading
import time

from swebench_interview_cases.batch import batch_mutate
from swebench_interview_cases.execute import (
    _completed_batch_matches,
    _completed_run_matches,
    _development_case_outcome,
    _paired_development_non_regression,
    _run_parallel,
    _development_case_delta,
)
from swebench_interview_cases.schemas import artifact_digest


def test_completed_run_is_reused_only_with_matching_identity_and_digests(tmp_path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    artifact = target / "contract.json"
    artifact.write_text("{}\n", encoding="utf-8")
    public = {"alias": "case", "metadata": {"partition": "development"}}
    sealed = {"schema": "sealed"}
    skill = "skill"
    manifest = {
        "schema": "NativeEvolutionImportedRun.v1",
        "alias": "case",
        "partition": "development",
        "model": "gpt-5.6-sol",
        "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
        "case_sha256": artifact_digest(public),
        "sealed_source_sha256": artifact_digest(sealed),
        "per_case_mutator_invoked": False,
        "artifact_sha256": {
            "contract.json": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
    }
    (target / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert _completed_run_matches(target, public=public, sealed=sealed, skill_text=skill)


def test_completed_batch_is_reused_only_with_matching_inputs_and_artifacts(tmp_path) -> None:
    runs = []
    for index in range(8):
        run = tmp_path / f"run-{index}"
        run.mkdir()
        (run / "run-manifest.json").write_text(
            json.dumps({"partition": "development", "alias": f"case-{index}"}),
            encoding="utf-8",
        )
        implementation = run / "implementation"
        implementation.mkdir()
        (implementation / "decision.jsonl").write_text("", encoding="utf-8")
        (implementation / "implementation-manifest.json").write_text(
            json.dumps({"decision_count": 0}), encoding="utf-8",
        )
        (run / "judge.json").write_text(json.dumps({
            "invented_requirements": [], "compatibility_regressions": [],
        }), encoding="utf-8")
        runs.append(run)

    output = tmp_path / "batch"
    batch_mutate(baseline_skill="skill", development_run_dirs=runs, output_dir=output)
    assert _completed_batch_matches(
        output, baseline_skill="skill", development_runs=runs,
    )


def test_run_parallel_uses_all_phase_workers_and_preserves_order() -> None:
    barrier = threading.Barrier(4)

    def operation(item: int) -> int:
        barrier.wait(timeout=2)
        time.sleep(0.01 * (4 - item))
        return item * 2

    assert _run_parallel([1, 2, 3, 4], operation, max_workers=None) == [2, 4, 6, 8]


def test_run_parallel_rejects_non_positive_worker_limit() -> None:
    try:
        _run_parallel([1], lambda item: item, max_workers=0)
    except ValueError as exc:
        assert str(exc) == "max_workers must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def _development_outcome_run(
    root, alias, *, invented=0, ready=True, decisions=0, material_decisions=None,
    approved_failure=None,
):
    run = root / alias
    run.mkdir(parents=True)
    (run / "run-manifest.json").write_text(json.dumps({"alias": alias}))
    (run / "judge.json").write_text(json.dumps({
        "implementation_ready": ready,
        "invented_requirements": ["x"] * invented,
        "compatibility_regressions": [],
        "redundant_questions": [],
    }))
    (run / "runtime-audit.json").write_text(json.dumps({"contamination": 0, "leakage": 0}))
    findings = ([{"id": "F1", "failure_class": approved_failure}]
                if approved_failure else [])
    verdicts = ([{"finding_id": "F1", "approved": True}]
                if approved_failure else [])
    (run / "blind-review.json").write_text(json.dumps({"findings": findings}))
    (run / "adjudication.json").write_text(json.dumps({"verdicts": verdicts}))
    implementation = run / "implementation"
    implementation.mkdir()
    (implementation / "implementation-manifest.json").write_text(
        json.dumps({
            "decision_count": decisions,
            "material_decision_count": decisions if material_decisions is None else material_decisions,
        })
    )
    return run


def test_paired_development_gate_requires_every_case_non_regression_and_one_improvement(tmp_path):
    baseline = [
        _development_outcome_run(tmp_path / "baseline", "a", invented=1),
        _development_outcome_run(tmp_path / "baseline", "b"),
    ]
    improved = [
        _development_outcome_run(tmp_path / "improved", "a"),
        _development_outcome_run(tmp_path / "improved", "b"),
    ]
    regressed_elsewhere = [
        _development_outcome_run(tmp_path / "regressed", "a"),
        _development_outcome_run(tmp_path / "regressed", "b", invented=1),
    ]
    assert _paired_development_non_regression(baseline, improved)
    assert not _paired_development_non_regression(baseline, regressed_elsewhere)
    assert not _paired_development_non_regression(baseline, baseline)


def test_development_delta_separates_decisions_and_approved_failure_class(tmp_path):
    baseline = _development_outcome_run(tmp_path / "baseline", "a", invented=2)
    candidate = _development_outcome_run(
        tmp_path / "candidate", "a", invented=0, decisions=1,
        approved_failure="invention",
    )
    assert _development_case_delta(baseline, candidate) == {
        "invented_requirements": -2,
        "material_implementation_decisions": 1,
        "approved_finding__invention": 1,
    }


def test_development_gate_ignores_minor_decision_count(tmp_path):
    baseline = [_development_outcome_run(tmp_path / "baseline", "a")]
    candidate = [
        _development_outcome_run(
            tmp_path / "candidate", "a", decisions=3, material_decisions=0,
            invented=0,
        )
    ]
    assert _development_case_outcome(baseline[0]) == _development_case_outcome(candidate[0])
