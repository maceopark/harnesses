"""Fail-closed fixed-worker tmux dashboard for discovery experiments."""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Mapping

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-_])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_PANE_ID = re.compile(r"%[0-9]+")
_DISCOVERY_REQUIRED_COMMANDS = {
    "kill-window",
    "list-panes",
    "new-window",
    "select-layout",
    "select-pane",
    "send-keys",
    "set-option",
    "split-window",
}
_TMUX_TIMEOUT_SECONDS = 5
_MAX_EXCHANGE_TEXT = 16 * 1024
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*)\S+"
    r"|\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})\b"
)

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class DiscoveryDashboardError(RuntimeError):
    """Raised when the mandatory discovery dashboard cannot be established."""


class DiscoveryDashboard:
    """A fail-closed tmux window containing fixed, persistent worker panes."""

    def __init__(
        self,
        executable: str,
        execution_pane: str,
        run_id: str,
        worker_count: int,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.executable = executable
        self.execution_pane = execution_pane
        self.run_id = run_id
        self.worker_count = worker_count
        self._runner = runner or _default_runner
        self._lock = threading.RLock()
        self.window_id = ""
        self.pane_ids: tuple[str, ...] = ()

    @classmethod
    def require(
        cls,
        *,
        run_id: str,
        worker_count: int = 4,
        environment: Mapping[str, str] | None = None,
        runner: Runner | None = None,
    ) -> DiscoveryDashboard:
        if not 1 <= worker_count <= 4:
            raise DiscoveryDashboardError("discovery worker count must be between one and four")
        environment = os.environ if environment is None else environment
        execution_pane = environment.get("TMUX_PANE", "")
        if not environment.get("TMUX") or _PANE_ID.fullmatch(execution_pane) is None:
            raise DiscoveryDashboardError("discovery runs require an attached tmux session")
        executable = shutil.which("tmux", path=environment.get("PATH"))
        if executable is None:
            raise DiscoveryDashboardError("tmux executable is unavailable")
        dashboard = cls(executable, execution_pane, run_id, worker_count, runner=runner)
        dashboard._create()
        return dashboard

    def _call(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = self._runner([self.executable, *arguments])
        if result.returncode:
            raise DiscoveryDashboardError(f"tmux {arguments[0]} failed")
        return result

    def _create(self) -> None:
        try:
            commands = self._call("list-commands").stdout
            available = {line.split(maxsplit=1)[0] for line in commands.splitlines()}
            if not _DISCOVERY_REQUIRED_COMMANDS <= available:
                raise DiscoveryDashboardError("tmux lacks required dashboard commands")
            panes = self._call("list-panes", "-a", "-F", "#{pane_id}").stdout.splitlines()
            if self.execution_pane not in panes:
                raise DiscoveryDashboardError("attached tmux pane is unavailable")
            result = self._call(
                "new-window", "-d", "-P", "-F", "#{window_id} #{pane_id}",
                "-n", f"driftbench-{_safe_text(self.run_id, title=True)[:40]}",
                "stty -echo; cat",
            ).stdout.split()
            if len(result) != 2 or not result[0].startswith("@") or _PANE_ID.fullmatch(result[1]) is None:
                raise DiscoveryDashboardError("tmux returned an invalid dashboard identity")
            self.window_id = result[0]
            pane_ids = [result[1]]
            for _ in range(1, self.worker_count):
                target = self._call(
                    "split-window", "-d", "-P", "-F", "#{pane_id}",
                    "-t", self.window_id, "stty -echo; cat",
                ).stdout.strip()
                if _PANE_ID.fullmatch(target) is None or target in pane_ids:
                    raise DiscoveryDashboardError("tmux returned an invalid worker pane")
                pane_ids.append(target)
            self._call("select-layout", "-t", self.window_id, "tiled")
            for index, pane_id in enumerate(pane_ids):
                self._call("set-option", "-p", "-t", pane_id, "@driftbench_run", _encoded(self.run_id))
                self._call("set-option", "-p", "-t", pane_id, "@driftbench_worker", str(index))
                self._call("select-pane", "-t", pane_id, "-T", f"Discovery worker {index + 1}")
            self.pane_ids = tuple(pane_ids)
        except (OSError, ValueError, DiscoveryDashboardError) as error:
            if self.window_id:
                try:
                    self._runner([self.executable, "kill-window", "-t", self.window_id])
                except OSError:
                    pass
            if isinstance(error, DiscoveryDashboardError):
                raise
            raise DiscoveryDashboardError(f"cannot create discovery dashboard: {error}") from error

    def worker(self, index: int) -> DiscoveryWorkerPane:
        if not 0 <= index < len(self.pane_ids):
            raise DiscoveryDashboardError("worker index is out of range")
        return DiscoveryWorkerPane(self, index, self.pane_ids[index])

    def finish(self, *, pareto: object, run_directory: object) -> None:
        block = (
            "\n=== Generation complete ===\n"
            f"Pareto archive: {_safe_exchange_text(pareto)}\n"
            f"Run directory: {_safe_exchange_text(run_directory)}\n"
        )
        for pane_id in self.pane_ids:
            self._write(pane_id, block)

    def _write(self, pane_id: str, text: str) -> None:
        with self._lock:
            self._call("send-keys", "-l", "-t", pane_id, text)


@dataclass(frozen=True)
class DiscoveryWorkerPane:
    dashboard: DiscoveryDashboard
    index: int
    pane_id: str

    def start_cell(self, *, candidate: object, case: object, repetition: object) -> None:
        self.dashboard._write(
            self.pane_id,
            "\n========================================\n"
            f"Candidate: {_safe_exchange_text(candidate)}\n"
            f"Case: {_safe_exchange_text(case)}\n"
            f"Repetition: {_safe_exchange_text(repetition)}\n",
        )

    def stage(self, name: object) -> None:
        self.dashboard._write(self.pane_id, f"Stage: {_safe_exchange_text(name)}\n")

    def decision(
        self,
        *,
        decision_id: object,
        question: object,
        options: object,
        recommended: object,
        selected: object,
    ) -> None:
        self.dashboard._write(
            self.pane_id,
            f"Question {_safe_exchange_text(decision_id)}: {_safe_exchange_text(question)}\n"
            f"Options: {_safe_exchange_text(options)}\n"
            f"Recommended: {_safe_exchange_text(recommended)}\n"
            f"Selected answer: {_safe_exchange_text(selected)}\n",
        )


def _safe_text(value: object, *, title: bool = False) -> str:
    text = _ANSI.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    if title:
        text = " ".join(text.split()).replace("#", "＃")
    return text


def _safe_exchange_text(value: object) -> str:
    text = _safe_text(value)
    text = _CREDENTIAL.sub(
        lambda match: f"{match.group(1)}[redacted]" if match.group(1) else "[redacted]",
        text,
    )
    if len(text) > _MAX_EXCHANGE_TEXT:
        text = text[:_MAX_EXCHANGE_TEXT] + "\n[truncated]"
    return text


def _encoded(value: object) -> str:
    return base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("ascii")


def _default_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            text=True,
            capture_output=True,
            check=False,
            timeout=_TMUX_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            argv, 124, error.stdout or "", error.stderr or ""
        )
