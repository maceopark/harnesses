from __future__ import annotations

import subprocess

import pytest

from driftbench import tmux_panes


class DashboardTmux:
    def __init__(self) -> None:
        self.commands = set(tmux_panes._DISCOVERY_REQUIRED_COMMANDS)
        self.panes = {"%1"}
        self.calls: list[list[str]] = []
        self.writes: list[tuple[str, str]] = []
        self.next_pane = 3

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        command, arguments = argv[1], argv[2:]
        output = ""
        if command == "list-commands":
            output = "\n".join(sorted(self.commands)) + "\n"
        elif command == "list-panes":
            output = "\n".join(sorted(self.panes)) + "\n"
        elif command == "new-window":
            self.panes.add("%2")
            output = "@2 %2\n"
        elif command == "split-window":
            pane = f"%{self.next_pane}"
            self.next_pane += 1
            self.panes.add(pane)
            output = pane + "\n"
        elif command == "send-keys":
            self.writes.append((arguments[arguments.index("-t") + 1], arguments[-1]))
        return subprocess.CompletedProcess(argv, 0, output, "")


def _dashboard(monkeypatch: pytest.MonkeyPatch, runner: DashboardTmux, workers: int = 4):
    monkeypatch.setattr(tmux_panes.shutil, "which", lambda *_args, **_kwargs: "/tmux")
    return tmux_panes.DiscoveryDashboard.require(
        run_id="run-1",
        worker_count=workers,
        environment={"TMUX": "active", "TMUX_PANE": "%1", "PATH": "/bin"},
        runner=runner,
    )


def test_preflight_fails_closed_without_attached_tmux() -> None:
    with pytest.raises(tmux_panes.DiscoveryDashboardError, match="attached tmux"):
        tmux_panes.DiscoveryDashboard.require(run_id="run", environment={})


def test_creates_exactly_four_fixed_tiled_panes(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = DashboardTmux()
    dashboard = _dashboard(monkeypatch, runner)

    assert dashboard.window_id == "@2"
    assert dashboard.pane_ids == ("%2", "%3", "%4", "%5")
    assert sum(call[1] == "new-window" for call in runner.calls) == 1
    assert sum(call[1] == "split-window" for call in runner.calls) == 3
    assert [call for call in runner.calls if call[1] == "select-layout"][-1][-1] == "tiled"
    assert not any(call[1] in {"kill-pane", "kill-window"} for call in runner.calls)


def test_worker_output_is_cumulative_structured_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = DashboardTmux()
    dashboard = _dashboard(monkeypatch, runner)
    worker = dashboard.worker(0)

    worker.start_cell(candidate="g00-c01", case="bookmarks", repetition=2)
    worker.stage("Interview")
    worker.decision(
        decision_id="DEC-1",
        question="Which behavior? token=supersecret",
        options="safe, strict",
        recommended="strict",
        selected="safe",
    )

    text = "".join(block for pane, block in runner.writes if pane == "%2")
    assert "Candidate: g00-c01" in text
    assert "Stage: Interview" in text
    assert "Question DEC-1" in text
    assert "Options: safe, strict" in text
    assert "Recommended: strict" in text
    assert "Selected answer: safe" in text
    assert "supersecret" not in text
    assert "token=[redacted]" in text


def test_finish_writes_all_panes_and_preserves_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = DashboardTmux()
    dashboard = _dashboard(monkeypatch, runner)
    runner.calls.clear()

    dashboard.finish(pareto="g00-c00,g00-c02", run_directory="/tmp/run")

    assert {pane for pane, _ in runner.writes} == set(dashboard.pane_ids)
    assert all("Generation complete" in block and "/tmp/run" in block for _, block in runner.writes)
    assert not any(call[1] in {"kill-pane", "kill-window"} for call in runner.calls)
