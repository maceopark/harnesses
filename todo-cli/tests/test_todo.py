"""Smoke suite for the todo CLI — covers REQ-001..009 of the build contract."""

import json

import pytest

import todo_cli
from todo_cli import main


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def store(tmp_path):
    return tmp_path / ".todo.json"


def read_store(tmp_path):
    return json.loads(store(tmp_path).read_text(encoding="utf-8"))


# REQ-001 + REQ-002: add persists an open item; list shows it with its id
def test_add_and_list(isolated_home, capsys):
    assert main(["add", "장보기"]) == 0
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "장보기" in out
    assert "1" in out
    item = read_store(isolated_home)["items"][0]
    assert item["id"] == 1
    assert item["status"] == "open"
    assert item["created_at"]  # REQ-007: timestamp present


# REQ-002: ascending id order, open items only
def test_list_ascending_id_and_open_only(isolated_home, capsys):
    main(["add", "first"])
    main(["add", "second"])
    main(["add", "third"])
    main(["done", "2"])
    capsys.readouterr()
    main(["list"])
    out = capsys.readouterr().out
    assert out.index("first") < out.index("third")
    assert "second" not in out


# REQ-003 + REQ-006: done hides the item from list but retains it in the file
def test_done_hides_but_retains(isolated_home, capsys):
    main(["add", "x"])
    assert main(["done", "1"]) == 0
    capsys.readouterr()
    main(["list"])
    assert "x" not in capsys.readouterr().out
    item = read_store(isolated_home)["items"][0]
    assert item["status"] == "done"
    assert item["completed_at"]  # REQ-007: completed timestamp


# REQ-004: unknown or already-done id fails, store unchanged
def test_done_unknown_id(isolated_home, capsys):
    main(["add", "x"])
    before = store(isolated_home).read_text()
    assert main(["done", "9"]) == 1
    assert "no task with id 9" in capsys.readouterr().err
    assert store(isolated_home).read_text() == before


def test_done_already_done(isolated_home, capsys):
    main(["add", "x"])
    main(["done", "1"])
    before = store(isolated_home).read_text()
    assert main(["done", "1"]) == 1
    assert "already done" in capsys.readouterr().err
    assert store(isolated_home).read_text() == before


# REQ-005: bare `todo` prints help, not the list
def test_bare_run_prints_help(isolated_home, capsys):
    main(["add", "secret task"])
    capsys.readouterr()
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    assert "secret task" not in out


# REQ-008: missing file = empty list; created on first write
def test_missing_file(isolated_home, capsys):
    assert not store(isolated_home).exists()
    assert main(["list"]) == 0
    assert "nothing to do" in capsys.readouterr().out
    assert not store(isolated_home).exists()  # list never creates the file
    main(["add", "x"])
    assert store(isolated_home).exists()


# REQ-009: unparseable JSON aborts, file untouched
def test_corrupt_json_aborts(isolated_home, capsys):
    store(isolated_home).write_text("{not json", encoding="utf-8")
    assert main(["list"]) == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert store(isolated_home).read_text(encoding="utf-8") == "{not json"
    assert main(["add", "x"]) == 1  # add must also refuse to overwrite
    assert store(isolated_home).read_text(encoding="utf-8") == "{not json"


# REQ-009: parseable-but-schema-invalid aborts, file untouched
@pytest.mark.parametrize(
    "bad",
    ['["not", "a", "dict"]', '{"items": {"wrong": "shape"}}', '{"items": [{"id": "1", "title": "x"}]}'],
)
def test_wrong_shape_aborts(isolated_home, capsys, bad):
    store(isolated_home).write_text(bad, encoding="utf-8")
    assert main(["list"]) == 1
    assert "refusing to touch it" in capsys.readouterr().err
    assert store(isolated_home).read_text(encoding="utf-8") == bad


# REQ-001: empty title rejected
def test_empty_title_rejected(isolated_home, capsys):
    assert main(["add", "   "]) == 1
    assert "empty" in capsys.readouterr().err
    assert not store(isolated_home).exists()


# ids never reused even after all open items are done (stable for future merge)
def test_ids_monotonic(isolated_home):
    main(["add", "a"])
    main(["done", "1"])
    main(["add", "b"])
    ids = [i["id"] for i in read_store(isolated_home)["items"]]
    assert ids == [1, 2]
