"""Adversarial red-team suite for todo_cli.

These tests TRY TO BREAK the CLI: malformed stores, hostile titles, id
abuse, idempotency/no-write guarantees, and domain-op purity. They complement
``test_todo.py`` (happy + basic error paths). All CLI invocations go through
``todo_cli.main([...])`` as a black-box consumer of the packaged CLI surface.

Store-file corruption must surface as exit code 3 (StoreError) with the
on-disk file left byte-for-byte unchanged (no clobbering the user's data).
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
)

EXIT_OK = 0
EXIT_DOMAIN = 1
EXIT_USAGE = 2
EXIT_STORAGE = 3


@pytest.fixture
def todo_file(tmp_path, monkeypatch):
    path = tmp_path / "todos.json"
    monkeypatch.setenv("TODO_FILE", str(path))
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _valid_task(**overrides):
    task = {"id": 1, "title": "a", "done": False, "due": None, "priority": "medium"}
    task.update(overrides)
    return task


def _write_store(path, *, next_id=2, tasks=None, schema_version=1, raw=None):
    """Write a store file; ``raw`` overrides the whole payload when given."""
    if raw is not None:
        payload = raw
    else:
        payload = {
            "schema_version": schema_version,
            "next_id": next_id,
            "tasks": [_valid_task()] if tasks is None else tasks,
        }
    text = payload if isinstance(payload, str) else json.dumps(payload)
    Path(path).write_text(text, encoding="utf-8")
    return Path(path).read_bytes()


# ==========================================================================
# Malformed store files -> exit 3 (StoreError), file NOT overwritten.
# Each case runs ``add`` (which would write on success) to prove the store
# is never clobbered when the load fails.
# ==========================================================================
_MALFORMED_STORES = {
    "corrupt_json_truncated": "{ not json",
    "corrupt_json_trailing": '{"schema_version": 1, "next_id": 2, "tasks": []',
    "not_a_json_object": "[1, 2, 3]",
    "json_scalar": "42",
    "wrong_schema_version_2": {"schema_version": 2, "next_id": 2, "tasks": []},
    "wrong_schema_version_str": {"schema_version": "1", "next_id": 2, "tasks": []},
    "missing_schema_version": {"next_id": 2, "tasks": []},
    "next_id_equal_max_id": {
        "schema_version": 1,
        "next_id": 1,
        "tasks": [_valid_task(id=1)],
    },
    "next_id_less_than_max_id": {
        "schema_version": 1,
        "next_id": 3,
        "tasks": [_valid_task(id=5)],
    },
    "next_id_zero": {"schema_version": 1, "next_id": 0, "tasks": []},
    "next_id_negative": {"schema_version": 1, "next_id": -1, "tasks": []},
    "next_id_bool": {"schema_version": 1, "next_id": True, "tasks": []},
    "next_id_float": {"schema_version": 1, "next_id": 2.0, "tasks": []},
    "next_id_string": {"schema_version": 1, "next_id": "2", "tasks": []},
    "tasks_not_list": {"schema_version": 1, "next_id": 2, "tasks": {}},
    "duplicate_ids": {
        "schema_version": 1,
        "next_id": 4,
        "tasks": [_valid_task(id=1), _valid_task(id=1, title="b")],
    },
    "unknown_task_field": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(extra="boom")],
    },
    "non_object_task_string": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": ["not-a-task"],
    },
    "non_object_task_int": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [123],
    },
    "non_object_task_null": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [None],
    },
    "task_id_zero": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(id=0)],
    },
    "task_id_negative": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(id=-5)],
    },
    "task_id_bool": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(id=True)],
    },
    "task_id_string": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(id="1")],
    },
    "task_id_float": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(id=1.0)],
    },
    "invalid_due_feb30": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(due="2026-02-30")],
    },
    "invalid_due_unpadded": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(due="2026-2-3")],
    },
    "invalid_due_slashes": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(due="2026/07/10")],
    },
    "invalid_due_datetime": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(due="2026-07-10T00:00:00")],
    },
    "invalid_due_type": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(due=20260710)],
    },
    "invalid_priority_value": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(priority="urgent")],
    },
    "invalid_priority_type": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(priority=3)],
    },
    "non_bool_done_int": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(done=1)],
    },
    "non_bool_done_string": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(done="false")],
    },
    "title_not_string": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(title=123)],
    },
    "title_whitespace_only": {
        "schema_version": 1,
        "next_id": 2,
        "tasks": [_valid_task(title="   ")],
    },
}


@pytest.mark.parametrize("name", sorted(_MALFORMED_STORES))
def test_malformed_store_exit3_and_file_not_overwritten(name, todo_file, capsys):
    before = _write_store(todo_file, raw=_MALFORMED_STORES[name])
    # ``add`` would persist on a successful load; a failed load must abort.
    rc = todo_cli.main(["add", "x"])
    assert rc == EXIT_STORAGE, f"{name}: expected exit 3, got {rc}"
    err = capsys.readouterr().err
    assert err.strip().startswith("error:"), f"{name}: expected error on stderr"
    assert todo_file.read_bytes() == before, f"{name}: store file was overwritten"


@pytest.mark.parametrize("name", sorted(_MALFORMED_STORES))
def test_malformed_store_exit3_on_list(name, todo_file):
    before = _write_store(todo_file, raw=_MALFORMED_STORES[name])
    rc = todo_cli.main(["list"])
    assert rc == EXIT_STORAGE, f"{name}: expected exit 3 on list, got {rc}"
    assert todo_file.read_bytes() == before


def test_malformed_store_raises_storeerror_not_bare_exception(todo_file):
    _write_store(todo_file, raw="{ not json")
    with pytest.raises(todo_cli.StoreError):
        load_store(todo_file)


# ==========================================================================
# TODO_FILE pointing at a directory -> graceful error, not a crash.
# ==========================================================================
def test_todo_file_is_directory_list_graceful_exit3(tmp_path, monkeypatch, capsys):
    dir_path = tmp_path / "todos.json"
    dir_path.mkdir()
    monkeypatch.setenv("TODO_FILE", str(dir_path))
    rc = todo_cli.main(["list"])
    assert rc == EXIT_STORAGE
    err = capsys.readouterr().err
    assert err.strip().startswith("error:")
    assert dir_path.is_dir()  # untouched


def test_todo_file_is_directory_add_graceful_exit3(tmp_path, monkeypatch, capsys):
    dir_path = tmp_path / "todos.json"
    dir_path.mkdir()
    monkeypatch.setenv("TODO_FILE", str(dir_path))
    rc = todo_cli.main(["add", "x"])
    assert rc == EXIT_STORAGE
    assert capsys.readouterr().err.strip().startswith("error:")
    assert dir_path.is_dir()


def test_todo_file_is_directory_load_raises_storeerror(tmp_path, monkeypatch):
    dir_path = tmp_path / "todos.json"
    dir_path.mkdir()
    monkeypatch.setenv("TODO_FILE", str(dir_path))
    with pytest.raises(todo_cli.StoreError):
        load_store(dir_path)


# ==========================================================================
# Title edge cases.
# ==========================================================================
@pytest.mark.parametrize("title", ["   ", "\t", "\n", "\t \n ", "  \t\n\t  "])
def test_whitespace_only_title_exit1_no_write(title, todo_file, capsys):
    rc = todo_cli.main(["add", title])
    assert rc == EXIT_DOMAIN
    assert "empty" in capsys.readouterr().err.lower()
    assert not todo_file.exists()


def test_title_with_internal_tabs_roundtrips_without_json_corruption(todo_file, capsys):
    title = "col1\tcol2\tcol3"
    assert todo_cli.main(["add", title]) == EXIT_OK
    assert capsys.readouterr().out.strip() == "added 1"
    # Persisted JSON preserves the tab characters exactly.
    persisted = read_json(todo_file)
    assert persisted["tasks"][0]["title"] == title
    # Store re-loads without error (JSON not corrupted by embedded tabs).
    store = load_store(todo_file)
    assert store.tasks[0].title == title
    # list must not crash on a tab-laden title.
    assert todo_cli.main(["list"]) == EXIT_OK


def test_title_with_internal_newlines_roundtrips(todo_file):
    title = "line1\nline2\nline3"
    assert todo_cli.main(["add", title]) == EXIT_OK
    assert read_json(todo_file)["tasks"][0]["title"] == title
    assert load_store(todo_file).tasks[0].title == title


def test_title_leading_trailing_whitespace_stripped_but_internal_kept(todo_file):
    assert todo_cli.main(["add", "  a\tb  "]) == EXIT_OK
    assert read_json(todo_file)["tasks"][0]["title"] == "a\tb"


# ==========================================================================
# Unicode title (Korean) round-trips through save/load.
# ==========================================================================
def test_unicode_korean_title_roundtrips(todo_file):
    title = "우유 사기 \u2764 마감"
    assert todo_cli.main(["add", title]) == EXIT_OK
    # ensure_ascii=False -> literal Korean on disk (not \uXXXX escapes).
    on_disk = Path(todo_file).read_text(encoding="utf-8")
    assert "우유 사기" in on_disk
    assert read_json(todo_file)["tasks"][0]["title"] == title
    assert load_store(todo_file).tasks[0].title == title


# ==========================================================================
# done/rm id validation: id<=0 -> usage error (exit 2); missing -> exit 1.
# ==========================================================================
@pytest.mark.parametrize("cmd", ["done", "rm"])
@pytest.mark.parametrize("bad_id", ["0", "-1", "-999"])
def test_done_rm_nonpositive_id_usage_error_exit2(cmd, bad_id, todo_file, capsys):
    todo_cli.main(["add", "a"])
    before = todo_file.read_bytes()
    capsys.readouterr()
    rc = todo_cli.main([cmd, bad_id])
    assert rc == EXIT_USAGE, f"{cmd} {bad_id}: expected usage exit 2, got {rc}"
    assert todo_file.read_bytes() == before


@pytest.mark.parametrize("cmd", ["done", "rm"])
@pytest.mark.parametrize("bad_id", ["abc", "1.5", "0x1", ""])
def test_done_rm_noninteger_id_usage_error_exit2(cmd, bad_id, todo_file):
    todo_cli.main(["add", "a"])
    before = todo_file.read_bytes()
    assert todo_cli.main([cmd, bad_id]) == EXIT_USAGE
    assert todo_file.read_bytes() == before


@pytest.mark.parametrize("cmd", ["done", "rm"])
def test_done_rm_nonexistent_id_exit1_file_unchanged(cmd, todo_file, capsys):
    todo_cli.main(["add", "a"])
    before = todo_file.read_bytes()
    capsys.readouterr()
    rc = todo_cli.main([cmd, "424242"])
    assert rc == EXIT_DOMAIN, f"{cmd}: expected domain exit 1, got {rc}"
    assert "424242" in capsys.readouterr().err
    assert todo_file.read_bytes() == before


# ==========================================================================
# Id monotonicity under stress: ids never reused, always strictly increasing.
# ==========================================================================
def test_id_monotonic_under_add_rm_reload_stress(todo_file):
    used_ids = []
    # Round 1: add several tasks.
    for i in range(5):
        assert todo_cli.main(["add", f"t{i}"]) == EXIT_OK
    used_ids = [t["id"] for t in read_json(todo_file)["tasks"]]
    assert used_ids == [1, 2, 3, 4, 5]
    max_used = max(used_ids)

    # Remove every task.
    for tid in list(used_ids):
        assert todo_cli.main(["rm", str(tid)]) == EXIT_OK
    data = read_json(todo_file)
    assert data["tasks"] == []
    assert data["next_id"] == max_used + 1

    # Reload persists next_id across the empty store.
    assert load_store(todo_file).next_id == max_used + 1

    # Round 2: add again -> ids strictly greater than everything used before.
    for i in range(3):
        assert todo_cli.main(["add", f"u{i}"]) == EXIT_OK
    new_ids = [t["id"] for t in read_json(todo_file)["tasks"]]
    assert all(nid > max_used for nid in new_ids), (used_ids, new_ids)
    # No reuse across the whole lifetime.
    assert set(new_ids).isdisjoint(set(used_ids))
    assert new_ids == sorted(new_ids)
    assert new_ids == [max_used + 1, max_used + 2, max_used + 3]


def test_id_not_reused_even_after_removing_highest(todo_file):
    todo_cli.main(["add", "a"])
    todo_cli.main(["add", "b"])
    todo_cli.main(["rm", "2"])  # remove highest id
    todo_cli.main(["add", "c"])
    ids = [t["id"] for t in read_json(todo_file)["tasks"]]
    assert 3 in ids and 2 not in ids  # id 2 not reused


# ==========================================================================
# Idempotent already-done: second call -> "already done", exit 0, no write.
# ==========================================================================
def test_done_twice_second_is_noop_on_disk(todo_file, capsys):
    todo_cli.main(["add", "a"])
    assert todo_cli.main(["done", "1"]) == EXIT_OK
    before = todo_file.read_bytes()
    capsys.readouterr()

    rc = todo_cli.main(["done", "1"])
    assert rc == EXIT_OK
    out = capsys.readouterr()
    assert out.out.strip() == "already done 1"
    assert out.err == ""
    # Byte-for-byte identical: no rewrite of the store on the idempotent call.
    assert todo_file.read_bytes() == before


def test_done_many_times_stays_stable(todo_file, capsys):
    todo_cli.main(["add", "a"])
    todo_cli.main(["done", "1"])
    snapshot = todo_file.read_bytes()
    for _ in range(4):
        capsys.readouterr()
        assert todo_cli.main(["done", "1"]) == EXIT_OK
        assert capsys.readouterr().out.strip() == "already done 1"
        assert todo_file.read_bytes() == snapshot


# ==========================================================================
# Purity: domain ops never mutate the input store or its task list.
# ==========================================================================
def test_add_task_does_not_mutate_input():
    tasks = [Task(id=1, title="a")]
    store = TodoStore(next_id=2, tasks=tasks)
    snapshot = list(tasks)
    new_store, task = add_task(store, "b", None, "high")
    assert store.tasks is tasks
    assert tasks == snapshot  # unchanged contents
    assert len(tasks) == 1
    assert new_store is not store
    assert new_store.tasks is not tasks
    assert task.id == 2


def test_mark_done_does_not_mutate_input():
    original = Task(id=1, title="a", done=False)
    tasks = [original]
    store = TodoStore(next_id=2, tasks=tasks)
    new_store, updated, changed = mark_done(store, 1)
    assert changed is True
    assert store.tasks is tasks
    assert tasks[0] is original
    assert tasks[0].done is False  # frozen dataclass: original untouched
    assert new_store is not store
    assert new_store.tasks is not tasks
    assert updated.done is True


def test_remove_task_does_not_mutate_input():
    tasks = [Task(id=1, title="a"), Task(id=2, title="b")]
    store = TodoStore(next_id=3, tasks=tasks)
    snapshot = list(tasks)
    new_store, removed = remove_task(store, 1)
    assert store.tasks is tasks
    assert tasks == snapshot
    assert len(tasks) == 2
    assert new_store.tasks is not tasks
    assert [t.id for t in new_store.tasks] == [2]
    assert removed.id == 1


def test_mark_done_noop_does_not_mutate_input():
    original = Task(id=1, title="a", done=True)
    tasks = [original]
    store = TodoStore(next_id=2, tasks=tasks)
    new_store, task, changed = mark_done(store, 1)
    assert changed is False
    assert store.tasks is tasks
    assert tasks[0] is original
    assert new_store is not store
