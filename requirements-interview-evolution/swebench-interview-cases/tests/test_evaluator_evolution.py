from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swebench_interview_cases.evaluator_evolution import (
    EvaluatorEvolutionError,
    EvaluatorSpec,
    canonical_anchor_manifest_bytes,
    freeze_epoch,
    generate_pairwise_anchor_manifest,
    promotion_decision,
    score_blind_predictions,
    selective_invalidation_paths,
    split_evaluator_anchor_manifest,
    validate_anchor_split_manifest,
    validate_anchor_study_split,
)
from swebench_interview_cases.schemas import artifact_digest


DIGEST = "a" * 64


def _sealed(alias: str, *, marker: str) -> dict:
    return {
        "schema": "SealedSWEbenchSource.v1",
        "alias": alias,
        "inputs": {
            name: {"cache_key": f"sha256:{DIGEST}", "digest": DIGEST}
            for name in ("issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass")
        },
        "evidence": [
            {
                "id": "issue",
                "source": "issue",
                "knowledge_timing": "issue_time_author_knowable",
                "source_digest": DIGEST,
                "locator": "issue",
                "excerpt": "",
                "excerpt_digest": hashlib.sha256(b"").hexdigest(),
                "cache_required": True,
            }
        ],
        "material_decisions": [
            {
                "id": "D1",
                "description": f"required {marker}",
                "sources": ["issue"],
                "knowledge_timing": "issue_time_author_knowable",
                "materiality": "changes behavior",
                "owner_answer": "yes",
                "question_intent": "resolve behavior",
                "failure_if_missed": "omission",
                "evidence_ids": ["issue"],
            }
        ],
        "hindsight_observations": [
            {"id": "H1", "description": f"hindsight {marker}", "evidence_ids": ["issue"]}
        ],
        "implementation_incidentals": [
            {"id": "I1", "description": f"incidental {marker}", "evidence_ids": ["issue"]},
            {"id": "I2", "description": f"another incidental {marker}", "evidence_ids": ["issue"]},
        ],
        "review_state": {"status": "approved", "dispositions_complete": True},
    }


def _fixtures(tmp_path: Path) -> tuple[Path, list[Path]]:
    cases = []
    paths = []
    for alias, partition in (("dev", "development"), ("val", "validation"), ("secret", "holdout")):
        sealed = _sealed(alias, marker=alias)
        path = tmp_path / f"{alias}.json"
        path.write_text(json.dumps(sealed), encoding="utf-8")
        paths.append(path)
        cases.append({
            "alias": alias,
            "repository_family": f"family/{alias}",
            "partition": partition,
        })
    approved = tmp_path / "approved.json"
    approved.write_text(
        json.dumps({"schema": "SWEbenchApprovedPilotSealed.v1", "cases": cases}),
        encoding="utf-8",
    )
    return approved, paths


def test_generation_is_deterministic_development_only_and_single_fault(tmp_path: Path) -> None:
    approved, paths = _fixtures(tmp_path)
    first = generate_pairwise_anchor_manifest(approved, paths)
    second = generate_pairwise_anchor_manifest(approved, list(reversed(paths)))

    assert canonical_anchor_manifest_bytes(first) == canonical_anchor_manifest_bytes(second)
    assert first["anchor_corpus_sha256"] == artifact_digest(
        {"sources": first["sources"], "anchors": first["anchors"]}
    )
    assert first["sources"] == [
        {
            "alias": "dev",
            "repository_family": "family/dev",
            "sha256": first["sources"][0]["sha256"],
            "partition": "development",
        }
    ]
    assert len(first["anchors"]) == 2
    serialized = canonical_anchor_manifest_bytes(first)
    assert b"secret" not in serialized and b"holdout" not in serialized
    assert b"required val" not in serialized and b'"alias":"val"' not in serialized
    for anchor in first["anchors"]:
        assert anchor["confidence"] == "A"
        assert anchor["preferred"] in {"left", "right"}
        preferred = anchor[anchor["preferred"]]["text"]
        rejected_side = "right" if anchor["preferred"] == "left" else "left"
        rejected = anchor[rejected_side]["text"]
        assert rejected.startswith(preferred)
        assert [item["collection"] for item in anchor["provenance"]] == [
            "material_decisions",
            "implementation_incidentals",
        ]


def test_hindsight_is_only_confidence_b_and_paired_with_incidental(tmp_path: Path) -> None:
    approved, paths = _fixtures(tmp_path)
    manifest = generate_pairwise_anchor_manifest(
        approved, paths, include_hindsight_confidence_b=True
    )
    confidence_b = [item for item in manifest["anchors"] if item["confidence"] == "B"]
    assert len(confidence_b) == 2
    for anchor in confidence_b:
        assert anchor["fault"] == "hindsight_observation_vs_implementation_incidental"
        assert [item["collection"] for item in anchor["provenance"]] == [
            "hindsight_observations",
            "implementation_incidentals",
        ]


def test_material_omission_adds_hard_confidence_a_anchor(tmp_path: Path) -> None:
    approved, paths = _fixtures(tmp_path)
    manifest = generate_pairwise_anchor_manifest(
        approved, paths, include_material_omission_confidence_a=True,
    )
    boundary = [item for item in manifest["anchors"] if item.get("difficulty") == "boundary"]
    assert len(boundary) == 1
    anchor = boundary[0]
    assert anchor["confidence"] == "A"
    assert anchor["fault"] == "missing_material_owner_answer"
    preferred = anchor[anchor["preferred"]]["text"]
    rejected = anchor["right" if anchor["preferred"] == "left" else "left"]["text"]
    assert "Owner-approved answer:" in preferred
    assert "Owner-approved answer:" not in rejected


def test_zero_decision_boundary_anchor_uses_raw_issue_and_incidental_text(tmp_path: Path) -> None:
    approved, paths = _fixtures(tmp_path)
    dev_path = next(path for path in paths if path.stem == "dev")
    sealed = json.loads(dev_path.read_text())
    sealed["material_decisions"] = []
    sealed["evidence"][0]["excerpt"] = "The public request requires observable behavior."
    sealed["evidence"][0]["excerpt_digest"] = hashlib.sha256(
        sealed["evidence"][0]["excerpt"].encode()
    ).hexdigest()
    dev_path.write_text(json.dumps(sealed))
    manifest = generate_pairwise_anchor_manifest(
        approved, paths, include_material_omission_confidence_a=True,
    )
    boundary = [item for item in manifest["anchors"] if item.get("difficulty") == "boundary"]
    assert len(boundary) == len(sealed["implementation_incidentals"])
    texts = [side["text"] for item in boundary for side in (item["left"], item["right"])]
    assert not any("Additional required clause:" in text for text in texts)
    assert not any("No additional contract clause" in text for text in texts)
    assert {item["fault"] for item in boundary} == {
        "issue_requirement_vs_implementation_incidental"
    }


def test_spec_scoring_and_strict_promotion() -> None:
    anchors = [
        {"anchor_id": "one", "preferred": "left"},
        {"anchor_id": "two", "preferred": "left"},
    ]
    manifest = {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        "anchors": anchors,
        "anchor_corpus_sha256": artifact_digest(anchors),
    }
    incumbent = EvaluatorSpec("Prefer supported clauses.")
    challenger = EvaluatorSpec("Reject unsupported implementation details.")
    incumbent_score = score_blind_predictions(
        manifest, incumbent, {"one": "left", "two": "right"}
    )
    challenger_score = score_blind_predictions(
        manifest, challenger, {"one": "left", "two": "left"}
    )
    assert incumbent.sha256 == incumbent.as_dict()["sha256"]
    assert incumbent.as_dict()["identity_algorithm"] == "rubric-utf8-sha256-v1"
    assert promotion_decision(incumbent_score, challenger_score)["selected"] == "challenger"
    tied = score_blind_predictions(manifest, challenger, {"one": "left", "two": "right"})
    decision = promotion_decision(incumbent_score, tied)
    assert decision["selected"] == "incumbent" and decision["promoted"] is False
    assert freeze_epoch(3, challenger, manifest) == {
        "schema": "EvaluatorEpochFreeze.v1",
        "epoch": 3,
        "evaluator_sha256": challenger.sha256,
        "anchor_corpus_sha256": manifest["anchor_corpus_sha256"],
    }


def test_scoring_rejects_partial_predictions_and_cross_corpus_promotion() -> None:
    manifest = {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        "anchors": [{"anchor_id": "one", "preferred": "left"}],
        "anchor_corpus_sha256": "a" * 64,
    }
    spec = EvaluatorSpec("rubric")
    with pytest.raises(EvaluatorEvolutionError, match="exactly"):
        score_blind_predictions(manifest, spec, {})
    score = score_blind_predictions(manifest, spec, {"one": "tie"})
    drifted = {**score, "anchor_corpus_sha256": "b" * 64}
    with pytest.raises(EvaluatorEvolutionError, match="same anchor corpus"):
        promotion_decision(score, drifted)


def test_spec_loading_authenticates_identity_and_explicitly_supports_epoch1() -> None:
    spec = EvaluatorSpec("rubric")
    assert EvaluatorSpec.from_dict(spec.as_dict()) == spec
    legacy = {"schema": "EvaluatorSpec.v1", "rubric": spec.rubric, "sha256": spec.sha256}
    with pytest.raises(EvaluatorEvolutionError, match="explicit opt-in"):
        EvaluatorSpec.from_dict(legacy)
    assert EvaluatorSpec.from_dict(legacy, allow_legacy_epoch1=True) == spec
    with pytest.raises(EvaluatorEvolutionError, match="digest drifted"):
        EvaluatorSpec.from_dict({**spec.as_dict(), "sha256": "0" * 64})
    with pytest.raises(EvaluatorEvolutionError, match="identity algorithm"):
        EvaluatorSpec.from_dict({**spec.as_dict(), "identity_algorithm": "unknown"})


def _family_manifest(*families: str) -> dict:
    sources = [
        {
            "alias": f"case-{index}",
            "repository_family": family,
            "partition": "development",
            "sha256": f"{index + 1:064x}",
        }
        for index, family in enumerate(families)
    ]
    anchors = [
        {
            "schema": "PairwiseEvaluatorAnchor.v1",
            "anchor_id": f"anchor-{index}",
            "source": source,
            "preferred": "left",
            "confidence": "A",
            "left": {"text": "supported"},
            "right": {"text": "unsupported"},
        }
        for index, source in enumerate(sources)
    ]
    corpus = {"sources": sources, "anchors": anchors}
    return {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        **corpus,
        "anchor_corpus_sha256": artifact_digest(corpus),
    }


def test_family_split_is_deterministic_digest_sealed_and_disjoint() -> None:
    manifest = _family_manifest("org/a", "org/b", "org/c")
    first = split_evaluator_anchor_manifest(manifest, validation_families=1, seed="fixed")
    second = split_evaluator_anchor_manifest(manifest, validation_families=1, seed="fixed")
    assert first == second
    training, validation, split = first
    validate_anchor_study_split(training, validation)
    assert split["split_sha256"] == artifact_digest({
        key: value for key, value in split.items() if key not in {"schema", "split_sha256"}
    })
    assert set(split["training_families"]).isdisjoint(split["validation_families"])
    validate_anchor_split_manifest(training, validation, split)
    with pytest.raises(EvaluatorEvolutionError, match="does not bind"):
        validate_anchor_split_manifest(
            training, validation,
            {**split, "training_anchor_corpus_sha256": "0" * 64,
             "split_sha256": artifact_digest({
                 **{key: value for key, value in split.items() if key not in {"schema", "split_sha256"}},
                 "training_anchor_corpus_sha256": "0" * 64,
             })},
        )


def test_anchor_split_rejects_same_family_and_digest_drift() -> None:
    manifest = _family_manifest("org/a", "org/a")
    with pytest.raises(EvaluatorEvolutionError, match="non-empty train and validation"):
        split_evaluator_anchor_manifest(manifest)
    training = _family_manifest("org/a")
    validation = _family_manifest("org/a")
    with pytest.raises(EvaluatorEvolutionError, match="source crosses"):
        validate_anchor_study_split(training, validation)
    with pytest.raises(EvaluatorEvolutionError, match="digest drifted"):
        validate_anchor_study_split({**training, "anchor_corpus_sha256": "0" * 64}, validation)


def test_anchor_split_rejects_spoofed_embedded_source() -> None:
    manifest = _family_manifest("org/a", "org/b")
    manifest["anchors"][0]["source"] = {
        **manifest["anchors"][0]["source"], "alias": "spoofed-alias",
    }
    corpus = {"sources": manifest["sources"], "anchors": manifest["anchors"]}
    manifest["anchor_corpus_sha256"] = artifact_digest(corpus)
    with pytest.raises(EvaluatorEvolutionError, match="not bound"):
        split_evaluator_anchor_manifest(manifest)


def test_promotion_rejects_aggregate_gain_that_regresses_a_anchor_and_family() -> None:
    anchors = [
        {
            "anchor_id": anchor_id,
            "preferred": "left",
            "confidence": "A",
            "source": {"repository_family": family},
        }
        for anchor_id, family in (("a", "org/a"), ("b", "org/b"), ("c", "org/b"))
    ]
    manifest = {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        "anchors": anchors,
        "anchor_corpus_sha256": artifact_digest(anchors),
    }
    incumbent = score_blind_predictions(
        manifest, EvaluatorSpec("incumbent"), {"a": "left", "b": "right", "c": "right"}
    )
    challenger = score_blind_predictions(
        manifest, EvaluatorSpec("challenger"), {"a": "right", "b": "left", "c": "left"}
    )
    decision = promotion_decision(incumbent, challenger)
    assert challenger["correct"] > incumbent["correct"]
    assert decision["promoted"] is False
    assert decision["confidence_a_regressions"] == ["a"]
    assert decision["family_regressions"] == ["org/a"]


def test_selective_invalidation_preserves_raw_artifacts() -> None:
    paths = [
        Path("run/contract.json"),
        Path("run/transcript.json"),
        Path("run/evidence.json"),
        Path("run/implementation.json"),
        Path("run/judge.json"),
        Path("run/adjudication.json"),
        Path("batch/development-selection.json"),
        Path("unrelated.json"),
    ]
    assert selective_invalidation_paths(paths) == (
        Path("batch/development-selection.json"),
        Path("run/judge.json"),
    )
