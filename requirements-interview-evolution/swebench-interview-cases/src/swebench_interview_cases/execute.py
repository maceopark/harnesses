"""Single-owner execution of development, validation, holdout, and promotion."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TypeVar

from .batch import (
    _apply_edit, _validate_strategy_portfolio, batch_mutate,
    development_signals,
)
from .cache import ContentAddressedCache
from .finalize import finalize_study
from .implementer import completed_implementation_matches, run_fresh_implementation
from .imported_native import DEFAULT_EVALUATOR_RUBRIC, run_imported_case
from .metrics import development_metrics, validation_metrics
from .repository import prepare_checkout
from .study import (
    development_candidate_is_eligible,
    development_non_regression_rank,
    select_validation_winner,
)
from .schemas import artifact_digest
from .evaluator_evolution import EvaluatorSpec


T = TypeVar("T")
R = TypeVar("R")


def _run_parallel(
    items: list[T], operation: Callable[[T], R], *, max_workers: int | None,
) -> list[R]:
    """Run one study phase concurrently while preserving its declared order."""

    if not items:
        return []
    workers = len(items) if max_workers is None else min(max_workers, len(items))
    if workers < 1:
        raise ValueError("max_workers must be at least 1")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(operation, items))


def _development_case_outcome(run_dir: Path) -> tuple[int, ...]:
    """Return ordered badness fields for paired development non-regression."""

    judge = json.loads((run_dir / "judge.json").read_text(encoding="utf-8"))
    audit = json.loads((run_dir / "runtime-audit.json").read_text(encoding="utf-8"))
    review = json.loads((run_dir / "blind-review.json").read_text(encoding="utf-8"))
    adjudication = json.loads((run_dir / "adjudication.json").read_text(encoding="utf-8"))
    approved_ids = {
        item["finding_id"] for item in adjudication["verdicts"] if item["approved"]
    }
    approved = [item for item in review["findings"] if item["id"] in approved_ids]
    implementation_path = run_dir / "implementation" / "implementation-manifest.json"
    material_decision_count = (
        (lambda value: value.get("material_decision_count", value["decision_count"]))(
            json.loads(implementation_path.read_text(encoding="utf-8"))
        )
        if implementation_path.is_file() else 0
    )
    return (
        int(not judge["implementation_ready"]),
        audit["contamination"],
        audit["leakage"] + sum(item["failure_class"] == "implementation-leakage" for item in approved),
        len(judge["invented_requirements"]),
        len(judge["compatibility_regressions"]),
        material_decision_count,
        len(approved),
        len(judge["redundant_questions"]),
    )


_DEVELOPMENT_OUTCOME_FIELDS = (
    "not_implementation_ready", "contamination", "leakage",
    "invented_requirements", "compatibility_regressions",
    "material_implementation_decisions", "approved_material_blockers", "redundant_questions",
)


def _development_case_delta(baseline_run: Path, candidate_run: Path) -> dict[str, int]:
    baseline = _development_case_outcome(baseline_run)
    candidate = _development_case_outcome(candidate_run)
    delta = {
        field: candidate_value - baseline_value
        for field, baseline_value, candidate_value in zip(
            _DEVELOPMENT_OUTCOME_FIELDS, baseline, candidate,
        )
        if candidate_value != baseline_value and field != "approved_material_blockers"
    }
    def approved_failure_counts(run: Path) -> dict[str, int]:
        review = json.loads((run / "blind-review.json").read_text(encoding="utf-8"))
        adjudication = json.loads((run / "adjudication.json").read_text(encoding="utf-8"))
        approved = {item["finding_id"] for item in adjudication["verdicts"] if item["approved"]}
        counts: dict[str, int] = {}
        for finding in review["findings"]:
            if finding["id"] in approved:
                key = f"approved_finding__{finding['failure_class']}"
                counts[key] = counts.get(key, 0) + 1
        return counts
    baseline_findings = approved_failure_counts(baseline_run)
    candidate_findings = approved_failure_counts(candidate_run)
    for field in sorted(set(baseline_findings) | set(candidate_findings)):
        difference = candidate_findings.get(field, 0) - baseline_findings.get(field, 0)
        if difference:
            delta[field] = difference
    return delta


def _paired_development_non_regression(
    baseline_runs: list[Path], candidate_runs: list[Path],
) -> bool:
    baseline_by_alias = {
        json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))["alias"]: path
        for path in baseline_runs
    }
    candidate_by_alias = {
        json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))["alias"]: path
        for path in candidate_runs
    }
    if set(baseline_by_alias) != set(candidate_by_alias):
        raise ValueError("paired development cases drifted")
    comparisons = [
        (_development_case_outcome(baseline_by_alias[alias]),
         _development_case_outcome(candidate_by_alias[alias]))
        for alias in sorted(baseline_by_alias)
    ]
    return all(
        all(candidate_value <= baseline_value for baseline_value, candidate_value in zip(baseline, candidate))
        for baseline, candidate in comparisons
    ) and any(
        any(candidate_value < baseline_value for baseline_value, candidate_value in zip(baseline, candidate))
        for baseline, candidate in comparisons
    )


def _evaluate_strategies(
    baseline_runs: list[Path], candidate_groups: list[list[Path]], edits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_by_alias = {
        json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))["alias"]: path
        for path in baseline_runs
    }
    evaluations = []
    for index, group in enumerate(candidate_groups):
        candidate_by_alias = {
            json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))["alias"]: path
            for path in group
        }
        if set(candidate_by_alias) != set(baseline_by_alias):
            raise ValueError("strategy evaluation cases drifted")
        improved_cases, regressed_cases = [], []
        regression_failure_counts: dict[str, int] = {}
        improvement_failure_counts: dict[str, int] = {}
        case_deltas: list[dict[str, Any]] = []
        for alias in sorted(baseline_by_alias):
            delta = _development_case_delta(
                baseline_by_alias[alias], candidate_by_alias[alias],
            )
            regressions = sorted(field for field, value in delta.items() if value > 0)
            improvements = sorted(field for field, value in delta.items() if value < 0)
            if regressions:
                regressed_cases.append(alias)
            elif improvements:
                improved_cases.append(alias)
            for field in regressions:
                regression_failure_counts[field] = regression_failure_counts.get(field, 0) + 1
            for field in improvements:
                improvement_failure_counts[field] = improvement_failure_counts.get(field, 0) + 1
            case_deltas.append({
                "case_alias_sha256": hashlib.sha256(alias.encode()).hexdigest(),
                "deltas": delta,
            })
        evaluations.append({
            "candidate": index + 1,
            "strategy": edits[index]["strategy"],
            "operation": edits[index]["operation"],
            "improved_cases": improved_cases,
            "regressed_cases": regressed_cases,
            "regression_failure_counts": regression_failure_counts,
            "improvement_failure_counts": improvement_failure_counts,
            "case_deltas": case_deltas,
            "changed_words": max(
                len(edits[index]["anchor_exact_text"].split()),
                len(edits[index]["replacement_text"].split()),
            ),
        })
    return evaluations


def recompute_strategy_outcomes(
    *, baseline_runs: list[Path], candidate_groups: list[list[Path]],
    mutation_path: Path, output: Path,
) -> dict[str, Any]:
    """Rebuild development-only strategy history with failure-class deltas."""

    mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
    edits = mutation.get("candidate_edits", [])
    if len(baseline_runs) != 8 or len(candidate_groups) != len(edits):
        raise ValueError("strategy outcome reconstruction input count drifted")
    if any(len(group) != 8 for group in candidate_groups):
        raise ValueError("each reconstructed strategy requires eight candidate runs")
    evaluations = _evaluate_strategies(baseline_runs, candidate_groups, edits)
    baseline_metrics = development_metrics(baseline_runs)
    result = {
        "schema": "MutationStrategyOutcomes.v2",
        "source_partitions": ["development"],
        "evaluations": [
            {**item, "eligible": (
                development_candidate_is_eligible(baseline_metrics, development_metrics(group))
                and _paired_development_non_regression(baseline_runs, group)
            )}
            for item, group in zip(evaluations, candidate_groups)
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _completed_run_matches(
    target: Path, *, public: dict[str, Any], sealed: dict[str, Any], skill_text: str,
    evaluator_rubric: str | None = None,
) -> bool:
    manifest_path = target / "run-manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema": "NativeEvolutionImportedRun.v1",
        "alias": public["alias"],
        "partition": public["metadata"]["partition"],
        "model": "gpt-5.6-sol",
        "skill_sha256": hashlib.sha256(skill_text.encode()).hexdigest(),
        "case_sha256": artifact_digest(public),
        "sealed_source_sha256": artifact_digest(sealed),
        "per_case_mutator_invoked": False,
    }
    if evaluator_rubric is not None:
        expected["evaluator_sha256"] = hashlib.sha256(evaluator_rubric.encode()).hexdigest()
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"completed imported run identity drifted: {target}")
    for name, digest in manifest.get("artifact_sha256", {}).items():
        artifact = target / name
        if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            raise ValueError(f"completed imported run artifact drifted: {artifact}")
    if not manifest.get("artifact_sha256"):
        raise ValueError(f"completed imported run has no artifact digest evidence: {target}")
    return True


def _completed_batch_matches(
    target: Path, *, baseline_skill: str, development_runs: list[Path],
) -> bool:
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_paths = sorted(target.glob("candidate-*-SKILL.md"))
    mutation_path = target / "mutation.json"
    audit_path = target / "mutation-input-audit.json"
    for artifact in (mutation_path, audit_path):
        if not artifact.is_file():
            raise ValueError(f"completed batch mutation artifact is missing: {artifact}")
    if not candidate_paths:
        raise ValueError(f"completed batch mutation has no candidates: {target}")
    candidates = [path.read_text(encoding="utf-8") for path in candidate_paths]
    mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
    signals = development_signals(development_runs)
    expected = {
        "schema": "DevelopmentSignalMutation.v6",
        "development_cases": 8,
        "signal_count": len(signals),
        "signal_corpus_sha256": hashlib.sha256(
            json.dumps(
                signals, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "baseline_sha256": hashlib.sha256(baseline_skill.encode()).hexdigest(),
        "candidate_sha256s": [hashlib.sha256(item.encode()).hexdigest() for item in candidates],
        "source_partitions": ["development"],
        "mutation_input_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"completed batch mutation identity drifted: {target}")
    edits = mutation.get("candidate_edits", [])
    if len(edits) != len(candidates):
        raise ValueError(f"completed batch mutation strategy count drifted: {target}")
    if manifest.get("mutation_performed"):
        _validate_strategy_portfolio(mutation.get("portfolio", {}).get("strategies", []))
        for edit, candidate in zip(edits, candidates):
            expected_candidate = _apply_edit(baseline_skill, edit)
            if expected_candidate != candidate:
                raise ValueError(f"completed batch mutation candidate drifted: {target}")
    elif candidates != [baseline_skill]:
        raise ValueError(f"completed zero-signal candidates drifted: {target}")
    if manifest.get("mutation_performed") != any(item != baseline_skill for item in candidates):
        raise ValueError(f"completed batch mutation performed flag drifted: {target}")
    if manifest.get("mutation_calls") != (len(candidates) + 1 if signals else 0):
        raise ValueError(f"completed batch mutation call count drifted: {target}")
    expected_ids = {item["signal_id"] for item in signals}
    for edit in edits:
        review_ids = [item["signal_id"] for item in edit["signal_reviews"]]
        if len(review_ids) != len(set(review_ids)) or set(review_ids) != expected_ids:
            raise ValueError(f"completed batch mutation review coverage drifted: {target}")
    return True


def execute_study(
    *, sealed_approved: Path, corpus_root: Path, cache: ContentAddressedCache,
    repository_root: Path, v5_skill: Path, run_root: Path, v6_skill: Path,
    deployed_skill: Path, decision_output: Path, max_workers: int | None = None,
    strategy_history: Path | None = None,
    evaluator_spec: Path | None = None,
    mutation_parent_skill: Path | None = None,
    mutation_signal_runs: list[Path] | None = None,
    development_baseline_runs: list[Path] | None = None,
) -> dict[str, Any]:
    approved = json.loads(sealed_approved.read_text(encoding="utf-8"))["cases"]
    by_partition = {
        name: [item for item in approved if item["partition"] == name]
        for name in ("development", "validation", "holdout")
    }
    expected = {"development": 8, "validation": 3, "holdout": 4}
    if {name: len(items) for name, items in by_partition.items()} != expected:
        raise ValueError("approved sealed manifest does not contain the 8/3/4 pilot")
    v5_text = v5_skill.read_text(encoding="utf-8")
    evaluator = (
        json.loads(evaluator_spec.read_text(encoding="utf-8"))
        if evaluator_spec is not None else {
            **EvaluatorSpec(DEFAULT_EVALUATOR_RUBRIC).as_dict(), "epoch": 0,
        }
    )
    evaluator_identity = EvaluatorSpec.from_dict(
        evaluator, allow_legacy_epoch1=True,
    )
    evaluator_rubric = evaluator_identity.rubric
    evaluator_sha256 = evaluator_identity.sha256

    def run_one(
        case: dict[str, Any], skill_text: str, target: Path, *, require_ready: bool = True,
    ) -> Path:
        checkout = prepare_checkout(
            repository=case["repository_family"], base_commit=case["base_commit"],
            alias=case["alias"], root=repository_root,
        )
        case_dir = (
            sealed_approved.parent / "holdout-cases" / case["alias"]
            if case["partition"] == "holdout"
            else corpus_root / "cases" / case["alias"]
        )
        public = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        sealed = json.loads((case_dir / "sealed-source.json").read_text(encoding="utf-8"))
        if _completed_run_matches(
            target, public=public, sealed=sealed, skill_text=skill_text,
            evaluator_rubric=evaluator_rubric,
        ):
            pass
        else:
            if target.exists():
                raise ValueError(f"incomplete imported run must be preserved before retry: {target}")
            run_imported_case(
                public_case=public, sealed_source=sealed, cache=cache,
                repo_root=repository_root / checkout["alias"], skill_md=skill_text, run_dir=target,
                evaluator_rubric=evaluator_rubric,
            )
        contract = json.loads((target / "contract.json").read_text(encoding="utf-8"))
        if not contract["implementation_ready"] and require_ready:
            raise ValueError(f"fresh implementation requires an implementation-ready contract: {target}")
        if not contract["implementation_ready"]:
            return target
        public_request = cache.get_text(
            public["public_request"]["cache_key"], public["public_request"]["digest"],
        )
        evidence = json.loads((target / "evidence.json").read_text(encoding="utf-8"))
        implementation_dir = target / "implementation"
        if not completed_implementation_matches(
            implementation_dir, base_commit=case["base_commit"],
            public_request=public_request, contract=contract,
        ):
            if implementation_dir.exists():
                raise ValueError(
                    f"incomplete implementation must be preserved before retry: {implementation_dir}"
                )
            run_fresh_implementation(
                source_repository=repository_root / checkout["alias"],
                base_commit=case["base_commit"], public_request=public_request,
                audited_evidence=evidence, contract=contract, output_dir=implementation_dir,
            )
        return target

    if development_baseline_runs is not None:
        development_runs = list(development_baseline_runs)
        expected_aliases = {str(item["alias"]) for item in by_partition["development"]}
        observed_aliases = set()
        for path in development_runs:
            manifest = json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))
            observed_aliases.add(str(manifest.get("alias")))
            if (
                manifest.get("partition") != "development"
                or manifest.get("skill_sha256") != hashlib.sha256(v5_text.encode()).hexdigest()
                or manifest.get("evaluator_sha256") != evaluator_sha256
            ):
                raise ValueError("external development baseline identity drifted")
            artifacts = manifest.get("artifact_sha256")
            if not isinstance(artifacts, dict) or not artifacts:
                raise ValueError("external development baseline artifacts are unauthenticated")
            case_dir = corpus_root / "cases" / str(manifest["alias"])
            if (
                artifact_digest(json.loads((case_dir / "case.json").read_text(encoding="utf-8")))
                != manifest.get("case_sha256")
                or artifact_digest(json.loads((case_dir / "sealed-source.json").read_text(encoding="utf-8")))
                != manifest.get("sealed_source_sha256")
            ):
                raise ValueError("external development baseline corpus drifted")
            for name, digest in artifacts.items():
                artifact = path / name
                if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
                    raise ValueError("external development baseline artifact drifted")
        if len(development_runs) != 8 or observed_aliases != expected_aliases:
            raise ValueError("external development baseline cases drifted")
    else:
        development_runs = _run_parallel(
            by_partition["development"],
            lambda case: run_one(
                case, v5_text, run_root / "development" / case["alias"] / "v5",
            ),
            max_workers=max_workers,
        )
    mutation_parent_text = (
        mutation_parent_skill.read_text(encoding="utf-8")
        if mutation_parent_skill is not None else v5_text
    )
    mutation_runs = mutation_signal_runs if mutation_signal_runs is not None else development_runs
    if (mutation_parent_skill is None) != (mutation_signal_runs is None):
        raise ValueError("mutation lineage parent and signal runs must be supplied together")
    if len(mutation_runs) != 8:
        raise ValueError("mutation lineage requires exactly eight development signal runs")
    parent_sha256 = hashlib.sha256(mutation_parent_text.encode()).hexdigest()
    mutation_aliases: set[str] = set()
    for path in mutation_runs:
        manifest = json.loads((path / "run-manifest.json").read_text(encoding="utf-8"))
        alias = str(manifest.get("alias"))
        mutation_aliases.add(alias)
        artifacts = manifest.get("artifact_sha256")
        case_dir = corpus_root / "cases" / alias
        if (
            manifest.get("partition") != "development"
            or manifest.get("skill_sha256") != parent_sha256
            or manifest.get("evaluator_sha256") != evaluator_sha256
            or not isinstance(artifacts, dict) or not artifacts
            or artifact_digest(json.loads((case_dir / "case.json").read_text(encoding="utf-8")))
            != manifest.get("case_sha256")
            or artifact_digest(json.loads((case_dir / "sealed-source.json").read_text(encoding="utf-8")))
            != manifest.get("sealed_source_sha256")
        ):
            raise ValueError("mutation lineage signal identity drifted")
        for name, digest in artifacts.items():
            artifact = path / name
            if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
                raise ValueError("mutation lineage signal artifact drifted")
    if mutation_aliases != {str(item["alias"]) for item in by_partition["development"]}:
        raise ValueError("mutation lineage cases drifted")
    batch_dir = run_root / "batch-mutation"
    if not _completed_batch_matches(
        batch_dir, baseline_skill=mutation_parent_text, development_runs=mutation_runs,
    ):
        if batch_dir.exists():
            raise ValueError(f"incomplete batch mutation must be preserved before retry: {batch_dir}")
        batch_mutate(
            baseline_skill=mutation_parent_text, development_run_dirs=mutation_runs,
            output_dir=batch_dir,
            strategy_history=(
                json.loads(strategy_history.read_text(encoding="utf-8"))
                if strategy_history is not None else None
            ),
        )
    candidate_skills = sorted(batch_dir.glob("candidate-*-SKILL.md"))
    candidate_texts = [path.read_text(encoding="utf-8") for path in candidate_skills]
    development_candidate_jobs = [
        (candidate_index, case, candidate_text,
         run_root / "development-candidates" / f"candidate-{candidate_index + 1}" / case["alias"])
        for candidate_index, candidate_text in enumerate(candidate_texts)
        for case in by_partition["development"]
    ]
    development_candidate_runs = _run_parallel(
        development_candidate_jobs,
        lambda job: (
            job[0], run_one(job[1], job[2], job[3], require_ready=False)
        ),
        max_workers=max_workers,
    )
    baseline_development_metrics = development_metrics(development_runs)
    candidate_groups = [
        [path for index, path in development_candidate_runs if index == candidate_index]
        for candidate_index in range(len(candidate_skills))
    ]
    candidate_development_metrics = [development_metrics(group) for group in candidate_groups]
    mutation = json.loads((batch_dir / "mutation.json").read_text(encoding="utf-8"))
    edits = mutation["candidate_edits"]
    strategy_evaluations = _evaluate_strategies(
        development_runs, candidate_groups, edits,
    )
    eligible = [
        index for index, metrics in enumerate(candidate_development_metrics)
        if development_candidate_is_eligible(baseline_development_metrics, metrics)
        and _paired_development_non_regression(development_runs, candidate_groups[index])
    ]
    selected_index = (
        max(
            eligible,
            key=lambda index: (
                development_non_regression_rank(candidate_development_metrics[index]), -index,
            ),
        )
        if eligible else None
    )
    (batch_dir / "development-selection.json").write_text(
        json.dumps({
            "schema": "DevelopmentCandidateSelection.v1",
            "selected_candidate": selected_index + 1 if selected_index is not None else None,
            "eligible_candidates": [index + 1 for index in eligible],
            "baseline": baseline_development_metrics.__dict__,
            "candidates": [item.__dict__ for item in candidate_development_metrics],
            "candidate_runs": [
                [str(path.relative_to(run_root)) for path in group]
                for group in candidate_groups
            ],
            "strategy_evaluations": strategy_evaluations,
            "rule": "paired per-case defect non-regression with strict improvement",
            "source_partitions": ["development"],
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (batch_dir / "strategy-outcomes.json").write_text(
        json.dumps({
            "schema": "MutationStrategyOutcomes.v2",
            "source_partitions": ["development"],
            "evaluations": [
                {**item, "eligible": item["candidate"] - 1 in eligible}
                for item in strategy_evaluations
            ],
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if selected_index is None:
        if hashlib.sha256(deployed_skill.read_bytes()).hexdigest() != hashlib.sha256(
            v5_skill.read_bytes()
        ).hexdigest():
            raise ValueError("deployed skill drifted from frozen baseline")
        if v6_skill.exists():
            raise ValueError("v6 must not exist after development rejection")
        result = {
            "schema": "SWEbenchEvolutionDecision.v2",
            "development_selected_candidate": None,
            "development_gate": "paired-per-case-non-regression-with-strict-improvement",
            "development_baseline": baseline_development_metrics.__dict__,
            "development_candidates": [item.__dict__ for item in candidate_development_metrics],
            "validation_winner": None,
            "validation_gate": "absolute-zero",
            "validation_opened": False,
            "holdout": None,
            "holdout_opened": False,
            "promotion_eligible": False,
            "promoted": False,
            "deployed_sha256": hashlib.sha256(deployed_skill.read_bytes()).hexdigest(),
            "evaluator_sha256": evaluator_sha256,
            "evaluator_epoch": evaluator.get("epoch", 0),
            "mutation_parent_sha256": parent_sha256,
            "v6_sha256": None,
        }
        decision_output.parent.mkdir(parents=True, exist_ok=True)
        decision_output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return result
    candidate_skill = batch_dir / "selected-candidate-SKILL.md"
    candidate_text = candidate_texts[selected_index]
    candidate_skill.write_text(candidate_text, encoding="utf-8")
    validation_jobs = [
        (case, v5_text, run_root / "validation" / case["alias"] / "v5", True)
        for case in by_partition["validation"]
    ] + [
        (case, candidate_text, run_root / "validation" / case["alias"] / "candidate", False)
        for case in by_partition["validation"]
    ]
    validation_runs = _run_parallel(
        validation_jobs,
        lambda job: run_one(job[0], job[1], job[2], require_ready=job[3]),
        max_workers=max_workers,
    )
    split = len(by_partition["validation"])
    baseline_validation = validation_runs[:split]
    candidate_validation = validation_runs[split:]
    winner = select_validation_winner(
        validation_metrics(baseline_validation), validation_metrics(candidate_validation)
    )
    if winner != "candidate":
        if hashlib.sha256(deployed_skill.read_bytes()).hexdigest() != hashlib.sha256(v5_skill.read_bytes()).hexdigest():
            raise ValueError("deployed skill drifted from frozen baseline")
        if v6_skill.exists():
            raise ValueError("v6 must not exist after validation rejection")
        result = {
            "schema": "SWEbenchEvolutionDecision.v2",
            "development_selected_candidate": selected_index + 1,
            "validation_winner": "baseline",
            "validation_gate": "absolute-zero",
            "validation_baseline": validation_metrics(baseline_validation).__dict__,
            "validation_candidate": validation_metrics(candidate_validation).__dict__,
            "holdout": None,
            "holdout_opened": False,
            "promotion_eligible": False,
            "promoted": False,
            "deployed_sha256": hashlib.sha256(deployed_skill.read_bytes()).hexdigest(),
            "evaluator_sha256": evaluator_sha256,
            "evaluator_epoch": evaluator.get("epoch", 0),
            "mutation_parent_sha256": parent_sha256,
            "v6_sha256": None,
        }
        decision_output.parent.mkdir(parents=True, exist_ok=True)
        decision_output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return result
    selected_text = candidate_text
    holdout_runs = _run_parallel(
        by_partition["holdout"],
        lambda case: run_one(
            case, selected_text, run_root / "holdout" / case["alias"] / "selected",
        ),
        max_workers=max_workers,
    )
    return finalize_study(
        v5_skill=v5_skill, candidate_skill=candidate_skill,
        baseline_validation_runs=baseline_validation,
        candidate_validation_runs=candidate_validation, holdout_runs=holdout_runs,
        v6_skill=v6_skill, deployed_skill=deployed_skill, output=decision_output,
    )
