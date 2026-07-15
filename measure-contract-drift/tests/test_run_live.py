from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _fake_command(path: Path, log_variable: str, *, exit_code: int = 0) -> None:
    path.write_text(
        "#!/bin/sh\n"
        f'eval log="\\${{{log_variable}}}"\n'
        'for argument in "$@"; do printf "<%s>" "$argument" >> "$log"; done\n'
        'printf "\\n" >> "$log"\n'
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _fake_tmux(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'for argument in "$@"; do printf "<%s>" "$argument" >> "$TMUX_LOG"; done\n'
        'printf "\\n" >> "$TMUX_LOG"\n'
        'if [ "$1" = "new-session" ]; then\n'
        "  shift\n"
        "  export TMUX=test-server TMUX_PANE=%9\n"
        '  exec "$@"\n'
        "fi\n"
        'exit "${TMUX_EXIT:-0}"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_wrapper(
    tmp_path: Path,
    *arguments: str,
    tmux: bool = True,
    inside_tmux: bool = True,
    tmux_exit: int = 0,
    expected_returncode: int = 0,
) -> tuple[list[str], list[str]]:
    project = Path(__file__).resolve().parents[1]
    binaries = tmp_path / "bin"
    binaries.mkdir()
    tmux_log = tmp_path / "tmux.log"
    uv_log = tmp_path / "uv.log"
    _fake_command(binaries / "uv", "UV_LOG")
    if tmux:
        _fake_tmux(binaries / "tmux")
    environment = dict(
        os.environ,
        PATH=f"{binaries}:{os.environ['PATH']}" if tmux else f"{binaries}:/usr/bin:/bin",
        TMUX="test-server" if inside_tmux else "",
        TMUX_PANE="%7" if inside_tmux else "",
        TMUX_LOG=str(tmux_log),
        TMUX_EXIT=str(tmux_exit),
        UV_LOG=str(uv_log),
    )

    result = subprocess.run(
        [str(project / "scripts/run-live.sh"), *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    assert result.returncode == expected_returncode, result.stderr
    return (
        tmux_log.read_text(encoding="utf-8").splitlines() if tmux_log.exists() else [],
        uv_log.read_text(encoding="utf-8").splitlines() if uv_log.exists() else [],
    )


def test_parallel_live_wrapper_shows_cell_titles_in_current_tmux_window(
    tmp_path: Path,
) -> None:
    tmux_calls, uv_calls = _run_wrapper(
        tmp_path, "--max-cells", "2", "--max-parallel", "2"
    )

    assert tmux_calls == [
        "<set-option><-w><-t><%7><pane-border-status><top>",
        "<set-option><-w><-t><%7><pane-border-format>< #{pane_title} >",
    ]
    assert len(uv_calls) == 1
    assert "<interview-eval><run>" in uv_calls[0]
    assert "<--max-parallel><2>" in uv_calls[0]


def test_live_wrapper_does_not_change_tmux_for_a_known_single_cell(
    tmp_path: Path,
) -> None:
    tmux_calls, _ = _run_wrapper(tmp_path, "--max-cells", "1", "--max-parallel", "2")

    assert tmux_calls == []


def test_live_wrapper_does_not_change_tmux_for_serial_execution(tmp_path: Path) -> None:
    tmux_calls, _ = _run_wrapper(tmp_path, "--max-cells", "2", "--max-parallel", "1")

    assert tmux_calls == []


def test_live_wrapper_does_not_change_tmux_when_cell_count_is_unknown(
    tmp_path: Path,
) -> None:
    tmux_calls, _ = _run_wrapper(tmp_path, "--max-parallel", "2")

    assert tmux_calls == []


def test_live_wrapper_requires_tmux_before_starting_interview(tmp_path: Path) -> None:
    tmux_calls, uv_calls = _run_wrapper(
        tmp_path,
        "--max-cells",
        "2",
        "--max-parallel",
        "2",
        tmux=False,
        inside_tmux=False,
        expected_returncode=1,
    )

    assert tmux_calls == []
    assert uv_calls == []


def test_live_wrapper_starts_tmux_first_and_runs_interview_inside(
    tmp_path: Path,
) -> None:
    tmux_calls, uv_calls = _run_wrapper(
        tmp_path,
        "--resume",
        "/tmp/run with spaces",
        "--max-cells",
        "2",
        "--max-parallel",
        "2",
        inside_tmux=False,
    )
    project = Path(__file__).resolve().parents[1]

    assert tmux_calls[0] == (
        f"<new-session><{project}/scripts/run-live.sh><--max-parallel><2>"
        "<--max-cells><2><--resume></tmp/run with spaces>"
    )
    assert tmux_calls[1:] == [
        "<set-option><-w><-t><%9><pane-border-status><top>",
        "<set-option><-w><-t><%9><pane-border-format>< #{pane_title} >",
    ]
    assert len(uv_calls) == 1
    assert "<interview-eval><resume>" in uv_calls[0]
    assert "<--run-dir></tmp/run with spaces>" in uv_calls[0]


def test_live_wrapper_continues_when_tmux_title_setup_fails(tmp_path: Path) -> None:
    tmux_calls, uv_calls = _run_wrapper(
        tmp_path,
        "--max-cells",
        "2",
        "--max-parallel",
        "2",
        tmux_exit=1,
    )

    assert tmux_calls == ["<set-option><-w><-t><%7><pane-border-status><top>"]
    assert len(uv_calls) == 1
    assert "<interview-eval><run>" in uv_calls[0]


def test_live_wrapper_resume_keeps_arguments_and_enables_titles(tmp_path: Path) -> None:
    tmux_calls, uv_calls = _run_wrapper(
        tmp_path,
        "--resume",
        "/tmp/run with spaces",
        "--max-cells",
        "2",
        "--max-parallel",
        "2",
    )
    project = Path(__file__).resolve().parents[1]

    assert len(tmux_calls) == 2
    assert uv_calls == [
        f"<run><--project><{project}><driftbench><interview-eval><resume>"
        "<--run-dir></tmp/run with spaces><--max-parallel><2>"
        "<--max-cells><2>"
    ]


def test_run_live_accepts_six_and_rejects_seven_before_tmux(tmp_path: Path) -> None:
    _, uv_calls = _run_wrapper(tmp_path, "--max-cells", "6", "--max-parallel", "6")
    assert "<--max-cells><6>" in uv_calls[0]
    assert "<--max-parallel><6>" in uv_calls[0]

    rejected_root = tmp_path / "rejected"
    rejected_root.mkdir()
    _, rejected = _run_wrapper(rejected_root, "--max-cells", "7", expected_returncode=2)
    assert rejected == []


def test_live_wrapper_prints_usage_and_validates_missing_values(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    help_result = subprocess.run(
        [str(project / "scripts/run-live.sh"), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "Usage:" in help_result.stdout
    assert "--max-cells 1-6" in help_result.stdout
    assert "--resume RUN_DIRECTORY" in help_result.stdout

    missing = subprocess.run(
        [str(project / "scripts/run-live.sh"), "--max-cells"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "Missing value for --max-cells" in missing.stderr
    assert "Usage:" in missing.stderr


def test_live_wrapper_without_options_prints_help_without_starting(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [str(project / "scripts/run-live.sh")],
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": "/usr/bin:/bin", "TMUX": "", "TMUX_PANE": ""},
        check=False,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "With no options, this help is displayed." in result.stdout
    assert result.stderr == ""
