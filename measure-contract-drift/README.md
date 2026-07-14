# Ultimateinterview Contract Drift Benchmark

A deterministic benchmark for measuring how well an interview-produced Build Contract survives a fresh implementation context. Conceptual guides: [English](USER_GUIDE.en.md) · [한국어](USER_GUIDE.ko.md)

## Deterministic development benchmark

From the workspace root:

```sh
measure-contract-drift/scripts/run-fake.sh
```

The fake-development run uses deterministic adapters. It does not call a model or access holdout data, and its scorecard is development evidence only.

Validate the public corpus:

```sh
uv run --project measure-contract-drift \
  driftbench validate-corpus \
  --public-root measure-contract-drift/corpus/public \
  --partition dev
```

## Live interview evaluation

The retained live runtime is `driftbench interview-eval`. It runs a direct Codex interview for each selected public case, uses the vendored Ultimateinterview skill to produce a Discovery Record, and uses the vendored compiler and checker to create and validate the Build Contract, implementation return, and postmortem evidence.

Start a run with the wrapper:

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-cells 1 \
  --max-parallel 1
```

Or invoke the CLI directly:

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --policy <policy-path> \
  --max-cells 1 \
  --max-parallel 1
```

The six public cases run in required `baseline` and `candidate` treatments, for 12 cells total. The baseline is the vendored immutable skill; `candidate_skill` names a workspace-contained relative path. Candidate bytes, enrollment, corpus rows, and starter trees are pinned inside the run before execution. `--max-cells` limits cells for that invocation, and `--max-parallel` controls concurrent cells; both accept 1–12.

Live output is written below `<project-root>/.measurecontractdrift/interview-eval/` unless the runtime is given a run directory. Persisted JSON uses sorted keys and two-space indentation. A run contains `state.json`, `manifest.json`, and `receipt.json`; each cell contains its repository and `.ultimateinterview` session evidence.

Resume an incomplete or failed run by its directory:

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory> \
  --max-parallel 1
```

The resume command reuses completed cells and reruns cells that are not completed.
