"""Digest-sealed coordinator for one evaluator/skill co-evolution epoch."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .batch import development_signals
from .cache import ContentAddressedCache
from .evaluator_evolution import (
    EvaluatorSpec, canonical_anchor_manifest_bytes, evolve_evaluator_once,
    generate_pairwise_anchor_manifest, split_evaluator_anchor_manifest,
    validate_anchor_split_manifest, verify_evaluator_epoch,
)
from .execute import execute_study
from .implementer import (
    DECISION_MATERIALITY_RUBRIC_SHA256,
    DECISION_MATERIALITY_SCHEMA_VERSION,
)
from . import MODEL_ID, MODEL_REASONING_EFFORT
from .replay import (
    materialize_materiality_run_views, materialize_rejudged_run_views,
    run_replay_2x2,
)
from .schemas import artifact_digest
from .verify import (
    _write_verified_promotion, verify_completed_pilot, verify_development_rejection,
)


class EpochError(RuntimeError):
    """Raised when a co-evolution epoch cannot preserve its identity contract."""


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "receipt.json"
    }


def _valid_receipt(attempt: Path, input_sha256: str) -> bool:
    receipt_path = attempt / "receipt.json"
    if not receipt_path.is_file():
        return False
    receipt = _read(receipt_path)
    payload = {key: value for key, value in receipt.items() if key not in {"schema", "receipt_sha256"}}
    if receipt.get("receipt_sha256") != artifact_digest(payload):
        return False
    return receipt.get("input_sha256") == input_sha256 and receipt.get("files") == _tree(attempt)


def _stage(
    stages_root: Path, name: str, input_identity: Mapping[str, Any],
    operation: Callable[[Path], None],
) -> Path:
    root = stages_root / name
    input_sha256 = artifact_digest(input_identity)
    for attempt in sorted(root.glob("attempt-*")):
        if _valid_receipt(attempt, input_sha256):
            return attempt
    root.mkdir(parents=True, exist_ok=True)
    attempt = root / f"attempt-{len(list(root.glob('attempt-*'))) + 1:03d}"
    attempt.mkdir()
    operation(attempt)
    payload = {"stage": name, "input_sha256": input_sha256, "files": _tree(attempt)}
    receipt = {"schema": "RQGMStageReceipt.v1", **payload, "receipt_sha256": artifact_digest(payload)}
    _atomic_json(attempt / "receipt.json", receipt)
    return attempt


def _file_identity(path: Path) -> dict[str, str]:
    return {"name": path.name, "sha256": _sha(path)}


def _corpus_manifest_path(corpus_root: Path) -> Path:
    for name in ("pilot-manifest.json", "manifest.json"):
        candidate = corpus_root / name
        if candidate.is_file():
            return candidate
    raise EpochError("recorded corpus manifest is missing")


def _run_identities(paths: list[Path]) -> list[dict[str, str]]:
    identities = []
    for path in paths:
        manifest_path = path / "run-manifest.json"
        manifest = _read(manifest_path)
        identities.append({"alias": str(manifest.get("alias")), "sha256": _sha(manifest_path)})
    return sorted(identities, key=lambda item: item["alias"])


def _corpus_case_identities(
    sealed_approved: Path, corpus_root: Path,
) -> list[dict[str, str]]:
    identities = []
    for case in _read(sealed_approved).get("cases", []):
        partition = str(case.get("partition"))
        if partition == "holdout":
            continue
        alias = str(case.get("alias"))
        case_dir = corpus_root / "cases" / alias
        public_path = case_dir / "case.json"
        sealed_path = case_dir / "sealed-source.json"
        if not public_path.is_file() or not sealed_path.is_file():
            raise EpochError(
                f"recorded corpus is missing {partition} case inputs for {alias}"
            )
        identities.append({
            "alias": alias,
            "partition": partition,
            "case_sha256": _sha(public_path),
            "sealed_source_sha256": _sha(sealed_path),
        })
    return sorted(identities, key=lambda item: (item["partition"], item["alias"]))


def _harness_evidence_identities(
    sealed_approved: Path, corpus_root: Path, harness_evidence_root: Path,
) -> list[dict[str, Any]]:
    identities = []
    for case in _read(sealed_approved).get("cases", []):
        alias = str(case.get("alias"))
        instance_id = str(case.get("instance_id"))
        partition = str(case.get("partition"))
        case_dir = (
            sealed_approved.parent / "holdout-cases" / alias
            if partition == "holdout"
            else corpus_root / "cases" / alias
        )
        preparation_path = case_dir / "run-manifest.json"
        evidence_path = harness_evidence_root / instance_id / "harness-evidence.json"
        if not preparation_path.is_file() or not evidence_path.is_file():
            raise EpochError(
                f"recorded harness evidence is missing for {partition} case {alias}"
            )
        preparation = _read(preparation_path)
        evidence = _read(evidence_path)
        evidence_digest = artifact_digest(evidence)
        if preparation.get("harness_evidence_sha256") != evidence_digest:
            raise EpochError(
                f"recorded harness evidence digest drifted for {partition} case {alias}"
            )
        reports = []
        for kind in ("baseline", "gold"):
            for relative, expected_digest in evidence.get(kind, {}).get(
                "report_sha256", {}
            ).items():
                report_path = harness_evidence_root.parent / relative
                if not report_path.is_file() or _sha(report_path) != expected_digest:
                    raise EpochError(
                        f"recorded harness report is missing or drifted for "
                        f"{partition} case {alias}"
                    )
                reports.append({
                    "kind": kind,
                    "path": relative,
                    "sha256": expected_digest,
                })
        identities.append({
            "alias": alias,
            "instance_id": instance_id,
            "partition": partition,
            "preparation_sha256": _sha(preparation_path),
            "evidence_sha256": _sha(evidence_path),
            "evidence_artifact_digest": evidence_digest,
            "reports": sorted(reports, key=lambda item: (item["kind"], item["path"])),
        })
    return sorted(identities, key=lambda item: (item["partition"], item["alias"]))


def _materiality_evaluator_identity() -> dict[str, str]:
    return {
        "rubric_sha256": DECISION_MATERIALITY_RUBRIC_SHA256,
        "schema_version": DECISION_MATERIALITY_SCHEMA_VERSION,
        "reviewer_model": MODEL_ID,
        "reviewer_reasoning_effort": MODEL_REASONING_EFFORT,
    }


def _decision_review_bundle_digest(root: Path) -> str:
    reviews = {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(root.rglob("decision-materiality.json"))
    }
    return artifact_digest(reviews)


def run_coevolution_epoch(*, config_path: Path, output_root: Path) -> dict[str, Any]:
    """Run and verify one complete co-evolution epoch, committing its manifest last."""

    config = _read(config_path)
    if config.get("schema") != "RQGMEpochConfig.v1":
        raise EpochError("unsupported epoch config schema")
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".epoch.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise EpochError("epoch is already running") from error

        path = lambda key: Path(config[key]).resolve()
        paths = lambda key: [Path(value).resolve() for value in config[key]]
        baseline_runs = paths("baseline_runs")
        mutation_runs = paths("mutation_signal_runs")
        anchor_sources = paths("anchor_sources")
        corpus_case_identities = _corpus_case_identities(
            path("sealed_approved"), path("corpus_root"),
        )
        harness_evidence_identities = (
            _harness_evidence_identities(
                path("sealed_approved"), path("corpus_root"),
                path("harness_evidence_root"),
            )
            if "harness_evidence_root" in config else []
        )
        input_payload = {
            "config": config,
            "config_sha256": _sha(config_path),
            "sealed_approved": _file_identity(path("sealed_approved")),
            "incumbent_evaluator": _file_identity(path("incumbent_evaluator")),
            "baseline_skill": _file_identity(path("baseline_skill")),
            "mutation_parent_skill": _file_identity(path("mutation_parent_skill")),
            "strategy_history": _file_identity(path("strategy_history")),
            "recorded_corpus_manifest": _file_identity(
                _corpus_manifest_path(path("corpus_root"))
            ),
            "recorded_corpus_cases": corpus_case_identities,
            "recorded_harness_evidence": harness_evidence_identities,
            "coordinator_source": _file_identity(Path(__file__)),
            "materiality_evaluator": _materiality_evaluator_identity(),
            "anchor_sources": [_file_identity(item) for item in anchor_sources],
            "baseline_runs": _run_identities(baseline_runs),
            "mutation_signal_runs": _run_identities(mutation_runs),
        }
        input_lock = {
            "schema": "RQGMEpochInputLock.v1", **input_payload,
            "input_lock_sha256": artifact_digest(input_payload),
        }
        input_path = output_root / "epoch-input.json"
        if input_path.is_file() and _read(input_path) != input_lock:
            raise EpochError("epoch input identity drifted")
        if not input_path.is_file():
            _atomic_json(input_path, input_lock)
        stages = output_root / "stages"

        def migrate_materiality(attempt: Path) -> None:
            materialize_materiality_run_views(
                source_runs=baseline_runs, output_root=attempt / "baseline",
            )
            materialize_materiality_run_views(
                source_runs=mutation_runs, output_root=attempt / "mutation-parent",
            )

        materiality_views = _stage(
            stages, "00-materiality-views", {
                "baseline": _run_identities(baseline_runs),
                "mutation_parent": _run_identities(mutation_runs),
                "materiality_evaluator": _materiality_evaluator_identity(),
            }, migrate_materiality,
        )
        migrated_baseline_runs = sorted((materiality_views / "baseline").iterdir())
        migrated_mutation_runs = sorted((materiality_views / "mutation-parent").iterdir())

        def build_anchors(attempt: Path) -> None:
            parent = generate_pairwise_anchor_manifest(
                path("sealed_approved"), anchor_sources,
                include_hindsight_confidence_b=True,
                include_material_omission_confidence_a=True,
            )
            train, validation, split = split_evaluator_anchor_manifest(
                parent, validation_families=int(config["validation_families"]),
                seed=str(config["split_seed"]),
            )
            for name, value in (("parent.json", parent), ("train.json", train),
                                ("validation.json", validation), ("split.json", split)):
                (attempt / name).write_bytes(canonical_anchor_manifest_bytes(value) + b"\n")

        anchors = _stage(stages, "01-anchors", input_lock, build_anchors)
        train = _read(anchors / "train.json")
        validation = _read(anchors / "validation.json")
        split = _read(anchors / "split.json")
        validate_anchor_split_manifest(train, validation, split)
        incumbent = EvaluatorSpec.from_dict(
            _read(path("incumbent_evaluator")), allow_legacy_epoch1=True,
        )

        def evolve(attempt: Path) -> None:
            evolution_root = attempt / "evolution"
            result = evolve_evaluator_once(
                incumbent=incumbent, training_manifest=train,
                validation_manifest=validation, split_manifest=split, output_dir=evolution_root,
            )
            selected_path = evolution_root / "selected.json"
            selected = _read(selected_path)
            incumbent_epoch = int(_read(path("incumbent_evaluator")).get("epoch", 0))
            selected["epoch"] = incumbent_epoch + int(result["promotion"]["promoted"])
            _atomic_json(selected_path, selected)

        evaluator = _stage(
            stages, "02-evaluator",
            {"input": input_lock["input_lock_sha256"], "anchors": split["split_sha256"]},
            evolve,
        )
        evaluator_root = evaluator / "evolution"
        selected = EvaluatorSpec.from_dict(_read(evaluator_root / "selected.json"))
        challenger = EvaluatorSpec.from_dict(_read(evaluator_root / "challenger.json"))

        replay = _stage(
            stages, "03-replay",
            {"baseline": _run_identities(migrated_baseline_runs),
             "candidate": _run_identities(migrated_mutation_runs),
             "materiality_receipt": _sha(materiality_views / "receipt.json"),
             "incumbent": incumbent.sha256, "challenger": challenger.sha256},
            lambda attempt: run_replay_2x2(
                baseline_runs=migrated_baseline_runs,
                candidate_runs=migrated_mutation_runs,
                incumbent=incumbent, challenger=challenger, output_dir=attempt,
            ),
        )

        evaluator_label = "challenger" if selected.sha256 == challenger.sha256 else "incumbent"
        def materialize(attempt: Path) -> None:
            materialize_rejudged_run_views(
                source_runs=migrated_baseline_runs, replay_root=replay, skill_arm="baseline",
                evaluator_label=evaluator_label, evaluator=selected,
                output_root=attempt / "baseline",
            )
            materialize_rejudged_run_views(
                source_runs=migrated_mutation_runs, replay_root=replay, skill_arm="candidate",
                evaluator_label=evaluator_label, evaluator=selected,
                output_root=attempt / "mutation-parent",
            )

        rejudged = _stage(
            stages, "03b-rejudged-views", {
                "replay_receipt": _sha(replay / "receipt.json"),
                "selected_evaluator": selected.sha256,
            }, materialize,
        )
        effective_baseline_runs = sorted((rejudged / "baseline").iterdir())
        effective_mutation_runs = sorted((rejudged / "mutation-parent").iterdir())

        deployed = output_root / "deployed-SKILL.md"
        if not deployed.exists():
            shutil.copyfile(path("baseline_skill"), deployed)
        v_next = output_root / "v-next-SKILL.md"

        def generate(attempt: Path) -> None:
            execute_study(
                sealed_approved=path("sealed_approved"), corpus_root=path("corpus_root"),
                cache=ContentAddressedCache(path("cache")),
                repository_root=path("repository_root"), v5_skill=path("baseline_skill"),
                run_root=attempt / "runs", v6_skill=v_next, deployed_skill=deployed,
                decision_output=attempt / "decision.json",
                max_workers=int(config.get("max_workers", 8)),
                strategy_history=path("strategy_history"),
                evaluator_spec=evaluator_root / "selected.json",
                mutation_parent_skill=path("mutation_parent_skill"),
                mutation_signal_runs=effective_mutation_runs,
                development_baseline_runs=effective_baseline_runs,
            )

        generation = _stage(
            stages, "04-generation",
            {"selected_evaluator": selected.sha256, "replay": _sha(replay / "manifest.json"),
             "signals": artifact_digest(development_signals(effective_mutation_runs)),
             "rejudged_receipt": _sha(rejudged / "receipt.json"),
             "materiality_evaluator": _materiality_evaluator_identity()},
            generate,
        )
        decision = _read(generation / "decision.json")
        def verify_generation(attempt: Path) -> None:
            common = {
                "sealed_approved": path("sealed_approved"),
                "corpus_root": path("corpus_root"),
                "development_runs": effective_baseline_runs,
                "batch_manifest": generation / "runs" / "batch-mutation" / "manifest.json",
                "decision_path": generation / "decision.json",
                "v5_skill": path("baseline_skill"), "deployed_skill": deployed,
                "v6_skill": v_next, "mutation_parent_skill": path("mutation_parent_skill"),
                "mutation_signal_runs": effective_mutation_runs,
            }
            if decision.get("development_selected_candidate") is None:
                result = verify_development_rejection(**common)
            else:
                if "public_selection" not in config or "harness_evidence_root" not in config:
                    raise EpochError("full generation verification inputs are missing")
                run_root = generation / "runs"
                result = verify_completed_pilot(
                    **common,
                    public_selection=path("public_selection"),
                    harness_evidence_root=path("harness_evidence_root"),
                    baseline_validation_runs=sorted(run_root.glob("validation/*/v5")),
                    candidate_validation_runs=sorted(run_root.glob("validation/*/candidate")),
                    holdout_runs=sorted(run_root.glob("holdout/*/selected")),
                    candidate_skill=run_root / "batch-mutation" / "selected-candidate-SKILL.md",
                )
            _atomic_json(attempt / "verification.json", result)

        generation_verifier = _stage(
            stages, "05-generation-verifier", {
                "decision": _sha(generation / "decision.json"),
            "generation_receipt": _sha(generation / "receipt.json"),
            "strategy_history": _sha(path("strategy_history")),
            "decision_review_bundle_sha256": _decision_review_bundle_digest(generation),
            },
            verify_generation,
        )

        def verify_evaluator(attempt: Path) -> None:
            result = verify_evaluator_epoch(
                validation_manifest=validation, training_manifest=train, split_manifest=split,
                evolution_dir=evaluator_root, run_root=generation / "runs",
                decision_path=generation / "decision.json",
            )
            _atomic_json(attempt / "verification.json", result)

        evaluator_verifier = _stage(
            stages, "06-evaluator-verifier", {
                "decision": _sha(generation / "decision.json"),
                "generation_receipt": _sha(generation / "receipt.json"),
                "evaluator_receipt": _sha(evaluator / "receipt.json"),
                "anchor_receipt": _sha(anchors / "receipt.json"),
                "decision_review_bundle_sha256": _decision_review_bundle_digest(generation),
            },
            verify_evaluator,
        )
        generation_check = _read(generation_verifier / "verification.json")
        evaluator_check = _read(evaluator_verifier / "verification.json")
        if generation_check.get("verified") is not True or evaluator_check.get("verified") is not True:
            raise EpochError("epoch verifiers did not both pass")

        def commit_promotion(attempt: Path) -> None:
            promoted = False
            if generation_check.get("promotion_eligible") is True:
                candidate_skill = (
                    generation / "runs" / "batch-mutation" / "selected-candidate-SKILL.md"
                )
                _write_verified_promotion(candidate_skill.read_bytes(), v_next, deployed)
                promoted = True
            _atomic_json(attempt / "promotion.json", {
                "schema": "RQGMEpochPromotionCommit.v1", "promoted": promoted,
                "deployed_sha256": _sha(deployed),
                "v_next_sha256": _sha(v_next) if v_next.exists() else None,
            })

        promotion = _stage(
            stages, "07-promotion-commit", {
                "generation_verifier_receipt": _sha(generation_verifier / "receipt.json"),
                "evaluator_verifier_receipt": _sha(evaluator_verifier / "receipt.json"),
            }, commit_promotion,
        )
        promotion_result = _read(promotion / "promotion.json")
        stage_receipts = {
            stage.parent.name: {
                "attempt": stage.name,
                "receipt_sha256": _sha(stage / "receipt.json"),
            }
            for stage in (
                materiality_views, anchors, evaluator, replay, rejudged, generation,
                generation_verifier, evaluator_verifier, promotion,
            )
        }
        payload = {
            "epoch": int(config["epoch"]),
            "input_lock_sha256": input_lock["input_lock_sha256"],
            "anchor_split_sha256": split["split_sha256"],
            "selected_evaluator_sha256": selected.sha256,
            "evaluator_promoted": bool(_read(evaluator_root / "promotion.json")["promoted"]),
            "replay_manifest_sha256": _sha(replay / "manifest.json"),
            "generation_decision_sha256": _sha(generation / "decision.json"),
            "materiality_evaluator": _materiality_evaluator_identity(),
            "decision_review_bundle_sha256": _decision_review_bundle_digest(generation),
            "generation_terminal_branch": (
                "development-rejection" if decision.get("development_selected_candidate") is None
                else "validation-or-holdout"
            ),
            "generation_verified": True, "evaluator_verified": True,
            "promoted": promotion_result["promoted"],
            "deployed_shadow_sha256": _sha(deployed),
            "dependency_sha256s": {
                "config": _sha(config_path),
                "sealed_approved": _sha(path("sealed_approved")),
                "recorded_corpus_manifest": _sha(
                    _corpus_manifest_path(path("corpus_root"))
                ),
                "baseline_skill": _sha(path("baseline_skill")),
                "mutation_parent_skill": _sha(path("mutation_parent_skill")),
                "strategy_history": _sha(path("strategy_history")),
            },
            "stage_receipts": stage_receipts,
        }
        manifest = {"schema": "RQGMCoEvolutionEpoch.v1", **payload,
                    "epoch_sha256": artifact_digest(payload)}
        manifest_path = output_root / "epoch-manifest.json"
        if manifest_path.is_file() and _read(manifest_path) != manifest:
            raise EpochError("completed epoch manifest drifted")
        if not manifest_path.is_file():
            _atomic_json(manifest_path, manifest)
        return manifest
