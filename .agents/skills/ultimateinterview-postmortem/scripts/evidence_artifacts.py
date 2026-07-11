from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, override

SLUG_LIMIT: Final[int] = 80
HASH_PREFIX_LENGTH: Final[int] = 16
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class EvidenceArtifactError(ValueError):
    detail: str

    @override
    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class EvidenceFile:
    path: Path
    relative_posix: str


def stable_artifact_id(relative_posix: str) -> str:
    if "\\" in relative_posix:
        raise EvidenceArtifactError("artifact path must use POSIX separators")
    path = PurePosixPath(relative_posix)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceArtifactError("artifact path must be canonical and repository-relative")
    canonical = path.as_posix()
    slug = re.sub(r"[^a-z0-9]+", "-", canonical.casefold()).strip("-")
    readable = (slug or "file")[:SLUG_LIMIT].rstrip("-")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:HASH_PREFIX_LENGTH]
    return f"artifact-{readable}-{digest}"


def legacy_artifact_id(relative_posix: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "-" for character in relative_posix.lower()
    )
    return "artifact-" + "-".join(part for part in normalized.split("-") if part)


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _relative_lexical(path: Path, root: Path) -> Path:
    try:
        return _absolute_without_resolving(path).relative_to(root)
    except ValueError as error:
        raise EvidenceArtifactError(
            f"evidence path {path} is outside resolved repository root {root}"
        ) from error


def _reject_symlink_components(path: Path, root: Path) -> Path:
    relative = _relative_lexical(path, root)
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise EvidenceArtifactError(f"evidence path contains symlink component: {current}")
    return relative


def _require_resolved_containment(path: Path, root: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise EvidenceArtifactError(f"evidence path cannot be resolved: {path}: {error}") from error
    try:
        _ = resolved.relative_to(root)
    except ValueError as error:
        raise EvidenceArtifactError(
            f"evidence path {path} resolves outside repository root {root}"
        ) from error
    return resolved


def validate_evidence_directory(path: Path, repo_root: Path) -> Path:
    root = repo_root.resolve(strict=True)
    candidate = _absolute_without_resolving(path)
    _ = _reject_symlink_components(candidate, root)
    resolved = _require_resolved_containment(candidate, root)
    if not resolved.is_dir():
        raise EvidenceArtifactError(f"--evidence-dir {path} is not a directory")
    return resolved


def validate_evidence_file(path: Path, repo_root: Path) -> EvidenceFile:
    root = repo_root.resolve(strict=True)
    candidate = _absolute_without_resolving(path)
    relative = _reject_symlink_components(candidate, root)
    resolved = _require_resolved_containment(candidate, root)
    if not resolved.is_file():
        raise EvidenceArtifactError(f"evidence artifact {path} is not a file")
    return EvidenceFile(path=resolved, relative_posix=relative.as_posix())


def discover_evidence_files(evidence_dir: Path, repo_root: Path) -> tuple[EvidenceFile, ...]:
    root = repo_root.resolve(strict=True)
    directory = validate_evidence_directory(evidence_dir, root)
    discovered: list[EvidenceFile] = []
    for candidate in sorted(directory.rglob("*")):
        _ = _reject_symlink_components(candidate, root)
        resolved = _require_resolved_containment(candidate, root)
        if resolved.is_file():
            discovered.append(validate_evidence_file(candidate, root))
    return tuple(discovered)


def validate_manifest_ids(records: list[JsonValue], repo_root: Path) -> frozenset[str]:
    observed: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise EvidenceArtifactError(f"artifact manifest row {index} is not an object")
        artifact_id = record.get("id")
        relative = record.get("path")
        digest = record.get("sha256")
        if (
            not isinstance(artifact_id, str)
            or not isinstance(relative, str)
            or not isinstance(digest, str)
        ):
            raise EvidenceArtifactError(f"artifact manifest row {index} lacks id/path/sha256")
        evidence = validate_evidence_file(repo_root / relative, repo_root)
        actual_digest = hashlib.sha256(evidence.path.read_bytes()).hexdigest()
        expected_id = stable_artifact_id(evidence.relative_posix)
        if (relative, artifact_id, digest) != (
            evidence.relative_posix,
            expected_id,
            actual_digest,
        ):
            raise EvidenceArtifactError(f"artifact manifest row {index} differs from disk")
        if artifact_id in observed:
            raise EvidenceArtifactError(f"artifact manifest duplicates {artifact_id!r}")
        observed.add(artifact_id)
    return frozenset(observed)
