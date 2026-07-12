from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .model import DONE, OPEN, Store, Task

_STATUSES = {OPEN, DONE}


class StorageError(Exception):
    """Raised when the todo store cannot be safely read or written."""


def resolve_path() -> Path:
    env_path = os.environ.get("TODO_FILE")
    if env_path:
        return Path(env_path)
    return Path.home() / ".todos.json"


def load(path: Path) -> Store:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        return Store(next_id=1, tasks=[])
    except json.JSONDecodeError as exc:
        raise StorageError(f"invalid JSON in todo store {path}: {exc.msg}") from exc
    except UnicodeDecodeError as exc:
        raise StorageError(f"could not decode todo store {path}: {exc}") from exc
    except OSError as exc:
        raise StorageError(f"could not read todo store {path}: {exc}") from exc

    return _store_from_validated_data(data, path)


def save(store: Store, path: Path) -> None:
    tmp_path: Path | None = None
    fd: int | None = None
    replaced = False
    try:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent)
        tmp_path = Path(tmp_name)
        payload = json.dumps(store.to_dict(), indent=2, ensure_ascii=False) + "\n"
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            fd = None
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
        replaced = True
    except Exception as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None and not replaced:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if isinstance(exc, StorageError):
            raise
        raise StorageError(f"could not write todo store {path}: {exc}") from exc

    _fsync_parent_dir(path.parent)


def _store_from_validated_data(data: Any, path: Path) -> Store:
    if not isinstance(data, dict):
        raise StorageError(f"invalid todo store {path}: top-level value must be an object")
    if set(data) != {"next_id", "tasks"}:
        raise StorageError(f"invalid todo store {path}: expected next_id and tasks fields")

    next_id = data["next_id"]
    tasks_data = data["tasks"]
    if type(next_id) is not int or next_id < 1:
        raise StorageError(f"invalid todo store {path}: next_id must be an integer >= 1")
    if not isinstance(tasks_data, list):
        raise StorageError(f"invalid todo store {path}: tasks must be a list")

    tasks: list[Task] = []
    seen_ids: set[int] = set()
    max_id = 0
    for index, task_data in enumerate(tasks_data):
        task = _task_from_validated_data(task_data, index, path)
        if task.id in seen_ids:
            raise StorageError(f"invalid todo store {path}: duplicate task id {task.id}")
        seen_ids.add(task.id)
        max_id = max(max_id, task.id)
        tasks.append(task)

    if next_id <= max_id:
        raise StorageError(f"invalid todo store {path}: next_id must be greater than every task id")

    return Store(next_id=next_id, tasks=tasks)


def _task_from_validated_data(data: Any, index: int, path: Path) -> Task:
    if not isinstance(data, dict):
        raise StorageError(f"invalid todo store {path}: task {index} must be an object")
    if set(data) != {"id", "title", "status"}:
        raise StorageError(f"invalid todo store {path}: task {index} must have id, title, and status")

    task_id = data["id"]
    title = data["title"]
    status = data["status"]
    if type(task_id) is not int or task_id <= 0:
        raise StorageError(f"invalid todo store {path}: task {index} id must be a positive integer")
    if not isinstance(title, str):
        raise StorageError(f"invalid todo store {path}: task {index} title must be a string")
    if status not in _STATUSES:
        raise StorageError(f"invalid todo store {path}: task {index} status must be open or done")

    return Task(id=task_id, title=title, status=status)


def _fsync_parent_dir(directory: Path) -> None:
    fd: int | None = None
    try:
        fd = os.open(directory, os.O_RDONLY)
        os.fsync(fd)
    except OSError:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
