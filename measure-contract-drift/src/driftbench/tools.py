"""Fail-closed validation for the benchmark's simulated tool requests.

The validator only checks requests; it neither opens a requested path nor executes a
command.  Executors must use direct ``argv`` execution and the resolved role roots
returned by their own filesystem layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path, PurePosixPath
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator, model_validator


class ToolRequestError(ValueError):
    """Raised when a tool request violates the portable sandbox contract."""


class ToolRole(StrEnum):
    """Roles with explicit, least-privilege tool capabilities."""

    PLANNER = "planner"
    IMPLEMENTER = "implementer"
    POSTMORTEM = "postmortem"


ROLE_TOOL_ALLOWLIST: dict[ToolRole, frozenset[str]] = {
    ToolRole.PLANNER: frozenset({"read", "search", "task"}),
    ToolRole.IMPLEMENTER: frozenset({"read", "search", "write_patch", "run"}),
    ToolRole.POSTMORTEM: frozenset({"read", "search"}),
}
"""The complete role-to-tool capability matrix."""

_FORBIDDEN_REQUEST_FIELDS = frozenset(
    {
        "command",
        "env",
        "environment",
        "executable",
        "shell",
        "stdin",
    }
)
_SHELL_META_CHARACTERS = frozenset("\\`$;&|<>(){}[]*?!'\"~=\r\n\t")
_SAFE_EXECUTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SAFE_ARGUMENT = re.compile(r"^[A-Za-z0-9_./:+,=@%-]+$")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_EXECUTABLES = frozenset({"bash", "cmd", "command", "dash", "env", "fish", "sh", "zsh"})

NonEmptyText: TypeAlias = Annotated[StrictStr, Field(min_length=1)]
SafeRelativePath: TypeAlias = Annotated[StrictStr, Field(min_length=1)]


def _validate_relative_path(value: str, *, allow_root: bool = False) -> str:
    """Accept only a portable, root-relative path with no shell syntax."""

    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("path must be a non-NUL string")
    if any(character in _SHELL_META_CHARACTERS for character in value):
        raise ValueError("path contains shell metacharacters")
    if "\\" in value:
        raise ValueError("path must use POSIX separators")

    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("path must be relative to the role root")
    if value in {"", "."}:
        if allow_root:
            return "."
        raise ValueError("path must name a file or directory below the role root")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path traversal is forbidden")
    if any(part.startswith("-") for part in path.parts):
        raise ValueError("path components must not be option-like")
    return path.as_posix()


def _validate_run_argument(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("run arguments must be non-empty strings")
    if any(character in _SHELL_META_CHARACTERS for character in value):
        raise ValueError("run arguments must not contain shell metacharacters")
    if not _SAFE_ARGUMENT.fullmatch(value):
        raise ValueError("run arguments contain unsupported characters")
    if value.startswith("/") or ".." in PurePosixPath(value).parts:
        raise ValueError("run arguments must not contain absolute or traversal paths")
    if _ENV_ASSIGNMENT.match(value):
        raise ValueError("environment overrides are forbidden")
    return value


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadRequest(_StrictRequest):
    tool: Literal["read"]
    path: SafeRelativePath

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class SearchRequest(_StrictRequest):
    tool: Literal["search"]
    pattern: NonEmptyText
    path: SafeRelativePath | None = None
    paths: tuple[SafeRelativePath, ...] | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else _validate_relative_path(value)

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None or not value:
            return value
        return tuple(_validate_relative_path(item) for item in value)

    @model_validator(mode="after")
    def require_exactly_one_path_form(self) -> SearchRequest:
        if (self.path is None) == (self.paths is None):
            raise ValueError("search requires exactly one of path or paths")
        if self.paths is not None and not self.paths:
            raise ValueError("search paths must not be empty")
        return self


class WritePatchRequest(_StrictRequest):
    tool: Literal["write_patch"]
    path: SafeRelativePath
    patch: NonEmptyText

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class RunRequest(_StrictRequest):
    tool: Literal["run"]
    argv: tuple[NonEmptyText, ...] = Field(min_length=1)
    cwd: SafeRelativePath = "."

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, value: str) -> str:
        return _validate_relative_path(value, allow_root=True)

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("run requires at least one argv element")
        executable = value[0]
        if _ENV_ASSIGNMENT.match(executable):
            raise ValueError("environment overrides are forbidden")
        if not _SAFE_EXECUTABLE.fullmatch(executable):
            raise ValueError("run executable must be a bare executable name")
        if executable in _SHELL_EXECUTABLES:
            raise ValueError("shell execution is forbidden")
        return tuple(_validate_run_argument(argument) for argument in value)


class TaskRequest(_StrictRequest):
    tool: Literal["task"]
    task: NonEmptyText
    path: SafeRelativePath | None = None
    paths: tuple[SafeRelativePath, ...] = ()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else _validate_relative_path(value)

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_validate_relative_path(item) for item in value)


ToolRequest: TypeAlias = ReadRequest | SearchRequest | WritePatchRequest | RunRequest | TaskRequest
RoleRoots: TypeAlias = Mapping[str | ToolRole, Path | str | Sequence[Path | str]]


def request_paths(request: ToolRequest) -> tuple[str, ...]:
    """Return every path field in a validated request in declaration order."""

    match request:
        case ReadRequest(path=path) | WritePatchRequest(path=path):
            return (path,)
        case SearchRequest(path=path, paths=paths):
            return (path,) if path is not None else paths or ()
        case RunRequest(cwd=cwd):
            return (cwd,)
        case TaskRequest(path=path, paths=paths):
            return ((path,) if path is not None else ()) + paths
    raise ToolRequestError("unsupported validated request")


def _role_roots(role: ToolRole, roots: RoleRoots) -> tuple[Path, ...]:
    if not isinstance(roots, Mapping):
        raise ToolRequestError("roots must map each role to one or more absolute directories")
    raw_roots = roots.get(role)
    if raw_roots is None:
        raw_roots = roots.get(role.value)
    if raw_roots is None:
        raise ToolRequestError(f"no root configured for role {role.value}")

    if isinstance(raw_roots, (str, Path)):
        candidates = (raw_roots,)
    elif isinstance(raw_roots, Sequence):
        candidates = tuple(raw_roots)
    else:
        raise ToolRequestError(f"roots for role {role.value} must be a path or path sequence")
    if not candidates:
        raise ToolRequestError(f"role {role.value} has no configured roots")

    normalized: list[Path] = []
    for candidate in candidates:
        if not isinstance(candidate, (str, Path)):
            raise ToolRequestError("configured roots must be paths")
        path = Path(candidate)
        if not path.is_absolute():
            raise ToolRequestError("configured roots must be absolute")
        try:
            if path.is_symlink() or not path.is_dir():
                raise ToolRequestError(f"configured root is not a real directory: {path}")
            normalized.append(path.resolve(strict=False))
        except OSError as error:
            raise ToolRequestError(f"cannot validate configured root {path}") from error
    return tuple(normalized)


def _assert_within_any_root(path: str, roots: tuple[Path, ...]) -> None:
    for root in roots:
        candidate = (root / PurePosixPath(path)).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return
    raise ToolRequestError("request path escapes the role root")


def validate_tool_request(role: ToolRole | str, request: Mapping[str, object], roots: RoleRoots) -> ToolRequest:
    """Validate a role-scoped request without opening paths or executing anything.

    ``roots`` are trusted controller roots, one or more absolute directories per
    role.  Every path is required to remain below at least one configured root,
    including after resolving any already-existing symlink component.
    """

    try:
        normalized_role = ToolRole(role)
    except (TypeError, ValueError) as error:
        raise ToolRequestError("unknown tool role") from error
    if not isinstance(request, Mapping):
        raise ToolRequestError("tool request must be an object")
    forbidden = _FORBIDDEN_REQUEST_FIELDS.intersection(request)
    if forbidden:
        raise ToolRequestError(f"forbidden request field: {sorted(forbidden)[0]}")

    tool = request.get("tool")
    model_type: type[_StrictRequest]
    if tool == "read":
        model_type = ReadRequest
    elif tool == "search":
        model_type = SearchRequest
    elif tool == "write_patch":
        model_type = WritePatchRequest
    elif tool == "run":
        model_type = RunRequest
    elif tool == "task":
        model_type = TaskRequest
    else:
        raise ToolRequestError("unknown tool")

    if tool not in ROLE_TOOL_ALLOWLIST[normalized_role]:
        raise ToolRequestError(f"role {normalized_role.value} may not invoke {tool}")
    try:
        parsed = model_type.model_validate(dict(request))
    except ValidationError as error:
        raise ToolRequestError(f"invalid {tool} request: {error}") from error

    roots_for_role = _role_roots(normalized_role, roots)
    for path in request_paths(parsed):
        _assert_within_any_root(path, roots_for_role)
    return parsed
