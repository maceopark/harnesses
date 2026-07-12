"""Single-module stdlib-only todo CLI.

Commands: add / list / done / rm. Storage is a JSON file at
``~/.todos.json`` by default (overridable via the ``TODO_FILE`` env var).

Sections below: imports/guard-target, constants/errors, model, store
representation, storage layer, pure domain operations, CLI layer.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


# --------------------------------------------------------------------------
# Constants / errors
# --------------------------------------------------------------------------
PRIORITIES = {"low": 1, "medium": 2, "high": 3}
DEFAULT_PRIORITY = "medium"
SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_DOMAIN = 1
EXIT_USAGE = 2
EXIT_STORAGE = 3


class TodoError(Exception):
    """Domain/input error (e.g. empty title)."""


class StoreError(Exception):
    """Storage error (corrupt/invalid store file)."""


class TaskNotFoundError(TodoError):
    """Requested task id does not exist."""


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Task:
    id: int
    title: str
    done: bool = False
    due: str | None = None
    priority: str = DEFAULT_PRIORITY


def validate_priority(value: object) -> str:
    if not isinstance(value, str) or value not in PRIORITIES:
        raise StoreError(f"invalid priority: {value!r}")
    return value


def parse_due(value: str | None) -> str | None:
    """Validate an exact ISO ``YYYY-MM-DD`` date, or ``None``.

    Rejects datetime-like strings and invalid calendar dates by requiring a
    round-trip through :func:`datetime.date.fromisoformat` /
    :meth:`datetime.date.isoformat`.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid date: {value!r}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"invalid date: {value!r}")
    return value


def task_to_dict(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "done": task.done,
        "due": task.due,
        "priority": task.priority,
    }


def task_from_dict(raw: object) -> Task:
    if not isinstance(raw, dict):
        raise StoreError("task entry must be an object")

    allowed = {"id", "title", "done", "due", "priority"}
    extra = set(raw.keys()) - allowed
    if extra:
        raise StoreError(f"unexpected task fields: {sorted(extra)}")

    task_id = raw.get("id")
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise StoreError(f"invalid task id: {task_id!r}")

    title = raw.get("title")
    if not isinstance(title, str) or title.strip() == "":
        raise StoreError(f"invalid task title: {title!r}")

    done = raw.get("done", False)
    if not isinstance(done, bool):
        raise StoreError(f"invalid task done flag: {done!r}")

    due_raw = raw.get("due", None)
    if due_raw is not None and not isinstance(due_raw, str):
        raise StoreError(f"invalid task due: {due_raw!r}")
    try:
        due = parse_due(due_raw)
    except ValueError as exc:
        raise StoreError(str(exc)) from exc

    priority = validate_priority(raw.get("priority", DEFAULT_PRIORITY))

    return Task(id=task_id, title=title, done=done, due=due, priority=priority)


# --------------------------------------------------------------------------
# Store representation
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TodoStore:
    next_id: int
    tasks: list[Task]


# --------------------------------------------------------------------------
# Storage layer
# --------------------------------------------------------------------------
def get_store_path() -> Path:
    env_value = os.environ.get("TODO_FILE")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".todos.json"


def load_store(path: Path | None = None) -> TodoStore:
    if path is None:
        path = get_store_path()

    if not path.exists():
        return TodoStore(next_id=1, tasks=[])

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"unreadable store file: {exc}") from exc

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StoreError(f"corrupt store file: {exc}") from exc

    if not isinstance(raw, dict):
        raise StoreError("store file must contain a JSON object")

    schema_version = raw.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise StoreError(f"unsupported schema_version: {schema_version!r}")

    next_id = raw.get("next_id")
    if not isinstance(next_id, int) or isinstance(next_id, bool) or next_id < 1:
        raise StoreError(f"invalid next_id: {next_id!r}")

    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, list):
        raise StoreError("tasks must be a list")

    tasks = [task_from_dict(entry) for entry in raw_tasks]

    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise StoreError("duplicate task ids")

    max_id = max(ids, default=0)
    if next_id <= max_id:
        raise StoreError(f"next_id {next_id} must be greater than max id {max_id}")

    return TodoStore(next_id=next_id, tasks=tasks)


def save_store(store: TodoStore, path: Path | None = None) -> None:
    if path is None:
        path = get_store_path()

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "next_id": store.next_id,
        "tasks": [task_to_dict(task) for task in store.tasks],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(parent), delete=False
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, str(path))
        tmp_name = None
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


# --------------------------------------------------------------------------
# Pure domain operations
# --------------------------------------------------------------------------
def add_task(
    store: TodoStore, title: str, due: str | None, priority: str
) -> tuple[TodoStore, Task]:
    stripped = title.strip()
    if stripped == "":
        raise TodoError("title must not be empty")
    task = Task(
        id=store.next_id, title=stripped, done=False, due=due, priority=priority
    )
    new_store = TodoStore(next_id=store.next_id + 1, tasks=[*store.tasks, task])
    return new_store, task


def mark_done(store: TodoStore, task_id: int) -> tuple[TodoStore, Task, bool]:
    target = next((t for t in store.tasks if t.id == task_id), None)
    if target is None:
        raise TaskNotFoundError(f"no task with id {task_id}")

    if target.done:
        new_store = TodoStore(next_id=store.next_id, tasks=list(store.tasks))
        return new_store, target, False

    updated = dataclasses.replace(target, done=True)
    new_tasks = [updated if t.id == task_id else t for t in store.tasks]
    new_store = TodoStore(next_id=store.next_id, tasks=new_tasks)
    return new_store, updated, True


def remove_task(store: TodoStore, task_id: int) -> tuple[TodoStore, Task]:
    target = next((t for t in store.tasks if t.id == task_id), None)
    if target is None:
        raise TaskNotFoundError(f"no task with id {task_id}")

    new_tasks = [t for t in store.tasks if t.id != task_id]
    new_store = TodoStore(next_id=store.next_id, tasks=new_tasks)
    return new_store, target


def filter_tasks(
    tasks: list[Task], priority: str | None = None, due: str | None = None
) -> list[Task]:
    result = list(tasks)
    if priority is not None:
        result = [t for t in result if t.priority == priority]
    if due is not None:
        result = [t for t in result if t.due == due]
    return result


def sort_tasks(tasks: list[Task]) -> list[Task]:
    def key(task: Task) -> tuple[bool, int, date, int]:
        due_date = date.fromisoformat(task.due) if task.due is not None else date.max
        return (task.done, -PRIORITIES[task.priority], due_date, task.id)

    return sorted(tasks, key=key)


# --------------------------------------------------------------------------
# CLI layer
# --------------------------------------------------------------------------
def parse_due_arg(value: str) -> str:
    try:
        result = parse_due(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    assert result is not None
    return result


def positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid id: {value!r}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"id must be positive: {value!r}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo", description="Simple todo CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="add a task")
    add_p.add_argument("title", help="task title")
    add_p.add_argument("--due", type=parse_due_arg, default=None, help="YYYY-MM-DD")
    add_p.add_argument(
        "--priority",
        choices=tuple(PRIORITIES.keys()),
        default=DEFAULT_PRIORITY,
        help="task priority",
    )

    list_p = subparsers.add_parser("list", help="list tasks")
    list_p.add_argument(
        "--priority", choices=tuple(PRIORITIES.keys()), default=None
    )
    list_p.add_argument("--due", type=parse_due_arg, default=None, help="YYYY-MM-DD")

    done_p = subparsers.add_parser("done", help="mark a task done")
    done_p.add_argument("id", type=positive_int_arg, help="task id")

    rm_p = subparsers.add_parser("rm", help="remove a task")
    rm_p.add_argument("id", type=positive_int_arg, help="task id")

    return parser


def _format_row(task: Task) -> str:
    status = "[x]" if task.done else "[ ]"
    due = task.due if task.due is not None else "-"
    return f"{task.id}\t{status}\t{task.priority}\t{due}\t{task.title}"


def _cmd_add(args: argparse.Namespace) -> int:
    path = get_store_path()
    store = load_store(path)
    new_store, task = add_task(store, args.title, args.due, args.priority)
    save_store(new_store, path)
    print(f"added {task.id}")
    return EXIT_OK


def _cmd_list(args: argparse.Namespace) -> int:
    path = get_store_path()
    store = load_store(path)
    tasks = filter_tasks(store.tasks, priority=args.priority, due=args.due)
    for task in sort_tasks(tasks):
        print(_format_row(task))
    return EXIT_OK


def _cmd_done(args: argparse.Namespace) -> int:
    path = get_store_path()
    store = load_store(path)
    new_store, task, changed = mark_done(store, args.id)
    if changed:
        save_store(new_store, path)
        print(f"done {task.id}")
    else:
        print(f"already done {task.id}")
    return EXIT_OK


def _cmd_rm(args: argparse.Namespace) -> int:
    path = get_store_path()
    store = load_store(path)
    new_store, task = remove_task(store, args.id)
    save_store(new_store, path)
    print(f"removed {task.id}")
    return EXIT_OK


_HANDLERS = {
    "add": _cmd_add,
    "list": _cmd_list,
    "done": _cmd_done,
    "rm": _cmd_rm,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        if exc.code is None:
            return EXIT_OK
        return EXIT_USAGE

    handler = _HANDLERS[args.command]
    try:
        return handler(args)
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_STORAGE
    except TodoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_DOMAIN


if __name__ == "__main__":
    sys.exit(main())
