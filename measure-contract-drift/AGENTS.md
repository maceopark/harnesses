# PROJECT GUIDE

## Purpose

This project is a deterministic, fail-closed benchmark for measuring how much intended behavior survives an interview-produced handoff into a fresh implementation context.

Read `README.md` for commands and `USER_GUIDE.en.md` or `USER_GUIDE.ko.md` for the benchmark model before changing behavior.

## Working Map

- `src/driftbench/`: deterministic benchmark controller, workers, replay, semantic comparison, scoring, and the direct-Codex `interview_eval.py` live CLI.
- `tests/`: behavioral, isolation, replay, integration, and live CLI coverage.
- `corpus/`: public development cases, private-test fixtures, and the external holdout boundary.
- `protocol/`: pinned deterministic benchmark snapshots plus the vendored Ultimateinterview skill, compiler, and checker used by the live CLI.
- `oci/`, `Dockerfile.worker`, `requirements.worker.lock`, `wheelhouse/`: hermetic worker runtime and isolation policy for the deterministic benchmark lifecycle only.
- `configs/`, `arms/`, `schemas/`: deterministic study and contract definitions.
- `scripts/run-fake.sh`: deterministic development lifecycle entry point.
- `.measurecontractdrift/`: generated direct live CLI output; do not hand-edit it to make checks pass.
- `runs/`, `artifacts/`: generated or observed deterministic evidence; do not hand-edit to make checks pass.

Read the nearest nested `AGENTS.md` before editing a governed subtree.

## Invariants

- Fail closed. Missing services, invalid bindings, stale digests, malformed deterministic receipts, or undeclared deterministic inputs must be rejected; never silently fall back.
- Preserve fresh-context role separation in the deterministic benchmark. Planner, implementer, observer, and postmortem may consume only their declared transfer artifacts.
- Preserve canonical serialization and SHA-256 binding across the deterministic benchmark receipt chain.
- Local fake-development evidence must never be described as live-model, holdout, or production effectiveness evidence.
- Holdout prompts and starters stay external. Do not add private holdout material to the repository.
- OCI execution is authoritative only for the deterministic benchmark lifecycle; the local operator and Docker daemon remain trusted boundaries there.
- The live `driftbench interview-eval` CLI runs direct Codex with the vendored Ultimateinterview skill, compiler, and checker, writes generated output below `.measurecontractdrift/`, and requires neither Docker/OCI nor the deterministic receipt chain or legacy live modules.
- Scored arms are policy data. Do not make the non-creditable full-v2 fixture scoreable without valid pinned deterministic receipts and corresponding policy/test changes.

## Commands

Run from the workspace root:

```sh
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests
uv run --project measure-contract-drift driftbench validate-corpus --public-root measure-contract-drift/corpus/public --partition dev
uv run --project measure-contract-drift python -m driftbench.worker_launcher --project-root measure-contract-drift preflight
measure-contract-drift/scripts/run-fake.sh
```

The README may mention an earlier checkout path; use this checkout's actual `measure-contract-drift` path.

## Change Discipline

- Use Python 3.14 and the project-managed `uv` environment.
- Make contract changes atomically across models, validation, serialization, replay, tests, and user guidance.
- Add focused tests for altered branch conditions, tamper rejection, digest validation, and error behavior.
- Do not weaken assertions, isolation controls, or receipt checks to accept a new fixture.
- Do not edit generated caches, egg-info, run output, or vendored wheels unless the task explicitly concerns regeneration.
