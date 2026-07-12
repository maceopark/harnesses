"""Fail-closed OCI worker launcher for the offline benchmark image.

The Dockerfile makes immutable inputs available; this module is the runtime
boundary that turns the OCI declaration into Docker controls.  It never accepts
caller-provided mounts, environment variables, or Docker option fragments.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tomllib
from typing import Any


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_RE = re.compile(r"(?:[a-z0-9][a-z0-9./_-]*@)?sha256:[0-9a-f]{64}\Z")
_VOLUME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,62}\Z")
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_REQUIREMENT_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)==([^ ]+) --hash=sha256:([0-9a-f]{64})$")
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED_PIP_FLAGS = (
    "--no-index",
    "--find-links=/opt/driftbench/wheelhouse",
    "--require-hashes",
    "--only-binary=:all:",
)
_WORKSPACE_VOLUME_SCHEMA = "DriftbenchWorkspaceVolume.v1"
_WORKSPACE_VOLUME_OWNER = "driftbench-worker-launcher"
_WORKSPACE_VOLUME_LABEL_PREFIX = "io.driftbench.workspace."
_VOLUME_NOT_FOUND_RE = re.compile(r"\b(?:no such volume|volume .+ not found)\b", re.IGNORECASE)
_RECEIPT_REPLAY_SCHEMA = "WorkerRoleReceiptReplay.v1"




@dataclass(frozen=True)
class WorkspaceVolumeCleanupReceipt:
    schema: str
    status: str
    volume: str
    ownership_sha256: str
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "volume": self.volume,
            "ownership_sha256": self.ownership_sha256,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }
@dataclass(frozen=True)
class WorkerReceiptReplayContext:
    """Pinned inputs for deterministic, Docker-free worker receipt replay."""

    schema: str
    project_root: Path
    profile: Mapping[str, Any]
    profile_sha256: str


class WorkerReceiptReplayError(ValueError):
    """Raised when persisted OCI receipt evidence diverges from replay."""



class WorkerPreflightError(ValueError):
    """Raised before launch when an immutable isolation control is absent."""


class WorkerLaunchError(RuntimeError):
    """Raised when Docker rejects or fails an already preflighted launch."""


@dataclass(frozen=True)
class WorkerPreflightReceipt:
    schema: str
    status: str
    profile_sha256: str
    base_image: str
    wheelhouse_sha256: str
    frozen_assets: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "status": self.status,
            "profile_sha256": self.profile_sha256,
            "base_image": self.base_image,
            "wheelhouse_sha256": self.wheelhouse_sha256,
            "frozen_assets": list(self.frozen_assets),
        }


@dataclass(frozen=True)
class WorkerLaunchPlan:
    command: tuple[str, ...]
    controls: Mapping[str, object]
    profile_sha256: str
    role: str
    worker_image: str
    binding_digest: str

@dataclass(frozen=True)
class WorkerIsolationLaunchReceipt:
    schema: str
    receipt_id: str
    status: str
    profile_sha256: str
    worker_image: str
    role: str
    controls: Mapping[str, object]
    returncode: int
    binding_digest: str
    command_digest: str
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "receipt_id": self.receipt_id,
            "status": self.status,
            "profile_sha256": self.profile_sha256,
            "worker_image": self.worker_image,
            "role": self.role,
            "controls": self.controls,
            "returncode": self.returncode,
            "binding_digest": self.binding_digest,
            "command_digest": self.command_digest,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def preflight_worker_image(project_root: Path) -> WorkerPreflightReceipt:
    """Validate the pinned build inputs before a Docker build or worker launch.

    A missing or malformed base digest is an error, not a reason to substitute
    the tag recorded as provenance metadata.  The same applies to missing or
    modified wheels: the runtime never has a registry fallback.
    """

    root = project_root.resolve()
    _verify_external_holdout_release_manifest(root)
    profile_path = root / "oci" / "profile.json"
    profile_bytes = _read_bytes(profile_path, "OCI profile")
    profile = _json_object(profile_bytes, "OCI profile")
    _require(profile.get("schema") == "DriftbenchWorkerOciProfile.v2", "unsupported OCI profile schema")
    platform = _object(profile, "platform")
    _require(platform == {"os": "linux", "architecture": "arm64"}, "worker platform must be linux/arm64")

    image = _object(profile, "image")
    base = _object(image, "base")
    digest = _string(base, "digest")
    _require(_DIGEST_RE.fullmatch(digest) is not None, "base image digest must be a sha256 digest")
    reference = _string(base, "reference")
    expected_reference = f"{_string(base, 'registry')}/{_string(base, 'repository')}@{digest}"
    _require(reference == expected_reference, "base image reference must match its declared digest")
    base_platform = _object(base, "resolved_platform")
    _require(base_platform.get("os") == "linux" and base_platform.get("architecture") == "arm64", "base image must resolve to linux/arm64")
    _require("@sha256:" in reference and _string(base, "tag") == "3.14-slim", "base image must preserve tag provenance and digest pin")
    _require(image.get("entrypoint") == ["driftbench"], "worker entrypoint must be the immutable direct-argv wrapper")

    dockerfile = _read_bytes(root / _string(image, "dockerfile"), "worker Dockerfile").decode("utf-8")
    from_lines = [line.strip() for line in dockerfile.splitlines() if line.lstrip().startswith("FROM ")]
    _require(from_lines == [f"FROM --platform=linux/arm64 {reference}"], "Dockerfile must use only the declared digest-pinned base image")
    _require(all(flag in dockerfile for flag in _REQUIRED_PIP_FLAGS), "Dockerfile must perform hash-verified offline wheelhouse installation")
    _require('COPY --chown=root:root corpus/public/ ./corpus/public/' in dockerfile, "Dockerfile must copy frozen public corpus assets")
    _require('COPY --chown=root:root oci/ ./oci/' in dockerfile, "Dockerfile must copy frozen OCI assets")
    _require(
        'COPY --chown=root:root protocol/ultimateinterview/ui-native-77b0327-r4/ ./protocol/ultimateinterview/ui-native-77b0327-r4/' in dockerfile,
        "Dockerfile must copy the vendored native snapshot",
    )
    worker_wrapper = _read_bytes(root / "oci" / "driftbench", "worker command wrapper").decode("utf-8")
    _require(worker_wrapper.endswith('exec python -m driftbench.cli "$@"\n'), "worker command wrapper must preserve direct argv")
    _require("install -m 0555 /opt/driftbench/oci/driftbench /usr/local/bin/driftbench" in dockerfile, "Dockerfile must install the immutable worker command wrapper")
    _require("install -m 0555 /opt/driftbench/oci/uv /usr/local/bin/uv" in dockerfile, "Dockerfile must install the native fixture runner")
    _require("ln -sf /usr/local/bin/python /usr/bin/python3" in dockerfile and "ln -sf /usr/local/bin/uv /usr/bin/uv" in dockerfile, "Dockerfile must expose native fixture command heads outside its interpreter prefix")
    _require('ENTRYPOINT ["driftbench"]' in dockerfile, "Dockerfile entrypoint must be the immutable worker command wrapper")
    _require('COPY --chown=root:root src/ ./src/' in dockerfile and "PYTHONPATH=/opt/driftbench/src" in dockerfile, "Dockerfile must expose only the copied worker source")
    _require("USER 10001:10001" in dockerfile, "Dockerfile must set the non-root worker user")

    build = _object(profile, "build")
    _require(build.get("offline") is True, "worker build must be declared offline")
    _require(build.get("require_hashes") is True, "worker build must require hashes")
    _require(build.get("allow_source_distributions") is False, "worker build must reject source distributions")
    lock_bytes = _read_bytes(root / _string(build, "lockfile"), "worker dependency lock")
    uv_lock_bytes = _read_bytes(root / _string(build, "uv_lockfile"), "uv lock")
    _verify_lock_binding(lock_bytes, uv_lock_bytes)
    wheels = _verify_wheelhouse(root, _string(build, "wheelhouse"), _string(build, "wheelhouse_manifest"), lock_bytes)

    frozen_assets = _array(profile, "frozen_assets")
    asset_sources: list[str] = []
    for asset in frozen_assets:
        _require(isinstance(asset, dict), "frozen asset declaration must be an object")
        source = _string(asset, "source")
        destination = _string(asset, "destination")
        _require(
            source in {"corpus/public", "oci", "protocol/ultimateinterview/ui-native-77b0327-r4"},
            "only declared public corpus, OCI policy, and vendored native assets may enter the image",
        )
        _require(destination.startswith("/opt/driftbench/"), "frozen asset destination must be under /opt/driftbench")
        _require(asset.get("read_only") is True, "frozen assets must be read-only")
        _require((root / source).is_dir(), f"frozen asset source is missing: {source}")
        asset_sources.append(source)
    _require(
        set(asset_sources) == {"corpus/public", "oci", "protocol/ultimateinterview/ui-native-77b0327-r4"},
        "profile must freeze public corpus, OCI policy, and vendored native assets",
    )

    runtime = _object(profile, "runtime")
    _require(runtime.get("read_only_root_filesystem") is True, "worker root filesystem must be read-only")
    network = _object(runtime, "network")
    _require(network == {"mode": "none", "allow_host_network": False, "allow_dns": False}, "worker network must be disabled")
    privileges = _object(runtime, "privileges")
    _require(privileges.get("allow_privileged") is False and privileges.get("no_new_privileges") is True, "privilege escalation must be disabled")
    capabilities = _object(privileges, "capabilities")
    _require(capabilities == {"drop": ["ALL"], "add": []}, "all Linux capabilities must be dropped")
    seccomp = _object(privileges, "seccomp")
    seccomp_path = root / _string(seccomp, "profile")
    seccomp_bytes = _read_bytes(seccomp_path, "seccomp profile")
    _require(seccomp.get("required") is True, "seccomp profile must be required")
    _require(seccomp.get("sha256") == sha256(seccomp_bytes).hexdigest(), "seccomp profile digest mismatch")
    seccomp_json = _json_object(seccomp_bytes, "seccomp profile")
    _require(seccomp_json.get("defaultAction") == "SCMP_ACT_ERRNO", "seccomp must default-deny syscalls")
    _require(not _seccomp_allows_socket(seccomp_json), "seccomp profile must not allow socket syscalls")

    mounts = _object(runtime, "mount_policy")
    _require(all(mounts.get(key) is False for key in ("allow_bind_mounts", "allow_host_home", "allow_socket_mounts", "allow_private_corpus", "allow_additional_mounts")), "host and extra mounts must be denied")
    _require(mounts.get("allowed_mount_types") == ["tmpfs", "named-volume"], "only tmpfs and named-volume mounts are allowed")
    _verify_workspace_policy(root, mounts)
    _verify_resources(_object(runtime, "resources"))
    _verify_role_capabilities(root, _string(mounts, "role_capabilities"))
    receipt_policy = _object(profile, "receipt")
    _require(
        receipt_policy == {
            "schema": "WorkerIsolationLaunchReceipt.v1",
            "required_controls": [
                "network",
                "read_only_root_filesystem",
                "nonroot_user",
                "capabilities",
                "no_new_privileges",
                "seccomp",
                "resources",
                "mounts",
            ],
        },
        "worker receipt policy is not immutable",
    )

    return WorkerPreflightReceipt(
        schema="WorkerImagePreflightReceipt.v1",
        status="passed",
        profile_sha256=sha256(profile_bytes).hexdigest(),
        base_image=reference,
        wheelhouse_sha256=wheels,
        frozen_assets=tuple(sorted(asset_sources)),
    )


def build_worker_launch_plan(
    project_root: Path,
    *,
    role: str,
    worker_image: str,
    binding_digest: str,
    argv: Sequence[str] = (),
    workspace_volume: str | None = None,
    docker_binary: str = "docker",
    stdin_open: bool = False,
) -> WorkerLaunchPlan:
    """Create a direct Docker argv with every declared isolation control applied."""

    root = project_root.resolve()
    receipt = preflight_worker_image(root)
    profile = _json_object(_read_bytes(root / "oci" / "profile.json", "OCI profile"), "OCI profile")
    return _build_worker_launch_plan(
        root,
        profile=profile,
        profile_sha256=receipt.profile_sha256,
        role=role,
        worker_image=worker_image,
        binding_digest=binding_digest,
        argv=argv,
        workspace_volume=workspace_volume,
        docker_binary=docker_binary,
        stdin_open=stdin_open,
    )


def _build_worker_launch_plan(
    root: Path,
    *,
    profile: Mapping[str, Any],
    profile_sha256: str,
    role: str,
    worker_image: str,
    binding_digest: str,
    argv: Sequence[str],
    workspace_volume: str | None,
    docker_binary: str,
    stdin_open: bool,
) -> WorkerLaunchPlan:
    _require(_IMAGE_RE.fullmatch(worker_image) is not None, "worker image must be referenced by digest")
    _require(_safe_argument(docker_binary), "docker binary is invalid")
    _require(all(_safe_argument(item) for item in argv), "worker command arguments must be direct non-empty argv values")
    _require(_SHA256_HEX_RE.fullmatch(binding_digest) is not None, "worker launch binding must be a SHA-256 digest")

    runtime = _object(profile, "runtime")
    mounts = _object(runtime, "mount_policy")
    role_root, access = _role_root(root, _string(mounts, "role_capabilities"), role)
    workspace = _object(mounts, "workspace")
    prefix = _string(workspace, "source_prefix")
    volume = workspace_volume or f"{prefix}{role}"
    _require(_VOLUME_RE.fullmatch(volume) is not None and volume.startswith(prefix), "workspace must be a launcher-managed named volume")
    destination = f"{_string(workspace, 'destination_prefix')}{role}"
    _require(destination == role_root, "role workspace mount does not match capability root")

    user = _object(_object(profile, "image"), "user")
    seccomp = _object(_object(runtime, "privileges"), "seccomp")
    resources = _object(runtime, "resources")
    cpu = _object(resources, "cpu_max")
    nofile = _object(_object(resources, "ulimits"), "nofile")
    tmpfs = _array(mounts, "tmpfs")
    _require(len(tmpfs) == 1 and isinstance(tmpfs[0], dict), "exactly one /tmp tmpfs is required")
    tmp = tmpfs[0]
    _require(tmp.get("destination") == "/tmp", "tmpfs must mount at /tmp")
    tmp_options = ["rw", *_string_list(tmp, "options"), f"size={tmp['size_bytes']}", f"mode={tmp['mode']}"]
    workspace_mount = f"type=volume,src={volume},dst={destination}"
    if workspace.get("copy_data") is False:
        workspace_mount += ",volume-nocopy"
    if access == "read-only":
        workspace_mount += ",readonly"

    command = (
        docker_binary,
        "run",
        "--rm",
        *(("-i",) if stdin_open else ()),
        "--network",
        "none",
        "--read-only",
        "--user",
        f"{user['uid']}:{user['gid']}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--security-opt",
        f"seccomp={root / _string(seccomp, 'profile')}",
        "--pids-limit",
        str(resources["pids_max"]),
        "--memory",
        str(resources["memory_bytes"]),
        "--cpu-period",
        str(cpu["period_us"]),
        "--cpu-quota",
        str(cpu["quota_us"]),
        "--ulimit",
        f"nofile={nofile['soft']}:{nofile['hard']}",
        "--tmpfs",
        f"/tmp:{','.join(tmp_options)}",
        "--mount",
        workspace_mount,
        "--workdir",
        destination,
        worker_image,
        *argv,
    )
    controls: dict[str, object] = {
        "network": {"mode": "none", "host_network": False, "dns": False},
        "read_only_root_filesystem": True,
        "nonroot_user": f"{user['uid']}:{user['gid']}",
        "capabilities": {"drop": ["ALL"], "add": []},
        "no_new_privileges": True,
        "seccomp": {"profile": _string(seccomp, "profile"), "sha256": _string(seccomp, "sha256")},
        "resources": {"pids_max": resources["pids_max"], "memory_bytes": resources["memory_bytes"], "cpu_max": cpu, "nofile": nofile},
        "mounts": [{"type": "tmpfs", "destination": "/tmp", "options": tmp_options}, {"type": "named-volume", "source": volume, "destination": destination, "read_only": access == "read-only", "copy_data": workspace["copy_data"]}],
    }
    return WorkerLaunchPlan(
        command=command,
        controls=controls,
        profile_sha256=profile_sha256,
        role=role,
        worker_image=worker_image,
        binding_digest=binding_digest,
    )


def workspace_volume_name(
    *,
    role: str,
    binding_digest: str,
    input_digest: str,
) -> str:
    _require(_SHA256_HEX_RE.fullmatch(binding_digest) is not None, "worker launch binding must be a SHA-256 digest")
    _require(_SHA256_HEX_RE.fullmatch(input_digest) is not None, "worker input digest must be a SHA-256 digest")
    volume = f"driftbench-workspace-{role}-{binding_digest[:12]}-{input_digest[:12]}"
    _require(_VOLUME_RE.fullmatch(volume) is not None, "workspace volume name is invalid")
    return volume


def build_worker_receipt_replay_context(project_root: Path) -> WorkerReceiptReplayContext:
    """Load immutable replay inputs without invoking Docker."""

    root = project_root.resolve()
    preflight = preflight_worker_image(root)
    profile_bytes = _read_bytes(root / "oci" / "profile.json", "OCI profile")
    if sha256(profile_bytes).hexdigest() != preflight.profile_sha256:
        raise WorkerPreflightError("OCI profile changed during receipt replay preflight")
    profile = _json_object(profile_bytes, "OCI profile")
    return WorkerReceiptReplayContext(
        schema=_RECEIPT_REPLAY_SCHEMA,
        project_root=root,
        profile=profile,
        profile_sha256=preflight.profile_sha256,
    )


def replay_worker_role_receipts(
    context: WorkerReceiptReplayContext,
    *,
    role: str,
    worker_image: str,
    binding_digest: str,
    input_digest: str,
    output_read_stdout: str,
) -> dict[str, dict[str, object]]:
    """Reconstruct all OCI phase and cleanup receipts without invoking Docker."""

    if context.schema != _RECEIPT_REPLAY_SCHEMA:
        raise WorkerReceiptReplayError("unsupported worker receipt replay schema")
    if not isinstance(output_read_stdout, str):
        raise WorkerReceiptReplayError("worker output replay requires textual stdout")
    volume = workspace_volume_name(
        role=role,
        binding_digest=binding_digest,
        input_digest=input_digest,
    )
    phases = (
        ("input_stage", ("worker-stage", "--input-digest", input_digest), True, ""),
        ("isolation_launch", ("worker-role", "--role", role, "--input-digest", input_digest), False, ""),
        ("output_read", ("worker-read-output", "--input-digest", input_digest), False, output_read_stdout),
    )
    expected: dict[str, dict[str, object]] = {}
    for name, argv, stdin_open, stdout in phases:
        plan = _build_worker_launch_plan(
            context.project_root,
            profile=context.profile,
            profile_sha256=context.profile_sha256,
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
            argv=argv,
            workspace_volume=volume,
            docker_binary="docker",
            stdin_open=stdin_open,
        )
        expected[name] = _completed_launch_receipt(plan, stdout=stdout, stderr="")
    ownership = _workspace_volume_ownership(
        role=role,
        binding_digest=binding_digest,
        input_digest=input_digest,
        worker_image=worker_image,
    )
    expected["workspace_cleanup"] = {
        "schema": "WorkspaceVolumeCleanupReceipt.v1",
        "status": "removed",
        "volume": volume,
        "ownership_sha256": ownership.sha256,
        "returncode": 0,
        "stdout": f"{volume}\n",
        "stderr": "",
    }
    return expected


def validate_worker_role_receipt_replay(
    context: WorkerReceiptReplayContext,
    *,
    role: str,
    worker_image: str,
    binding_digest: str,
    input_digest: str,
    output_read_stdout: str,
    receipts: Mapping[str, object],
) -> None:
    """Require exact agreement with the versioned, deterministic receipt replay."""

    expected = replay_worker_role_receipts(
        context,
        role=role,
        worker_image=worker_image,
        binding_digest=binding_digest,
        input_digest=input_digest,
        output_read_stdout=output_read_stdout,
    )
    if set(receipts) != set(expected):
        raise WorkerReceiptReplayError("OCI receipt phases do not close over the replay contract")
    for name, expected_receipt in expected.items():
        actual = receipts.get(name)
        if not isinstance(actual, Mapping) or dict(actual) != expected_receipt:
            raise WorkerReceiptReplayError(f"OCI {name} receipt diverges from deterministic replay")
def create_workspace_volume(
    project_root: Path,
    *,
    role: str,
    binding_digest: str,
    input_digest: str,
    worker_image: str,
    docker_binary: str = "docker",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Create a fresh volume, removing only a provably owned stale predecessor."""

    root = project_root.resolve()
    preflight_worker_image(root)
    _require(_IMAGE_RE.fullmatch(worker_image) is not None, "worker image must be referenced by digest")
    _require(_safe_argument(docker_binary), "docker binary is invalid")
    profile = _json_object(_read_bytes(root / "oci" / "profile.json", "OCI profile"), "OCI profile")
    mounts = _object(_object(profile, "runtime"), "mount_policy")
    _role_root(root, _string(mounts, "role_capabilities"), role)

    volume = workspace_volume_name(
        role=role,
        binding_digest=binding_digest,
        input_digest=input_digest,
    )
    ownership = _workspace_volume_ownership(
        role=role,
        binding_digest=binding_digest,
        input_digest=input_digest,
        worker_image=worker_image,
    )
    existing = _inspect_workspace_volume(volume, docker_binary=docker_binary, runner=runner)
    if existing is not None:
        if existing != ownership.labels:
            raise WorkerLaunchError("workspace volume is foreign, unlabeled, or owned by another invocation")
        _remove_owned_workspace_volume(
            volume,
            ownership=ownership,
            docker_binary=docker_binary,
            runner=runner,
        )

    try:
        result = runner(
            [
                docker_binary,
                "volume",
                "create",
                *(f"--label={key}={value}" for key, value in ownership.labels.items()),
                volume,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise WorkerLaunchError(f"worker volume could not be created: {error}") from error
    if result.returncode != 0:
        raise WorkerLaunchError(
            f"worker volume creation was rejected by Docker (exit {result.returncode}): {result.stderr.strip()}"
        )
    created = _inspect_workspace_volume(volume, docker_binary=docker_binary, runner=runner)
    if created != ownership.labels:
        raise WorkerLaunchError("created workspace volume ownership labels do not match this invocation")
    return volume


def remove_workspace_volume(
    volume: str,
    *,
    role: str,
    binding_digest: str,
    input_digest: str,
    worker_image: str,
    docker_binary: str = "docker",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> WorkspaceVolumeCleanupReceipt:
    """Remove only a validated workspace volume owned by this exact invocation."""

    _require(
        _VOLUME_RE.fullmatch(volume) is not None and volume.startswith("driftbench-workspace-"),
        "workspace must be a launcher-managed named volume",
    )
    _require(_SHA256_HEX_RE.fullmatch(binding_digest) is not None, "worker launch binding must be a SHA-256 digest")
    _require(_SHA256_HEX_RE.fullmatch(input_digest) is not None, "worker input digest must be a SHA-256 digest")
    _require(_IMAGE_RE.fullmatch(worker_image) is not None, "worker image must be referenced by digest")
    _require(_safe_argument(docker_binary), "docker binary is invalid")
    ownership = _workspace_volume_ownership(
        role=role,
        binding_digest=binding_digest,
        input_digest=input_digest,
        worker_image=worker_image,
    )
    return _remove_owned_workspace_volume(
        volume,
        ownership=ownership,
        docker_binary=docker_binary,
        runner=runner,
    )




@dataclass(frozen=True)
class _WorkspaceVolumeOwnership:
    labels: Mapping[str, str]
    sha256: str


def _workspace_volume_ownership(
    *,
    role: str,
    binding_digest: str,
    input_digest: str,
    worker_image: str,
) -> _WorkspaceVolumeOwnership:
    labels = {
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}owner": _WORKSPACE_VOLUME_OWNER,
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}schema": _WORKSPACE_VOLUME_SCHEMA,
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}role": role,
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}binding-sha256": binding_digest,
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}input-sha256": input_digest,
        f"{_WORKSPACE_VOLUME_LABEL_PREFIX}worker-image": worker_image,
    }
    ownership_sha256 = sha256(_canonical_bytes(labels)).hexdigest()
    labels[f"{_WORKSPACE_VOLUME_LABEL_PREFIX}ownership-sha256"] = ownership_sha256
    return _WorkspaceVolumeOwnership(labels=labels, sha256=ownership_sha256)


def _inspect_workspace_volume(
    volume: str,
    *,
    docker_binary: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, str] | None:
    try:
        result = runner(
            [docker_binary, "volume", "inspect", volume],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise WorkerLaunchError(f"worker volume could not be inspected: {error}") from error
    if result.returncode != 0:
        if _VOLUME_NOT_FOUND_RE.search(result.stderr) is not None:
            return None
        raise WorkerLaunchError(
            f"worker volume inspection was rejected by Docker (exit {result.returncode}): {result.stderr.strip()}"
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise WorkerLaunchError("worker volume inspection returned invalid JSON") from error
    if (
        not isinstance(document, list)
        or len(document) != 1
        or not isinstance(document[0], dict)
        or document[0].get("Name") != volume
    ):
        raise WorkerLaunchError("worker volume inspection did not identify the requested volume")
    labels = document[0].get("Labels")
    if not isinstance(labels, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in labels.items()):
        raise WorkerLaunchError("worker volume inspection returned invalid ownership labels")
    return dict(labels)


def _remove_owned_workspace_volume(
    volume: str,
    *,
    ownership: _WorkspaceVolumeOwnership,
    docker_binary: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> WorkspaceVolumeCleanupReceipt:
    labels = _inspect_workspace_volume(volume, docker_binary=docker_binary, runner=runner)
    if labels is None:
        raise WorkerLaunchError("workspace volume disappeared before ownership validation")
    if labels != ownership.labels:
        raise WorkerLaunchError("workspace volume is foreign, unlabeled, or owned by another invocation")
    try:
        result = runner(
            [docker_binary, "volume", "rm", volume],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise WorkerLaunchError(f"worker volume could not be removed: {error}") from error
    if result.returncode != 0:
        raise WorkerLaunchError(
            f"worker volume removal was rejected by Docker (exit {result.returncode}): {result.stderr.strip()}"
        )
    return WorkspaceVolumeCleanupReceipt(
        schema="WorkspaceVolumeCleanupReceipt.v1",
        status="removed",
        volume=volume,
        ownership_sha256=ownership.sha256,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )

def _completed_launch_receipt(
    plan: WorkerLaunchPlan,
    *,
    stdout: str,
    stderr: str,
) -> dict[str, object]:
    command_digest = sha256(_canonical_bytes({"command": plan.command})).hexdigest()
    receipt_id = "workeriso-" + sha256(
        _canonical_bytes(
            {
                "profile": plan.profile_sha256,
                "image": plan.worker_image,
                "role": plan.role,
                "command_digest": command_digest,
                "binding_digest": plan.binding_digest,
            }
        )
    ).hexdigest()[:23]
    return {
        "schema": "WorkerIsolationLaunchReceipt.v1",
        "receipt_id": receipt_id,
        "status": "completed",
        "profile_sha256": plan.profile_sha256,
        "worker_image": plan.worker_image,
        "role": plan.role,
        "controls": plan.controls,
        "returncode": 0,
        "binding_digest": plan.binding_digest,
        "command_digest": command_digest,
        "stdout": stdout,
        "stderr": stderr,
    }


def launch_worker(
    plan: WorkerLaunchPlan,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    input_text: str | None = None,
) -> WorkerIsolationLaunchReceipt:
    """Run a preflighted plan and return a receipt only after Docker succeeds."""

    try:
        result = runner(list(plan.command), check=False, capture_output=True, text=True, input=input_text)
    except OSError as error:
        raise WorkerLaunchError(f"worker launcher could not execute Docker: {error}") from error
    if result.returncode != 0:
        raise WorkerLaunchError(f"worker launcher rejected by Docker (exit {result.returncode}): {result.stderr.strip()}")
    return WorkerIsolationLaunchReceipt(
        **_completed_launch_receipt(
            plan,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    )


def _verify_lock_binding(requirements: bytes, uv_lock: bytes) -> None:
    try:
        document = tomllib.loads(uv_lock.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise WorkerPreflightError("uv lock is not valid TOML") from error
    packages = document.get("package")
    _require(isinstance(packages, list), "uv lock has no package list")
    resolved: dict[str, tuple[str, set[str]]] = {}
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        wheels = package.get("wheels")
        if not isinstance(name, str) or not isinstance(version, str) or not isinstance(wheels, list):
            continue
        hashes = {wheel.get("hash", "").removeprefix("sha256:") for wheel in wheels if isinstance(wheel, dict)}
        resolved[name] = (version, hashes)
    for line in requirements.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT_RE.fullmatch(line)
        _require(match is not None, "worker dependency lock must contain only pinned hash requirements")
        name, version, digest = match.groups()
        _require(name in resolved, f"worker dependency is absent from uv lock: {name}")
        locked_version, locked_hashes = resolved[name]
        _require(version == locked_version and digest in locked_hashes, f"worker dependency lock diverges from uv lock: {name}")

def _verify_wheelhouse(root: Path, wheelhouse_name: str, manifest_name: str, lock_bytes: bytes) -> str:
    wheelhouse = root / wheelhouse_name
    manifest_bytes = _read_bytes(root / manifest_name, "wheelhouse manifest")
    manifest = _json_object(manifest_bytes, "wheelhouse manifest")
    _require(manifest.get("schema") == "DriftbenchWorkerWheelhouse.v1", "unsupported wheelhouse manifest schema")
    _require(_object(manifest, "platform") == {"os": "linux", "architecture": "arm64", "python_abi": "cp314"}, "wheelhouse must target Linux arm64 CPython 3.14")
    manifest_wheels = _array(manifest, "wheels")
    expected: set[str] = set()
    hashes: set[str] = set()
    for item in manifest_wheels:
        _require(isinstance(item, dict), "wheel manifest entry must be an object")
        name = _string(item, "path")
        _require(Path(name).name == name and name.endswith(".whl"), "wheel manifest paths must name wheel files")
        expected.add(name)
        wheel = wheelhouse / name
        contents = _read_bytes(wheel, f"wheel {name}")
        _require(item.get("size") == len(contents), f"wheel size mismatch: {name}")
        digest = sha256(contents).hexdigest()
        _require(item.get("sha256") == digest, f"wheel digest mismatch: {name}")
        hashes.add(digest)
    actual = {path.name for path in wheelhouse.glob("*.whl") if path.is_file()}
    _require(actual == expected and expected, "wheelhouse contents must exactly match the manifest")
    lock_hashes = set(_HASH_RE.findall(lock_bytes.decode("utf-8")))
    _require(lock_hashes and lock_hashes <= hashes, "dependency lock hashes must all be present in the wheelhouse")
    return sha256(manifest_bytes).hexdigest()


def _verify_external_holdout_release_manifest(root: Path) -> None:
    manifest = _json_object(
        _read_bytes(root / "corpus" / "external-holdout" / "service-manifest.template.json", "external holdout service manifest"),
        "external holdout service manifest",
    )
    _require(
        manifest.get("schema") == "DriftBenchExternalHoldoutServiceManifestTemplate.v1",
        "unsupported external holdout service manifest schema",
    )
    _require(
        manifest.get("provisioning") == "external-only" and manifest.get("repository_content") == "none",
        "external holdout manifest must remain repository-free",
    )
    _require(
        _object(manifest, "boundary_requirements")
        == {
            "local_controller_access": False,
            "worker_image_access": False,
            "repository_mount": False,
            "holdout_payload": "externally-provisioned",
        },
        "external holdout boundary requirements are not immutable",
    )
    release = _object(manifest, "frozen_release")
    _require(release.get("schema") == "DriftBenchFrozenReleaseMetadata.v1", "unsupported frozen release metadata schema")
    _require(
        release.get("dev_case_count") == 6
        and release.get("holdout_case_count") == 4
        and release.get("total_case_count") == 10,
        "frozen release must bind exactly six development and four holdout cases",
    )
    for field in ("frozen_release_digest", "opaque_record_set_digest"):
        value = release.get(field)
        _require(isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None, f"{field} must be a sha256 digest")
    signature = _object(release, "signature")
    _require(
        signature
        == {
            "algorithm": "ed25519",
            "key_id": "external-holdout-release-key-v1",
            "value": "EXTERNAL-PROVISIONER-SIGNATURE-REQUIRED",
        },
        "external holdout signature placeholder is not immutable",
    )
    attestation = _object(release, "attestation")
    _require(
        attestation
        == {
            "schema": "DriftBenchExternalHoldoutReleaseAttestation.v1",
            "status": "required",
            "value": "EXTERNAL-PROVISIONER-ATTESTATION-REQUIRED",
        },
        "external holdout attestation placeholder is not immutable",
    )

def _verify_workspace_policy(root: Path, mounts: Mapping[str, Any]) -> None:
    workspace = _object(mounts, "workspace")
    _require(workspace == {"type": "named-volume", "source_prefix": "driftbench-workspace-", "destination_prefix": "/workspace/", "copy_data": True}, "workspace mount policy is not immutable")
    tmpfs = _array(mounts, "tmpfs")
    _require(tmpfs == [{"destination": "/tmp", "size_bytes": 67108864, "mode": "1777", "options": ["noexec", "nodev", "nosuid"]}], "tmpfs policy is not immutable")
    role_file = root / _string(mounts, "role_capabilities")
    _require(role_file.is_file(), "role capability policy is missing")


def _verify_resources(resources: Mapping[str, Any]) -> None:
    _require(resources.get("pids_max") == 64 and resources.get("memory_bytes") == 536870912, "worker pids and memory limits are not immutable")
    _require(_object(resources, "cpu_max") == {"quota_us": 100000, "period_us": 100000}, "worker CPU limit is not immutable")
    _require(_object(_object(resources, "ulimits"), "nofile") == {"soft": 1024, "hard": 1024}, "worker nofile limit is not immutable")


def _verify_role_capabilities(root: Path, relative_path: str) -> None:
    capabilities = _json_object(_read_bytes(root / relative_path, "role capability policy"), "role capability policy")
    policy = _object(capabilities, "default_policy")
    _require(policy.get("allow_network") is False and policy.get("allow_credentials") is False, "roles must deny network and credentials")
    _require(policy.get("allow_shell") is False and policy.get("allow_environment_overrides") is False, "roles must use direct argv without environment overrides")
    roles = _object(capabilities, "roles")
    _require(set(roles) == {"planner", "implementer", "observation", "postmortem"}, "unexpected worker role capability declaration")
    for role in ("planner", "implementer", "observation", "postmortem"):
        roots = _array(_object(roles, role), "roots")
        _require(roots == [{"path": f"/workspace/{role}", "access": "read-write", "allow_symlinks": False}], f"invalid {role} workspace policy")


def _role_root(root: Path, relative_path: str, role: str) -> tuple[str, str]:
    capabilities = _json_object(_read_bytes(root / relative_path, "role capability policy"), "role capability policy")
    roles = _object(capabilities, "roles")
    _require(role in roles, "worker role is not declared")
    roots = _array(_object(roles, role), "roots")
    _require(len(roots) == 1 and isinstance(roots[0], dict), "worker role must have exactly one workspace root")
    return _string(roots[0], "path"), _string(roots[0], "access")


def _seccomp_allows_socket(profile: Mapping[str, Any]) -> bool:
    for syscall in _array(profile, "syscalls"):
        if isinstance(syscall, dict) and syscall.get("action") == "SCMP_ACT_ALLOW" and "socket" in syscall.get("names", []):
            return True
    return False


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise WorkerPreflightError(f"{label} is unavailable: {path}") from error


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkerPreflightError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise WorkerPreflightError(f"{label} must be a JSON object")
    return value


def _object(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise WorkerPreflightError(f"{key} must be an object")
    return item


def _array(value: Mapping[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise WorkerPreflightError(f"{key} must be an array")
    return item


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise WorkerPreflightError(f"{key} must be a non-empty string")
    return item


def _string_list(value: Mapping[str, Any], key: str) -> list[str]:
    item = _array(value, key)
    if not all(isinstance(part, str) and part for part in item):
        raise WorkerPreflightError(f"{key} must be an array of non-empty strings")
    return list(item)


def _safe_argument(value: str) -> bool:
    return bool(value) and "\x00" not in value and "\n" not in value and "\r" not in value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkerPreflightError(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="driftbench-worker-launcher")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    launch = commands.add_parser("launch")
    launch.add_argument("--role", required=True)
    launch.add_argument("--image", required=True)
    launch.add_argument("--workspace-volume")
    launch.add_argument("--binding-digest", required=True)
    launch.add_argument("worker_argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            print(json.dumps(preflight_worker_image(args.project_root).to_dict(), sort_keys=True))
        else:
            receipt = launch_worker(build_worker_launch_plan(args.project_root, role=args.role, worker_image=args.image, binding_digest=args.binding_digest, workspace_volume=args.workspace_volume, argv=args.worker_argv))
            print(json.dumps(receipt.to_dict(), sort_keys=True))
    except (WorkerPreflightError, WorkerLaunchError) as error:
        print(json.dumps({"schema": "WorkerIsolationLaunchReceipt.v1", "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
