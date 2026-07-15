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

The retained live runtime is `driftbench interview-eval`. It runs direct Codex sessions with `gpt-5.6-sol` and configurable reasoning effort (medium by default) for each selected public case, uses the vendored Ultimateinterview skill to produce a Discovery Record, and uses the vendored compiler and checker to create and validate the Build Contract, implementation return, and postmortem evidence.

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

Live enrollment is read from `<project-root>/.measurecontractdrift/live.toml`. Set `model_reasoning_effort` to `"low"`, `"medium"`, or `"high"`; the default is `"medium"` when the key is omitted. The pinned model remains `gpt-5.6-sol`.

`run-live.sh` requires tmux. When invoked outside tmux, it first starts a tmux session and re-runs itself there with the same validated run or resume arguments; if tmux is unavailable it exits with a clear error before starting the interview. When an invocation schedules at least two cells with `--max-parallel 2` or higher, each executing cell automatically gets a detached pane as its first runtime action. The pane shows `Preparing` while local interview inputs are set up, then labeled interview questions and answers, ordered `Interview`, `Contract`, `Implementation`, `Checking`, and `Postmortem` stages, and live content-free Codex activity such as command, tool, file-change, and turn state. It never shows prompts, reasoning text, messages, arguments, output, file contents, or secrets. The owned pane closes only after the complete cell succeeds; a failed cell retains a safe stage, exception class, and manual-close message. The wrapper also enables current-window pane borders; each bounded safe title contains the treatment, case, and a concise coding-task summary. A pane operation failure warns once for that cell and preserves the existing locked, case-labeled stderr fallback for interview exchanges. This transient presentation creates no pane transcript or registry, adds no CLI flag, and does not change run evidence or final stdout JSON.

Live output is written below `<project-root>/.measurecontractdrift/interview-eval/` unless the runtime is given a run directory. Persisted JSON uses sorted keys and two-space indentation. A run contains `state.json`, `manifest.json`, and `receipt.json`; each cell contains its repository and `.ultimateinterview` session evidence.

Resume an incomplete or failed run by its directory:

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory> \
  --max-parallel 1
```

The resume command reuses completed cells and reruns cells that are not completed.
