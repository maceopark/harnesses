# Ultimateinterview Contract Drift Benchmark

A deterministic, fail-closed benchmark for measuring drift between an interview-produced handoff/Build Contract and a fresh implementation context.
Conceptual guides: [English](USER_GUIDE.en.md) · [한국어](USER_GUIDE.ko.md)

## One-line deterministic development run

From the workspace root:

```sh
benchmark/ultimateinterview-contract-drift/scripts/run-fake.sh
```

The hermetic `fake-dev` run creates and validates planner handoff, Build Contract, implementation, observation, and postmortem artifacts across declared fresh-context transfers. Its scorecard is deterministic development-treatment evidence only: it never calls a model, never accesses holdout data, and never claims live benchmark effectiveness.

## Commands

```sh
uv run --project benchmark/ultimateinterview-contract-drift driftbench validate-corpus --public-root benchmark/ultimateinterview-contract-drift/corpus/public --partition dev
uv run --project benchmark/ultimateinterview-contract-drift --extra test pytest -q benchmark/ultimateinterview-contract-drift/tests
```
## Offline worker isolation

`Dockerfile.worker` uses the Linux arm64 digest declared in `oci/profile.json`; it
does not accept a floating base tag. Its dependencies are installed from the
hash-verified `requirements.worker.lock` and checked-in `wheelhouse/`, with no
package-index fallback. The image contains only worker source, public corpus,
OCI policy assets, and the vendored native v1 snapshot required by the canonical
structural fixture.

Before building or launching a worker, run:

```sh
uv run --project benchmark/ultimateinterview-contract-drift python -m driftbench.worker_launcher --project-root benchmark/ultimateinterview-contract-drift preflight
```

The launcher requires a digest-addressed worker image and creates direct Docker
arguments for disabled networking, a read-only root filesystem, UID/GID 10001,
dropped capabilities, no-new-privileges, the pinned seccomp policy, resource
limits, and only `/tmp` tmpfs plus the role-specific named volume. A successful
launch returns a `WorkerIsolationLaunchReceipt.v1`; rejected preflight never
falls back to a tag, registry install, bind mount, or extra runtime option.
Each planner, implementer, observation, and postmortem invocation receives one
canonical digest-bound closure through a launcher-managed named volume, emits
one canonical volume output, and is validated by the controller before its
projected lifecycle artifact is accepted. Implementers materialize the public
starter in their own volume; the independent observation role materializes and
executes its own copy. OCI execution is authoritative for this deterministic
development lifecycle, not evidence of live provider or holdout performance.

Scored arms are `direct-v1`, `plan-v1`, and `ultimateinterview-current-v1-structural`. The native full-v2 path is excluded from scoring because the pinned protocol has no creditable execution receipt; it may only be represented as an expected-fail conformance fixture.

Local controller commands reject holdout scoring. Private evaluator, simulator, and reporter services must be provisioned separately before any live or holdout study.
