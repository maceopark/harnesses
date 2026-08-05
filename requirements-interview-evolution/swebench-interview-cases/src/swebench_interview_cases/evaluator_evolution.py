"""Deterministic evaluator anchors and conservative evaluator promotion.

This module deliberately does not ask a model to invent anchor labels.  Labels
come from the approved sealed source: material decisions are required clauses,
while each implementation incidental supplies exactly one unsupported clause.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .schemas import artifact_digest, canonical_json_bytes, validate_sealed_source
from .model import CodexJsonModel


class EvaluatorEvolutionError(ValueError):
    """Raised when evaluator-evolution artifacts are inconsistent."""


@dataclass(frozen=True)
class EvaluatorSpec:
    """A content-addressed, versioned evaluator rubric."""

    rubric: str
    version: str = "EvaluatorSpec.v1"

    IDENTITY_ALGORITHM = "rubric-utf8-sha256-v1"

    def __post_init__(self) -> None:
        if self.version != "EvaluatorSpec.v1":
            raise EvaluatorEvolutionError("unsupported evaluator spec version")
        if not self.rubric.strip():
            raise EvaluatorEvolutionError("evaluator rubric must not be empty")

    @property
    def sha256(self) -> str:
        # The runtime judge consumes exactly these UTF-8 rubric bytes.  Use the
        # same identity in specs, epoch records, and run manifests.
        return hashlib.sha256(self.rubric.encode()).hexdigest()

    def as_dict(self) -> dict[str, str]:
        return {
            "schema": self.version,
            "identity_algorithm": self.IDENTITY_ALGORITHM,
            "rubric": self.rubric,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any], *, allow_legacy_epoch1: bool = False
    ) -> EvaluatorSpec:
        """Load and authenticate a persisted evaluator specification.

        Epoch 1 predates the explicit identity-algorithm field but already used
        the same rubric-byte digest.  Accept that representation only through
        the named compatibility switch so new callers cannot silently create
        more unversioned artifacts.
        """

        if value.get("schema") != "EvaluatorSpec.v1":
            raise EvaluatorEvolutionError("unsupported evaluator spec version")
        algorithm = value.get("identity_algorithm")
        if algorithm is None:
            if not allow_legacy_epoch1:
                raise EvaluatorEvolutionError("legacy evaluator identity requires explicit opt-in")
        elif algorithm != cls.IDENTITY_ALGORITHM:
            raise EvaluatorEvolutionError("unsupported evaluator identity algorithm")
        rubric = value.get("rubric")
        if not isinstance(rubric, str):
            raise EvaluatorEvolutionError("evaluator rubric must be a string")
        spec = cls(rubric=rubric)
        if value.get("sha256") != spec.sha256:
            raise EvaluatorEvolutionError("evaluator spec digest drifted")
        return spec


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _provenance(item: Mapping[str, Any], *, collection: str) -> dict[str, Any]:
    return {
        "collection": collection,
        "item_id": item["id"],
        "evidence_ids": sorted(str(value) for value in item["evidence_ids"]),
    }


def _clause(item: Mapping[str, Any], *, required: bool) -> str:
    if required:
        return f"{item['description']} Owner-approved answer: {item['owner_answer']}"
    return str(item["description"])


def _randomized_pair(
    *, source_sha256: str, preferred_text: str, rejected_text: str, salt: str,
) -> tuple[dict[str, str], dict[str, str], str]:
    """Deterministically blind side placement without exposing label patterns."""

    preferred_left = int(hashlib.sha256(f"{source_sha256}:{salt}".encode()).hexdigest(), 16) % 2 == 0
    if preferred_left:
        return {"text": preferred_text}, {"text": rejected_text}, "left"
    return {"text": rejected_text}, {"text": preferred_text}, "right"


def generate_pairwise_anchor_manifest(
    approved_sealed_path: Path,
    sealed_source_paths: Sequence[Path],
    *,
    include_hindsight_confidence_b: bool = False,
    include_material_omission_confidence_a: bool = False,
) -> dict[str, Any]:
    """Build a canonical development-only pairwise anchor corpus.

    Every confidence-A negative differs from its positive by one incidental.
    Optional hindsight anchors never stand alone: a hindsight observation is
    compared only with one incidental and is explicitly marked confidence B.
    """

    approved = _read_json(approved_sealed_path)
    if approved.get("schema") != "SWEbenchApprovedPilotSealed.v1":
        raise EvaluatorEvolutionError("unsupported approved selection schema")
    cases = {str(item["alias"]): item for item in approved.get("cases", [])}
    anchors: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []

    for path in sorted((Path(value) for value in sealed_source_paths), key=str):
        sealed = _read_json(path)
        validate_sealed_source(sealed)
        alias = str(sealed["alias"])
        selected = cases.get(alias)
        if selected is None:
            raise EvaluatorEvolutionError(f"sealed source is not approved: {alias}")
        partition = str(selected["partition"])
        if partition != "development":
            continue
        source_sha256 = hashlib.sha256(canonical_json_bytes(sealed)).hexdigest()
        repository_family = str(selected.get("repository_family") or alias)
        source = {
            "alias": alias,
            "repository_family": repository_family,
            "sha256": source_sha256,
            "partition": partition,
        }
        sources.append(source)

        for decision in sealed["material_decisions"]:
            positive = _clause(decision, required=True)
            if include_material_omission_confidence_a:
                rejected = f"Required outcome: {decision['description']}"
                left, right, preferred = _randomized_pair(
                    source_sha256=source_sha256, preferred_text=positive,
                    rejected_text=rejected, salt=f"{decision['id']}:missing-owner-answer",
                )
                payload = {
                    "schema": "PairwiseEvaluatorAnchor.v1",
                    "source": source,
                    "preferred": preferred,
                    "confidence": "A",
                    "difficulty": "boundary",
                    "left": left,
                    "right": right,
                    "fault": "missing_material_owner_answer",
                    "provenance": [
                        _provenance(decision, collection="material_decisions"),
                    ],
                }
                payload["anchor_id"] = artifact_digest(payload)
                anchors.append(payload)
            for incidental in sealed["implementation_incidentals"]:
                rejected = f"{positive}\nAdditional required clause: {_clause(incidental, required=False)}"
                left, right, preferred = _randomized_pair(
                    source_sha256=source_sha256, preferred_text=positive,
                    rejected_text=rejected, salt=f"{decision['id']}:{incidental['id']}",
                )
                payload = {
                    "schema": "PairwiseEvaluatorAnchor.v1",
                    "source": source,
                    "preferred": preferred,
                    "confidence": "A",
                    "left": left,
                    "right": right,
                    "fault": "unsupported_implementation_incidental",
                    "provenance": [
                        _provenance(decision, collection="material_decisions"),
                        _provenance(incidental, collection="implementation_incidentals"),
                    ],
                }
                payload["anchor_id"] = artifact_digest(payload)
                anchors.append(payload)

        if include_material_omission_confidence_a and not sealed["material_decisions"]:
            issue_evidence = [
                item for item in sealed["evidence"]
                if item["source"] == "issue"
                and item["knowledge_timing"] == "issue_time_author_knowable"
                and str(item["excerpt"]).strip()
            ]
            if not issue_evidence:
                raise EvaluatorEvolutionError(
                    f"boundary anchor requires issue-time evidence: {alias}"
                )
            preferred_text = str(issue_evidence[0]["excerpt"])
            for incidental in sealed["implementation_incidentals"]:
                rejected = _clause(incidental, required=False)
                left, right, preferred = _randomized_pair(
                    source_sha256=source_sha256, preferred_text=preferred_text,
                    rejected_text=rejected, salt=f"{incidental['id']}:unsupported-only-clause",
                )
                payload = {
                    "schema": "PairwiseEvaluatorAnchor.v1", "source": source,
                    "preferred": preferred, "confidence": "A", "difficulty": "boundary",
                    "left": left, "right": right,
                    "fault": "issue_requirement_vs_implementation_incidental",
                    "provenance": [
                        {
                            "collection": "evidence", "item_id": issue_evidence[0]["id"],
                            "evidence_ids": [issue_evidence[0]["id"]],
                        },
                        _provenance(incidental, collection="implementation_incidentals"),
                    ],
                }
                payload["anchor_id"] = artifact_digest(payload)
                anchors.append(payload)

        if include_hindsight_confidence_b:
            for observation in sealed["hindsight_observations"]:
                for incidental in sealed["implementation_incidentals"]:
                    left, right, preferred = _randomized_pair(
                        source_sha256=source_sha256,
                        preferred_text=str(observation["description"]),
                        rejected_text=str(incidental["description"]),
                        salt=f"{observation['id']}:{incidental['id']}",
                    )
                    payload = {
                        "schema": "PairwiseEvaluatorAnchor.v1",
                        "source": source,
                        "preferred": preferred,
                        "confidence": "B",
                        "left": left,
                        "right": right,
                        "fault": "hindsight_observation_vs_implementation_incidental",
                        "provenance": [
                            _provenance(observation, collection="hindsight_observations"),
                            _provenance(incidental, collection="implementation_incidentals"),
                        ],
                    }
                    payload["anchor_id"] = artifact_digest(payload)
                    anchors.append(payload)

    sources.sort(key=lambda item: (item["alias"], item["sha256"]))
    anchors.sort(key=lambda item: item["anchor_id"])
    corpus = {"sources": sources, "anchors": anchors}
    return {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        **corpus,
        "anchor_corpus_sha256": artifact_digest(corpus),
    }


def canonical_anchor_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Return the byte-stable representation used for persisted manifests."""

    return canonical_json_bytes(manifest)


def _anchor_manifest(sources: Sequence[Mapping[str, Any]], anchors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    corpus = {
        "sources": sorted((dict(item) for item in sources), key=lambda item: (item["alias"], item["sha256"])),
        "anchors": sorted((dict(item) for item in anchors), key=lambda item: item["anchor_id"]),
    }
    return {
        "schema": "PairwiseEvaluatorAnchorManifest.v1",
        **corpus,
        "anchor_corpus_sha256": artifact_digest(corpus),
    }


def _validate_anchor_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != "PairwiseEvaluatorAnchorManifest.v1":
        raise EvaluatorEvolutionError("invalid anchor manifest")
    sources = manifest.get("sources")
    anchors = manifest.get("anchors")
    if not isinstance(sources, list) or not isinstance(anchors, list):
        raise EvaluatorEvolutionError("invalid anchor manifest")
    expected = artifact_digest({"sources": sources, "anchors": anchors})
    if manifest.get("anchor_corpus_sha256") != expected:
        raise EvaluatorEvolutionError("anchor corpus digest drifted")
    if any(not str(item.get("repository_family", "")).strip() for item in sources):
        raise EvaluatorEvolutionError("anchor source repository family is required")
    source_ids = [str(item.get("sha256", "")) for item in sources]
    anchor_ids = [str(item.get("anchor_id", "")) for item in anchors]
    if not all(source_ids) or len(source_ids) != len(set(source_ids)):
        raise EvaluatorEvolutionError("anchor source identities must be unique")
    if not all(anchor_ids) or len(anchor_ids) != len(set(anchor_ids)):
        raise EvaluatorEvolutionError("anchor identities must be unique")
    sources_by_sha = {str(item["sha256"]): item for item in sources}
    for anchor in anchors:
        embedded = anchor.get("source")
        if not isinstance(embedded, dict) or embedded != sources_by_sha.get(str(embedded.get("sha256"))):
            raise EvaluatorEvolutionError("anchor source is not bound to its declared source")


def split_evaluator_anchor_manifest(
    manifest: Mapping[str, Any], *, validation_families: int = 1, seed: str = "evaluator-anchor-split-v1"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Deterministically split one corpus at the indivisible family boundary."""

    _validate_anchor_manifest(manifest)
    families = sorted(
        {str(item["repository_family"]) for item in manifest["sources"]},
        key=lambda family: (hashlib.sha256(f"{seed}:{family}".encode()).hexdigest(), family),
    )
    if validation_families < 1 or validation_families >= len(families):
        raise EvaluatorEvolutionError("anchor split requires non-empty train and validation families")
    validation_set = set(families[:validation_families])
    def build(*, validation: bool) -> dict[str, Any]:
        selected_sources = [
            item for item in manifest["sources"]
            if (str(item["repository_family"]) in validation_set) is validation
        ]
        selected_sha = {str(item["sha256"]) for item in selected_sources}
        selected_anchors = [
            item for item in manifest["anchors"]
            if str(item["source"]["sha256"]) in selected_sha
        ]
        return _anchor_manifest(selected_sources, selected_anchors)

    training = build(validation=False)
    validation = build(validation=True)
    validate_anchor_study_split(training, validation)
    split_payload = {
        "parent_anchor_corpus_sha256": manifest["anchor_corpus_sha256"],
        "seed": seed,
        "training_anchor_corpus_sha256": training["anchor_corpus_sha256"],
        "validation_anchor_corpus_sha256": validation["anchor_corpus_sha256"],
        "training_families": sorted(set(families) - validation_set),
        "validation_families": sorted(validation_set),
    }
    split = {
        "schema": "EvaluatorAnchorSplit.v1",
        **split_payload,
        "split_sha256": artifact_digest(split_payload),
    }
    return training, validation, split


def validate_anchor_study_split(
    training_manifest: Mapping[str, Any], validation_manifest: Mapping[str, Any]
) -> None:
    """Fail closed when evaluator training and validation share evidence or family."""

    _validate_anchor_manifest(training_manifest)
    _validate_anchor_manifest(validation_manifest)
    training_sources = {str(item["sha256"]) for item in training_manifest["sources"]}
    validation_sources = {str(item["sha256"]) for item in validation_manifest["sources"]}
    training_families = {str(item["repository_family"]) for item in training_manifest["sources"]}
    validation_families = {str(item["repository_family"]) for item in validation_manifest["sources"]}
    if training_sources & validation_sources:
        raise EvaluatorEvolutionError("anchor source crosses training and validation")
    if training_families & validation_families:
        raise EvaluatorEvolutionError("repository family crosses evaluator training and validation")


def validate_anchor_split_manifest(
    training_manifest: Mapping[str, Any], validation_manifest: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
) -> None:
    """Bind persisted train/validation manifests to their signed split descriptor."""

    validate_anchor_study_split(training_manifest, validation_manifest)
    if split_manifest.get("schema") != "EvaluatorAnchorSplit.v1":
        raise EvaluatorEvolutionError("invalid anchor split manifest")
    payload = {key: value for key, value in split_manifest.items() if key not in {"schema", "split_sha256"}}
    if split_manifest.get("split_sha256") != artifact_digest(payload):
        raise EvaluatorEvolutionError("anchor split digest drifted")
    if (
        split_manifest.get("training_anchor_corpus_sha256")
        != training_manifest.get("anchor_corpus_sha256")
        or split_manifest.get("validation_anchor_corpus_sha256")
        != validation_manifest.get("anchor_corpus_sha256")
    ):
        raise EvaluatorEvolutionError("anchor split does not bind supplied corpora")


def score_blind_predictions(
    manifest: Mapping[str, Any],
    evaluator: EvaluatorSpec,
    predictions: Mapping[str, str],
) -> dict[str, Any]:
    """Purely score blind left/right/tie predictions against an anchor corpus."""

    anchors = manifest.get("anchors")
    if manifest.get("schema") != "PairwiseEvaluatorAnchorManifest.v1" or not isinstance(
        anchors, list
    ):
        raise EvaluatorEvolutionError("invalid anchor manifest")
    expected_ids = {str(item["anchor_id"]) for item in anchors}
    if set(predictions) != expected_ids:
        raise EvaluatorEvolutionError("predictions must cover the anchor corpus exactly")
    if any(value not in {"left", "right", "tie"} for value in predictions.values()):
        raise EvaluatorEvolutionError("prediction must be left, right, or tie")
    result_rows = []
    for item in sorted(anchors, key=lambda row: str(row["anchor_id"])):
        anchor_id = str(item["anchor_id"])
        prediction = predictions[anchor_id]
        source = item.get("source", {})
        result_rows.append({
            "anchor_id": anchor_id,
            "confidence": str(item.get("confidence", "B")),
            "repository_family": str(source.get("repository_family") or source.get("alias") or "legacy"),
            "prediction": prediction,
            "correct": prediction == item["preferred"],
        })
    correct = sum(bool(item["correct"]) for item in result_rows)
    ties = sum(value == "tie" for value in predictions.values())
    prediction_rows = [
        {"anchor_id": anchor_id, "prediction": predictions[anchor_id]}
        for anchor_id in sorted(predictions)
    ]
    return {
        "schema": "BlindEvaluatorScore.v1",
        "evaluator_sha256": evaluator.sha256,
        "anchor_corpus_sha256": manifest["anchor_corpus_sha256"],
        "prediction_sha256": artifact_digest(prediction_rows),
        "total": len(anchors),
        "correct": correct,
        "incorrect": len(anchors) - correct - ties,
        "ties": ties,
        "results": result_rows,
    }


def promotion_decision(
    incumbent_score: Mapping[str, Any], challenger_score: Mapping[str, Any]
) -> dict[str, Any]:
    """Promote only a strictly more accurate challenger on the exact same corpus."""

    if incumbent_score.get("schema") != "BlindEvaluatorScore.v1" or challenger_score.get(
        "schema"
    ) != "BlindEvaluatorScore.v1":
        raise EvaluatorEvolutionError("promotion requires blind evaluator scores")
    if incumbent_score.get("anchor_corpus_sha256") != challenger_score.get(
        "anchor_corpus_sha256"
    ) or incumbent_score.get("total") != challenger_score.get("total"):
        raise EvaluatorEvolutionError("scores do not use the same anchor corpus")
    incumbent_rows = incumbent_score.get("results")
    challenger_rows = challenger_score.get("results")
    if not isinstance(incumbent_rows, list) or not isinstance(challenger_rows, list):
        raise EvaluatorEvolutionError("promotion requires per-anchor score results")
    incumbent_by_id = {str(item["anchor_id"]): item for item in incumbent_rows}
    challenger_by_id = {str(item["anchor_id"]): item for item in challenger_rows}
    if set(incumbent_by_id) != set(challenger_by_id):
        raise EvaluatorEvolutionError("scores do not cover the same anchors")
    incumbent_errors = {
        anchor_id for anchor_id, item in incumbent_by_id.items() if not item["correct"]
    }
    challenger_errors = {
        anchor_id for anchor_id, item in challenger_by_id.items() if not item["correct"]
    }
    metadata_drift = any(
        (
            incumbent_by_id[anchor_id]["confidence"],
            incumbent_by_id[anchor_id]["repository_family"],
        )
        != (
            challenger_by_id[anchor_id]["confidence"],
            challenger_by_id[anchor_id]["repository_family"],
        )
        for anchor_id in incumbent_by_id
    )
    if metadata_drift:
        raise EvaluatorEvolutionError("anchor metadata drifted between scores")
    error_subset = challenger_errors < incumbent_errors
    confidence_a_regressions = sorted(
        anchor_id for anchor_id in challenger_errors - incumbent_errors
        if challenger_by_id[anchor_id]["confidence"] == "A"
    )
    families = {str(item["repository_family"]) for item in incumbent_rows}
    family_regressions = sorted(
        family for family in families
        if sum(
            bool(item["correct"]) for item in challenger_rows
            if item["repository_family"] == family
        )
        < sum(
            bool(item["correct"]) for item in incumbent_rows
            if item["repository_family"] == family
        )
    )
    promote = error_subset and not confidence_a_regressions and not family_regressions
    selected = "challenger" if promote else "incumbent"
    return {
        "schema": "EvaluatorPromotionDecision.v1",
        "anchor_corpus_sha256": incumbent_score["anchor_corpus_sha256"],
        "incumbent_evaluator_sha256": incumbent_score["evaluator_sha256"],
        "challenger_evaluator_sha256": challenger_score["evaluator_sha256"],
        "incumbent_correct": incumbent_score["correct"],
        "challenger_correct": challenger_score["correct"],
        "promoted": promote,
        "selected": selected,
        "incumbent_error_anchor_ids": sorted(incumbent_errors),
        "challenger_error_anchor_ids": sorted(challenger_errors),
        "confidence_a_regressions": confidence_a_regressions,
        "family_regressions": family_regressions,
        "rule": "challenger errors are a strict subset; confidence-A and family regressions are forbidden; ties retain incumbent",
    }


_CHALLENGER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["rubric", "rationale"],
    "properties": {"rubric": {"type": "string"}, "rationale": {"type": "string"}},
}


def _prediction_schema(anchor_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "required": ["predictions"],
        "properties": {"predictions": {
            "type": "array", "minItems": len(anchor_ids), "maxItems": len(anchor_ids),
            "items": {"type": "object", "additionalProperties": False,
                "required": ["anchor_id", "choice"],
                "properties": {
                    "anchor_id": {"enum": list(anchor_ids)},
                    "choice": {"enum": ["left", "right", "tie"]},
                }},
        }},
    }


def _blind_anchor_payload(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"anchor_id": item["anchor_id"], "left": item["left"], "right": item["right"]}
        for item in manifest["anchors"]
    ]


def evolve_evaluator_once(
    *, incumbent: EvaluatorSpec, training_manifest: Mapping[str, Any],
    validation_manifest: Mapping[str, Any], output_dir: Path,
    split_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate one challenger from training anchors and blind-test both on validation anchors."""

    if split_manifest is None:
        validate_anchor_study_split(training_manifest, validation_manifest)
    else:
        validate_anchor_split_manifest(training_manifest, validation_manifest, split_manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    model = CodexJsonModel(output_dir / "calls")
    challenger_result = model.generate(
        role="evaluator-mutator",
        instructions=(
            "Improve the contract-evaluation rubric using the labeled training pairs. Keep it concise, "
            "general, evidence-bound, and independent of case names. Do not encode anchor IDs, quoted "
            "examples, repositories, or side positions. The rubric must distinguish required observable "
            "behavior from unsupported implementation incidentals and hindsight-only choices."
        ),
        payload={"incumbent_rubric": incumbent.rubric, "training_anchors": training_manifest["anchors"]},
        schema=_CHALLENGER_SCHEMA,
    )
    challenger = EvaluatorSpec(challenger_result["rubric"])
    anchor_ids = [str(item["anchor_id"]) for item in validation_manifest["anchors"]]
    scores = []
    for label, evaluator in (("incumbent", incumbent), ("challenger", challenger)):
        result = model.generate(
            role=f"evaluator-{label}-blind",
            instructions=(
                "Apply the frozen rubric to each blind pair. Choose the clause that is the better "
                "runtime contract: materially complete but no broader or more implementation-specific "
                "than the evidence supports. Return every anchor exactly once.\nRUBRIC:\n"
                f"{evaluator.rubric}"
            ),
            payload={"anchors": _blind_anchor_payload(validation_manifest)},
            schema=_prediction_schema(anchor_ids),
        )
        predictions = {row["anchor_id"]: row["choice"] for row in result["predictions"]}
        if len(predictions) != len(anchor_ids):
            raise EvaluatorEvolutionError("blind predictions contain duplicate anchor IDs")
        scores.append(score_blind_predictions(validation_manifest, evaluator, predictions))
    decision = promotion_decision(scores[0], scores[1])
    selected = challenger if decision["promoted"] else incumbent
    artifacts = {
        "incumbent": incumbent.as_dict(), "challenger": challenger.as_dict(),
        "challenger_rationale": challenger_result["rationale"],
        "incumbent_score": scores[0], "challenger_score": scores[1],
        "promotion": decision, "selected": selected.as_dict(),
    }
    for name, value in artifacts.items():
        (output_dir / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
    return artifacts


def verify_evaluator_epoch(
    *, validation_manifest: Mapping[str, Any], evolution_dir: Path,
    run_root: Path, decision_path: Path,
    training_manifest: Mapping[str, Any] | None = None,
    split_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute promotion and prove one evaluator identity was frozen in the generation."""

    if (training_manifest is None) != (split_manifest is None):
        raise EvaluatorEvolutionError("evaluator split verification inputs must be supplied together")
    if training_manifest is not None and split_manifest is not None:
        validate_anchor_split_manifest(training_manifest, validation_manifest, split_manifest)
    incumbent_data = _read_json(evolution_dir / "incumbent.json")
    challenger_data = _read_json(evolution_dir / "challenger.json")
    incumbent = EvaluatorSpec.from_dict(incumbent_data, allow_legacy_epoch1=True)
    challenger = EvaluatorSpec.from_dict(challenger_data, allow_legacy_epoch1=True)
    labels = ("incumbent", "challenger")
    evaluators = (incumbent, challenger)
    scores = []
    for sequence, (label, evaluator) in enumerate(zip(labels, evaluators), start=2):
        record = _read_json(evolution_dir / "calls" / f"{sequence:03d}-evaluator-{label}-blind.json")
        result = json.loads(record["stdout"])
        predictions = {row["anchor_id"]: row["choice"] for row in result["predictions"]}
        score = score_blind_predictions(validation_manifest, evaluator, predictions)
        if score != _read_json(evolution_dir / f"{label}_score.json"):
            raise EvaluatorEvolutionError(f"{label} score drifted")
        scores.append(score)
    promotion = promotion_decision(scores[0], scores[1])
    if promotion != _read_json(evolution_dir / "promotion.json"):
        raise EvaluatorEvolutionError("promotion decision drifted")
    selected_data = _read_json(evolution_dir / "selected.json")
    selected = challenger if promotion["promoted"] else incumbent
    if selected_data.get("rubric") != selected.rubric or selected_data.get("sha256") != selected.sha256:
        raise EvaluatorEvolutionError("selected evaluator contradicts promotion")
    decision = _read_json(decision_path)
    manifests = [_read_json(path) for path in sorted(run_root.rglob("run-manifest.json"))]
    observed = {item.get("evaluator_sha256") for item in manifests}
    if observed != {selected.sha256} or decision.get("evaluator_sha256") != selected.sha256:
        raise EvaluatorEvolutionError("generation did not freeze the selected evaluator")
    return {
        "schema": "EvaluatorEpochVerification.v1", "verified": True,
        "anchor_corpus_sha256": validation_manifest["anchor_corpus_sha256"],
        "incumbent_correct": scores[0]["correct"], "challenger_correct": scores[1]["correct"],
        "promoted": promotion["promoted"], "selected_evaluator_sha256": selected.sha256,
        "run_manifests": len(manifests), "evaluator_identities_in_generation": len(observed),
    }


def freeze_epoch(
    epoch: int, evaluator: EvaluatorSpec, anchor_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Freeze evaluator identity and anchor corpus for one immutable epoch."""

    if epoch < 0:
        raise EvaluatorEvolutionError("epoch must be non-negative")
    return {
        "schema": "EvaluatorEpochFreeze.v1",
        "epoch": epoch,
        "evaluator_sha256": evaluator.sha256,
        "anchor_corpus_sha256": anchor_manifest["anchor_corpus_sha256"],
    }


_RAW_ARTIFACTS = frozenset(
    {"contract.json", "transcript.json", "evidence.json", "discovery.json", "implementation.json"}
)
_EVALUATOR_DERIVED = frozenset(
    {
        "judge.json",
        "development-selection.json",
        "strategy-outcomes.json",
        "decision.json",
        "completion-verification.json",
        "evaluator-score.json",
        "evaluator-promotion.json",
    }
)


def selective_invalidation_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Select evaluator-derived artifacts while preserving raw execution evidence."""

    selected: set[Path] = set()
    for value in paths:
        path = Path(value)
        if path.name in _RAW_ARTIFACTS:
            continue
        if path.name in _EVALUATOR_DERIVED:
            selected.add(path)
    return tuple(sorted(selected, key=str))
