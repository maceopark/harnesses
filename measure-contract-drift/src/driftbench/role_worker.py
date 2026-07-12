"""Canonical, volume-backed role work executed inside the OCI worker image."""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any

from . import corpus
from .postmortem import FakePostmortemClient, PostmortemRequest
from .semantic import Assertion, ExecutableObservation, compare_assertions
from .state import canonical_bytes, canonical_digest
from .worker import (
    DETERMINISTIC_STARTER_IMPLEMENTATION,
    FakeDevelopmentAdapter,
    FakeWorkerClient,
    FreshRoleContext,
    WorkerRole,
    WorkerSessionError,
    _derived_identifier,
    transferred_artifacts,
)

INPUT_FILENAME = "input.json"
OUTPUT_FILENAME = "output.json"
INPUT_SCHEMA = "RoleWorkInput.v1"
OUTPUT_SCHEMA = "RoleWorkOutput.v1"
WORKER_PROVENANCE = "oci-deterministic-worker"
_PUBLIC_ROOT = Path("/opt/driftbench/corpus/public")
_NATIVE_ROOT = Path("/opt/driftbench/protocol/ultimateinterview/ui-native-77b0327-r4")
_COMMANDS: dict[str, tuple[str, ...]] = {
    "bookmarks": ("bookmark", "tag", "bm-1", "reading"),
    "config-merge": ("config", "merge", "team"),
    "contacts-csv": ("contacts", "import", "incoming.csv"),
    "expense": ("expense", "add", "9", "tea"),
    "reminder": ("reminder", "add", "Call Ada", "Monday"),
    "todo": ("todo", "complete", "todo-1"),
}

_STATE_FILENAMES: dict[str, str] = {
    "bookmarks": "bookmarks.json",
    "config-merge": "config.json",
    "contacts-csv": "contacts.json",
    "expense": "expenses.json",
    "reminder": "reminders.json",
    "todo": "todos.json",
}
_CASE_STATE_EFFECTS: dict[str, str] = {
    "bookmarks": "bookmark-tag-added",
    "config-merge": "named-overlay-merged",
    "contacts-csv": "csv-contacts-imported",
    "expense": "expense-recorded",
    "reminder": "reminder-created",
    "todo": "todo-completed",
}
_CONFIG_OVERLAYS: dict[str, dict[str, Any]] = {
    "team": {"retries": 2, "timeout": 45},
}
_IMPLEMENTED_STARTER_SOURCE = """#!/usr/bin/env python3
\"\"\"Deterministic implementation for DriftBench public starter contracts.\"\"\"

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys

OPERATIONS = {
    "bookmarks.json": ("bookmarks", ("bookmark", "tag"), 4),
    "config.json": ("config-merge", ("config", "merge"), 3),
    "contacts.json": ("contacts-csv", ("contacts", "import"), 3),
    "expenses.json": ("expense", ("expense", "add"), 4),
    "reminders.json": ("reminder", ("reminder", "add"), 4),
    "todos.json": ("todo", ("todo", "complete"), 3),
}
OVERLAYS = {"team": {"retries": 2, "timeout": 45}}


class OperationError(ValueError):
    pass


def _state_file(root: Path) -> tuple[str, Path, tuple[str, ...], int]:
    matches = [
        (case_id, root / name, command, argc)
        for name, (case_id, command, argc) in OPERATIONS.items()
        if (root / name).is_file()
    ]
    if len(matches) != 1:
        raise RuntimeError("starter must contain exactly one known state file")
    return matches[0]


def _emit(
    *,
    case_id: str,
    argv: list[str],
    status: str,
    exit_code: int,
    changed: bool,
    state_file: Path,
) -> None:
    print(
        json.dumps(
            {
                "argv": argv,
                "case_id": case_id,
                "changed": changed,
                "exit_code": exit_code,
                "schema": "StarterObservation.v1",
                "state_file": state_file.name,
                "state_sha256": hashlib.sha256(state_file.read_bytes()).hexdigest(),
                "status": status,
            },
            sort_keys=True,
        )
    )


def _load_state(state_file: Path) -> dict[str, object]:
    value = json.loads(state_file.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OperationError("state must be a JSON object")
    return value


def _write_state(state_file: Path, value: dict[str, object]) -> None:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    temporary = state_file.with_name(f".{state_file.name}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.write_bytes(payload)
    temporary.replace(state_file)


def _bookmarks(state: dict[str, object], args: list[str]) -> None:
    bookmarks = state.get("bookmarks")
    if not isinstance(bookmarks, list):
        raise OperationError("bookmarks state is invalid")
    bookmark = next(
        (item for item in bookmarks if isinstance(item, dict) and item.get("id") == args[2]),
        None,
    )
    if bookmark is None or not isinstance(bookmark.get("tags"), list):
        raise OperationError("bookmark is unknown or invalid")
    tag = args[3].strip()
    if not tag or tag in bookmark["tags"]:
        raise OperationError("tag is invalid or already present")
    bookmark["tags"].append(tag)


def _config_merge(state: dict[str, object], args: list[str]) -> None:
    overlay = OVERLAYS.get(args[2])
    if overlay is None:
        raise OperationError("overlay is unknown")
    state.update(overlay)


def _contacts(root: Path, state: dict[str, object], args: list[str]) -> None:
    contacts = state.get("contacts")
    source = root / args[2]
    if (
        not isinstance(contacts, list)
        or source.parent != root
        or source.is_symlink()
        or not source.is_file()
    ):
        raise OperationError("contact source is unavailable")
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "email"]:
            raise OperationError("contact CSV headers are invalid")
        imported: list[dict[str, str]] = []
        for row in reader:
            if not isinstance(row, dict) or set(row) != {"name", "email"}:
                raise OperationError("contact CSV row is malformed")
            raw_name = row["name"]
            raw_email = row["email"]
            if not isinstance(raw_name, str) or not isinstance(raw_email, str):
                raise OperationError("contact CSV row is malformed")
            name = raw_name.strip()
            email = raw_email.strip()
            if not name or "@" not in email:
                raise OperationError("contact CSV row is malformed")
            imported.append({"name": name, "email": email})
    if not imported:
        raise OperationError("contact CSV has no rows")
    contacts.extend(imported)


def _expense(state: dict[str, object], args: list[str]) -> None:
    expenses = state.get("expenses")
    if not isinstance(expenses, list) or not args[3].strip():
        raise OperationError("expense state or note is invalid")
    try:
        amount = Decimal(args[2])
    except InvalidOperation as error:
        raise OperationError("expense amount is invalid") from error
    if not amount.is_finite() or amount < 0:
        raise OperationError("expense amount is invalid")
    recorded_amount: int | float
    if amount == amount.to_integral_value():
        recorded_amount = int(amount)
    else:
        recorded_amount = float(amount)
    expenses.append({"amount": recorded_amount, "note": args[3]})


def _reminder(state: dict[str, object], args: list[str]) -> None:
    reminders = state.get("reminders")
    if not isinstance(reminders, list) or not args[2].strip() or not args[3].strip():
        raise OperationError("reminder text or due label is invalid")
    reminders.append({"text": args[2], "due": args[3]})


def _todo(state: dict[str, object], args: list[str]) -> None:
    todos = state.get("todos")
    if not isinstance(todos, list):
        raise OperationError("todo state is invalid")
    todo = next(
        (item for item in todos if isinstance(item, dict) and item.get("id") == args[2]),
        None,
    )
    if todo is None or todo.get("done") is not False:
        raise OperationError("todo is unknown or already complete")
    todo["done"] = True


def _apply(root: Path, case_id: str, state: dict[str, object], args: list[str]) -> None:
    if case_id == "bookmarks":
        _bookmarks(state, args)
    elif case_id == "config-merge":
        _config_merge(state, args)
    elif case_id == "contacts-csv":
        _contacts(root, state, args)
    elif case_id == "expense":
        _expense(state, args)
    elif case_id == "reminder":
        _reminder(state, args)
    elif case_id == "todo":
        _todo(state, args)
    else:
        raise OperationError("unsupported public starter")


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(__file__).resolve().parent
    try:
        case_id, state_file, command, argc = _state_file(root)
    except RuntimeError as error:
        print(json.dumps({"error": str(error), "exit_code": 70, "schema": "StarterObservation.v1", "status": "invalid_starter"}, sort_keys=True))
        return 70
    if len(args) != argc or tuple(args[:2]) != command:
        _emit(
            case_id=case_id,
            argv=args,
            status="invalid_invocation",
            exit_code=64,
            changed=False,
            state_file=state_file,
        )
        return 64
    try:
        state = _load_state(state_file)
        _apply(root, case_id, state, args)
    except (OSError, json.JSONDecodeError, OperationError):
        _emit(
            case_id=case_id,
            argv=args,
            status="operation_failed",
            exit_code=1,
            changed=False,
            state_file=state_file,
        )
        return 1
    try:
        _write_state(state_file, state)
    except (OSError, TypeError, ValueError):
        _emit(
            case_id=case_id,
            argv=args,
            status="operation_failed",
            exit_code=70,
            changed=False,
            state_file=state_file,
        )
        return 70
    _emit(
        case_id=case_id,
        argv=args,
        status="completed",
        exit_code=0,
        changed=True,
        state_file=state_file,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
_IMPLEMENTED_CONTACTS_CSV = "name,email\nGrace,grace@example.test\n"


class RoleWorkError(ValueError):
    """Raised when a volume-backed role input or output is invalid."""


def stage_input(workspace: Path, payload: bytes, expected_digest: str) -> None:
    """Validate canonical stdin bytes and stage exactly one digest-bound input."""

    if sha256(payload).hexdigest() != expected_digest:
        raise RoleWorkError("staged input digest does not match --input-digest")
    document = _canonical_object(payload, "staged input")
    if canonical_bytes(document) != payload:
        raise RoleWorkError("staged input must use canonical JSON bytes")
    destination = workspace / INPUT_FILENAME
    if destination.exists() or destination.is_symlink():
        raise RoleWorkError("role workspace already contains an input artifact")
    destination.write_bytes(payload)


def read_output(workspace: Path, expected_input_digest: str) -> bytes:
    """Return only a canonical output bound to the staged input digest."""

    source = workspace / OUTPUT_FILENAME
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise RoleWorkError("role output is absent") from error
    document = _canonical_object(payload, "role output")
    if canonical_bytes(document) != payload:
        raise RoleWorkError("role output must use canonical JSON bytes")
    if document.get("schema") != OUTPUT_SCHEMA or document.get("input_digest") != expected_input_digest:
        raise RoleWorkError("role output is not bound to the staged input")
    return payload


def execute_staged_role(workspace: Path, *, role: str, input_digest: str) -> dict[str, Any]:
    """Execute one role against its staged canonical input and emit canonical output."""

    source = workspace / INPUT_FILENAME
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise RoleWorkError("role input is absent") from error
    if sha256(payload).hexdigest() != input_digest:
        raise RoleWorkError("role input digest does not match --input-digest")
    envelope = _canonical_object(payload, "role input")
    try:
        output = execute_role_input(role, envelope, input_digest=input_digest, workspace=workspace)
    except OSError as error:
        raise RoleWorkError(f"role work failed before output write: {error}") from error
    destination = workspace / OUTPUT_FILENAME
    if destination.exists() or destination.is_symlink():
        raise RoleWorkError("role workspace already contains an output artifact")
    try:
        destination.write_bytes(canonical_bytes(output))
    except OSError as error:
        raise RoleWorkError(f"cannot write canonical role output: {error}") from error
    return output


def execute_role_input(
    role: str,
    envelope: Mapping[str, Any],
    *,
    input_digest: str | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Run deterministic development work; this function is the unit-test runner only."""

    if not isinstance(envelope, Mapping) or envelope.get("schema") != INPUT_SCHEMA:
        raise RoleWorkError("role input must be a RoleWorkInput.v1 object")
    if envelope.get("role") != role:
        raise RoleWorkError("role input role does not match invocation")
    binding_digest = envelope.get("binding_digest")
    if not _is_digest(binding_digest):
        raise RoleWorkError("role input lacks a binding digest")
    context_document = envelope.get("context")
    artifacts = envelope.get("artifacts")
    if not isinstance(context_document, Mapping) or not isinstance(artifacts, Mapping):
        raise RoleWorkError("role input requires context and artifacts objects")
    try:
        context = FreshRoleContext.model_validate_json(canonical_bytes(context_document))
    except Exception as error:
        raise RoleWorkError(f"role input context is invalid: {error}") from error
    if context.role.value != role:
        raise RoleWorkError("role context does not match invocation")
    try:
        received = transferred_artifacts(context, artifacts)
    except WorkerSessionError as error:
        raise RoleWorkError(str(error)) from error
    actual_input_digest = canonical_digest(envelope)
    if input_digest is not None and input_digest != actual_input_digest:
        raise RoleWorkError("role input canonical digest drift")

    adapter = FakeDevelopmentAdapter(
        worker_client=FakeWorkerClient(provenance=WORKER_PROVENANCE),
        postmortem_client=FakePostmortemClient(provenance=WORKER_PROVENANCE),
    )
    working_directory = workspace or Path.cwd()
    documents = _execute(role, context, received, envelope, adapter, working_directory)
    return {
        "schema": OUTPUT_SCHEMA,
        "role": role,
        "input_digest": actual_input_digest,
        "binding_digest": binding_digest,
        "context_digest": canonical_digest(context),
        "documents": documents,
        "provenance": WORKER_PROVENANCE,
    }


def _execute(
    role: str,
    context: FreshRoleContext,
    artifacts: Mapping[str, Any],
    envelope: Mapping[str, Any],
    adapter: FakeDevelopmentAdapter,
    workspace: Path,
) -> dict[str, Any]:
    if role == WorkerRole.PLANNER.value:
        if envelope.get("native_v1") is True:
            runtime = _native_v1_runtime(artifacts["cell-input"])
            result = adapter.native_v1_planner(context, artifacts, runtime)
            return {
                "execution": result["execution"],
                "handoff": result["handoff"],
                "build-contract": result["build_contract"],
                "native-v1-runtime": runtime,
            }
        if envelope.get("native_v1") is not False:
            raise RoleWorkError("planner input must declare native_v1")
        result = adapter.planner(context, artifacts)
        return {
            "execution": result["execution"],
            "handoff": result["handoff"],
            "build-contract": result["build_contract"],
        }
    if role == WorkerRole.IMPLEMENTER.value:
        if context.source_role is None:
            result = adapter.direct_implementer(context, artifacts)
            case_contract = _mapping(artifacts["cell-input"].get("case_contract"), "case contract")
        else:
            result = adapter.implementer(context, artifacts)
            case_contract = _mapping(result["implementation"].get("case_contract"), "case contract")
        implementation = dict(result["implementation"])
        materialized = _materialize_starter(
            workspace,
            case_contract,
            recipe=_implementation_recipe(implementation),
        )
        implementation["starter"] = materialized
        return {"execution": result["execution"], "implementation": implementation}
    if role == WorkerRole.OBSERVATION.value:
        return _observe(context, artifacts, adapter, workspace)
    if role == WorkerRole.POSTMORTEM.value:
        request_document = artifacts["postmortem-request"]
        request: Any
        if request_document.get("schema") == "DirectPostmortemRequest.v1":
            request = request_document
        else:
            try:
                request = PostmortemRequest.model_validate_json(canonical_bytes(request_document))
            except Exception as error:
                raise RoleWorkError(f"postmortem request is invalid: {error}") from error
        result = adapter.postmortem(context, artifacts, request)
        return {"execution": result["execution"], "postmortem-report": result["report"]}
    raise RoleWorkError("unknown worker role")


def _observe(
    context: FreshRoleContext,
    artifacts: Mapping[str, Any],
    adapter: FakeDevelopmentAdapter,
    workspace: Path,
) -> dict[str, Any]:
    implementation = _mapping(artifacts["implementation"], "implementation")
    starter = _mapping(implementation.get("starter"), "implementation starter")
    case_contract = _mapping(starter.get("case_contract"), "case contract")
    materialized = _materialize_starter(
        workspace,
        case_contract,
        recipe=_implementation_recipe(implementation),
    )
    _require_materialized_implementation(starter, materialized)
    case_id = str(case_contract.get("case_id", ""))
    command = _COMMANDS.get(case_id)
    state_filename = _STATE_FILENAMES.get(case_id)
    if command is None or state_filename is None:
        raise RoleWorkError("observation cannot select a public starter command")
    starter_directory = workspace / "starter"
    state_file = starter_directory / state_filename
    pre_state_digest, pre_state, pre_state_text = _state_snapshot(state_file)
    command_source = _command_source_snapshot(starter_directory, case_id, command)
    completed = subprocess.run(
        [sys.executable, "cli.py", *command],
        cwd=starter_directory,
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
    )
    if completed.stderr:
        raise RoleWorkError("starter observation emitted stderr")
    try:
        starter_observation = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RoleWorkError("starter observation emitted invalid JSON") from error
    if not isinstance(starter_observation, Mapping) or starter_observation.get("schema") != "StarterObservation.v1":
        raise RoleWorkError("starter observation has an invalid schema")
    post_state_digest, post_state, post_state_text = _state_snapshot(state_file)
    starter_execution = {
        "argv": ["python", "cli.py", *command],
        "exit_code": completed.returncode,
        "stdout_digest": sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "starter_observation": dict(starter_observation),
        "materialized_starter_digest": materialized["materialized_digest"],
        "pre_state": pre_state,
        "pre_state_sha256": pre_state_digest,
        "pre_state_text": pre_state_text,
        "post_state": post_state,
        "post_state_sha256": post_state_digest,
        "post_state_text": post_state_text,
        "command_source": command_source,
    }
    expected_assertion = _expected_assertion(implementation)
    replay = replay_observation_evidence(case_contract, starter_execution)
    if replay["expected_assertion"] != expected_assertion:
        raise RoleWorkError("implementation assertion drifts from immutable case contract")
    actual_assertion = replay["actual_assertion"]
    comparison = compare_assertions(expected_assertion, actual_assertion).model_dump(mode="json")
    observation_result = replay["observation_result"]
    executable = ExecutableObservation(
        result=observation_result,
        assertion=Assertion.model_validate_json(canonical_bytes(actual_assertion))
        if observation_result == "observed"
        else None,
    )
    build_digest = implementation.get("build_contract_digest")
    observation: dict[str, Any] = {
        "schema": "DevelopmentObservation.v2",
        "receipt_id": _derived_identifier("observation", context.context_id),
        "cell_id": implementation.get("cell_id"),
        "implementation_digest": canonical_digest(implementation),
        "observation_result": executable.result,
        "starter_execution": starter_execution,
        "predicate_results": replay["predicate_results"],
        "expected_assertion": expected_assertion,
        "actual_assertion": actual_assertion,
        "comparison": comparison,
        "primary_credit": comparison["primary_credit"] if executable.result == "observed" else 0,
        "semantic_evidence_authoritative": (
            executable.result == "observed" and comparison["primary_credit"] == 1
        ),
        "provenance": WORKER_PROVENANCE,
    }
    if isinstance(build_digest, str):
        observation["build_contract_digest"] = build_digest
    else:
        observation["input_digest"] = implementation.get("input_digest")
    return {"execution": adapter._execution(context), "observation": observation}


def _materialize_starter(
    workspace: Path,
    case_contract: Mapping[str, Any],
    *,
    recipe: str,
) -> dict[str, Any]:
    case_id = case_contract.get("case_id")
    starter_tree = case_contract.get("starter_tree")
    starter_digest = case_contract.get("starter_digest")
    if not all(isinstance(item, str) for item in (case_id, starter_tree, starter_digest)):
        raise RoleWorkError("case contract lacks a starter binding")
    if recipe != DETERMINISTIC_STARTER_IMPLEMENTATION:
        raise RoleWorkError("implementation recipe is not approved for public starters")
    case = corpus.PublicCaseRecord(
        case_id=case_id,
        opaque_token="a1c2e3g4",
        prompt="public deterministic starter execution",
        starter_tree=starter_tree,
        starter_digest=starter_digest,
    )
    destination = workspace / "starter"
    if destination.exists():
        shutil.rmtree(destination)
    try:
        copied = corpus.materialize_starter_tree(_public_root_for_execution(), case, destination)
        changed_files = _apply_deterministic_implementation(copied, case_id)
        materialized_digest = corpus.starter_tree_digest(copied)
    except Exception as error:
        raise RoleWorkError(f"cannot materialize public starter: {error}") from error
    if materialized_digest == starter_digest:
        raise RoleWorkError("implemented starter must differ from its public placeholder")
    return {
        "case_contract": {
            "case_id": case_id,
            "starter_tree": starter_tree,
            "starter_digest": starter_digest,
        },
        "path": "starter",
        "source_digest": starter_digest,
        "materialized_digest": materialized_digest,
        "implementation_recipe": recipe,
        "implementation_source_digest": sha256(
            _IMPLEMENTED_STARTER_SOURCE.encode("utf-8")
        ).hexdigest(),
        "changed_files": list(changed_files),
    }


def _apply_deterministic_implementation(starter: Path, case_id: str) -> tuple[str, ...]:
    state_filename = _STATE_FILENAMES.get(case_id)
    if state_filename is None:
        raise RoleWorkError("public starter case has no deterministic implementation")
    cli = starter / "cli.py"
    state_file = starter / state_filename
    if (
        starter.is_symlink()
        or not starter.is_dir()
        or cli.is_symlink()
        or not cli.is_file()
        or state_file.is_symlink()
        or not state_file.is_file()
    ):
        raise RoleWorkError("public starter lacks writable regular implementation files")
    try:
        for path in (starter, cli, state_file):
            path.chmod(path.stat().st_mode | 0o200)
        cli.write_text(_IMPLEMENTED_STARTER_SOURCE, encoding="utf-8")
        changed_files = ["cli.py"]
        if case_id == "contacts-csv":
            incoming = starter / "incoming.csv"
            if incoming.exists() and (incoming.is_symlink() or not incoming.is_file()):
                raise RoleWorkError("contacts starter has an unsafe incoming.csv")
            incoming.write_text(_IMPLEMENTED_CONTACTS_CSV, encoding="utf-8")
            changed_files.append("incoming.csv")
    except OSError as error:
        raise RoleWorkError(f"cannot apply deterministic starter implementation: {error}") from error
    return tuple(changed_files)


def _implementation_recipe(implementation: Mapping[str, Any]) -> str:
    recipe = implementation.get("implementation_recipe")
    if recipe != DETERMINISTIC_STARTER_IMPLEMENTATION:
        raise RoleWorkError("implementation does not declare the deterministic starter recipe")
    return recipe


def _require_materialized_implementation(
    declared: Mapping[str, Any],
    materialized: Mapping[str, Any],
) -> None:
    required = (
        "case_contract",
        "path",
        "source_digest",
        "materialized_digest",
        "implementation_recipe",
        "implementation_source_digest",
        "changed_files",
    )
    if any(field not in declared for field in required):
        raise RoleWorkError("implementation lacks a replayable patched starter artifact")
    if (
        declared.get("path") != "starter"
        or declared.get("source_digest") != materialized.get("source_digest")
        or declared.get("materialized_digest") != materialized.get("materialized_digest")
        or declared.get("implementation_recipe") != DETERMINISTIC_STARTER_IMPLEMENTATION
        or declared.get("implementation_source_digest")
        != materialized.get("implementation_source_digest")
        or declared.get("changed_files") != materialized.get("changed_files")
        or canonical_digest(declared.get("case_contract"))
        != canonical_digest(materialized.get("case_contract"))
    ):
        raise RoleWorkError("implementation starter artifact does not match its replayed patch")
    if declared.get("materialized_digest") == declared.get("source_digest"):
        raise RoleWorkError("unimplemented starter cannot produce semantic evidence")


def _state_snapshot(path: Path) -> tuple[str | None, dict[str, Any] | None, str | None]:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None, None
    digest = sha256(payload).hexdigest()
    try:
        state = json.loads(text)
    except json.JSONDecodeError:
        return digest, None, text
    return (digest, dict(state), text) if isinstance(state, Mapping) else (digest, None, text)


def _command_source_snapshot(
    starter_directory: Path,
    case_id: str,
    command: tuple[str, ...],
) -> dict[str, str] | None:
    if case_id != "contacts-csv":
        return None
    source = starter_directory / command[2]
    try:
        payload = source.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return {
        "filename": command[2],
        "sha256": sha256(payload).hexdigest(),
        "text": text,
    }


def _case_behavior(
    case_contract: Mapping[str, Any],
) -> tuple[str, tuple[str, ...], str, str]:
    case_id = case_contract.get("case_id")
    if not isinstance(case_id, str):
        raise RoleWorkError("case contract lacks a case identifier")
    command = _COMMANDS.get(case_id)
    state_filename = _STATE_FILENAMES.get(case_id)
    effect = _CASE_STATE_EFFECTS.get(case_id)
    if command is None or state_filename is None or effect is None:
        raise RoleWorkError("case contract is not a scored public starter")
    required = ("starter_tree", "starter_digest")
    if any(not isinstance(case_contract.get(field), str) or not case_contract[field] for field in required):
        raise RoleWorkError("case contract lacks immutable public starter fields")
    return case_id, command, state_filename, effect


def _command_effect(command: tuple[str, ...]) -> str:
    return "argv=" + json.dumps(list(command), ensure_ascii=False, separators=(",", ":"))


def _expected_case_assertion(case_contract: Mapping[str, Any]) -> dict[str, Any]:
    case_id, command, state_filename, state_effect = _case_behavior(case_contract)
    guard = f"case={case_id}"
    boundary = f"state-file={state_filename}"
    return {
        "atoms": [
            {
                "guard": guard,
                "effect": _command_effect(command),
                "polarity": "must",
                "boundary": boundary,
                "temporal": "subprocess-terminal",
            },
            {
                "guard": guard,
                "effect": state_effect,
                "polarity": "must",
                "boundary": boundary,
                "temporal": "post-state",
            },
        ]
    }


def _observed_case_id(value: Any) -> str:
    return value if isinstance(value, str) and value in _COMMANDS else "unknown-case"


def _observed_state_filename(value: Any) -> str:
    return value if isinstance(value, str) and value in _STATE_FILENAMES.values() else "unknown-state-file"


def _observed_argv(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return ()
    return tuple(value)


def _starter_stdout_matches_digest(observation: Mapping[str, Any], digest: Any) -> bool:
    if not isinstance(digest, str):
        return False
    try:
        stdout = json.dumps(dict(observation), sort_keys=True) + "\n"
    except (TypeError, ValueError):
        return False
    return sha256(stdout.encode("utf-8")).hexdigest() == digest



def _canonical_state_matches_digest(state: Any, digest: Any, text: Any) -> bool:
    if not isinstance(state, Mapping) or not isinstance(digest, str) or not isinstance(text, str):
        return False
    if sha256(text.encode("utf-8")).hexdigest() != digest:
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, Mapping) and dict(parsed) == dict(state)


def _contacts_from_source(source: Any, filename: str) -> list[dict[str, str]] | None:
    if not isinstance(source, Mapping):
        return None
    text = source.get("text")
    if (
        source.get("filename") != filename
        or not isinstance(text, str)
        or source.get("sha256") != sha256(text.encode("utf-8")).hexdigest()
    ):
        return None
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames != ["name", "email"]:
            return None
        contacts: list[dict[str, str]] = []
        for row in reader:
            if not isinstance(row, dict) or set(row) != {"name", "email"}:
                return None
            raw_name = row["name"]
            raw_email = row["email"]
            if not isinstance(raw_name, str) or not isinstance(raw_email, str):
                return None
            name = raw_name.strip()
            email = raw_email.strip()
            if not name or "@" not in email:
                return None
            contacts.append({"name": name, "email": email})
    except csv.Error:
        return None
    return contacts or None


def _expected_post_state(
    case_id: str,
    command: tuple[str, ...],
    before_state: Mapping[str, Any],
    command_source: Any,
) -> dict[str, Any] | None:
    state = copy.deepcopy(dict(before_state))
    try:
        if case_id == "bookmarks" and len(command) == 4 and command[:2] == ("bookmark", "tag"):
            bookmarks = state.get("bookmarks")
            if not isinstance(bookmarks, list):
                return None
            bookmark = next(
                (item for item in bookmarks if isinstance(item, dict) and item.get("id") == command[2]),
                None,
            )
            tag = command[3].strip()
            if bookmark is None or not isinstance(bookmark.get("tags"), list) or not tag or tag in bookmark["tags"]:
                return None
            bookmark["tags"].append(tag)
        elif case_id == "config-merge" and len(command) == 3 and command[:2] == ("config", "merge"):
            overlay = _CONFIG_OVERLAYS.get(command[2])
            if overlay is None:
                return None
            state.update(overlay)
        elif case_id == "contacts-csv" and len(command) == 3 and command[:2] == ("contacts", "import"):
            contacts = state.get("contacts")
            imported = _contacts_from_source(command_source, command[2])
            if not isinstance(contacts, list) or imported is None:
                return None
            contacts.extend(imported)
        elif case_id == "expense" and len(command) == 4 and command[:2] == ("expense", "add"):
            expenses = state.get("expenses")
            if not isinstance(expenses, list) or not command[3].strip():
                return None
            amount = Decimal(command[2])
            if not amount.is_finite() or amount < 0:
                return None
            recorded_amount: int | float = (
                int(amount) if amount == amount.to_integral_value() else float(amount)
            )
            expenses.append({"amount": recorded_amount, "note": command[3]})
        elif case_id == "reminder" and len(command) == 4 and command[:2] == ("reminder", "add"):
            reminders = state.get("reminders")
            if not isinstance(reminders, list) or not command[2].strip() or not command[3].strip():
                return None
            reminders.append({"text": command[2], "due": command[3]})
        elif case_id == "todo" and len(command) == 3 and command[:2] == ("todo", "complete"):
            todos = state.get("todos")
            if not isinstance(todos, list):
                return None
            todo = next(
                (item for item in todos if isinstance(item, dict) and item.get("id") == command[2]),
                None,
            )
            if todo is None or todo.get("done") is not False:
                return None
            todo["done"] = True
        else:
            return None
    except (InvalidOperation, TypeError, ValueError):
        return None
    return state


def _observed_state_effect(
    case_id: str,
    command: tuple[str, ...],
    before_state: Any,
    after_state: Any,
    command_source: Any,
    post_state_digest: Any,
) -> tuple[str, bool]:
    if not isinstance(before_state, Mapping) or not isinstance(after_state, Mapping):
        return f"state-sha256={post_state_digest if isinstance(post_state_digest, str) else 'absent'}", False
    expected = _expected_post_state(case_id, command, before_state, command_source)
    effect = _CASE_STATE_EFFECTS.get(case_id)
    if expected is not None and effect is not None and dict(after_state) == expected:
        return effect, True
    return f"state-sha256={post_state_digest if isinstance(post_state_digest, str) else 'absent'}", False


def replay_observation_evidence(
    case_contract: Mapping[str, Any],
    starter_execution: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute scored predicates from retained subprocess and state evidence."""
    case_id, command, state_filename, _ = _case_behavior(case_contract)
    starter_observation = _mapping(
        starter_execution.get("starter_observation"), "starter execution observation"
    )
    executed_argv = _observed_argv(starter_execution.get("argv"))
    reported_argv = _observed_argv(starter_observation.get("argv"))
    observed_case_id = _observed_case_id(starter_observation.get("case_id"))
    observed_state_filename = _observed_state_filename(starter_observation.get("state_file"))
    pre_state = starter_execution.get("pre_state")
    post_state = starter_execution.get("post_state")
    pre_state_digest = starter_execution.get("pre_state_sha256")
    post_state_digest = starter_execution.get("post_state_sha256")
    pre_state_text = starter_execution.get("pre_state_text")
    post_state_text = starter_execution.get("post_state_text")
    state_effect, post_state_effect = _observed_state_effect(
        observed_case_id,
        reported_argv,
        pre_state,
        post_state,
        starter_execution.get("command_source"),
        post_state_digest,
    )
    predicates = {
        "case_identity": observed_case_id == case_id,
        "command_identity": reported_argv == command,
        "executed_command_identity": executed_argv == ("python", "cli.py", *command),
        "state_file_identity": observed_state_filename == state_filename,
        "starter_observation_schema": starter_observation.get("schema") == "StarterObservation.v1",
        "starter_stdout_digest": _starter_stdout_matches_digest(
            starter_observation, starter_execution.get("stdout_digest")
        ),
        "completed_success": (
            starter_execution.get("exit_code") == 0
            and starter_observation.get("changed") is True
            and type(starter_observation.get("exit_code")) is int
            and starter_observation.get("exit_code") == 0
            and starter_observation.get("status") == "completed"
        ),
        "reported_state_digest": starter_observation.get("state_sha256") == post_state_digest,
        "canonical_pre_state": _canonical_state_matches_digest(
            pre_state, pre_state_digest, pre_state_text
        ),
        "canonical_post_state": _canonical_state_matches_digest(
            post_state, post_state_digest, post_state_text
        ),
        "post_state_effect": post_state_effect,
    }
    predicates["positive_observation"] = all(predicates.values())
    actual_guard = f"case={observed_case_id}"
    actual_boundary = f"state-file={observed_state_filename}"
    actual_assertion = {
        "atoms": [
            {
                "guard": actual_guard,
                "effect": _command_effect(reported_argv),
                "polarity": "must" if predicates["positive_observation"] else "must-not",
                "boundary": actual_boundary,
                "temporal": "subprocess-terminal",
            },
            {
                "guard": actual_guard,
                "effect": state_effect,
                "polarity": "must" if predicates["positive_observation"] else "must-not",
                "boundary": actual_boundary,
                "temporal": "post-state",
            },
        ]
    }
    return {
        "expected_assertion": _expected_case_assertion(case_contract),
        "actual_assertion": actual_assertion,
        "predicate_results": predicates,
        "observation_result": "observed" if predicates["positive_observation"] else "unobserved",
    }


def _public_root_for_execution() -> Path:
    """Use the image path; source-tree fallback exists only for injected unit runners."""

    if _PUBLIC_ROOT.is_dir():
        return _PUBLIC_ROOT
    return Path(__file__).resolve().parents[2] / "corpus" / "public"



def _native_v1_runtime(cell_input: Any) -> dict[str, Any]:
    from .native_snapshot import validate_native_snapshot

    input_document = _mapping(cell_input, "cell input")
    try:
        native_root = _native_root_for_execution()
        validation = validate_native_snapshot(native_root)
        fixture_path = native_root / "fixtures" / "native-v1-structural-valid.json"
        fixture_bytes = fixture_path.read_bytes()
        fixture = json.loads(fixture_bytes)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise RoleWorkError(f"vendored native v1 fixture is unavailable or invalid: {error}") from error
    invocation = _mapping(fixture.get("invocation"), "native fixture invocation")
    argv = invocation.get("argv")
    working_directory = invocation.get("working_directory")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise RoleWorkError("native fixture has unsafe argv")
    if not isinstance(working_directory, str) or Path(working_directory).is_absolute() or ".." in Path(working_directory).parts:
        raise RoleWorkError("native fixture has unsafe working directory")
    executable_argv = argv
    if argv[:2] == ["uv", "run"] and shutil.which("uv") is None:
        executable_argv = [sys.executable, *argv[2:]]
    completed = subprocess.run(
        executable_argv,
        cwd=_native_root_for_execution() / working_directory,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
    )
    if completed.returncode != _mapping(fixture.get("expected"), "native fixture expected").get("exit_code"):
        raise RoleWorkError("vendored native v1 fixture failed")
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RoleWorkError("vendored native v1 fixture emitted invalid JSON") from error
    if not isinstance(receipt, Mapping) or _mapping(receipt.get("implementation_gate"), "native implementation gate").get("implementation_ready") is not True:
        raise RoleWorkError("vendored native v1 fixture did not satisfy implementation gate")
    return {
        "schema": "NativeV1FixtureRuntimeReceipt.v2",
        "cell_id": input_document.get("cell_id"),
        "input_digest": canonical_digest(input_document),
        "snapshot_id": validation.snapshot_id,
        "source_tree_digest": validation.source_tree_digest,
        "source_record_count": validation.record_count,
        "fixture_id": fixture.get("fixture_id"),
        "fixture_digest": sha256(fixture_bytes).hexdigest(),
        "invocation": {"argv": argv, "working_directory": working_directory},
        "exit_code": completed.returncode,
        "stdout_digest": sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "native_runtime_receipt": dict(receipt),
        "implementation_ready": True,
        "provenance": WORKER_PROVENANCE,
    }


def _native_root_for_execution() -> Path:
    """Use the image snapshot; source-tree fallback exists only for injected unit runners."""

    if _NATIVE_ROOT.is_dir():
        return _NATIVE_ROOT
    return Path(__file__).resolve().parents[2] / "protocol" / "ultimateinterview" / "ui-native-77b0327-r4"

def _expected_assertion(implementation: Mapping[str, Any]) -> dict[str, Any]:
    requirement_ids = implementation.get("implemented_atom_ids")
    if (
        not isinstance(requirement_ids, (list, tuple))
        or not requirement_ids
        or not all(isinstance(item, str) for item in requirement_ids)
    ):
        raise RoleWorkError("implementation lacks acceptance requirement provenance")
    starter = _mapping(implementation.get("starter"), "implementation starter")
    return _expected_case_assertion(_mapping(starter.get("case_contract"), "case contract"))


def _canonical_object(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoleWorkError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise RoleWorkError(f"{label} must be a JSON object")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RoleWorkError(f"{label} must be a JSON object")
    return value


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
