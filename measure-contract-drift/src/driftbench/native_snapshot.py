"""Validation for a self-contained, frozen Ultimateinterview native snapshot.

The validator never follows symlinks and checks the copied source bytes before a
native command is allowed to run. It intentionally validates source closure only;
it does not invoke native code or make an assurance claim.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from stat import S_ISDIR, S_ISREG
from typing import Any


MANIFEST_FILENAME = "protocol-source-manifest.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
DIRECT_CLOSURE_ROLE = "direct-local-import-closure"
ROOT_ROLES = frozenset({"native-entrypoint", "native-runtime"})
TREE_DIGEST_ALGORITHM = "SHA-256 over UTF-8 lines '<source_path>\\t<sha256>\\n' sorted by source_path"


class NativeSnapshotValidationError(ValueError):
    """The frozen snapshot is missing, substituted, or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class NativeSourceRecord:
    """One immutable source-byte binding in the native closure."""

    role: str
    source_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class NativeSnapshotValidation:
    """Identity of a successfully validated frozen native snapshot."""

    snapshot_id: str
    source_tree_digest: str
    record_count: int


def _require_text(value: Any, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise NativeSnapshotValidationError(f"{field_name} must be nonblank trimmed text")
    return value


def _relative_path(value: Any, field_name: str) -> PurePosixPath:
    text = _require_text(value, field_name)
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise NativeSnapshotValidationError(f"{field_name} must be a canonical relative path")
    return path


def _no_symlink_path(root: Path, relative: PurePosixPath, *, directory: bool) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            status = current.lstat()
        except OSError as error:
            raise NativeSnapshotValidationError(f"required frozen path is absent: {relative.as_posix()}") from error
        if current.is_symlink():
            raise NativeSnapshotValidationError(f"frozen path must not be a symlink: {relative.as_posix()}")
    if directory:
        if not S_ISDIR(status.st_mode):
            raise NativeSnapshotValidationError(f"frozen path must be a directory: {relative.as_posix()}")
    elif not S_ISREG(status.st_mode):
        raise NativeSnapshotValidationError(f"frozen path must be a regular file: {relative.as_posix()}")
    return current


def _read_regular(root: Path, relative: PurePosixPath) -> bytes:
    return _no_symlink_path(root, relative, directory=False).read_bytes()


def _manifest_document(snapshot_root: Path) -> dict[str, Any]:
    manifest_path = _no_symlink_path(snapshot_root, PurePosixPath(MANIFEST_FILENAME), directory=False)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeSnapshotValidationError("native snapshot manifest is not valid UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise NativeSnapshotValidationError("native snapshot manifest must be a JSON object")
    return document


def _records(document: dict[str, Any]) -> tuple[NativeSourceRecord, ...]:
    raw_records = document.get("native_source_records")
    if not isinstance(raw_records, list) or not raw_records:
        raise NativeSnapshotValidationError("native_source_records must be a nonempty array")
    records: list[NativeSourceRecord] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict) or set(raw_record) != {"role", "sha256", "source_path"}:
            raise NativeSnapshotValidationError(f"native source record {index} has an invalid shape")
        source_path = _relative_path(raw_record["source_path"], f"native source record {index} path")
        digest = _require_text(raw_record["sha256"], f"native source record {index} digest")
        if not SHA256_RE.fullmatch(digest):
            raise NativeSnapshotValidationError(f"native source record {index} has an invalid SHA-256 digest")
        records.append(
            NativeSourceRecord(
                role=_require_text(raw_record["role"], f"native source record {index} role"),
                source_path=source_path.as_posix(),
                sha256=digest,
            )
        )
    paths = tuple(record.source_path for record in records)
    if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
        raise NativeSnapshotValidationError("native source records must have sorted, unique source paths")
    return tuple(records)


def _tree_digest(records: tuple[NativeSourceRecord, ...]) -> str:
    payload = "".join(f"{record.source_path}\t{record.sha256}\n" for record in records).encode("utf-8")
    return sha256(payload).hexdigest()


def _script_modules(records: tuple[NativeSourceRecord, ...]) -> tuple[dict[str, NativeSourceRecord], str]:
    package_records = [
        record
        for record in records
        if record.source_path.endswith("/scripts/__init__.py")
    ]
    if len(package_records) != 1:
        raise NativeSnapshotValidationError("native closure must contain exactly one scripts package initializer")
    package_prefix = str(PurePosixPath(package_records[0].source_path).parent)
    modules: dict[str, NativeSourceRecord] = {"scripts": package_records[0]}
    for record in records:
        path = PurePosixPath(record.source_path)
        if str(path.parent) != package_prefix or path.suffix != ".py" or path.name == "__init__.py":
            continue
        modules[f"scripts.{path.stem}"] = record
    return modules, package_prefix


def _relative_import_base(current_module: str, level: int, module: str | None) -> str:
    package = current_module if current_module == "scripts" else current_module.rpartition(".")[0]
    parts = package.split(".")
    if level > len(parts):
        raise NativeSnapshotValidationError(f"relative import escapes scripts package in {current_module}")
    base_parts = parts[: len(parts) - level + 1]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def _imported_modules(module: str, payload: bytes, known_modules: dict[str, NativeSourceRecord]) -> set[str]:
    try:
        tree = ast.parse(payload, filename=module)
    except SyntaxError as error:
        raise NativeSnapshotValidationError(f"native source cannot be parsed: {module}") from error

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "scripts" or alias.name.startswith("scripts."):
                    if alias.name not in known_modules:
                        raise NativeSnapshotValidationError(f"native import is absent from closure: {alias.name}")
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _relative_import_base(module, node.level, node.module)
                if node.level
                else node.module
            )
            if base is None or (base != "scripts" and not base.startswith("scripts.")):
                continue
            if base not in known_modules:
                raise NativeSnapshotValidationError(f"native import is absent from closure: {base}")
            imported.add(base)
            if base == "scripts":
                for alias in node.names:
                    if alias.name == "*":
                        raise NativeSnapshotValidationError("native scripts package cannot use wildcard imports")
                    child = f"scripts.{alias.name}"
                    if child not in known_modules:
                        raise NativeSnapshotValidationError(f"native import is absent from closure: {child}")
                    imported.add(child)
    return imported


def _validate_direct_import_closure(
    frozen_root: Path,
    records: tuple[NativeSourceRecord, ...],
) -> None:
    modules, _ = _script_modules(records)
    roots = {
        module
        for module, record in modules.items()
        if record.role in ROOT_ROLES
    }
    if not roots:
        raise NativeSnapshotValidationError("native closure has no executable roots")
    expected_direct = {
        module
        for module, record in modules.items()
        if record.role == DIRECT_CLOSURE_ROLE
    }
    if not expected_direct:
        raise NativeSnapshotValidationError("native closure has no direct import records")

    discovered = set(roots)
    pending = list(sorted(roots))
    while pending:
        module = pending.pop()
        record = modules[module]
        payload = _read_regular(frozen_root, PurePosixPath(record.source_path))
        for imported in sorted(_imported_modules(module, payload, modules)):
            if imported not in discovered:
                discovered.add(imported)
                pending.append(imported)

    actual_direct = discovered - roots
    if actual_direct != expected_direct:
        missing = sorted(expected_direct - actual_direct)
        extra = sorted(actual_direct - expected_direct)
        raise NativeSnapshotValidationError(
            f"direct local import closure mismatch; missing={missing!r}, extra={extra!r}"
        )


def _is_interpreter_cache(path: PurePosixPath) -> bool:
    return path.suffix == ".pyc" and "__pycache__" in path.parts


def _validate_frozen_tree(frozen_root: Path, records: tuple[NativeSourceRecord, ...]) -> None:
    expected = {record.source_path for record in records}
    actual: set[str] = set()
    for path in frozen_root.rglob("*"):
        relative = PurePosixPath(path.relative_to(frozen_root).as_posix())
        try:
            status = path.lstat()
        except OSError as error:
            raise NativeSnapshotValidationError(f"cannot inspect frozen path: {relative.as_posix()}") from error
        if path.is_symlink():
            raise NativeSnapshotValidationError(f"frozen tree must not contain symlinks: {relative.as_posix()}")
        if S_ISDIR(status.st_mode):
            continue
        if not S_ISREG(status.st_mode):
            raise NativeSnapshotValidationError(f"frozen tree has a non-regular entry: {relative.as_posix()}")
        if _is_interpreter_cache(relative):
            continue
        actual.add(relative.as_posix())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise NativeSnapshotValidationError(f"frozen source tree mismatch; missing={missing!r}, extra={extra!r}")


def validate_native_snapshot(snapshot: str | Path) -> NativeSnapshotValidation:
    """Fail closed unless the vendored native closure is immutable and complete.

    ``snapshot`` is the directory containing the manifest and ``frozen`` copy.
    Validation performs no native invocation; callers must run it before using a
    fixture command from that copy.
    """
    snapshot_root = Path(snapshot)
    try:
        status = snapshot_root.lstat()
    except OSError as error:
        raise NativeSnapshotValidationError("native snapshot directory is absent") from error
    if snapshot_root.is_symlink() or not S_ISDIR(status.st_mode):
        raise NativeSnapshotValidationError("native snapshot root must be a real directory")

    document = _manifest_document(snapshot_root)
    if document.get("format") != "ultimateinterview-protocol-source-manifest" or document.get("format_version") != 1:
        raise NativeSnapshotValidationError("unsupported native snapshot manifest format")
    if document.get("source_root") != ".":
        raise NativeSnapshotValidationError("native snapshot source_root must remain '.'")
    snapshot_id = _require_text(document.get("snapshot_id"), "snapshot_id")
    frozen_relative = _relative_path(document.get("frozen_source_root"), "frozen_source_root")
    if frozen_relative.as_posix() != "frozen":
        raise NativeSnapshotValidationError("frozen_source_root must be 'frozen'")
    frozen_root = _no_symlink_path(snapshot_root, frozen_relative, directory=True)
    records = _records(document)

    source_tree = document.get("source_tree")
    if not isinstance(source_tree, dict):
        raise NativeSnapshotValidationError("native snapshot source_tree is absent")
    if source_tree.get("algorithm") != TREE_DIGEST_ALGORITHM:
        raise NativeSnapshotValidationError("native snapshot source tree algorithm is unsupported")
    if source_tree.get("record_count") != len(records):
        raise NativeSnapshotValidationError("native snapshot record count does not match records")
    expected_tree_digest = _tree_digest(records)
    if source_tree.get("sha256") != expected_tree_digest:
        raise NativeSnapshotValidationError("native snapshot source tree digest does not match records")

    _validate_frozen_tree(frozen_root, records)
    for record in records:
        payload = _read_regular(frozen_root, PurePosixPath(record.source_path))
        if sha256(payload).hexdigest() != record.sha256:
            raise NativeSnapshotValidationError(f"frozen source digest mismatch: {record.source_path}")
    _validate_direct_import_closure(frozen_root, records)

    return NativeSnapshotValidation(
        snapshot_id=snapshot_id,
        source_tree_digest=expected_tree_digest,
        record_count=len(records),
    )


__all__ = [
    "NativeSnapshotValidation",
    "NativeSnapshotValidationError",
    "NativeSourceRecord",
    "validate_native_snapshot",
]
