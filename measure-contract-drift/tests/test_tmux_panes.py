from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from driftbench import tmux_panes


class RecordingTmux:
    def __init__(self, *, width: int = 120, height: int = 40) -> None:
        self.width = width
        self.height = height
        self.calls: list[list[str]] = []
        self.panes = {"%1"}
        self.windows = {"%1": "@1"}
        self.commands = set(tmux_panes._REQUIRED_COMMANDS)
        self.options: dict[tuple[str, str], str] = {}
        self.writes: list[tuple[str, str]] = []
        self.kills: list[str] = []
        self.fail: set[str] = set()
        self.next_pane = 2
        self.split_target: str | None = None

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        command, arguments = argv[1], argv[2:]
        if command in self.fail:
            return subprocess.CompletedProcess(argv, 1, "", "injected")
        output = ""
        if command == "list-commands":
            output = "\n".join(sorted(self.commands)) + "\n"
        elif command == "list-panes":
            output = "\n".join(sorted(self.panes)) + "\n"
        elif command == "display-message":
            target = arguments[arguments.index("-t") + 1]
            if target not in self.panes:
                return subprocess.CompletedProcess(argv, 1, "", "missing")
            if arguments[-1] == "#{pane_id} #{window_id}":
                output = f"{target} {self.windows[target]}\n"
            elif arguments[-1].startswith("#{@driftbench_"):
                keys = [part[2:-1] for part in arguments[-1].split("\t")]
                if any((target, key) not in self.options for key in keys):
                    return subprocess.CompletedProcess(argv, 1, "", "missing")
                output = "\t".join(self.options[(target, key)] for key in keys) + "\n"
            else:
                output = f"{self.width} {self.height}\n"
        elif command == "split-window":
            target = self.split_target or f"%{self.next_pane}"
            self.next_pane += 1
            self.panes.add(target)
            self.windows[target] = "@1"
            output = target + "\n"
        elif command == "set-option":
            target = arguments[arguments.index("-t") + 1]
            self.options[(target, arguments[-2])] = arguments[-1]
        elif command == "show-options":
            target = arguments[arguments.index("-t") + 1]
            key = arguments[-1]
            if target not in self.panes or (target, key) not in self.options:
                return subprocess.CompletedProcess(argv, 1, "", "missing")
            output = self.options[(target, key)] + "\n"
        elif command == "send-keys":
            target = arguments[arguments.index("-t") + 1]
            if target not in self.panes:
                return subprocess.CompletedProcess(argv, 1, "", "missing")
            self.writes.append((target, arguments[-1]))
        elif command == "kill-pane":
            target = arguments[arguments.index("-t") + 1]
            if target not in self.panes:
                return subprocess.CompletedProcess(argv, 1, "", "missing")
            self.panes.remove(target)
            self.kills.append(target)
        return subprocess.CompletedProcess(argv, 0, output, "")


def _environment() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", ""), "TMUX": "active", "TMUX_PANE": "%1"}


def _detect(
    monkeypatch: pytest.MonkeyPatch,
    runner: RecordingTmux,
    *,
    scheduled_cells: int = 2,
    max_parallel: int = 2,
    environment: dict[str, str] | None = None,
) -> tmux_panes.TmuxPresentation | None:
    monkeypatch.setattr(tmux_panes.shutil, "which", lambda *_args, **_kwargs: "/tmux")
    return tmux_panes.TmuxPresentation.detect(
        scheduled_cells=scheduled_cells,
        max_parallel=max_parallel,
        run_id="run-α",
        attempt_id="attempt-1",
        environment=_environment() if environment is None else environment,
        runner=runner,
    )


def _cell() -> dict[str, str]:
    return {
        "cell_id": "case-1-candidate",
        "case_id": "case-1",
        "treatment": "candidate",
    }


def test_activation_covers_cell_and_parallel_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for scheduled in range(1, 13):
        for parallel in range(1, 13):
            runner = RecordingTmux()
            detected = _detect(
                monkeypatch,
                runner,
                scheduled_cells=scheduled,
                max_parallel=parallel,
            )
            assert (detected is not None) == (scheduled >= 2 and parallel >= 2)


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"PATH": "", "TMUX": "active", "TMUX_PANE": "%1"},
        {"PATH": "", "TMUX": "active", "TMUX_PANE": "invalid"},
    ],
)
def test_ordinary_tmux_unavailability_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: dict[str, str],
) -> None:
    monkeypatch.setattr(tmux_panes.shutil, "which", lambda *_args, **_kwargs: None)
    assert (
        tmux_panes.TmuxPresentation.detect(
            scheduled_cells=2,
            max_parallel=2,
            run_id="run",
            attempt_id="attempt",
            environment=environment,
            runner=RecordingTmux(),
        )
        is None
    )
    assert capsys.readouterr() == ("", "")


def test_missing_capability_or_execution_pane_disables_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    runner.fail.add("list-commands")
    assert _detect(monkeypatch, runner) is None

    runner = RecordingTmux()
    runner.panes.clear()
    assert _detect(monkeypatch, runner) is None

    runner = RecordingTmux()
    runner.commands.remove("send-keys")
    assert _detect(monkeypatch, runner) is None


@pytest.mark.parametrize(
    ("width", "height", "direction"), [(160, 40, "-h"), (70, 50, "-v")]
)
def test_create_uses_detached_adaptive_split_and_attempt_metadata(
    monkeypatch: pytest.MonkeyPatch, width: int, height: int, direction: str
) -> None:
    runner = RecordingTmux(width=width, height=height)
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())

    pane.create()

    split = next(call for call in runner.calls if call[1] == "split-window")
    assert split == [
        "/tmux",
        "split-window",
        "-d",
        "-P",
        "-F",
        "#{pane_id}",
        "-t",
        "%1",
        direction,
        "stty -echo; cat",
    ]
    assert not any("select-layout" in call for call in runner.calls)
    assert pane.target == "%2"
    assert len([key for key in runner.options if key[0] == "%2"]) == 5
    title = next(call for call in runner.calls if call[1] == "select-pane")
    assert "[candidate] case-1 — case-1" == title[-1]


def test_exchange_sanitizes_terminal_input_and_checks_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    pane.create()
    runner.calls.clear()

    pane.exchange("Q #{pane_id}\x1b[31m red\x00\nnext", "답\x9bunsafe\nline")

    assert runner.writes == [
        (
            "%2",
            "Question\nQ #{pane_id} red\nnext\n\nAnswer\n답unsafe\nline\n\n",
        )
    ]
    assert [call[1] for call in runner.calls].count("display-message") == 1
    assert all(call[1] != "set-buffer" for call in runner.calls)


def test_exchange_redacts_credentials_and_bounds_content() -> None:
    block = tmux_panes.CellPane._exchange(
        "token=super-secret-value",
        "sk-abcdefghijklmnop " + ("x" * (16 * 1024 + 50)),
    )

    assert "super-secret-value" not in block
    assert "sk-abcdefghijklmnop" not in block
    assert "token=[redacted]" in block
    assert "[truncated]" in block


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"type": "thread.started", "thread_id": "secret"}, "Session started"),
        ({"type": "turn.completed", "usage": {"secret": "x"}}, "Turn completed"),
        (
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "cat ~/.ssh/id_rsa",
                    "output": "secret",
                },
            },
            "Command started",
        ),
        (
            {
                "type": "item.completed",
                "item": {
                    "type": "mcp_tool_call",
                    "tool": "filesystem.read_file",
                    "arguments": {"path": "/secret"},
                    "result": "secret",
                },
            },
            "Tool filesystem.read_file completed",
        ),
        ({"type": "future.event", "payload": "secret"}, "Activity"),
    ],
)
def test_activity_summary_allowlists_only_category_name_and_state(
    event: dict[str, object], expected: str
) -> None:
    summary = tmux_panes.activity_summary(json.dumps(event))

    assert summary == expected
    assert "secret" not in summary
    assert "/secret" not in summary


def test_activity_summary_ignores_malformed_oversized_and_unsafe_tool_names() -> None:
    assert tmux_panes.activity_summary("not json") is None
    assert tmux_panes.activity_summary("x" * (64 * 1024 + 1)) is None
    event = '{"type":"item.started","item":{"type":"mcp_tool_call","tool":"bad name; secret"}}'
    assert tmux_panes.activity_summary(event) == "Tool started"
    secret = '{"type":"item.started","item":{"type":"mcp_tool_call","tool":"AWS_SECRET_ACCESS_KEY"}}'
    assert tmux_panes.activity_summary(secret) == "Tool started"


def test_stage_and_activity_write_only_sanitized_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    pane.create()

    pane.stage("Implementation\x1b[31m")
    pane.activity_line(
        '{"type":"item.completed","item":{"type":"command_execution",'
        '"command":"echo secret","output":"secret"}}'
    )

    assert runner.writes[-2:] == [
        ("%2", "\nStage  Implementation\n"),
        ("%2", "  Command completed\n"),
    ]
    assert "secret" not in "".join(block for _target, block in runner.writes)


def test_concurrent_activity_streams_stay_cell_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner, scheduled_cells=6, max_parallel=6)
    assert presentation is not None
    panes = []
    for index in range(6):
        pane = presentation.pane_for(
            {
                "cell_id": f"case-{index}-candidate",
                "case_id": f"case-{index}",
                "treatment": "candidate",
            }
        )
        pane.create()
        panes.append(pane)
    runner.writes.clear()

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(
            pool.map(
                lambda item: item[1].activity_line(
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {"type": "mcp_tool_call", "tool": f"tool{item[0]}"},
                        }
                    )
                ),
                enumerate(panes),
            )
        )

    assert sorted(runner.writes) == [
        (str(pane.target), "  Tool completed\n") for pane in panes
    ]


def test_hostile_titles_and_metadata_are_never_control_or_format_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(
        {
            "cell_id": "cell;$(touch nope)#{pane_id}\x1b[31m",
            "case_id": "case;$(touch nope)#{pane_id}\x1b[31m",
            "treatment": "candidate\nforged",
        }
    )

    pane.create()

    title = next(call[-1] for call in runner.calls if call[1] == "select-pane")
    assert "\x1b" not in title
    assert "#{" not in title
    assert "＃{pane_id}" in title
    for (target, _key), value in runner.options.items():
        if target == pane.target:
            assert set(value) <= set(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
            )


def test_title_identifies_task_and_redacts_bounds_and_flattens_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(
        {
            "cell_id": "bookmark-tag-candidate",
            "case_id": "bookmark-tag",
            "treatment": "candidate",
            "prompt": (
                "Add duplicate-tag handling\nwithout mutation "
                "token=credential-value #{pane_id} " + ("long " * 100)
            ),
        }
    )

    pane.create()

    title = next(call[-1] for call in runner.calls if call[1] == "select-pane")
    assert title.startswith(
        "[candidate] bookmark-tag — Add duplicate-tag handling without mutation"
    )
    assert "credential-value" not in title
    assert "token=[redacted]" in title
    assert "#{" not in title
    assert "\n" not in title
    assert len(title) <= 160
    assert "attempt-" not in title


def test_two_through_twelve_cells_get_distinct_independent_panes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for count in range(2, 13):
        runner = RecordingTmux()
        presentation = _detect(
            monkeypatch, runner, scheduled_cells=count, max_parallel=count
        )
        assert presentation is not None
        panes = []
        for index in range(count):
            cell = {
                "cell_id": f"case-{index}-candidate",
                "case_id": f"case-{index}",
                "treatment": "candidate",
            }
            pane = presentation.pane_for(cell)
            pane.create()
            panes.append(pane)
        assert len({pane.target for pane in panes}) == count

        runner.calls.clear()
        with ThreadPoolExecutor(max_workers=count) as pool:
            list(pool.map(lambda pane: pane.exchange("q", "a"), panes))
        assert len(runner.calls) == count * 2
        for pane in panes:
            target_calls = [
                call[1]
                for call in runner.calls
                if "-t" in call and call[call.index("-t") + 1] == pane.target
            ]
            assert target_calls == [
                "display-message",
                "send-keys",
            ]


def test_ownership_mismatch_warns_once_falls_back_and_never_kills(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    pane.create()
    runner.options[("%2", "@driftbench_attempt")] = "forged"

    pane.exchange("one", "answer one")
    pane.exchange("two", "answer two")

    captured = capsys.readouterr()
    assert captured.err.count("warning: tmux presentation unavailable") == 1
    assert captured.err.count("[case-1/candidate]") == 2
    assert runner.kills == []
    assert runner.writes == []


def test_concurrent_fallback_exchanges_are_complete_locked_blocks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner, scheduled_cells=6, max_parallel=6)
    assert presentation is not None
    panes = []
    for index in range(6):
        pane = presentation.pane_for(
            {
                "cell_id": f"case-{index}-candidate",
                "case_id": f"case-{index}",
                "treatment": "candidate",
            }
        )
        pane.create()
        assert pane.target is not None
        runner.options[(pane.target, "@driftbench_attempt")] = "forged"
        panes.append(pane)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(
            pool.map(
                lambda item: item[1].exchange(
                    f"question-{item[0]}", f"answer-{item[0]}"
                ),
                enumerate(panes),
            )
        )

    stderr = capsys.readouterr().err
    for index in range(6):
        block = (
            f"[case-{index}/candidate]\nQuestion\nquestion-{index}\n\n"
            f"Answer\nanswer-{index}\n\n"
        )
        assert stderr.count(block) == 1


def test_racing_write_finishes_before_owned_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BarrierTmux(RecordingTmux):
        def __init__(self) -> None:
            super().__init__()
            self.barrier_enabled = False
            self.entered = threading.Event()
            self.release = threading.Event()

        def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
            if self.barrier_enabled and argv[1] == "display-message":
                self.barrier_enabled = False
                self.entered.set()
                assert self.release.wait(timeout=2)
            return super().__call__(argv)

    runner = BarrierTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    pane.create()
    runner.calls.clear()
    runner.barrier_enabled = True

    writer = threading.Thread(target=pane.exchange, args=("question", "answer"))
    cleaner = threading.Thread(target=pane.cell_succeeded)
    writer.start()
    assert runner.entered.wait(timeout=2)
    cleaner.start()
    runner.release.set()
    writer.join(timeout=2)
    cleaner.join(timeout=2)

    operations = [call[1] for call in runner.calls]
    assert operations.index("send-keys") < operations.index("kill-pane")
    assert runner.writes == [
        ("%2", "Question\nquestion\n\nAnswer\nanswer\n\n"),
        ("%2", "\nStage  Complete\n"),
    ]
    assert runner.kills == ["%2"]


@pytest.mark.parametrize(
    ("operation", "expect_kill"), [("send-keys", True), ("display-message", False)]
)
def test_write_and_lookup_failures_warn_fall_back_without_losing_exchange(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    expect_kill: bool,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    pane.create()
    runner.fail.add(operation)

    pane.exchange("question", "answer")

    captured = capsys.readouterr().err
    assert captured.count("warning: tmux presentation unavailable") == 1
    assert "Question\nquestion\n\nAnswer\nanswer" in captured
    assert bool(runner.kills) is expect_kill


def test_forged_split_target_is_never_used(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingTmux()
    runner.split_target = "%2; kill-server"
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())

    pane.create()
    pane.exchange("question", "answer")

    assert pane.target is None
    assert not any(
        call[1] in {"set-option", "send-keys", "kill-pane"} for call in runner.calls
    )
    assert "using stderr fallback" in capsys.readouterr().err


def test_valid_existing_pane_target_is_never_bootstrapped_as_owned(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingTmux()
    runner.split_target = "%1"
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())

    pane.create()
    pane.exchange("question", "answer")

    assert pane.target is None
    assert not any(
        call[1] in {"set-option", "select-pane", "send-keys", "kill-pane"}
        for call in runner.calls
    )
    assert "%1" in runner.panes
    assert "using stderr fallback" in capsys.readouterr().err


def test_ambiguous_creation_cleans_only_the_returned_new_pane(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class AmbiguousTmux(RecordingTmux):
        def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
            result = super().__call__(argv)
            if argv[1] == "split-window" and result.returncode == 0:
                self.panes.add("%99")
                self.windows["%99"] = "@1"
            return result

    runner = AmbiguousTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())

    pane.create()

    assert runner.kills == ["%2"]
    assert "%2" not in runner.panes
    assert "%99" in runner.panes
    assert "using stderr fallback" in capsys.readouterr().err


def test_broken_stderr_never_fails_benchmark_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenStderr:
        def write(self, value: str) -> int:
            del value
            raise BrokenPipeError

        def flush(self) -> None:
            raise BrokenPipeError

    runner = RecordingTmux()
    runner.fail.add("split-window")
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())
    monkeypatch.setattr(tmux_panes.sys, "stderr", BrokenStderr())

    pane.create()
    pane.exchange("question", "answer")


def test_tmux_subprocess_timeout_becomes_operation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(tmux_panes.subprocess, "run", timeout)

    result = tmux_panes._default_runner(["tmux", "list-commands"])

    assert result.returncode == 124


@pytest.mark.parametrize(
    ("operation", "expected_kills"),
    [("split-window", []), ("set-option", ["%2"]), ("select-pane", ["%2"])],
)
def test_create_failure_is_cell_scoped_and_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    expected_kills: list[str],
) -> None:
    runner = RecordingTmux()
    runner.fail.add(operation)
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    pane = presentation.pane_for(_cell())

    pane.create()
    pane.exchange("question", "answer")

    assert capsys.readouterr().err.count("warning: tmux presentation unavailable") == 1
    assert runner.writes == []
    assert runner.kills == expected_kills


def test_success_kills_owned_pane_and_failure_retains_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    successful = presentation.pane_for(_cell())
    successful.create()
    successful.cell_succeeded()
    assert runner.kills == ["%2"]

    failed = presentation.pane_for(
        {
            "cell_id": "case-2-baseline",
            "case_id": "case-2",
            "treatment": "baseline",
        }
    )
    failed.create()
    failed.stage("Implementation")
    failed.cell_failed(RuntimeError("credential=secret"))
    assert "%3" in runner.panes
    assert runner.writes[-1][1].startswith(
        "\nCell stopped\nStage: Implementation\nClassification: RuntimeError"
    )
    assert "secret" not in runner.writes[-1][1]


def test_cleanup_and_failure_summary_failures_warn_without_cross_pane_kill(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingTmux()
    presentation = _detect(monkeypatch, runner)
    assert presentation is not None
    cleanup = presentation.pane_for(_cell())
    cleanup.create()
    runner.fail.add("kill-pane")
    cleanup.cell_succeeded()
    assert "%2" in runner.panes
    assert capsys.readouterr().err.count("warning: tmux presentation unavailable") == 1

    runner.fail.remove("kill-pane")
    summary = presentation.pane_for(
        {
            "cell_id": "case-2-baseline",
            "case_id": "case-2",
            "treatment": "baseline",
        }
    )
    summary.create()
    runner.fail.add("send-keys")
    summary.cell_failed(RuntimeError("secret"))
    assert summary.target in runner.panes
    assert summary.target not in runner.kills


def test_resume_attempts_use_distinct_ownership() -> None:
    runner = RecordingTmux()
    first = tmux_panes.TmuxPresentation("/tmux", "%1", "run", "attempt-1", runner)
    second = tmux_panes.TmuxPresentation("/tmux", "%1", "run", "attempt-2", runner)
    old = first.pane_for(_cell())
    old.create()
    old.cell_failed(RuntimeError("failed"))
    new = second.pane_for(_cell())
    new.create()
    assert new._metadata()["attempt"] != old._metadata()["attempt"]
    assert old.target == "%2"
    assert new.target == "%3"
    assert "%2" in runner.panes


def test_invocation_interruption_retains_all_active_panes_and_blocks_cleanup() -> None:
    runner = RecordingTmux()
    presentation = tmux_panes.TmuxPresentation(
        "/tmux", "%1", "run", "attempt-1", runner
    )
    cells = [
        {
            "cell_id": f"case-{index}-candidate",
            "case_id": f"case-{index}",
            "treatment": "candidate",
        }
        for index in range(2)
    ]
    for cell in cells:
        pane = presentation.pane_for(cell)
        pane.create()
        pane.stage("Implementation")

    presentation.invocation_failed(KeyboardInterrupt())
    for cell in cells:
        presentation.cell_succeeded(cell)

    assert runner.kills == []
    summaries = [block for _target, block in runner.writes if "Cell stopped" in block]
    assert len(summaries) == 2
    assert all("Stage: Implementation" in block for block in summaries)
    assert all("Classification: KeyboardInterrupt" in block for block in summaries)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is unavailable")
def test_real_tmux_smoke_uses_isolated_server() -> None:
    executable = shutil.which("tmux")
    assert executable is not None
    socket = f"driftbench-test-{uuid.uuid4().hex}"

    def isolated(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [argv[0], "-L", socket, *argv[1:]],
            text=True,
            capture_output=True,
            check=False,
        )

    subprocess.run(
        [
            executable,
            "-L",
            socket,
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "smoke",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        original = isolated(
            [executable, "display-message", "-p", "-t", "smoke", "#{pane_id}"]
        ).stdout.strip()
        active_before = isolated(
            [
                executable,
                "list-panes",
                "-t",
                "smoke",
                "-F",
                "#{pane_id} #{pane_active}",
            ]
        ).stdout.splitlines()
        assert f"{original} 1" in active_before
        presentation = tmux_panes.TmuxPresentation.detect(
            scheduled_cells=2,
            max_parallel=2,
            run_id="smoke-run",
            attempt_id="smoke-attempt",
            environment={
                "PATH": os.environ["PATH"],
                "TMUX": "isolated",
                "TMUX_PANE": original,
            },
            runner=isolated,
        )
        assert presentation is not None
        pane = presentation.pane_for(_cell())
        pane.create()
        target = pane.target
        assert target is not None and target != original
        active_after = isolated(
            [
                executable,
                "list-panes",
                "-t",
                "smoke",
                "-F",
                "#{pane_id} #{pane_active}",
            ]
        ).stdout.splitlines()
        assert f"{original} 1" in active_after
        pane.exchange("multiline\nquestion", "unicode 답")
        time.sleep(0.1)
        captured = isolated([executable, "capture-pane", "-p", "-t", target]).stdout
        assert "multiline" in captured
        assert "unicode 답" in captured
        pane.cell_succeeded()
        remaining = isolated(
            [executable, "list-panes", "-a", "-F", "#{pane_id}"]
        ).stdout.splitlines()
        assert original in remaining
        assert target not in remaining
    finally:
        subprocess.run(
            [executable, "-L", socket, "kill-server"],
            check=False,
            capture_output=True,
            text=True,
        )
