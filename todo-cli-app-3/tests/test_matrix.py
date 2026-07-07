"""Operation x store-state matrix (REQ-001..010): every op against
{absent, empty, populated, corrupt} stores, plus the unknown-operation row.
"""

from __future__ import annotations

import hashlib

import pytest
from conftest import TODAY, populate, read_store, run, store_file

POPULATED = [
    {"title": "보고서 작성", "pri": "high"},
    {"title": "메일 회신"},
    {"title": "회의 준비", "pri": "low"},
]

OPS = [[], ["add", "테스트 항목"], ["done", "1"], ["rm", "1"], ["frobnicate"]]
CORRUPT_BODIES = ["{not json", "", '{"nope": 1}', '["wrong shape"]']


# --- store absent -------------------------------------------------------------


def test_view_absent_store_creates_empty(home):
    result = run(home)
    assert result.returncode == 0
    assert store_file(home).exists()
    assert read_store(home) == {"items": []}


def test_add_absent_store_creates_and_persists(home):
    result = run(home, "add", "보고서 작성")
    assert result.returncode == 0
    assert [i["title"] for i in read_store(home)["items"]] == ["보고서 작성"]


def test_done_rm_absent_store_rejects_number(home):
    for op in ("done", "rm"):
        result = run(home, op, "1")
        assert result.returncode == 1, op
        assert "에러" in result.stderr


def test_unknown_command_absent_store(home):
    result = run(home, "frobnicate")
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert not store_file(home).exists()


# --- store empty ---------------------------------------------------------------


def test_view_empty(home):
    populate(home, [])
    result = run(home)
    assert result.returncode == 0
    assert "오늘 할일 없음" in result.stdout


def test_done_empty_store_rejects(home):
    populate(home, [])
    result = run(home, "done", "1")
    assert result.returncode == 1
    assert read_store(home)["items"] == []


# --- store populated -----------------------------------------------------------


def test_view_populated(home):
    populate(home, POPULATED)
    result = run(home)
    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert "1. 보고서 작성" in lines[0]
    assert "2. 메일 회신" in lines[1]
    assert "3. 회의 준비" in lines[2]


def test_done_and_rm_populated(home):
    populate(home, POPULATED)
    assert run(home, "done", "1").returncode == 0
    assert read_store(home)["items"][0]["done_on"] == TODAY
    assert run(home, "rm", "1").returncode == 0
    titles = [i["title"] for i in read_store(home)["items"]]
    assert "메일 회신" not in titles  # position 1 after renumber was 메일 회신


def test_unknown_command_populated_store_unchanged(home):
    populate(home, POPULATED)
    before = store_file(home).read_bytes()
    result = run(home, "frobnicate")
    assert result.returncode == 2
    assert store_file(home).read_bytes() == before


# --- store corrupt (REQ-010): refuse, exit 1, file byte-identical ----------------


@pytest.mark.parametrize("body", CORRUPT_BODIES)
@pytest.mark.parametrize("op", OPS[:4], ids=["view", "add", "done", "rm"])
def test_corrupt_store_refuses_and_never_touches_file(home, body, op):
    path = store_file(home)
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = run(home, *op)
    assert result.returncode == 1
    assert "todos.json" in result.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_store_io_failure_exits_1(home):
    # ~/.todo existing as a regular file makes every store access an I/O failure
    (home / ".todo").write_text("i am a file, not a directory")
    result = run(home)
    assert result.returncode == 1
    assert "에러" in result.stderr
