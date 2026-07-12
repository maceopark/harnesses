"""claudeplan CLI: add / list / done / delete over a single JSON store.

Exit codes: 0 success, 1 domain/data error, 2 usage/validation error (argparse).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__

PRIORITIES = ("high", "medium", "low")
PRIORITY_RANK = {name: rank for rank, name in enumerate(PRIORITIES)}
STORE_VERSION = 1
STORE_FILENAME = "todos.json"
DUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StoreError(Exception):
    """The store file cannot be used; it is left untouched."""


class DomainError(Exception):
    """A well-formed command that cannot be applied to the current data."""


# --- validation ---------------------------------------------------------

def parse_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise argparse.ArgumentTypeError("title must not be empty")
    return title


def parse_due(value: str) -> str:
    # Regex first: date.fromisoformat on 3.11+ also accepts YYYYMMDD and week dates.
    if not DUE_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid date '{value}' (expected YYYY-MM-DD)")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}' (expected YYYY-MM-DD)") from None
    return value


def _today() -> date:  # seam so tests can freeze the clock
    return date.today()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- store --------------------------------------------------------------

def store_path() -> Path:
    override = os.environ.get("CLAUDEPLAN_HOME")
    if override:
        return Path(override) / STORE_FILENAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "claudeplan" / STORE_FILENAME
    return Path.home() / ".config" / "claudeplan" / STORE_FILENAME


def _corrupt(path: Path, detail: object) -> StoreError:
    return StoreError(
        f"todo store at {path} is corrupted or unreadable; refusing to modify it. "
        f"Back up and inspect the file manually. ({detail})"
    )


def empty_store() -> dict:
    return {"version": STORE_VERSION, "next_id": 1, "todos": []}


def load_store(path: Path) -> dict:
    if not path.exists():
        return empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _corrupt(path, exc) from exc
    if not isinstance(data, dict):
        raise _corrupt(path, "top-level value is not an object")
    version = data.get("version")
    if not isinstance(version, int):
        raise _corrupt(path, "missing or invalid 'version'")
    if version > STORE_VERSION:
        raise StoreError(
            f"todo store at {path} was written by a newer version of claudeplan "
            f"(store version {version}, supported {STORE_VERSION})"
        )
    if not isinstance(data.get("next_id"), int) or not isinstance(data.get("todos"), list):
        raise _corrupt(path, "missing or invalid 'next_id' or 'todos'")
    for item in data["todos"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), int)
            or not isinstance(item.get("title"), str)
            or item.get("priority") not in PRIORITIES
            or not isinstance(item.get("done"), bool)
            or (item.get("due") is not None and not isinstance(item["due"], str))
        ):
            raise _corrupt(path, f"malformed todo entry: {item!r}")
    return data


def save_store(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".todos-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --- domain operations ---------------------------------------------------

def find_todo(store: dict, todo_id: int) -> dict | None:
    for todo in store["todos"]:
        if todo["id"] == todo_id:
            return todo
    return None


def sort_key(todo: dict) -> tuple:
    # ISO date strings compare lexicographically in chronological order;
    # (1, "") places no-due-date items after every dated item.
    due = todo.get("due")
    return (PRIORITY_RANK[todo["priority"]], (0, due) if due else (1, ""), todo["id"])


def render_table(todos: list[dict]) -> str:
    id_width = max(len("ID"), *(len(str(t["id"])) for t in todos))
    lines = [f"{'ID':>{id_width}}  {'St':<3}  {'Pri':<6}  {'Due':<10}  Title"]
    for t in todos:
        status = "[x]" if t["done"] else "[ ]"
        due = t.get("due") or "-"
        lines.append(
            f"{t['id']:>{id_width}}  {status:<3}  {t['priority']:<6}  {due:<10}  {t['title']}"
        )
    return "\n".join(lines)


# --- commands -------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    todo = {
        "id": store["next_id"],
        "title": args.title,
        "priority": args.priority,
        "due": args.due,
        "done": False,
        "created_at": _now_iso(),
        "completed_at": None,
    }
    store["todos"].append(todo)
    store["next_id"] += 1
    save_store(path, store)
    print(f'Added todo {todo["id"]}: "{todo["title"]}"')
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    todos = load_store(store_path())["todos"]
    if args.done:
        todos = [t for t in todos if t["done"]]
    elif not args.all:
        todos = [t for t in todos if not t["done"]]
    if args.priority:
        todos = [t for t in todos if t["priority"] == args.priority]
    if args.due_before:
        todos = [t for t in todos if t.get("due") and t["due"] < args.due_before]
    if args.overdue:
        today = _today().isoformat()
        todos = [t for t in todos if t.get("due") and t["due"] < today]
    todos = sorted(todos, key=sort_key)
    if not todos:
        print("No todos found.")
        return 0
    print(render_table(todos))
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    todo = find_todo(store, args.id)
    if todo is None:
        raise DomainError(f"no todo with id {args.id}")
    if todo["done"]:
        raise DomainError(f"todo {args.id} is already done")
    todo["done"] = True
    todo["completed_at"] = _now_iso()
    save_store(path, store)
    print(f'Completed todo {todo["id"]}: "{todo["title"]}"')
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    path = store_path()
    store = load_store(path)
    todo = find_todo(store, args.id)
    if todo is None:
        raise DomainError(f"no todo with id {args.id}")
    store["todos"].remove(todo)
    save_store(path, store)
    print(f'Deleted todo {todo["id"]}: "{todo["title"]}"')
    return 0


# --- CLI wiring ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo", description="claudeplan: a minimal todo list CLI"
    )
    parser.add_argument("--version", action="version", version=f"claudeplan {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="add a new todo")
    p_add.add_argument("title", type=parse_title, help="todo title (quote multi-word titles)")
    p_add.add_argument("-p", "--priority", choices=PRIORITIES, default="medium")
    p_add.add_argument("-d", "--due", type=parse_due, default=None, metavar="YYYY-MM-DD")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list todos")
    status = p_list.add_mutually_exclusive_group()
    status.add_argument("--all", action="store_true", help="include completed todos")
    status.add_argument("--done", action="store_true", help="show only completed todos")
    p_list.add_argument("--priority", choices=PRIORITIES, default=None)
    p_list.add_argument("--due-before", type=parse_due, default=None, metavar="YYYY-MM-DD")
    p_list.add_argument("--overdue", action="store_true", help="due strictly before today")
    p_list.set_defaults(func=cmd_list)

    p_done = sub.add_parser("done", help="mark a todo as completed")
    p_done.add_argument("id", type=int)
    p_done.set_defaults(func=cmd_done)

    p_delete = sub.add_parser("delete", help="delete a todo")
    p_delete.add_argument("id", type=int)
    p_delete.set_defaults(func=cmd_delete)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (DomainError, StoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
