"""Validation selection, holdout gate, and auditable promotion decision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from .metrics import holdout_metrics, validation_metrics
from .study import passes_strict_holdout_gate, select_validation_winner


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_run_skill(run_dirs: Iterable[Path], expected_digest: str, partition: str) -> None:
    for run_dir in run_dirs:
        manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        if manifest["partition"] != partition or manifest["skill_sha256"] != expected_digest:
            raise ValueError(f"{partition} run used the wrong skill or partition")
        if manifest["per_case_mutator_invoked"]:
            raise ValueError(f"{partition} run invoked a forbidden per-case mutator")


def finalize_study(
    *, v5_skill: Path, candidate_skill: Path, baseline_validation_runs: Iterable[Path],
    candidate_validation_runs: Iterable[Path], holdout_runs: Iterable[Path],
    v6_skill: Path, deployed_skill: Path, output: Path,
) -> dict[str, object]:
    baseline_runs = tuple(baseline_validation_runs)
    candidate_runs = tuple(candidate_validation_runs)
    sealed_holdout_runs = tuple(holdout_runs)
    v5_digest = _digest(v5_skill)
    candidate_digest = _digest(candidate_skill)
    _assert_run_skill(baseline_runs, v5_digest, "validation")
    _assert_run_skill(candidate_runs, candidate_digest, "validation")
    baseline_metrics = validation_metrics(baseline_runs)
    candidate_metrics = validation_metrics(candidate_runs)
    winner = select_validation_winner(baseline_metrics, candidate_metrics)
    selected_skill = candidate_skill if winner == "candidate" else v5_skill
    selected_digest = _digest(selected_skill)
    _assert_run_skill(sealed_holdout_runs, selected_digest, "holdout")
    metrics = holdout_metrics(sealed_holdout_runs)
    if _digest(deployed_skill) != v5_digest:
        raise ValueError("deployed skill drifted from frozen v5 before promotion")
    if v6_skill.exists():
        raise ValueError("v6 must not exist before full completion verification")
    eligible = passes_strict_holdout_gate(metrics)
    result: dict[str, object] = {
        "schema": "SWEbenchEvolutionDecision.v2", "validation_winner": winner,
        "validation_gate": "absolute-zero", "holdout_opened": True,
        "validation_baseline": baseline_metrics.__dict__,
        "validation_candidate": candidate_metrics.__dict__,
        "selected_skill_sha256": selected_digest, "holdout": metrics.__dict__,
        "promotion_eligible": eligible, "promoted": False,
        "deployed_sha256": _digest(deployed_skill), "v6_sha256": None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result
