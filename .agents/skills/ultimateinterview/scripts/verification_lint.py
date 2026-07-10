#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
# (pydantic/rich are pulled in by the shared handoff_coverage import.)

# ─── How to run ───
#      uv run scripts/verification_lint.py <session-dir> [--advisory]
# ──────────────────
#
# Verification-command executability gate.
#
# A Build Contract's Verification Commands are a contract with the build host:
# the todo-cli-app-5 handoff wrote `python -m pytest` and `HOME=... python
# todo.py` on a host that has only `python3` and no global pytest, so the
# implementer had to substitute invocations on the fly (two decisions.jsonl
# `execution_process_gap` entries). The interviewer's host and the build host
# are the same in this workflow - a missing binary is checkable for free at
# drafting time, and this script owns that check: it scans every Part-1 table
# column whose header mentions command/verification, extracts command heads,
# and verifies each against PATH.
#
from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from collections.abc import Iterable
from typing import Annotated, Final

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.handoff_coverage import extract_part1  # noqa: E402

SHELL_BUILTINS: Final[frozenset[str]] = frozenset(
    {
        ".", ":", "!", "[", "[[", "alias", "break", "case", "cd", "command",
        "continue", "do", "done", "echo", "elif", "else", "esac", "eval",
        "exec", "exit", "export", "false", "fi", "for", "if", "local",
        "printf", "read", "return", "set", "shift", "source", "test", "then",
        "trap", "true", "type", "umask", "unset", "until", "wait", "while",
    }
)
LINTABLE_COLUMN: Final[re.Pattern[str]] = re.compile(r"command|verification", re.IGNORECASE)
SEGMENT_SPLIT: Final[re.Pattern[str]] = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
SUBSHELL: Final[re.Pattern[str]] = re.compile(r"\$\(([^()]*)\)")
ASSIGNMENT: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
COMMAND_HEAD: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][A-Za-z0-9._+-]*$")
SOURCE_TAG: Final[re.Pattern[str]] = re.compile(r"\(source:[^)]*\)")
REDIRECTION: Final[frozenset[str]] = frozenset({">", ">>", "<", "<<", "2>", "&>", "|&"})
SCRIPT_SUFFIXES: Final[tuple[str, ...]] = (".py", ".sh", ".js", ".ts", ".rb", ".pl", ".ps1")
# A path-looking argument: leading /, ./, ../ or ~/ with real content after.
# Deliberately NOT a bare mid-token "/" - prose uses slashes ("before/after",
# "stdout/stderr", "and/or") and those are not command signals.
PATH_TOKEN: Final[re.Pattern[str]] = re.compile(r"^(?:\.{0,2}/|~/)\S")
# English function words that start prose fragments inside command cells
# ("no third-party runtime deps", "or inspect pyproject") - never binaries.
PROSE_HEADS: Final[frozenset[str]] = frozenset(
    {"a", "all", "an", "and", "any", "each", "etc", "no", "not", "or", "plus",
     "see", "the", "then", "with"}
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = [line.strip() for line in strip_fenced_blocks(text).splitlines()]
    found: list[tuple[list[str], list[list[str]]]] = []
    index = 0

    def cells(line: str) -> list[str]:
        escaped_pipe = "\x00ULTIMATEINTERVIEW_PIPE\x00"
        protected = line.replace("\\|", escaped_pipe)
        return [
            cell.replace(escaped_pipe, "|").strip()
            for cell in protected.strip().strip("|").split("|")
        ]

    while index < len(lines) - 1:
        if lines[index].startswith("|") and lines[index + 1].startswith("|") and "---" in lines[index + 1]:
            headers = cells(lines[index])
            rows: list[list[str]] = []
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                rows.append(cells(lines[index]))
                index += 1
            found.append((headers, rows))
        else:
            index += 1
    return found


def strip_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in text.splitlines():
        match = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line)
        marker = match.group(1) if match is not None else ""
        if fence_character is None and marker:
            fence_character = marker[0]
            fence_length = len(marker)
            lines.append("")
        elif (
            fence_character is not None
            and marker
            and match is not None
            and marker[0] == fence_character
            and len(marker) >= fence_length
            and not line[match.end() :].strip()
        ):
            fence_character = None
            fence_length = 0
            lines.append("")
        elif fence_character is None:
            lines.append(line)
        else:
            lines.append("")
    return "\n".join(lines)


def looks_like_prose(segment: str) -> bool:
    """Sentence punctuation marks a prose action row, not a shell command."""
    stripped = segment.strip()
    return stripped.endswith(".") or ", " in stripped


def is_command_like(tokens: list[str], had_assignment: bool) -> bool:
    """A segment is a shell command (not a prose fragment) only when it carries
    an affirmative command signal: a leading env-assignment, a flag, a path or
    script-suffix argument, or a redirection. A bare lowercase word followed by
    prose ("assert exit code", "checksum store file", "user runs ...") carries
    none and is skipped - the false-positive class the app-2/app-4 handoffs hit.
    """
    if had_assignment:
        return True
    for token in tokens[1:]:
        if token.startswith("-") and len(token) > 1:
            return True
        if token in REDIRECTION:
            return True
        if token.endswith(SCRIPT_SUFFIXES) or PATH_TOKEN.match(token):
            return True
    return False


def looks_like_shell_cell(cell_text: str) -> bool:
    if "`" in cell_text or re.search(r"&&|\|\||;|\|", cell_text):
        return True
    rough_tokens = cell_text.split()
    return bool(rough_tokens) and (
        bool(ASSIGNMENT.match(rough_tokens[0]))
        or any(
            (token.startswith("-") and len(token) > 1)
            or token.endswith(SCRIPT_SUFFIXES)
            or bool(PATH_TOKEN.match(token))
            for token in rough_tokens
        )
    )


def normalize_command_tokens(tokens: list[str]) -> tuple[list[str], tuple[str, ...]]:
    wrappers: list[str] = []
    while tokens:
        while tokens and ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            break
        if tokens[0] in {"command", "exec"}:
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            continue
        if tokens[0] == "env":
            wrappers.append("env")
            tokens = tokens[1:]
            while tokens and (tokens[0].startswith("-") or ASSIGNMENT.match(tokens[0])):
                tokens = tokens[1:]
            continue
        break
    return tokens, tuple(wrappers)


def command_heads(cell_text: str) -> list[str]:
    """Extract the command-head tokens of every shell segment in one cell."""
    explicit_command = "`" in cell_text
    text = SOURCE_TAG.sub("", cell_text.replace("`", ""))
    segments = [part for part in SEGMENT_SPLIT.split(text) if part.strip()]
    segments.extend(match.group(1) for match in SUBSHELL.finditer(text))
    heads: list[str] = []
    for segment in segments:
        if looks_like_prose(segment):
            continue
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            continue
        had_assignment = bool(tokens) and bool(ASSIGNMENT.match(tokens[0]))
        tokens, wrappers = normalize_command_tokens(tokens)
        heads.extend(wrappers)
        if not tokens or tokens[0] == "eval":
            continue
        head = tokens[0]
        if head in SHELL_BUILTINS or head in PROSE_HEADS or head.startswith("$"):
            continue
        is_path = bool(PATH_TOKEN.match(head) or Path(head).is_absolute())
        if not is_path and not COMMAND_HEAD.match(head):
            continue
        if not is_path and not explicit_command and not is_command_like(tokens, had_assignment):
            continue
        heads.append(head)
    return heads


def lintable_cells(part1: str) -> list[str]:
    cells: list[str] = []
    for headers, rows in tables(part1):
        columns = [index for index, header in enumerate(headers) if LINTABLE_COLUMN.search(header)]
        for row in rows:
            cells.extend(row[column] for column in columns if column < len(row))
    return cells


def command_parse_findings(part1: str) -> tuple[str, ...]:
    findings: list[str] = []
    for cell in lintable_cells(part1):
        if not looks_like_shell_cell(cell):
            continue
        text = SOURCE_TAG.sub("", cell.replace("`", ""))
        for segment in (part for part in SEGMENT_SPLIT.split(text) if part.strip()):
            try:
                tokens = shlex.split(segment, posix=True)
            except ValueError as error:
                findings.append(f"malformed verification command {segment!r}: {error}")
                continue
            tokens, _wrappers = normalize_command_tokens(tokens)
            if tokens and tokens[0] == "eval":
                findings.append("unsupported dynamic verification wrapper 'eval'; use explicit argv")
    return tuple(findings)


def host_search_path() -> str:
    """PATH minus this script's own interpreter venv.

    `uv run` prepends a venv bin that contains a `python` shim; the handoff's
    commands run in a plain shell that has no such shim, so resolving heads
    against the venv would hide exactly the miss this lint exists to catch.
    """
    venv_bins = {
        str(Path(prefix, "bin").resolve())
        for prefix in (sys.prefix, os.environ.get("VIRTUAL_ENV"))
        if prefix
    }
    entries = [
        entry
        for entry in os.environ.get("PATH", os.defpath).split(os.pathsep)
        if entry and str(Path(entry).resolve()) not in venv_bins
    ]
    return os.pathsep.join(entries)


def cell_head_status(
    cells: Iterable[str],
    search_path: str | None = None,
    workdir: Path | None = None,
) -> dict[str, bool]:
    resolved_path = host_search_path() if search_path is None else search_path
    resolved_workdir = Path.cwd() if workdir is None else workdir
    heads: dict[str, bool] = {}
    for cell in cells:
        for head in command_heads(cell):
            candidate = Path(head).expanduser()
            if PATH_TOKEN.match(head) or candidate.is_absolute():
                if not candidate.is_absolute():
                    candidate = resolved_workdir / candidate
                present = candidate.is_file() and os.access(candidate, os.X_OK)
            else:
                present = shutil.which(head, path=resolved_path) is not None
            heads.setdefault(head, present)
    return heads


def command_head_status(
    part1: str,
    search_path: str | None = None,
    workdir: Path | None = None,
) -> dict[str, bool]:
    return cell_head_status(lintable_cells(part1), search_path, workdir)


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Session dir containing handoff.md")
    ],
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit non-zero on a missing head. Default is advisory (report only) - "
            "the head heuristic has false positives on prose-heavy cells, so blocking "
            "is opt-in and only safe on a build host identical to this one.",
        ),
    ] = False,
) -> None:
    handoff_path = session_dir / "handoff.md"
    if not handoff_path.is_file():
        typer.echo(f"error: missing handoff.md at {handoff_path}", err=True)
        raise typer.Exit(2)

    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    workdir = session_dir.parents[1] if session_dir.parent.name == ".ultimateinterview" else Path.cwd()
    parse_findings = command_parse_findings(part1)
    heads = command_head_status(part1, workdir=workdir)

    missing = sorted(head for head, present in heads.items() if not present)
    typer.echo("## Verification Command Lint\n")
    typer.echo(f"- Command heads checked (Part-1 command/verification columns): {len(heads)}")
    for head in sorted(heads):
        typer.echo(f"  - {head}: {'ok' if heads[head] else 'MISSING on this host'}")
    for finding in parse_findings:
        typer.echo(f"  - {finding}")
    if parse_findings and strict:
        raise typer.Exit(1)
    if missing:
        typer.echo(
            f"\n- executable_ok: no - {len(missing)} head(s) not on PATH: {', '.join(missing)}"
        )
        typer.echo(
            "  Swap in the invocation this host actually has (the interview host validated "
            "it), or annotate the row when the build host is genuinely a different machine."
        )
        if strict:
            raise typer.Exit(1)
    else:
        typer.echo("\n- executable_ok: yes")


if __name__ == "__main__":
    app()
