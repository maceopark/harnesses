from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from scripts.forward_harness_contract import (
    CORPUS_MANIFEST,
    EXPECTED_NAME,
    ForwardHarnessError,
    corpus_files,
)

type CorpusFileSnapshot = tuple[Path, int, int, str, bytes]


@dataclass(frozen=True, slots=True)
class CorpusSnapshot:
    files: tuple[CorpusFileSnapshot, ...]
    directories: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class StagedOutput:
    path: Path
    content: bytes
    digest: str
    snapshot: CorpusFileSnapshot


def safe_write(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ForwardHarnessError(
                "regeneration requires regular unlinked target files"
            )
        os.ftruncate(descriptor, 0)
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            descriptor = -1
            _ = target.write(content)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _snapshot_file(path: Path) -> CorpusFileSnapshot:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ForwardHarnessError(
                "regeneration requires regular unlinked target files"
            )
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            contents = source.read()
    except OSError as error:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return (
        path,
        info.st_dev,
        info.st_ino,
        hashlib.sha256(contents).hexdigest(),
        contents,
    )


def corpus_snapshot(root: Path) -> CorpusSnapshot:
    if root.is_symlink() or not root.is_dir():
        raise ForwardHarnessError("regeneration target changed after preflight")
    files = (*corpus_files(root), root / CORPUS_MANIFEST)
    directories = tuple(sorted(path for path in root.rglob("*") if path.is_dir()))
    return CorpusSnapshot(
        files=tuple(sorted(_snapshot_file(path) for path in files)),
        directories=directories,
    )


def _verify_corpus_snapshot(root: Path, snapshot: CorpusSnapshot) -> None:
    try:
        current = corpus_snapshot(root)
    except ForwardHarnessError:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from None
    if current != snapshot:
        raise ForwardHarnessError("regeneration target changed after preflight")


def _snapshot_index(snapshot: CorpusSnapshot) -> dict[Path, CorpusFileSnapshot]:
    return {path: member for member in snapshot.files for path in (member[0],)}


def _staged_outputs(
    root: Path, stage: Path, snapshot: CorpusSnapshot
) -> tuple[StagedOutput, ...]:
    members = _snapshot_index(snapshot)
    expected_paths = tuple(
        sorted(path for path in members if path.name == EXPECTED_NAME)
    )
    targets = (*expected_paths, root / CORPUS_MANIFEST)
    staged = tuple(sorted(path for path in stage.rglob("*") if path.is_file()))
    if tuple(path.relative_to(stage) for path in staged) != tuple(
        sorted(path.relative_to(root) for path in targets)
    ):
        raise ForwardHarnessError(
            "regeneration stage contains unexpected generated members"
        )
    try:
        staged_outputs = tuple(
            (path, (stage / path.relative_to(root)).read_bytes(), members[path])
            for path in targets
        )
    except OSError as error:
        raise ForwardHarnessError("cannot read staged regenerated corpus") from error
    return tuple(
        StagedOutput(
            path=path,
            content=content,
            digest=hashlib.sha256(content).hexdigest(),
            snapshot=member,
        )
        for path, content, member in staged_outputs
    )


def _verify_static_snapshot(
    root: Path, snapshot: CorpusSnapshot, generated: tuple[Path, ...]
) -> None:
    generated_set = set(generated)
    try:
        current = corpus_snapshot(root)
    except ForwardHarnessError:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from None
    expected_files = tuple(
        member for member in snapshot.files if member[0] not in generated_set
    )
    current_files = tuple(
        member for member in current.files if member[0] not in generated_set
    )
    if current_files != expected_files or current.directories != snapshot.directories:
        raise ForwardHarnessError("regeneration target changed after preflight")


def _write_snapshot_target(
    path: Path,
    content: bytes,
    snapshot: CorpusFileSnapshot,
    expected_digest: str,
) -> None:
    flags = os.O_RDWR | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ForwardHarnessError(
            "regeneration target changed after preflight"
        ) from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or (info.st_dev, info.st_ino) != snapshot[1:3]
        ):
            raise ForwardHarnessError("regeneration target changed after preflight")
        with os.fdopen(descriptor, "r+b") as target:
            descriptor = -1
            if hashlib.sha256(target.read()).hexdigest() != expected_digest:
                raise ForwardHarnessError("regeneration target changed after preflight")
            _ = target.seek(0)
            _ = target.truncate()
            _ = target.write(content)
            target.flush()
            os.fsync(target.fileno())
            current = os.stat(path, follow_symlinks=False)
            if (
                (current.st_dev, current.st_ino) != snapshot[1:3]
                or not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
            ):
                raise ForwardHarnessError("regeneration target changed after preflight")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_snapshot_target(
    path: Path, content: bytes, snapshot: CorpusFileSnapshot
) -> None:
    _write_snapshot_target(path, content, snapshot, snapshot[3])


def _verify_published_outputs(outputs: tuple[StagedOutput, ...]) -> None:
    for output in outputs:
        descriptor = -1
        try:
            descriptor = os.open(output.path, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != output.snapshot[1:3]
            ):
                raise ForwardHarnessError(
                    "published generated output changed after publication"
                )
            with os.fdopen(descriptor, "rb") as source:
                descriptor = -1
                published_digest = hashlib.sha256(source.read()).hexdigest()
        except OSError as error:
            raise ForwardHarnessError(
                "published generated output changed after publication"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if published_digest != output.digest:
            raise ForwardHarnessError(
                "published generated output changed after publication"
            )


def commit_staged_corpus(root: Path, stage: Path, snapshot: CorpusSnapshot) -> None:
    outputs = _staged_outputs(root, stage, snapshot)
    generated = tuple(output.path for output in outputs)
    expected = tuple(output for output in outputs if output.path.name == EXPECTED_NAME)
    manifest = tuple(
        output for output in outputs if output.path == root / CORPUS_MANIFEST
    )
    if len(manifest) != 1:
        raise ForwardHarnessError("regeneration stage lacks a corpus manifest")
    _verify_corpus_snapshot(root, snapshot)
    _verify_static_snapshot(root, snapshot, generated)
    attempted: list[StagedOutput] = []
    try:
        for output in expected:
            _verify_static_snapshot(root, snapshot, generated)
            attempted.append(output)
            write_snapshot_target(output.path, output.content, output.snapshot)
            _verify_static_snapshot(root, snapshot, generated)
        _verify_static_snapshot(root, snapshot, generated)
        output = manifest[0]
        attempted.append(output)
        write_snapshot_target(output.path, output.content, output.snapshot)
        _verify_static_snapshot(root, snapshot, generated)
        _verify_published_outputs(outputs)
    except ForwardHarnessError as error:
        for output in reversed(attempted):
            try:
                _write_snapshot_target(
                    output.path, output.snapshot[4], output.snapshot, output.digest
                )
            except ForwardHarnessError as rollback_error:
                error.add_note(
                    f"rollback preserved changed target: {output.path}: {rollback_error}"
                )
        raise
