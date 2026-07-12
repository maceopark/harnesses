#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from scripts import atomic_write, build_contract, build_contract_schema, protocol_state

MANIFEST_NAME: Final[str] = "session-manifest.json"
MANIFEST_SCHEMA_VERSION: Final[int] = 1
POLICY_VERSION: Final[str] = "v2-source-snapshot"
REQUIRED_MEMBERS: Final[tuple[str, ...]] = (
    "ledger.json",
    "protocol.json",
    "questions.json",
    "transcript.md",
    "decisions.jsonl",
    "handoff.md",
    "build-contract.json",
)
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class SessionManifestError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class ManifestMember(StrictModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: StrictInt = Field(ge=0)


class SessionManifest(StrictModel):
    manifest_schema_version: StrictInt
    policy_version: str
    material_revision: StrictInt = Field(ge=0)
    schema_versions: dict[str, StrictInt]
    sealed_at_ns: StrictInt = Field(ge=0)
    members: tuple[ManifestMember, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def is_canonical_v2_snapshot(self) -> SessionManifest:
        if self.manifest_schema_version != MANIFEST_SCHEMA_VERSION:
            raise SessionManifestError("unknown session manifest schema version")
        if self.policy_version != POLICY_VERSION:
            raise SessionManifestError("unknown session manifest policy version")
        if self.schema_versions != {"evidence": 2, "contract": 2}:
            raise SessionManifestError("manifest requires schema v2 evidence and contract versions")
        if tuple(member.path for member in self.members) != REQUIRED_MEMBERS:
            raise SessionManifestError("manifest member paths must exactly match the v2 source set")
        return self


@dataclass(frozen=True, slots=True)
class ManifestStatus:
    snapshot_complete: bool
    manifest_digest: str | None
    reason: str | None


def _canonical_bytes(payload: JsonValue) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(payload: JsonValue) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _manifest_body(manifest: SessionManifest) -> JsonObject:
    return cast(
        JsonObject,
        manifest.model_dump(mode="json", exclude={"manifest_digest"}),
    )


def canonical_json(manifest: SessionManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _session_root(session_dir: Path) -> Path:
    if not session_dir.is_dir() or session_dir.is_symlink():
        raise SessionManifestError(f"session directory is not a regular directory: {session_dir}")
    return session_dir.resolve()


def _required_file(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink():
        raise SessionManifestError(f"required member is a symlink: {name}")
    if not path.exists():
        raise SessionManifestError(f"required member is missing: {name}")
    if not path.is_file():
        raise SessionManifestError(f"required member is not a regular file: {name}")
    return path


def _source_state(root: Path) -> protocol_state.ProtocolState:
    protocol_path = _required_file(root, "protocol.json")
    try:
        state = protocol_state.parse_state(protocol_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SessionManifestError(f"invalid protocol.json: {error}") from error
    if (state.evidence_schema_version, state.contract_schema_version) != (2, 2):
        raise SessionManifestError("session manifests require evidence_schema_version=2 and contract_schema_version=2")
    return state


def _validated_sidecar(root: Path) -> build_contract_schema.BuildContract:
    handoff = _required_file(root, "handoff.md").read_text(encoding="utf-8")
    sidecar_path = _required_file(root, "build-contract.json")
    try:
        contract = build_contract_schema.BuildContract.model_validate_json(
            sidecar_path.read_text(encoding="utf-8"),
        )
    except (ValidationError, ValueError) as error:
        raise SessionManifestError(f"invalid build-contract.json: {error}") from error
    if not build_contract.is_current(contract, handoff):
        raise SessionManifestError("build-contract.json is stale for handoff.md")
    return contract


def _member(path: Path, name: str) -> ManifestMember:
    content = path.read_bytes()
    return ManifestMember(
        path=name,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
    )


def _manifest_from_source(root: Path) -> SessionManifest:
    state = _source_state(root)
    _ = _validated_sidecar(root)
    members = tuple(_member(_required_file(root, name), name) for name in REQUIRED_MEMBERS)
    body: JsonObject = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "material_revision": state.material_revision,
        "schema_versions": {"evidence": 2, "contract": 2},
        "sealed_at_ns": time.time_ns(),
        "members": [member.model_dump(mode="json") for member in members],
    }
    return SessionManifest(
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        material_revision=state.material_revision,
        schema_versions={"evidence": 2, "contract": 2},
        sealed_at_ns=cast(int, body["sealed_at_ns"]),
        members=members,
        manifest_digest=_digest(body),
    )


def _load_manifest(root: Path) -> SessionManifest:
    path = root / MANIFEST_NAME
    if path.is_symlink():
        raise SessionManifestError("session manifest must not be a symlink")
    if not path.exists():
        raise SessionManifestError("session manifest is missing")
    if not path.is_file():
        raise SessionManifestError("session manifest is not a regular file")
    try:
        manifest = SessionManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as error:
        raise SessionManifestError(f"invalid session manifest: {error}") from error
    if manifest.manifest_digest != _digest(_manifest_body(manifest)):
        raise SessionManifestError("session manifest digest does not match its canonical body")
    return manifest


def _validate_manifest(root: Path, manifest: SessionManifest) -> None:
    state = _source_state(root)
    if manifest.material_revision != state.material_revision:
        raise SessionManifestError("session manifest is stale for material_revision")
    for member in manifest.members:
        path = _required_file(root, member.path)
        current = _member(path, member.path)
        if current != member:
            raise SessionManifestError(f"session manifest is stale for {member.path}")
    _ = _validated_sidecar(root)
    sidecar_mtime = (root / "build-contract.json").stat().st_mtime_ns
    if sidecar_mtime > manifest.sealed_at_ns:
        raise SessionManifestError("build-contract.json was compiled after the session manifest was sealed")


def seal_session(session_dir: Path) -> SessionManifest:
    root = _session_root(session_dir)
    with atomic_write.session_transaction(root):
        manifest = _manifest_from_source(root)
        atomic_write.commit_text_files(
            {root / MANIFEST_NAME: canonical_json(manifest)},
            locked=True,
        )
    return manifest


def _manifest_status_locked(root: Path) -> ManifestStatus:
    manifest = _load_manifest(root)
    try:
        _validate_manifest(root, manifest)
    except SessionManifestError as error:
        return ManifestStatus(False, manifest.manifest_digest, str(error))
    return ManifestStatus(True, manifest.manifest_digest, None)


def manifest_status(session_dir: Path) -> ManifestStatus:
    try:
        root = _session_root(session_dir)
        with atomic_write.session_read_transaction(root):
            return _manifest_status_locked(root)
    except (SessionManifestError, atomic_write.SessionLockError) as error:
        return ManifestStatus(False, None, str(error))
