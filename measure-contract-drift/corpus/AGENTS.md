# CORPUS GUIDE

This file refines the project-root guidance for `corpus/`.

## Boundaries

- `public/`: six fixed development cases, manifest, and clean executable starter trees.
- `external-holdout/`: public-safe provisioning contract only; no private prompts or starters.
- `trusted-private-fixtures/`: local trust-boundary fixtures for tests, not study holdout data and not public effectiveness evidence.

## Rules

- Keep case IDs, opaque tokens, expected commands, persistence boundaries, starter paths, and tree digests mutually consistent.
- Public starters must be minimal, deterministic, offline, and independently executable from a clean copy.
- Do not expose private holdout content, credentials, evaluator answers, or data that permits optimization against holdouts.
- Do not relabel trusted test fixtures as holdout evidence.
- Corpus or starter changes require manifest/digest updates through the canonical project code and coverage in corpus/starter tests.
- Preserve exact typed behavior expectations; broadening an obligation is a semantic contract change, not fixture cleanup.

## Verification

```sh
uv run --project measure-contract-drift driftbench validate-corpus --public-root measure-contract-drift/corpus/public --partition dev
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/test_public_starter_execution.py
```
