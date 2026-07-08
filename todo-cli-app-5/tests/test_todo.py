from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol, TypeAlias

import pytest

ROOT = Path(__file__).resolve().parents[1]
TODO = ROOT / "todo.py"
STORE_NAME = ".todo-cli-app-5.json"
JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class TextWriter(Protocol):
    def write(self, text: str) -> int: ...


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(TODO), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def store_path(home: Path) -> Path:
    return home / STORE_NAME


def read_store(home: Path) -> dict[str, JsonValue]:
    content = store_path(home).read_text(encoding="utf-8")
    loaded = json.loads(content)
    assert isinstance(loaded, dict)
    return loaded


def assert_success(
    result: subprocess.CompletedProcess[str],
    stdout: str,
) -> None:
    assert result.returncode == 0
    assert result.stdout == stdout
    assert result.stderr == ""


def assert_usage_error(
    result: subprocess.CompletedProcess[str],
    message_fragment: str | None = None,
) -> None:
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert result.stderr.endswith("\n")
    if message_fragment is not None:
        assert message_fragment in result.stderr


def assert_storage_error(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert result.stderr.endswith("\n")


def test_happy_path_default_list_completion_and_delete(tmp_path: Path) -> None:
    assert_success(run_cli(tmp_path), "No tasks.\n")
    assert_success(run_cli(tmp_path, "list-completed"), "No completed tasks.\n")

    assert_success(run_cli(tmp_path, "add", "buy", "milk"), "Added 1. buy milk\n")
    assert_success(run_cli(tmp_path, "add", "buy", "milk"), "Added 2. buy milk\n")
    assert_success(run_cli(tmp_path), "1. buy milk\n2. buy milk\n")

    assert_success(run_cli(tmp_path, "complete", "1"), "Completed 1. buy milk\n")
    assert_success(run_cli(tmp_path, "list"), "2. buy milk\n")
    assert_success(run_cli(tmp_path, "list-completed"), "1. buy milk\n")

    assert_success(run_cli(tmp_path, "delete", "1"), "Deleted 1. buy milk\n")
    assert_success(run_cli(tmp_path, "list-completed"), "No completed tasks.\n")
    assert_success(run_cli(tmp_path, "list"), "2. buy milk\n")


def test_storage_ids_are_monotonic_and_creation_order_survives_changes(
    tmp_path: Path,
) -> None:
    assert_success(run_cli(tmp_path, "add", "first"), "Added 1. first\n")
    assert_success(run_cli(tmp_path, "add", "second"), "Added 2. second\n")
    assert_success(run_cli(tmp_path, "delete", "1"), "Deleted 1. first\n")
    assert_success(run_cli(tmp_path, "add", "third"), "Added 3. third\n")
    assert_success(run_cli(tmp_path, "complete", "2"), "Completed 2. second\n")

    assert_success(run_cli(tmp_path, "list"), "3. third\n")
    assert_success(run_cli(tmp_path, "list-completed"), "2. second\n")
    assert read_store(tmp_path)["next_id"] == 4


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (("wat",), "unknown"),
        (("list", "extra"), "extra"),
        (("list-completed", "extra"), "extra"),
        (("add",), "title"),
        (("add", "   "), "title"),
        (("add", "x" * 257), "title"),
        (("add", "bad\ninput"), "title"),
        (("add", "bad\x01input"), "title"),
        (("complete",), "id"),
        (("complete", "1", "extra"), "extra"),
        (("complete", "abc"), "id"),
        (("complete", "0"), "id"),
        (("delete",), "id"),
        (("delete", "1", "extra"), "extra"),
        (("delete", "abc"), "id"),
        (("delete", "-1"), "id"),
    ],
)
def test_errors_invalid_arguments_do_not_write_store(
    tmp_path: Path,
    args: tuple[str, ...],
    fragment: str,
) -> None:
    result = run_cli(tmp_path, *args)

    assert_usage_error(result, fragment)
    assert not store_path(tmp_path).exists()


def test_errors_nonexistent_and_completed_ids_do_not_mutate(
    tmp_path: Path,
) -> None:
    assert_success(run_cli(tmp_path, "add", "alpha"), "Added 1. alpha\n")
    before = store_path(tmp_path).read_text(encoding="utf-8")

    assert_usage_error(run_cli(tmp_path, "complete", "2"), "task 2")
    assert store_path(tmp_path).read_text(encoding="utf-8") == before

    assert_usage_error(run_cli(tmp_path, "delete", "2"), "task 2")
    assert store_path(tmp_path).read_text(encoding="utf-8") == before

    assert_success(run_cli(tmp_path, "complete", "1"), "Completed 1. alpha\n")
    completed = store_path(tmp_path).read_text(encoding="utf-8")

    assert_usage_error(
        run_cli(tmp_path, "complete", "1"),
        "task 1 is already completed",
    )
    assert store_path(tmp_path).read_text(encoding="utf-8") == completed


def test_storage_corrupt_non_utf8_and_invalid_schema_remain_unchanged(
    tmp_path: Path,
) -> None:
    store = store_path(tmp_path)

    cases = [
        b"{not-json",
        b"\xff\xfe\x00",
        json.dumps({"next_id": 1}).encode(),
        json.dumps({"next_id": 1, "tasks": [{"id": 1, "title": "x", "done": False}, {"id": 1, "title": "y", "done": False}]}).encode(),
        json.dumps({"next_id": 1, "tasks": [{"id": 1, "title": "bad\n", "done": False}]}).encode(),
        json.dumps({"next_id": 1, "tasks": [{"id": 1, "title": "x", "done": False}]}).encode(),
    ]

    for content in cases:
        store.write_bytes(content)
        result = run_cli(tmp_path, "list")

        assert_storage_error(result)
        assert store.read_bytes() == content


def test_storage_unknown_root_and_task_keys_are_preserved(
    tmp_path: Path,
) -> None:
    store_path(tmp_path).write_text(
        json.dumps(
            {
                "next_id": 2,
                "tasks": [
                    {
                        "id": 1,
                        "title": "alpha",
                        "done": False,
                        "note": {"kept": True},
                    }
                ],
                "owner": "fixture",
            }
        ),
        encoding="utf-8",
    )

    assert_success(run_cli(tmp_path, "complete", "1"), "Completed 1. alpha\n")

    stored = read_store(tmp_path)
    assert stored["owner"] == "fixture"
    tasks = stored["tasks"]
    assert isinstance(tasks, list)
    assert tasks[0]["note"] == {"kept": True}
    assert tasks[0]["done"] is True


def test_atomic_save_failure_leaves_existing_store_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.path.insert(0, str(ROOT))
    try:
        import todo
    finally:
        sys.path.remove(str(ROOT))

    store_path(tmp_path).write_text(
        json.dumps(
            {
                "next_id": 2,
                "tasks": [{"id": 1, "title": "alpha", "done": False}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    before = store_path(tmp_path).read_text(encoding="utf-8")

    def fail_replace(source: str, destination: str) -> None:
        _ = source
        _ = destination
        raise OSError("forced replace failure")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(todo.os, "replace", fail_replace)

    assert todo.main(["add", "beta"]) == 3
    assert store_path(tmp_path).read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob(f".{STORE_NAME}.*.tmp"))


def test_atomic_temp_write_failure_removes_partial_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.path.insert(0, str(ROOT))
    try:
        import todo
    finally:
        sys.path.remove(str(ROOT))

    store_path(tmp_path).write_text(
        json.dumps(
            {
                "next_id": 2,
                "tasks": [{"id": 1, "title": "alpha", "done": False}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    before = store_path(tmp_path).read_text(encoding="utf-8")

    def fail_dump(
        data: dict[str, todo.JsonValue],
        handle: TextWriter,
        *,
        ensure_ascii: bool,
        indent: int,
    ) -> None:
        _ = data
        _ = ensure_ascii
        _ = indent
        assert hasattr(handle, "write")
        handle.write("{")
        raise OSError("forced partial write failure")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(todo.json, "dump", fail_dump)

    assert todo.main(["add", "beta"]) == 3
    assert store_path(tmp_path).read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob(f".{STORE_NAME}.*.tmp"))
