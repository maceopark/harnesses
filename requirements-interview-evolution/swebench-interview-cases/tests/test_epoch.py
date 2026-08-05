from __future__ import annotations

import json
import inspect

import pytest

from swebench_interview_cases.epoch import (
    EpochError, _corpus_case_identities, _corpus_manifest_path,
    _decision_review_bundle_digest, _harness_evidence_identities,
    _materiality_evaluator_identity, _stage, run_coevolution_epoch,
)
from swebench_interview_cases.schemas import artifact_digest


def test_stage_reuses_valid_receipt_and_preserves_tampered_attempt(tmp_path) -> None:
    calls = []

    def operation(attempt):
        calls.append(attempt.name)
        (attempt / "artifact.json").write_text(json.dumps({"call": len(calls)}))

    first = _stage(tmp_path, "01-test", {"input": "same"}, operation)
    assert _stage(tmp_path, "01-test", {"input": "same"}, operation) == first
    assert calls == ["attempt-001"]

    (first / "artifact.json").write_text("tampered")
    second = _stage(tmp_path, "01-test", {"input": "same"}, operation)
    assert second.name == "attempt-002"
    assert (first / "artifact.json").read_text() == "tampered"
    assert calls == ["attempt-001", "attempt-002"]


def test_stage_input_drift_creates_new_attempt(tmp_path) -> None:
    def operation(attempt):
        (attempt / "artifact").write_text(attempt.name)

    first = _stage(tmp_path, "stage", {"version": 1}, operation)
    second = _stage(tmp_path, "stage", {"version": 2}, operation)
    assert first.name == "attempt-001"
    assert second.name == "attempt-002"


def test_promotion_commit_is_ordered_after_both_read_only_verifiers() -> None:
    source = inspect.getsource(run_coevolution_epoch)
    assert "verify_and_promote" not in source
    generation_verify = source.index('stages, "05-generation-verifier"')
    evaluator_verify = source.index('stages, "06-evaluator-verifier"')
    verified_guard = source.index('generation_check.get("verified") is not True')
    promotion_commit = source.index('stages, "07-promotion-commit"')
    manifest_commit = source.index('manifest_path = output_root / "epoch-manifest.json"')
    assert generation_verify < evaluator_verify < verified_guard < promotion_commit < manifest_commit


def test_materiality_evaluator_identity_and_review_bundle_are_sealed(tmp_path) -> None:
    identity = _materiality_evaluator_identity()
    assert set(identity) == {
        "rubric_sha256", "schema_version", "reviewer_model",
        "reviewer_reasoning_effort",
    }
    assert identity["reviewer_reasoning_effort"] == "medium"
    assert len(identity["rubric_sha256"]) == 64
    first = _decision_review_bundle_digest(tmp_path)
    review = tmp_path / "run" / "implementation" / "decision-materiality.json"
    review.parent.mkdir(parents=True)
    review.write_text('{"schema":"DecisionMaterialityReview.v1"}\n')
    second = _decision_review_bundle_digest(tmp_path)
    assert first != second


def test_epoch_manifest_declares_materiality_identity_and_review_digest() -> None:
    source = inspect.getsource(run_coevolution_epoch)
    assert '"materiality_evaluator": _materiality_evaluator_identity()' in source
    assert '"decision_review_bundle_sha256": _decision_review_bundle_digest(generation)' in source


def test_corpus_case_identities_seal_all_non_holdout_inputs(tmp_path) -> None:
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"cases": [
        {"alias": "dev", "partition": "development"},
        {"alias": "validation", "partition": "validation"},
        {"alias": "secret", "partition": "holdout"},
    ]}))
    corpus = tmp_path / "corpus"
    for alias in ("dev", "validation"):
        case_dir = corpus / "cases" / alias
        case_dir.mkdir(parents=True)
        (case_dir / "case.json").write_text(f'{{"alias":"{alias}"}}\n')
        (case_dir / "sealed-source.json").write_text(f'{{"alias":"{alias}"}}\n')

    identities = _corpus_case_identities(approved, corpus)
    assert [(item["partition"], item["alias"]) for item in identities] == [
        ("development", "dev"), ("validation", "validation"),
    ]
    assert all(len(item["case_sha256"]) == 64 for item in identities)


def test_corpus_case_identities_fail_before_run_when_validation_is_missing(tmp_path) -> None:
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({
        "cases": [{"alias": "missing", "partition": "validation"}],
    }))
    with pytest.raises(EpochError, match="missing validation case inputs for missing"):
        _corpus_case_identities(approved, tmp_path / "corpus")


def test_corpus_manifest_prefers_complete_pilot_manifest(tmp_path) -> None:
    legacy = tmp_path / "manifest.json"
    complete = tmp_path / "pilot-manifest.json"
    legacy.write_text("{}\n")
    complete.write_text("{}\n")
    assert _corpus_manifest_path(tmp_path) == complete


def test_harness_evidence_is_preflighted_and_sealed(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    case_dir = corpus / "cases" / "dev"
    case_dir.mkdir(parents=True)
    evidence_root = tmp_path / "harness-run" / "evidence"
    evidence_dir = evidence_root / "owner__repo-1"
    evidence_dir.mkdir(parents=True)
    report = evidence_root.parent / "logs" / "report.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"ok":true}\n')
    import hashlib
    report_sha256 = hashlib.sha256(report.read_bytes()).hexdigest()
    evidence = {
        "baseline": {"report_sha256": {"logs/report.json": report_sha256}},
        "gold": {"report_sha256": {"logs/report.json": report_sha256}},
    }
    (evidence_dir / "harness-evidence.json").write_text(json.dumps(evidence))
    (case_dir / "run-manifest.json").write_text(json.dumps({
        "harness_evidence_sha256": artifact_digest(evidence),
    }))
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"cases": [{
        "alias": "dev", "instance_id": "owner__repo-1",
        "partition": "development",
    }]}))

    identities = _harness_evidence_identities(approved, corpus, evidence_root)
    assert identities[0]["evidence_artifact_digest"] == artifact_digest(evidence)
    assert len(identities[0]["reports"]) == 2


def test_harness_evidence_preflight_fails_on_wrong_root(tmp_path) -> None:
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps({"cases": [{
        "alias": "validation", "instance_id": "owner__repo-2",
        "partition": "validation",
    }]}))
    with pytest.raises(EpochError, match="recorded harness evidence is missing"):
        _harness_evidence_identities(
            approved, tmp_path / "corpus", tmp_path / "wrong-root",
        )
