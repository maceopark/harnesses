# Ultimateinterview Contract-Drift Benchmark

## What it measures

The benchmark asks a software-engineering question: when requirements pass through an interview and a Build Contract, how much intended behavior survives a fresh implementation context?

The public development corpus is defined in `corpus/public/cases.json`. Each case has a prompt and clean starter tree. Private holdout material is not stored in this repository.

## Deterministic development benchmark

`measure-contract-drift/scripts/run-fake.sh` runs the deterministic development fixture. It validates benchmark mechanics without calling a model or accessing holdout data. Its result is not evidence of model quality, production interview effectiveness, or holdout performance.

```sh
measure-contract-drift/scripts/run-fake.sh
```

Validate the public corpus independently:

```sh
uv run --project measure-contract-drift \
  driftbench validate-corpus \
  --public-root measure-contract-drift/corpus/public \
  --partition dev
```

## Live interview evaluation

The live lifecycle is `driftbench interview-eval run` and `driftbench interview-eval resume`. All direct Codex roles use `gpt-5.6-sol` with configurable reasoning effort, defaulting to medium.

For every selected case and treatment, the runtime:

1. copies the public starter into an isolated cell repository;
2. starts a direct Codex interviewer session and retains its thread only for that interview;
3. uses the vendored Ultimateinterview skill to produce a Discovery Record;
4. runs the vendored authority compiler to create the Build Contract;
5. starts a fresh direct Codex implementation session limited to the starter tree;
6. validates the implementation return and evidence with the vendored checker; and
7. starts a fresh direct Codex postmortem session and checks its report.

The simulator and implementation/postmortem sessions are ephemeral. The implementation session receives the sealed Build Contract rather than the interview transcript.

Start a bounded run:

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-cells 1 \
  --max-parallel 1
```

The same CLI can be called directly:

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --policy <policy-path> \
  --max-cells 1 \
  --max-parallel 1
```

The six public cases run in required `baseline` and `candidate` treatments, for 12 cells total. The baseline is the vendored immutable skill. `candidate_skill` must be a relative path inside the workspace; its bytes, the enrollment, corpus rows, and starter trees are copied into the run's `inputs/` directory before execution. Resume validates those pinned inputs and every completed cell before continuing. `--max-cells` selects 1–12 pending cells for the current invocation; `--max-parallel` runs 1–12 cells concurrently.

The enrollment file `<project-root>/.measurecontractdrift/live.toml` may set `model_reasoning_effort`. It defaults to `"medium"` when omitted and applies to interviewer, simulator, implementation, and postmortem Codex sessions. The model remains pinned to `gpt-5.6-sol`.

`run-live.sh` requires tmux. Outside tmux it first starts a tmux session and re-runs itself there with the same validated run or resume arguments; missing tmux fails clearly before any interview starts. For an invocation that schedules at least two cells with `--max-parallel` set to 2–12, each executing cell receives one detached pane as its first runtime action. The pane starts at `Preparing` while local interview inputs are set up, then remains through `Interview`, `Contract`, `Implementation`, `Checking`, and `Postmortem`. It shows color-independent `Question` and `Answer` blocks plus live content-free activity categories and lifecycle states. Raw prompts, reasoning text, model messages, command or tool arguments and output, file contents, and secrets are never rendered. The wrapper enables current-window pane borders; each bounded credential-safe title identifies the treatment, case, and coding task. A pane closes only after its complete cell succeeds. Failed or catchably interrupted cells retain their panes with the safe current stage, exception class, and manual-close instruction; a resume attempt uses a new attempt identity and does not reuse a retained pane. An operational pane failure warns once and preserves the existing case-and-treatment-prefixed stderr fallback for interview exchanges. Pane content is transient: it is not added to transcripts, manifests, receipts, state, or any separate pane artifact. Final compact stdout JSON and existing diagnostics are unchanged.

## Run output and resume

New runs are written to:

```text
<project-root>/.measurecontractdrift/interview-eval/live-<timestamp>-interview-eval/
```

Persisted JSON files are pretty printed with sorted keys and two-space indentation. The run root contains:

- `state.json`: per-cell progress and result;
- `manifest.json`: hashes for generated files; and
- `receipt.json`: overall status, completed/total cell counts, and the manifest digest.

Each cell stores its `repo/` and `.ultimateinterview/<case-id>/` session directory, including the Discovery Record, Build Contract, implementation return, diff, checker evidence, and postmortem.

Resume by run directory:

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory> \
  --max-parallel 1
```

Completed cells are retained; cells without a completed result are run again. `--max-cells` can also restrict a resume invocation.

## Reading results

The CLI emits compact JSON with the run directory and status. `partial` means the bounded invocation succeeded while pending cells remain; `completed` means all 12 cells completed. `failed` means at least one attempted cell failed; inspect that cell's `state.json` entry and session evidence.

The live path evaluates public development cases only. It does not make claims about private holdouts or general model performance.
