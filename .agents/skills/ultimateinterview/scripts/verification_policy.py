#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

import re
import shlex
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Final

SHELL_CONTROL: Final[frozenset[str]] = frozenset({";", "&", "&&", "|", "||", ">", ">>", "<", "<<"})
ASSIGNMENT: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PYTHON: Final[re.Pattern[str]] = re.compile(r"^python(?:3(?:\.\d+)?)?$")
EXIT_OBSERVABLE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:(?:exit|return)\s+code\s*(?:=|is|equals|:)?\s*\d+|exits?\s+(?:with\s+)?(?:code\s*)?\d+)\b",
    re.IGNORECASE,
)
OUTPUT_OBSERVABLE: Final[re.Pattern[str]] = re.compile(
    r"\boutput\s+(?:exactly\s+)?(?:equals|contains|matches|reports)\s+\S+",
    re.IGNORECASE,
)
ARTIFACT_OBSERVABLE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:artifact|file)\s+(?P<path>\S+)\s+(?:exists|equals|contains|matches|has\s+sha256|sha256\s+equals)\s*\S*",
    re.IGNORECASE,
)
AMBIGUOUS_EXIT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:exit|return)\s+code\s*(?:=|is|equals|:)?\s*\d+\s+(?:or|and)\s+\d+\b",
    re.IGNORECASE,
)


class SafeAutoPolicyError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class OptionPolicy:
    boolean: frozenset[str]
    valued: frozenset[str]
    path_valued: frozenset[str] = frozenset()


PYTEST_POLICY: Final[OptionPolicy] = OptionPolicy(
    boolean=frozenset(
        {"-q", "-qq", "-v", "-vv", "-x", "-s", "--quiet", "--verbose", "--collect-only", "--co", "--disable-warnings", "--strict-config", "--strict-markers", "--showlocals"},
    ),
    valued=frozenset(
        {"-k", "-m", "--tb", "--color", "--capture", "--rootdir", "--basetemp", "--ignore", "--junitxml", "--durations", "--maxfail", "--log-level"},
    ),
    path_valued=frozenset({"--rootdir", "--basetemp", "--ignore", "--junitxml"}),
)
RUFF_POLICY: Final[OptionPolicy] = OptionPolicy(
    boolean=frozenset({"--check", "--diff", "--no-cache", "--statistics", "--show-fixes", "--verbose", "-v", "--quiet", "-q"}),
    valued=frozenset({"--config", "--target-version", "--line-length", "--output-format", "--select", "--ignore", "--extend-select", "--extend-ignore"}),
    path_valued=frozenset({"--config"}),
)
TYPE_POLICY: Final[OptionPolicy] = OptionPolicy(
    boolean=frozenset({"--warnings", "--outputjson", "--verbose"}),
    valued=frozenset({"--project", "-p", "--level", "--pythonversion", "--pythonplatform", "--threads"}),
    path_valued=frozenset({"--project", "-p"}),
)
CARGO_POLICY: Final[OptionPolicy] = OptionPolicy(
    boolean=frozenset({"--workspace", "--all", "--all-targets", "--all-features", "--no-default-features", "--locked", "--frozen", "--offline", "--release", "--quiet", "-q", "--verbose", "-v", "--tests"}),
    valued=frozenset({"--test", "--package", "-p", "--features", "--target", "--manifest-path", "--jobs", "-j"}),
    path_valued=frozenset({"--manifest-path"}),
)
GO_POLICY: Final[OptionPolicy] = OptionPolicy(
    boolean=frozenset({"-v", "-race", "-cover"}),
    valued=frozenset({"-run", "-shuffle", "-timeout", "-coverprofile", "-tags", "-mod", "-p"}),
    path_valued=frozenset({"-coverprofile"}),
)


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character) in {"Cc", "Cf"} for character in value)


def _tokens(command: str) -> tuple[str, ...]:
    if "\n" in command or "\r" in command:
        raise SafeAutoPolicyError("safe-auto forbids newline-separated shell commands")
    if "\\" in command or "$" in command or _has_control(command):
        raise SafeAutoPolicyError("safe-auto forbids ASCII controls, backslashes, and shell expansion markers")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    try:
        tokens = tuple(lexer)
    except ValueError as error:
        raise SafeAutoPolicyError(f"safe-auto command is malformed: {error}") from error
    if not tokens or any(token in SHELL_CONTROL for token in tokens):
        raise SafeAutoPolicyError("safe-auto forbids empty commands and shell control/background operators")
    if any("`" in token or "$(" in token or ASSIGNMENT.match(token) for token in tokens):
        raise SafeAutoPolicyError("safe-auto forbids substitution and environment/credential assignment")
    return tokens


def _repository_relative(value: str) -> bool:
    target = value.split("::", maxsplit=1)[0]
    posix = PurePosixPath(target)
    windows = PureWindowsPath(target)
    clean = "\\" not in target and "$" not in target and not _has_control(target)
    return bool(target) and clean and "://" not in target and not target.startswith("~") and not posix.is_absolute() and not windows.drive and ".." not in posix.parts


def _options_allowed(arguments: tuple[str, ...], policy: OptionPolicy) -> bool:
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not argument.startswith("-") or argument == "-":
            if not _repository_relative(argument):
                return False
            index += 1
            continue
        name, separator, value = argument.partition("=")
        if name in policy.boolean and not separator:
            index += 1
            continue
        if name in policy.valued:
            if separator:
                if not value or (name in policy.path_valued and not _repository_relative(value)):
                    return False
                index += 1
                continue
            if index + 1 < len(arguments) and not arguments[index + 1].startswith("-"):
                if name in policy.path_valued and not _repository_relative(arguments[index + 1]):
                    return False
                index += 2
                continue
        return False
    return True


def _unwrap(tokens: tuple[str, ...]) -> tuple[str, ...]:
    if tokens[:2] == ("uv", "run"):
        nested = tokens[2:]
        if not nested or nested[0].startswith("-"):
            raise SafeAutoPolicyError("safe-auto uv run requires a direct allowlisted verification command")
        return nested
    return tokens


def _python_family(tokens: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    head = PurePath(tokens[0]).name
    if PYTHON.fullmatch(head) is None:
        return head, tokens[1:]
    if len(tokens) < 3 or tokens[1] != "-m":
        raise SafeAutoPolicyError("safe-auto Python requires an allowlisted -m verification module")
    return tokens[2], tokens[3:]


def _go_options_allowed(arguments: tuple[str, ...]) -> bool:
    normalized: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-count=1":
            index += 1
            continue
        if argument == "-count" and index + 1 < len(arguments) and arguments[index + 1] == "1":
            index += 2
            continue
        if argument.startswith("-count"):
            return False
        normalized.append(argument)
        index += 1
    return _options_allowed(tuple(normalized), GO_POLICY)


def _command_allowed(tokens: tuple[str, ...]) -> bool:
    family, arguments = _python_family(_unwrap(tokens))
    if family == "pytest":
        return _options_allowed(arguments, PYTEST_POLICY)
    if family == "ruff":
        if not arguments or arguments[0] not in {"check", "format"}:
            return False
        if arguments[0] == "format" and "--check" not in arguments[1:]:
            return False
        return _options_allowed(arguments[1:], RUFF_POLICY)
    if family in {"basedpyright", "pyright"}:
        return _options_allowed(arguments, TYPE_POLICY)
    if family == "compileall":
        return bool(arguments) and _options_allowed(arguments, OptionPolicy(frozenset({"-q"}), frozenset({"-j"})))
    if family in {"npm", "pnpm", "bun"}:
        return arguments == ("test",) or (
            len(arguments) == 2 and arguments[0] == "run" and arguments[1] in {"build", "check", "lint", "test", "typecheck", "verify"}
        )
    if family == "cargo":
        return bool(arguments) and arguments[0] in {"build", "check", "clippy", "test"} and _options_allowed(arguments[1:], CARGO_POLICY)
    if family == "go":
        return bool(arguments) and arguments[0] in {"build", "test", "vet"} and _go_options_allowed(arguments[1:])
    if family == "git":
        return arguments in {("diff", "--check"), ("diff", "--cached", "--check"), ("diff", "--check", "--cached")}
    if family in {"make", "just"}:
        return len(arguments) == 1 and arguments[0] in {"build", "check", "lint", "test", "typecheck", "verify"}
    return False


def validate_safe_auto(command: str, pass_condition: str) -> None:
    if not _command_allowed(_tokens(command)):
        raise SafeAutoPolicyError("safe-auto requires a recognized bounded local test/lint/type/build command and options")
    explicit_exit = EXIT_OBSERVABLE.search(pass_condition) is not None and AMBIGUOUS_EXIT.search(pass_condition) is None
    artifact_matches = tuple(ARTIFACT_OBSERVABLE.finditer(pass_condition))
    if any(not _repository_relative(match.group("path")) for match in artifact_matches):
        raise SafeAutoPolicyError("safe-auto artifact observable requires a canonical repository-relative path")
    explicit_assertion = OUTPUT_OBSERVABLE.search(pass_condition) is not None or bool(artifact_matches)
    if not explicit_exit and not explicit_assertion:
        raise SafeAutoPolicyError("safe-auto pass condition requires an explicit numeric exit code or exact output/artifact observable")
