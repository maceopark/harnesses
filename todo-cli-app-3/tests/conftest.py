"""Matrix tests interact ONLY via the real CLI subprocess + on-disk store inspection
(anti-gaming clause in the spec): no imports of todo_cli internals here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

TODO_BIN = shutil.which("todo")
TODAY = "2026-07-09"  # a Thursday; fixed via the TODO_TODAY seam
YESTERDAY = "2026-07-08"
TOMORROW = "2026-07-10"


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path


def run(home: Path, *args: str, today: str = TODAY) -> subprocess.CompletedProcess:
    assert TODO_BIN, "installed `todo` entry point not found on PATH (run under `uv run pytest`)"
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TODO_TODAY"] = today
    return subprocess.run([TODO_BIN, *args], env=env, capture_output=True, text=True, timeout=30)


def store_file(home: Path) -> Path:
    return home / ".todo" / "todos.json"


def read_store(home: Path) -> dict:
    return json.loads(store_file(home).read_text(encoding="utf-8"))


def populate(home: Path, items: list[dict]) -> None:
    path = store_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    full = []
    for index, item in enumerate(items, start=1):
        full.append(
            {
                "title": item["title"],
                "pri": item.get("pri", "mid"),
                "due": item.get("due"),
                "memo": item.get("memo"),
                "seq": item.get("seq", index),
                "done_on": item.get("done_on"),
            }
        )
    path.write_text(json.dumps({"items": full}, ensure_ascii=False), encoding="utf-8")
