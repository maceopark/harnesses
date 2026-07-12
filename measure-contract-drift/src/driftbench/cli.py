"""Fail-closed command line controller for deterministic contract-drift runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from hashlib import sha256
import importlib
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import (
    ArmDefinition,
    CellIdentity,
    CellRecord,
    CellStatus,
    DevelopmentArmScore,
    DevelopmentBootstrapCI,
    DevelopmentScore,
    EvaluationStatusReceipt,
    RunConfig,
    RunManifest,
    RunMode,
    RunState,
    RunStatus,
    Scorecard,
    TERMINAL_CELL_STATUSES,
    validate_worker_image_identity,
)
from .state import (
    StateError,
    StateStore,
    atomic_write_model,
    canonical_bytes,
    canonical_digest,
    digest_bytes,
    read_canonical_json,
)

EXIT_COMPLETE = 0
EXIT_INVALID = 10
EXIT_BLOCKED = 11
EXIT_INCOMPATIBLE_RESUME = 12
EXIT_RUNTIME_FAILURE = 13
EXIT_CANCELLED = 14
EXIT_UNSAFE_LOCAL = 15


class CliError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class DriftArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError(EXIT_RUNTIME_FAILURE, message)


def _emit(value: Any) -> None:
    sys.stdout.buffer.write(canonical_bytes(value))


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _document(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=False)
    return value


def _load_config(path: Path) -> tuple[RunConfig, str]:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as error:
        raise CliError(EXIT_BLOCKED, f"required config is absent: {path}") from error
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CliError(EXIT_INVALID, f"invalid config {path}: {error}") from error
    try:
        config = RunConfig.model_validate(raw)
    except ValidationError as error:
        raise CliError(EXIT_INVALID, f"config violates RunConfig.v1: {error}") from error
    return config, canonical_digest(raw)


def _project_root(config_path: Path) -> Path:
    for directory in (config_path.parent, *config_path.parent.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    return config_path.parent


def _resolve_config_relative(config_path: Path, configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate
    config_relative = config_path.parent / candidate
    project_relative = _project_root(config_path) / candidate
    return config_relative if config_relative.exists() or not project_relative.exists() else project_relative


def _lazy_module(name: str) -> Any:
    qualified_name = f"{__package__}.{name}"
    try:
        return importlib.import_module(qualified_name)
    except ModuleNotFoundError as error:
        if error.name == qualified_name:
            raise CliError(EXIT_BLOCKED, f"required {name} helper is unavailable") from error
        raise CliError(EXIT_BLOCKED, f"required {name} helper cannot load: {error}") from error
    except Exception as error:
        raise CliError(EXIT_BLOCKED, f"required {name} helper cannot load: {error}") from error


def _require_callable(module: Any, name: str) -> Any:
    function = getattr(module, name, None)
    if not callable(function):
        raise CliError(EXIT_BLOCKED, f"required helper function is unavailable: {module.__name__}.{name}")
    return function

def _require_scored_arm_allowlist(
    arm_ids: Mapping[str, str] | Sequence[str],
    *,
    code: int,
) -> None:
    metrics = _lazy_module("metrics")
    require_allowlist = _require_callable(metrics, "require_scored_arm_allowlist")
    try:
        require_allowlist(arm_ids)
    except (TypeError, ValueError) as error:
        raise CliError(code, str(error)) from error


def _validation_failed(result: Any) -> bool:
    document = _document(result)
    if document is False:
        return True
    if isinstance(document, Mapping):
        return document.get("valid") is False
    return False


def _load_cases(corpus_root: Path, partition: str) -> tuple[list[dict[str, Any]], str]:
    if not corpus_root.is_dir():
        raise CliError(EXIT_BLOCKED, f"required public corpus directory is absent: {corpus_root}")
    cases_path = corpus_root / "cases.json"
    manifest_path = corpus_root / "manifest.json"
    corpus = _lazy_module("corpus")
    validate_corpus = _require_callable(corpus, "validate_corpus")
    load_cases = _require_callable(corpus, "load_cases")
    try:
        validation = validate_corpus(cases_path, manifest_path, partition=partition)
        if _validation_failed(validation):
            raise CliError(EXIT_INVALID, "corpus validation reported invalid records")
        loaded = _document(load_cases(cases_path))
    except CliError:
        raise
    except (ValidationError, ValueError, TypeError) as error:
        raise CliError(EXIT_INVALID, f"invalid corpus: {error}") from error
    except OSError as error:
        raise CliError(EXIT_BLOCKED, f"cannot load required corpus artifact: {error}") from error
    except Exception as error:
        raise CliError(EXIT_BLOCKED, f"corpus helper failed closed: {error}") from error

    if isinstance(loaded, Mapping):
        loaded = loaded.get("cases", loaded)
    if not isinstance(loaded, Sequence) or isinstance(loaded, (str, bytes, bytearray)):
        raise CliError(EXIT_INVALID, "corpus.load_cases must return a sequence of CaseRecord documents")

    cases: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for case in loaded:
        document = _document(case)
        if not isinstance(document, Mapping):
            raise CliError(EXIT_INVALID, "corpus contains a non-object CaseRecord")
        copied = dict(document)
        if copied.get("partition") != partition:
            continue
        token = copied.get("opaque_token")
        if not isinstance(token, str) or not token.strip():
            raise CliError(EXIT_INVALID, "CaseRecord lacks opaque_token")
        if token in seen_tokens:
            raise CliError(EXIT_INVALID, f"corpus has duplicate opaque_token: {token}")
        seen_tokens.add(token)
        cases.append(copied)
    if not cases:
        raise CliError(EXIT_INVALID, f"corpus has no {partition} cases")
    cases.sort(key=lambda case: str(case["opaque_token"]))
    return cases, canonical_digest(cases)


def _load_arm_digests(config: RunConfig, config_path: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for arm in config.arms:
        source = _resolve_config_relative(config_path, arm.source)
        if source.is_symlink():
            raise CliError(EXIT_BLOCKED, f"required arm source is absent or unsafe: {source}")
        if source.is_file():
            try:
                digests[arm.arm_id] = digest_bytes(source.read_bytes())
            except OSError as error:
                raise CliError(EXIT_BLOCKED, f"cannot read required arm source {source}: {error}") from error
            continue
        if source.exists():
            raise CliError(EXIT_BLOCKED, f"required arm source is absent or unsafe: {source}")
        if config.mode is RunMode.FAKE_DEV:
            digests[arm.arm_id] = canonical_digest(
                {
                    "schema": "FakeArmBinding.v1",
                    "arm_id": arm.arm_id,
                    "source": arm.source,
                }
            )
            continue
        raise CliError(EXIT_BLOCKED, f"required arm source is absent or unsafe: {source}")
    return dict(sorted(digests.items()))


def _run_id(
    config_digest: str,
    corpus_digest: str,
    arm_digests: Mapping[str, str],
    worker_image: str,
) -> str:
    return "run-" + canonical_digest(
        {
            "schema": "RunIdentity.v2",
            "config_digest": config_digest,
            "corpus_digest": corpus_digest,
            "arm_digests": dict(arm_digests),
            "worker_image": worker_image,
        }
    )[:24]


def _cell_inputs(
    config: RunConfig,
    config_digest: str,
    corpus_digest: str,
    cases: Sequence[Mapping[str, Any]],
    arm_digests: Mapping[str, str],
) -> tuple[CellRecord, ...]:
    cells: list[CellRecord] = []
    for case in cases:
        for arm in sorted(config.arms, key=lambda item: item.arm_id):
            identity = CellIdentity(
                corpus_version=corpus_digest,
                partition=config.partition,
                opaque_case_token=str(case["opaque_token"]),
                arm_id=arm.arm_id,
                planner_model=config.models.planner,
                implementer_model=config.models.implementer,
                postmortem_model=config.models.postmortem,
                seed_label=config.seed_label,
            )
            cell_id = "cell-" + canonical_digest({"schema": "CellIdentity.v1", "identity": identity})[:32]
            provisional = CellRecord(
                cell_id=cell_id,
                identity=identity,
                input_digest="0" * 64,
            )
            input_document = _cell_input_document(
                provisional,
                config_digest,
                case,
                arm_digests[arm.arm_id],
            )
            cells.append(
                CellRecord(
                    cell_id=cell_id,
                    identity=identity,
                    input_digest=canonical_digest(input_document),
                )
            )
    return tuple(sorted(cells, key=lambda cell: cell.cell_id))


def _cell_input_document(
    cell: CellRecord,
    config_digest: str,
    case: Mapping[str, Any],
    arm_digest: str,
) -> dict[str, Any]:
    required_fields = ("case_id", "prompt", "starter_tree", "starter_digest")
    if any(not isinstance(case.get(field), str) or not case[field] for field in required_fields):
        raise CliError(EXIT_INVALID, f"case contract is incomplete: {cell.identity.opaque_case_token}")
    case_contract = {field: case[field] for field in required_fields}
    acceptance_requirement_id = "requirement-" + canonical_digest({"cell_id": cell.cell_id})[:24]
    return {
        "schema": "CellInput.v2",
        "cell_id": cell.cell_id,
        "identity": cell.identity,
        "config_digest": config_digest,
        "corpus_case_digest": canonical_digest(case),
        "arm_digest": arm_digest,
        "case_contract": case_contract,
        "acceptance_requirement_ids": [acceptance_requirement_id],
        "metric_case": {
            "case_id": cell.cell_id,
            "weight": 1,
        },
    }


def _rebuild_manifest(manifest: RunManifest, status: RunStatus) -> RunManifest:
    document = manifest.model_dump(mode="json", by_alias=True, exclude_none=False)
    document["status"] = status
    return RunManifest.model_validate(document)


def _bound_resume_check(
    store: StateStore,
    config_digest: str,
    corpus_digest: str,
    arm_digests: Mapping[str, str],
    worker_image: str,
) -> tuple[RunManifest, RunState]:
    try:
        manifest = store.load_manifest()
        state = store.load_state()
    except StateError as error:
        raise CliError(EXIT_INCOMPATIBLE_RESUME, str(error)) from error
    _require_manifest_state_closure(manifest, state)
    if (
        manifest.config_digest != config_digest
        or manifest.corpus_digest != corpus_digest
        or manifest.arm_digests != dict(arm_digests)
        or manifest.worker_image != worker_image
        or state.worker_image != worker_image
    ):
        raise CliError(EXIT_INCOMPATIBLE_RESUME, "resume input digest or worker image drift")
    return manifest, state


def _require_manifest_state_closure(manifest: RunManifest, state: RunState) -> None:
    _require_scored_arm_allowlist(manifest.arm_digests, code=EXIT_INCOMPATIBLE_RESUME)
    if (
        manifest.run_id != state.run_id
        or manifest.config_digest != state.config_digest
        or manifest.corpus_digest != state.corpus_digest
        or manifest.arm_digests != state.arm_digests
        or manifest.worker_image != state.worker_image
    ):
        raise CliError(EXIT_INCOMPATIBLE_RESUME, "manifest-state input or worker image closure drift")
    for cell in state.cells:
        if cell.identity.partition != manifest.partition or cell.identity.arm_id not in manifest.arm_digests:
            raise CliError(EXIT_INCOMPATIBLE_RESUME, f"manifest-state cell closure drift: {cell.cell_id}")


def _write_status(
    store: StateStore,
    config: RunConfig,
    state: RunState,
    message: str,
) -> None:
    completed = sum(cell.status is CellStatus.COMPLETED for cell in state.cells)
    invalid = sum(cell.status is CellStatus.INVALID for cell in state.cells)
    receipt = EvaluationStatusReceipt(
        run_id=state.run_id,
        status=state.status,
        mode=config.mode,
        partition=config.partition,
        provider_execution="not-attempted" if config.mode is RunMode.FAKE_DEV else "unavailable",
        completed_cells=completed,
        invalid_cells=invalid,
        message=message,
    )
    atomic_write_model(store.run_dir / store.status_name, receipt)


def _unscored_card(config: RunConfig, manifest: RunManifest, state: RunState, reason: str) -> Scorecard:
    return Scorecard(
        run_id=state.run_id,
        mode=config.mode,
        reason=reason,
        completed_cells=sum(cell.status is CellStatus.COMPLETED for cell in state.cells),
        invalid_cells=sum(cell.status is CellStatus.INVALID for cell in state.cells),
        manifest_digest=canonical_digest(manifest),
        state_digest=canonical_digest(state),
    )


def _build_arm_scorecard(run_dir: Path, state: RunState, manifest: RunManifest) -> Scorecard:
    metrics = _lazy_module("metrics")
    build_scorecard = _require_callable(metrics, "build_scorecard")
    return Scorecard.model_validate(
        _document(build_scorecard(run_dir=run_dir, state=state, manifest=manifest))
    )

def _write_scorecard(store: StateStore, config: RunConfig, state: RunState) -> int:
    try:
        manifest = store.load_manifest()
        current_state = store.load_state()
        _require_manifest_state_closure(manifest, current_state)
    except (StateError, CliError) as error:
        raise CliError(EXIT_INVALID, f"invalid manifest-state closure: {error}") from error
    if current_state != state:
        raise CliError(EXIT_INVALID, "score request state is stale")

    scorecard_path = store.run_dir / store.scorecard_name
    if config.mode is not RunMode.FAKE_DEV:
        expected = _unscored_card(config, manifest, current_state, "provider-execution-not-attempted")
    else:
        try:
            expected = _build_arm_scorecard(store.run_dir, current_state, manifest)
        except (StateError, ValidationError, TypeError, ValueError, CliError):
            expected = _unscored_card(config, manifest, current_state, "lifecycle_evidence_invalid")
            if scorecard_path.exists():
                try:
                    Scorecard.model_validate(read_canonical_json(scorecard_path))
                except (StateError, ValidationError) as artifact_error:
                    raise CliError(EXIT_INVALID, f"invalid scorecard artifact: {artifact_error}") from artifact_error
            else:
                atomic_write_model(scorecard_path, expected)
            return EXIT_INVALID
        except Exception:
            expected = _unscored_card(config, manifest, current_state, "lifecycle_evidence_invalid")
            if not scorecard_path.exists():
                atomic_write_model(scorecard_path, expected)
            return EXIT_INVALID

    if scorecard_path.exists():
        try:
            persisted = Scorecard.model_validate(read_canonical_json(scorecard_path))
        except (StateError, ValidationError) as error:
            raise CliError(EXIT_INVALID, f"invalid scorecard artifact: {error}") from error
        if persisted != expected:
            raise CliError(EXIT_INVALID, "scorecard is not bound to current manifest-state closure")
        return EXIT_COMPLETE
    atomic_write_model(scorecard_path, expected)
    return EXIT_COMPLETE


def _write_cell_inputs(
    store: StateStore,
    config: RunConfig,
    config_digest: str,
    cases: Sequence[Mapping[str, Any]],
    arm_digests: Mapping[str, str],
    state: RunState,
) -> None:
    cases_by_token = {str(case["opaque_token"]): case for case in cases}
    for cell in state.cells:
        case = cases_by_token.get(cell.identity.opaque_case_token)
        if case is None:
            raise CliError(EXIT_INCOMPATIBLE_RESUME, f"cell case is absent: {cell.identity.opaque_case_token}")
        document = _cell_input_document(
            cell,
            config_digest,
            case,
            arm_digests[cell.identity.arm_id],
        )
        try:
            store.write_cell_input(cell.cell_id, document, cell.input_digest)
        except StateError as error:
            raise CliError(EXIT_INCOMPATIBLE_RESUME, str(error)) from error


def _write_immutable_cell_artifact(
    store: StateStore,
    cell_id: str,
    filename: str,
    document: Any,
) -> str:
    """Write a deterministic lifecycle artifact once, rejecting resumed drift."""

    expected_digest = canonical_digest(document)
    path = store.cells_dir / cell_id / filename
    if path.exists():
        if canonical_digest(read_canonical_json(path)) != expected_digest:
            raise StateError(f"immutable lifecycle artifact drift: {cell_id}/{filename}")
        return expected_digest
    written_digest = store.write_cell_artifact(cell_id, filename, document)
    if written_digest != expected_digest:
        raise StateError(f"lifecycle artifact write digest drift: {cell_id}/{filename}")
    return written_digest


def _terminal_receipt_filename(attempt: int) -> str:
    return "terminal-receipt.json" if attempt == 1 else f"terminal-receipt-{attempt:06d}.json"


def _worker_binding(
    current: CellRecord,
    arm_id: str,
    context: Any,
) -> str:
    return canonical_digest(
        {
            "schema": "WorkerLaunchBinding.v1",
            "cell_id": current.cell_id,
            "arm_id": arm_id,
            "input_digest": current.input_digest,
            "context": _document(context),
        }
    )


def _role_receipt_document(value: Any, *, role: str, worker_image: str, binding_digest: str) -> dict[str, Any]:
    receipt = value.to_dict() if hasattr(value, "to_dict") else _document(value)
    if not isinstance(receipt, Mapping) or (
        receipt.get("schema") != "WorkerIsolationLaunchReceipt.v1"
        or receipt.get("status") != "completed"
        or receipt.get("returncode") != 0
        or receipt.get("role") != role
        or receipt.get("worker_image") != worker_image
        or receipt.get("binding_digest") != binding_digest
        or not isinstance(receipt.get("command_digest"), str)
        or len(receipt["command_digest"]) != 64
    ):
        raise CliError(EXIT_BLOCKED, "required OCI worker launch receipt is invalid")
    controls = receipt.get("controls")
    required_controls = {
        "network",
        "read_only_root_filesystem",
        "nonroot_user",
        "capabilities",
        "no_new_privileges",
        "seccomp",
        "resources",
        "mounts",
    }
    if not isinstance(controls, Mapping) or set(controls) != required_controls:
        raise CliError(EXIT_BLOCKED, "required OCI worker launch receipt lacks isolation controls")
    return dict(receipt)


def _run_role_work(
    project_root: Path,
    *,
    role: str,
    worker_image: str,
    binding_digest: str,
    context: Any,
    artifacts: Mapping[str, Any],
    native_v1: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Stage one canonical role closure, execute it in OCI, and verify its output."""

    launcher = _lazy_module("worker_launcher")
    envelope = {
        "schema": "RoleWorkInput.v1",
        "role": role,
        "binding_digest": binding_digest,
        "context": _document(context),
        "artifacts": dict(artifacts),
        "native_v1": native_v1,
    }
    input_bytes = canonical_bytes(envelope)
    input_digest = sha256(input_bytes).hexdigest()
    volume: str | None = None
    result: tuple[dict[str, Any], dict[str, Any]] | None = None
    failure: CliError | None = None
    try:
        volume = launcher.create_workspace_volume(
            project_root,
            role=role,
            binding_digest=binding_digest,
            input_digest=input_digest,
            worker_image=worker_image,
        )
        stage_plan = launcher.build_worker_launch_plan(
            project_root,
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
            workspace_volume=volume,
            argv=("worker-stage", "--input-digest", input_digest),
            stdin_open=True,
        )
        stage = _role_receipt_document(
            launcher.launch_worker(stage_plan, input_text=input_bytes.decode("utf-8")),
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
        )
        role_plan = launcher.build_worker_launch_plan(
            project_root,
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
            workspace_volume=volume,
            argv=("worker-role", "--role", role, "--input-digest", input_digest),
        )
        launch = _role_receipt_document(
            launcher.launch_worker(role_plan),
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
        )
        read_plan = launcher.build_worker_launch_plan(
            project_root,
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
            workspace_volume=volume,
            argv=("worker-read-output", "--input-digest", input_digest),
        )
        read = _role_receipt_document(
            launcher.launch_worker(read_plan),
            role=role,
            worker_image=worker_image,
            binding_digest=binding_digest,
        )
        raw_output = read.get("stdout")
        if not isinstance(raw_output, str):
            raise CliError(EXIT_BLOCKED, "OCI worker output is absent")
        output_bytes = raw_output.encode("utf-8")
        output = json.loads(output_bytes)
        if canonical_bytes(output) != output_bytes:
            raise CliError(EXIT_BLOCKED, "OCI worker output is not canonical JSON")
        if not isinstance(output, Mapping) or (
            output.get("schema") != "RoleWorkOutput.v1"
            or output.get("role") != role
            or output.get("input_digest") != input_digest
            or output.get("binding_digest") != binding_digest
            or output.get("context_digest") != canonical_digest(_document(context))
            or output.get("provenance") != "oci-deterministic-worker"
        ):
            raise CliError(EXIT_BLOCKED, "OCI worker output receipt is not bound to its staged input")
        documents = output.get("documents")
        if not isinstance(documents, Mapping) or not all(isinstance(key, str) and isinstance(value, Mapping) for key, value in documents.items()):
            raise CliError(EXIT_BLOCKED, "OCI worker output has an invalid document closure")
        receipt = {
            "isolation_launch": launch,
            "input_stage": stage,
            "output_read": read,
            "role_output_digest": canonical_digest(output),
        }
        result = (dict(documents), receipt)
    except CliError as error:
        failure = error
    except Exception as error:
        if isinstance(error, (launcher.WorkerLaunchError, launcher.WorkerPreflightError)):
            failure = CliError(EXIT_BLOCKED, f"required OCI worker launch is unavailable: {error}")
        else:
            failure = CliError(EXIT_BLOCKED, f"required OCI worker role failed closed: {error}")
        failure.__cause__ = error

    cleanup_receipt: Any | None = None
    cleanup_failure: Exception | None = None
    if volume is not None:
        try:
            cleanup_receipt = launcher.remove_workspace_volume(
                volume,
                role=role,
                binding_digest=binding_digest,
                input_digest=input_digest,
                worker_image=worker_image,
            )
        except Exception as error:
            cleanup_failure = error
    if cleanup_failure is not None:
        message = f"required OCI workspace cleanup failed: {cleanup_failure}"
        if failure is not None:
            message = f"{failure}; {message}"
        raise CliError(EXIT_BLOCKED, message) from cleanup_failure
    if failure is not None:
        raise failure
    if result is None or cleanup_receipt is None:
        raise CliError(EXIT_BLOCKED, "OCI worker role did not produce a cleanup receipt")
    documents, receipt = result
    receipt["workspace_cleanup"] = cleanup_receipt.to_dict()
    return documents, receipt


def _attach_oci_receipt(execution: Mapping[str, Any], receipts: Mapping[str, Any]) -> dict[str, Any]:
    document = dict(execution)
    document.update(dict(receipts))
    return document


def _run_role(
    project_root: Path,
    current: CellRecord,
    worker_image: str,
    *,
    role: str,
    context: Any,
    artifacts: Mapping[str, Any],
    native_v1: bool = False,
) -> dict[str, Any]:
    documents, receipts = _run_role_work(
        project_root,
        role=role,
        worker_image=worker_image,
        binding_digest=_worker_binding(current, current.identity.arm_id, context),
        context=context,
        artifacts=artifacts,
        native_v1=native_v1,
    )
    execution = documents.get("execution")
    if not isinstance(execution, Mapping) or execution.get("role") != role or execution.get("provenance") != "oci-deterministic-worker":
        raise CliError(EXIT_BLOCKED, "OCI worker did not return a role-bound execution receipt")
    documents["execution"] = _attach_oci_receipt(execution, receipts)
    return documents


def _write_lifecycle_terminal(
    store: StateStore,
    current: CellRecord,
    worker: Any,
    documents: Mapping[str, Any],
    *,
    semantic_result: str,
) -> tuple[str, str]:
    filenames = worker.LIFECYCLE_ARTIFACT_FILENAMES
    for artifact_id, document in documents.items():
        if artifact_id == "cell-input":
            continue
        _write_immutable_cell_artifact(store, current.cell_id, filenames[artifact_id], document)
    lifecycle = {
        "schema": "DevelopmentLifecycleManifest.v2",
        "cell_id": current.cell_id,
        "arm_id": current.identity.arm_id,
        "artifacts": [
            _document(worker.artifact_reference(artifact_id, filenames[artifact_id], document))
            for artifact_id, document in sorted(documents.items())
        ],
    }
    lifecycle_digest = _write_immutable_cell_artifact(
        store,
        current.cell_id,
        worker.LIFECYCLE_MANIFEST_FILENAME,
        lifecycle,
    )
    role_output_digests = {
        artifact_id: document["role_output_digest"]
        for artifact_id, document in documents.items()
        if artifact_id.endswith("-execution") and isinstance(document, Mapping) and isinstance(document.get("role_output_digest"), str)
    }
    attempt_receipt = {
        "schema": "AttemptReceipt.v2",
        "cell_id": current.cell_id,
        "attempt": current.attempt,
        "fence": current.fence,
        "input_digest": current.input_digest,
        "mode": "fake-dev",
        "provider_execution": "oci-deterministic-worker",
        "claim": "deterministic-development-treatment",
        "oci_receipts_required": True,
        "lifecycle_manifest_digest": lifecycle_digest,
        "role_output_digests": role_output_digests,
    }
    attempt_digest = _write_immutable_cell_artifact(
        store,
        current.cell_id,
        f"attempt-{current.attempt:06d}.json",
        attempt_receipt,
    )
    terminal_receipt = {
        "schema": "CellTerminalReceipt.v2",
        "cell_id": current.cell_id,
        "attempt": current.attempt,
        "fence": current.fence,
        "input_digest": current.input_digest,
        "status": CellStatus.COMPLETED.value,
        "provider_execution": "oci-deterministic-worker",
        "semantic_result": semantic_result,
        "observation_digest": canonical_digest(documents["observation"]),
        "comparison_digest": canonical_digest(documents["observation"]["comparison"]),
        "attempt_receipt_digest": attempt_digest,
        "claim": "deterministic-development-treatment",
        "authoritative": True,
        "oci_receipts_required": True,
        "lifecycle_manifest_digest": lifecycle_digest,
    }
    terminal_digest = _write_immutable_cell_artifact(
        store,
        current.cell_id,
        _terminal_receipt_filename(current.attempt),
        terminal_receipt,
    )
    return attempt_digest, terminal_digest


def _run_direct_lifecycle(
    store: StateStore,
    current: CellRecord,
    worker: Any,
    input_document: Mapping[str, Any],
    project_root: Path,
    worker_image: str,
) -> tuple[str, str]:
    filenames = worker.LIFECYCLE_ARTIFACT_FILENAMES
    documents: dict[str, Any] = {"cell-input": dict(input_document)}
    implementer_context = worker.fresh_role_context(
        worker.WorkerRole.IMPLEMENTER,
        f"direct-implementer-{current.cell_id}",
        {"cell-input": (filenames["cell-input"], input_document)},
        provenance="oci-deterministic-worker",
    )
    implementation = _run_role(
        project_root,
        current,
        worker_image,
        role="implementer",
        context=implementer_context,
        artifacts={"cell-input": input_document},
    )
    documents.update(
        {
            "implementer-context": _document(implementer_context),
            "implementer-execution": implementation["execution"],
            "implementation": implementation["implementation"],
        }
    )
    observation_context = worker.fresh_role_context(
        worker.WorkerRole.OBSERVATION,
        f"direct-observation-{current.cell_id}",
        {
            "cell-input": (filenames["cell-input"], input_document),
            "implementation": (filenames["implementation"], documents["implementation"]),
        },
        provenance="oci-deterministic-worker",
    )
    observation = _run_role(
        project_root,
        current,
        worker_image,
        role="observation",
        context=observation_context,
        artifacts={"cell-input": input_document, "implementation": documents["implementation"]},
    )
    documents.update(
        {
            "observation-context": _document(observation_context),
            "observation-execution": observation["execution"],
            "observation": observation["observation"],
        }
    )
    documents["evidence-manifest"] = {
        "schema": "DirectDevelopmentEvidenceManifest.v2",
        "cell_id": current.cell_id,
        "entries": [
            _document(worker.artifact_reference(artifact_id, filenames[artifact_id], documents[artifact_id]))
            for artifact_id in ("implementation", "observation")
        ],
    }
    postmortem_context_id = f"direct-postmortem-{current.cell_id}"
    documents["postmortem-request"] = {
        "schema": "DirectPostmortemRequest.v1",
        "request_id": "postreq-" + canonical_digest({"cell_id": current.cell_id})[:24],
        "run_id": store.load_state().run_id,
        "cell_id": current.cell_id,
        "fresh_context_id": postmortem_context_id,
        "artifact_manifest_digest": canonical_digest(documents["evidence-manifest"]),
        "implementation_digest": canonical_digest(documents["implementation"]),
        "observation_digest": canonical_digest(documents["observation"]),
        "evaluation_receipt_id": documents["observation"]["receipt_id"],
    }
    postmortem_context = worker.fresh_role_context(
        worker.WorkerRole.POSTMORTEM,
        postmortem_context_id,
        {
            "evidence-manifest": (filenames["evidence-manifest"], documents["evidence-manifest"]),
            "implementation": (filenames["implementation"], documents["implementation"]),
            "observation": (filenames["observation"], documents["observation"]),
            "postmortem-request": (filenames["postmortem-request"], documents["postmortem-request"]),
        },
        provenance="oci-deterministic-worker",
    )
    worker.require_distinct_fresh_contexts(implementer_context, observation_context, postmortem_context)
    postmortem_result = _run_role(
        project_root,
        current,
        worker_image,
        role="postmortem",
        context=postmortem_context,
        artifacts={
            "evidence-manifest": documents["evidence-manifest"],
            "implementation": documents["implementation"],
            "observation": documents["observation"],
            "postmortem-request": documents["postmortem-request"],
        },
    )
    documents.update(
        {
            "postmortem-context": _document(postmortem_context),
            "postmortem-execution": postmortem_result["execution"],
            "postmortem-report": postmortem_result["postmortem-report"],
        }
    )
    return _write_lifecycle_terminal(
        store,
        current,
        worker,
        documents,
        semantic_result=documents["observation"]["observation_result"],
    )


def _run_planned_lifecycle(
    store: StateStore,
    current: CellRecord,
    worker: Any,
    input_document: Mapping[str, Any],
    project_root: Path,
    worker_image: str,
    *,
    native_v1: bool,
) -> tuple[str, str]:
    postmortem = _lazy_module("postmortem")
    filenames = worker.LIFECYCLE_ARTIFACT_FILENAMES
    documents: dict[str, Any] = {"cell-input": dict(input_document)}
    planner_context = worker.fresh_role_context(
        worker.WorkerRole.PLANNER,
        f"{'native-v1' if native_v1 else 'planner'}-{current.cell_id}",
        {"cell-input": (filenames["cell-input"], input_document)},
        provenance="oci-deterministic-worker",
    )
    planner = _run_role(
        project_root,
        current,
        worker_image,
        role="planner",
        context=planner_context,
        artifacts={"cell-input": input_document},
        native_v1=native_v1,
    )
    documents.update(
        {
            "planner-context": _document(planner_context),
            "planner-execution": planner["execution"],
            "handoff": planner["handoff"],
            "build-contract": planner["build-contract"],
        }
    )
    if native_v1:
        documents["native-v1-runtime"] = planner["native-v1-runtime"]
    implementer_context = worker.fresh_role_context(
        worker.WorkerRole.IMPLEMENTER,
        f"implementer-{current.cell_id}",
        {
            "build-contract": (filenames["build-contract"], documents["build-contract"]),
            "handoff": (filenames["handoff"], documents["handoff"]),
        },
        provenance="oci-deterministic-worker",
    )
    implementation = _run_role(
        project_root,
        current,
        worker_image,
        role="implementer",
        context=implementer_context,
        artifacts={"build-contract": documents["build-contract"], "handoff": documents["handoff"]},
    )
    documents.update(
        {
            "implementer-context": _document(implementer_context),
            "implementer-execution": implementation["execution"],
            "implementation": implementation["implementation"],
        }
    )
    observation_context = worker.fresh_role_context(
        worker.WorkerRole.OBSERVATION,
        f"observation-{current.cell_id}",
        {
            "build-contract": (filenames["build-contract"], documents["build-contract"]),
            "implementation": (filenames["implementation"], documents["implementation"]),
        },
        provenance="oci-deterministic-worker",
    )
    observation = _run_role(
        project_root,
        current,
        worker_image,
        role="observation",
        context=observation_context,
        artifacts={"build-contract": documents["build-contract"], "implementation": documents["implementation"]},
    )
    documents.update(
        {
            "observation-context": _document(observation_context),
            "observation-execution": observation["execution"],
            "observation": observation["observation"],
        }
    )
    documents["evidence-manifest"] = {
        "schema": "DevelopmentEvidenceManifest.v2",
        "cell_id": current.cell_id,
        "entries": [
            _document(worker.artifact_reference(artifact_id, filenames[artifact_id], documents[artifact_id]))
            for artifact_id in ("build-contract", "implementation", "observation")
        ],
    }
    postmortem_context_id = f"postmortem-{current.cell_id}"
    request = postmortem.PostmortemRequest(
        request_id="postreq-" + canonical_digest({"cell_id": current.cell_id})[:24],
        run_id=store.load_state().run_id,
        cell_id=current.cell_id,
        artifact_manifest_digest=canonical_digest(documents["evidence-manifest"]),
        build_contract_digest=canonical_digest(documents["build-contract"]),
        implementation_digest=canonical_digest(documents["implementation"]),
        observation_digest=canonical_digest(documents["observation"]),
        evaluation_receipt_id=documents["observation"]["receipt_id"],
        fresh_context_id=postmortem_context_id,
    )
    documents["postmortem-request"] = _document(request)
    postmortem_context = worker.fresh_role_context(
        worker.WorkerRole.POSTMORTEM,
        postmortem_context_id,
        {
            "build-contract": (filenames["build-contract"], documents["build-contract"]),
            "evidence-manifest": (filenames["evidence-manifest"], documents["evidence-manifest"]),
            "implementation": (filenames["implementation"], documents["implementation"]),
            "observation": (filenames["observation"], documents["observation"]),
            "postmortem-request": (filenames["postmortem-request"], documents["postmortem-request"]),
        },
        provenance="oci-deterministic-worker",
    )
    worker.require_distinct_fresh_contexts(
        planner_context,
        implementer_context,
        observation_context,
        postmortem_context,
    )
    postmortem_result = _run_role(
        project_root,
        current,
        worker_image,
        role="postmortem",
        context=postmortem_context,
        artifacts={
            "build-contract": documents["build-contract"],
            "evidence-manifest": documents["evidence-manifest"],
            "implementation": documents["implementation"],
            "observation": documents["observation"],
            "postmortem-request": documents["postmortem-request"],
        },
    )
    documents.update(
        {
            "postmortem-context": _document(postmortem_context),
            "postmortem-execution": postmortem_result["execution"],
            "postmortem-report": postmortem_result["postmortem-report"],
        }
    )
    return _write_lifecycle_terminal(
        store,
        current,
        worker,
        documents,
        semantic_result=documents["observation"]["observation_result"],
    )


def _run_fake_lifecycle(
    store: StateStore,
    current: CellRecord,
    project_root: Path,
    worker_image: str,
) -> tuple[str, str]:
    worker = _lazy_module("worker")
    filenames = worker.LIFECYCLE_ARTIFACT_FILENAMES
    input_document = read_canonical_json(store.cells_dir / current.cell_id / filenames["cell-input"])
    if canonical_digest(input_document) != current.input_digest:
        raise StateError(f"cell input digest drift: {current.cell_id}")
    if current.identity.arm_id == "direct-v1":
        return _run_direct_lifecycle(store, current, worker, input_document, project_root, worker_image)
    if current.identity.arm_id == "plan-v1":
        return _run_planned_lifecycle(
            store, current, worker, input_document, project_root, worker_image, native_v1=False
        )
    if current.identity.arm_id == "ultimateinterview-current-v1-structural":
        return _run_planned_lifecycle(
            store, current, worker, input_document, project_root, worker_image, native_v1=True
        )
    raise CliError(EXIT_BLOCKED, f"unsupported scored arm lifecycle: {current.identity.arm_id}")


def _run_fake_cells(
    store: StateStore,
    config: RunConfig,
    project_root: Path,
    worker_image: str,
) -> RunState:
    """Run every scored arm through OCI-authoritative deterministic role work."""

    try:
        store.recover_leases()
        state = store.set_run_status(RunStatus.RUNNING)
        for original in state.cells:
            current = store.lease_cell(original.cell_id, config.max_attempts)
            if current.status in TERMINAL_CELL_STATUSES:
                continue
            attempt_digest, terminal_digest = _run_fake_lifecycle(
                store, current, project_root, worker_image
            )
            store.commit_terminal_cell(
                current.cell_id,
                current.fence,
                CellStatus.COMPLETED,
                attempt_digest,
                terminal_digest,
            )
        state = store.load_state()
        if any(cell.status not in TERMINAL_CELL_STATUSES for cell in state.cells):
            raise StateError("fake run ended with non-terminal cells")
        return store.set_run_status(RunStatus.COMPLETE)
    except CliError:
        raise
    except (StateError, ValidationError, TypeError, ValueError) as error:
        raise CliError(EXIT_RUNTIME_FAILURE, str(error)) from error


def _cmd_worker_stage(args: argparse.Namespace) -> int:
    role_worker = _lazy_module("role_worker")
    try:
        role_worker.stage_input(Path.cwd(), sys.stdin.buffer.read(), args.input_digest)
    except (OSError, ValueError) as error:
        raise CliError(EXIT_INVALID, f"worker input staging failed: {error}") from error
    return EXIT_COMPLETE


def _cmd_worker_role(args: argparse.Namespace) -> int:
    role_worker = _lazy_module("role_worker")
    try:
        role_worker.execute_staged_role(Path.cwd(), role=args.role, input_digest=args.input_digest)
    except (OSError, ValueError) as error:
        raise CliError(EXIT_RUNTIME_FAILURE, f"worker role execution failed: {error}") from error
    return EXIT_COMPLETE


def _cmd_worker_read_output(args: argparse.Namespace) -> int:
    role_worker = _lazy_module("role_worker")
    try:
        sys.stdout.buffer.write(role_worker.read_output(Path.cwd(), args.input_digest))
    except (OSError, ValueError) as error:
        raise CliError(EXIT_INVALID, f"worker output read failed: {error}") from error
    return EXIT_COMPLETE


def _cmd_validate_corpus(args: argparse.Namespace) -> int:
    corpus_root = Path(args.public_root)
    _load_cases(corpus_root, args.partition)
    _emit({"schema": "CorpusValidationReceipt.v1", "partition": args.partition, "status": "valid"})
    return EXIT_COMPLETE


def _cmd_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config, config_digest = _load_config(config_path)
    if args.partition is not None and args.partition != config.partition:
        raise CliError(EXIT_INVALID, "--partition must match the digest-bound config partition")
    if config.partition != "dev":
        raise CliError(EXIT_UNSAFE_LOCAL, "local controller only accepts the development partition")
    if config.mode is not RunMode.FAKE_DEV:
        raise CliError(EXIT_BLOCKED, "live/provider execution is unavailable in this standalone controller")
    _require_scored_arm_allowlist(
        [arm.arm_id for arm in config.arms],
        code=EXIT_BLOCKED,
    )
    try:
        validate_worker_image_identity(args.worker_image)
    except ValueError as error:
        raise CliError(EXIT_INVALID, f"invalid worker image: {error}") from error

    corpus_root = _resolve_config_relative(config_path, config.corpus_root)
    cases, corpus_digest = _load_cases(corpus_root, config.partition)
    arm_digests = _load_arm_digests(config, config_path)
    deterministic_run_id = _run_id(config_digest, corpus_digest, arm_digests, args.worker_image)
    project_root = _project_root(config_path)
    run_dir = Path(args.run_dir) if args.run_dir is not None else _project_root(config_path) / "runs" / deterministic_run_id
    store = StateStore(run_dir)

    if store.has_state():
        if not args.resume:
            raise CliError(EXIT_INCOMPATIBLE_RESUME, "run artifacts already exist; --resume is required")
        manifest, state = _bound_resume_check(
            store,
            config_digest,
            corpus_digest,
            arm_digests,
            args.worker_image,
        )
    else:
        if args.run_dir is not None and run_dir.exists() and any(run_dir.iterdir()):
            raise CliError(EXIT_INCOMPATIBLE_RESUME, "run directory contains unrecognized artifacts")
        cells = _cell_inputs(config, config_digest, corpus_digest, cases, arm_digests)
        manifest = RunManifest(
            run_id=deterministic_run_id,
            release_id=config.release_id,
            mode=config.mode,
            partition=config.partition,
            config_digest=config_digest,
            corpus_digest=corpus_digest,
            arm_digests=arm_digests,
            worker_image=args.worker_image,
            status=RunStatus.CREATED,
        )
        state = RunState(
            run_id=deterministic_run_id,
            status=RunStatus.CREATED,
            config_digest=config_digest,
            corpus_digest=corpus_digest,
            arm_digests=arm_digests,
            worker_image=args.worker_image,
            cells=cells,
        )
        try:
            store.initialize(manifest, state)
        except StateError as error:
            raise CliError(EXIT_INCOMPATIBLE_RESUME, str(error)) from error

    _write_cell_inputs(store, config, config_digest, cases, arm_digests, state)
    if state.status is not RunStatus.COMPLETE:
        try:
            state = store.set_run_status(RunStatus.PREFLIGHTED)
            store.save_manifest(_rebuild_manifest(manifest, RunStatus.PREFLIGHTED))
        except StateError as error:
            raise CliError(EXIT_RUNTIME_FAILURE, str(error)) from error
        try:
            state = _run_fake_cells(store, config, project_root, args.worker_image)
        except CliError as error:
            if error.code == EXIT_BLOCKED:
                state = store.set_run_status(RunStatus.BLOCKED)
                manifest = _rebuild_manifest(manifest, RunStatus.BLOCKED)
                store.save_manifest(manifest)
                _write_status(store, config, state, str(error))
            raise
        manifest = _rebuild_manifest(manifest, RunStatus.COMPLETE)
        store.save_manifest(manifest)
    else:
        state = store.load_state()

    _write_status(
        store,
        config,
        state,
        "deterministic development lifecycle completed with declared fresh-context artifact transfers",
    )
    result = _write_scorecard(store, config, state)
    _emit(
        {
            "schema": "RunReceipt.v1",
            "run_id": state.run_id,
            "status": state.status.value,
            "mode": config.mode.value,
            "score_exit": result,
            "claim": "deterministic-development-treatment",
        }
    )
    return result


def _config_for_existing_run(manifest: RunManifest) -> RunConfig:
    """Build the minimum public shape needed to score a manifest-bound fake run."""

    return RunConfig(
        mode=manifest.mode,
        release_id=manifest.release_id,
        corpus_root="bound-in-manifest",
        arms=tuple(ArmDefinition(arm_id=arm_id, source="bound-in-manifest") for arm_id in manifest.arm_digests),
        models={"planner": "bound", "implementer": "bound", "postmortem": "bound"},
        seed_label="bound-in-manifest",
        partition=manifest.partition,
    )


def _cmd_resume(args: argparse.Namespace) -> int:
    store = StateStore(Path(args.run_dir))
    try:
        validate_worker_image_identity(args.worker_image)
    except ValueError as error:
        raise CliError(EXIT_INVALID, f"invalid worker image: {error}") from error
    try:
        manifest = store.load_manifest()
    except StateError as error:
        raise CliError(EXIT_BLOCKED, str(error)) from error
    if manifest.partition != "dev":
        raise CliError(EXIT_UNSAFE_LOCAL, "local controller only resumes development runs")
    config = _config_for_existing_run(manifest)
    if manifest.mode is not RunMode.FAKE_DEV:
        raise CliError(EXIT_BLOCKED, "only fake-development runs can resume in this controller")
    try:
        state = store.load_state()
        _require_manifest_state_closure(manifest, state)
    except StateError as error:
        raise CliError(EXIT_INCOMPATIBLE_RESUME, str(error)) from error
    if manifest.worker_image != args.worker_image or state.worker_image != args.worker_image:
        raise CliError(EXIT_INCOMPATIBLE_RESUME, "resume worker image drift")
    if state.status is not RunStatus.COMPLETE:
        try:
            state = _run_fake_cells(store, config, Path(args.project_root), args.worker_image)
        except CliError as error:
            if error.code == EXIT_BLOCKED:
                state = store.set_run_status(RunStatus.BLOCKED)
                manifest = _rebuild_manifest(manifest, RunStatus.BLOCKED)
                store.save_manifest(manifest)
                _write_status(store, config, state, str(error))
            raise
    manifest = _rebuild_manifest(manifest, RunStatus.COMPLETE)
    store.save_manifest(manifest)
    _write_status(
        store,
        config,
        state,
        "deterministic development lifecycle resumed with declared fresh-context artifact transfers",
    )
    result = _write_scorecard(store, config, state)
    _emit(
        {
            "schema": "ResumeReceipt.v1",
            "run_id": state.run_id,
            "status": state.status.value,
            "score_exit": result,
            "claim": "deterministic-development-treatment",
        }
    )
    return result


def _cmd_score(args: argparse.Namespace) -> int:
    store = StateStore(Path(args.run_dir))
    try:
        manifest = store.load_manifest()
        state = store.load_state()
        _require_manifest_state_closure(manifest, state)
    except StateError as error:
        raise CliError(EXIT_BLOCKED, str(error)) from error
    if manifest.partition != "dev":
        raise CliError(EXIT_UNSAFE_LOCAL, "local controller cannot score holdout/private results")
    config = _config_for_existing_run(manifest)
    result = _write_scorecard(store, config, state)
    _emit(
        {
            "schema": "ScoreReceipt.v1",
            "run_id": state.run_id,
            "score_exit": result,
            "claim": "deterministic-development-treatment",
        }
    )
    return result


def _cmd_inspect_safe(args: argparse.Namespace) -> int:
    store = StateStore(Path(args.run_dir))
    try:
        state = store.load_state()
    except StateError as error:
        raise CliError(EXIT_BLOCKED, str(error)) from error
    cell = next((item for item in state.cells if item.cell_id == args.cell), None)
    if cell is None:
        raise CliError(EXIT_INVALID, f"unknown cell: {args.cell}")
    _emit(
        {
            "schema": "SafeCellInspection.v1",
            "run_id": state.run_id,
            "cell_id": cell.cell_id,
            "status": cell.status.value,
            "attempt": cell.attempt,
            "fence": cell.fence,
            "input_digest": cell.input_digest,
            "terminal_receipt_digest": cell.terminal_receipt_digest,
        }
    )
    return EXIT_COMPLETE


def _cmd_gc(args: argparse.Namespace) -> int:
    store = StateStore(Path(args.run_dir))
    try:
        manifest = store.load_manifest()
    except StateError as error:
        raise CliError(EXIT_BLOCKED, str(error)) from error
    if args.confirm != manifest.run_id:
        raise CliError(EXIT_INVALID, "--confirm must exactly match the run ID")
    removed = 0
    try:
        with store.locked():
            for path in store.run_dir.rglob(".*"):
                if path.name == ".state.lock" or path.is_symlink() or not path.is_file():
                    continue
                path.unlink()
                removed += 1
    except OSError as error:
        raise CliError(EXIT_RUNTIME_FAILURE, f"safe garbage collection failed: {error}") from error
    _emit({"schema": "GcReceipt.v1", "run_id": manifest.run_id, "removed_orphan_files": removed})
    return EXIT_COMPLETE


def build_parser() -> DriftArgumentParser:
    parser = DriftArgumentParser(prog="driftbench")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-corpus")
    validate.add_argument("--public-root", required=True)
    validate.add_argument("--partition", choices=("dev",), default="dev")
    validate.set_defaults(handler=_cmd_validate_corpus)
    worker_stage = commands.add_parser("worker-stage")
    worker_stage.add_argument("--input-digest", required=True)
    worker_stage.set_defaults(handler=_cmd_worker_stage)

    worker_role = commands.add_parser("worker-role")
    worker_role.add_argument("--role", choices=("planner", "implementer", "observation", "postmortem"), required=True)
    worker_role.add_argument("--input-digest", required=True)
    worker_role.set_defaults(handler=_cmd_worker_role)

    worker_read = commands.add_parser("worker-read-output")
    worker_read.add_argument("--input-digest", required=True)
    worker_read.set_defaults(handler=_cmd_worker_read_output)

    run = commands.add_parser("run")
    run.add_argument("--config", required=True)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--run-dir")
    run.add_argument("--partition", choices=("dev",))
    run.add_argument("--worker-image", required=True)
    run.set_defaults(handler=_cmd_run)

    resume = commands.add_parser("resume")
    resume.add_argument("--run-dir", required=True)
    resume.add_argument("--project-root", default=str(Path.cwd()))
    resume.add_argument("--worker-image", required=True)
    resume.set_defaults(handler=_cmd_resume)

    score = commands.add_parser("score")
    score.add_argument("--run-dir", required=True)
    score.set_defaults(handler=_cmd_score)

    inspect_safe = commands.add_parser("inspect-safe")
    inspect_safe.add_argument("--run-dir", required=True)
    inspect_safe.add_argument("--cell", required=True)
    inspect_safe.set_defaults(handler=_cmd_inspect_safe)

    gc = commands.add_parser("gc")
    gc.add_argument("--run-dir", required=True)
    gc.add_argument("--confirm", required=True)
    gc.set_defaults(handler=_cmd_gc)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.handler(args)
    except KeyboardInterrupt:
        _error("cancelled")
        return EXIT_CANCELLED
    except CliError as error:
        _error(str(error))
        return error.code
    except (StateError, OSError) as error:
        _error(str(error))
        return EXIT_RUNTIME_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
