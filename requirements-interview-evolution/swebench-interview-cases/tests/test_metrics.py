import json

from swebench_interview_cases.metrics import holdout_metrics, validation_metrics


def make_run(root, partition, alias):
    run = root / alias; run.mkdir()
    (run / "run-manifest.json").write_text(json.dumps({"partition": partition, "alias": alias, "per_case_mutator_invoked": False}))
    (run / "judge.json").write_text(json.dumps({"implementation_ready": True, "owner_recall": 1.0, "repository_fidelity": 1.0, "invented_requirements": [], "compatibility_regressions": [], "redundant_questions": []}))
    (run / "blind-review.json").write_text(json.dumps({"findings": []}))
    (run / "adjudication.json").write_text(json.dumps({"verdicts": []}))
    (run / "runtime-audit.json").write_text(json.dumps({"contamination": 0, "leakage": 0}))
    implementation = run / "implementation"; implementation.mkdir()
    (implementation / "implementation-manifest.json").write_text(
        json.dumps({"decision_count": 0, "material_decision_count": 0})
    )
    return run


def test_validation_aggregate_requires_three_ready_cases(tmp_path):
    metrics = validation_metrics([make_run(tmp_path, "validation", str(i)) for i in range(3)])
    assert metrics.implementation_ready == 3
    assert metrics.owner_recall == 1.0
    assert metrics.implementation_decisions == 0
    assert metrics.material_implementation_decisions == 0


def test_holdout_aggregate_produces_strict_passing_shape(tmp_path):
    metrics = holdout_metrics([make_run(tmp_path, "holdout", str(i)) for i in range(4)])
    assert metrics.completed_cases == metrics.implementation_ready == 4
    assert metrics.approved_material_blockers == 0
