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

## Live skill evolution evaluation

`driftbench interview-eval` evolves and evaluates `SKILL.md` candidates with direct Codex roles. The checked-in study binds the model, reasoning effort, 12-case corpus, 6/3/3 split, baseline skill, runtime, and every starter digest.

Start a run with the wrapper:

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-generations 10 \
  --max-candidates 8
```

Or invoke the CLI directly:

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --study measure-contract-drift/configs/evolution-study.json
```

Use `--smoke` for the bounded live-model check: it runs the frozen candidate on the first train case for the required two repetitions and emits no effectiveness claim. Each direct model role fails closed after a five-minute wall-clock limit.

Generation zero contains the frozen baseline plus seven variants. Later generations contain eight candidates selected from the cumulative validation Pareto archive. Every candidate-case runs at least twice and statistically non-dominated candidates may run up to five times. Evolution stops after 10 generations or three validation generations without Pareto hypervolume improvement.

The fixed public split is six train cases, three validation cases, and three final-test cases. Generator calls receive only train failure taxonomy and at most three suggestions; validation contributes aggregate selection scores only, and final-test is first opened after champion selection. Because every case is public, final-test is process-isolated evaluation, not private holdout evidence. Once final-test results are published, mutation and champion reselection are permanently closed for that run.

Live enrollment is read from `<project-root>/.measurecontractdrift/live.toml`. Set `model_reasoning_effort` to `"low"`, `"medium"`, or `"high"`; the default is `"medium"` when the key is omitted. The pinned model remains `gpt-5.6-sol`.

Interviewer questions carry decision IDs, explicit options, one matching recommended/preselected option, rationale, and impact boundary. The simulator submits those recommendations verbatim. The fresh implementer receives only the sealed spec and must return its diff, implementation return, execution evidence, and `decision.jsonl`. Scores are reconstructed from deterministic checks, independent execution, and a candidate-blinded judge; copied self-scores are ignored.

Live output is written below `<project-root>/.measurecontractdrift/interview-eval/`. A run retains bound rubrics, candidate skills, per-cell evidence, evolution state, the final-test report, and a receipt.

Resume an incomplete or failed run by its directory:

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory>
```

Resume reuses digest-valid completed cells and rejects study, corpus, baseline skill, runtime, rubric, or artifact drift. Frozen-only v2 state is intentionally incompatible with the evolution schema.
