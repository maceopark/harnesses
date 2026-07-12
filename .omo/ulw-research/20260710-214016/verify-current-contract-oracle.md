# Current contract-oracle rebaseline

Observed: 2026-07-11. Repository state: clean `master` at `1b0ed6f`, after `944a0c1` introduced the contract-oracle v1 controls. This ledger supersedes only the **current-state** interpretation of the 2026-07-10 snapshot; it does not erase that snapshot's historical bypass evidence.

## Fresh executed verification

Working directory: `.agents/skills/ultimateinterview`.

```text
uv run --python 3.13 --with 'pydantic>=2.7' --with 'pytest>=8.0' --with 'rich>=13.7' --with 'typer>=0.12' pytest -q \
  scripts/test_v1_gate_integration.py \
  scripts/test_v1_build_contract_integration.py \
  scripts/test_v1_session_integration.py \
  scripts/test_v1_probe_integration.py
```

Observed output:

```text
.............                                                            [100%]
13 passed in 0.84s
```

## What v1 now mechanically provides

- A canonical `build-contract.json` sidecar is compiled from reviewed Part 1, self-digested, recompiled by the gate, and rejected if stale or unequal.
- The composite gate requires structured evidence, current orientation/breadth open-world records, a resolved typed L0-L3 probe sequence, checkpoint and lens obligations, a fresh-implementer test, testable predicates, a real-surface verification row, and host-resolvable command heads.
- A material requirement/evidence/probe change advances `material_revision` and invalidates the relevant review/open-world freshness.

These are ABI and structural/process-policy properties. They are not proof that an external command ran, that an evidence producer is authenticated, that two declared groups are causally independent, that all consumed session files form one snapshot, or that natural-language behavior is semantically preserved.

## Fresh residual checks

An isolated-runtime audit re-ran the following against current v1:

- The same actor can label two evidence records with distinct `independence_group` strings; a year-2000 observation declared `freshness=current` is eligible; and `channel=from-code` with `source_actor=user` is accepted. These fields remain claimant declarations.
- `pytest does-not-exist.py` remains accepted by the command policy because the gate checks a command head, not execution outcome.
- A temporary copy of `integration_fixtures/v1-ready` whose `ledger.json` requirement text alone was semantically changed still returned `implementation_ready: true`; the BuildContract sidecar is bound, but a whole-session manifest is absent.
- A legacy v0 temporary session containing only ledger/protocol/handoff still passed `--gate`; v1 requires a decision-log instruction but not the decisions file itself.

## Scope

The prior 666-test result and its six bypass probes remain evidence about the 2026-07-10 pre-commit snapshot. They must not be read as the present v1 test baseline. The current focused test result above and the residual checks are the evidence for this update.
