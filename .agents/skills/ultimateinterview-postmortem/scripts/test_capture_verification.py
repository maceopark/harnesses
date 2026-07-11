#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import IO

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_verification
import process_cleanup
from verification_contract import CapturedOutput, VerificationRow

runner = CliRunner()


def make_session(tmp_path: Path) -> Path:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (tmp_path / "output_fixture_test.py").write_text(
        "def test_output_fixture():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text("test:\n\t@sleep 20 & wait\n", encoding="utf-8")
    (session / "handoff.md").write_text(
        """# Part 1 - Build Contract

## Verification Commands

| ID | Covers | Check | Kind | Command / action | Pass condition | Run policy |
| --- | --- | --- | --- | --- | --- | --- |
| VER-001 | REQ-001 | Output capture | test | python3 -m pytest --collect-only -q output_fixture_test.py | exit code = 0 | safe-auto |
| VER-002 | REQ-001 | Nonzero capture | test | python3 -m pytest --collect-only -q missing_fixture_test.py | exit code = 0 | safe-auto |
| VER-003 | REQ-001 | Slow capture | test | make test | exit code = 0 | safe-auto |
| VER-004 | REQ-001 | Manual action | prose | Run the app and inspect it. | visually approved | manual |
""",
        encoding="utf-8",
    )
    return session


def artifact_path(tmp_path: Path, row: int) -> Path:
    return tmp_path / ".omo" / "evidence" / "demo" / f"captured-output-row-{row:04d}.json"


def read_capture(tmp_path: Path, row: int) -> CapturedOutput:
    return CapturedOutput.model_validate_json(artifact_path(tmp_path, row).read_bytes())


def test_selects_exact_row_and_check(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(
        capture_verification.app,
        [str(session), "--row", "2", "--check", "Nonzero capture"],
    )

    assert result.exit_code == 0, result.output
    capture = read_capture(tmp_path, 2)
    assert capture.spec_row_number == 2
    assert capture.check == "Nonzero capture"
    mismatch = runner.invoke(
        capture_verification.app,
        [str(session), "--row", "2", "--check", "Output capture"],
    )
    assert mismatch.exit_code == 2
    assert "does not match" in mismatch.output


def test_prose_action_row_is_refused(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(capture_verification.app, [str(session), "--row", "4"])

    assert result.exit_code == 2
    assert "prose/action-only" in result.output
    assert not artifact_path(tmp_path, 4).exists()


def test_captures_stdout_stderr_and_exit_code(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(capture_verification.app, [str(session), "--row", "1"])

    assert result.exit_code == 0, result.output
    capture = read_capture(tmp_path, 1)
    assert capture.spawned is True
    assert capture.timed_out is False
    assert capture.exit_code == 0
    assert "test_output_fixture" in capture.stdout
    assert capture.stderr == ""
    assert capture.stdout_full_bytes == len(capture.stdout.encode())
    assert capture.stderr_full_bytes == 0


def test_nonzero_exit_persists_capture(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(capture_verification.app, [str(session), "--row", "2"])

    assert result.exit_code == 0, result.output
    capture = read_capture(tmp_path, 2)
    assert capture.exit_code != 0
    assert "not found" in capture.stdout + capture.stderr


def test_timeout_is_recorded_without_raising(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(
        capture_verification.app, [str(session), "--row", "3", "--timeout", "1"]
    )

    assert result.exit_code == 0, result.output
    capture = read_capture(tmp_path, 3)
    assert capture.spawned is True
    assert capture.timed_out is True
    assert capture.exit_code is None
    assert capture.timeout_seconds == 1


def _process_group_members(process_group_id: int) -> dict[int, str]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,pgid=,command="], capture_output=True, text=True, check=True
    )
    processes: dict[int, str] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) == 3 and int(fields[1]) == process_group_id:
            processes[int(fields[0])] = fields[2]
    return processes


def test_timeout_terminates_background_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given the real orphaning command isolated as one executable verification row
    session = make_session(tmp_path)
    process_group_ids: list[int] = []
    original_signal = process_cleanup.signal_process_group

    def record_group(process: subprocess.Popen[bytes], selected: signal.Signals) -> None:
        process_group_ids.append(process.pid)
        original_signal(process, selected)

    monkeypatch.setattr(process_cleanup, "signal_process_group", record_group)

    # When capture reaches its one-second deadline
    result = runner.invoke(
        capture_verification.app, [str(session), "--row", "3", "--timeout", "1"]
    )
    record = read_capture(tmp_path, 3)
    remaining = _process_group_members(process_group_ids[0])

    # Then timeout facts persist and no descendant remains alive
    try:
        assert result.exit_code == 0, result.output
        assert record.spawned is True
        assert record.timed_out is True
        assert record.exit_code is None
        assert remaining == {}
    finally:
        for process_id in remaining:
            try:
                os.kill(process_id, signal.SIGKILL)
            except ProcessLookupError:
                continue


def test_timeout_escalates_term_resistant_group_and_preserves_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given a descendant that ignores TERM and continuously respawns its sleeper
    (tmp_path / "Makefile").write_text(
        "test:\n\t@printf before-timeout; trap '' TERM; while :; do sleep 20; done\n",
        encoding="utf-8",
    )
    command = "make test"
    row = VerificationRow(
        1, "TERM resistant", "test", command, (), True,
        "VER-001", "exit code = 0", "safe-auto",
    )
    monkeypatch.setattr(capture_verification, "parse_verification_rows", lambda _part1: [row])
    sent_signals: list[signal.Signals] = []
    process_group_ids: list[int] = []
    original_signal = process_cleanup.signal_process_group

    def record_signal(process: subprocess.Popen[bytes], selected: signal.Signals) -> None:
        sent_signals.append(selected)
        process_group_ids.append(process.pid)
        original_signal(process, selected)

    monkeypatch.setattr(process_cleanup, "signal_process_group", record_signal)
    # When capture reaches its one-second deadline
    record = capture_verification.capture(1, None, "# Part 1", tmp_path, 1)
    remaining = _process_group_members(process_group_ids[0])

    # Then TERM escalates to KILL, streams drain, and the process group disappears
    try:
        assert sent_signals[0] == signal.SIGTERM
        assert sent_signals[1:]
        assert set(sent_signals[1:]) == {signal.SIGKILL}
        assert record.timed_out is True
        assert "before-timeout" in record.stdout
        assert record.stdout_full_bytes >= len(b"before-timeout")
        assert remaining == {}
    finally:
        for process_id in remaining:
            try:
                os.kill(process_id, signal.SIGKILL)
            except ProcessLookupError:
                continue


class DirectProcessFallback:
    def __init__(self) -> None:
        self.pid = 90001
        self.stdout: IO[bytes] | None = None
        self.stderr: IO[bytes] | None = None
        self.returncode: int | None = None
        self.communications = 0
        self.terminated = False
        self.killed = False

    def communicate(self, *, timeout: float) -> tuple[bytes, bytes]:
        self.communications += 1
        if self.communications == 1:
            raise subprocess.TimeoutExpired("fixture", timeout, output=b"partial", stderr=b"")
        return b"complete", b"done"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, *, timeout: float) -> int:
        self.returncode = -9
        return self.returncode


def test_non_posix_timeout_fallback_reaps_direct_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a non-POSIX direct process that does not exit during TERM grace
    process = DirectProcessFallback()
    monkeypatch.setattr(
        process_cleanup,
        "signal_process_group",
        lambda _process, _signal: pytest.fail("POSIX process-group signal used in fallback"),
    )

    # When timeout cleanup uses the safe direct-process fallback
    stdout, stderr = capture_verification._terminate_and_drain(process, False)

    # Then it terminates, kills, reaps/drains, and never invokes POSIX group APIs
    assert process.terminated is True
    assert process.killed is True
    assert process.communications == 2
    assert stdout == b"partialcomplete"
    assert stderr == b"done"


def test_timeout_fails_closed_when_process_group_never_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = DirectProcessFallback()
    monkeypatch.setattr(process_cleanup, "TERMINATION_GRACE_SECONDS", 0)
    monkeypatch.setattr(process_cleanup, "PROCESS_GROUP_EXIT_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(process_cleanup, "signal_process_group", lambda *_args: None)
    monkeypatch.setattr(process_cleanup, "process_group_exists", lambda _process: True)

    with pytest.raises(RuntimeError, match="process group"):
        capture_verification._terminate_and_drain(process, True)


def test_truncation_preserves_full_byte_count_and_sha_and_leaves_no_tmp(
    tmp_path: Path, monkeypatch
) -> None:
    session = make_session(tmp_path)
    monkeypatch.setattr(capture_verification, "MAX_CAPTURED_OUTPUT_BYTES", 2)

    result = runner.invoke(capture_verification.app, [str(session), "--row", "1"])

    assert result.exit_code == 0, result.output
    capture = read_capture(tmp_path, 1)
    assert len(capture.stdout.encode()) == 2
    assert capture.stdout_full_bytes > 2
    assert capture.stdout_sha256 != hashlib.sha256(capture.stdout.encode()).hexdigest()
    assert not list(artifact_path(tmp_path, 1).parent.glob("*.tmp"))
