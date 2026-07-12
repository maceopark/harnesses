# DRIFTBENCH SOURCE GUIDE

This file refines the project-root guidance for `src/driftbench/`.

## Module Map

- `cli.py`: command surface and lifecycle orchestration.
- `models.py`, `state.py`: typed contracts and persisted run state.
- `artifacts.py`, `redaction.py`, `decision_log.py`: canonical evidence handling.
- `corpus.py`: corpus loading and validation.
- `worker_launcher.py`, `worker.py`, `role_worker.py`: isolated role staging, launch, execution, and import.
- `semantic.py`: exact typed behavior-atom comparison.
- `metrics.py`, `reporter.py`: score reconstruction and reporting.
- `native_snapshot.py`, `native_receipt_precheck.py`, `canonical_execution_binding.py`: pinned protocol evidence and binding checks.
- `evaluation_client.py`, `simulator_service.py`, `simulator.py`: externally provisioned live-service boundaries.
- `gjc_episode.py`, `postmortem.py`: episode and postmortem artifacts.

## Rules

- Treat persisted models as public contracts. Reject unknown, contradictory, or incomplete state at the boundary.
- Canonical bytes, normalization, ordering, trailing-newline rules, and digest computation must remain centralized and deterministic.
- Never trust copied score fields. Reconstruct outcomes from bound inputs, receipts, observations, and policy.
- Do not let controller processes inspect role-private context or private holdout payloads.
- Worker launch arguments must remain direct, allowlisted, digest-addressed, network-disabled, read-only, non-root, capability-free, and resource-bounded.
- Rejected preflight or unavailable external services must produce an explicit blocked/error result, not a fake adapter fallback.
- Avoid broad exception handling around validation and security boundaries; preserve actionable failure causes without leaking private material.

## Verification

Run the narrowest relevant test module, then the full suite for changes to models, lifecycle state, receipts, canonicalization, worker launch, or scoring:

```sh
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/test_core.py
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests
```
