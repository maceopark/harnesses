from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import process_cleanup


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 43210


def fake_process() -> FakeProcess:
    return FakeProcess()


def test_permission_race_becomes_bounded_proof_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny(_process_group: int, _signal: signal.Signals | int) -> None:
        raise PermissionError("benign race")

    monkeypatch.setattr(process_cleanup.os, "killpg", deny)

    assert process_cleanup.signal_process_group(fake_process(), signal.SIGKILL) is False


def test_group_exit_requires_stable_absence_after_late_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter((False, False, True, False, False, False, False))
    ticks = iter((0.00, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16))
    signals: list[signal.Signals] = []
    monkeypatch.setattr(process_cleanup, "PROCESS_GROUP_EXIT_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(process_cleanup, "PROCESS_GROUP_STABLE_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(process_cleanup, "PROCESS_GROUP_POLL_SECONDS", 0.0)
    monkeypatch.setattr(process_cleanup.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(process_cleanup.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        process_cleanup, "process_group_exists", lambda _process: next(states, False)
    )
    monkeypatch.setattr(
        process_cleanup,
        "signal_process_group",
        lambda _process, selected: signals.append(selected) or True,
    )

    process_cleanup._wait_for_process_group_exit(fake_process())

    assert signals == [signal.SIGKILL]
