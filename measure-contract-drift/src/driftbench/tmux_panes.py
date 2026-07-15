"""Transient, best-effort tmux presentation for interview-eval cells."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable, Mapping

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-_])")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_PANE_ID = re.compile(r"%[0-9]+")
_REQUIRED_COMMANDS = {
    "display-message",
    "kill-pane",
    "list-panes",
    "select-pane",
    "send-keys",
    "set-option",
    "show-options",
    "split-window",
}
_OPTION_NAMES = ("run", "attempt", "cell", "case")
_TMUX_TIMEOUT_SECONDS = 5
_MAX_ACTIVITY_EVENT_BYTES = 64 * 1024
_MAX_EXCHANGE_TEXT = 16 * 1024
_MAX_PANE_TITLE = 160
_SAFE_TOOL_NAMES = {
    "apply_patch",
    "exec_command",
    "filesystem.read_file",
    "filesystem.write_file",
    "web.run",
    "write_stdin",
}
_CREDENTIAL = re.compile(
    r"(?i)(\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*)\S+"
    r"|\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})\b"
)

_ACTIVITY_CATEGORIES = {
    "agent_message": "Agent response",
    "command_execution": "Command",
    "file_change": "File change",
    "mcp_tool_call": "Tool",
    "reasoning": "Reasoning",
    "web_search": "Web search",
}

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def activity_summary(line: str) -> str | None:
    """Reduce one Codex JSONL event to a bounded, content-free status line."""
    if len(line.encode("utf-8", errors="replace")) > _MAX_ACTIVITY_EVENT_BYTES:
        return None
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if not isinstance(event_type, str):
        return None
    fixed = {
        "thread.started": "Session started",
        "turn.started": "Turn started",
        "turn.completed": "Turn completed",
        "turn.failed": "Turn failed",
        "error": "Activity failed",
    }
    if event_type in fixed:
        return fixed[event_type]
    if event_type not in {"item.started", "item.completed", "item.failed"}:
        return "Activity"
    item = event.get("item")
    item = item if isinstance(item, dict) else {}
    category = _ACTIVITY_CATEGORIES.get(item.get("type"), "Activity")
    if category == "Tool":
        candidate = item.get("tool") or item.get("name")
        if candidate in _SAFE_TOOL_NAMES:
            category = f"Tool {candidate}"
    state = event_type.removeprefix("item.")
    return f"{category} {state}"


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


class TmuxPresentation:
    """Invocation-scoped tmux capability and serialized output controller."""

    def __init__(
        self,
        executable: str,
        execution_pane: str,
        run_id: str,
        attempt_id: str,
        runner: Runner = _default_runner,
    ) -> None:
        self.executable = executable
        self.execution_pane = execution_pane
        self.run_id = run_id
        self.attempt_id = attempt_id
        self._runner = runner
        self._lock = threading.RLock()
        self._fallback_lock = threading.RLock()
        self._panes: dict[str, CellPane] = {}
        self._aborted = False

    @classmethod
    def detect(
        cls,
        *,
        scheduled_cells: int,
        max_parallel: int,
        run_id: str,
        attempt_id: str,
        environment: Mapping[str, str] | None = None,
        runner: Runner = _default_runner,
    ) -> TmuxPresentation | None:
        """Return an active controller, silently falling back when tmux is unavailable."""
        if scheduled_cells < 2 or not 2 <= max_parallel <= 6:
            return None
        environment = os.environ if environment is None else environment
        execution_pane = environment.get("TMUX_PANE", "")
        if not environment.get("TMUX") or _PANE_ID.fullmatch(execution_pane) is None:
            return None
        executable = shutil.which("tmux", path=environment.get("PATH"))
        if executable is None:
            return None
        presentation = cls(
            executable, execution_pane, run_id, attempt_id, runner=runner
        )
        try:
            commands = presentation._call("list-commands").stdout
            available = {line.split(maxsplit=1)[0] for line in commands.splitlines()}
            if not _REQUIRED_COMMANDS <= available:
                return None
            if execution_pane not in presentation._pane_ids():
                return None
            dimensions = presentation._dimensions()
            if dimensions[0] < 2 or dimensions[1] < 2:
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        return presentation

    def _call(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = self._runner([self.executable, *arguments])
        if result.returncode:
            raise RuntimeError(f"tmux {arguments[0]} failed")
        return result

    def _dimensions(self) -> tuple[int, int]:
        output = self._call(
            "display-message",
            "-p",
            "-t",
            self.execution_pane,
            "#{pane_width} #{pane_height}",
        ).stdout.split()
        if len(output) != 2:
            raise ValueError("invalid tmux dimensions")
        return int(output[0]), int(output[1])

    def _pane_ids(self) -> set[str]:
        return set(
            self._call("list-panes", "-a", "-F", "#{pane_id}").stdout.splitlines()
        )

    def _window_id(self, target: str) -> str:
        output = self._call(
            "display-message", "-p", "-t", target, "#{pane_id} #{window_id}"
        ).stdout.split()
        if len(output) != 2 or output[0] != target or not output[1].startswith("@"):
            raise ValueError("invalid tmux pane identity")
        return output[1]

    def pane_for(self, cell: Mapping[str, object]) -> CellPane:
        cell_id = str(cell["cell_id"])
        with self._lock:
            pane = self._panes.get(cell_id)
            if pane is None:
                pane = CellPane(self, cell)
                self._panes[cell_id] = pane
            return pane

    def cell_succeeded(self, cell: Mapping[str, object]) -> None:
        with self._lock:
            if self._aborted:
                return
            pane = self._panes.get(str(cell["cell_id"]))
        if pane is not None:
            pane.cell_succeeded()

    def cell_failed(self, cell: Mapping[str, object], error: BaseException) -> None:
        with self._lock:
            pane = self._panes.get(str(cell["cell_id"]))
        if pane is not None:
            pane.cell_failed(error)

    def invocation_failed(self, error: BaseException) -> None:
        with self._lock:
            self._aborted = True
            panes = list(self._panes.values())
        for pane in panes:
            pane.cell_failed(error)

    def _warning(self, pane: CellPane, operation: str) -> None:
        if pane._warned:
            return
        pane._warned = True
        identity = _safe_text(pane.case_id, title=True)
        try:
            print(
                f"warning: tmux presentation unavailable for {identity} ({operation}); "
                "using stderr fallback",
                file=sys.stderr,
                flush=True,
            )
        except (OSError, ValueError):
            pass

    def _fallback(self, pane: CellPane, block: str) -> None:
        identity = _safe_text(pane.case_id, title=True)
        with self._fallback_lock:
            try:
                print(f"[{identity}]\n{block}", file=sys.stderr, end="", flush=True)
            except (OSError, ValueError):
                pass


@dataclass
class CellPane:
    """One attempt-aware pane, created when an executing cell starts."""

    presentation: TmuxPresentation
    cell: Mapping[str, object]
    target: str | None = None
    _fallback_only: bool = False
    _warned: bool = False
    _stage: str = "Starting"
    _terminal: bool = False
    _created_by_this_call: bool = False
    _io_lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def cell_id(self) -> str:
        return str(self.cell["cell_id"])

    @property
    def case_id(self) -> str:
        return str(self.cell["case_id"])

    def _metadata(self) -> dict[str, str]:
        return {
            "run": _encoded(self.presentation.run_id),
            "attempt": _encoded(self.presentation.attempt_id),
            "cell": _encoded(self.cell_id),
            "case": _encoded(self.case_id),
        }

    def _title(self) -> str:
        prompt = self.cell.get("prompt")
        summary = (
            _safe_exchange_text(prompt) if str(prompt or "").strip() else self.case_id
        )
        title = _safe_text(f"{self.case_id} — {summary}", title=True)
        return title[:_MAX_PANE_TITLE].rstrip()

    def create(self) -> None:
        with self.presentation._lock:
            try:
                width, height = self.presentation._dimensions()
                panes_before = self.presentation._pane_ids()
                source_window = self.presentation._window_id(
                    self.presentation.execution_pane
                )
                direction = "-h" if width >= height * 2 else "-v"
                result = self.presentation._call(
                    "split-window",
                    "-d",
                    "-P",
                    "-F",
                    "#{pane_id}",
                    "-t",
                    self.presentation.execution_pane,
                    direction,
                    "stty -echo; cat",
                )
                target = result.stdout.strip()
                if _PANE_ID.fullmatch(target) is None or target in panes_before:
                    raise RuntimeError("tmux returned an invalid pane target")
                if self.presentation._window_id(target) != source_window:
                    raise RuntimeError("tmux returned a pane in the wrong window")
                self.target = target
                self._created_by_this_call = True
                if self.presentation._pane_ids() - panes_before != {target}:
                    raise RuntimeError("tmux pane creation identity is ambiguous")
                for name, value in self._metadata().items():
                    self.presentation._call(
                        "set-option", "-p", "-t", target, f"@driftbench_{name}", value
                    )
                if not self._owned():
                    raise RuntimeError("tmux pane ownership mismatch")
                self._created_by_this_call = False
                self.presentation._call(
                    "select-pane", "-t", target, "-T", self._title()
                )
            except (OSError, RuntimeError, ValueError):
                self._break("create")

    def _owned(self) -> bool:
        if self.target is None:
            return False
        expected = self._metadata()
        try:
            format_string = "\t".join(
                f"#{{@driftbench_{name}}}" for name in _OPTION_NAMES
            )
            actual = (
                self.presentation._call(
                    "display-message", "-p", "-t", self.target, format_string
                )
                .stdout.rstrip("\n")
                .split("\t")
            )
        except (OSError, RuntimeError):
            return False
        return actual == [expected[name] for name in _OPTION_NAMES]

    def _kill_if_owned(self) -> None:
        if self.target is not None and (self._created_by_this_call or self._owned()):
            try:
                self.presentation._call("kill-pane", "-t", self.target)
                self.target = None
                self._created_by_this_call = False
            except (OSError, RuntimeError):
                pass

    def _break(self, operation: str) -> None:
        self._kill_if_owned()
        self._fallback_only = True
        self.presentation._warning(self, operation)

    @staticmethod
    def _exchange(question: object, answer: object) -> str:
        return (
            f"Question\n{_safe_exchange_text(question)}\n\n"
            f"Answer\n{_safe_exchange_text(answer)}\n\n"
        )

    def exchange(self, question: object, answer: object) -> None:
        block = self._exchange(question, answer)
        with self._io_lock:
            if self._terminal:
                return
            if not self._fallback_only and self._owned():
                try:
                    self.presentation._call(
                        "send-keys", "-l", "-t", self.target or "", block
                    )
                    return
                except (OSError, RuntimeError):
                    self._break("write")
            elif not self._fallback_only:
                self._break("ownership")
            self.presentation._fallback(self, block)

    def _status(self, text: str, operation: str) -> None:
        with self._io_lock:
            if self._fallback_only or self._terminal:
                return
            if not self._owned():
                self._break(f"{operation} ownership")
                return
            try:
                self.presentation._call(
                    "send-keys", "-l", "-t", self.target or "", text
                )
            except (OSError, RuntimeError):
                self._break(operation)

    def stage(self, name: str) -> None:
        safe_name = _safe_text(name, title=True)[:64] or "Activity"
        with self._io_lock:
            if self._terminal:
                return
            self._stage = safe_name
        self._status(f"\nStage  {safe_name}\n", "stage")

    def activity_line(self, line: str) -> None:
        summary = activity_summary(line)
        if summary is not None:
            self._status(f"  {summary}\n", "activity")

    def cell_succeeded(self) -> None:
        self.stage("Complete")
        with self._io_lock:
            if self._fallback_only:
                return
            if not self._owned():
                self._break("cleanup ownership")
                return
            try:
                self.presentation._call("kill-pane", "-t", self.target or "")
                self.target = None
                self._terminal = True
            except (OSError, RuntimeError):
                self._break("cleanup")

    def cell_failed(self, error: BaseException) -> None:
        with self._io_lock:
            if self._fallback_only or self._terminal:
                return
            summary = (
                "\nCell stopped\n"
                f"Stage: {_safe_text(self._stage, title=True)}\n"
                f"Classification: {_safe_text(type(error).__name__, title=True)}\n"
                f"Close manually: tmux kill-pane -t {self.target}\n"
            )
            if not self._owned():
                self._break("failure summary ownership")
                return
            try:
                self.presentation._call(
                    "send-keys", "-l", "-t", self.target or "", summary
                )
            except (OSError, RuntimeError):
                self._fallback_only = True
                self.presentation._warning(self, "failure summary")
            finally:
                self._terminal = True
