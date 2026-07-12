from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "todo_cli"
USAGE = """usage: todo add <title...>
       todo list
       todo completed
       todo all
       todo complete <id>
       todo undo <id>
       todo delete <id>"""

VALID_STORE = {
    "next_id": 3,
    "tasks": [
        {"id": 1, "title": "open task", "status": "open"},
        {"id": 2, "title": "done task", "status": "done"},
    ],
}


def todo_command() -> list[str]:
    resolved = shutil.which("todo")
    if resolved:
        return [resolved]
    return ["uv", "run", "todo"]


def run_todo(args: list[str], todo_file: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TODO_FILE"] = str(todo_file)
    env.pop("PYTHONHOME", None)
    return subprocess.run(
        [*todo_command(), *args],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_store(path: Path, data: object) -> bytes:
    payload = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return payload


def read_store(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def usage_stderr(message: str) -> str:
    return f"{USAGE}\nerror: {message}\n"


def assert_result(
    result: subprocess.CompletedProcess[str],
    code: int,
    stdout: str = "",
    stderr: str = "",
) -> None:
    assert result.returncode == code
    assert result.stdout == stdout
    assert result.stderr == stderr


def assert_store_unchanged(path: Path, before: bytes | None) -> None:
    if before is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == before


def test_happy_flow_end_to_end_stdout_format_and_persistence(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"

    result = run_todo(["list"], todo_file)
    assert_result(result, 0)
    assert not todo_file.exists()

    assert_result(run_todo(["add", "buy", "milk"], todo_file), 0, "added 1\n")
    assert_result(run_todo(["add", "write", "tests"], todo_file), 0, "added 2\n")
    assert_result(run_todo(["list"], todo_file), 0, "1\t[ ]\tbuy milk\n2\t[ ]\twrite tests\n")
    assert_result(run_todo(["completed"], todo_file), 0, "")
    assert_result(run_todo(["complete", "1"], todo_file), 0, "completed 1\n")
    assert_result(run_todo(["list"], todo_file), 0, "2\t[ ]\twrite tests\n")
    assert_result(run_todo(["completed"], todo_file), 0, "1\t[x]\tbuy milk\n")
    assert_result(run_todo(["all"], todo_file), 0, "1\t[x]\tbuy milk\n2\t[ ]\twrite tests\n")
    assert_result(run_todo(["undo", "1"], todo_file), 0, "undone 1\n")
    assert_result(run_todo(["delete", "2"], todo_file), 0, "deleted 2\n")
    assert_result(run_todo(["all"], todo_file), 0, "1\t[ ]\tbuy milk\n")

    assert read_store(todo_file) == {
        "next_id": 3,
        "tasks": [{"id": 1, "title": "buy milk", "status": "open"}],
    }


@pytest.mark.parametrize(
    ("op", "args", "expected_code", "expected_stdout", "expected_stderr", "expected_store"),
    [
        ("add", ["add", "matrix item"], 0, "added 1\n", "", {"next_id": 2, "tasks": [{"id": 1, "title": "matrix item", "status": "open"}]}),
        ("list", ["list"], 0, "", "", None),
        ("completed", ["completed"], 0, "", "", None),
        ("all", ["all"], 0, "", "", None),
        ("complete", ["complete", "1"], 1, "", "error: no such task: 1\n", None),
        ("undo", ["undo", "1"], 1, "", "error: no such task: 1\n", None),
        ("delete", ["delete", "1"], 1, "", "error: no such task: 1\n", None),
    ],
)
def test_op_store_matrix_absent_store(
    tmp_path: Path,
    op: str,
    args: list[str],
    expected_code: int,
    expected_stdout: str,
    expected_stderr: str,
    expected_store: dict[str, object] | None,
) -> None:
    todo_file = tmp_path / f"{op}.json"

    result = run_todo(args, todo_file)

    assert_result(result, expected_code, expected_stdout, expected_stderr)
    if expected_store is None:
        assert not todo_file.exists()
    else:
        assert read_store(todo_file) == expected_store


@pytest.mark.parametrize(
    ("op", "args", "expected_code", "expected_stdout", "expected_stderr", "expected_store"),
    [
        ("add", ["add", "new item"], 0, "added 3\n", "", {"next_id": 4, "tasks": [*VALID_STORE["tasks"], {"id": 3, "title": "new item", "status": "open"}]}),
        ("list", ["list"], 0, "1\t[ ]\topen task\n", "", VALID_STORE),
        ("completed", ["completed"], 0, "2\t[x]\tdone task\n", "", VALID_STORE),
        ("all", ["all"], 0, "1\t[ ]\topen task\n2\t[x]\tdone task\n", "", VALID_STORE),
        ("complete", ["complete", "1"], 0, "completed 1\n", "", {"next_id": 3, "tasks": [{"id": 1, "title": "open task", "status": "done"}, {"id": 2, "title": "done task", "status": "done"}]}),
        ("undo", ["undo", "2"], 0, "undone 2\n", "", {"next_id": 3, "tasks": [{"id": 1, "title": "open task", "status": "open"}, {"id": 2, "title": "done task", "status": "open"}]}),
        ("delete", ["delete", "1"], 0, "deleted 1\n", "", {"next_id": 3, "tasks": [{"id": 2, "title": "done task", "status": "done"}]}),
    ],
)
def test_op_store_matrix_valid_store(
    tmp_path: Path,
    op: str,
    args: list[str],
    expected_code: int,
    expected_stdout: str,
    expected_stderr: str,
    expected_store: dict[str, object],
) -> None:
    todo_file = tmp_path / f"{op}.json"
    write_store(todo_file, VALID_STORE)

    result = run_todo(args, todo_file)

    assert_result(result, expected_code, expected_stdout, expected_stderr)
    assert read_store(todo_file) == expected_store


@pytest.mark.parametrize(
    ("op", "args"),
    [
        ("add", ["add", "new item"]),
        ("list", ["list"]),
        ("completed", ["completed"]),
        ("all", ["all"]),
        ("complete", ["complete", "1"]),
        ("undo", ["undo", "1"]),
        ("delete", ["delete", "1"]),
    ],
)
def test_op_store_matrix_invalid_json_store_is_unchanged(tmp_path: Path, op: str, args: list[str]) -> None:
    todo_file = tmp_path / f"{op}.json"
    before = b"{not-json\n"
    todo_file.write_bytes(before)

    result = run_todo(args, todo_file)

    assert_result(
        result,
        3,
        "",
        f"error: invalid JSON in todo store {todo_file}: Expecting property name enclosed in double quotes\n",
    )
    assert_store_unchanged(todo_file, before)


@pytest.mark.parametrize(
    ("args", "message", "initial_store"),
    [
        (["bogus"], "unknown subcommand: bogus", None),
        ([], "missing subcommand", VALID_STORE),
    ],
)
def test_unknown_or_missing_operation_is_usage_error_without_store_write(
    tmp_path: Path, args: list[str], message: str, initial_store: dict[str, object] | None
) -> None:
    todo_file = tmp_path / "todos.json"
    before = write_store(todo_file, initial_store) if initial_store is not None else None

    result = run_todo(args, todo_file)

    assert_result(result, 2, "", usage_stderr(message))
    assert_store_unchanged(todo_file, before)


def test_ids_are_never_reused_and_next_id_is_monotonic(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"
    for title, task_id in [("one", 1), ("two", 2), ("three", 3)]:
        assert_result(run_todo(["add", title], todo_file), 0, f"added {task_id}\n")

    assert_result(run_todo(["delete", "3"], todo_file), 0, "deleted 3\n")
    assert_result(run_todo(["add", "four"], todo_file), 0, "added 4\n")
    assert read_store(todo_file)["next_id"] == 5

    for task_id in ["1", "2", "4"]:
        assert_result(run_todo(["delete", task_id], todo_file), 0, f"deleted {task_id}\n")
    assert_result(run_todo(["add", "five"], todo_file), 0, "added 5\n")

    assert read_store(todo_file) == {
        "next_id": 6,
        "tasks": [{"id": 5, "title": "five", "status": "open"}],
    }


@pytest.mark.parametrize(
    ("name", "payload", "expected_fragment"),
    [
        ("syntax", b"{bad-json\n", "invalid JSON"),
        ("duplicate_ids", {"next_id": 3, "tasks": [{"id": 1, "title": "a", "status": "open"}, {"id": 1, "title": "b", "status": "done"}]}, "duplicate task id 1"),
        ("bad_status", {"next_id": 2, "tasks": [{"id": 1, "title": "a", "status": "blocked"}]}, "status must be open or done"),
        ("next_id_not_greater", {"next_id": 1, "tasks": [{"id": 1, "title": "a", "status": "open"}]}, "next_id must be greater than every task id"),
        ("wrong_top_level", [1, 2, 3], "top-level value must be an object"),
    ],
)
def test_dual_corrupt_syntax_and_schema_invalid_stores_fail_without_write(
    tmp_path: Path, name: str, payload: bytes | object, expected_fragment: str
) -> None:
    todo_file = tmp_path / f"{name}.json"
    if isinstance(payload, bytes):
        before = payload
        todo_file.write_bytes(before)
    else:
        before = write_store(todo_file, payload)

    result = run_todo(["list"], todo_file)

    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert str(todo_file) in result.stderr
    assert expected_fragment in result.stderr
    assert_store_unchanged(todo_file, before)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["bogus"], "unknown subcommand: bogus"),
        (["complete"], "complete requires an id"),
        (["complete", "abc"], "invalid id: abc"),
    ],
)
def test_usage_errors_are_reported_before_corrupt_store_is_read(
    tmp_path: Path, args: list[str], message: str
) -> None:
    todo_file = tmp_path / "corrupt.json"
    before = b"{bad-json\n"
    todo_file.write_bytes(before)

    result = run_todo(args, todo_file)

    assert_result(result, 2, "", usage_stderr(message))
    assert_store_unchanged(todo_file, before)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["complete", "0"], "invalid id: 0"),
        (["complete", "-1"], "invalid id: -1"),
        (["complete", "1.0"], "invalid id: 1.0"),
        (["complete", "abc"], "invalid id: abc"),
        (["complete", ""], "invalid id: "),
        (["complete", "1", "2"], "complete accepts exactly one id"),
    ],
)
def test_id_parsing_usage_errors_do_not_read_or_write_store(tmp_path: Path, args: list[str], message: str) -> None:
    todo_file = tmp_path / "todos.json"
    before = write_store(todo_file, VALID_STORE)

    result = run_todo(args, todo_file)

    assert_result(result, 2, "", usage_stderr(message))
    assert_store_unchanged(todo_file, before)


def test_nonexistent_id_is_domain_error_not_usage_error(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"
    before = write_store(todo_file, VALID_STORE)

    result = run_todo(["complete", "99"], todo_file)

    assert_result(result, 1, "", "error: no such task: 99\n")
    assert_store_unchanged(todo_file, before)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["add", ""], "title must not be empty"),
        (["add", "   "], "title must not be empty"),
        (["add", "line1\nline2"], "title must not contain control characters"),
        (["add", "has\ttab"], "title must not contain control characters"),
        (["add", "x" * 1025], "title must be at most 1024 characters"),
    ],
)
def test_title_validation_rejects_invalid_titles_without_store_write(
    tmp_path: Path, args: list[str], message: str
) -> None:
    todo_file = tmp_path / "todos.json"
    before = write_store(todo_file, VALID_STORE)

    result = run_todo(args, todo_file)

    assert_result(result, 1, "", f"error: {message}\n")
    assert_store_unchanged(todo_file, before)


def test_title_validation_rejects_nul_control_character_in_subprocess(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"
    before = write_store(todo_file, VALID_STORE)
    runner = tmp_path / "invoke_with_nul.py"
    runner.write_text(
        "from todo_cli.cli import main\n"
        "import sys\n"
        "sys.exit(main(['add', 'bad\\0title']))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["TODO_FILE"] = str(todo_file)

    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert_result(result, 1, "", "error: title must not contain control characters\n")
    assert_store_unchanged(todo_file, before)


def test_title_length_boundary_and_multi_word_joining(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"
    title_1024 = "x" * 1024

    assert_result(run_todo(["add", title_1024], todo_file), 0, "added 1\n")
    assert_result(run_todo(["add", "alpha", "beta", "gamma"], todo_file), 0, "added 2\n")

    assert read_store(todo_file) == {
        "next_id": 3,
        "tasks": [
            {"id": 1, "title": title_1024, "status": "open"},
            {"id": 2, "title": "alpha beta gamma", "status": "open"},
        ],
    }


def test_invalid_state_transitions_do_not_write(tmp_path: Path) -> None:
    todo_file = tmp_path / "todos.json"
    write_store(todo_file, VALID_STORE)

    before_done = todo_file.read_bytes()
    assert_result(run_todo(["complete", "2"], todo_file), 1, "", "error: task 2 is already done\n")
    assert_store_unchanged(todo_file, before_done)

    before_open = todo_file.read_bytes()
    assert_result(run_todo(["undo", "1"], todo_file), 1, "", "error: task 1 is not done\n")
    assert_store_unchanged(todo_file, before_open)


def test_storage_save_is_atomic_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from todo_cli import storage
    from todo_cli.model import OPEN, Store, Task

    todo_file = tmp_path / "todos.json"
    original = Store(next_id=2, tasks=[Task(id=1, title="original", status=OPEN)])
    replacement = Store(next_id=3, tasks=[Task(id=2, title="replacement", status=OPEN)])
    storage.save(original, todo_file)
    before_names = {path.name for path in tmp_path.iterdir()}

    def fail_replace(src: object, dst: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(storage.StorageError, match="could not write todo store"):
        storage.save(replacement, todo_file)

    assert storage.load(todo_file) == original
    assert {path.name for path in tmp_path.iterdir()} == before_names


def test_project_declares_no_runtime_dependencies() -> None:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - test environment is currently Python 3.11+
        pytest.fail("Python 3.11+ is required for stdlib tomllib dependency inspection")

    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["dependencies"] == []


def test_src_uses_only_stdlib_and_local_runtime_imports() -> None:
    stdlib = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}
    local_roots = {"todo_cli"}
    third_party_imports: dict[str, list[str]] = {}

    for source in SRC_ROOT.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".", 1)[0]
                    if module not in stdlib and module not in local_roots:
                        third_party_imports.setdefault(source.name, []).append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module is None:
                    continue
                module = node.module.split(".", 1)[0]
                if module not in stdlib and module not in local_roots:
                    third_party_imports.setdefault(source.name, []).append(node.module)

    assert third_party_imports == {}
