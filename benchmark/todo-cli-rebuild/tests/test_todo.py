"""Behavior-contract tests (REQ-001..REQ-008) run against the real CLI surface.

Every test invokes the actual entry point in a subprocess with an isolated
HOME, per the spec's isolation constraint — no in-process shortcuts.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent / "todo_rebuild.py"
STRIKE = "\x1b[9m"


def run(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
    )


def store(home: Path) -> Path:
    return home / ".todo-rebuild" / "todos.json"


def read_items(home: Path) -> list[dict]:
    return json.loads(store(home).read_text(encoding="utf-8"))["items"]


def write_items(home: Path, items: list[dict]) -> None:
    store(home).parent.mkdir(parents=True, exist_ok=True)
    store(home).write_text(json.dumps({"items": items}), encoding="utf-8")


# REQ-001 / matrix: view on absent store
def test_view_absent_store_is_empty_and_creates_nothing(tmp_path):
    result = run(tmp_path, )
    assert result.returncode == 0
    assert "nothing for today" in result.stdout
    assert not store(tmp_path).exists()


# REQ-004 / matrix: add on absent store creates it; title verbatim
def test_add_persists_title_verbatim(tmp_path):
    result = run(tmp_path, "add", "buy milk")
    assert result.returncode == 0
    items = read_items(tmp_path)
    assert items == [{"title": "buy milk", "created": items[0]["created"], "done_at": None}]
    view = run(tmp_path)
    assert "1. buy milk" in view.stdout


def test_add_long_title_not_truncated(tmp_path):
    title = "x" * 10_000
    assert run(tmp_path, "add", title).returncode == 0
    assert read_items(tmp_path)[0]["title"] == title


def test_add_multiline_title_round_trips(tmp_path):
    title = "line1\nline2\tend"
    assert run(tmp_path, "add", title).returncode == 0
    assert read_items(tmp_path)[0]["title"] == title


def test_duplicate_titles_allowed(tmp_path):
    run(tmp_path, "add", "buy milk")
    run(tmp_path, "add", "buy milk")
    view = run(tmp_path)
    assert "1. buy milk" in view.stdout
    assert "2. buy milk" in view.stdout


# REQ-005: empty/whitespace add rejected, store untouched
def test_empty_add_rejected_no_file_created(tmp_path):
    for bad in ([], [""], ["   "], ["\t"]):
        result = run(tmp_path, "add", *bad)
        assert result.returncode == 2
        assert "empty" in result.stderr
    assert not store(tmp_path).exists()


def test_empty_add_leaves_existing_store_byte_identical(tmp_path):
    run(tmp_path, "add", "keep me")
    before = store(tmp_path).read_bytes()
    assert run(tmp_path, "add", "  ").returncode == 2
    assert store(tmp_path).read_bytes() == before


# REQ-006: complete by number -> persisted done record, strike-through, contiguous numbering
def test_complete_by_number(tmp_path):
    for title in ("first", "second", "third"):
        run(tmp_path, "add", title)
    result = run(tmp_path, "done", "2")
    assert result.returncode == 0
    items = read_items(tmp_path)
    assert items[1]["done_at"] is not None
    view = run(tmp_path)
    assert f"{STRIKE}second" in view.stdout
    assert "1. first" in view.stdout
    assert "2. third" in view.stdout  # renumbered contiguously
    assert "3." not in view.stdout


# REQ-002: carryover — older creation dates still listed
def test_carryover_from_earlier_day(tmp_path):
    run(tmp_path, "add", "old task")
    items = read_items(tmp_path)
    items[0]["created"] = "2000-01-01"
    write_items(tmp_path, items)
    view = run(tmp_path)
    assert view.returncode == 0
    assert "1. old task" in view.stdout


# REQ-003: completed on a previous day -> hidden but retained
def test_previous_day_completion_hidden_but_retained(tmp_path):
    run(tmp_path, "add", "yesterday task")
    run(tmp_path, "done", "1")
    items = read_items(tmp_path)
    items[0]["done_at"] = "2000-01-01T09:00:00"
    write_items(tmp_path, items)
    view = run(tmp_path)
    assert "yesterday task" not in view.stdout
    assert read_items(tmp_path)[0]["title"] == "yesterday task"  # still in store


# REQ-008: hand-edit is the sanctioned recovery path
def test_hand_edit_uncomplete_restores_pending(tmp_path):
    run(tmp_path, "add", "oops")
    run(tmp_path, "done", "1")
    items = read_items(tmp_path)
    items[0]["done_at"] = None
    write_items(tmp_path, items)
    view = run(tmp_path)
    assert "1. oops" in view.stdout


# matrix: invalid complete targets on valid store
def test_invalid_index_rejected_store_unchanged(tmp_path):
    run(tmp_path, "add", "only one")
    before = store(tmp_path).read_bytes()
    for bad in ("99", "0", "-1", "abc"):
        result = run(tmp_path, "done", bad)
        assert result.returncode == 2
        assert result.stderr
    assert store(tmp_path).read_bytes() == before


def test_done_on_absent_store_errors_cleanly(tmp_path):
    result = run(tmp_path, "done", "1")
    assert result.returncode == 2
    assert not store(tmp_path).exists()


# REQ-007: corrupt store -> error names path, exits non-zero, bytes unmodified
def test_corrupt_store_never_modified(tmp_path):
    corruptions = [b"{not json", b'{"items": "nope"}', b'{"items": [{"title": 3}]}']
    for corrupt in corruptions:
        store(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        store(tmp_path).write_bytes(corrupt)
        for op in ((), ("add", "x"), ("done", "1")):
            result = run(tmp_path, *op)
            assert result.returncode == 1
            assert str(store(tmp_path)) in result.stderr
            assert store(tmp_path).read_bytes() == corrupt


def test_unknown_command_usage_error(tmp_path):
    result = run(tmp_path, "frobnicate")
    assert result.returncode == 2
    assert "usage" in result.stderr
