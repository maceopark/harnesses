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

## Live skill evolution evaluation

The live lifecycle is `driftbench interview-eval run --study ...` and `driftbench interview-eval resume --run-dir ...`. The study manifest pins the direct Codex model and reasoning effort for every role.

For every candidate-case repetition, the runtime:

1. copies the public starter into an isolated cell repository;
2. obtains structured interviewer decisions with explicit recommendations;
3. submits every compatible recommendation verbatim through the simulator;
4. seals the implementation spec;
5. starts a fresh implementer with only that sealed spec;
6. requires a diff, implementation return, execution evidence, and `decision.jsonl`; and
7. reconstructs five metrics from deterministic checks, independent execution, and a blinded judge.

The implementer never receives the interview transcript or evaluator feedback. A missing or malformed recommendation, evidence binding, or decision log fails closed.

Start a bounded run:

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-generations 10 \
  --max-candidates 8
```

The same CLI can be called directly:

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --study measure-contract-drift/configs/evolution-study.json
```

`--smoke` is the only live-model smoke path. It evaluates one frozen candidate on one train case for two repetitions and explicitly makes no effectiveness claim. Every direct model role fails closed after a five-minute wall-clock limit.

The 12 public cases use a fixed 6 train / 3 validation / 3 final-test split. Generation zero is the frozen baseline plus seven variants; later generations contain eight candidates. Each candidate-case runs 2–5 times. The run stops at 10 generations or after three validation generations without Pareto hypervolume improvement. Final-test evaluates the frozen baseline and selected champion five times per case, then locks mutation and reselection.

All cases are public. Final-test is process-isolated evaluation, not private holdout or generalization evidence. Generator inputs contain train failure taxonomy and at most three suggestions. Validation exposes aggregate selection scores, not detailed case artifacts.

The enrollment file `<project-root>/.measurecontractdrift/live.toml` may set `model_reasoning_effort`. It defaults to `"medium"` when omitted and applies to interviewer, simulator, implementation, and postmortem Codex sessions. The model remains pinned to `gpt-5.6-sol`.

## Run output and resume

New runs are written to:

```text
<project-root>/.measurecontractdrift/interview-eval/live-<timestamp>-evolution/
```

Persisted JSON files are pretty printed with sorted keys and two-space indentation. The run root contains:

- `state.json`: digest bindings, candidates, completed cells, archive progress, and final lock;
- `rubrics/`, `candidates/`, and `cells/`: fixed rubrics and bound candidate evidence;
- `final-test.json`: public process-isolated baseline/champion comparison; and
- `receipt.json`: completion and champion identity.

Resume by run directory:

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory>
```

Completed cells are retained only when their artifact hashes still match. Resume rejects drift in the study, corpus, baseline skill, runtime, rubric, or completed cell evidence.

## Reading results

The CLI emits compact JSON with the run directory and status. Cell effectiveness is the minimum of contract coverage, recommendation integrity, implementation conformance, verification credibility, and decision governance. Invalid evidence or a critical governance failure makes the cell effectiveness zero.

The live path evaluates public development cases only. It does not make claims about private holdouts or general model performance.
