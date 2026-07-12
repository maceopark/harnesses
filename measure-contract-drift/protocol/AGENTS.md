# PINNED PROTOCOL GUIDE

This file refines the project-root guidance for `protocol/`.

## Purpose

`protocol/ultimateinterview/` contains a frozen native protocol snapshot, source manifest, and conformance fixtures used to bind benchmark arms to specific evidence.

## Rules

- Treat each snapshot directory as immutable vendored evidence. Do not casually edit files under `frozen/`.
- A protocol update must be added as a newly identified snapshot with provenance and digest bindings; do not rewrite an existing snapshot in place.
- Keep structural-valid and expected-fail fixtures distinct. Expected-fail v2 evidence is non-creditable and must remain excluded from scoring.
- Source manifest, native snapshot loading, receipt prechecks, arm policy, fixtures, and semantic tests must agree.
- Do not import runtime state, user-home skill copies, or unpinned external protocol files into benchmark execution.
- Changes here require explicit conformance tests for valid bindings, substitution, digest mismatch, and non-creditable receipts.

## Verification

```sh
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/test_semantic_native_snapshot.py
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/test_cli.py
```
