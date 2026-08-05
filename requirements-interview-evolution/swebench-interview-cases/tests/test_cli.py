import json

import pytest

from swebench_interview_cases.cli import download_dataset, main


def write_json(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def test_study_validation_admits_absolute_zero_candidate_independent_of_baseline(tmp_path, capsys):
    metrics = {"implementation_ready": 3}
    baseline = write_json(tmp_path, "baseline.json", metrics)
    candidate = write_json(tmp_path, "candidate.json", metrics)
    assert main(["study", "validation", "--baseline", baseline, "--candidate", candidate]) == 0
    assert json.loads(capsys.readouterr().out) == {"winner": "candidate"}


def test_study_holdout_returns_nonzero_when_strict_gate_fails(tmp_path, capsys):
    metrics = {"completed_cases": 4, "implementation_ready": 3, "contamination": 0, "leakage": 0, "invented_requirements": 0, "compatibility_regressions": 0, "implementation_decisions": 0, "approved_material_blockers": 0}
    candidate = write_json(tmp_path, "holdout.json", metrics)
    assert main(["study", "holdout", "--candidate", candidate]) == 1
    assert json.loads(capsys.readouterr().out) == {"promote": False}


def test_validate_command_accepts_closed_partition_index(tmp_path):
    path = write_json(tmp_path, "index.json", {"schema": "SWEbenchPartitionIndex.v1", "partition": "development", "cases": []})
    assert main(["validate", "partition_index", path]) == 0


def test_download_rejects_moving_revision_before_network_access(tmp_path):
    with pytest.raises(ValueError, match="immutable revision SHA"):
        download_dataset("dataset", "test", "main", str(tmp_path / "rows.jsonl"))


def test_download_rejects_non_contract_pin_before_network_access(tmp_path):
    with pytest.raises(ValueError, match="Build Contract"):
        download_dataset("other/dataset", "test", "0" * 40, str(tmp_path / "rows.parquet"))


def test_standalone_promotion_command_does_not_exist():
    with pytest.raises(SystemExit):
        main(["promote"])
