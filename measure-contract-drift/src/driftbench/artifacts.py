"""Closed, regular-file-only artifact manifests.

This module never follows artifact symlinks and does not invoke external tools.
A manifest is a complete snapshot of the directory tree below a supplied root:
regular file bytes, mode, size, and link count must all match during validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, field_validator, model_validator


class ArtifactValidationError(ValueError):
    """Raised when an artifact tree is unsafe or differs from its manifest."""


@dataclass(frozen=True, slots=True)
class ArtifactLimits:
    """Resource ceilings enforced while closing an artifact tree."""

    max_files: int = 1_024
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_files", "max_file_bytes", "max_total_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ArtifactValidationError(f"{name} must be a non-negative integer")


class _ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ArtifactEntry(_ArtifactModel):
    """A regular file recorded by a closed artifact manifest."""

    path: StrictStr = Field(min_length=1)
    digest: StrictStr = Field(min_length=64, max_length=64)
    size: StrictInt = Field(ge=0)
    mode: StrictInt = Field(ge=0, le=0o7777)
    link_count: StrictInt = Field(ge=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("digest must be lowercase SHA-256 hexadecimal")
        return value

    @model_validator(mode="after")
    def require_single_link(self) -> ArtifactEntry:
        if self.link_count != 1:
            raise ValueError("artifact entries must have exactly one hard link")
        return self


class ArtifactDirectory(_ArtifactModel):
    """A real directory required for exact closure, excluding the manifest root."""

    path: StrictStr = Field(min_length=1)
    mode: StrictInt = Field(ge=0, le=0o7777)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class ArtifactManifest(_ArtifactModel):
    """Canonical shape for a regular-file-only artifact closure."""

    schema_: Literal["ArtifactManifest.v1"] = Field(default="ArtifactManifest.v1", alias="schema", serialization_alias="schema")
    entries: tuple[ArtifactEntry, ...]
    directories: tuple[ArtifactDirectory, ...] = ()
    total_size: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def validate_closure(self) -> ArtifactManifest:
        entry_paths = tuple(entry.path for entry in self.entries)
        directory_paths = tuple(directory.path for directory in self.directories)
        if entry_paths != tuple(sorted(entry_paths)) or len(set(entry_paths)) != len(entry_paths):
            raise ValueError("artifact entries must be unique and sorted by path")
        if directory_paths != tuple(sorted(directory_paths)) or len(set(directory_paths)) != len(directory_paths):
            raise ValueError("artifact directories must be unique and sorted by path")
        if set(entry_paths).intersection(directory_paths):
            raise ValueError("an artifact path cannot be both a file and directory")
        if sum(entry.size for entry in self.entries) != self.total_size:
            raise ValueError("total_size does not equal the sum of entry sizes")
        return self


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("artifact path must be a non-empty, NUL-free string")
    if "\\" in value or value.startswith("/"):
        raise ValueError("artifact path must be a relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("artifact path must not contain traversal components")
    return "/".join(parts)


def _coerce_limits(limits: ArtifactLimits | Mapping[str, object] | None) -> ArtifactLimits:
    if limits is None:
        return ArtifactLimits()
    if isinstance(limits, ArtifactLimits):
        return limits
    if not isinstance(limits, Mapping):
        raise ArtifactValidationError("limits must be ArtifactLimits or an object")
    allowed = {"max_files", "max_file_bytes", "max_total_bytes"}
    unknown = set(limits).difference(allowed)
    if unknown:
        raise ArtifactValidationError(f"unknown artifact limit: {sorted(unknown)[0]}")
    try:
        return ArtifactLimits(**dict(limits))
    except (TypeError, ArtifactValidationError) as error:
        raise ArtifactValidationError("invalid artifact limits") from error


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_nlink,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _require_directory(info: os.stat_result, path: str) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise ArtifactValidationError(f"symlinked directory is forbidden: {path}")
    if not stat.S_ISDIR(info.st_mode):
        raise ArtifactValidationError(f"artifact tree contains a non-directory: {path}")


def _require_regular_single_link(info: os.stat_result, path: str) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise ArtifactValidationError(f"symlinked artifact is forbidden: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactValidationError(f"artifact must be a regular file: {path}")
    if info.st_nlink != 1:
        raise ArtifactValidationError(f"artifact must have exactly one hard link: {path}")


def _open_flags(*, directory: bool = False) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    try:
        if dir_fd is None:
            return os.open(name, _open_flags(directory=True))
        return os.open(name, _open_flags(directory=True), dir_fd=dir_fd)
    except OSError as error:
        raise ArtifactValidationError(f"cannot open artifact directory {name}") from error


def _read_regular_entry(
    directory_fd: int,
    name: str,
    relative_path: str,
    expected: os.stat_result,
    limits: ArtifactLimits,
) -> ArtifactEntry:
    _require_regular_single_link(expected, relative_path)
    if expected.st_size > limits.max_file_bytes:
        raise ArtifactValidationError(f"artifact exceeds max_file_bytes: {relative_path}")
    try:
        descriptor = os.open(name, _open_flags(), dir_fd=directory_fd)
    except OSError as error:
        raise ArtifactValidationError(f"cannot open artifact file {relative_path}") from error
    try:
        opened = os.fstat(descriptor)
        _require_regular_single_link(opened, relative_path)
        if _stat_signature(opened) != _stat_signature(expected):
            raise ArtifactValidationError(f"artifact changed while being closed: {relative_path}")

        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            size += len(chunk)
            if size > limits.max_file_bytes:
                raise ArtifactValidationError(f"artifact exceeds max_file_bytes: {relative_path}")
            digest.update(chunk)
        final = os.fstat(descriptor)
        _require_regular_single_link(final, relative_path)
        if _stat_signature(final) != _stat_signature(opened) or size != final.st_size:
            raise ArtifactValidationError(f"artifact changed while being read: {relative_path}")
    finally:
        os.close(descriptor)

    return ArtifactEntry(
        path=relative_path,
        digest=digest.hexdigest(),
        size=size,
        mode=stat.S_IMODE(final.st_mode),
        link_count=final.st_nlink,
    )


def _close_directory(
    directory_fd: int,
    relative_prefix: str,
    expected: os.stat_result,
    limits: ArtifactLimits,
    entries: list[ArtifactEntry],
    directories: list[ArtifactDirectory],
) -> None:
    """Close an already-open directory using descriptor-relative child opens."""

    opened = os.fstat(directory_fd)
    _require_directory(opened, relative_prefix or ".")
    if _stat_signature(opened) != _stat_signature(expected):
        raise ArtifactValidationError("artifact directory changed while being closed")
    scan_fd = os.dup(directory_fd)
    try:
        with os.scandir(scan_fd) as iterator:
            children = sorted(
                ((entry.name, entry.stat(follow_symlinks=False)) for entry in iterator),
                key=lambda item: item[0],
            )
    except OSError as error:
        try:
            os.close(scan_fd)
        except OSError:
            pass
        raise ArtifactValidationError("cannot enumerate artifact directory") from error

    for name, child_stat in children:
        relative_path = f"{relative_prefix}/{name}" if relative_prefix else name
        _validate_relative_path(relative_path)
        if stat.S_ISLNK(child_stat.st_mode):
            raise ArtifactValidationError(f"symlinked artifact is forbidden: {relative_path}")
        if stat.S_ISDIR(child_stat.st_mode):
            child_fd = _open_directory(name, dir_fd=directory_fd)
            try:
                child_opened = os.fstat(child_fd)
                _require_directory(child_opened, relative_path)
                if _stat_signature(child_opened) != _stat_signature(child_stat):
                    raise ArtifactValidationError(f"artifact directory changed while being closed: {relative_path}")
                directories.append(
                    ArtifactDirectory(path=relative_path, mode=stat.S_IMODE(child_opened.st_mode))
                )
                _close_directory(
                    child_fd,
                    relative_path,
                    child_opened,
                    limits,
                    entries,
                    directories,
                )
            finally:
                os.close(child_fd)
        else:
            entries.append(_read_regular_entry(directory_fd, name, relative_path, child_stat, limits))
            if len(entries) > limits.max_files:
                raise ArtifactValidationError("artifact tree exceeds max_files")


def build_artifact_manifest(
    root: str | Path,
    limits: ArtifactLimits | Mapping[str, object] | None = None,
) -> ArtifactManifest:
    """Build a complete manifest for the real regular files beneath ``root``.

    Symlinks, special files, hard-linked files, and any file exceeding a limit are
    rejected rather than skipped.  The root itself must be a real directory.
    """

    resolved_limits = _coerce_limits(limits)
    root_path = Path(root)
    try:
        root_stat = root_path.lstat()
    except OSError as error:
        raise ArtifactValidationError(f"cannot stat artifact root {root_path}") from error
    _require_directory(root_stat, str(root_path))

    root_fd = _open_directory(root_path)
    entries: list[ArtifactEntry] = []
    directories: list[ArtifactDirectory] = []
    try:
        opened_root = os.fstat(root_fd)
        _require_directory(opened_root, str(root_path))
        if _stat_signature(opened_root) != _stat_signature(root_stat):
            raise ArtifactValidationError("artifact root changed while being opened")
        _close_directory(root_fd, "", opened_root, resolved_limits, entries, directories)
    finally:
        os.close(root_fd)

    entries.sort(key=lambda entry: entry.path)
    directories.sort(key=lambda directory: directory.path)
    total_size = sum(entry.size for entry in entries)
    if total_size > resolved_limits.max_total_bytes:
        raise ArtifactValidationError("artifact tree exceeds max_total_bytes")
    return ArtifactManifest(entries=tuple(entries), directories=tuple(directories), total_size=total_size)


def _coerce_manifest(manifest: ArtifactManifest | Mapping[str, Any]) -> ArtifactManifest:
    if isinstance(manifest, ArtifactManifest):
        return manifest
    if not isinstance(manifest, Mapping):
        raise ArtifactValidationError("artifact manifest must be an object")
    try:
        return ArtifactManifest.model_validate(dict(manifest))
    except ValidationError as error:
        raise ArtifactValidationError("artifact manifest has an invalid schema") from error


def validate_artifact_manifest(
    root: str | Path,
    manifest: ArtifactManifest | Mapping[str, Any],
    limits: ArtifactLimits | Mapping[str, object] | None = None,
) -> ArtifactManifest:
    """Fail closed unless the current regular-file closure exactly matches ``manifest``."""

    expected = _coerce_manifest(manifest)
    actual = build_artifact_manifest(root, limits)
    if actual != expected:
        raise ArtifactValidationError("artifact closure does not match manifest")
    return actual
