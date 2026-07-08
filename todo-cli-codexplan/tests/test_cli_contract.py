from __future__ import annotations

from typing import TYPE_CHECKING

from codexplan.cli import main
from codexplan.storage import load_store

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_missing_store_lists_empty_without_creating_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    result = main(["list"])

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == ""
    assert captured.err == ""
    assert not store_path.exists()


def test_add_list_done_rm_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    assert main(["add", "buy milk"]) == 0
    assert capsys.readouterr().out == "added 1\n"

    assert main(["list"]) == 0
    assert capsys.readouterr().out == "1\t[ ]\tbuy milk\n"

    assert main(["done", "1"]) == 0
    assert capsys.readouterr().out == "done 1\n"

    assert main(["list"]) == 0
    assert capsys.readouterr().out == "1\t[x]\tbuy milk\n"

    assert main(["done", "1"]) == 0
    assert capsys.readouterr().out == "already done 1\n"

    assert main(["rm", "1"]) == 0
    assert capsys.readouterr().out == "removed 1\n"

    assert main(["list"]) == 0
    assert capsys.readouterr().out == ""


def test_removed_ids_are_not_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    assert main(["add", "first"]) == 0
    assert main(["rm", "1"]) == 0
    assert main(["add", "second"]) == 0

    _ = capsys.readouterr()
    store = load_store(store_path)
    assert int(store.next_id) == 3
    assert int(store.tasks[0].id) == 2


def test_domain_errors_return_1_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    assert main(["add", "   "]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert not store_path.exists()

    assert main(["done", "999"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")


def test_signed_invalid_ids_are_domain_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    assert main(["done", "-1"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")

    assert main(["rm", "-1"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error:")


def test_usage_errors_return_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert capsys.readouterr().err.startswith("usage:")

    assert main(["add"]) == 2
    assert capsys.readouterr().err.startswith("usage:")

    assert main(["done", "not-an-int"]) == 2
    assert capsys.readouterr().err.startswith("usage:")
