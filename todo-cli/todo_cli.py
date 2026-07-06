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


def store_path() -> Path:
    return Path.home() / ".todo.json"


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
            or item.get("status") not in ("open", "done")
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


def save_items(path: Path, items: list[dict]) -> None:
    data = json.dumps({"items": items}, indent=2, ensure_ascii=False) + "\n"
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
            "status": "open",
            "created_at": _now(),
            "completed_at": None,
        }
    )
    save_items(path, items)
    print(f"added #{next_id}: {title}")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    open_items = [i for i in load_items(store_path()) if i["status"] == "open"]
    if not open_items:
        print("nothing to do")
        return 0
    for item in sorted(open_items, key=lambda i: i["id"]):
        print(f'{item["id"]:>4}  {item["title"]}')
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    path = store_path()
    items = load_items(path)
    match = next((i for i in items if i["id"] == args.id), None)
    if match is None:
        print(f"error: no task with id {args.id}", file=sys.stderr)
        return 1
    if match["status"] == "done":
        print(f'error: task {args.id} is already done ({match["title"]})', file=sys.stderr)
        return 1
    match["status"] = "done"
    match["completed_at"] = _now()
    save_items(path, items)
    print(f'done #{args.id}: {match["title"]}')
    return 0


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
