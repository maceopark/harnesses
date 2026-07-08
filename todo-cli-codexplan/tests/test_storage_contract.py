from __future__ import annotations

import json
from typing import TYPE_CHECKING

from codexplan.cli import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_corrupt_store_exits_3_and_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    _ = store_path.write_text("{ not json", encoding="utf-8")
    before = store_path.read_bytes()
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    result = main(["add", "x"])

    captured = capsys.readouterr()
    assert result == 3
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert store_path.read_bytes() == before


def test_schema_invalid_store_exits_3_and_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store_path = tmp_path / "todos.json"
    _ = store_path.write_text(
        json.dumps({"schema_version": 2, "next_id": 1, "tasks": []}),
        encoding="utf-8",
    )
    before = store_path.read_bytes()
    monkeypatch.setenv("CODEXPLAN_FILE", str(store_path))

    result = main(["list"])

    captured = capsys.readouterr()
    assert result == 3
    assert captured.out == ""
    assert captured.err.startswith("error:")
    assert store_path.read_bytes() == before
