"""Command-line entry points for the SWE-bench interview pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable
from urllib.request import urlopen

from . import DATASET_ID, DATASET_PARQUET_SHA256, DATASET_REVISION
from .cache import ContentAddressedCache
from .importer import import_rows
from .harness import OfficialHarness, validate_pilot
from .batch import batch_mutate
from .metrics import holdout_metrics, validation_metrics
from .pilot import prepare_pilot
from .pipeline import build_approved_corpus
from .repository import prepare_pilot_checkouts
from .finalize import finalize_study
from .verify import verify_and_promote, verify_development_rejection
from .execute import execute_study, recompute_strategy_outcomes
from .evaluator_evolution import (
    EvaluatorSpec, canonical_anchor_manifest_bytes, evolve_evaluator_once,
    generate_pairwise_anchor_manifest, split_evaluator_anchor_manifest,
    verify_evaluator_epoch,
)
from .replay import run_replay_2x2, snapshot_recorded_development_corpus
from .epoch import run_coevolution_epoch
from .report import write_completion_report
from .schemas import validate_artifact
from .selection import Candidate, stratified_select
from .study import HoldoutMetrics, ValidationMetrics, passes_strict_holdout_gate, select_validation_winner


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def _read_jsonl(path: str) -> Iterable[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number} must be a JSON object")
                yield value


def _read_rows(path: str) -> Iterable[dict[str, Any]]:
    source = Path(path)
    if source.suffix == ".parquet":
        from datasets import Dataset

        return (dict(row) for row in Dataset.from_parquet(str(source)))
    return _read_jsonl(path)


def _write(value: Any, output: str | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def download_dataset(dataset_id: str, split: str, revision: str, output: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("download requires a 40-character immutable revision SHA")
    if (dataset_id, split, revision) != (DATASET_ID, "test", DATASET_REVISION):
        raise ValueError("download must use the Build Contract dataset, split, and revision")
    url = (
        f"https://huggingface.co/datasets/{dataset_id}/resolve/{revision}/"
        "data/test-00000-of-00001.parquet"
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "wb") as stream, urlopen(url) as response:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                digest.update(block)
                stream.write(block)
        if digest.hexdigest() != DATASET_PARQUET_SHA256:
            raise ValueError(
                "downloaded parquet digest does not match the Build Contract: "
                f"{digest.hexdigest()}"
            )
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swebench-interview-cases")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download")
    download.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    download.add_argument("--split", default="test")
    download.add_argument("--revision", required=True)
    download.add_argument("--output", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("--input", required=True)
    importer.add_argument("--revision", required=True)
    importer.add_argument("--cache", required=True)
    importer.add_argument("--output")
    select = commands.add_parser("select")
    select.add_argument("--input", required=True)
    select.add_argument("--revision-digest", required=True)
    select.add_argument("--output")
    validate = commands.add_parser("validate")
    validate.add_argument("kind", choices=("public_case", "sealed_source", "partition_index"))
    validate.add_argument("path")
    prepare = commands.add_parser("prepare-pilot")
    prepare.add_argument("--parquet", required=True)
    prepare.add_argument("--cache")
    prepare.add_argument("--public-output", required=True)
    prepare.add_argument("--sealed-output", required=True)
    reseed = commands.add_parser("reseed-exhausted-slot")
    reseed.add_argument("--parquet", required=True)
    reseed.add_argument("--public-selection", required=True)
    reseed.add_argument("--sealed-selection", required=True)
    reseed.add_argument("--slot", type=int, required=True)
    reseed.add_argument("--excluded-instance-id", action="append", required=True)
    reseed.add_argument("--cache", required=True)
    harness = commands.add_parser("validate-harness")
    harness.add_argument("--parquet", required=True)
    harness.add_argument("--sealed-selection", required=True)
    harness.add_argument("--harness-source", required=True)
    harness.add_argument("--run-root", required=True)
    harness.add_argument("--output", required=True)
    corpus = commands.add_parser("build-corpus")
    corpus.add_argument("--parquet", required=True)
    corpus.add_argument("--sealed-selection", required=True)
    corpus.add_argument("--cache", required=True)
    corpus.add_argument("--harness-source", required=True)
    corpus.add_argument("--run-root", required=True)
    corpus.add_argument("--corpus-root", required=True)
    batch = commands.add_parser("batch-mutate")
    batch.add_argument("--skill", required=True)
    batch.add_argument("--development-run", action="append", required=True)
    batch.add_argument("--output-dir", required=True)
    metrics = commands.add_parser("metrics")
    metrics.add_argument("partition", choices=("validation", "holdout"))
    metrics.add_argument("--run", action="append", required=True)
    metrics.add_argument("--output", required=True)
    checkouts = commands.add_parser("checkout-repositories")
    checkouts.add_argument("--sealed-selection", required=True)
    checkouts.add_argument("--root", required=True)
    checkouts.add_argument("--output", required=True)
    finalize = commands.add_parser("finalize-study")
    finalize.add_argument("--v5-skill", required=True)
    finalize.add_argument("--candidate-skill", required=True)
    finalize.add_argument("--baseline-validation-run", action="append", required=True)
    finalize.add_argument("--candidate-validation-run", action="append", required=True)
    finalize.add_argument("--holdout-run", action="append", required=True)
    finalize.add_argument("--v6-skill", required=True)
    finalize.add_argument("--deployed-skill", required=True)
    finalize.add_argument("--output", required=True)
    verify = commands.add_parser("verify-completion")
    verify.add_argument("--public-selection", required=True)
    verify.add_argument("--sealed-approved", required=True)
    verify.add_argument("--corpus-root", required=True)
    verify.add_argument("--harness-evidence-root", required=True)
    verify.add_argument("--development-run", action="append", required=True)
    verify.add_argument("--batch-manifest", required=True)
    verify.add_argument("--baseline-validation-run", action="append", required=True)
    verify.add_argument("--candidate-validation-run", action="append", required=True)
    verify.add_argument("--holdout-run", action="append", required=True)
    verify.add_argument("--decision", required=True)
    verify.add_argument("--v5-skill", required=True)
    verify.add_argument("--candidate-skill", required=True)
    verify.add_argument("--v6-skill", required=True)
    verify.add_argument("--deployed-skill", required=True)
    verify.add_argument("--mutation-parent-skill")
    verify.add_argument("--mutation-signal-run", action="append")
    verify.add_argument("--output", required=True)
    verify_development = commands.add_parser("verify-development-rejection")
    verify_development.add_argument("--sealed-approved", required=True)
    verify_development.add_argument("--corpus-root", required=True)
    verify_development.add_argument("--development-run", action="append", required=True)
    verify_development.add_argument("--batch-manifest", required=True)
    verify_development.add_argument("--decision", required=True)
    verify_development.add_argument("--v5-skill", required=True)
    verify_development.add_argument("--v6-skill", required=True)
    verify_development.add_argument("--deployed-skill", required=True)
    verify_development.add_argument("--mutation-parent-skill")
    verify_development.add_argument("--mutation-signal-run", action="append")
    verify_development.add_argument("--output", required=True)
    execute = commands.add_parser("execute-study")
    execute.add_argument("--sealed-approved", required=True)
    execute.add_argument("--corpus-root", required=True)
    execute.add_argument("--cache", required=True)
    execute.add_argument("--repository-root", required=True)
    execute.add_argument("--v5-skill", required=True)
    execute.add_argument("--run-root", required=True)
    execute.add_argument("--v6-skill", required=True)
    execute.add_argument("--deployed-skill", required=True)
    execute.add_argument("--decision-output", required=True)
    execute.add_argument(
        "--evaluator-spec",
        help="versioned evaluator JSON frozen for the entire generation",
    )
    execute.add_argument(
        "--mutation-parent-skill",
        help="non-deployed lineage parent used only to generate the next candidates",
    )
    execute.add_argument(
        "--mutation-signal-run", action="append",
        help="eight development runs belonging to the mutation lineage parent",
    )
    execute.add_argument(
        "--development-baseline-run", action="append",
        help="reuse eight immutable baseline runs with matching skill and evaluator identities",
    )
    anchors = commands.add_parser("build-evaluator-anchors")
    anchors.add_argument("--approved-sealed", required=True)
    anchors.add_argument("--sealed-source", action="append", required=True)
    anchors.add_argument("--include-hindsight-confidence-b", action="store_true")
    anchors.add_argument("--include-material-omission-confidence-a", action="store_true")
    anchors.add_argument("--output", required=True)
    split_anchors = commands.add_parser("split-evaluator-anchors")
    split_anchors.add_argument("--input", required=True)
    split_anchors.add_argument("--validation-families", type=int, default=1)
    split_anchors.add_argument("--seed", default="evaluator-anchor-split-v1")
    split_anchors.add_argument("--output-dir", required=True)
    evolve_evaluator = commands.add_parser("evolve-evaluator")
    evolve_evaluator.add_argument("--incumbent", required=True)
    evolve_evaluator.add_argument("--training-anchors", required=True)
    evolve_evaluator.add_argument("--validation-anchors", required=True)
    evolve_evaluator.add_argument("--split-manifest")
    evolve_evaluator.add_argument("--output-dir", required=True)
    verify_evaluator = commands.add_parser("verify-evaluator-epoch")
    verify_evaluator.add_argument("--validation-anchors", required=True)
    verify_evaluator.add_argument("--training-anchors")
    verify_evaluator.add_argument("--split-manifest")
    verify_evaluator.add_argument("--evolution-dir", required=True)
    verify_evaluator.add_argument("--run-root", required=True)
    verify_evaluator.add_argument("--decision", required=True)
    verify_evaluator.add_argument("--output", required=True)
    replay = commands.add_parser("replay-evaluator-2x2")
    replay.add_argument("--baseline-run", action="append", required=True)
    replay.add_argument("--candidate-run", action="append", required=True)
    replay.add_argument("--incumbent", required=True)
    replay.add_argument("--challenger", required=True)
    replay.add_argument("--output-dir", required=True)
    snapshot = commands.add_parser("snapshot-recorded-corpus")
    snapshot.add_argument("--source-run", action="append", required=True)
    snapshot.add_argument("--sealed-corpus-root", required=True)
    snapshot.add_argument("--output-root", required=True)
    epoch = commands.add_parser("run-coevolution-epoch")
    epoch.add_argument("--config", required=True)
    epoch.add_argument("--output-root", required=True)
    outcomes = commands.add_parser("recompute-strategy-outcomes")
    outcomes.add_argument("--baseline-run", action="append", required=True)
    for number in range(1, 4):
        outcomes.add_argument(f"--candidate-{number}-run", action="append", required=True)
    outcomes.add_argument("--mutation", required=True)
    outcomes.add_argument("--output", required=True)
    execute.add_argument(
        "--strategy-history",
        help="development-only mutation strategy outcomes from a prior generation",
    )
    execute.add_argument(
        "--max-workers", type=int, default=None,
        help="maximum concurrent cases per phase (default: all cases in the phase)",
    )
    report = commands.add_parser("write-completion-report")
    report.add_argument("--verification", required=True)
    report.add_argument("--decision", required=True)
    report.add_argument("--output", required=True)
    study = commands.add_parser("study")
    study.add_argument("phase", choices=("validation", "holdout"))
    study.add_argument("--baseline")
    study.add_argument("--candidate", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "download":
        download_dataset(args.dataset, args.split, args.revision, args.output)
    elif args.command == "import":
        imported = import_rows(_read_rows(args.input), dataset_revision=args.revision, cache=ContentAddressedCache(Path(args.cache)))
        _write(
            [{"alias": item.alias, "instance_id": item.instance_id, "public_source": item.public_source_descriptor(), "sealed_inputs": item.sealed_inputs()} for item in imported],
            args.output,
        )
    elif args.command == "select":
        candidates = [Candidate(**item) for item in _read_json(args.input)]
        selected = stratified_select(candidates, args.revision_digest)
        _write(
            [{"partition": item.partition, "alias": item.alias, "instance_id": item.ranked.candidate.instance_id, "repository_family": item.ranked.candidate.repository_family, "stratum": item.ranked.stratum, "rank": item.ranked.rank} for item in selected],
            args.output,
        )
    elif args.command == "validate":
        validate_artifact(args.kind, _read_json(args.path))
    elif args.command == "prepare-pilot":
        public, sealed = prepare_pilot(
            Path(args.parquet), ContentAddressedCache(Path(args.cache) if args.cache else None)
        )
        _write(public, args.public_output)
        _write(sealed, args.sealed_output)
    elif args.command == "reseed-exhausted-slot":
        from datasets import Dataset
        from .pilot import reseed_exhausted_slot

        public, sealed = reseed_exhausted_slot(
            public=_read_json(args.public_selection),
            sealed=_read_json(args.sealed_selection),
            rows=[dict(row) for row in Dataset.from_parquet(args.parquet)],
            slot_number=args.slot,
            excluded_instance_ids=set(args.excluded_instance_id),
            cache=ContentAddressedCache(Path(args.cache)),
        )
        _write(public, args.public_selection)
        _write(sealed, args.sealed_selection)
    elif args.command == "validate-harness":
        from datasets import Dataset

        runner = OfficialHarness(
            project_root=Path(args.run_root),
            dataset_path=Path(args.parquet),
            output_root=Path(args.run_root) / "evidence",
            harness_source=Path(args.harness_source),
        )
        rows = [dict(row) for row in Dataset.from_parquet(args.parquet)]
        result = validate_pilot(runner, rows, _read_json(args.sealed_selection))
        _write(result, args.output)
    elif args.command == "build-corpus":
        from datasets import Dataset

        cache = ContentAddressedCache(Path(args.cache))
        runner = OfficialHarness(
            project_root=Path(args.run_root), dataset_path=Path(args.parquet),
            output_root=Path(args.run_root) / "evidence", harness_source=Path(args.harness_source),
        )
        result = build_approved_corpus(
            harness=runner, rows=[dict(row) for row in Dataset.from_parquet(args.parquet)],
            sealed_selection=_read_json(args.sealed_selection), cache=cache,
            corpus_root=Path(args.corpus_root), record_root=cache.root / "pilot" / "generation",
            repository_root=cache.root / "repositories",
        )
        _write(result, None)
    elif args.command == "batch-mutate":
        result = batch_mutate(
            baseline_skill=Path(args.skill).read_text(encoding="utf-8"),
            development_run_dirs=[Path(item) for item in args.development_run],
            output_dir=Path(args.output_dir),
        )
        _write(result, None)
    elif args.command == "metrics":
        result = (
            validation_metrics([Path(item) for item in args.run])
            if args.partition == "validation"
            else holdout_metrics([Path(item) for item in args.run])
        )
        _write(result.__dict__, args.output)
    elif args.command == "checkout-repositories":
        result = prepare_pilot_checkouts(_read_json(args.sealed_selection), Path(args.root))
        _write(result, args.output)
    elif args.command == "finalize-study":
        result = finalize_study(
            v5_skill=Path(args.v5_skill), candidate_skill=Path(args.candidate_skill),
            baseline_validation_runs=[Path(item) for item in args.baseline_validation_run],
            candidate_validation_runs=[Path(item) for item in args.candidate_validation_run],
            holdout_runs=[Path(item) for item in args.holdout_run],
            v6_skill=Path(args.v6_skill), deployed_skill=Path(args.deployed_skill),
            mutation_parent_skill=(
                Path(args.mutation_parent_skill) if args.mutation_parent_skill else None
            ),
            mutation_signal_runs=(
                [Path(item) for item in args.mutation_signal_run]
                if args.mutation_signal_run else None
            ),
            output=Path(args.output),
        )
        _write(result, None)
    elif args.command == "verify-completion":
        result = verify_and_promote(
            public_selection=Path(args.public_selection), sealed_approved=Path(args.sealed_approved),
            corpus_root=Path(args.corpus_root), harness_evidence_root=Path(args.harness_evidence_root),
            development_runs=[Path(item) for item in args.development_run],
            batch_manifest=Path(args.batch_manifest),
            baseline_validation_runs=[Path(item) for item in args.baseline_validation_run],
            candidate_validation_runs=[Path(item) for item in args.candidate_validation_run],
            holdout_runs=[Path(item) for item in args.holdout_run], decision_path=Path(args.decision),
            v5_skill=Path(args.v5_skill), candidate_skill=Path(args.candidate_skill),
            v6_skill=Path(args.v6_skill), deployed_skill=Path(args.deployed_skill),
        )
        _write(result, args.output)
    elif args.command == "verify-development-rejection":
        result = verify_development_rejection(
            sealed_approved=Path(args.sealed_approved),
            corpus_root=Path(args.corpus_root),
            development_runs=[Path(item) for item in args.development_run],
            batch_manifest=Path(args.batch_manifest), decision_path=Path(args.decision),
            v5_skill=Path(args.v5_skill), v6_skill=Path(args.v6_skill),
            deployed_skill=Path(args.deployed_skill),
            mutation_parent_skill=(
                Path(args.mutation_parent_skill) if args.mutation_parent_skill else None
            ),
            mutation_signal_runs=(
                [Path(item) for item in args.mutation_signal_run]
                if args.mutation_signal_run else None
            ),
        )
        _write(result, args.output)
    elif args.command == "execute-study":
        result = execute_study(
            sealed_approved=Path(args.sealed_approved), corpus_root=Path(args.corpus_root),
            cache=ContentAddressedCache(Path(args.cache)), repository_root=Path(args.repository_root),
            v5_skill=Path(args.v5_skill), run_root=Path(args.run_root),
            v6_skill=Path(args.v6_skill), deployed_skill=Path(args.deployed_skill),
            decision_output=Path(args.decision_output), max_workers=args.max_workers,
            strategy_history=Path(args.strategy_history) if args.strategy_history else None,
            evaluator_spec=Path(args.evaluator_spec) if args.evaluator_spec else None,
            mutation_parent_skill=(
                Path(args.mutation_parent_skill) if args.mutation_parent_skill else None
            ),
            mutation_signal_runs=(
                [Path(item) for item in args.mutation_signal_run]
                if args.mutation_signal_run else None
            ),
            development_baseline_runs=(
                [Path(item) for item in args.development_baseline_run]
                if args.development_baseline_run else None
            ),
        )
        _write(result, None)
    elif args.command == "build-evaluator-anchors":
        manifest = generate_pairwise_anchor_manifest(
            Path(args.approved_sealed), [Path(item) for item in args.sealed_source],
            include_hindsight_confidence_b=args.include_hindsight_confidence_b,
            include_material_omission_confidence_a=(
                args.include_material_omission_confidence_a
            ),
        )
        Path(args.output).write_bytes(canonical_anchor_manifest_bytes(manifest) + b"\n")
    elif args.command == "split-evaluator-anchors":
        training, validation, split = split_evaluator_anchor_manifest(
            _read_json(args.input), validation_families=args.validation_families,
            seed=args.seed,
        )
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=False)
        for name, value in (
            ("train.json", training), ("validation.json", validation), ("split.json", split),
        ):
            (output_dir / name).write_bytes(canonical_anchor_manifest_bytes(value) + b"\n")
    elif args.command == "evolve-evaluator":
        incumbent_data = _read_json(args.incumbent)
        incumbent = EvaluatorSpec.from_dict(incumbent_data, allow_legacy_epoch1=True)
        result = evolve_evaluator_once(
            incumbent=incumbent, training_manifest=_read_json(args.training_anchors),
            validation_manifest=_read_json(args.validation_anchors),
            output_dir=Path(args.output_dir),
            split_manifest=_read_json(args.split_manifest) if args.split_manifest else None,
        )
        selected_path = Path(args.output_dir) / "selected.json"
        selected = _read_json(str(selected_path))
        selected["epoch"] = int(incumbent_data.get("epoch", 0)) + int(result["promotion"]["promoted"])
        selected_path.write_text(
            json.dumps(selected, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    elif args.command == "verify-evaluator-epoch":
        result = verify_evaluator_epoch(
            validation_manifest=_read_json(args.validation_anchors),
            evolution_dir=Path(args.evolution_dir), run_root=Path(args.run_root),
            decision_path=Path(args.decision),
            training_manifest=(
                _read_json(args.training_anchors) if args.training_anchors else None
            ),
            split_manifest=_read_json(args.split_manifest) if args.split_manifest else None,
        )
        _write(result, args.output)
    elif args.command == "replay-evaluator-2x2":
        result = run_replay_2x2(
            baseline_runs=[Path(item) for item in args.baseline_run],
            candidate_runs=[Path(item) for item in args.candidate_run],
            incumbent=EvaluatorSpec.from_dict(_read_json(args.incumbent), allow_legacy_epoch1=True),
            challenger=EvaluatorSpec.from_dict(_read_json(args.challenger), allow_legacy_epoch1=True),
            output_dir=Path(args.output_dir),
        )
        _write(result, None)
    elif args.command == "snapshot-recorded-corpus":
        result = snapshot_recorded_development_corpus(
            source_runs=[Path(item) for item in args.source_run],
            sealed_corpus_root=Path(args.sealed_corpus_root),
            output_root=Path(args.output_root),
        )
        _write(result, None)
    elif args.command == "run-coevolution-epoch":
        result = run_coevolution_epoch(
            config_path=Path(args.config), output_root=Path(args.output_root),
        )
        _write(result, None)
    elif args.command == "recompute-strategy-outcomes":
        result = recompute_strategy_outcomes(
            baseline_runs=[Path(item) for item in args.baseline_run],
            candidate_groups=[
                [Path(item) for item in getattr(args, f"candidate_{number}_run")]
                for number in range(1, 4)
            ],
            mutation_path=Path(args.mutation), output=Path(args.output),
        )
        _write(result, None)
    elif args.command == "write-completion-report":
        write_completion_report(
            verification_path=Path(args.verification), decision_path=Path(args.decision),
            output=Path(args.output),
        )
    elif args.phase == "validation":
        if not args.baseline:
            raise ValueError("study validation requires --baseline")
        winner = select_validation_winner(ValidationMetrics(**_read_json(args.baseline)), ValidationMetrics(**_read_json(args.candidate)))
        _write({"winner": winner}, None)
    else:
        holdout_data = _read_json(args.candidate)
        holdout_data.setdefault(
            "material_implementation_decisions",
            holdout_data["implementation_decisions"],
        )
        passed = passes_strict_holdout_gate(HoldoutMetrics(**holdout_data))
        _write({"promote": passed}, None)
        return 0 if passed else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
