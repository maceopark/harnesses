# OCI POLICY GUIDE

This file refines the project-root guidance for `oci/`, together with root `Dockerfile.worker`, `requirements.worker.lock`, and `wheelhouse/`.

## Rules

- Worker images must be Linux arm64 and digest-addressed; floating tags are forbidden.
- Dependency installation must be offline and hash-verified from the checked-in wheelhouse. No package-index or network fallback.
- Preserve disabled networking, read-only root filesystem, UID/GID 10001, dropped capabilities, `no-new-privileges`, pinned seccomp, resource limits, `/tmp` tmpfs, and one role-specific named volume.
- `oci/driftbench` and `oci/uv` are controlled entry surfaces; do not add arbitrary command execution or environment-dependent lookup.
- Capability and profile changes require matching launcher validation, receipt replay checks, and isolation tests.
- Never weaken policy to accommodate a local Docker setup. Preflight must reject unsupported or unbound execution.

## Verification

```sh
uv run --project measure-contract-drift python -m driftbench.worker_launcher --project-root measure-contract-drift preflight
uv run --project measure-contract-drift --extra test pytest -q measure-contract-drift/tests/test_isolation.py measure-contract-drift/tests/test_oci_role_execution.py
```
