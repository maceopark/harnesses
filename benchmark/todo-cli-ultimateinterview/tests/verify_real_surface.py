from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run_todo(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("todo")
    return subprocess.run([str(executable), *arguments], cwd=cwd, text=True, capture_output=True, check=False)


def assert_result(result: subprocess.CompletedProcess[str], stdout: str) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout == stdout
    assert result.stderr == ""


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        first = Path(temporary) / "first"
        second = Path(temporary) / "second"
        first.mkdir()
        second.mkdir()

        assert_result(run_todo(first, "add", "  first  "), "added #1: first\n")
        assert_result(run_todo(first, "add", "second"), "added #2: second\n")
        assert_result(run_todo(first, "list"), "1 first\n2 second\n")
        assert_result(run_todo(first, "done", "1"), "done #1: first\n")
        assert_result(run_todo(first, "list"), "2 second\n")
        assert_result(run_todo(second, "list"), "")
        assert not (second / ".todo.json").exists()

        store = json.loads((first / ".todo.json").read_text(encoding="utf-8"))
        assert store == {
            "schema_version": 1,
            "items": [
                {"id": 1, "title": "first", "done": True},
                {"id": 2, "title": "second", "done": False},
            ],
        }
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
