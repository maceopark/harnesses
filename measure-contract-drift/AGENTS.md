# PROJECT GUIDE

This project is a generational interview-discovery experiment with an immutable seed and
parent-copy-then-edit replacement overlays.

- `discovery-study.json` binds the minimal seed, twelve public cases, fixed Markdown owner world
  models, and defaults.
- `src/driftbench/discovery*.py` owns strict contracts, scheduling, direct model roles, receipts,
  resume, feedback, and Pareto evaluation.
- `src/driftbench/tmux_panes.py` is the mandatory twelve-pane, one-pane-per-case presentation boundary.
- `protocol/ultimateinterview/schema3-discovery/` is immutable vendored measurement infrastructure.
- `corpus/public/` contains the public prompts and starter repositories.

Run tests with `uv run --extra test pytest -q`. Run the experiment from attached tmux with
`scripts/run-live.sh --one-generation`. Fail closed on malformed output, digest drift, missing
tmux, compiler/checker rejection, or unsafe paths. Do not reintroduce legacy evolution, fake,
OCI, holdout, champion, or final-test paths.
