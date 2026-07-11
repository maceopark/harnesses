from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Annotated, ClassVar, Final, Literal, Self, override

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator, model_validator

from scripts import assurance_schema

CORPUS_MANIFEST: Final[str] = "corpus-manifest.json"
INPUT_NAME: Final[str] = "input.json"
EXPECTED_NAME: Final[str] = "expected.json"
ZERO_DIGEST: Final[str] = "0" * 64
type Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
type NonBlank = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class ForwardHarnessError(ValueError):
    detail: str

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    @override
    def __str__(self) -> str:
        return self.detail


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid", strict=True)


class ForwardInput(StrictModel):
    schema_version: Literal[1]
    session_id: NonBlank
    ledger_path: NonBlank
    protocol_path: NonBlank
    handoff_path: NonBlank
    sidecar_path: NonBlank
    manifest_path: NonBlank
    receipt_paths: tuple[NonBlank, ...] = ()
    mutation_phase: Literal["before-seal", "after-seal"] = "before-seal"

    @field_validator("receipt_paths")
    @classmethod
    def receipt_paths_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ForwardHarnessError("forward fixture receipt paths must be unique")
        return value


class ForwardVerdicts(StrictModel):
    abi: assurance_schema.AbiVerdict
    trace: assurance_schema.TraceVerdict
    property: assurance_schema.PropertyVerdict
    adequacy: assurance_schema.AdequacyVerdict
    stakeholder: assurance_schema.StakeholderVerdict


class ForwardGate(StrictModel):
    implementation_ready: bool
    failures: tuple[NonBlank, ...]

    @model_validator(mode="after")
    def readiness_matches_failures(self) -> Self:
        if self.implementation_ready != (not self.failures):
            raise ForwardHarnessError("forward gate readiness must match its failure list")
        return self


class ForwardResult(StrictModel):
    corpus_digest: Digest
    verdicts: ForwardVerdicts
    gate: ForwardGate


class CorpusManifest(StrictModel):
    corpus_version: Literal["v2"]
    members: dict[str, Digest]
    corpus_digest: Digest

    @field_validator("members")
    @classmethod
    def members_are_sorted_normalized_paths(cls, value: dict[str, str]) -> dict[str, str]:
        if tuple(value) != tuple(sorted(value)):
            raise ForwardHarnessError("corpus members must be sorted")
        for member in value:
            path = PurePosixPath(member)
            if path.is_absolute() or path.as_posix() != member or ".." in path.parts:
                raise ForwardHarnessError("corpus member path must be normalized and relative")
        return value

    @model_validator(mode="after")
    def digest_matches_members(self) -> Self:
        if self.corpus_digest != _digest(_manifest_preimage(self.corpus_version, self.members)):
            raise ForwardHarnessError("corpus digest does not match canonical member manifest")
        return self


class CorpusVersionProbe(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore", strict=True)
    corpus_version: Literal["v2"]


def _canonical_bytes(payload: Mapping[str, JsonValue]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(payload: Mapping[str, JsonValue]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _manifest_preimage(version: str, members: Mapping[str, str]) -> dict[str, JsonValue]:
    return {"corpus_version": version, "members": dict(members)}


def _result_preimage(result: ForwardResult) -> dict[str, JsonValue]:
    return result.model_dump(mode="json", exclude={"corpus_digest"})


def _file_digest(path: Path, relative: str) -> str:
    if relative.endswith(f"/{EXPECTED_NAME}"):
        try:
            result = ForwardResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as error:
            raise ForwardHarnessError(f"invalid reviewed expected result: {relative}") from error
        return _digest(_result_preimage(result))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corpus_files(root: Path) -> tuple[Path, ...]:
    manifest_path = root / CORPUS_MANIFEST
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ForwardHarnessError("corpus must not contain symbolic links")
        if path.is_file() and path.stat().st_nlink != 1:
            raise ForwardHarnessError("corpus files must not have external hard links")
        if path.is_file() and path != manifest_path:
            if path.name == CORPUS_MANIFEST:
                raise ForwardHarnessError("corpus manifest is valid only at the corpus root")
            files.append(path)
    return tuple(sorted(files))


def _member_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _file_digest(path, path.relative_to(root).as_posix())
        for path in _corpus_files(root)
    }


def _corpus_root(fixture: Path) -> Path:
    if fixture.is_symlink() or not fixture.is_dir():
        raise ForwardHarnessError(f"fixture is not a regular directory: {fixture}")
    root = fixture.parent
    manifest = root / CORPUS_MANIFEST
    if root.is_symlink() or not root.is_dir():
        raise ForwardHarnessError("corpus root is not a regular directory")
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_nlink != 1:
        raise ForwardHarnessError("fixture parent does not contain a corpus manifest")
    return root


def _manifest(root: Path) -> CorpusManifest:
    try:
        manifest = CorpusManifest.model_validate_json((root / CORPUS_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise ForwardHarnessError("invalid corpus manifest") from error
    actual = _member_digests(root)
    if tuple(actual) != tuple(manifest.members):
        raise ForwardHarnessError("corpus member set does not match reviewed manifest")
    if any(actual[path] != digest for path, digest in manifest.members.items()):
        raise ForwardHarnessError("corpus member digest does not match reviewed manifest")
    return manifest


def _fixture_input(fixture: Path) -> ForwardInput:
    try:
        return ForwardInput.model_validate_json((fixture / INPUT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise ForwardHarnessError(f"invalid forward fixture input: {fixture.name}") from error


corpus_files = _corpus_files
corpus_root = _corpus_root
digest = _digest
fixture_input = _fixture_input
manifest = _manifest
manifest_preimage = _manifest_preimage
