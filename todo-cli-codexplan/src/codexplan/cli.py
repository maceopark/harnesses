"""Command-line boundary for the codexplan executable."""

import sys
from collections.abc import Sequence

from codexplan.storage import (
    DomainError,
    StorageError,
    add_task,
    format_task,
    load_store,
    mark_done,
    parse_task_id,
    parse_title,
    remove_task,
    save_store,
    store_path_from_env,
)

EXIT_OK = 0
EXIT_DOMAIN = 1
EXIT_USAGE = 2
EXIT_STORAGE = 3

USAGE = """usage: codexplan <command> [args]

commands:
  add TITLE
  list
  done ID
  rm ID
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run codexplan and return a process-style exit code."""
    args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except DomainError as exc:
        _ = sys.stderr.write(f"error: {exc}\n")
        return EXIT_DOMAIN
    except StorageError as exc:
        _ = sys.stderr.write(f"error: {exc}\n")
        return EXIT_STORAGE


def run(args: tuple[str, ...]) -> int:
    """Dispatch parsed command tokens to the requested command."""
    match args:
        case ("--help",) | ("-h",):
            _ = sys.stdout.write(USAGE)
            result = EXIT_OK
        case ("list",):
            result = list_tasks()
        case ("add", raw_title):
            result = add(raw_title)
        case ("done", raw_id):
            result = done(raw_id)
        case ("rm", raw_id):
            result = remove(raw_id)
        case ("done" | "rm", *_):
            result = usage_error()
        case ("add", *_):
            result = usage_error()
        case _:
            result = usage_error()
    return result


def usage_error() -> int:
    """Write usage text for invalid command shapes."""
    _ = sys.stderr.write(USAGE)
    return EXIT_USAGE


def add(raw_title: str) -> int:
    """Add a todo and print its immutable id."""
    title = parse_title(raw_title)
    path = store_path_from_env()
    store = load_store(path)
    updated_store, task_id = add_task(store, title)
    save_store(path, updated_store)
    _ = sys.stdout.write(f"added {int(task_id)}\n")
    return EXIT_OK


def list_tasks() -> int:
    """Print all todos sorted by immutable id."""
    store = load_store(store_path_from_env())
    for task in sorted(store.tasks, key=lambda item: int(item.id)):
        _ = sys.stdout.write(f"{format_task(task)}\n")
    return EXIT_OK


def done(raw_id: str) -> int:
    """Mark a todo complete by immutable id."""
    if not is_integer_token(raw_id):
        return usage_error()
    task_id = parse_task_id(raw_id)
    path = store_path_from_env()
    store = load_store(path)
    updated_store, changed = mark_done(store, task_id)
    if changed:
        save_store(path, updated_store)
        _ = sys.stdout.write(f"done {int(task_id)}\n")
        return EXIT_OK
    _ = sys.stdout.write(f"already done {int(task_id)}\n")
    return EXIT_OK


def remove(raw_id: str) -> int:
    """Remove a todo by immutable id."""
    if not is_integer_token(raw_id):
        return usage_error()
    task_id = parse_task_id(raw_id)
    path = store_path_from_env()
    store = load_store(path)
    updated_store = remove_task(store, task_id)
    save_store(path, updated_store)
    _ = sys.stdout.write(f"removed {int(task_id)}\n")
    return EXIT_OK


def is_integer_token(raw_id: str) -> bool:
    """Return whether a CLI token is syntactically an integer."""
    if raw_id.isdecimal():
        return True
    return raw_id[:1] in {"-", "+"} and raw_id[1:].isdecimal()
