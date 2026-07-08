"""Typed JSON storage and domain operations for codexplan."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NewType, override

TaskId = NewType("TaskId", int)
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
SCHEMA_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class Task:
    """A persisted todo item."""

    id: TaskId
    title: str
    done: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class Store:
    """The complete persisted todo store."""

    next_id: TaskId
    tasks: tuple[Task, ...]


@dataclass(frozen=True, slots=True)
class DomainError(Exception):
    """User-correctable command/domain error."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class StorageError(Exception):
    """Store read, write, or schema error."""

    message: str

    @override
    def __str__(self) -> str:
        return self.message


def store_path_from_env() -> Path:
    """Return the configured store path."""
    configured = os.environ.get("CODEXPLAN_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codexplan_todos.json"


def empty_store() -> Store:
    """Return a new empty store."""
    return Store(next_id=TaskId(1), tasks=())


def parse_title(raw_title: str) -> str:
    """Parse a command title into a non-empty title."""
    title = raw_title.strip()
    if title == "":
        raise DomainError(message="title must not be empty")
    return title


def parse_task_id(raw_id: str) -> TaskId:
    """Parse a positive task id."""
    try:
        task_id = int(raw_id)
    except ValueError as exc:
        raise DomainError(message="id must be a positive integer") from exc
    if task_id <= 0:
        raise DomainError(message="id must be a positive integer")
    return TaskId(task_id)


def load_store(path: Path) -> Store:
    """Load a store from disk or return an empty store when absent."""
    if not path.exists():
        return empty_store()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StorageError(message="unreadable store") from exc
    try:
        decoded: JsonValue = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StorageError(message="invalid JSON") from exc
    return parse_store(decoded)


def save_store(path: Path, store: Store) -> None:
    """Atomically write a store to disk."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(serialize_store(store), temp_file, indent=2)
            _ = temp_file.write("\n")
            temp_file.flush()
            _ = os.fsync(temp_file.fileno())
        _ = temp_path.replace(path)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise StorageError(message="write failed") from exc


def add_task(store: Store, title: str) -> tuple[Store, TaskId]:
    """Return a store with one appended task and its id."""
    task_id = store.next_id
    created_at = datetime.now(tz=UTC).isoformat(timespec="seconds")
    task = Task(id=task_id, title=title, done=False, created_at=created_at)
    next_id = TaskId(int(task_id) + 1)
    return Store(next_id=next_id, tasks=(*store.tasks, task)), task_id


def mark_done(store: Store, task_id: TaskId) -> tuple[Store, bool]:
    """Return a store with the target task marked done."""
    updated_tasks: list[Task] = []
    found_task: Task | None = None
    changed = False
    for task in store.tasks:
        if task.id != task_id:
            updated_tasks.append(task)
            continue
        found_task = task
        if task.done:
            updated_tasks.append(task)
            continue
        updated_tasks.append(
            Task(id=task.id, title=task.title, done=True, created_at=task.created_at),
        )
        changed = True
    if found_task is None:
        raise DomainError(message=f"todo {int(task_id)} not found")
    return Store(next_id=store.next_id, tasks=tuple(updated_tasks)), changed


def remove_task(store: Store, task_id: TaskId) -> Store:
    """Return a store without the target task."""
    updated_tasks = tuple(task for task in store.tasks if task.id != task_id)
    if len(updated_tasks) == len(store.tasks):
        raise DomainError(message=f"todo {int(task_id)} not found")
    return Store(next_id=store.next_id, tasks=updated_tasks)


def format_task(task: Task) -> str:
    """Format a task as one CLI row."""
    marker = "[x]" if task.done else "[ ]"
    return f"{int(task.id)}\t{marker}\t{task.title}"


def parse_store(decoded: JsonValue) -> Store:
    """Parse decoded JSON into a typed store."""
    match decoded:
        case {"schema_version": 1, "next_id": int(next_id), "tasks": list(raw_tasks)}:
            if isinstance(next_id, bool) or next_id <= 0:
                raise StorageError(message="invalid schema")
            tasks = tuple(parse_task(raw_task) for raw_task in raw_tasks)
            task_ids = tuple(int(task.id) for task in tasks)
            if len(set(task_ids)) != len(task_ids):
                raise StorageError(message="invalid schema")
            if any(task_id >= next_id for task_id in task_ids):
                raise StorageError(message="invalid schema")
            return Store(next_id=TaskId(next_id), tasks=tasks)
        case _:
            raise StorageError(message="invalid schema")


def parse_task(raw_task: JsonValue) -> Task:
    """Parse decoded JSON into a typed task."""
    match raw_task:
        case {
            "id": int(task_id),
            "title": str(title),
            "done": bool(done),
            "created_at": str(created_at),
        }:
            if isinstance(task_id, bool) or task_id <= 0 or title == "":
                raise StorageError(message="invalid schema")
            try:
                _ = datetime.fromisoformat(created_at)
            except ValueError as exc:
                raise StorageError(message="invalid schema") from exc
            return Task(id=TaskId(task_id), title=title, done=done, created_at=created_at)
        case _:
            raise StorageError(message="invalid schema")


def serialize_store(store: Store) -> dict[str, JsonValue]:
    """Serialize a store into JSON-compatible values."""
    return {
        "schema_version": SCHEMA_VERSION,
        "next_id": int(store.next_id),
        "tasks": [
            serialize_task(task) for task in sorted(store.tasks, key=lambda task: int(task.id))
        ],
    }


def serialize_task(task: Task) -> dict[str, JsonValue]:
    """Serialize a task into JSON-compatible values."""
    return {
        "id": int(task.id),
        "title": task.title,
        "done": task.done,
        "created_at": task.created_at,
    }
