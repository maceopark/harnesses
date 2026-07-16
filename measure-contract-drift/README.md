# Minimal Seed Interview Discovery

Generation-zero experiment for discovering compact interview strategies from one minimal seed.

Run inside an attached tmux session:

```sh
scripts/run-live.sh --one-generation
scripts/run-live.sh --evolve .measurecontractdrift/discovery/G00_RUN --one-generation
scripts/run-live.sh --resume .measurecontractdrift/discovery/RUN --one-generation
```

The default run creates four candidates, evaluates six train and three validation cases twice
(72 terminal cells), uses four persistent tmux worker panes, and stops without opening final-test.
Every cell retries once at most and preserves its transcript, selections, schema-3 compiler session,
implementation diff, validated postmortem, parsed result, attempts, and receipt.

The generation receipt contains all non-dominated candidates across fidelity Wilson lower bound,
median material-decision count, and absolute `SKILL.md` bytes. Train findings are written to
`generation-feedback.json`; validation details are never generator input.

`--evolve` verifies a completed resumable parent generation, selects parents from its validation
Pareto archive, and makes four independent mutation calls. Each call receives only its parent
`SKILL.md`, the parent's train-only `generation-feedback.json`, and the pinned runtime contract.
It then runs a fresh 72-cell generation. Parent artifacts, feedback, lineage, generated skills,
effective limits, and every cell input are digest-bound for fail-closed resume.

The four candidate slots are manifest-bound structural mutations: fidelity repair, question
compression, interaction redesign, and novel structure. Parents are assigned round-robin from the
previous Pareto archive, so empty slots retain distinct mutation purposes rather than becoming
unconstrained copies. After each evolved generation, `generation-comparison.html` provides a
self-contained parent comparison and `convergence.json` records the early-stop decision. Evolution
stops before generation 9 when the historical Pareto frontier epsilon-covers every new frontier for
two consecutive full generations; reduced diagnostic runs never trigger convergence.

Tests:

```sh
uv run --extra test pytest -q
```
