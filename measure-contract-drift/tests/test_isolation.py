from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from driftbench import cli

from driftbench.artifacts import (
    ArtifactValidationError,
    build_artifact_manifest,
    validate_artifact_manifest,
)
from driftbench.redaction import REDACTION_MARKER, redact, scan_sentinels
from driftbench.tools import ReadRequest, ToolRequestError, validate_tool_request
from driftbench.worker import WorkerRole, WorkerSessionError, fresh_role_context, transferred_artifacts
from driftbench.worker_launcher import (
    WorkerPreflightError,
    WorkerLaunchError,
    build_worker_launch_plan,
    create_workspace_volume,
    launch_worker,
    remove_workspace_volume,
    preflight_worker_image,
)


def _roots(root: Path) -> dict[str, Path]:
    return {"planner": root, "implementer": root, "postmortem": root}


def test_role_root_rejects_traversal_and_unauthorized_write(tmp_path: Path) -> None:
    with pytest.raises(ToolRequestError, match="path"):
        validate_tool_request("planner", {"tool": "read", "path": "../outside.txt"}, _roots(tmp_path))
    with pytest.raises(ToolRequestError, match="may not invoke"):
        validate_tool_request(
            "planner",
            {"tool": "write_patch", "path": "src/app.py", "patch": "safe patch"},
            _roots(tmp_path),
        )


def test_run_rejects_shell_syntax_and_environment_override(tmp_path: Path) -> None:
    with pytest.raises(ToolRequestError, match="shell"):
        validate_tool_request(
            "implementer",
            {"tool": "run", "argv": ["pytest", "tests;rm"]},
            _roots(tmp_path),
        )
    with pytest.raises(ToolRequestError, match="forbidden request field"):
        validate_tool_request(
            "implementer",
            {"tool": "run", "argv": ["pytest"], "env": {"PYTHONPATH": "/tmp"}},
            _roots(tmp_path),
        )
    with pytest.raises(ToolRequestError, match="environment overrides"):
        validate_tool_request(
            "implementer",
            {"tool": "run", "argv": ["PYTHONPATH=/tmp", "pytest"]},
            _roots(tmp_path),
        )
def test_fresh_role_context_rejects_undeclared_artifact_input() -> None:
    input_document = {"schema": "CellInput.v2", "cell_id": "cell-example"}
    context = fresh_role_context(
        WorkerRole.PLANNER,
        "planner-example",
        {"cell-input": ("input.json", input_document)},
    )

    with pytest.raises(WorkerSessionError, match="undeclared or missing"):
        transferred_artifacts(
            context,
            {
                "cell-input": input_document,
                "private-score": {"score": 1},
            },
        )



def test_validated_paths_remain_under_role_root(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    request = validate_tool_request("planner", {"tool": "read", "path": "src/app.py"}, _roots(tmp_path))
    assert isinstance(request, ReadRequest)
    assert request.path == "src/app.py"


def test_artifact_manifest_rejects_symlink_special_and_hardlinked_files(tmp_path: Path) -> None:
    (tmp_path / "result.txt").write_text("complete", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path)
    assert manifest.entries[0].size == len("complete")
    assert validate_artifact_manifest(tmp_path, manifest) == manifest

    (tmp_path / "link.txt").symlink_to(tmp_path / "result.txt")
    with pytest.raises(ArtifactValidationError, match="symlink"):
        build_artifact_manifest(tmp_path)
    (tmp_path / "link.txt").unlink()

    os.link(tmp_path / "result.txt", tmp_path / "hard-link.txt")
    with pytest.raises(ArtifactValidationError, match="hard link"):
        build_artifact_manifest(tmp_path)
    (tmp_path / "hard-link.txt").unlink()

    os.mkfifo(tmp_path / "artifact.pipe")
    with pytest.raises(ArtifactValidationError, match="regular file"):
        build_artifact_manifest(tmp_path)


def test_recursive_redaction_removes_nested_sentinels() -> None:
    sentinel = "PRIVATE-SENTINEL-8f14e45f"
    value = {"metadata": {"token": sentinel}, "events": [f"before {sentinel} after"]}

    assert scan_sentinels(value, [sentinel])
    public_value = redact(value, [sentinel])
    assert public_value["metadata"]["token"] == REDACTION_MARKER
    assert public_value["events"][0] == f"before {REDACTION_MARKER} after"
    assert scan_sentinels(public_value, [sentinel]) == ()


def test_expected_fail_v2_is_excluded_from_scored_arm_allowlist() -> None:
    arms_path = Path(__file__).parents[1] / "arms" / "arms.json"
    payload = json.loads(arms_path.read_text(encoding="utf-8"))

    arms = {arm["arm_id"]: arm for arm in payload["arms"]}
    scored = {arm_id for arm_id, arm in arms.items() if arm["scored"]}
    v2 = arms["ultimateinterview-full-v2-expected-fail"]
    assert v2 == {
        "arm_id": "ultimateinterview-full-v2-expected-fail",
        "scored": False,
        "expected_failure": True,
    }
    assert "ultimateinterview-full-v2-expected-fail" not in scored
    assert payload["scored_allowlist"] == [
        "direct-v1",
        "plan-v1",
        "ultimateinterview-current-v1-structural",
    ]


def _copy_worker_build_context(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1]
    target = tmp_path / "worker"
    target.mkdir()
    for file_name in ("Dockerfile.worker", "requirements.worker.lock", "uv.lock"):
        shutil.copy2(source / file_name, target / file_name)
    for directory in ("corpus", "oci", "wheelhouse", "protocol"):
        shutil.copytree(source / directory, target / directory)
    return target


def test_worker_preflight_requires_real_pinned_base_and_frozen_wheelhouse() -> None:
    root = Path(__file__).parents[1]
    receipt = preflight_worker_image(root)

    assert receipt.status == "passed"
    assert receipt.base_image == (
        "docker.io/library/python@"
        "sha256:8b48630e688730a22bd25f3c9e04606b37fa1488cf70e665932ef78a3ee1e4d0"
    )
    assert receipt.frozen_assets == (
        "corpus/public",
        "oci",
        "protocol/ultimateinterview/ui-native-77b0327-r4",
    )


def test_worker_preflight_rejects_floating_base_and_tampered_wheel(tmp_path: Path) -> None:
    root = _copy_worker_build_context(tmp_path)
    dockerfile = root / "Dockerfile.worker"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "docker.io/library/python@sha256:8b48630e688730a22bd25f3c9e04606b37fa1488cf70e665932ef78a3ee1e4d0",
            "python:3.14-slim",
        ),
        encoding="utf-8",
    )
    with pytest.raises(WorkerPreflightError, match="digest-pinned"):
        preflight_worker_image(root)

    shutil.copy2(Path(__file__).parents[1] / "Dockerfile.worker", dockerfile)
    wheel = next((root / "wheelhouse").glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"tamper")
    with pytest.raises(WorkerPreflightError, match="wheel (size|digest) mismatch"):
        preflight_worker_image(root)


def test_worker_launcher_emits_full_isolation_controls_and_receipt() -> None:
    root = Path(__file__).parents[1]
    image = "registry.example/driftbench-worker@sha256:" + "a" * 64
    plan = build_worker_launch_plan(
        root,
        role="planner",
        worker_image=image,
        binding_digest="c" * 64,
        argv=("validate-corpus", "--public-root", "corpus/public", "--partition", "dev"),
    )

    assert "--network" in plan.command
    assert plan.command[plan.command.index("--network") + 1] == "none"
    assert "--read-only" in plan.command
    assert plan.command[plan.command.index("--cap-drop") + 1] == "ALL"
    assert any(item.startswith("seccomp=") for item in plan.command)
    assert plan.controls["mounts"][1]["read_only"] is False
    workspace_mount = plan.command[plan.command.index("--mount") + 1]
    assert "volume-nocopy" not in workspace_mount
    assert plan.controls["mounts"][1]["copy_data"] is True
    assert all("type=bind" not in item for item in plan.command)

    receipt = launch_worker(
        plan,
        runner=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )
    assert receipt.status == "completed"
    assert receipt.controls["network"] == {"mode": "none", "host_network": False, "dns": False}


def test_worker_launcher_rejects_floating_worker_images_and_unmanaged_volumes() -> None:
    root = Path(__file__).parents[1]
    with pytest.raises(WorkerPreflightError, match="referenced by digest"):
        build_worker_launch_plan(root, role="implementer", worker_image="driftbench-worker:latest", binding_digest="c" * 64)
    with pytest.raises(WorkerPreflightError, match="launcher-managed named volume"):
        build_worker_launch_plan(
            root,
            role="implementer",
            worker_image="registry.example/driftbench-worker@sha256:" + "b" * 64,
            binding_digest="c" * 64,
            workspace_volume="host-workspace",
        )


class _VolumeDocker:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.labels: dict[str, str] = {}
        self.volume: str | None = None
        self.fail_remove = False

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        action = command[2]
        if action == "inspect":
            if self.volume != command[3]:
                return subprocess.CompletedProcess(command, 1, "", "Error response from daemon: no such volume")
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps([{"Name": self.volume, "Labels": self.labels}]),
                "",
            )
        if action == "create":
            self.volume = command[-1]
            self.labels = {}
            for label in command[3:-1]:
                key, value = label.removeprefix("--label=").split("=", 1)
                self.labels[key] = value
            return subprocess.CompletedProcess(command, 0, f"{self.volume}\n", "")
        if action == "rm":
            if self.fail_remove:
                return subprocess.CompletedProcess(command, 1, "", "volume is in use")
            self.volume = None
            self.labels = {}
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected Docker volume command: {command}")


def _workspace_volume_arguments() -> dict[str, str]:
    return {
        "role": "planner",
        "binding_digest": "a" * 64,
        "input_digest": "b" * 64,
        "worker_image": "registry.example/driftbench-worker@sha256:" + "c" * 64,
    }


def test_workspace_volume_recovers_labeled_stale_volume_after_stage_interruption() -> None:
    root = Path(__file__).parents[1]
    docker = _VolumeDocker()
    arguments = _workspace_volume_arguments()

    volume = create_workspace_volume(root, runner=docker, **arguments)
    recovered = create_workspace_volume(root, runner=docker, **arguments)

    assert recovered == volume
    assert [command[2] for command in docker.commands].count("create") == 2
    assert [command[2] for command in docker.commands].count("rm") == 1
    assert docker.labels["io.driftbench.workspace.owner"] == "driftbench-worker-launcher"
    assert docker.labels["io.driftbench.workspace.input-sha256"] == arguments["input_digest"]


def test_workspace_volume_rejects_foreign_or_unlabeled_stale_volume() -> None:
    root = Path(__file__).parents[1]
    docker = _VolumeDocker()
    arguments = _workspace_volume_arguments()
    docker.volume = "driftbench-workspace-planner-aaaaaaaaaaaa-bbbbbbbbbbbb"
    docker.labels = {"purpose": "foreign"}

    with pytest.raises(WorkerLaunchError, match="foreign, unlabeled"):
        create_workspace_volume(root, runner=docker, **arguments)

    assert [command[2] for command in docker.commands] == ["inspect"]


def test_cleanup_failure_is_not_swallowed_by_role_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).parents[1]
    docker = _VolumeDocker()
    arguments = _workspace_volume_arguments()
    volume = create_workspace_volume(root, runner=docker, **arguments)
    docker.fail_remove = True
    with pytest.raises(WorkerLaunchError, match="volume removal was rejected.*volume is in use"):
        remove_workspace_volume(volume, runner=docker, **arguments)
    class FailingCleanupLauncher:
        WorkerLaunchError = WorkerLaunchError
        WorkerPreflightError = WorkerPreflightError

        def __init__(self) -> None:
            self.cleanup_arguments: dict[str, str] | None = None

        def create_workspace_volume(self, _: Path, **__: str) -> str:
            return "driftbench-workspace-planner-aaaaaaaaaaaa-bbbbbbbbbbbb"

        def build_worker_launch_plan(self, *_: object, **__: object) -> None:
            raise WorkerLaunchError("stage command rejected")

        def remove_workspace_volume(self, _: str, **kwargs: str) -> None:
            self.cleanup_arguments = kwargs
            raise WorkerLaunchError("volume removal denied")

    launcher = FailingCleanupLauncher()
    monkeypatch.setattr(cli, "_lazy_module", lambda _: launcher)

    with pytest.raises(
        cli.CliError,
        match="stage command rejected; required OCI workspace cleanup failed: volume removal denied",
    ):
        cli._run_role_work(
            Path(__file__).parents[1],
            role="planner",
            worker_image=_workspace_volume_arguments()["worker_image"],
            binding_digest="a" * 64,
            context={},
            artifacts={},
        )

    assert launcher.cleanup_arguments is not None
    assert launcher.cleanup_arguments["role"] == "planner"
    assert launcher.cleanup_arguments["binding_digest"] == "a" * 64


def test_external_holdout_frozen_release_metadata_is_public_safe_and_preflighted(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    manifest_path = root / "corpus" / "external-holdout" / "service-manifest.template.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release = manifest["frozen_release"]

    assert release["dev_case_count"] == 6
    assert release["holdout_case_count"] == 4
    assert release["total_case_count"] == 10
    assert release["opaque_record_set_digest"].startswith("sha256:")
    assert release["signature"]["value"] == "EXTERNAL-PROVISIONER-SIGNATURE-REQUIRED"
    assert release["attestation"]["value"] == "EXTERNAL-PROVISIONER-ATTESTATION-REQUIRED"
    assert not (set(release) & {"cases", "records", "prompts", "starter_trees", "tokens", "scoring_rules"})

    copied_root = _copy_worker_build_context(tmp_path)
    copied_manifest_path = copied_root / "corpus" / "external-holdout" / "service-manifest.template.json"
    copied_manifest = json.loads(copied_manifest_path.read_text(encoding="utf-8"))
    copied_manifest["frozen_release"]["holdout_case_count"] = 5
    copied_manifest_path.write_text(json.dumps(copied_manifest), encoding="utf-8")
    with pytest.raises(WorkerPreflightError, match="six development and four holdout"):
        preflight_worker_image(copied_root)
