"""Aggregate sealed run evidence into fixed validation and holdout metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .study import HoldoutMetrics, ValidationMetrics


def _load_run(
    run_dir: Path, expected_partition: str, *, judge_path: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    if manifest["partition"] != expected_partition or manifest["per_case_mutator_invoked"]:
        raise ValueError("run partition or mutator invariant is invalid")
    return {
        "manifest": manifest,
        "judge": json.loads((judge_path or run_dir / "judge.json").read_text(encoding="utf-8")),
        "review": json.loads((run_dir / "blind-review.json").read_text(encoding="utf-8")),
        "adjudication": json.loads((run_dir / "adjudication.json").read_text(encoding="utf-8")),
        "audit": json.loads((run_dir / "runtime-audit.json").read_text(encoding="utf-8")),
        "implementation": (
            json.loads(
                (run_dir / "implementation" / "implementation-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            if (run_dir / "implementation" / "implementation-manifest.json").is_file()
            else {"decision_count": 0}
        ),
    }


def _approved_findings(run: dict[str, Any]) -> list[dict[str, Any]]:
    findings = {item["id"]: item for item in run["review"]["findings"]}
    return [findings[item["finding_id"]] for item in run["adjudication"]["verdicts"] if item["approved"]]


def _contract_metrics(
    run_dirs: Iterable[Path], *, partition: str, expected_cases: int,
    judge_paths: Iterable[Path] | None = None,
) -> ValidationMetrics:
    paths = list(run_dirs)
    judges = list(judge_paths) if judge_paths is not None else [None] * len(paths)
    if len(judges) != len(paths):
        raise ValueError("judge replay count must match run count")
    runs = [
        _load_run(path, partition, judge_path=judge)
        for path, judge in zip(paths, judges)
    ]
    if len(runs) != expected_cases or len({run["manifest"]["alias"] for run in runs}) != expected_cases:
        raise ValueError(f"{partition} requires exactly {expected_cases} distinct cases")
    approved = [item for run in runs for item in _approved_findings(run)]
    return ValidationMetrics(
        contamination=sum(run["audit"]["contamination"] for run in runs),
        leakage=sum(run["audit"]["leakage"] for run in runs) + sum(item["failure_class"] == "implementation-leakage" for item in approved),
        invented_requirements=sum(len(run["judge"]["invented_requirements"]) for run in runs),
        compatibility_regressions=sum(len(run["judge"]["compatibility_regressions"]) for run in runs),
        implementation_decisions=sum(run["implementation"]["decision_count"] for run in runs),
        material_implementation_decisions=sum(
            run["implementation"].get(
                "material_decision_count", run["implementation"]["decision_count"],
            ) for run in runs
        ),
        approved_material_blockers=len(approved),
        implementation_ready=sum(run["judge"]["implementation_ready"] for run in runs),
        owner_recall=sum(run["judge"]["owner_recall"] for run in runs) / expected_cases,
        repository_fidelity=sum(run["judge"]["repository_fidelity"] for run in runs) / expected_cases,
        redundant_questions=sum(len(run["judge"]["redundant_questions"]) for run in runs),
    )


def validation_metrics(run_dirs: Iterable[Path]) -> ValidationMetrics:
    return _contract_metrics(run_dirs, partition="validation", expected_cases=3)


def development_metrics(run_dirs: Iterable[Path]) -> ValidationMetrics:
    return _contract_metrics(run_dirs, partition="development", expected_cases=8)


def development_metrics_with_replays(
    run_dirs: Iterable[Path], judge_paths: Iterable[Path],
) -> ValidationMetrics:
    """Aggregate development metrics using replayed judges over original raw runs."""

    return _contract_metrics(
        run_dirs, partition="development", expected_cases=8, judge_paths=judge_paths,
    )


def holdout_metrics(run_dirs: Iterable[Path]) -> HoldoutMetrics:
    runs = [_load_run(path, "holdout") for path in run_dirs]
    if len(runs) != 4 or len({run["manifest"]["alias"] for run in runs}) != 4:
        raise ValueError("holdout requires exactly four distinct cases")
    approved = [item for run in runs for item in _approved_findings(run)]
    return HoldoutMetrics(
        completed_cases=4,
        implementation_ready=sum(run["judge"]["implementation_ready"] for run in runs),
        contamination=sum(run["audit"]["contamination"] for run in runs),
        leakage=sum(run["audit"]["leakage"] for run in runs) + sum(item["failure_class"] == "implementation-leakage" for item in approved),
        invented_requirements=sum(len(run["judge"]["invented_requirements"]) for run in runs),
        compatibility_regressions=sum(len(run["judge"]["compatibility_regressions"]) for run in runs),
        implementation_decisions=sum(run["implementation"]["decision_count"] for run in runs),
        material_implementation_decisions=sum(
            run["implementation"].get(
                "material_decision_count", run["implementation"]["decision_count"],
            ) for run in runs
        ),
        approved_material_blockers=len(approved),
    )
