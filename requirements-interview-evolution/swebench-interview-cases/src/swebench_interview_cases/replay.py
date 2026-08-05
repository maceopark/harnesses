"""Raw-controlled evaluator replay and 2x2 development comparison."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from .evaluator_evolution import EvaluatorSpec
from .implementer import materialize_implementation_materiality
from .imported_native import authenticate_recorded_judge_payload, replay_recorded_judge
from .metrics import development_metrics_with_replays
from .schemas import artifact_digest


class ReplayStudyError(ValueError):
    """Raised when a replay study violates its raw-control invariants."""


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ordered_runs(paths: Iterable[Path], *, require_single_skill: bool = True) -> list[Path]:
    by_alias: dict[str, Path] = {}
    skill_sha256s: set[str] = set()
    for path in paths:
        manifest = _read(Path(path) / "run-manifest.json")
        alias = str(manifest["alias"])
        if alias in by_alias:
            raise ReplayStudyError(f"duplicate replay alias: {alias}")
        if manifest.get("partition") != "development":
            raise ReplayStudyError("2x2 replay accepts development runs only")
        skill_sha256s.add(str(manifest.get("skill_sha256", "")))
        by_alias[alias] = Path(path)
    if len(by_alias) != 8:
        raise ReplayStudyError("each skill arm requires exactly eight development runs")
    if require_single_skill and (len(skill_sha256s) != 1 or not next(iter(skill_sha256s))):
        raise ReplayStudyError("each replay arm requires one authenticated skill identity")
    return [by_alias[alias] for alias in sorted(by_alias)]


def snapshot_recorded_development_corpus(
    *, source_runs: Iterable[Path], sealed_corpus_root: Path, output_root: Path,
) -> dict[str, Any]:
    """Reconstruct the exact public cases used by recorded runs after corpus rotation."""

    runs = _ordered_runs(source_runs, require_single_skill=False)
    output_root.mkdir(parents=True, exist_ok=False)
    cases = []
    for run in runs:
        manifest = _read(run / "run-manifest.json")
        alias = str(manifest["alias"])
        records = [
            _read(path) for path in sorted((run / "calls").glob("*.json"))
            if _read(path).get("role") == "judge"
        ]
        if len(records) != 1:
            raise ReplayStudyError("recorded corpus snapshot requires one judge call per run")
        payload = records[0]["input"]
        upstream = payload["upstream"]
        public = {
            "schema": "InterviewerSafeCase.v1", "alias": alias,
            "upstream": upstream,
            "public_request": {
                "cache_key": upstream["issue_cache_key"], "digest": upstream["issue_digest"],
            },
            "repository_facts": payload["repository_facts"],
            "metadata": payload["metadata"],
            "sealed_source_digest": manifest["sealed_source_sha256"],
        }
        if artifact_digest(public) != manifest["case_sha256"]:
            raise ReplayStudyError("recorded public case cannot reproduce source digest")
        sealed = _read(sealed_corpus_root / "cases" / alias / "sealed-source.json")
        if artifact_digest(sealed) != manifest["sealed_source_sha256"]:
            raise ReplayStudyError("sealed source drifted from recorded run")
        target = output_root / "cases" / alias
        target.mkdir(parents=True)
        for name, value in (("case.json", public), ("sealed-source.json", sealed)):
            (target / name).write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        cases.append({
            "alias": alias, "case_sha256": manifest["case_sha256"],
            "sealed_source_sha256": manifest["sealed_source_sha256"],
        })
    result = {"schema": "RecordedDevelopmentCorpus.v1", "cases": cases}
    result["sha256"] = artifact_digest(result)
    (output_root / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _outcome(run: Path, judge: Mapping[str, Any]) -> tuple[int, ...]:
    audit = _read(run / "runtime-audit.json")
    review = _read(run / "blind-review.json")
    adjudication = _read(run / "adjudication.json")
    finding_by_id = {item["id"]: item for item in review["findings"]}
    approved = [
        finding_by_id[item["finding_id"]]
        for item in adjudication["verdicts"] if item["approved"]
    ]
    implementation_path = run / "implementation" / "implementation-manifest.json"
    decisions = (
        (lambda value: value.get("material_decision_count", value["decision_count"]))(
            _read(implementation_path)
        )
        if implementation_path.is_file() else 0
    )
    return (
        int(not judge["implementation_ready"]),
        int(audit["contamination"]),
        int(audit["leakage"])
        + sum(item["failure_class"] == "implementation-leakage" for item in approved),
        len(judge["invented_requirements"]),
        len(judge["compatibility_regressions"]),
        int(decisions),
        len(approved),
        len(judge["redundant_questions"]),
    )


def _non_regresses(candidate: tuple[int, ...], baseline: tuple[int, ...]) -> bool:
    return all(candidate_value <= baseline_value for candidate_value, baseline_value in zip(candidate, baseline))


def _load_completed_replay(
    replay_dir: Path, *, source_run: Path, evaluator: EvaluatorSpec,
) -> dict[str, Any] | None:
    manifest_path = replay_dir / "replay-manifest.json"
    if not manifest_path.is_file():
        if replay_dir.exists():
            raise ReplayStudyError(f"incomplete replay must be preserved before retry: {replay_dir}")
        return None
    manifest = _read(manifest_path)
    source_manifest_path = source_run / "run-manifest.json"
    expected = {
        "source_run_manifest_sha256": hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
        "replay_evaluator_sha256": evaluator.sha256,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ReplayStudyError("completed replay identity drifted")
    source_manifest = _read(source_manifest_path)
    raw_digests = manifest.get("raw_artifact_sha256")
    if not isinstance(raw_digests, dict) or not raw_digests:
        raise ReplayStudyError("completed replay raw artifact identity is missing")
    for name, digest in raw_digests.items():
        path = source_run / name
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            or source_manifest.get("artifact_sha256", {}).get(name) != digest
        ):
            raise ReplayStudyError("completed replay raw artifact drifted")
    try:
        source_judge_call, _ = authenticate_recorded_judge_payload(source_run)
    except ValueError as error:
        raise ReplayStudyError(str(error)) from error
    if (
        hashlib.sha256(source_judge_call.read_bytes()).hexdigest()
        != manifest.get("source_judge_call_sha256")
    ):
        raise ReplayStudyError("completed replay source judge call drifted")
    judge_path = replay_dir / "judge.json"
    if hashlib.sha256(judge_path.read_bytes()).hexdigest() != manifest.get(
        "judge_sha256"
    ):
        raise ReplayStudyError("completed replay judge drifted")
    return {"manifest": manifest, "judge": _read(judge_path)}


def run_replay_2x2(
    *, baseline_runs: Iterable[Path], candidate_runs: Iterable[Path],
    incumbent: EvaluatorSpec, challenger: EvaluatorSpec,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay both evaluators over two skill arms without changing raw artifacts."""

    baseline = _ordered_runs(baseline_runs)
    candidate = _ordered_runs(candidate_runs)
    baseline_aliases = [_read(path / "run-manifest.json")["alias"] for path in baseline]
    candidate_aliases = [_read(path / "run-manifest.json")["alias"] for path in candidate]
    if baseline_aliases != candidate_aliases:
        raise ReplayStudyError("skill arms must contain the same development aliases")
    baseline_skill = _read(baseline[0] / "run-manifest.json")["skill_sha256"]
    candidate_skill = _read(candidate[0] / "run-manifest.json")["skill_sha256"]
    if baseline_skill == candidate_skill:
        raise ReplayStudyError("2x2 replay requires distinct skill identities")
    output_dir.mkdir(parents=True, exist_ok=True)
    arms = {"baseline": baseline, "candidate": candidate}
    evaluators = {"incumbent": incumbent, "challenger": challenger}
    cells: dict[str, Any] = {}
    outcomes: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {}
    for skill_name, runs in arms.items():
        for evaluator_name, evaluator in evaluators.items():
            judges: list[Path] = []
            replay_manifests: list[dict[str, Any]] = []
            cell_outcomes: dict[str, tuple[int, ...]] = {}
            for run in runs:
                source_manifest = _read(run / "run-manifest.json")
                alias = str(source_manifest["alias"])
                replay_dir = output_dir / "replays" / skill_name / evaluator_name / alias
                replay = _load_completed_replay(
                    replay_dir, source_run=run, evaluator=evaluator,
                ) or replay_recorded_judge(
                    source_run=run, evaluator_rubric=evaluator.rubric,
                    evaluator_sha256=evaluator.sha256, output_dir=replay_dir,
                )
                judges.append(replay_dir / "judge.json")
                replay_manifests.append(replay["manifest"])
                cell_outcomes[alias] = _outcome(run, replay["judge"])
            metrics = development_metrics_with_replays(runs, judges)
            key = f"{skill_name}:{evaluator_name}"
            cells[key] = {
                "skill": skill_name,
                "evaluator": evaluator_name,
                "skill_sha256": replay_manifests[0]["source_skill_sha256"],
                "evaluator_sha256": evaluator.sha256,
                "metrics": metrics.__dict__,
                "replay_manifest_sha256s": [artifact_digest(item) for item in replay_manifests],
            }
            outcomes[(skill_name, evaluator_name)] = cell_outcomes
    flips = []
    for skill_name in arms:
        left = outcomes[(skill_name, "incumbent")]
        right = outcomes[(skill_name, "challenger")]
        for alias in baseline_aliases:
            if left[alias] != right[alias]:
                flips.append({
                    "skill": skill_name, "alias": alias,
                    "incumbent_outcome": list(left[alias]),
                    "challenger_outcome": list(right[alias]),
                })
    result = {
        "schema": "EvaluatorReplay2x2.v1",
        "raw_control": "within each skill arm only",
        "aliases": baseline_aliases,
        "cells": cells,
        "evaluator_induced_flips": flips,
        "incumbent_skill_non_regression": all(
            _non_regresses(
                outcomes[("candidate", "incumbent")][alias],
                outcomes[("baseline", "incumbent")][alias],
            )
            for alias in baseline_aliases
        ),
        "challenger_skill_non_regression": all(
            _non_regresses(
                outcomes[("candidate", "challenger")][alias],
                outcomes[("baseline", "challenger")][alias],
            )
            for alias in baseline_aliases
        ),
    }
    result["sha256"] = artifact_digest(result)
    (output_dir / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def materialize_rejudged_run_views(
    *, source_runs: Iterable[Path], replay_root: Path, skill_arm: str,
    evaluator_label: str, evaluator: EvaluatorSpec, output_root: Path,
) -> list[Path]:
    """Create authenticated run views whose only changed raw artifact is replayed judge output."""

    runs = _ordered_runs(source_runs)
    output_root.mkdir(parents=True, exist_ok=False)
    views = []
    for source in runs:
        source_manifest = _read(source / "run-manifest.json")
        alias = str(source_manifest["alias"])
        replay_dir = replay_root / "replays" / skill_arm / evaluator_label / alias
        replay = _load_completed_replay(
            replay_dir, source_run=source, evaluator=evaluator,
        )
        if replay is None:
            raise ReplayStudyError("rejudged view requires a completed authenticated replay")
        view = output_root / alias
        view.mkdir()
        artifacts = dict(source_manifest.get("artifact_sha256", {}))
        for name in artifacts:
            if name == "judge.json":
                continue
            os.symlink((source / name).resolve(), view / name)
        implementation = source / "implementation"
        if implementation.exists():
            os.symlink(implementation.resolve(), view / "implementation", target_is_directory=True)
        judge_source = replay_dir / "judge.json"
        os.symlink(judge_source.resolve(), view / "judge.json")
        artifacts["judge.json"] = hashlib.sha256(judge_source.read_bytes()).hexdigest()
        manifest = {
            **source_manifest,
            "evaluator_sha256": evaluator.sha256,
            "artifact_sha256": artifacts,
            "rejudged_source_manifest_sha256": hashlib.sha256(
                (source / "run-manifest.json").read_bytes()
            ).hexdigest(),
            "replay_manifest_sha256": hashlib.sha256(
                (replay_dir / "replay-manifest.json").read_bytes()
            ).hexdigest(),
        }
        (view / "run-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        views.append(view)
    return views


def materialize_materiality_run_views(
    *, source_runs: Iterable[Path], output_root: Path,
) -> list[Path]:
    """Overlay legacy runs with independently reviewed implementation decisions."""

    runs = _ordered_runs(source_runs)
    output_root.mkdir(parents=True, exist_ok=False)
    views = []
    for source in runs:
        manifest = _read(source / "run-manifest.json")
        alias = str(manifest["alias"])
        view = output_root / alias
        view.mkdir()
        for item in sorted(source.iterdir()):
            if item.name == "implementation":
                continue
            os.symlink(item.resolve(), view / item.name, target_is_directory=item.is_dir())
        public_request = None
        for record_path in sorted((source / "calls").glob("*.json")):
            candidate = _read(record_path).get("input", {}).get("public_request")
            if isinstance(candidate, str):
                public_request = candidate
                break
        if public_request is None:
            raise ReplayStudyError("legacy materiality migration lacks public request evidence")
        materialize_implementation_materiality(
            source_dir=source / "implementation", output_dir=view / "implementation",
            public_request=public_request, audited_evidence=_read(source / "evidence.json"),
            contract=_read(source / "contract.json"),
        )
        views.append(view)
    return views
