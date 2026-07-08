import json
import shutil
import subprocess
from pathlib import Path

import pytest

from claudeplan import cli

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --- REQ-32: store path resolution ---------------------------------------

def test_req32_claudeplan_home_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDEPLAN_HOME", str(tmp_path / "cp"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert cli.store_path() == tmp_path / "cp" / "todos.json"


def test_req32_xdg_beats_home(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDEPLAN_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert cli.store_path() == tmp_path / "xdg" / "claudeplan" / "todos.json"


def test_req32_home_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDEPLAN_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.store_path() == tmp_path / ".config" / "claudeplan" / "todos.json"


def test_req32_parents_created_on_first_write(tmp_path, monkeypatch, run_cli):
    nested = tmp_path / "deep" / "nested"
    monkeypatch.setenv("CLAUDEPLAN_HOME", str(nested))
    code, _, _ = run_cli(["add", "x"])
    assert code == 0
    assert (nested / "todos.json").exists()


# --- REQ-33/34: corrupt and newer stores ----------------------------------

@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"version": 1, "todos": []}',
        '{"version": "one", "next_id": 1, "todos": []}',
    ],
)
def test_req33_corrupt_store_refused_by_every_command(run_cli, store_file, content):
    store_file.write_text(content, encoding="utf-8")
    before = store_file.read_bytes()
    for command in (["list"], ["add", "x"], ["done", "1"], ["delete", "1"]):
        code, out, err = run_cli(command)
        assert code == 1, command
        assert str(store_file) in err
        assert "Back up" in err
        assert out == ""
    assert store_file.read_bytes() == before


def test_req34_newer_store_version(run_cli, store_file):
    store_file.write_text(
        json.dumps({"version": 2, "next_id": 1, "todos": []}), encoding="utf-8"
    )
    before = store_file.read_bytes()
    code, _, err = run_cli(["list"])
    assert code == 1
    assert "newer version" in err
    assert store_file.read_bytes() == before


# --- REQ-35/36: store shape and atomic writes ------------------------------

def test_req35_store_shape_and_done_retention(run_cli, read_store):
    run_cli(["add", "x"])
    run_cli(["done", "1"])
    data = read_store()
    assert set(data) == {"version", "next_id", "todos"}
    assert data["version"] == 1
    assert len(data["todos"]) == 1
    assert data["todos"][0]["done"] is True


def test_req36_no_temp_files_left_behind(run_cli, store_file):
    run_cli(["add", "x"])
    run_cli(["done", "1"])
    leftovers = [p.name for p in store_file.parent.iterdir() if p.name != "todos.json"]
    assert leftovers == []


# --- REQ-37..39: CLI plumbing ----------------------------------------------

def test_req37_success_stdout_error_stderr(run_cli):
    _, out, err = run_cli(["add", "x"])
    assert out and not err
    _, out, err = run_cli(["done", "99"])
    assert err.startswith("Error: ") and not out


def test_req38_version(run_cli):
    code, out, _ = run_cli(["--version"])
    assert code == 0
    assert out.strip() == "claudeplan 0.1.0"


@pytest.mark.parametrize("args", [["--help"], ["add", "--help"], ["list", "--help"]])
def test_req38_help_exits_zero(run_cli, args):
    code, out, _ = run_cli(args)
    assert code == 0
    assert "usage" in out.lower()


def test_req39_bare_invocation_is_usage_error(run_cli):
    code, out, err = run_cli([])
    assert code == 2
    assert "usage" in err.lower()
    assert out == ""


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_entry_point_smoke():
    result = subprocess.run(
        ["uv", "run", "todo", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "claudeplan 0.1.0"
