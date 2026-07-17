"""Command line entry point for the minimal-seed discovery experiment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

from .discovery_backend import DirectCodexDiscoveryBackend, terminate_active_model_processes
from .discovery_runner import DiscoveryRunner, load_manifest
from .tmux_panes import DiscoveryDashboard


def _project(manifest: Path) -> Path:
    return manifest.resolve(strict=True).parent


def _run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve(strict=True)
    manifest = load_manifest(manifest_path)
    project = _project(manifest_path)
    run_dir = Path(args.run_dir).resolve() if args.run_dir else (
        project / ".measurecontractdrift/discovery" /
        ("g00-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    dashboard = DiscoveryDashboard.require(
        run_id=run_dir.name, worker_count=12,
        pane_labels=tuple(case.case_id for case in manifest.cases))
    backend = DirectCodexDiscoveryBackend(
        project, run_dir / "backend",
        codex=os.environ.get("CODEX", shutil.which("codex") or "codex"),
        model=manifest.model, reasoning_effort=manifest.reasoning_effort,
        runtime_digest=manifest.runtime_digest,
    )
    result = DiscoveryRunner(manifest_path, run_dir, backend, dashboard).run(
        max_candidates=args.max_candidates, max_parallel=args.max_parallel,
    )
    print(result)
    return 0


def _evolve(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve(strict=True)
    manifest = load_manifest(manifest_path)
    project = _project(manifest_path)
    parent_run = Path(args.parent_run).resolve(strict=True)
    parent_receipt = json.loads((parent_run / "receipt.json").read_text(encoding="utf-8"))
    generation = int(parent_receipt["generation"]) + 1
    run_dir = Path(args.run_dir).resolve() if args.run_dir else (
        project / ".measurecontractdrift/discovery" /
        (f"g{generation:02d}-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    )
    dashboard = DiscoveryDashboard.require(
        run_id=run_dir.name, worker_count=12,
        pane_labels=tuple(case.case_id for case in manifest.cases))
    backend = DirectCodexDiscoveryBackend(
        project, run_dir / "backend",
        codex=os.environ.get("CODEX", shutil.which("codex") or "codex"),
        model=manifest.model, reasoning_effort=manifest.reasoning_effort,
        runtime_digest=manifest.runtime_digest,
    )
    result = DiscoveryRunner(
        manifest_path, run_dir, backend, dashboard,
        generation=generation, parent_run=parent_run,
    ).run(max_candidates=args.max_candidates, max_parallel=args.max_parallel)
    print(result)
    return 0


def _resume(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve(strict=True)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    manifest_path = Path(args.manifest).resolve(strict=True)
    manifest = load_manifest(manifest_path)
    if not isinstance(state, dict):
        raise RuntimeError("resume state is invalid")
    context_path = run_dir / "generation-context.json"
    if context_path.is_file():
        context = json.loads(context_path.read_text(encoding="utf-8"))
        generation = int(context["generation"])
        parent_run = Path(context["parent_run"])
    else:
        generation = 0
        parent_run = None
    dashboard = DiscoveryDashboard.require(
        run_id=run_dir.name, worker_count=12,
        pane_labels=tuple(case.case_id for case in manifest.cases))
    backend = DirectCodexDiscoveryBackend(
        _project(manifest_path), run_dir / "backend",
        codex=os.environ.get("CODEX", shutil.which("codex") or "codex"),
        model=manifest.model, reasoning_effort=manifest.reasoning_effort,
        runtime_digest=manifest.runtime_digest,
    )
    result = DiscoveryRunner(
        manifest_path, run_dir, backend, dashboard,
        generation=generation, parent_run=parent_run,
    ).run(
        max_candidates=args.max_candidates, max_parallel=args.max_parallel,
    )
    print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="driftbench")
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser("discovery")
    actions = discovery.add_subparsers(dest="action", required=True)
    run = actions.add_parser("run")
    run.add_argument("--manifest", required=True)
    run.add_argument("--run-dir")
    run.add_argument("--one-generation", action="store_true", required=True)
    run.add_argument("--max-candidates", type=int, choices=range(1, 5))
    run.add_argument("--max-parallel", type=int, choices=range(1, 13))
    run.set_defaults(handler=_run)
    evolve = actions.add_parser("evolve")
    evolve.add_argument("--manifest", required=True)
    evolve.add_argument("--parent-run", required=True)
    evolve.add_argument("--run-dir")
    evolve.add_argument("--one-generation", action="store_true", required=True)
    evolve.add_argument("--max-candidates", type=int, choices=range(1, 5))
    evolve.add_argument("--max-parallel", type=int, choices=range(1, 13))
    evolve.set_defaults(handler=_evolve)
    resume = actions.add_parser("resume")
    resume.add_argument("--manifest", required=True)
    resume.add_argument("--run-dir", required=True)
    resume.add_argument("--one-generation", action="store_true", required=True)
    resume.add_argument("--max-candidates", type=int, choices=range(1, 5))
    resume.add_argument("--max-parallel", type=int, choices=range(1, 13))
    resume.set_defaults(handler=_resume)
    return parser


def main(argv: list[str] | None = None) -> int:
    def stop_model_processes(signum: int, _frame: object) -> None:
        terminate_active_model_processes()
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, stop_model_processes)
    signal.signal(signal.SIGTERM, stop_model_processes)
    try:
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
