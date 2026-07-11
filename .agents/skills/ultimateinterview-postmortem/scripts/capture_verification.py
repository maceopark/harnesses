#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
#
# Capture one Part-1 verification command as an execution fact artifact.

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Annotated, Final

import typer

_POSTMORTEM_SCRIPTS: Final[Path] = Path(__file__).resolve().parent
_INTERVIEW_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "ultimateinterview"
sys.path.insert(0, str(_POSTMORTEM_SCRIPTS))
sys.path.insert(0, str(_INTERVIEW_ROOT))

from scripts.handoff_coverage import extract_part1  # noqa: E402
from scripts.verification_policy import SafeAutoPolicyError, validate_safe_auto  # noqa: E402
from evidence_artifacts import stable_artifact_id  # noqa: E402
from process_cleanup import (  # noqa: E402
    ProcessCleanupError,
    as_bytes,
    terminate_and_drain as _terminate_and_drain,
)
from verification_contract import (  # noqa: E402
    CapturedOutput,
    canonical_command_digest,
    parse_verification_rows,
)

DEFAULT_TIMEOUT_SECONDS: Final[int] = 60
MAX_CAPTURED_OUTPUT_BYTES: Final[int] = 128_000
EVIDENCE_RELPATH: Final[str] = ".omo/evidence"
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]

app = typer.Typer(add_completion=False, no_args_is_help=True)


def fail(message: str, code: int = 2) -> typer.Exit:
    typer.secho(f"capture_verification: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=code)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def bounded_text(content: bytes) -> str:
    """Return the bounded inline representation of a stream's raw bytes."""
    return content[:MAX_CAPTURED_OUTPUT_BYTES].decode("utf-8", errors="replace")


def artifact_id(rel_path: str) -> str:
    return stable_artifact_id(rel_path)


def atomically_write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def capture(row_number: int, check: str | None, handoff_text: str, repo_root: Path, timeout: int) -> CapturedOutput:
    rows = parse_verification_rows(extract_part1(handoff_text))
    row = next((candidate for candidate in rows if candidate.row_number == row_number), None)
    if row is None:
        raise fail(f"verification row {row_number} was not found")
    if check is not None and check != row.check:
        raise fail(f"--check does not match verification row {row_number}: expected {row.check!r}")
    if not row.is_command_row:
        raise fail(f"verification row {row_number} is prose/action-only and cannot be executed")
    if row.run_policy != "safe-auto":
        policy = row.run_policy or "unspecified"
        raise fail(
            f"verification row {row_number} run policy {policy!r} is not safe-auto; "
            "supply manual/external evidence without command capture"
        )
    try:
        validate_safe_auto(row.raw_command, row.pass_condition)
    except SafeAutoPolicyError as error:
        raise fail(f"verification row {row_number} safe-auto policy rejected command: {error}") from error
    argv = shlex.split(row.raw_command, posix=True)

    started_at = utc_now()
    spawned = False
    timed_out = False
    exit_code: int | None = None
    stdout_bytes = b""
    stderr_bytes = b""
    isolated_group = os.name == "posix"
    try:
        process = subprocess.Popen(
            argv,
            shell=False,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=isolated_group,
        )
        spawned = True
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired as error:
            timed_out = True
            stdout_bytes, stderr_bytes = _terminate_and_drain(
                process,
                isolated_group,
                as_bytes(error.stdout),
                as_bytes(error.stderr),
            )
    except OSError as error:
        stderr_bytes = str(error).encode("utf-8", errors="replace")
    ended_at = utc_now()

    return CapturedOutput(
        marker="CAPTURED-OUTPUT",
        spec_row_number=row.row_number,
        check=row.check,
        kind=row.kind,
        exact_command=row.raw_command,
        command_digest=canonical_command_digest(row.raw_command),
        effective_heads=row.effective_heads,
        cwd=str(repo_root),
        started_at=started_at,
        ended_at=ended_at,
        spawned=spawned,
        timed_out=timed_out,
        timeout_seconds=timeout,
        exit_code=exit_code,
        stdout=bounded_text(stdout_bytes),
        stderr=bounded_text(stderr_bytes),
        stdout_full_bytes=len(stdout_bytes),
        stderr_full_bytes=len(stderr_bytes),
        stdout_sha256=hashlib.sha256(stdout_bytes).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr_bytes).hexdigest(),
    )


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help=".ultimateinterview/<slug>/ session directory")
    ],
    row: Annotated[int, typer.Option("--row", help="One-based Part-1 verification row number")],
    check: Annotated[str | None, typer.Option("--check", help="Exact verification check text")] = None,
    slug: Annotated[str | None, typer.Option("--slug", help="Evidence slug; default session directory name")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Command timeout in seconds")] = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Execute one command row and write its fact-only capture artifact."""
    if not session_dir.is_dir():
        raise fail(f"session dir {session_dir} is not a directory")
    if timeout <= 0:
        raise fail("--timeout must be a positive integer")
    selected_slug = slug or session_dir.resolve().name
    if (
        not selected_slug
        or selected_slug in {".", ".."}
        or Path(selected_slug).name != selected_slug
    ):
        raise fail("--slug must be a single directory name")

    handoff_path = session_dir / "handoff.md"
    if not handoff_path.is_file():
        raise fail(f"handoff.md not found at {handoff_path}")
    repo_root = session_dir.parent.parent.resolve()
    try:
        record = capture(row, check, handoff_path.read_text(encoding="utf-8"), repo_root, timeout)
    except ProcessCleanupError as error:
        raise fail(f"timeout cleanup could not prove process-group exit: {error}", code=1) from error

    filename = f"captured-output-row-{row:04d}.json"
    output_path = repo_root / EVIDENCE_RELPATH / selected_slug / filename
    atomically_write_json(output_path, record.model_dump(mode="json"))
    rel_path = str(output_path.relative_to(repo_root))
    typer.echo(f"capture written: {output_path} | artifact id: {artifact_id(rel_path)}")


if __name__ == "__main__":
    app()
