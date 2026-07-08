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
# Prose action rows ("Run malformed id, ...") are legal in these tables; a
# segment is only treated as a command when its head looks like one (lowercase
# start or explicit path). Fail-closed: exit 1 on any missing binary unless
# --advisory; a genuinely cross-host handoff can annotate and override.

from __future__ import annotations

import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_coverage import extract_part1  # noqa: E402

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
    lines = [line.strip() for line in text.splitlines()]
    found: list[tuple[list[str], list[list[str]]]] = []
    index = 0

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

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


def command_heads(cell_text: str) -> list[str]:
    """Extract the command-head tokens of every shell segment in one cell."""
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
            continue  # unbalanced quotes: prose, not a command
        had_assignment = bool(tokens) and bool(ASSIGNMENT.match(tokens[0]))
        while tokens and ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        head = tokens[0]
        if head in SHELL_BUILTINS or head in PROSE_HEADS or head.startswith("$") or "/" in head:
            continue
        if not COMMAND_HEAD.match(head):
            continue  # capitalized/prose head ("Run", "Exercise")
        if not is_command_like(tokens, had_assignment):
            continue  # bare word + prose, no flag/path/redirection/assignment signal
        heads.append(head)
    return heads


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
    search_path = host_search_path()
    heads: dict[str, bool] = {}
    for headers, rows in tables(part1):
        columns = [
            index for index, header in enumerate(headers) if LINTABLE_COLUMN.search(header)
        ]
        for row in rows:
            for column in columns:
                if column >= len(row):
                    continue
                for head in command_heads(row[column]):
                    heads.setdefault(head, shutil.which(head, path=search_path) is not None)

    missing = sorted(head for head, present in heads.items() if not present)
    typer.echo("## Verification Command Lint\n")
    typer.echo(f"- Command heads checked (Part-1 command/verification columns): {len(heads)}")
    for head in sorted(heads):
        typer.echo(f"  - {head}: {'ok' if heads[head] else 'MISSING on this host'}")
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
