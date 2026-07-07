"""Morning todo CLI — blind-rebuild experiment arm.

Spec: Part 1 of .ultimateinterview/todo-cli-app-2/handoff.md.
Store: ~/.todo-rebuild/todos.json (human-readable JSON; hand-editing is the
sanctioned recovery path — clear an item's "done_at" to un-complete it,
remove its object to delete it). The tool itself never purges records and
never rewrites a store it cannot parse.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

STORE_DIR = ".todo-rebuild"
STORE_NAME = "todos.json"

STRIKE = "\x1b[9m"
RESET = "\x1b[0m"

EXIT_OK = 0
EXIT_STORE_ERROR = 1
EXIT_USAGE = 2

USAGE = """usage:
  todo               show today's view
  todo add <title>   add a pending item
  todo done <number> complete the pending item shown with that number"""


def store_path() -> Path:
    return Path.home() / STORE_DIR / STORE_NAME


class StoreError(Exception):
    """The store file exists but cannot be trusted; never write over it."""


def _valid_item(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    if not isinstance(obj.get("title"), str) or not isinstance(obj.get("created"), str):
        return False
    done_at = obj.get("done_at")
    return done_at is None or isinstance(done_at, str)


def load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StoreError(f"cannot read store file {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise StoreError(f'store file {path} is invalid: expected {{"items": [...]}}')
    items = data["items"]
    if not all(_valid_item(item) for item in items):
        raise StoreError(
            f"store file {path} is invalid: every item needs a string title,"
            ' a string created date, and "done_at" as null or a string'
        )
    return items


def save_items(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=STORE_NAME, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def pending(items: list[dict]) -> list[dict]:
    return [item for item in items if item["done_at"] is None]


def done_today(items: list[dict]) -> list[dict]:
    prefix = today()
    finished = [i for i in items if i["done_at"] is not None and i["done_at"][:10] == prefix]
    return sorted(finished, key=lambda item: item["done_at"])


def cmd_view(items: list[dict]) -> int:
    open_items = pending(items)
    finished = done_today(items)
    if not open_items and not finished:
        print(f"Todo — {today()}: nothing for today.")
        return EXIT_OK
    print(f"Todo — {today()}")
    for number, item in enumerate(open_items, start=1):
        print(f"  {number}. {item['title']}")
    if finished:
        print("Done today:")
        for item in finished:
            print(f"  {STRIKE}{item['title']}{RESET}")
    return EXIT_OK


def cmd_add(items: list[dict], path: Path, title: str) -> int:
    if not title.strip():
        print("error: todo title is empty or whitespace-only; nothing added.", file=sys.stderr)
        return EXIT_USAGE
    items.append({"title": title, "created": today(), "done_at": None})
    save_items(path, items)
    print(f"added: {title}")
    return EXIT_OK


def cmd_done(items: list[dict], path: Path, raw_number: str) -> int:
    open_items = pending(items)
    try:
        number = int(raw_number)
    except ValueError:
        print(f"error: '{raw_number}' is not an item number.", file=sys.stderr)
        return EXIT_USAGE
    if not 1 <= number <= len(open_items):
        print(
            f"error: no pending item {number} (there are {len(open_items)} pending items).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    item = open_items[number - 1]
    item["done_at"] = now_stamp()
    save_items(path, items)
    print(f"done: {STRIKE}{item['title']}{RESET}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = store_path()
    try:
        items = load_items(path)
    except StoreError as error:
        print(f"error: {error}", file=sys.stderr)
        print("fix the file by hand (it was not modified) and rerun.", file=sys.stderr)
        return EXIT_STORE_ERROR

    if not args:
        return cmd_view(items)
    command, rest = args[0], args[1:]
    if command == "add":
        return cmd_add(items, path, " ".join(rest))
    if command == "done":
        if len(rest) != 1:
            print("error: done takes exactly one item number.", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return EXIT_USAGE
        return cmd_done(items, path, rest[0])
    print(f"error: unknown command '{command}'.", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
