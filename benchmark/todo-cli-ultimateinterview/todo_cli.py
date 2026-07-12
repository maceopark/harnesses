from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno, json, os, stat, sys, tempfile, unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Final, NewType, Sequence, TypeAlias

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.config.argparsing import Parser


TaskId = NewType("TaskId", int); Title = NewType("Title", str)
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
STORE_PATH: Final = Path(".todo.json")
SCHEMA_VERSION: Final = 1
READ_OPEN_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


@dataclass(frozen=True, slots=True)
class Task:
    id: TaskId
    title: Title
    done: bool


@dataclass(frozen=True, slots=True)
class Store:
    items: tuple[Task, ...]


class InputError(Exception): pass


class StorageError(Exception): pass


class DuplicateMemberError(ValueError): pass


def canonical_title(raw: str) -> Title:
    title = raw.strip()
    if not title:
        raise InputError("title is empty")
    for character in title:
        if unicodedata.category(character) == "Cc":
            raise InputError(f"title contains U+{ord(character):04X}")
    try:
        title.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InputError(f"title contains U+{ord(title[error.start]):04X}") from None
    return Title(title)


def _reject_duplicate_members(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateMemberError(key)
        result[key] = value
    return result


def _schema_error(reason: str) -> StorageError: return StorageError(f"invalid schema: {reason}")


def _json_integer(value: JsonValue) -> bool: return isinstance(value, int) and not isinstance(value, bool)


def validate_store(value: JsonValue) -> Store:
    if not isinstance(value, dict) or set(value) != {"schema_version", "items"}:
        raise _schema_error("root must contain exactly schema_version and items")
    version = value["schema_version"]
    if not _json_integer(version) or version != SCHEMA_VERSION:
        raise _schema_error("schema_version must be integer 1")
    raw_items = value["items"]
    if not isinstance(raw_items, list):
        raise _schema_error("items must be an array")
    seen_ids: set[int] = set()
    tasks: list[Task] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict) or set(raw_item) != {"id", "title", "done"}:
            raise _schema_error(f"items[{index}] must contain exactly id, title, and done")
        raw_id = raw_item["id"]
        raw_title = raw_item["title"]
        raw_done = raw_item["done"]
        if not _json_integer(raw_id) or raw_id <= 0:
            raise _schema_error(f"items[{index}].id must be a positive integer")
        if raw_id in seen_ids:
            raise _schema_error(f"items[{index}].id is duplicated")
        if not isinstance(raw_title, str):
            raise _schema_error(f"items[{index}].title must be a string")
        try:
            title = canonical_title(raw_title)
        except InputError as error:
            raise _schema_error(f"items[{index}].{error}") from None
        if title != raw_title:
            raise _schema_error(f"items[{index}].title is not canonical")
        if not isinstance(raw_done, bool):
            raise _schema_error(f"items[{index}].done must be a boolean")
        seen_ids.add(raw_id)
        tasks.append(Task(id=TaskId(raw_id), title=title, done=raw_done))
    return Store(items=tuple(tasks))


def _read_descriptor(descriptor: int) -> bytes:
    return b"".join(iter(lambda: os.read(descriptor, 65536), b""))


def _store_is_nonregular() -> bool:
    try:
        return not stat.S_ISREG(STORE_PATH.lstat().st_mode)
    except OSError:
        return False


def load_store() -> Store:
    if not (READ_OPEN_FLAGS & getattr(os, "O_NOFOLLOW", 0)) and _store_is_nonregular():
        raise StorageError("invalid file type")
    try:
        descriptor = os.open(STORE_PATH, READ_OPEN_FLAGS)
    except FileNotFoundError:
        return Store(items=())
    except OSError as error:
        if error.errno == errno.ELOOP or _store_is_nonregular():
            raise StorageError("invalid file type") from None
        raise StorageError(f"read failed: {error}") from None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise StorageError("invalid file type")
        payload = _read_descriptor(descriptor)
    except OSError as error:
        raise StorageError(f"read failed: {error}") from None
    finally:
        os.close(descriptor)
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise StorageError("not valid UTF-8") from None
    try:
        parsed = json.loads(decoded, object_pairs_hook=_reject_duplicate_members)
    except (DuplicateMemberError, json.JSONDecodeError, RecursionError):
        raise StorageError("malformed JSON") from None
    return validate_store(parsed)


def _store_payload(store: Store) -> str:
    value: dict[str, JsonValue] = {
        "schema_version": SCHEMA_VERSION,
        "items": [
            {"id": int(task.id), "title": str(task.title), "done": task.done}
            for task in store.items
        ],
    }
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def save_store(store: Store) -> None:
    temporary_name: str | None = None
    try:
        metadata = STORE_PATH.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as error:
        raise StorageError(f"write failed: {error}") from None
    if metadata is not None:
        if not stat.S_ISREG(metadata.st_mode):
            raise StorageError("invalid file type")
        write_mode_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
        if metadata.st_mode & write_mode_bits == 0:
            raise StorageError("write failed: no write-mode bits")
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"{STORE_PATH.name}.", suffix=".tmp", dir=str(STORE_PATH.parent)
        )
        try:
            temporary = os.fdopen(descriptor, "w", encoding="utf-8", newline="\n")
        except OSError:
            os.close(descriptor)
            raise
        with temporary:
            temporary.write(_store_payload(store))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, STORE_PATH)
        temporary_name = None
    except OSError as error:
        raise StorageError(f"write failed: {error}") from None
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def next_id(store: Store) -> TaskId:
    return TaskId(max((int(task.id) for task in store.items), default=0) + 1)


def active_items(store: Store) -> tuple[Task, ...]:
    return tuple(sorted((task for task in store.items if not task.done), key=lambda task: task.id))


def complete_task(store: Store, task_id: int) -> Store | InputError:
    for task in store.items:
        if task.id == task_id:
            if task.done:
                return InputError(f"task {task_id} is already done ({task.title})")
            updated = Task(id=task.id, title=task.title, done=True)
            return Store(items=tuple(updated if item.id == task.id else item for item in store.items))
    return InputError(f"no task with id {task_id}")


def _write_error(error: InputError | StorageError, exit_code: int) -> int:
    prefix = ".todo.json: " if isinstance(error, StorageError) else ""
    print(f"error: {prefix}{error}", file=sys.stderr)
    return exit_code


def _add(title: str) -> int:
    try:
        canonical = canonical_title(title)
    except InputError as error:
        return _write_error(error, 1)
    try:
        store = load_store()
        task = Task(id=next_id(store), title=canonical, done=False)
        save_store(Store(items=(*store.items, task)))
    except StorageError as error:
        return _write_error(error, 3)
    print(f"added #{task.id}: {task.title}")
    return 0


def _list() -> int:
    try:
        store = load_store()
    except StorageError as error:
        return _write_error(error, 3)
    for task in active_items(store):
        print(f"{task.id} {task.title}")
    return 0


def _done(task_id: int) -> int:
    try:
        store = load_store()
    except StorageError as error:
        return _write_error(error, 3)
    transition = complete_task(store, task_id)
    if isinstance(transition, InputError):
        return _write_error(transition, 1)
    try:
        save_store(transition)
    except StorageError as error:
        return _write_error(error, 3)
    task = next(task for task in transition.items if task.id == task_id)
    print(f"done #{task.id}: {task.title}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add").add_argument("title")
    commands.add_parser("list")
    commands.add_parser("done").add_argument("id", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    if arguments.command == "add":
        return _add(arguments.title)
    if arguments.command == "list":
        return _list()
    return _done(arguments.id)


def pytest_load_initial_conftests(
    early_config: Config | None, parser: Parser | None, args: list[str]
) -> None:
    del early_config, parser
    if (
        Path.cwd().resolve() == Path(__file__).resolve().parents[2]
        and not any(Path(argument).exists() or argument.endswith(".py") for argument in args)
    ):
        args.append(str(Path(__file__).with_name("tests")))


if __name__ == "__main__":
    raise SystemExit(main())
