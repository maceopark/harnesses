from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from driftbench import cli, role_worker
from driftbench.worker import LIFECYCLE_ARTIFACT_FILENAMES, WorkerRole, fresh_role_context
from driftbench.semantic import compare_assertions


PROJECT_ROOT = Path(__file__).resolve().parents[1]

COMMANDS = {
    "access-grant": ("access", "grant", "ada", "editor"),
    "appointment-reschedule": ("appointment", "reschedule", "appt-1", "Tuesday"),
    "bookmarks": ("bookmark", "tag", "bm-1", "reading"),
    "config-merge": ("config", "merge", "team"),
    "contacts-csv": ("contacts", "import", "incoming.csv"),
    "expense": ("expense", "add", "9", "tea"),
    "feature-flags": ("flag", "set", "dev", "dark_mode", "true"),
    "inventory-transfer": ("inventory", "transfer", "widget", "east", "west", "2"),
    "order-cancel": ("order", "cancel", "ord-1", "duplicate"),
    "playlist-reorder": ("playlist", "move", "track-3", "1"),
    "reminder": ("reminder", "add", "Call Ada", "Monday"),
    "todo": ("todo", "complete", "todo-1"),
}
STATE_FILENAMES = {
    "access-grant": "access.json",
    "appointment-reschedule": "appointments.json",
    "bookmarks": "bookmarks.json",
    "config-merge": "config.json",
    "contacts-csv": "contacts.json",
    "expense": "expenses.json",
    "feature-flags": "flags.json",
    "inventory-transfer": "inventory.json",
    "order-cancel": "orders.json",
    "playlist-reorder": "playlist.json",
    "reminder": "reminders.json",
    "todo": "todos.json",
}
STATE_EFFECTS = {
    "access-grant": "role-granted",
    "appointment-reschedule": "appointment-rescheduled",
    "bookmarks": "bookmark-tag-added",
    "config-merge": "named-overlay-merged",
    "contacts-csv": "csv-contacts-imported",
    "expense": "expense-recorded",
    "feature-flags": "feature-flag-set",
    "inventory-transfer": "inventory-transferred",
    "order-cancel": "order-cancelled",
    "playlist-reorder": "playlist-track-moved",
    "reminder": "reminder-created",
    "todo": "todo-completed",
}

def _docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    tag = "driftbench-worker:g004-integration"
    built = subprocess.run(
        ["docker", "build", "--quiet", "--file", "Dockerfile.worker", "--tag", tag, "."],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if built.returncode != 0:
        pytest.fail(f"Docker worker build failed: {built.stderr}")
    inspected = subprocess.run(
        ["docker", "image", "inspect", tag, "--format", "{{.Id}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0:
        pytest.fail(f"Docker worker image inspection failed: {inspected.stderr}")
    return inspected.stdout.strip()


@pytest.fixture(scope="module")
def oci_worker_image() -> str:
    return _docker_image()


def _cell_input(case: dict[str, object]) -> dict[str, object]:
    case_id = str(case["case_id"])
    cell_id = f"cell-oci-{case_id}"
    return {
        "schema": "CellInput.v2",
        "cell_id": cell_id,
        "identity": {"arm_id": "direct-v1", "opaque_case_token": case["opaque_token"]},
        "case_contract": {
            key: case[key] for key in ("case_id", "prompt", "starter_tree", "starter_digest")
        },
        "acceptance_requirement_ids": ["requirement-aaaaaaaaaaaaaaaaaaaaaaaa"],
        "metric_case": {"case_id": cell_id, "weight": 1},
    }


def _direct_implementer(
    image: str,
    case: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    cell_input = _cell_input(case)
    context = fresh_role_context(
        WorkerRole.IMPLEMENTER,
        f"direct-implementer-oci-{case['case_id']}",
        {"cell-input": (LIFECYCLE_ARTIFACT_FILENAMES["cell-input"], cell_input)},
        provenance="oci-deterministic-worker",
    )
    documents, receipts = cli._run_role_work(
        PROJECT_ROOT,
        role="implementer",
        worker_image=image,
        binding_digest="d" * 64,
        context=context,
        artifacts={"cell-input": cell_input},
    )
    return cell_input, documents, receipts


def test_oci_implementer_applies_and_observes_all_public_starter_implementations(
    oci_worker_image: str,
) -> None:
    cases = json.loads(
        (PROJECT_ROOT / "corpus" / "public" / "cases.json").read_text(encoding="utf-8")
    )["cases"]

    observed_case_ids: set[str] = set()
    for case in cases:
        cell_input, implementer_documents, implementer_receipts = _direct_implementer(
            oci_worker_image, case
        )
        implementation = implementer_documents["implementation"]
        starter = implementation["starter"]
        assert implementation["implementation_recipe"] == "public-starter-implementation-v1"
        assert starter["source_digest"] == case["starter_digest"]
        assert starter["materialized_digest"] != case["starter_digest"]
        assert starter["changed_files"] == (
            ["cli.py", "incoming.csv"] if case["case_id"] == "contacts-csv" else ["cli.py"]
        )
        assert implementer_documents["execution"]["provenance"] == "oci-deterministic-worker"
        assert implementer_receipts["isolation_launch"]["role"] == "implementer"
        assert implementer_receipts["input_stage"]["returncode"] == 0
        assert implementer_receipts["output_read"]["returncode"] == 0

        observation_context = fresh_role_context(
            WorkerRole.OBSERVATION,
            f"direct-observation-oci-{case['case_id']}",
            {
                "cell-input": (LIFECYCLE_ARTIFACT_FILENAMES["cell-input"], cell_input),
                "implementation": (
                    LIFECYCLE_ARTIFACT_FILENAMES["implementation"],
                    implementation,
                ),
            },
            provenance="oci-deterministic-worker",
        )
        observation_documents, observation_receipts = cli._run_role_work(
            PROJECT_ROOT,
            role="observation",
            worker_image=oci_worker_image,
            binding_digest="e" * 64,
            context=observation_context,
            artifacts={"cell-input": cell_input, "implementation": implementation},
        )
        observation = observation_documents["observation"]
        command = observation["starter_execution"]["argv"]
        starter_observation = observation["starter_execution"]["starter_observation"]

        assert observation["observation_result"] == "observed"
        assert observation["semantic_evidence_authoritative"] is True
        assert observation["primary_credit"] == 1
        assert observation["comparison"] == {"relation": "exact", "primary_credit": 1}
        case_id = str(case["case_id"])
        expected_assertion = {
            "atoms": [
                {
                    "guard": f"case={case_id}",
                    "effect": "argv=" + json.dumps(
                        list(COMMANDS[case_id]), ensure_ascii=False, separators=(",", ":")
                    ),
                    "polarity": "must",
                    "boundary": f"state-file={STATE_FILENAMES[case_id]}",
                    "temporal": "subprocess-terminal",
                },
                {
                    "guard": f"case={case_id}",
                    "effect": STATE_EFFECTS[case_id],
                    "polarity": "must",
                    "boundary": f"state-file={STATE_FILENAMES[case_id]}",
                    "temporal": "post-state",
                },
            ]
        }
        assert observation["expected_assertion"] == expected_assertion
        assert observation["actual_assertion"] == expected_assertion
        assert observation["predicate_results"] == {
            "case_identity": True,
            "command_identity": True,
            "executed_command_identity": True,
            "state_file_identity": True,
            "starter_observation_schema": True,
            "starter_stdout_digest": True,
            "completed_success": True,
            "reported_state_digest": True,
            "canonical_pre_state": True,
            "canonical_post_state": True,
            "post_state_effect": True,
            "positive_observation": True,
        }
        assert command == ["python", "cli.py", *COMMANDS[case_id]]
        assert starter_observation["argv"] == command[2:]
        assert starter_observation["status"] == "completed"
        assert starter_observation["changed"] is True
        assert observation["starter_execution"]["exit_code"] == 0
        assert observation_receipts["isolation_launch"]["role"] == "observation"
        assert observation_receipts["input_stage"]["returncode"] == 0
        assert observation_receipts["output_read"]["returncode"] == 0
        observed_case_ids.add(case["case_id"])

    assert observed_case_ids == set(COMMANDS)


def test_oci_observation_rejects_an_unimplemented_starter_artifact(
    oci_worker_image: str,
) -> None:
    case = json.loads(
        (PROJECT_ROOT / "corpus" / "public" / "cases.json").read_text(encoding="utf-8")
    )["cases"][0]
    cell_input, implementer_documents, _ = _direct_implementer(oci_worker_image, case)
    unimplemented = dict(implementer_documents["implementation"])
    unimplemented.pop("implementation_recipe")
    unimplemented["starter"] = {
        "case_contract": unimplemented["starter"]["case_contract"],
        "path": "starter",
        "materialized_digest": case["starter_digest"],
    }
    observation_context = fresh_role_context(
        WorkerRole.OBSERVATION,
        "direct-observation-oci-unimplemented",
        {
            "cell-input": (LIFECYCLE_ARTIFACT_FILENAMES["cell-input"], cell_input),
            "implementation": (
                LIFECYCLE_ARTIFACT_FILENAMES["implementation"],
                unimplemented,
            ),
        },
        provenance="oci-deterministic-worker",
    )

    with pytest.raises(cli.CliError):
        cli._run_role_work(
            PROJECT_ROOT,
            role="observation",
            worker_image=oci_worker_image,
            binding_digest="f" * 64,
            context=observation_context,
            artifacts={"cell-input": cell_input, "implementation": unimplemented},
        )


def test_generated_starters_reject_failed_commands_without_state_mutation(tmp_path: Path) -> None:
    cases = json.loads(
        (PROJECT_ROOT / "corpus" / "public" / "cases.json").read_text(encoding="utf-8")
    )["cases"]
    failed_commands = {
        "access-grant": ("access", "grant", "missing", "editor"),
        "appointment-reschedule": ("appointment", "reschedule", "missing", "Tuesday"),
        "bookmarks": ("bookmark", "tag", "missing", "reading"),
        "config-merge": ("config", "merge", "missing"),
        "contacts-csv": ("contacts", "import", "missing.csv"),
        "expense": ("expense", "add", "-1", "tea"),
        "feature-flags": ("flag", "set", "missing", "dark_mode", "true"),
        "inventory-transfer": ("inventory", "transfer", "widget", "east", "west", "999"),
        "order-cancel": ("order", "cancel", "ord-2", "late"),
        "playlist-reorder": ("playlist", "move", "missing", "1"),
        "reminder": ("reminder", "add", "Call Ada", ""),
        "todo": ("todo", "complete", "missing"),
    }
    state_files = {
        "access-grant": "access.json",
        "appointment-reschedule": "appointments.json",
        "bookmarks": "bookmarks.json",
        "config-merge": "config.json",
        "contacts-csv": "contacts.json",
        "expense": "expenses.json",
        "feature-flags": "flags.json",
        "inventory-transfer": "inventory.json",
        "order-cancel": "orders.json",
        "playlist-reorder": "playlist.json",
        "reminder": "reminders.json",
        "todo": "todos.json",
    }

    for case in cases:
        workspace = tmp_path / case["case_id"]
        workspace.mkdir()
        role_worker._materialize_starter(
            workspace,
            case,
            recipe="public-starter-implementation-v1",
        )
        starter = workspace / "starter"
        state_file = starter / state_files[case["case_id"]]
        original_digest = hashlib.sha256(state_file.read_bytes()).hexdigest()
        completed = subprocess.run(
            [sys.executable, "cli.py", *failed_commands[case["case_id"]]],
            cwd=starter,
            check=False,
            capture_output=True,
            text=True,
        )
        observation = json.loads(completed.stdout)

        assert completed.returncode == 1
        assert completed.stderr == ""
        assert observation["status"] == "operation_failed"
        assert observation["changed"] is False
        assert observation["state_sha256"] == original_digest
        assert hashlib.sha256(state_file.read_bytes()).hexdigest() == original_digest

def _positive_starter_execution(
    tmp_path: Path,
    case: dict[str, object],
) -> dict[str, object]:
    workspace = tmp_path / "positive"
    workspace.mkdir()
    role_worker._materialize_starter(
        workspace,
        case,
        recipe="public-starter-implementation-v1",
    )
    case_id = str(case["case_id"])
    command = COMMANDS[case_id]
    starter = workspace / "starter"
    state_file = starter / STATE_FILENAMES[case_id]
    pre_digest, pre_state, pre_text = role_worker._state_snapshot(state_file)
    command_source = role_worker._command_source_snapshot(starter, case_id, command)
    completed = subprocess.run(
        [sys.executable, "cli.py", *command],
        cwd=starter,
        check=False,
        capture_output=True,
        text=True,
    )
    post_digest, post_state, post_text = role_worker._state_snapshot(state_file)
    return {
        "argv": ["python", "cli.py", *command],
        "exit_code": completed.returncode,
        "stdout_digest": hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest(),
        "starter_observation": json.loads(completed.stdout),
        "pre_state": pre_state,
        "pre_state_sha256": pre_digest,
        "pre_state_text": pre_text,
        "post_state": post_state,
        "post_state_sha256": post_digest,
        "post_state_text": post_text,
        "command_source": command_source,
    }


def test_observation_predicates_reject_forged_cross_case_command_and_state_file(
    tmp_path: Path,
) -> None:
    cases = json.loads(
        (PROJECT_ROOT / "corpus" / "public" / "cases.json").read_text(encoding="utf-8")
    )["cases"]
    case = next(item for item in cases if item["case_id"] == "todo")
    execution = _positive_starter_execution(tmp_path, case)

    baseline = role_worker.replay_observation_evidence(case, execution)
    assert baseline["observation_result"] == "observed"
    assert compare_assertions(
        baseline["expected_assertion"], baseline["actual_assertion"]
    ).primary_credit == 1

    forged_cross_case = copy.deepcopy(execution)
    forged_cross_case["starter_observation"]["case_id"] = "reminder"
    tampered_command = copy.deepcopy(execution)
    tampered_command["starter_observation"]["argv"] = ["todo", "complete", "todo-2"]
    tampered_state_file = copy.deepcopy(execution)
    tampered_state_file["starter_observation"]["state_file"] = "reminders.json"

    for tampered, failed_predicate in (
        (forged_cross_case, "case_identity"),
        (tampered_command, "command_identity"),
        (tampered_state_file, "state_file_identity"),
    ):
        replayed = role_worker.replay_observation_evidence(case, tampered)
        assert replayed["predicate_results"]["completed_success"] is True
        assert replayed["predicate_results"][failed_predicate] is False
        assert replayed["observation_result"] == "unobserved"
        assert compare_assertions(
            replayed["expected_assertion"], replayed["actual_assertion"]
        ).primary_credit == 0
