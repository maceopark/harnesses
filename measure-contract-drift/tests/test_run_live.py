from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _fake_uv(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'for argument in "$@"; do printf "<%s>" "$argument" >> "$UV_LOG"; done\n'
        'printf "\\n" >> "$UV_LOG"\n', encoding="utf-8"
    )
    path.chmod(0o755)


def _run(tmp_path: Path, *arguments: str, expected: int = 0) -> list[str]:
    project = Path(__file__).resolve().parents[1]
    binary = tmp_path / "bin"
    binary.mkdir()
    _fake_uv(binary / "uv")
    log = tmp_path / "uv.log"
    result = subprocess.run(
        [str(project / "scripts/run-live.sh"), *arguments], text=True,
        capture_output=True, check=False,
        env={**os.environ, "PATH": f"{binary}:/usr/bin:/bin", "UV_LOG": str(log)},
    )
    assert result.returncode == expected, result.stderr
    return log.read_text().splitlines() if log.exists() else []


def test_live_wrapper_starts_bound_study(tmp_path: Path) -> None:
    calls = _run(tmp_path, "--max-generations", "2", "--max-candidates", "3")
    project = Path(__file__).resolve().parents[1]
    assert calls == [
        f"<run><--project><{project}><driftbench><interview-eval><run>"
        f"<--study><{project}/configs/evolution-study.json>"
        "<--max-generations><2><--max-candidates><3>"
    ]


def test_live_wrapper_resumes_by_run_directory(tmp_path: Path) -> None:
    calls = _run(tmp_path, "--resume", "/tmp/run with spaces", "--max-candidates", "4")
    project = Path(__file__).resolve().parents[1]
    assert calls == [
        f"<run><--project><{project}><driftbench><interview-eval><resume>"
        "<--run-dir></tmp/run with spaces><--max-candidates><4>"
    ]


def test_live_wrapper_forwards_smoke_mode(tmp_path: Path) -> None:
    calls = _run(tmp_path, "--smoke")
    assert "<--smoke>" in calls[0]


def test_live_wrapper_validates_bounds_before_uv(tmp_path: Path) -> None:
    assert _run(tmp_path, "--max-generations", "11", expected=2) == []
    other = tmp_path / "other"
    other.mkdir()
    assert _run(other, "--max-candidates", "9", expected=2) == []


def test_live_wrapper_help_and_missing_values(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    help_result = subprocess.run([str(project / "scripts/run-live.sh"), "--help"],
                                 text=True, capture_output=True, check=False)
    assert help_result.returncode == 0
    assert "--max-generations 1-10" in help_result.stdout
    assert "--max-candidates 1-8" in help_result.stdout
    missing = subprocess.run([str(project / "scripts/run-live.sh"), "--max-generations"],
                             text=True, capture_output=True, check=False)
    assert missing.returncode == 2
    assert "Missing value for --max-generations" in missing.stderr


def test_live_wrapper_without_options_only_prints_help(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([str(project / "scripts/run-live.sh")], text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0
    assert "With no options, this help is displayed." in result.stdout
