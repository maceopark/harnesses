from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

STORE_NAME = ".todo-cli-app-5.json"
MAX_TITLE_LENGTH = 256

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class TodoError(Exception):
    exit_code: int

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(TodoError):
    exit_code = 2


class StorageError(TodoError):
    exit_code = 3


@dataclass(frozen=True, slots=True)
class Task:
    id: int
    title: str
    done: bool
    extra: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Store:
    next_id: int
    tasks: tuple[Task, ...]
    extra: dict[str, JsonValue]


def main(argv: Sequence[str] | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        output = run(args)
    except TodoError as error:
        print(f"error: {error.message}", file=sys.stderr)
        return error.exit_code

    print(output)
    return 0


def run(args: tuple[str, ...]) -> str:
    command = "list" if not args else args[0]
    command_args = () if not args else args[1:]

    if command == "list":
        require_arg_count(command_args, 0, "list")
        store = load_store(store_path())
        return format_tasks(tuple(task for task in store.tasks if not task.done), "No tasks.")

    if command == "list-completed":
        require_arg_count(command_args, 0, "list-completed")
        store = load_store(store_path())
        return format_tasks(
            tuple(task for task in store.tasks if task.done),
            "No completed tasks.",
        )

    if command == "add":
        title = parse_title(command_args)
        path = store_path()
        store = load_store(path)
        task = Task(id=store.next_id, title=title, done=False, extra={})
        updated = Store(
            next_id=store.next_id + 1,
            tasks=(*store.tasks, task),
            extra=store.extra,
        )
        save_store(path, updated)
        return f"Added {task.id}. {task.title}"

    if command == "complete":
        require_arg_count(command_args, 1, "complete")
        task_id = parse_id(command_args[0])
        path = store_path()
        store = load_store(path)
        task = find_task(store, task_id)
        if task.done:
            raise UsageError(f"task {task_id} is already completed")
        updated_task = Task(id=task.id, title=task.title, done=True, extra=task.extra)
        updated = replace_task(store, updated_task)
        save_store(path, updated)
        return f"Completed {task.id}. {task.title}"

    if command == "delete":
        require_arg_count(command_args, 1, "delete")
        task_id = parse_id(command_args[0])
        path = store_path()
        store = load_store(path)
        task = find_task(store, task_id)
        updated = Store(
            next_id=store.next_id,
            tasks=tuple(candidate for candidate in store.tasks if candidate.id != task_id),
            extra=store.extra,
        )
        save_store(path, updated)
        return f"Deleted {task.id}. {task.title}"

    raise UsageError(f"unknown command: {command}")


def require_arg_count(args: tuple[str, ...], expected: int, command: str) -> None:
    if len(args) < expected:
        raise UsageError(f"{command} requires an id")
    if len(args) > expected:
        raise UsageError(f"{command} received extra arguments")


def parse_title(args: tuple[str, ...]) -> str:
    if not args:
        raise UsageError("title is required")
    title = " ".join(args)
    if not valid_title(title):
        raise UsageError("title must be 1-256 printable characters")
    return title


def valid_title(title: str) -> bool:
    if not title.strip():
        return False
    if len(title) > MAX_TITLE_LENGTH:
        return False
    return all(not character_is_control(character) for character in title)


def character_is_control(character: str) -> bool:
    return ord(character) < 32 or ord(character) == 127


def parse_id(raw: str) -> int:
    try:
        task_id = int(raw, 10)
    except ValueError as exc:
        raise UsageError("id must be a positive integer") from exc
    if str(task_id) != raw or task_id <= 0:
        raise UsageError("id must be a positive integer")
    return task_id


def find_task(store: Store, task_id: int) -> Task:
    for task in store.tasks:
        if task.id == task_id:
            return task
    raise UsageError(f"task {task_id} does not exist")


def replace_task(store: Store, updated_task: Task) -> Store:
    return Store(
        next_id=store.next_id,
        tasks=tuple(
            updated_task if task.id == updated_task.id else task for task in store.tasks
        ),
        extra=store.extra,
    )


def format_tasks(tasks: tuple[Task, ...], empty_message: str) -> str:
    if not tasks:
        return empty_message
    return "\n".join(f"{task.id}. {task.title}" for task in tasks)


def store_path() -> Path:
    return Path.home() / STORE_NAME


def load_store(path: Path) -> Store:
    if not path.exists():
        return Store(next_id=1, tasks=(), extra={})

    try:
        raw_text = path.read_text(encoding="utf-8")
        loaded = json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError("could not read todo store") from exc

    return parse_store(loaded)


def parse_store(value: JsonValue) -> Store:
    if not isinstance(value, dict):
        raise StorageError("todo store has invalid format")

    next_id = parse_next_id(value.get("next_id"))
    raw_tasks = value.get("tasks")
    if not isinstance(raw_tasks, list):
        raise StorageError("todo store has invalid tasks")

    seen_ids: set[int] = set()
    tasks: list[Task] = []
    for raw_task in raw_tasks:
        task = parse_task(raw_task)
        if task.id in seen_ids:
            raise StorageError("todo store has duplicate task ids")
        seen_ids.add(task.id)
        tasks.append(task)

    highest_id = max(seen_ids, default=0)
    if next_id <= highest_id:
        raise StorageError("todo store has invalid next_id")

    extra = {
        key: item
        for key, item in value.items()
        if key not in {"next_id", "tasks"}
    }
    return Store(next_id=next_id, tasks=tuple(tasks), extra=extra)


def parse_next_id(value: JsonValue | None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StorageError("todo store has invalid next_id")
    return value


def parse_task(value: JsonValue) -> Task:
    if not isinstance(value, dict):
        raise StorageError("todo store has invalid task")

    raw_id = value.get("id")
    raw_title = value.get("title")
    raw_done = value.get("done")

    if not isinstance(raw_id, int) or isinstance(raw_id, bool) or raw_id <= 0:
        raise StorageError("todo store has invalid task id")
    if not isinstance(raw_title, str) or not valid_title(raw_title):
        raise StorageError("todo store has invalid task title")
    if not isinstance(raw_done, bool):
        raise StorageError("todo store has invalid task status")

    extra = {
        key: item
        for key, item in value.items()
        if key not in {"id", "title", "done"}
    }
    return Task(id=raw_id, title=raw_title, done=raw_done, extra=extra)


def save_store(path: Path, store: Store) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = write_temp_file(path, store_to_json(store))
        os.replace(str(temp_path), str(path))
    except OSError as exc:
        cleanup_temp_file(temp_path)
        raise StorageError("could not save todo store") from exc


def write_temp_file(path: Path, data: dict[str, JsonValue]) -> Path:
    temp_path: Path | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        )
        temp_path = Path(handle.name)
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        cleanup_temp_file(temp_path)
        raise
    return temp_path


def cleanup_temp_file(candidate: Path | None) -> None:
    if candidate is not None:
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            return


def store_to_json(store: Store) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = dict(store.extra)
    data["next_id"] = store.next_id
    data["tasks"] = [task_to_json(task) for task in store.tasks]
    return data


def task_to_json(task: Task) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = dict(task.extra)
    data["id"] = task.id
    data["title"] = task.title
    data["done"] = task.done
    return data


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
