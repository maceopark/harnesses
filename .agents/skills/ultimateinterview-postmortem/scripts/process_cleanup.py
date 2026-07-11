from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Final, IO, Protocol, override

TERMINATION_GRACE_SECONDS: Final[float] = 0.25
PROCESS_GROUP_EXIT_TIMEOUT_SECONDS: Final[float] = 2.0
PROCESS_GROUP_POLL_SECONDS: Final[float] = 0.01
PROCESS_GROUP_STABLE_SECONDS: Final[float] = 0.10


class ProcessIdentity(Protocol):
    pid: int


class ProcessLike(ProcessIdentity, Protocol):
    stdout: IO[bytes] | None
    stderr: IO[bytes] | None

    def communicate(self, *, timeout: float) -> tuple[bytes, bytes]: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def poll(self) -> int | None: ...

    def wait(self, *, timeout: float) -> int: ...


@dataclass(frozen=True, slots=True)
class ProcessCleanupError(RuntimeError):
    process_group_id: int
    timeout_seconds: float

    @override
    def __str__(self) -> str:
        return (
            f"process group {self.process_group_id} still exists after "
            f"{self.timeout_seconds:.2f}s cleanup deadline"
        )


def as_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")


def signal_process_group(
    process: ProcessIdentity, selected_signal: signal.Signals
) -> bool:
    try:
        os.killpg(process.pid, selected_signal)
    except (PermissionError, ProcessLookupError):
        return False
    return True


def process_group_exists(process: ProcessIdentity) -> bool:
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_group_exit(process: ProcessIdentity) -> None:
    deadline = time.monotonic() + PROCESS_GROUP_EXIT_TIMEOUT_SECONDS
    absent_since: float | None = None
    while True:
        now = time.monotonic()
        if process_group_exists(process):
            absent_since = None
            _ = signal_process_group(process, signal.SIGKILL)
        elif absent_since is None:
            absent_since = now
        elif now - absent_since >= PROCESS_GROUP_STABLE_SECONDS:
            return
        remaining = deadline - now
        if remaining <= 0:
            raise ProcessCleanupError(process.pid, PROCESS_GROUP_EXIT_TIMEOUT_SECONDS)
        time.sleep(min(PROCESS_GROUP_POLL_SECONDS, remaining))


def _close_process_pipes(process: ProcessLike) -> None:
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()


def _merge_output(prefix: bytes, completed: bytes) -> bytes:
    if completed.startswith(prefix):
        return completed
    if prefix.startswith(completed):
        return prefix
    return prefix + completed


def terminate_and_drain(
    process: ProcessLike,
    isolated_group: bool,
    stdout_prefix: bytes = b"",
    stderr_prefix: bytes = b"",
) -> tuple[bytes, bytes]:
    deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    if isolated_group:
        _ = signal_process_group(process, signal.SIGTERM)
    else:
        process.terminate()
    stdout_bytes = stdout_prefix
    stderr_bytes = stderr_prefix
    try:
        stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        stdout_bytes = _merge_output(stdout_bytes, as_bytes(stdout))
        stderr_bytes = _merge_output(stderr_bytes, as_bytes(stderr))
    except subprocess.TimeoutExpired as error:
        stdout_bytes = _merge_output(stdout_bytes, as_bytes(error.stdout))
        stderr_bytes = _merge_output(stderr_bytes, as_bytes(error.stderr))
    if isolated_group:
        remaining = deadline - time.monotonic()
        if remaining > 0 and process_group_exists(process):
            time.sleep(remaining)
        if process_group_exists(process):
            _ = signal_process_group(process, signal.SIGKILL)
    elif process.poll() is None:
        process.kill()
    try:
        stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
        stdout_bytes = _merge_output(stdout_bytes, as_bytes(stdout))
        stderr_bytes = _merge_output(stderr_bytes, as_bytes(stderr))
    except subprocess.TimeoutExpired as error:
        if process.poll() is None:
            process.kill()
        stdout_bytes = _merge_output(stdout_bytes, as_bytes(error.stdout))
        stderr_bytes = _merge_output(stderr_bytes, as_bytes(error.stderr))
        _close_process_pipes(process)
        _ = process.wait(timeout=TERMINATION_GRACE_SECONDS)
    if isolated_group:
        _wait_for_process_group_exit(process)
    return stdout_bytes, stderr_bytes
