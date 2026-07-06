"""todo — a deliberately minimal personal todo CLI.

Three commands: add / list / done. One human-editable JSON store in the
home directory. Done items are hidden from `list` but kept forever.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class StoreError(Exception):
    """The store file cannot be used; it must never be modified in this state."""


class TaskNotFoundError(Exception):
    """Raised by mark_done when no task has the requested id."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"no task with id {task_id}")


class TaskAlreadyDoneError(Exception):
    """Raised by mark_done when the task is already marked done."""

    def __init__(self, task_id: int, title: str) -> None:
        self.task_id = task_id
        self.title = title
        super().__init__(f"task {task_id} is already done ({title})")


def store_path() -> Path:
    """Return the fixed storage path, independent of the current working directory.

    Using Path.home() (which resolves the HOME environment variable to an
    absolute path) ensures the same file is used regardless of which directory
    the `todo` command is invoked from.
    """
    return Path.home() / ".config" / "todo" / "todos.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _validate(raw: object, path: Path) -> list[dict]:
    # Hand-editing is the sanctioned recovery path, so a parseable-but-wrong
    # shape is the most likely corruption; refuse it as loudly as bad JSON.
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise StoreError(f'{path}: expected {{"items": [...]}} — refusing to touch it')
    for item in raw["items"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), int)
            or not isinstance(item.get("title"), str)
            or not isinstance(item.get("done"), bool)
            or not isinstance(item.get("created_at"), str)
        ):
            raise StoreError(f"{path}: item {item!r} is malformed — refusing to touch it")
    return raw["items"]


def load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StoreError(f"{path}: not valid JSON ({exc}) — fix or move the file; it was not modified") from exc
    return _validate(raw, path)


SCHEMA_VERSION = 1


def save_items(path: Path, items: list[dict]) -> None:
    data = json.dumps({"schema_version": SCHEMA_VERSION, "items": items}, indent=2, ensure_ascii=False) + "\n"
    # Create ~/.config/todo/ (and any intermediate dirs) on first write.
    # mkdir(parents=True, exist_ok=True) is idempotent — safe to call every time.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def cmd_add(args: argparse.Namespace) -> int:
    title = args.title.strip()
    if not title:
        print("error: title is empty", file=sys.stderr)
        return 1
    path = store_path()
    items = load_items(path)
    next_id = max((item["id"] for item in items), default=0) + 1
    items.append(
        {
            "id": next_id,
            "title": title,
            "done": False,
            "created_at": _now(),
            "completed_at": None,
        }
    )
    save_items(path, items)
    print(f"added #{next_id}: {title}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    open_items = [i for i in load_items(store_path()) if not i["done"]]
    for item in sorted(open_items, key=lambda i: i["id"]):
        print(f'{item["id"]} {item["title"]}')
    return 0


def mark_done(task_id: int, path: Path | None = None) -> dict:
    """Set the task's done flag and atomically persist the change to the store.

    Returns the updated task dict on success.

    Raises TaskNotFoundError  — if no task has the given id.
    Raises TaskAlreadyDoneError — if the task is already marked done.

    The file is never written on error, so the store is always left intact.
    """
    if path is None:
        path = store_path()
    items = load_items(path)
    match = next((i for i in items if i["id"] == task_id), None)
    if match is None:
        raise TaskNotFoundError(task_id)
    if match["done"]:
        raise TaskAlreadyDoneError(task_id, match["title"])
    match["done"] = True
    match["completed_at"] = _now()
    save_items(path, items)
    return match


def cmd_done(args: argparse.Namespace) -> int:
    path = store_path()
    try:
        task = mark_done(args.id, path)
        print(f'done #{args.id}: {task["title"]}')
        return 0
    except TaskNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except TaskAlreadyDoneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="add a task: todo add \"title\"")
    p_add.add_argument("title", help="task title")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="show open tasks")
    p_list.set_defaults(func=cmd_list)

    p_done = sub.add_parser("done", help="complete a task by id: todo done 3")
    p_done.add_argument("id", type=int, help="task id shown by `todo list`")
    p_done.set_defaults(func=cmd_done)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
