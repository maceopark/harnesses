#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest>=8.0"]
# ///

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atomic_write
import pytest


@pytest.mark.parametrize("constant", ("O_NOFOLLOW", "O_DIRECTORY"))
def test_session_lock_requires_each_posix_nofollow_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
) -> None:
    # Given
    monkeypatch.delattr(atomic_write.os, constant)

    # When / Then
    with pytest.raises(
        atomic_write.SessionLockError,
        match="requires POSIX no-follow directory opens",
    ):
        with atomic_write.session_lock(tmp_path):
            pass


def test_multi_file_commit_rolls_back_when_replace_fails(tmp_path: Path) -> None:
    first = tmp_path / "ledger.json"
    second = tmp_path / "protocol.json"
    first.write_text("old-ledger\n", encoding="utf-8")
    second.write_text("old-protocol\n", encoding="utf-8")
    calls = 0

    def fail_second(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replacement failure")
        os.replace(source, target)

    try:
        atomic_write.commit_text_files(
            {first: "new-ledger\n", second: "new-protocol\n"},
            replace=fail_second,
        )
    except OSError as error:
        assert "injected" in str(error)
    else:
        raise AssertionError("replacement failure was not propagated")

    assert first.read_text(encoding="utf-8") == "old-ledger\n"
    assert second.read_text(encoding="utf-8") == "old-protocol\n"


def test_staging_failure_cleans_already_staged_files(tmp_path: Path) -> None:
    first = tmp_path / "ledger.json"
    second = tmp_path / "protocol.json"
    first.write_text("old-ledger\n", encoding="utf-8")
    second.write_text("old-protocol\n", encoding="utf-8")
    calls = 0

    def fail_second(path: Path, text: str) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected staging failure")
        return atomic_write.staged_file(path, text)

    with pytest.raises(OSError, match="staging"):
        atomic_write.commit_text_files(
            {first: "new-ledger\n", second: "new-protocol\n"},
            stage=fail_second,
        )

    assert first.read_text(encoding="utf-8") == "old-ledger\n"
    assert second.read_text(encoding="utf-8") == "old-protocol\n"
    assert not list(tmp_path.glob(".ledger.json.*"))


def test_recovery_restores_pretransaction_generation(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    protocol = tmp_path / "protocol.json"
    ledger.write_text("old-ledger\n", encoding="utf-8")
    protocol.write_text("old-protocol\n", encoding="utf-8")
    atomic_write.write_recovery_journal(
        {ledger: "old-ledger\n", protocol: "old-protocol\n"},
        root=tmp_path,
    )
    ledger.write_text("new-ledger\n", encoding="utf-8")

    atomic_write.recover_text_files(tmp_path)

    assert ledger.read_text(encoding="utf-8") == "old-ledger\n"
    assert protocol.read_text(encoding="utf-8") == "old-protocol\n"
    assert not (tmp_path / atomic_write.JOURNAL_NAME).exists()


def test_journal_creation_failure_removes_all_staged_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger.json"
    protocol = tmp_path / "protocol.json"
    ledger.write_text("old-ledger\n", encoding="utf-8")
    protocol.write_text("old-protocol\n", encoding="utf-8")

    def fail_journal(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("journal unavailable")

    monkeypatch.setattr(atomic_write, "write_recovery_journal", fail_journal)

    with pytest.raises(OSError, match="journal unavailable"):
        atomic_write.commit_text_files(
            {ledger: "new-ledger\n", protocol: "new-protocol\n"},
        )

    assert ledger.read_text(encoding="utf-8") == "old-ledger\n"
    assert protocol.read_text(encoding="utf-8") == "old-protocol\n"
    assert not list(tmp_path.glob(".ledger.json.*"))
    assert not list(tmp_path.glob(".protocol.json.*"))


def test_session_lock_serializes_writers(tmp_path: Path) -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_writer() -> None:
        with atomic_write.session_transaction(tmp_path):
            first_entered.set()
            release_first.wait(timeout=2)

    def second_writer() -> None:
        first_entered.wait(timeout=2)
        with atomic_write.session_transaction(tmp_path):
            second_entered.set()

    first = threading.Thread(target=first_writer)
    second = threading.Thread(target=second_writer)
    first.start()
    second.start()
    assert first_entered.wait(timeout=2)
    assert not second_entered.wait(timeout=0.05)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert second_entered.is_set()


def test_session_read_transaction_blocks_writer_without_creating_a_lock(
    tmp_path: Path,
) -> None:
    # Given: a reader enters an unlocked session before any writer creates its lock file.
    reader_entered = threading.Event()
    release_reader = threading.Event()
    writer_entered = threading.Event()

    def reader() -> None:
        with atomic_write.session_read_transaction(tmp_path):
            reader_entered.set()
            release_reader.wait(timeout=2)

    def writer() -> None:
        reader_entered.wait(timeout=2)
        with atomic_write.session_transaction(tmp_path):
            writer_entered.set()

    first = threading.Thread(target=reader)
    second = threading.Thread(target=writer)
    first.start()
    second.start()

    # When: the reader holds the shared directory lock.
    assert reader_entered.wait(timeout=2)
    assert not (tmp_path / atomic_write.LOCK_NAME).exists()
    assert not writer_entered.wait(timeout=0.05)
    release_reader.set()
    first.join(timeout=2)
    second.join(timeout=2)

    # Then: the writer proceeds only after the read completes.
    assert writer_entered.is_set()


def test_session_read_transaction_rejects_a_journal_created_before_shared_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a recovery journal appears after the first check but before the shared lock.
    ledger = tmp_path / "ledger.json"
    ledger.write_text("old-ledger\n", encoding="utf-8")
    original_lock = atomic_write.session_lock
    journal_added = False

    @contextmanager
    def lock_after_journal(directory: Path, *, write: bool = True) -> Iterator[None]:
        nonlocal journal_added
        if not write and not journal_added:
            journal_added = True
            atomic_write.write_recovery_journal(
                {ledger: "old-ledger\n"},
                root=directory,
            )
            ledger.write_text("incomplete-ledger\n", encoding="utf-8")
        with original_lock(directory, write=write):
            yield

    monkeypatch.setattr(atomic_write, "session_lock", lock_after_journal)

    # When: the read transaction begins.
    with pytest.raises(atomic_write.PendingRecoveryError, match="pending recovery"):
        with atomic_write.session_read_transaction(tmp_path):
            pass

    # Then: it fails closed and leaves recovery for a writer.
    assert journal_added
    assert ledger.read_text(encoding="utf-8") == "incomplete-ledger\n"
    assert (tmp_path / atomic_write.JOURNAL_NAME).exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
