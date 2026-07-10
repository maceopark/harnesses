from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Final

try:
    import fcntl
except ModuleNotFoundError as error:
    raise RuntimeError(
        "ultimateinterview state helpers require a POSIX host with fcntl locking",
    ) from error

Replace = Callable[[str | Path, str | Path], None]
Stage = Callable[[Path, str], Path]
JOURNAL_NAME: Final[str] = ".session-update-journal.json"
LOCK_NAME: Final[str] = ".session-update.lock"


def staged_file(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    staged = Path(raw_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def session_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / LOCK_NAME).open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _target_record(path: Path, content: str | None, root: Path) -> dict[str, object]:
    resolved_root = root.resolve()
    resolved_path = path.resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"transaction path escapes root: {path}")
    return {
        "path": str(resolved_path.relative_to(resolved_root)),
        "existed": content is not None,
        "content": content,
    }


def write_recovery_journal(
    originals: Mapping[Path, str | None],
    *,
    root: Path,
) -> None:
    payload = {
        "version": 1,
        "originals": [
            _target_record(path, content, root)
            for path, content in originals.items()
        ],
    }
    journal = root / JOURNAL_NAME
    staged = staged_file(journal, json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        os.replace(staged, journal)
        fsync_directory(root)
    finally:
        staged.unlink(missing_ok=True)


def _recover_text_files(root: Path) -> None:
    journal = root / JOURNAL_NAME
    if not journal.is_file():
        return
    payload = json.loads(journal.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("originals"), list):
        raise ValueError(f"invalid recovery journal: {journal}")
    resolved_root = root.resolve()
    for record in payload["originals"]:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ValueError(f"invalid recovery journal record: {record!r}")
        target = (resolved_root / record["path"]).resolve(strict=False)
        if not target.is_relative_to(resolved_root):
            raise ValueError(f"recovery path escapes session root: {target}")
        if record.get("existed"):
            content = record.get("content")
            if not isinstance(content, str):
                raise ValueError(f"invalid recovery content for {target}")
            os.replace(staged_file(target, content), target)
        else:
            target.unlink(missing_ok=True)
    journal.unlink()
    fsync_directory(root)


def recover_text_files(root: Path) -> None:
    with session_lock(root):
        _recover_text_files(root)


@contextmanager
def session_transaction(root: Path) -> Iterator[None]:
    with session_lock(root):
        _recover_text_files(root)
        yield


def _transaction_root(paths: tuple[Path, ...]) -> Path:
    if not paths:
        raise ValueError("at least one update is required")
    return Path(os.path.commonpath([str(path.parent.resolve()) for path in paths]))


def _commit_text_files(
    updates: Mapping[Path, str],
    *,
    root: Path,
    replace: Replace,
    stage: Stage,
) -> None:
    originals = {
        path: path.read_text(encoding="utf-8") if path.exists() else None
        for path in updates
    }
    staged: dict[Path, Path] = {}
    try:
        for path, content in updates.items():
            staged[path] = stage(path, content)
    except BaseException:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        raise

    committed: list[Path] = []
    try:
        write_recovery_journal(originals, root=root)
        for path, temporary in staged.items():
            replace(temporary, path)
            committed.append(path)
        fsync_directory(root)
    except BaseException:
        for path in reversed(committed):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(staged_file(path, original), path)
        fsync_directory(root)
        (root / JOURNAL_NAME).unlink(missing_ok=True)
        fsync_directory(root)
        raise
    else:
        (root / JOURNAL_NAME).unlink(missing_ok=True)
        fsync_directory(root)
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def commit_text_files(
    updates: Mapping[Path, str],
    *,
    replace: Replace = os.replace,
    stage: Stage = staged_file,
    locked: bool = False,
) -> None:
    paths = tuple(updates)
    root = _transaction_root(paths)
    if locked:
        _commit_text_files(updates, root=root, replace=replace, stage=stage)
        return
    with session_transaction(root):
        _commit_text_files(updates, root=root, replace=replace, stage=stage)
