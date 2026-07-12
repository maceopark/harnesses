# TEST GUIDE

This file refines the project-root guidance for `tests/`.

## Coverage Map

- `test_core.py`: core deterministic contracts.
- `test_cli.py`: command flow, lifecycle state, replay, and scorecard behavior.
- `test_isolation.py`: worker policy, launch controls, and fail-closed boundaries.
- `test_oci_role_execution.py`: real OCI role lifecycle and receipts.
- `test_public_starter_execution.py`: public starter behavior.
- `test_semantic_native_snapshot.py`: semantic comparison and pinned native fixtures.

## Rules

- Assert observable behavior and exact rejection reasons at trust boundaries.
- Include positive, malformed, tampered, stale-digest, replay, and resume cases when changing artifact contracts.
- Keep deterministic tests independent of live providers, private holdouts, network access, wall-clock timing, and mutable global state.
- OCI tests may require Docker; do not replace them with mocks when validating launch or isolation semantics.
- Use temporary paths and isolated volumes. Never reuse or mutate checked-in `runs/` as a fixture.
- Do not regenerate expected digests merely to silence a failure; first prove the underlying canonical input intentionally changed.

## Commands

```sh
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/<target>.py
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests
```
