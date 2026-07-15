from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from driftbench import corpus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = PROJECT_ROOT / "corpus" / "public"
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
STATE_FILES = {
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


def _public_cases() -> dict[str, corpus.PublicCaseRecord]:
    return {case.case_id: case for case in corpus.validate_corpus(PUBLIC_ROOT / "cases.json")}


@pytest.mark.parametrize("case_id", sorted(COMMANDS))
def test_materialized_public_starter_recognizes_its_prompt_operation(
    case_id: str, tmp_path: Path
) -> None:
    case = _public_cases()[case_id]
    copied = corpus.materialize_starter_tree(PUBLIC_ROOT, case, tmp_path / "fresh-copy")
    state_file = copied / STATE_FILES[case_id]
    before = state_file.read_bytes()

    result = subprocess.run(
        [sys.executable, str(copied / "cli.py"), *COMMANDS[case_id]],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert result.returncode == 3
    observation = json.loads(result.stdout)
    assert observation == {
        "argv": list(COMMANDS[case_id]),
        "case_id": case_id,
        "changed": False,
        "exit_code": 3,
        "schema": "StarterObservation.v1",
        "state_file": state_file.name,
        "state_sha256": hashlib.sha256(before).hexdigest(),
        "status": "operation_unimplemented",
    }
    assert state_file.read_bytes() == before
    assert corpus.starter_tree_digest(copied) == case.starter_digest


def test_materialization_rejects_a_tampered_executable_tree(tmp_path: Path) -> None:
    copied_public_root = tmp_path / "public"
    shutil.copytree(PUBLIC_ROOT, copied_public_root)
    case = _public_cases()["todo"]
    (copied_public_root / "starters" / "todo" / "cli.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )

    with pytest.raises(corpus.CorpusValidationError, match="starter digest"):
        corpus.materialize_starter_tree(copied_public_root, case, tmp_path / "fresh-copy")
    assert not (tmp_path / "fresh-copy").exists()


def test_starter_digest_rejects_symlinked_directories(tmp_path: Path) -> None:
    copied = tmp_path / "todo"
    shutil.copytree(PUBLIC_ROOT / "starters" / "todo", copied)
    (copied / "linked-state").symlink_to(copied / "todos.json")

    with pytest.raises(corpus.CorpusValidationError, match="symlink"):
        corpus.starter_tree_digest(copied)


NEW_CASES = {
    "access-grant", "appointment-reschedule", "feature-flags",
    "inventory-transfer", "order-cancel", "playlist-reorder",
}


@pytest.mark.parametrize("case_id", sorted(NEW_CASES))
def test_new_starter_preserves_existing_success_dispatcher(case_id: str, tmp_path: Path) -> None:
    case = _public_cases()[case_id]
    copied = corpus.materialize_starter_tree(PUBLIC_ROOT, case, tmp_path / "fresh-copy")
    state = copied / STATE_FILES[case_id]
    before = state.read_bytes()

    result = subprocess.run([sys.executable, str(copied / "cli.py"), "state", "show"],
                            cwd=tmp_path, check=False, capture_output=True, text=True)

    observation = json.loads(result.stdout)
    assert result.returncode == 0
    assert observation["schema"] == "StarterObservation.v1"
    assert observation["status"] == "observed"
    assert observation["changed"] is False
    assert state.read_bytes() == before


@pytest.mark.parametrize("case_id", sorted(NEW_CASES))
def test_new_starter_invalid_invocation_is_byte_identical_failure(
    case_id: str, tmp_path: Path
) -> None:
    case = _public_cases()[case_id]
    copied = corpus.materialize_starter_tree(PUBLIC_ROOT, case, tmp_path / "fresh-copy")
    state = copied / STATE_FILES[case_id]
    before = state.read_bytes()

    result = subprocess.run([sys.executable, str(copied / "cli.py"), "unknown"],
                            cwd=tmp_path, check=False, capture_output=True, text=True)

    observation = json.loads(result.stdout)
    assert result.returncode == 64
    assert observation["status"] == "invalid_invocation"
    assert observation["changed"] is False
    assert state.read_bytes() == before
