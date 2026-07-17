# Minimal Seed Interview Discovery

Generational experiment for discovering compact interview strategies from one minimal seed.

Candidate skills mutate only the discovery overlay: repository grounding, material-decision
identification, question interaction, and termination. The current Ultimateinterview contract
surface (authority reconciliation, v2 decision projection, compilation, and projection checking)
is a digest-bound immutable runtime snapshot shared by every candidate. The independent evaluator
and both postmortem validators come from the matching current postmortem snapshot. The seed text is
kept byte-for-byte unchanged.

Run from a normal terminal; the wrapper creates and attaches a tmux session automatically. If it
is already running inside tmux, it creates the twelve-pane dashboard in the current session:

```sh
scripts/run-live.sh --one-generation
scripts/run-live.sh --evolve .measurecontractdrift/discovery/G00_RUN --one-generation
scripts/run-live.sh --resume .measurecontractdrift/discovery/RUN --one-generation
```

Before a live run, an independent card author must seal one Owner Card per case in
[`discovery/oracle`](discovery/oracle/README.md). The checked-in study intentionally has no cards,
so it fails closed rather than manufacturing user policy from the starter repository.

The default run creates one immutable control plus four open mutations, evaluates eight train and
four validation cases twice (120 terminal cells), uses twelve persistent case-bound tmux panes, and stops
without opening any final-test path.
Every cell retries once at most and preserves its transcript, selections, schema-3 compiler session,
implementation diff, validated postmortem, parsed result, attempts, and receipt.
Each worker pane shows Q&A, coding, and postmortem role transitions plus a compact first-line summary
for command, MCP, web-search, collaboration, and file-change tool activity.

The owner responder, which does not receive a candidate ID or skill text, alone grants authority
when a proposed option uniquely maps to an Owner Card item. Each cell records `owner-exchanges.json`
and `discovery-result.json`; a critical miss, ambiguity, failed card probe, authority expansion, or
invalid lineage is a hard veto. The archive uses discovery-success Wilson lower bound and question
burden, not contract fidelity. Train feedback is candidate-specific; validation details are never
generator input.

Implementation is fail-closed on interview completeness. If the contract draft is explicitly
incomplete, names unresolved material decisions, or leaves any Owner Card item unresolved or
ambiguous, the cell writes `interview-blocked.json` and never compiles or edits the starter. A fresh
implementer may also return `blocked-contract-gap`, but only with a nonempty gap list and a byte-empty
repository diff. `decision.jsonl` is available at an exact writable session path only for internal
choices covered by active bounded delegation; it cannot authorize observable behavior. Any escaped
requirement or scope drift found by the independent postmortem is a hard veto and is fed back as an
unreported contract gap.
The coordinator binds `fail-closed-contract-gaps-v1` into run and cell digests, so cells produced
under the earlier permissive semantics cannot be silently reused by `--resume`.

`--evolve` verifies a completed resumable parent generation, selects the first archived candidate as
the incumbent, and retains its complete overlay unchanged as the control. Four independent mutation
calls receive the immutable seed, that incumbent overlay, its candidate-specific train feedback, and
the pinned runtime boundary. Each call edits the parent into one complete replacement overlay; the
controller evaluates `seed + child overlay`, never `parent skill + delta`. Parent artifacts, card
digests, owner-responder version, overlays, effective limits, and every cell input are digest-bound
for fail-closed resume. A parent run produced by the old cumulative format is rejected rather than
silently mixed with replacement semantics.

The four mutation slots are intentionally open: the generator may explore a different interviewing
algorithm, but cannot edit the seed, authority model, compiler, or postmortem. `convergence.json`
records early stopping; reduced diagnostic runs never trigger convergence.

Tests:

```sh
uv run --extra test pytest -q
```
