from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _fake_uv(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'for argument in "$@"; do printf "<%s>" "$argument" >> "$UV_LOG"; done\n'
        'printf "\\n" >> "$UV_LOG"\n', encoding="utf-8")
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


def test_wrapper_runs_one_discovery_generation(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    assert _run(tmp_path, "--one-generation") == [
        f"<run><--project><{project}><driftbench><discovery><run>"
        f"<--manifest><{project}/discovery-study.json><--one-generation>"
    ]


def test_wrapper_resumes_and_forwards_safe_limits(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    assert _run(tmp_path, "--resume", "/tmp/run path", "--one-generation",
                "--max-candidates", "2", "--max-parallel", "3") == [
        f"<run><--project><{project}><driftbench><discovery><resume>"
        "<--run-dir></tmp/run path>"
        f"<--manifest><{project}/discovery-study.json><--one-generation>"
        "<--max-candidates><2><--max-parallel><3>"
    ]


def test_wrapper_evolves_exactly_one_generation(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    assert _run(tmp_path, "--evolve", "/tmp/g00 run", "--one-generation") == [
        f"<run><--project><{project}><driftbench><discovery><evolve>"
        "<--parent-run></tmp/g00 run>"
        f"<--manifest><{project}/discovery-study.json><--one-generation>"
    ]


def test_wrapper_rejects_missing_generation_and_bad_limits(tmp_path: Path) -> None:
    assert _run(tmp_path, expected=2) == []
    other = tmp_path / "other"
    other.mkdir()
    assert _run(other, "--one-generation", "--max-parallel", "5", expected=2) == []
    third = tmp_path / "third"
    third.mkdir()
    assert _run(third, "--resume", "a", "--evolve", "b", "--one-generation",
                expected=2) == []
