from __future__ import annotations

import json
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest
from driftbench import cli, role_worker, worker_launcher
from driftbench import corpus
from driftbench.models import FULL_V2_ARM_ID, RunManifest, RunState
from driftbench.state import StateStore, atomic_write_json, canonical_bytes, canonical_digest, digest_bytes, read_canonical_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = PROJECT_ROOT / "corpus" / "public"
WORKER_IMAGE = "driftbench-worker@sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def _fake_isolated_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject the unit-only role runner; production code has no host fallback."""
    replay_context = worker_launcher.build_worker_receipt_replay_context(PROJECT_ROOT)

    def fake_role_work(
        _project_root,
        *,
        role: str,
        worker_image: str,
        binding_digest: str,
        context,
        artifacts,
        native_v1: bool = False,
    ):
        envelope = {
            "schema": "RoleWorkInput.v1",
            "role": role,
            "binding_digest": binding_digest,
            "context": context.model_dump(mode="json", by_alias=True),
            "artifacts": dict(artifacts),
            "native_v1": native_v1,
        }
        input_digest = canonical_digest(envelope)
        with TemporaryDirectory() as directory:
            output = role_worker.execute_role_input(
                role,
                envelope,
                input_digest=input_digest,
                workspace=Path(directory),
            )
        replayed_receipts = worker_launcher.replay_worker_role_receipts(
            replay_context,
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
            input_digest=input_digest,
            output_read_stdout=canonical_bytes(output).decode("utf-8"),
        )
        return output["documents"], {
            **replayed_receipts,
            "role_output_digest": canonical_digest(output),
        }

    monkeypatch.setattr(cli, "_run_role_work", fake_role_work)


def _artifact_bytes(run_dir: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(run_dir): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }

def _refresh_cell_closure(run_dir: Path, cell_id: str) -> None:
    store = StateStore(run_dir)
    state = store.load_state()
    cell = next(item for item in state.cells if item.cell_id == cell_id)
    cell_dir = run_dir / "cells" / cell_id
    lifecycle_path = cell_dir / "lifecycle-manifest.json"
    lifecycle = read_canonical_json(lifecycle_path)
    for reference in lifecycle["artifacts"]:
        document = read_canonical_json(cell_dir / reference["filename"])
        reference["digest"] = canonical_digest(document)
    atomic_write_json(lifecycle_path, lifecycle)

    attempt_path = cell_dir / f"attempt-{cell.attempt:06d}.json"
    attempt = read_canonical_json(attempt_path)
    attempt["lifecycle_manifest_digest"] = canonical_digest(lifecycle)
    attempt["role_output_digests"] = {
        reference["artifact_id"]: read_canonical_json(cell_dir / reference["filename"])["role_output_digest"]
        for reference in lifecycle["artifacts"]
        if reference["artifact_id"].endswith("-execution")
    }
    atomic_write_json(attempt_path, attempt)

    terminal_path = cell_dir / (
        "terminal-receipt.json" if cell.attempt == 1 else f"terminal-receipt-{cell.attempt:06d}.json"
    )
    terminal = read_canonical_json(terminal_path)
    terminal["lifecycle_manifest_digest"] = canonical_digest(lifecycle)
    terminal["attempt_receipt_digest"] = canonical_digest(attempt)
    atomic_write_json(terminal_path, terminal)

    state_document = state.model_dump(mode="json", by_alias=True, exclude_none=False)
    state_cell = next(item for item in state_document["cells"] if item["cell_id"] == cell_id)
    state_cell["attempt_receipt_digest"] = digest_bytes(attempt_path.read_bytes())
    state_cell["terminal_receipt_digest"] = digest_bytes(terminal_path.read_bytes())
    store.save_state(RunState.model_validate(state_document))


def test_validate_corpus_resolves_public_root(capsys) -> None:
    assert (
        cli.main(["validate-corpus", "--public-root", str(PUBLIC_ROOT), "--partition", "dev"])
        == cli.EXIT_COMPLETE
    )

    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "partition": "dev",
        "schema": "CorpusValidationReceipt.v1",
        "status": "valid",
    }

def test_public_corpus_contains_only_dev_prompts_and_starters() -> None:
    document = json.loads((PUBLIC_ROOT / "cases.json").read_text(encoding="utf-8"))
    manifest = json.loads((PUBLIC_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert corpus.validate_corpus(PUBLIC_ROOT / "cases.json", PUBLIC_ROOT / "manifest.json", partition="dev")
    assert document["schema"] == "DriftBenchPublicCorpus.v3"
    assert len(document["cases"]) == 12
    assert all(set(case) == {"schema", "case_id", "opaque_token", "partition", "prompt", "starter_tree", "starter_digest"} for case in document["cases"])
    assert all((PUBLIC_ROOT / case["starter_tree"]).is_dir() for case in document["cases"])
    assert all(corpus.starter_tree_digest(PUBLIC_ROOT / case["starter_tree"]) == case["starter_digest"] for case in document["cases"])
    assert "holdout" not in json.dumps(manifest).casefold()

def test_holdout_boundary_fixture_is_synthetic_and_external_only(capsys) -> None:
    private_fixture = PROJECT_ROOT / "corpus" / "trusted-private-fixtures" / "records.json"
    external_template = PROJECT_ROOT / "corpus" / "external-holdout" / "service-manifest.template.json"
    private_document = json.loads(private_fixture.read_text(encoding="utf-8"))
    sentinel = "SYNTHETIC-EXTERNAL-HOLDOUT-BOUNDARY-9fd4b"

    assert set(private_document) == {
        "schema",
        "release_id",
        "development_annotations",
        "boundary_fixture",
    }
    assert private_document["schema"] == "DriftBenchPrivateDevelopmentFixture.v2"
    annotations = private_document["development_annotations"]
    assert len(annotations) == 6
    assert {annotation["case_id"] for annotation in annotations} == {
        "bookmarks", "config-merge", "contacts-csv", "expense", "reminder", "todo"
    }
    assert all(
        set(annotation) == {"case_id", "fact_families", "atoms", "simulator"}
        for annotation in annotations
    )
    assert all(
        not {"opaque_token", "partition", "prompt", "starter_tree", "starter_digest"}.intersection(annotation)
        for annotation in annotations
    )
    assert not (private_fixture.parent / "starters").exists()

    boundary_fixture = private_document["boundary_fixture"]
    assert boundary_fixture == {
        "schema": "ExternalHoldoutBoundarySentinel.v1",
        "fixture_id": "synthetic-no-content",
        "sentinel": sentinel,
        "external_manifest": "corpus/external-holdout/service-manifest.template.json",
        "assertions": [
            "No holdout prompts, tokens, rules, atoms, or starter trees are stored here.",
            "Local configuration, controller, and worker image must not receive the sentinel.",
        ],
    }

    template = json.loads(external_template.read_text(encoding="utf-8"))
    assert set(template) == {
        "schema",
        "provisioning",
        "repository_content",
        "service_capabilities",
        "boundary_requirements",
        "provisioner_must_supply_outside_this_repository",
        "frozen_release",
    }
    assert template["provisioning"] == "external-only"
    assert template["repository_content"] == "none"
    assert template["boundary_requirements"] == {
        "local_controller_access": False,
        "worker_image_access": False,
        "repository_mount": False,
        "holdout_payload": "externally-provisioned",
    }
    assert sentinel not in external_template.read_text(encoding="utf-8")

    local_surfaces = [
        PROJECT_ROOT / "configs" / "fake-dev.toml",
        PROJECT_ROOT / "configs" / "live-dev.toml",
        PROJECT_ROOT / "src" / "driftbench" / "cli.py",
        PROJECT_ROOT / "Dockerfile.worker",
    ]
    assert all(sentinel not in surface.read_text(encoding="utf-8") for surface in local_surfaces)
    assert all(
        "trusted-private-fixtures" not in surface.read_text(encoding="utf-8")
        and "external-holdout" not in surface.read_text(encoding="utf-8")
        for surface in local_surfaces
    )
    assert cli.main(
        [
            "validate-corpus",
            "--public-root",
            str(PUBLIC_ROOT),
            "--partition",
            "holdout",
        ]
    ) == cli.EXIT_RUNTIME_FAILURE
    assert "invalid choice" in capsys.readouterr().err
def test_public_corpus_rejects_tampered_starter_tree(tmp_path: Path) -> None:
    copied_root = tmp_path / "public"
    shutil.copytree(PUBLIC_ROOT, copied_root)
    (copied_root / "starters" / "todo" / "todos.json").write_text(
        "{\"todos\":[]}\n",
        encoding="utf-8",
    )

    with pytest.raises(corpus.CorpusValidationError, match="starter digest"):
        corpus.validate_corpus(copied_root / "cases.json", copied_root / "manifest.json", partition="dev")


def test_fake_run_completes_and_resume_is_idempotent(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    command = [
        "run",
        "--config",
        "configs/fake-dev.toml",
        "--run-dir",
        str(run_dir),
        "--worker-image",
        WORKER_IMAGE,
        "--resume",
    ]

    assert cli.main(command) == cli.EXIT_COMPLETE
    first_receipt = json.loads(capsys.readouterr().out)
    assert first_receipt["status"] == "complete"
    assert first_receipt["claim"] == "deterministic-development-treatment"
    assert first_receipt["score_exit"] == cli.EXIT_COMPLETE

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "complete"
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    assert state["worker_image"] == WORKER_IMAGE
    assert manifest["worker_image"] == WORKER_IMAGE
    assert len(state["cells"]) == 36
    assert all(cell["status"] == "completed" for cell in state["cells"])
    base_artifacts = {
        "input.json",
        "implementer-context.json",
        "implementer-execution.json",
        "implementation.json",
        "observation.json",
        "evidence-manifest.json",
        "postmortem-context.json",
        "postmortem-request.json",
        "postmortem-execution.json",
        "postmortem-report.json",
        "lifecycle-manifest.json",
        "attempt-000001.json",
        "terminal-receipt.json",
    }
    for cell in state["cells"]:
        cell_dir = run_dir / "cells" / cell["cell_id"]
        filenames = {path.name for path in cell_dir.iterdir()}
        assert base_artifacts.issubset(filenames)
        if cell["identity"]["arm_id"] == "direct-v1":
            assert {"planner-context.json", "handoff.json", "build-contract.json"}.isdisjoint(filenames)
        else:
            assert {"planner-context.json", "planner-execution.json", "handoff.json", "build-contract.json"}.issubset(filenames)
        if cell["identity"]["arm_id"] == "ultimateinterview-current-v1-structural":
            assert "native-v1-runtime.json" in filenames
        else:
            assert "native-v1-runtime.json" not in filenames

    scorecard = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["scored"] is True
    assert scorecard["claim"] == "deterministic-development-treatment"
    assert scorecard["development_metrics"] == {
        "case_count": 36,
        "total_weight": 36.0,
        "weighted_primary_credit": 1.0,
    }
    assert [score["arm_id"] for score in scorecard["arm_scores"]] == [
        "direct-v1",
        "plan-v1",
        "ultimateinterview-current-v1-structural",
    ]

    first_artifacts = _artifact_bytes(run_dir)
    assert cli.main(command) == cli.EXIT_COMPLETE
    second_receipt = json.loads(capsys.readouterr().out)
    assert second_receipt == first_receipt
    assert _artifact_bytes(run_dir) == first_artifacts
def test_resume_and_score_reject_manifest_state_closure_drift(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    store = StateStore(run_dir)
    state_document = store.load_state().model_dump(mode="json", by_alias=True, exclude_none=False)
    state_document["config_digest"] = "f" * 64
    store.save_state(RunState.model_validate(state_document))

    assert cli.main(["resume", "--run-dir", str(run_dir), "--worker-image", WORKER_IMAGE]) == cli.EXIT_INCOMPATIBLE_RESUME
    assert "manifest-state input or worker image closure drift" in capsys.readouterr().err
    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INCOMPATIBLE_RESUME
    assert "manifest-state input or worker image closure drift" in capsys.readouterr().err

def test_score_rejects_observation_not_bound_to_lifecycle(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    state = StateStore(run_dir).load_state()
    observation_path = run_dir / "cells" / state.cells[0].cell_id / "observation.json"
    observation = read_canonical_json(observation_path)
    observation["comparison"]["primary_credit"] = 0
    atomic_write_json(observation_path, observation)

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INVALID

def test_resume_rejects_changed_worker_image(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    alternate_image = "driftbench-worker@sha256:" + "b" * 64
    assert cli.main(
        ["resume", "--run-dir", str(run_dir), "--worker-image", alternate_image]
    ) == cli.EXIT_INCOMPATIBLE_RESUME
    assert "resume worker image drift" in capsys.readouterr().err


def test_score_rejects_worker_image_mixed_receipts(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    store = StateStore(run_dir)
    alternate_image = "driftbench-worker@sha256:" + "b" * 64
    state_document = store.load_state().model_dump(mode="json", by_alias=True, exclude_none=False)
    state_document["worker_image"] = alternate_image
    store.save_state(RunState.model_validate(state_document))
    manifest_document = store.load_manifest().model_dump(mode="json", by_alias=True, exclude_none=False)
    manifest_document["worker_image"] = alternate_image
    store.save_manifest(RunManifest.model_validate(manifest_document))

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INVALID


def test_score_rejects_tampered_native_runtime_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    state = StateStore(run_dir).load_state()
    cell = next(
        item
        for item in state.cells
        if item.identity.arm_id == "ultimateinterview-current-v1-structural"
    )
    cell_dir = run_dir / "cells" / cell.cell_id
    native_path = cell_dir / "native-v1-runtime.json"
    native_runtime = read_canonical_json(native_path)
    native_runtime["implementation_ready"] = False
    atomic_write_json(native_path, native_runtime)

    planner_execution_path = cell_dir / "planner-execution.json"
    planner_execution = read_canonical_json(planner_execution_path)
    output = json.loads(planner_execution["output_read"]["stdout"])
    output["documents"]["native-v1-runtime"]["implementation_ready"] = False
    planner_execution["output_read"]["stdout"] = canonical_bytes(output).decode("utf-8")
    planner_execution["role_output_digest"] = canonical_digest(output)
    atomic_write_json(planner_execution_path, planner_execution)
    _refresh_cell_closure(run_dir, cell.cell_id)

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INVALID


def test_score_rejects_tampered_retained_role_output(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    state = StateStore(run_dir).load_state()
    cell = next(item for item in state.cells if item.identity.arm_id == "direct-v1")
    execution_path = run_dir / "cells" / cell.cell_id / "implementer-execution.json"
    execution = read_canonical_json(execution_path)
    output = json.loads(execution["output_read"]["stdout"])
    output["documents"]["implementation"]["starter"]["materialized_digest"] = "0" * 64
    execution["output_read"]["stdout"] = canonical_bytes(output).decode("utf-8")
    execution["role_output_digest"] = canonical_digest(output)
    atomic_write_json(execution_path, execution)
    _refresh_cell_closure(run_dir, cell.cell_id)

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INVALID
def test_score_rejects_replayed_oci_receipt_drift_after_outer_digest_refresh(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / "run"
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    cell = next(item for item in StateStore(run_dir).load_state().cells if item.identity.arm_id == "direct-v1")
    cases = (
        "mounts",
        "profile",
        "seccomp",
        "resources",
        "reused_phase_receipt",
        "workspace_volume",
        "missing_cleanup",
        "cleanup",
    )
    for case in cases:
        candidate = tmp_path / case
        shutil.copytree(run_dir, candidate)
        execution_path = candidate / "cells" / cell.cell_id / "implementer-execution.json"
        execution = read_canonical_json(execution_path)
        if case == "mounts":
            execution["input_stage"]["controls"]["mounts"] = []
        elif case == "profile":
            execution["isolation_launch"]["profile_sha256"] = "0" * 64
        elif case == "seccomp":
            execution["isolation_launch"]["controls"]["seccomp"]["sha256"] = "0" * 64
        elif case == "resources":
            execution["isolation_launch"]["controls"]["resources"]["memory_bytes"] = 1
        elif case == "reused_phase_receipt":
            execution["input_stage"] = dict(execution["isolation_launch"])
        elif case == "workspace_volume":
            for receipt_name in ("input_stage", "isolation_launch", "output_read"):
                execution[receipt_name]["controls"]["mounts"][1]["source"] = "driftbench-workspace-replayed"
        elif case == "missing_cleanup":
            del execution["workspace_cleanup"]
        else:
            execution["workspace_cleanup"]["ownership_sha256"] = "0" * 64
        atomic_write_json(execution_path, execution)
        _refresh_cell_closure(candidate, cell.cell_id)

        assert cli.main(["score", "--run-dir", str(candidate)]) == cli.EXIT_INVALID
        capsys.readouterr()


@pytest.mark.parametrize(
    "forged_arm",
    [FULL_V2_ARM_ID, "forged-unallowlisted-arm"],
)
def test_resume_and_score_reject_forged_unallowlisted_persisted_arms(
    tmp_path: Path,
    monkeypatch,
    capsys,
    forged_arm: str,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    run_dir = tmp_path / forged_arm
    assert cli.main(
        [
            "run",
            "--config",
            "configs/fake-dev.toml",
            "--run-dir",
            str(run_dir),
            "--worker-image",
            WORKER_IMAGE,
            "--resume",
        ]
    ) == cli.EXIT_COMPLETE
    capsys.readouterr()

    store = StateStore(run_dir)
    state_document = store.load_state().model_dump(mode="json", by_alias=True, exclude_none=False)
    state_document["arm_digests"] = {forged_arm: "f" * 64}
    for cell in state_document["cells"]:
        cell["identity"]["arm_id"] = forged_arm
    store.save_state(RunState.model_validate(state_document))

    manifest_document = store.load_manifest().model_dump(mode="json", by_alias=True, exclude_none=False)
    manifest_document["arm_digests"] = {forged_arm: "f" * 64}
    store.save_manifest(RunManifest.model_validate(manifest_document))

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_INCOMPATIBLE_RESUME
    score_error = capsys.readouterr().err
    assert "allowlisted" in score_error or "non-scored" in score_error
    assert cli.main(
        ["resume", "--run-dir", str(run_dir), "--worker-image", WORKER_IMAGE]
    ) == cli.EXIT_INCOMPATIBLE_RESUME
    resume_error = capsys.readouterr().err
    assert "allowlisted" in resume_error or "non-scored" in resume_error
