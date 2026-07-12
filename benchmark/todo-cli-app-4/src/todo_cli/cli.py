from __future__ import annotations

import sys
import unicodedata
from typing import NamedTuple

from .model import DONE, OPEN, Store, Task
from .storage import StorageError, load, resolve_path, save

_USAGE = """usage: todo add <title...>
       todo list
       todo completed
       todo all
       todo complete <id>
       todo undo <id>
       todo delete <id>"""

_READ_COMMANDS = {"list", "completed", "all"}
_ID_COMMANDS = {"complete", "undo", "delete"}
_COMMANDS = {"add", *_READ_COMMANDS, *_ID_COMMANDS}


class UsageError(Exception):
    pass


class DomainError(Exception):
    pass


class ParsedCommand(NamedTuple):
    name: str
    title: str | None = None
    task_id: int | None = None


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    try:
        command = _parse_args(args)
    except UsageError as exc:
        _print_usage_error(str(exc))
        return 2

    try:
        if command.name == "add" and command.title is not None:
            _validate_title(command.title)
    except DomainError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    path = resolve_path()
    try:
        store = load(path)
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    try:
        return _dispatch(command, store, path)
    except DomainError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except StorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


def _parse_args(args: list[str]) -> ParsedCommand:
    if not args:
        raise UsageError("missing subcommand")

    command = args[0]
    rest = args[1:]
    if command not in _COMMANDS:
        raise UsageError(f"unknown subcommand: {command}")

    if command == "add":
        if not rest:
            raise UsageError("add requires a title")
        return ParsedCommand(name=command, title=" ".join(rest).strip())

    if command in _READ_COMMANDS:
        if rest:
            raise UsageError(f"{command} does not accept arguments")
        return ParsedCommand(name=command)

    if len(rest) == 0:
        raise UsageError(f"{command} requires an id")
    if len(rest) > 1:
        raise UsageError(f"{command} accepts exactly one id")
    return ParsedCommand(name=command, task_id=_parse_id(rest[0]))


def _parse_id(token: str) -> int:
    if not token or any(char not in "0123456789" for char in token):
        raise UsageError(f"invalid id: {token}")
    task_id = int(token)
    if task_id <= 0:
        raise UsageError(f"invalid id: {token}")
    return task_id


def _validate_title(title: str) -> None:
    if not title:
        raise DomainError("title must not be empty")
    if any(unicodedata.category(char) == "Cc" for char in title):
        raise DomainError("title must not contain control characters")
    if len(title) > 1024:
        raise DomainError("title must be at most 1024 characters")


def _dispatch(command: ParsedCommand, store: Store, path) -> int:
    if command.name == "add":
        return _add(store, path, _required_title(command))
    if command.name == "list":
        return _print_tasks(store, OPEN)
    if command.name == "completed":
        return _print_tasks(store, DONE)
    if command.name == "all":
        return _print_tasks(store, None)
    if command.name == "complete":
        return _complete(store, path, _required_task_id(command))
    if command.name == "undo":
        return _undo(store, path, _required_task_id(command))
    if command.name == "delete":
        return _delete(store, path, _required_task_id(command))
    raise UsageError(f"unknown subcommand: {command.name}")


def _add(store: Store, path, title: str) -> int:
    task_id = store.next_id
    store.tasks.append(Task(id=task_id, title=title, status=OPEN))
    store.next_id += 1
    save(store, path)
    print(f"added {task_id}")
    return 0


def _print_tasks(store: Store, status: str | None) -> int:
    tasks = sorted(store.tasks, key=lambda task: task.id)
    for task in tasks:
        if status is not None and task.status != status:
            continue
        marker = "[x]" if task.status == DONE else "[ ]"
        print(f"{task.id}\t{marker}\t{task.title}")
    return 0


def _complete(store: Store, path, task_id: int) -> int:
    task = _get_task(store, task_id)
    if task.status == DONE:
        raise DomainError(f"task {task_id} is already done")
    task.status = DONE
    save(store, path)
    print(f"completed {task_id}")
    return 0


def _undo(store: Store, path, task_id: int) -> int:
    task = _get_task(store, task_id)
    if task.status == OPEN:
        raise DomainError(f"task {task_id} is not done")
    task.status = OPEN
    save(store, path)
    print(f"undone {task_id}")
    return 0


def _delete(store: Store, path, task_id: int) -> int:
    _get_task(store, task_id)
    store.tasks = [task for task in store.tasks if task.id != task_id]
    save(store, path)
    print(f"deleted {task_id}")
    return 0


def _get_task(store: Store, task_id: int) -> Task:
    for task in store.tasks:
        if task.id == task_id:
            return task
    raise DomainError(f"no such task: {task_id}")


def _required_title(command: ParsedCommand) -> str:
    assert command.title is not None
    return command.title


def _required_task_id(command: ParsedCommand) -> int:
    assert command.task_id is not None
    return command.task_id


def _print_usage_error(message: str) -> None:
    print(_USAGE, file=sys.stderr)
    print(f"error: {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
