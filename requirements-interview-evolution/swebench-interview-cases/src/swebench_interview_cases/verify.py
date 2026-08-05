"""Requirement-level completion verifier for the full 15-case pilot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import (
    DATASET_PARQUET_SHA256, DATASET_REVISION, HARNESS_REVISION, MODEL_ID,
    MODEL_REASONING_EFFORT,
)
from .schemas import artifact_digest, validate_case_pair
from .batch import _apply_edit, _validate_strategy_portfolio, development_signals
from .implementer import (
    DECISION_MATERIALITY_RUBRIC_SHA256,
    DECISION_MATERIALITY_SCHEMA_VERSION,
    read_decisions,
    validate_decision_materiality,
)
from .metrics import development_metrics, holdout_metrics, validation_metrics
from .execute import _evaluate_strategies, _paired_development_non_regression
from .review import DecisionDisposition, ReviewDecision, unanimous_disposition
from .study import (
    development_candidate_is_eligible,
    development_non_regression_rank,
    select_validation_winner,
)


def _verify_strategy_portfolio(mutation: dict[str, Any]) -> None:
    try:
        _validate_strategy_portfolio(
            mutation.get("portfolio", {}).get("strategies", [])
        )
    except RuntimeError as error:
        raise VerificationError("batch mutation principle portfolio failed") from error
from .selection import holdout_alias
from .study import passes_strict_holdout_gate


class VerificationError(RuntimeError):
    pass


def _read(path: Path) -> Any:
    if not path.is_file():
        raise VerificationError(f"required artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_run_artifacts(run: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifact_sha256")
    if not isinstance(artifacts, dict) or not artifacts:
        raise VerificationError("imported run artifact identity is missing")
    for name, digest in artifacts.items():
        path = run / name
        if not path.is_file() or _sha(path) != digest:
            raise VerificationError("imported run artifact digest is missing or drifted")


def _verify_implementation(run: Path, case: dict[str, Any]) -> None:
    contract = _read(run / "contract.json")
    implementation = run / "implementation"
    manifest = _read(implementation / "implementation-manifest.json")
    decisions = read_decisions(implementation / "decision.jsonl")
    materiality = _read(implementation / "decision-materiality.json")
    validate_decision_materiality(materiality, decision_count=len(decisions))
    material_count = sum(item["material"] for item in materiality["reviews"])
    if (
        manifest.get("schema") != "FreshImplementationRun.v1"
        or manifest.get("base_commit") != case["base_commit"]
        or manifest.get("contract_sha256") != hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        or manifest.get("decision_count") != len(decisions)
        or manifest.get("material_decision_count") != material_count
        or manifest.get("materiality_rubric_sha256") != DECISION_MATERIALITY_RUBRIC_SHA256
        or manifest.get("materiality_schema_version") != DECISION_MATERIALITY_SCHEMA_VERSION
        or manifest.get("materiality_reviewer_model") != MODEL_ID
        or manifest.get("materiality_reviewer_reasoning_effort") != MODEL_REASONING_EFFORT
        or manifest.get("decision_review_sha256") != _sha(
            implementation / "decision-materiality.json"
        )
        or manifest.get("fresh_context") is not True
        or manifest.get("sealed_inputs_exposed") is not False
    ):
        raise VerificationError("fresh implementation identity or decisions drifted")
    for name, digest in manifest.get("artifact_sha256", {}).items():
        path = implementation / name
        if not path.is_file() or _sha(path) != digest:
            raise VerificationError("fresh implementation artifact drifted")


def _write_verified_promotion(content: bytes, v6_skill: Path, deployed_skill: Path) -> None:
    original = deployed_skill.read_bytes()
    v6_skill.parent.mkdir(parents=True, exist_ok=True)
    temporary_paths: list[Path] = []
    try:
        for target in (v6_skill, deployed_skill):
            descriptor, raw = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            temporary = Path(raw)
            temporary_paths.append(temporary)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary_paths[0], v6_skill)
        os.replace(temporary_paths[1], deployed_skill)
    except Exception:
        v6_skill.unlink(missing_ok=True)
        deployed_skill.write_bytes(original)
        raise
    finally:
        for path in temporary_paths:
            path.unlink(missing_ok=True)


def verify_completed_pilot(
    *, public_selection: Path, sealed_approved: Path, corpus_root: Path,
    harness_evidence_root: Path, development_runs: list[Path], batch_manifest: Path,
    baseline_validation_runs: list[Path], candidate_validation_runs: list[Path],
    holdout_runs: list[Path], decision_path: Path, v5_skill: Path,
    candidate_skill: Path, v6_skill: Path, deployed_skill: Path,
    mutation_parent_skill: Path | None = None,
    mutation_signal_runs: list[Path] | None = None,
) -> dict[str, Any]:
    selection = _read(public_selection)
    if selection["dataset"]["revision"] != DATASET_REVISION or selection["dataset"]["parquet_sha256"] != DATASET_PARQUET_SHA256:
        raise VerificationError("dataset pin or parquet digest drifted")
    if selection["quotas"] != {"development": 8, "holdout": 4, "validation": 3} or selection["actual_repository_families"] < 6:
        raise VerificationError("frozen selection quotas or diversity are invalid")
    if any(item["instance_id"] is not None or item["repository_family"] is not None for item in selection["cases"] if item["partition"] == "holdout"):
        raise VerificationError("public selection reveals holdout identity")
    sealed = _read(sealed_approved)
    public_manifest = _read(corpus_root / "pilot-manifest.json")
    license_policy = _read(corpus_root / "license-policy.json")
    if license_policy["raw_dataset_and_repository_redistribution"] != "forbidden" or license_policy["dataset_license_declaration"] != "not present in pinned SWE-bench Verified dataset card":
        raise VerificationError("license and redistribution limitation is missing")
    if sealed["public_manifest_sha256"] != artifact_digest(public_manifest):
        raise VerificationError("sealed approved manifest is not bound to public manifest")
    cases = sealed["cases"]
    counts = {name: sum(item["partition"] == name for item in cases) for name in ("development", "validation", "holdout")}
    if counts != {"development": 8, "validation": 3, "holdout": 4} or len({item["repository_family"] for item in cases}) < 6:
        raise VerificationError("approved corpus quotas or family diversity are invalid")
    family_partitions: dict[str, set[str]] = {}
    for item in cases:
        family_partitions.setdefault(item["repository_family"], set()).add(item["partition"])
        if item["partition"] == "holdout" and item["alias"] != holdout_alias(item["instance_id"]):
            raise VerificationError("holdout alias is not plain SHA-256 pseudonymization")
        case_dir = (
            sealed_approved.parent / "holdout-cases" / item["alias"]
            if item["partition"] == "holdout"
            else corpus_root / "cases" / item["alias"]
        )
        required = {"case.json", "sealed-source.json", "review-a.json", "review-b.json", "audit.json", "run-manifest.json"}
        if {path.name for path in case_dir.iterdir() if path.is_file()} < required:
            raise VerificationError(f"case layout is incomplete: {item['alias']}")
        public = _read(case_dir / "case.json")
        source = _read(case_dir / "sealed-source.json")
        validate_case_pair(public, source)
        if source["review_state"] != {"status": "approved", "dispositions_complete": True} or not _read(case_dir / "audit.json")["approved"]:
            raise VerificationError("unapproved case entered corpus")
        decisions = {decision["id"] for decision in source["material_decisions"]}
        classified_expected = {
            item["id"]: "hindsight_observation" for item in source["hindsight_observations"]
        } | {
            item["id"]: "implementation_incidental" for item in source["implementation_incidentals"]
        }
        dispositions: dict[str, list[DecisionDisposition]] = {decision: [] for decision in decisions}
        for reviewer_id in ("a", "b"):
            review = _read(case_dir / f"review-{reviewer_id}.json")
            seen: set[str] = set()
            for value in review["dispositions"]:
                decision_id = value["decision_id"]
                if decision_id not in dispositions or decision_id in seen:
                    raise VerificationError("review disposition identity is invalid")
                seen.add(decision_id)
                dispositions[decision_id].append(DecisionDisposition(
                    decision_id, reviewer_id, ReviewDecision(value["material"]),
                    ReviewDecision(value["issue_time_knowable"]),
                    ReviewDecision(value["implementation_independent"]),
                    ReviewDecision(value["separated_from_repository_fact"]),
                    ReviewDecision(value["leakage_free"]),
                ))
            if seen != decisions or not review["semantic_leakage_free"] or not review["alternative_implementation_satisfied"]:
                raise VerificationError("reviewer did not independently approve every decision")
            classified = review["classified_items"]
            if {item["item_id"]: item["classification"] for item in classified} != classified_expected:
                raise VerificationError("reviewer did not disposition every observation/incidental")
            if any(not (item["provenance_supported"] and item["classification_correct"] and item["leakage_free"]) for item in classified):
                raise VerificationError("reviewer did not approve observation/incidental provenance and classification")
        if not all(unanimous_disposition(decision, dispositions[decision]).approved for decision in decisions):
            raise VerificationError("case lacks unanimous two-reviewer approval")
        harness = _read(harness_evidence_root / item["instance_id"] / "harness-evidence.json")
        if harness["harness_revision"] != HARNESS_REVISION:
            raise VerificationError("harness revision drifted")
        for kind in ("baseline", "gold"):
            if not harness[kind]["image_digests"]:
                raise VerificationError("harness evidence lacks immutable image digest")
            for relative, expected_digest in harness[kind]["report_sha256"].items():
                report = harness_evidence_root.parent / relative
                if not report.is_file() or _sha(report) != expected_digest:
                    raise VerificationError("official harness report evidence is missing or drifted")
        expected_f2p = set(harness["expected"]["fail_to_pass"])
        expected_p2p = set(harness["expected"]["pass_to_pass"])
        baseline_status = harness["baseline"]["tests_status"]
        gold_status = harness["gold"]["tests_status"]
        if not (
            set(baseline_status["FAIL_TO_PASS"]["failure"]) == expected_f2p
            and not baseline_status["FAIL_TO_PASS"]["success"]
            and set(baseline_status["PASS_TO_PASS"]["success"]) == expected_p2p
            and not baseline_status["PASS_TO_PASS"]["failure"]
            and set(gold_status["FAIL_TO_PASS"]["success"]) == expected_f2p
            and not gold_status["FAIL_TO_PASS"]["failure"]
            and set(gold_status["PASS_TO_PASS"]["success"]) == expected_p2p
            and not gold_status["PASS_TO_PASS"]["failure"]
        ):
            raise VerificationError("official harness test inventory/dispositions are invalid")
        prep = _read(case_dir / "run-manifest.json")
        if prep["harness_evidence_sha256"] != artifact_digest(harness):
            raise VerificationError("case preparation is not bound to harness evidence")
    if any(len(partitions) != 1 for partitions in family_partitions.values()):
        raise VerificationError("repository family crosses partitions")
    for name, expected in (("development", 8), ("validation", 3), ("holdout", 4)):
        index = _read(corpus_root / name / "index.json")
        if index["partition"] != name or len(index["cases"]) != expected:
            raise VerificationError("partition index is incomplete")
        expected_digests = {item["alias"]: item["case_digest"] for item in cases if item["partition"] == name}
        if {item["alias"]: item["case_digest"] for item in index["cases"]} != expected_digests:
            raise VerificationError("partition index case digests drifted")
    v5_digest, candidate_digest = _sha(v5_skill), _sha(candidate_skill)
    expected_aliases = {
        partition: {item["alias"] for item in cases if item["partition"] == partition}
        for partition in ("development", "validation", "holdout")
    }
    case_by_alias = {item["alias"]: item for item in cases}
    if len(development_runs) != 8:
        raise VerificationError("exactly eight development runs are required")
    for run in development_runs:
        manifest = _read(run / "run-manifest.json")
        if manifest["partition"] != "development" or manifest["skill_sha256"] != v5_digest or manifest["model"] != MODEL_ID or manifest["per_case_mutator_invoked"]:
            raise VerificationError("development run invariant failed")
        _verify_run_artifacts(run, manifest)
        case = case_by_alias[manifest["alias"]]
        case_dir = corpus_root / "cases" / manifest["alias"]
        if (
            artifact_digest(_read(case_dir / "case.json")) != manifest.get("case_sha256")
            or artifact_digest(_read(case_dir / "sealed-source.json"))
            != manifest.get("sealed_source_sha256")
        ):
            raise VerificationError("development run corpus identity failed")
        _verify_implementation(run, case)
    if {_read(run / "run-manifest.json")["alias"] for run in development_runs} != expected_aliases["development"]:
        raise VerificationError("development runs do not match approved cases")
    if (mutation_parent_skill is None) != (mutation_signal_runs is None):
        raise VerificationError("mutation lineage parent and signal runs must be supplied together")
    mutation_parent = mutation_parent_skill or v5_skill
    mutation_runs = mutation_signal_runs or development_runs
    mutation_parent_digest = _sha(mutation_parent)
    if len(mutation_runs) != 8:
        raise VerificationError("mutation lineage requires eight development runs")
    baseline_evaluators = {
        _read(run / "run-manifest.json").get("evaluator_sha256") for run in development_runs
    }
    if len(baseline_evaluators) != 1 or None in baseline_evaluators:
        raise VerificationError("development evaluator identity drifted")
    mutation_aliases: set[str] = set()
    for run in mutation_runs:
        manifest = _read(run / "run-manifest.json")
        alias = str(manifest.get("alias"))
        mutation_aliases.add(alias)
        case_dir = corpus_root / "cases" / alias
        if (
            manifest.get("partition") != "development"
            or manifest.get("skill_sha256") != mutation_parent_digest
            or manifest.get("evaluator_sha256") not in baseline_evaluators
            or manifest.get("per_case_mutator_invoked")
            or artifact_digest(_read(case_dir / "case.json")) != manifest.get("case_sha256")
            or artifact_digest(_read(case_dir / "sealed-source.json"))
            != manifest.get("sealed_source_sha256")
        ):
            raise VerificationError("mutation lineage identity failed")
        _verify_run_artifacts(run, manifest)
    if mutation_aliases != expected_aliases["development"]:
        raise VerificationError("mutation lineage cases drifted")
    batch = _read(batch_manifest)
    signals = development_signals(mutation_runs)
    signal_ids = {item["signal_id"] for item in signals}
    mutation = _read(batch_manifest.parent / "mutation.json")
    strategies = mutation.get("candidate_edits", [])
    if (
        batch.get("schema") != "DevelopmentSignalMutation.v6"
        or batch["development_cases"] != 8
        or batch["mutation_calls"] != (batch["candidate_count"] + 1 if signals else 0)
        or batch["signal_count"] != len(signals)
        or batch["source_partitions"] != ["development"]
        or batch.get("baseline_sha256") != mutation_parent_digest
        or candidate_digest not in batch["candidate_sha256s"]
        or len(strategies) != batch["candidate_count"]
    ):
        raise VerificationError("batch mutation invariant failed")
    _verify_strategy_portfolio(mutation)
    for strategy in strategies:
        reviewed_ids = [item["signal_id"] for item in strategy["signal_reviews"]]
        if len(reviewed_ids) != len(set(reviewed_ids)) or set(reviewed_ids) != signal_ids:
            raise VerificationError("batch mutation review coverage failed")
    candidate_paths = sorted(batch_manifest.parent.glob("candidate-*-SKILL.md"))
    if [_sha(path) for path in candidate_paths] != batch.get("candidate_sha256s"):
        raise VerificationError("batch candidate identity failed")
    for path, edit in zip(candidate_paths, strategies):
        if path.read_text(encoding="utf-8") != _apply_edit(
            mutation_parent.read_text(encoding="utf-8"), edit,
        ):
            raise VerificationError("batch candidate is not the declared lineage edit")
    selection = _read(batch_manifest.parent / "development-selection.json")
    selected_index = selection["selected_candidate"] - 1
    if (
        selection.get("schema") != "DevelopmentCandidateSelection.v1"
        or selected_index < 0
        or selected_index >= batch["candidate_count"]
        or batch["candidate_sha256s"][selected_index] != candidate_digest
        or selection.get("source_partitions") != ["development"]
    ):
        raise VerificationError("development candidate selection identity failed")
    run_root = batch_manifest.parent.parent
    candidate_groups = [
        [run_root / relative for relative in group]
        for group in selection["candidate_runs"]
    ]
    recomputed_development = [development_metrics(group) for group in candidate_groups]
    recomputed_strategy_evaluations = _evaluate_strategies(
        development_runs, candidate_groups, strategies,
    )
    if selection["baseline"] != development_metrics(development_runs).__dict__ or selection[
        "candidates"
    ] != [item.__dict__ for item in recomputed_development] or selection.get(
        "strategy_evaluations"
    ) != recomputed_strategy_evaluations:
        raise VerificationError("development candidate metrics drifted")
    recomputed_eligible = [
        index + 1 for index, group in enumerate(candidate_groups)
        if development_candidate_is_eligible(
            development_metrics(development_runs), recomputed_development[index]
        ) and _paired_development_non_regression(development_runs, group)
    ]
    recomputed_selected = max(
        (index - 1 for index in recomputed_eligible),
        key=lambda index: (development_non_regression_rank(recomputed_development[index]), -index),
    ) + 1
    if selection["eligible_candidates"] != recomputed_eligible or selection["selected_candidate"] != recomputed_selected:
        raise VerificationError("development non-regression selection drifted")
    outcomes = _read(batch_manifest.parent / "strategy-outcomes.json")
    if outcomes.get("evaluations") != [
        {**item, "eligible": item["candidate"] in recomputed_eligible}
        for item in recomputed_strategy_evaluations
    ]:
        raise VerificationError("mutation strategy outcomes drifted")
    mutator_audit = batch_manifest.parent / "mutation-input-audit.json"
    if not mutator_audit.is_file() or _sha(mutator_audit) != batch["mutation_input_audit_sha256"]:
        raise VerificationError("batch mutator input audit is missing or drifted")
    for runs, expected_digest in ((baseline_validation_runs, v5_digest), (candidate_validation_runs, candidate_digest)):
        if len(runs) != 3:
            raise VerificationError("both validation arms require three runs")
        for run in runs:
            manifest = _read(run / "run-manifest.json")
            if manifest["partition"] != "validation" or manifest["skill_sha256"] != expected_digest or manifest["model"] != MODEL_ID or manifest["per_case_mutator_invoked"]:
                raise VerificationError("validation run invariant failed")
            _verify_run_artifacts(run, manifest)
            case = case_by_alias[manifest["alias"]]
            case_dir = corpus_root / "cases" / manifest["alias"]
            contract = _read(run / "contract.json")
            if contract["implementation_ready"]:
                _verify_implementation(run, case)
        if {_read(run / "run-manifest.json")["alias"] for run in runs} != expected_aliases["validation"]:
            raise VerificationError("validation arm does not match approved cases")
    decision = _read(decision_path)
    recomputed_baseline = validation_metrics(baseline_validation_runs)
    recomputed_candidate = validation_metrics(candidate_validation_runs)
    recomputed_winner = select_validation_winner(recomputed_baseline, recomputed_candidate)
    if decision["validation_baseline"] != recomputed_baseline.__dict__ or decision["validation_candidate"] != recomputed_candidate.__dict__ or decision["validation_winner"] != recomputed_winner:
        raise VerificationError("validation decision metrics or absolute-zero result were not recomputed faithfully")
    if recomputed_winner != "candidate":
        if holdout_runs or decision.get("holdout_opened") is not False or decision.get("holdout") is not None:
            raise VerificationError("failed validation must not open holdout")
        if decision.get("promotion_eligible") is not False or decision.get("promoted") is not False:
            raise VerificationError("failed validation cannot be promoted")
        if _sha(deployed_skill) != v5_digest or v6_skill.exists():
            raise VerificationError("failed generation changed deployed or v6 skill")
        return {
            "schema": "SWEbenchPilotCompletionVerification.v2", "verified": True,
            "approved_cases": 15, "repository_families": len(family_partitions),
            "development_runs": 8, "validation_runs": 6, "holdout_runs": 0,
            "development_signals": len(signals),
            "mutation_performed": batch["mutation_performed"],
            "candidate_equals_v5": candidate_digest == v5_digest,
            "promotion_eligible": False, "promoted": False,
            "decision_sha256": artifact_digest(decision),
        }
    selected_digest = decision["selected_skill_sha256"]
    expected_selected = candidate_digest if recomputed_winner == "candidate" else v5_digest
    if selected_digest != expected_selected:
        raise VerificationError("selected skill digest is not bound to the recomputed validation winner")
    if len(holdout_runs) != 4:
        raise VerificationError("holdout requires exactly four runs")
    for run in holdout_runs:
        manifest = _read(run / "run-manifest.json")
        if manifest["partition"] != "holdout" or manifest["skill_sha256"] != selected_digest or manifest["model"] != MODEL_ID or manifest["per_case_mutator_invoked"]:
            raise VerificationError("holdout isolation invariant failed")
        _verify_run_artifacts(run, manifest)
        case = case_by_alias[manifest["alias"]]
        case_dir = sealed_approved.parent / "holdout-cases" / manifest["alias"]
        _verify_implementation(run, case)
    if {_read(run / "run-manifest.json")["alias"] for run in holdout_runs} != expected_aliases["holdout"]:
        raise VerificationError("holdout runs do not match approved cases")
    recomputed_holdout = holdout_metrics(holdout_runs)
    if decision["holdout"] != recomputed_holdout.__dict__:
        raise VerificationError("holdout metrics were not recomputed from sealed runs")
    strict_pass = passes_strict_holdout_gate(recomputed_holdout)
    if decision.get("promotion_eligible") != strict_pass or decision.get("promoted") is not False:
        raise VerificationError("pre-promotion decision disagrees with strict holdout gate")
    if _sha(deployed_skill) != v5_digest or v6_skill.exists():
        raise VerificationError("full verification must run before any v6/deployed mutation")
    return {
        "schema": "SWEbenchPilotCompletionVerification.v1", "verified": True,
        "approved_cases": 15, "repository_families": len(family_partitions),
        "development_runs": 8, "validation_runs": 6, "holdout_runs": 4,
        "development_signals": len(signals),
        "skill_gap_signals": batch["skill_gap_counts"][selected_index],
        "mutation_performed": batch["mutation_performed"],
        "candidate_equals_v5": candidate_digest == v5_digest,
        "promotion_eligible": strict_pass, "promoted": False,
        "decision_sha256": artifact_digest(decision),
    }


def verify_and_promote(**kwargs: Any) -> dict[str, Any]:
    result = verify_completed_pilot(**kwargs)
    decision = _read(kwargs["decision_path"])
    selected_skill = (
        kwargs["candidate_skill"]
        if decision["validation_winner"] == "candidate"
        else kwargs["v5_skill"]
    )
    promoted = False
    if result["promotion_eligible"]:
        _write_verified_promotion(
            selected_skill.read_bytes(), kwargs["v6_skill"], kwargs["deployed_skill"]
        )
        promoted = True
        if _sha(kwargs["v6_skill"]) != _sha(kwargs["deployed_skill"]):
            raise VerificationError("atomic post-verification promotion failed")
    elif _sha(kwargs["deployed_skill"]) != _sha(kwargs["v5_skill"]):
        raise VerificationError("failed gate changed deployed v5")
    result["promoted"] = promoted
    result["deployed_sha256"] = _sha(kwargs["deployed_skill"])
    result["v6_sha256"] = _sha(kwargs["v6_skill"]) if promoted else None
    return result


def verify_development_rejection(
    *, sealed_approved: Path, corpus_root: Path, development_runs: list[Path], batch_manifest: Path,
    decision_path: Path, v5_skill: Path, deployed_skill: Path, v6_skill: Path,
    mutation_parent_skill: Path | None = None,
    mutation_signal_runs: list[Path] | None = None,
) -> dict[str, Any]:
    """Verify a generation that correctly stopped before validation."""

    approved = _read(sealed_approved)["cases"]
    cases = {item["alias"]: item for item in approved if item["partition"] == "development"}
    if len(cases) != 8 or len(development_runs) != 8:
        raise VerificationError("development rejection requires eight approved baseline runs")
    v5_digest = _sha(v5_skill)
    evaluator_digests: set[str] = set()
    for run in development_runs:
        manifest = _read(run / "run-manifest.json")
        alias = str(manifest.get("alias"))
        case_dir = corpus_root / "cases" / alias
        if (
            manifest["partition"] != "development"
            or manifest["skill_sha256"] != v5_digest
            or manifest["alias"] not in cases
            or manifest["per_case_mutator_invoked"]
            or artifact_digest(_read(case_dir / "case.json")) != manifest.get("case_sha256")
            or artifact_digest(_read(case_dir / "sealed-source.json"))
            != manifest.get("sealed_source_sha256")
        ):
            raise VerificationError("development baseline identity failed")
        evaluator_digests.add(str(manifest.get("evaluator_sha256", "")))
        _verify_run_artifacts(run, manifest)
        _verify_implementation(run, cases[manifest["alias"]])
    if {_read(run / "run-manifest.json")["alias"] for run in development_runs} != set(cases):
        raise VerificationError("development baseline cases drifted")
    if len(evaluator_digests) != 1 or not next(iter(evaluator_digests)):
        raise VerificationError("development baseline evaluator identity drifted")

    if (mutation_parent_skill is None) != (mutation_signal_runs is None):
        raise VerificationError("mutation lineage parent and signal runs must be supplied together")
    mutation_parent = mutation_parent_skill or v5_skill
    mutation_runs = mutation_signal_runs or development_runs
    mutation_parent_digest = _sha(mutation_parent)
    if len(mutation_runs) != 8:
        raise VerificationError("mutation lineage requires eight development runs")
    for run in mutation_runs:
        manifest = _read(run / "run-manifest.json")
        alias = str(manifest.get("alias"))
        case_dir = corpus_root / "cases" / alias
        if (
            manifest["partition"] != "development"
            or manifest["skill_sha256"] != mutation_parent_digest
            or manifest["alias"] not in cases
            or manifest["per_case_mutator_invoked"]
            or manifest.get("evaluator_sha256") not in evaluator_digests
            or artifact_digest(_read(case_dir / "case.json")) != manifest.get("case_sha256")
            or artifact_digest(_read(case_dir / "sealed-source.json"))
            != manifest.get("sealed_source_sha256")
        ):
            raise VerificationError("mutation lineage identity failed")
        _verify_run_artifacts(run, manifest)
    if {_read(run / "run-manifest.json")["alias"] for run in mutation_runs} != set(cases):
        raise VerificationError("mutation lineage cases drifted")

    batch = _read(batch_manifest)
    mutation = _read(batch_manifest.parent / "mutation.json")
    signals = development_signals(mutation_runs)
    signal_ids = {item["signal_id"] for item in signals}
    candidate_paths = sorted(batch_manifest.parent.glob("candidate-*-SKILL.md"))
    candidate_digests = [_sha(path) for path in candidate_paths]
    strategies = mutation.get("candidate_edits", [])
    if (
        batch.get("schema") != "DevelopmentSignalMutation.v6"
        or batch.get("baseline_sha256") != mutation_parent_digest
        or batch.get("candidate_count") != 3
        or batch.get("candidate_sha256s") != candidate_digests
        or batch.get("signal_count") != len(signals)
        or batch.get("source_partitions") != ["development"]
        or batch.get("mutation_calls") != 4
        or len(strategies) != 3
    ):
        raise VerificationError("development mutation pool invariant failed")
    _verify_strategy_portfolio(mutation)
    for strategy in strategies:
        reviewed = [item["signal_id"] for item in strategy["signal_reviews"]]
        if len(reviewed) != len(set(reviewed)) or set(reviewed) != signal_ids:
            raise VerificationError("mutation strategy did not review every development signal")
    for path, edit in zip(candidate_paths, strategies):
        if path.read_text(encoding="utf-8") != _apply_edit(
            mutation_parent.read_text(encoding="utf-8"), edit,
        ):
            raise VerificationError("candidate does not match its bounded strategy edit")

    selection = _read(batch_manifest.parent / "development-selection.json")
    run_root = batch_manifest.parent.parent
    groups = [[run_root / relative for relative in group] for group in selection["candidate_runs"]]
    if len(groups) != 3 or any(len(group) != 8 for group in groups):
        raise VerificationError("candidate development run matrix is not 3 by 8")
    for index, group in enumerate(groups):
        for run in group:
            manifest = _read(run / "run-manifest.json")
            if (
                manifest["partition"] != "development"
                or manifest["skill_sha256"] != candidate_digests[index]
                or manifest["alias"] not in cases
                or manifest["per_case_mutator_invoked"]
            ):
                raise VerificationError("candidate development identity failed")
            _verify_run_artifacts(run, manifest)
            if _read(run / "contract.json")["implementation_ready"]:
                _verify_implementation(run, cases[manifest["alias"]])
    baseline_metrics = development_metrics(development_runs)
    candidate_metrics = [development_metrics(group) for group in groups]
    recomputed_strategy_evaluations = _evaluate_strategies(
        development_runs, groups, strategies,
    )
    eligible = [
        index + 1 for index, group in enumerate(groups)
        if development_candidate_is_eligible(baseline_metrics, candidate_metrics[index])
        and _paired_development_non_regression(development_runs, group)
    ]
    if (
        selection.get("selected_candidate") is not None
        or selection.get("eligible_candidates") != eligible
        or eligible
        or selection.get("baseline") != baseline_metrics.__dict__
        or selection.get("candidates") != [item.__dict__ for item in candidate_metrics]
        or selection.get("source_partitions") != ["development"]
        or selection.get("strategy_evaluations") != recomputed_strategy_evaluations
    ):
        raise VerificationError("development rejection was not recomputed faithfully")
    outcomes = _read(batch_manifest.parent / "strategy-outcomes.json")
    expected_outcomes = [
        {**item, "eligible": item["candidate"] in eligible}
        for item in recomputed_strategy_evaluations
    ]
    if (
        outcomes.get("schema") not in {"MutationStrategyOutcomes.v1", "MutationStrategyOutcomes.v2"}
        or outcomes.get("source_partitions") != ["development"]
        or outcomes.get("evaluations") != expected_outcomes
    ):
        raise VerificationError("mutation strategy outcomes drifted")

    decision = _read(decision_path)
    if (
        decision.get("development_selected_candidate") is not None
        or decision.get("development_baseline") != baseline_metrics.__dict__
        or decision.get("development_candidates") != [item.__dict__ for item in candidate_metrics]
        or decision.get("validation_opened") is not False
        or decision.get("validation_winner") is not None
        or decision.get("holdout_opened") is not False
        or decision.get("holdout") is not None
        or decision.get("promotion_eligible") is not False
        or decision.get("promoted") is not False
        or decision.get("mutation_parent_sha256") != mutation_parent_digest
    ):
        raise VerificationError("development rejection decision drifted")
    if list((run_root / "validation").glob("**/run-manifest.json")):
        raise VerificationError("validation was opened after development rejection")
    if list((run_root / "holdout").glob("**/run-manifest.json")):
        raise VerificationError("holdout was opened after development rejection")
    if _sha(deployed_skill) != v5_digest or v6_skill.exists():
        raise VerificationError("development rejection changed the deployed generation")
    return {
        "schema": "DevelopmentRejectionVerification.v1",
        "verified": True,
        "development_runs": 8,
        "candidate_count": 3,
        "candidate_development_runs": 24,
        "development_signals": len(signals),
        "mutation_parent_sha256": mutation_parent_digest,
        "eligible_candidates": [],
        "strategy_outcomes_verified": True,
        "validation_opened": False,
        "holdout_opened": False,
        "deployed_sha256": v5_digest,
        "decision_sha256": artifact_digest(decision),
    }
