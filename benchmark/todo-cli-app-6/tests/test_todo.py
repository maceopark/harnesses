from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORE = ".todo.json"


def _run(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("todo")
    return subprocess.run(
        [str(executable), *arguments], cwd=cwd, text=True, capture_output=True, check=False
    )


def _value(*items: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "items": list(items)}


def _bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _write(cwd: Path, value: dict[str, Any]) -> Path:
    path = cwd / STORE
    path.write_bytes(_bytes(value))
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_req001_commands_outputs_titles_and_ids(tmp_path: Path) -> None:
    first = _run(tmp_path, "add", "  같은 일  ")
    second = _run(tmp_path, "add", "같은 일")
    assert (first.returncode, first.stdout, first.stderr) == (0, "added #1: 같은 일\n", "")
    assert (second.returncode, second.stdout, second.stderr) == (0, "added #2: 같은 일\n", "")

    done = _run(tmp_path, "done", "1")
    third = _run(tmp_path, "add", "third")
    listed = _run(tmp_path, "list")
    assert (done.returncode, done.stdout, done.stderr) == (0, "done #1: 같은 일\n", "")
    assert third.stdout == "added #3: third\n"
    assert listed.stdout == "2 같은 일\n3 third\n"
    assert listed.stderr == ""

    before = _digest(tmp_path / STORE)
    for arguments in (("add", "   "), ("add", "bad\nname"), ("add", "--", "-dash")):
        result = _run(tmp_path, *arguments)
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr.startswith("error: ")
        assert _digest(tmp_path / STORE) == before

    unsupported = _run(tmp_path, "delete", "1")
    assert unsupported.returncode == 2
    assert "usage:" in unsupported.stderr
    assert _digest(tmp_path / STORE) == before


def test_req001_list_sorts_active_ids_and_empty_is_silent(tmp_path: Path) -> None:
    _write(
        tmp_path,
        _value(
            {"id": 3, "title": "third", "done": False},
            {"id": 2, "title": "second", "done": True},
            {"id": 1, "title": "first", "done": False},
        ),
    )
    result = _run(tmp_path, "list")
    assert (result.returncode, result.stdout, result.stderr) == (0, "1 first\n3 third\n", "")

    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run(empty, "list")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (empty / STORE).exists()


def test_req002_completion_and_missing_store_semantics(tmp_path: Path) -> None:
    missing = _run(tmp_path, "done", "1")
    assert missing.returncode == 1
    assert missing.stderr.startswith("error: ")
    assert not (tmp_path / STORE).exists()

    _write(tmp_path, _value({"id": 1, "title": "first", "done": False}))
    completed = _run(tmp_path, "done", "1")
    assert completed.stdout == "done #1: first\n"
    assert json.loads((tmp_path / STORE).read_text())["items"][0] == {
        "id": 1,
        "title": "first",
        "done": True,
    }
    assert _run(tmp_path, "list").stdout == ""

    before = _digest(tmp_path / STORE)
    for identifier in ("1", "2"):
        result = _run(tmp_path, "done", identifier)
        assert result.returncode == 1
        assert result.stderr.startswith("error: ")
        assert _digest(tmp_path / STORE) == before


def test_req002_invalid_ids_precede_store_access(tmp_path: Path) -> None:
    store = tmp_path / STORE
    store.write_text("not json", encoding="utf-8")
    before = _digest(store)
    for identifier in ("0", "-1"):
        result = _run(tmp_path, "done", identifier)
        assert result.returncode == 1
        assert result.stderr == "error: id must be a positive integer\n"
        assert _digest(store) == before
    for identifier in ("x", "1.5"):
        result = _run(tmp_path, "done", identifier)
        assert result.returncode == 2
        assert "usage:" in result.stderr
        assert _digest(store) == before


def test_req002_read_only_list_has_no_write_preflight(tmp_path: Path) -> None:
    store = _write(tmp_path, _value({"id": 1, "title": "read", "done": False}))
    store.chmod(0o400)
    try:
        result = _run(tmp_path, "list")
    finally:
        store.chmod(0o600)
    assert (result.returncode, result.stdout, result.stderr) == (0, "1 read\n", "")


def test_req003_closed_schema_and_exact_json_bytes(tmp_path: Path) -> None:
    result = _run(tmp_path, "add", "한글")
    assert result.returncode == 0
    assert (tmp_path / STORE).read_bytes() == (
        b'{\n  "schema_version": 1,\n  "items": [\n    {\n      "id": 1,\n'
        + '      "title": "한글",\n'.encode()
        + b'      "done": false\n    }\n  ]\n}\n'
    )

    invalid_values = [
        {"schema_version": 1, "items": [], "extra": True},
        {"schema_version": 2, "items": []},
        _value({"id": 0, "title": "bad", "done": False}),
        _value({"id": 1, "title": " bad ", "done": False}),
        _value({"id": 1, "title": "ok", "done": 0}),
        _value(
            {"id": 1, "title": "one", "done": False},
            {"id": 1, "title": "two", "done": False},
        ),
    ]
    for index, value in enumerate(invalid_values):
        cwd = tmp_path / str(index)
        cwd.mkdir()
        store = _write(cwd, value)
        before = _digest(store)
        failure = _run(cwd, "list")
        assert failure.returncode == 3
        assert failure.stderr.startswith("error: .todo.json: ")
        assert _digest(store) == before


def test_req004_result_classes_corruption_and_path_types(tmp_path: Path) -> None:
    domain = _run(tmp_path, "add", " ")
    usage = _run(tmp_path, "unknown")
    assert (domain.returncode, domain.stdout) == (1, "")
    assert domain.stderr.startswith("error: ")
    assert usage.returncode == 2 and "usage:" in usage.stderr

    invalid_utf8 = tmp_path / STORE
    invalid_utf8.write_bytes(b"\xff")
    before = _digest(invalid_utf8)
    storage = _run(tmp_path, "list")
    assert storage.returncode == 3
    assert storage.stdout == ""
    assert storage.stderr.startswith("error: .todo.json: ")
    assert _digest(invalid_utf8) == before

    invalid_utf8.unlink()
    target = tmp_path / "target.json"
    target.write_bytes(_bytes(_value()))
    (tmp_path / STORE).symlink_to(target)
    link_result = _run(tmp_path, "list")
    assert link_result.returncode == 3
    assert "invalid file type" in link_result.stderr
    assert target.read_bytes() == _bytes(_value())

    (tmp_path / STORE).unlink()
    (tmp_path / STORE).mkdir()
    directory_result = _run(tmp_path, "list")
    assert directory_result.returncode == 3
    assert "invalid file type" in directory_result.stderr


class _FailingFile:
    def __init__(self, wrapped: Any, stage: str) -> None:
        self.wrapped = wrapped
        self.stage = stage

    def __enter__(self) -> "_FailingFile":
        self.wrapped.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self.wrapped.__exit__(*args)

    def write(self, value: str) -> int:
        if self.stage == "write":
            raise OSError("injected write")
        return self.wrapped.write(value)

    def flush(self) -> None:
        if self.stage == "flush":
            raise OSError("injected flush")
        self.wrapped.flush()

    def fileno(self) -> int:
        return self.wrapped.fileno()


@pytest.mark.parametrize("stage", ("temp", "write", "flush", "fsync", "replace"))
def test_req004_storage_stage_failures_preserve_and_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], stage: str
) -> None:
    import todo_cli

    monkeypatch.chdir(tmp_path)
    store = _write(tmp_path, _value({"id": 1, "title": "first", "done": False}))
    before = store.read_bytes()

    if stage == "temp":
        monkeypatch.setattr(todo_cli.tempfile, "mkstemp", lambda **_: (_ for _ in ()).throw(OSError("injected temp")))
    elif stage in {"write", "flush"}:
        original_fdopen = todo_cli.os.fdopen
        monkeypatch.setattr(
            todo_cli.os,
            "fdopen",
            lambda *args, **kwargs: _FailingFile(original_fdopen(*args, **kwargs), stage),
        )
    elif stage == "fsync":
        monkeypatch.setattr(todo_cli.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("injected fsync")))
    else:
        monkeypatch.setattr(todo_cli.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("injected replace")))

    assert todo_cli.main(["add", "second"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: .todo.json: write failed: ")
    assert store.read_bytes() == before
    assert list(tmp_path.glob(".todo.json.*.tmp")) == []


def test_req004_success_invokes_fsync_and_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import todo_cli

    monkeypatch.chdir(tmp_path)
    calls: list[str] = []
    real_fsync = todo_cli.os.fsync
    real_replace = todo_cli.os.replace
    monkeypatch.setattr(todo_cli.os, "fsync", lambda fd: (calls.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(
        todo_cli.os,
        "replace",
        lambda source, target: (calls.append("replace"), real_replace(source, target))[1],
    )
    assert todo_cli.main(["add", "first"]) == 0
    assert capsys.readouterr().out == "added #1: first\n"
    assert calls == ["fsync", "replace"]


def test_req005_local_offline_surface() -> None:
    source = (PROJECT_ROOT / "todo_cli.py").read_text(encoding="utf-8")
    forbidden = (
        "urllib", "http.client", "socket", "requests", "ftplib", "imaplib", "poplib",
        "smtplib", "telnetlib", "xmlrpc", "://", "password", "credential", "login",
    )
    assert all(marker not in source for marker in forbidden)
    assert set(("add", "list", "done")) <= set(source.split('"'))


def test_req006_compatibility_and_dependencies() -> None:
    manifest = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    source = (PROJECT_ROOT / "todo_cli.py").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in manifest
    assert "dependencies = []" in manifest
    assert 'dev = ["pytest>=8"]' in manifest
    assert "requests" not in source and "typer" not in source and "click" not in source


def test_req007_exact_authored_files_and_entrypoint() -> None:
    observed = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and not any(
            part in {"__pycache__", ".pytest_cache", ".venv"} or part.endswith(".egg-info")
            for part in path.parts
        )
        and not path.name.endswith((".pyc", ".pyo"))
    }
    assert observed == {"pyproject.toml", "todo_cli.py", "README.md", "uv.lock", "tests/test_todo.py"}
    assert 'todo = "todo_cli:main"' in (PROJECT_ROOT / "pyproject.toml").read_text()


def test_req008_selected_algorithm_is_present() -> None:
    source = (PROJECT_ROOT / "todo_cli.py").read_text(encoding="utf-8")
    for marker in (
        "import argparse", "import json", "import os", "from pathlib import Path",
        "import tempfile", "os.open", "os.fstat", "tempfile.mkstemp", ".flush()",
        "os.fsync", "os.replace", "ensure_ascii=False", "indent=2",
    ):
        assert marker in source


def test_req009_verification_lanes_are_present() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "_run(" in source
    for stage in ("temp", "write", "flush", "fsync", "replace"):
        assert f'"{stage}"' in source
