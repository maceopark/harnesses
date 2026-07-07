"""Acceptance-mapped pytest suite for todo_cli.

Tests invoke the CLI via ``main([...])`` with ``capsys`` and assert on-disk
state via ``load_store`` / raw JSON reads. A ``todo_file`` fixture points the
``TODO_FILE`` env var at a tmp path so tests never touch ``~/.todos.json``.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import todo_cli
from todo_cli import (
    Task,
    TodoStore,
    add_task,
    load_store,
    mark_done,
    remove_task,
    save_store,
    sort_tasks,
)


@pytest.fixture
def todo_file(tmp_path, monkeypatch):
    path = tmp_path / "todos.json"
    monkeypatch.setenv("TODO_FILE", str(path))
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# AC1 add/list/done/rm success
# --------------------------------------------------------------------------
def test_missing_file_list_empty_exit0_no_create(todo_file, capsys):
    assert todo_cli.main(["list"]) == 0
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""
    assert not todo_file.exists()


def test_add_creates_schema_and_increments_next_id(todo_file, capsys):
    assert todo_cli.main(["add", "buy milk"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "added 1"

    data = read_json(todo_file)
    assert data["schema_version"] == 1
    assert data["next_id"] == 2
    assert data["tasks"] == [
        {"id": 1, "title": "buy milk", "done": False, "due": None, "priority": "medium"}
    ]


def test_add_with_due_priority_persists_fields(todo_file):
    assert todo_cli.main(["add", "gym", "--due", "2026-07-10", "--priority", "high"]) == 0
    task = read_json(todo_file)["tasks"][0]
    assert task["due"] == "2026-07-10"
    assert task["priority"] == "high"


def test_add_strips_title(todo_file):
    assert todo_cli.main(["add", "  spaced  "]) == 0
    assert read_json(todo_file)["tasks"][0]["title"] == "spaced"


def test_list_outputs_tasks(todo_file, capsys):
    todo_cli.main(["add", "alpha", "--priority", "high"])
    capsys.readouterr()
    assert todo_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert out == "1\t[ ]\thigh\t-\talpha\n"


def test_done_marks_by_id(todo_file):
    todo_cli.main(["add", "a"])
    todo_cli.main(["add", "b"])
    assert todo_cli.main(["done", "2"]) == 0
    tasks = {t["id"]: t for t in read_json(todo_file)["tasks"]}
    assert tasks[2]["done"] is True
    assert tasks[1]["done"] is False


def test_rm_removes_by_id(todo_file, capsys):
    todo_cli.main(["add", "a"])
    todo_cli.main(["add", "b"])
    capsys.readouterr()
    assert todo_cli.main(["rm", "1"]) == 0
    assert capsys.readouterr().out.strip() == "removed 1"
    ids = [t["id"] for t in read_json(todo_file)["tasks"]]
    assert ids == [2]


# --------------------------------------------------------------------------
# AC2 persistence across runs
# --------------------------------------------------------------------------
def test_persistence_across_main_calls(todo_file, capsys):
    assert todo_cli.main(["add", "persisted"]) == 0
    capsys.readouterr()
    assert todo_cli.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "persisted" in out
    assert out.startswith("1\t[ ]\t")


# --------------------------------------------------------------------------
# AC3 default sort
# --------------------------------------------------------------------------
def _list_ids(capsys):
    out = capsys.readouterr().out
    return [int(line.split("\t", 1)[0]) for line in out.splitlines() if line]


def test_list_default_sort_incomplete_priority_due_id(todo_file, capsys):
    # id1 done high; id2 incomplete low; id3 incomplete high due early;
    # id4 incomplete high due later; id5 incomplete medium
    todo_cli.main(["add", "t1", "--priority", "high"])
    todo_cli.main(["add", "t2", "--priority", "low"])
    todo_cli.main(["add", "t3", "--priority", "high", "--due", "2026-07-01"])
    todo_cli.main(["add", "t4", "--priority", "high", "--due", "2026-08-01"])
    todo_cli.main(["add", "t5", "--priority", "medium"])
    todo_cli.main(["done", "1"])
    capsys.readouterr()

    assert todo_cli.main(["list"]) == 0
    ids = _list_ids(capsys)
    # incomplete first, higher priority first, nearer due first, id tiebreak,
    # done (id1) last.
    assert ids == [3, 4, 2, 5, 1] or ids == [3, 4, 5, 2, 1]
    # Precise expected order:
    # incomplete high: id3 (due 07-01) < id4 (due 08-01)
    # then remaining incomplete by priority: id5 medium before id2 low
    # then done last: id1
    assert ids == [3, 4, 5, 2, 1]


def test_none_due_sorts_after_dated_within_same_done_priority(todo_file, capsys):
    todo_cli.main(["add", "dated_early", "--priority", "medium", "--due", "2026-07-01"])
    todo_cli.main(["add", "no_due", "--priority", "medium"])
    todo_cli.main(["add", "dated_late", "--priority", "medium", "--due", "2026-08-01"])
    capsys.readouterr()
    assert todo_cli.main(["list"]) == 0
    ids = _list_ids(capsys)
    assert ids == [1, 3, 2]  # early, late, then None-due last


# --------------------------------------------------------------------------
# AC4 filters
# --------------------------------------------------------------------------
def test_list_filter_priority(todo_file, capsys):
    todo_cli.main(["add", "h", "--priority", "high"])
    todo_cli.main(["add", "l", "--priority", "low"])
    capsys.readouterr()
    assert todo_cli.main(["list", "--priority", "high"]) == 0
    assert _list_ids(capsys) == [1]


def test_list_filter_due(todo_file, capsys):
    todo_cli.main(["add", "a", "--due", "2026-07-10"])
    todo_cli.main(["add", "b", "--due", "2026-07-11"])
    capsys.readouterr()
    assert todo_cli.main(["list", "--due", "2026-07-10"]) == 0
    assert _list_ids(capsys) == [1]


def test_list_filter_priority_and_due_combined(todo_file, capsys):
    todo_cli.main(["add", "a", "--priority", "high", "--due", "2026-07-10"])
    todo_cli.main(["add", "b", "--priority", "high", "--due", "2026-07-11"])
    todo_cli.main(["add", "c", "--priority", "low", "--due", "2026-07-10"])
    capsys.readouterr()
    assert todo_cli.main(["list", "--priority", "high", "--due", "2026-07-10"]) == 0
    assert _list_ids(capsys) == [1]


# --------------------------------------------------------------------------
# AC5 done/rm by id, not list position
# --------------------------------------------------------------------------
def test_done_uses_id_not_list_position(todo_file):
    todo_cli.main(["add", "a", "--priority", "low"])
    todo_cli.main(["add", "b", "--priority", "high"])
    # After sorting, id2 (high) would be first, but done targets id 1.
    assert todo_cli.main(["done", "1"]) == 0
    tasks = {t["id"]: t for t in read_json(todo_file)["tasks"]}
    assert tasks[1]["done"] is True
    assert tasks[2]["done"] is False


def test_rm_uses_id_not_list_position(todo_file):
    todo_cli.main(["add", "a", "--priority", "low"])
    todo_cli.main(["add", "b", "--priority", "high"])
    assert todo_cli.main(["rm", "1"]) == 0
    ids = [t["id"] for t in read_json(todo_file)["tasks"]]
    assert ids == [2]


# --------------------------------------------------------------------------
# AC6 error handling
# --------------------------------------------------------------------------
def test_add_empty_title_exit1_stderr_no_write(todo_file, capsys):
    assert todo_cli.main(["add", "   "]) == 1
    err = capsys.readouterr().err
    assert "empty" in err
    assert not todo_file.exists()


def test_add_invalid_due_returns_2_no_systemexit_no_write(todo_file, capsys):
    assert todo_cli.main(["add", "x", "--due", "2026-02-30"]) == 2
    err = capsys.readouterr().err
    assert "invalid date" in err.lower() or "2026-02-30" in err
    assert not todo_file.exists()


def test_list_invalid_due_returns_2_no_systemexit(todo_file):
    assert todo_cli.main(["list", "--due", "2026-02-30"]) == 2


def test_add_invalid_priority_returns_2_no_systemexit(todo_file, capsys):
    assert todo_cli.main(["add", "x", "--priority", "urgent"]) == 2
    err = capsys.readouterr().err
    assert "urgent" in err or "choice" in err.lower()


def test_missing_required_arg_returns_2(todo_file):
    assert todo_cli.main(["done"]) == 2
    assert todo_cli.main(["add"]) == 2


def test_done_nonexistent_id_exit1_stderr_file_unchanged(todo_file, capsys):
    todo_cli.main(["add", "a"])
    before = todo_file.read_bytes()
    capsys.readouterr()
    assert todo_cli.main(["done", "999"]) == 1
    assert "999" in capsys.readouterr().err
    assert todo_file.read_bytes() == before


def test_rm_nonexistent_id_exit1_stderr_file_unchanged(todo_file, capsys):
    todo_cli.main(["add", "a"])
    before = todo_file.read_bytes()
    capsys.readouterr()
    assert todo_cli.main(["rm", "999"]) == 1
    assert "999" in capsys.readouterr().err
    assert todo_file.read_bytes() == before


def test_corrupt_json_exit3_file_unchanged_on_list(todo_file, capsys):
    todo_file.write_text("{ not json", encoding="utf-8")
    before = todo_file.read_bytes()
    assert todo_cli.main(["list"]) == 3
    err = capsys.readouterr().err
    assert "corrupt" in err.lower() or "error" in err.lower()
    assert todo_file.read_bytes() == before


def test_corrupt_json_exit3_no_overwrite_on_add(todo_file):
    todo_file.write_text("{ not json", encoding="utf-8")
    before = todo_file.read_bytes()
    assert todo_cli.main(["add", "x"]) == 3
    assert todo_file.read_bytes() == before


def test_invalid_schema_duplicate_ids_exit3(todo_file):
    todo_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "next_id": 3,
                "tasks": [
                    {"id": 1, "title": "a", "done": False, "due": None, "priority": "medium"},
                    {"id": 1, "title": "b", "done": False, "due": None, "priority": "medium"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert todo_cli.main(["list"]) == 3


def test_invalid_schema_next_id_not_greater_than_max_exit3(todo_file):
    todo_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "next_id": 1,
                "tasks": [
                    {"id": 1, "title": "a", "done": False, "due": None, "priority": "medium"}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert todo_cli.main(["list"]) == 3


def test_empty_schema_next_id_1_valid(todo_file):
    todo_file.write_text(
        json.dumps({"schema_version": 1, "next_id": 1, "tasks": []}),
        encoding="utf-8",
    )
    store = load_store(todo_file)
    assert store.next_id == 1
    assert store.tasks == []
    assert todo_cli.main(["list"]) == 0


# --------------------------------------------------------------------------
# AC8 id monotonicity
# --------------------------------------------------------------------------
def test_id_not_reused_after_rm(todo_file):
    todo_cli.main(["add", "a"])
    todo_cli.main(["rm", "1"])
    todo_cli.main(["add", "b"])
    data = read_json(todo_file)
    assert [t["id"] for t in data["tasks"]] == [2]
    assert data["next_id"] == 3


def test_add_rm_last_task_reload_add_new_id_strictly_greater_than_removed_id(todo_file):
    todo_cli.main(["add", "only"])
    removed_id = read_json(todo_file)["tasks"][0]["id"]
    assert removed_id == 1
    todo_cli.main(["rm", "1"])

    data = read_json(todo_file)
    assert data["tasks"] == []
    assert data["next_id"] == 2

    # empty store validates via max((ids), default=0)
    store = load_store(todo_file)
    assert store.next_id == 2

    todo_cli.main(["add", "again"])
    new_id = read_json(todo_file)["tasks"][0]["id"]
    assert new_id == 2
    assert new_id > removed_id


# --------------------------------------------------------------------------
# AC10 already-done idempotent
# --------------------------------------------------------------------------
def test_done_already_done_idempotent_success_no_save(todo_file, capsys):
    todo_cli.main(["add", "a"])
    todo_cli.main(["done", "1"])
    before = todo_file.read_bytes()
    capsys.readouterr()

    assert todo_cli.main(["done", "1"]) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "already done 1"
    assert out.err == ""
    assert todo_file.read_bytes() == before


# --------------------------------------------------------------------------
# AC9 pure domain operations
# --------------------------------------------------------------------------
def test_add_task_is_pure():
    original_tasks = [Task(id=1, title="a")]
    store = TodoStore(next_id=2, tasks=original_tasks)
    new_store, task = add_task(store, "b", None, "medium")
    assert store.tasks is original_tasks
    assert len(store.tasks) == 1
    assert new_store is not store
    assert new_store.tasks is not original_tasks
    assert new_store.next_id == 3
    assert task.id == 2


def test_mark_done_is_pure():
    original = Task(id=1, title="a", done=False)
    store = TodoStore(next_id=2, tasks=[original])
    new_store, task, changed = mark_done(store, 1)
    assert changed is True
    assert store.tasks[0].done is False
    assert new_store is not store
    assert new_store.tasks is not store.tasks
    assert task.done is True
    assert new_store.next_id == 2


def test_mark_done_already_done_is_pure_changed_false():
    original = Task(id=1, title="a", done=True)
    store = TodoStore(next_id=2, tasks=[original])
    new_store, task, changed = mark_done(store, 1)
    assert changed is False
    assert new_store is not store
    assert new_store.tasks is not store.tasks
    assert store.tasks[0].done is True
    assert task.done is True


def test_remove_task_is_pure():
    original_tasks = [Task(id=1, title="a"), Task(id=2, title="b")]
    store = TodoStore(next_id=3, tasks=original_tasks)
    new_store, removed = remove_task(store, 1)
    assert len(store.tasks) == 2
    assert store.tasks is original_tasks
    assert len(new_store.tasks) == 1
    assert new_store.tasks is not original_tasks
    assert new_store.next_id == 3
    assert removed.id == 1


def test_sort_tasks_does_not_mutate_input():
    tasks = [
        Task(id=1, title="a", priority="low"),
        Task(id=2, title="b", priority="high"),
    ]
    result = sort_tasks(tasks)
    assert [t.id for t in result] == [2, 1]
    assert [t.id for t in tasks] == [1, 2]  # input unchanged
    assert result is not tasks


# --------------------------------------------------------------------------
# save/load round-trip + atomic no-leftover
# --------------------------------------------------------------------------
def test_save_store_no_leftover_temp_files(todo_file):
    store = TodoStore(next_id=2, tasks=[Task(id=1, title="a")])
    save_store(store, todo_file)
    siblings = list(todo_file.parent.iterdir())
    assert siblings == [todo_file]
