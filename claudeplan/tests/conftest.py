from __future__ import annotations

import contextlib
import io
import json
from datetime import date

import pytest

from claudeplan import cli


@pytest.fixture(autouse=True)
def store_file(tmp_path, monkeypatch):
    """Point the CLI at a throwaway store so no test can touch the real home dir."""
    monkeypatch.setenv("CLAUDEPLAN_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path / "todos.json"


@pytest.fixture
def run_cli():
    """Invoke the CLI in-process; returns (exit_code, stdout, stderr)."""

    def _run(args: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = cli.main(args)
            except SystemExit as exc:  # argparse exits (usage errors, --help, --version)
                if exc.code is None:
                    code = 0
                elif isinstance(exc.code, int):
                    code = exc.code
                else:
                    code = 1
        return code, stdout.getvalue(), stderr.getvalue()

    return _run


@pytest.fixture
def read_store(store_file):
    def _read() -> dict:
        return json.loads(store_file.read_text(encoding="utf-8"))

    return _read


@pytest.fixture
def frozen_today(monkeypatch):
    today = date(2026, 7, 7)
    monkeypatch.setattr(cli, "_today", lambda: today)
    return today


def listed_ids(stdout: str) -> list[int]:
    """Extract todo ids from `list` output rows (header dropped)."""
    lines = stdout.strip().splitlines()[1:]
    return [int(line.split()[0]) for line in lines]
