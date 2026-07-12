"""Canonical digesting and fenced, atomic persistence for benchmark runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar
from unicodedata import normalize

from pydantic import BaseModel, ValidationError

from .models import CellRecord, CellStatus, RunManifest, RunState, RunStatus, TERMINAL_CELL_STATUSES

try:  # The supported controller host is POSIX; import lazily for importability elsewhere.
    import fcntl
except ImportError:  # pragma: no cover - unsupported host protection
    fcntl = None  # type: ignore[assignment]

ModelT = TypeVar("ModelT", bound=BaseModel)


class StateError(RuntimeError):
    """Raised when a persisted artifact violates a controller invariant."""


def _normalized_json(value: Any) -> Any:
    """Return a JSON value with recursively NFC-normalized strings and keys."""

    if isinstance(value, BaseModel):
        return _normalized_json(value.model_dump(mode="json", by_alias=True, exclude_none=False))
    if isinstance(value, Enum):
        return _normalized_json(value.value)
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StateError("canonical JSON does not permit non-finite floats")
        return value
    if isinstance(value, str):
        return normalize("NFC", value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StateError("canonical JSON object keys must be strings")
            normalized_key = normalize("NFC", key)
            if normalized_key in normalized:
                raise StateError("canonical JSON has duplicate normalized object keys")
            normalized[normalized_key] = _normalized_json(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        return [_normalized_json(item) for item in value]
    raise StateError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Encode canonical, compact, sorted UTF-8 JSON followed by one newline."""

    normalized = _normalized_json(value)
    return (
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def canonical_digest(value: Any) -> str:
    """SHA-256 digest of the exact canonical JSON bytes written to artifacts."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StateError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def read_canonical_json(path: Path) -> Any:
    """Read and verify a canonical JSON artifact rather than accepting a loose JSON lookalike."""

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise StateError(f"cannot read artifact {path}: {error}") from error
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_object_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, StateError) as error:
        raise StateError(f"invalid JSON artifact {path}: {error}") from error
    if canonical_bytes(value) != raw:
        raise StateError(f"artifact is not canonical JSON: {path}")
    return value


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Durably publish bytes with fsync followed by atomic replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, value: Any) -> str:
    payload = canonical_bytes(value)
    atomic_write_bytes(path, payload)
    return digest_bytes(payload)


def atomic_write_model(path: Path, model: BaseModel) -> str:
    return atomic_write_json(path, model)


def load_model(path: Path, model_type: type[ModelT]) -> ModelT:
    try:
        return model_type.model_validate(read_canonical_json(path))
    except ValidationError as error:
        raise StateError(f"artifact schema validation failed for {path}: {error}") from error


def _rebuild_state(state: RunState, **changes: Any) -> RunState:
    document = state.model_dump(mode="json", by_alias=True, exclude_none=False)
    document.update(changes)
    return RunState.model_validate(document)


def _rebuild_cell(cell: CellRecord, **changes: Any) -> CellRecord:
    document = cell.model_dump(mode="json", by_alias=True, exclude_none=False)
    document.update(changes)
    return CellRecord.model_validate(document)


class StateStore:
    """Owns public run artifacts and serializes fenced state transitions."""

    manifest_name = "run-manifest.json"
    state_name = "state.json"
    status_name = "evaluation-status.json"
    scorecard_name = "scorecard.json"

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.cells_dir = run_dir / "cells"
        self.manifest_path = run_dir / self.manifest_name
        self.state_path = run_dir / self.state_name
        self.lock_path = run_dir / ".state.lock"

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Use an advisory OS lock so stale processes cannot overwrite a newer fence."""

        if fcntl is None:
            raise StateError("fenced state requires POSIX advisory file locks")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def has_state(self) -> bool:
        return self.state_path.is_file() or self.manifest_path.is_file()

    def initialize(self, manifest: RunManifest, state: RunState) -> None:
        with self.locked():
            if self.manifest_path.exists() or self.state_path.exists():
                raise StateError("run artifacts already exist")
            if manifest.run_id != state.run_id:
                raise StateError("manifest and state run IDs differ")
            if (
                manifest.config_digest != state.config_digest
                or manifest.corpus_digest != state.corpus_digest
                or manifest.arm_digests != state.arm_digests
            ):
                raise StateError("manifest and state input bindings differ")
            atomic_write_model(self.manifest_path, manifest)
            atomic_write_model(self.state_path, state)

    def load_manifest(self) -> RunManifest:
        return load_model(self.manifest_path, RunManifest)

    def load_state(self) -> RunState:
        return load_model(self.state_path, RunState)

    def save_manifest(self, manifest: RunManifest) -> None:
        with self.locked():
            atomic_write_model(self.manifest_path, manifest)

    def save_state(self, state: RunState) -> None:
        with self.locked():
            atomic_write_model(self.state_path, state)

    def write_cell_input(self, cell_id: str, value: Any, expected_digest: str) -> None:
        cell_path = self._cell_path(cell_id)
        input_path = cell_path / "input.json"
        payload_digest = canonical_digest(value)
        if payload_digest != expected_digest:
            raise StateError(f"cell input digest mismatch for {cell_id}")
        if input_path.exists():
            existing = read_canonical_json(input_path)
            if canonical_digest(existing) != expected_digest:
                raise StateError(f"immutable cell input drift for {cell_id}")
            return
        atomic_write_json(input_path, value)

    def write_cell_artifact(self, cell_id: str, filename: str, value: Any) -> str:
        if filename.startswith(".") or "/" in filename or "\\" in filename:
            raise StateError("invalid cell artifact filename")
        return atomic_write_json(self._cell_path(cell_id) / filename, value)

    def recover_leases(self) -> int:
        """Return abandoned leases to pending without changing their monotonically increasing fence."""

        with self.locked():
            state = self.load_state()
            recovered = 0
            cells: list[CellRecord] = []
            for cell in state.cells:
                if cell.status is CellStatus.LEASED:
                    cells.append(_rebuild_cell(cell, status=CellStatus.PENDING))
                    recovered += 1
                else:
                    cells.append(cell)
            if recovered:
                atomic_write_model(self.state_path, _rebuild_state(state, cells=tuple(cells)))
            return recovered

    def lease_cell(self, cell_id: str, max_attempts: int) -> CellRecord:
        with self.locked():
            state = self.load_state()
            current = self._require_cell(state, cell_id)
            if current.status in TERMINAL_CELL_STATUSES:
                return current
            if current.status is not CellStatus.PENDING:
                raise StateError(f"cell {cell_id} is not ready to lease")
            if current.attempt >= max_attempts:
                raise StateError(f"cell {cell_id} exceeded maximum attempts")
            leased = _rebuild_cell(
                current,
                status=CellStatus.LEASED,
                attempt=current.attempt + 1,
                fence=current.fence + 1,
            )
            cells = tuple(leased if cell.cell_id == cell_id else cell for cell in state.cells)
            atomic_write_model(self.state_path, _rebuild_state(state, cells=cells))
            return leased

    def commit_terminal_cell(
        self,
        cell_id: str,
        fence: int,
        status: CellStatus,
        attempt_receipt_digest: str,
        terminal_receipt_digest: str,
    ) -> CellRecord:
        """Commit only the current lease fence; an older worker cannot supersede it."""

        if status not in TERMINAL_CELL_STATUSES:
            raise StateError("terminal commit requires a terminal cell status")
        with self.locked():
            state = self.load_state()
            current = self._require_cell(state, cell_id)
            if current.status in TERMINAL_CELL_STATUSES:
                return current
            if current.status is not CellStatus.LEASED or current.fence != fence:
                raise StateError(f"stale or invalid fence for cell {cell_id}")
            completed = _rebuild_cell(
                current,
                status=status,
                attempt_receipt_digest=attempt_receipt_digest,
                terminal_receipt_digest=terminal_receipt_digest,
            )
            cells = tuple(completed if cell.cell_id == cell_id else cell for cell in state.cells)
            atomic_write_model(self.state_path, _rebuild_state(state, cells=cells))
            return completed

    def set_run_status(self, status: RunStatus) -> RunState:
        with self.locked():
            state = self.load_state()
            updated = _rebuild_state(state, status=status)
            atomic_write_model(self.state_path, updated)
            return updated

    def _cell_path(self, cell_id: str) -> Path:
        if not cell_id.startswith("cell-") or "/" in cell_id or "\\" in cell_id:
            raise StateError("invalid cell identifier")
        return self.cells_dir / cell_id

    @staticmethod
    def _require_cell(state: RunState, cell_id: str) -> CellRecord:
        for cell in state.cells:
            if cell.cell_id == cell_id:
                return cell
        raise StateError(f"unknown cell: {cell_id}")
