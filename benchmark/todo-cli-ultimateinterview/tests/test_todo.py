from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
from types import TracebackType
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from _pytest.tmpdir import TempPathFactory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
DECISION_LOG = WORKSPACE_ROOT / ".ultimateinterview/todo-cli-benchmark-new/decisions.jsonl"
STORE = ".todo.json"
NETWORK_IMPORTS = frozenset(
    {
        "aiohttp", "boto3", "ftplib", "http", "httpx", "imaplib", "nntplib", "poplib",
        "requests", "smtplib", "socket", "telnetlib", "urllib", "webbrowser", "websocket", "websockets", "xmlrpc",
    }
)
NETWORK_ENDPOINT_MARKER = "://"

REQUIREMENT_MATRIX: dict[str, tuple[str, str, str, str, str]] = {
    "REQ-001": ("argv", "stdout empty", "usage stderr", "2", "store untouched"),
    "REQ-002": ("stored active records", "ordered active stdout", "stderr empty", "0", "no date fields"),
    "REQ-003": ("valid title", "added stdout", "stderr empty", "0", "canonical record persisted"),
    "REQ-004": ("blank/control title", "stdout empty", "validation stderr", "1", "store untouched"),
    "REQ-005": ("absent/valid store", "active lines", "stderr empty", "0", "list never creates/writes"),
    "REQ-006": ("active ID", "done stdout", "stderr empty", "0", "retained completed record"),
    "REQ-007": ("completed/absent ID", "stdout empty", "transition stderr", "1/2", "store untouched"),
    "REQ-008": ("closed JSON v1", "cwd-isolated stdout", "schema stderr", "0/3", "strict local store"),
    "REQ-009": ("retained IDs", "added stdout", "stderr empty", "0", "max-plus-one persisted"),
    "REQ-010": ("bad paths/stages", "stdout empty", "storage stderr", "3", "original bytes unchanged"),
    "REQ-011": ("artifact checks", "verification output", "assertion failures", "0", "trace artifacts valid"),
}


def _run(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("todo")
    if executable.exists():
        command = [str(executable), *arguments]
    else:
        command = [sys.executable, "-m", "todo_cli", *arguments]
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _store_bytes(path: Path) -> bytes:
    return json.dumps(
        path,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"


def _write_store(cwd: Path, value: dict[str, list[dict[str, int | str | bool]] | int]) -> Path:
    store = cwd / STORE
    store.write_bytes(_store_bytes(value))
    return store


def _valid_store(*items: dict[str, int | str | bool]) -> dict[str, list[dict[str, int | str | bool]] | int]:
    return {"schema_version": 1, "items": list(items)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_storage_failure_unchanged(
    result: subprocess.CompletedProcess[str], path: Path, before: str, expected: str
) -> None:
    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr.startswith(f"error: .todo.json: {expected}")
    assert _sha256(path) == before


def test_req001_parser_rejects_unknown_and_never_reads_store(tmp_path: Path) -> None:
    # Given: an invalid store that must not be inspected.
    store = tmp_path / STORE
    store.write_text("not json", encoding="utf-8")

    # When: no command, an unknown command, and unsupported options run.
    for arguments in ((), ("priority",), ("list", "--priority", "high"), ("add", "--unknown")):
        result = _run(tmp_path, *arguments)

        # Then: argparse reports usage and the invalid store cannot affect the result.
        assert result.returncode == 2
        assert result.stdout == ""
        assert "usage:" in result.stderr
        assert store.read_text(encoding="utf-8") == "not json"


def test_req002_list_is_undated_sorted_and_omits_completed(tmp_path: Path) -> None:
    # Given: active records out of order and a completed record.
    _write_store(
        tmp_path,
        _valid_store(
            {"id": 3, "title": "third", "done": False},
            {"id": 1, "title": "first", "done": False},
            {"id": 2, "title": "hidden", "done": True},
        ),
    )

    # When: listing twice without a date boundary.
    first = _run(tmp_path, "list")
    second = _run(tmp_path, "list")

    # Then: only active records appear in stable ascending ID order.
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout == "1 first\n3 third\n"


def test_req003_add_trims_and_persists_canonical_record(tmp_path: Path) -> None:
    # Given: no store exists.
    store = tmp_path / STORE

    # When: a title with outer whitespace is added.
    result = _run(tmp_path, "add", "  write tests  ")

    # Then: the exact message, exit, and canonical JSON record are observable.
    assert result.returncode == 0
    assert result.stdout == "added #1: write tests\n"
    assert result.stderr == ""
    assert json.loads(store.read_text(encoding="utf-8")) == _valid_store(
        {"id": 1, "title": "write tests", "done": False}
    )


def test_req003_installed_cli_accepts_dash_prefixed_title_after_separator(tmp_path: Path) -> None:
    # Given: an empty cwd and a title beginning with a dash.
    store = tmp_path / STORE

    # When: the installed console command uses argparse's explicit option separator.
    result = _run(tmp_path, "add", "--", "--alpha")

    # Then: the dash-prefixed title is stored and reported exactly like any other valid title.
    assert result.returncode == 0
    assert result.stdout == "added #1: --alpha\n"
    assert result.stderr == ""
    assert json.loads(store.read_text(encoding="utf-8")) == _valid_store(
        {"id": 1, "title": "--alpha", "done": False}
    )


@pytest.mark.parametrize(
    ("title", "diagnostic"),
    [(" \t ", "error: title is empty\n"), ("bad\u0085title", "error: title contains U+0085\n")],
)
def test_req004_invalid_title_precedes_store_access(
    tmp_path: Path, title: str, diagnostic: str
) -> None:
    # Given: a malformed store that proves the title boundary has precedence.
    store = tmp_path / STORE
    store.write_text("{", encoding="utf-8")
    before = _sha256(store)

    # When: a title fails its input predicate.
    result = _run(tmp_path, "add", title)

    # Then: only the validation result is reported and bytes remain identical.
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == diagnostic
    assert _sha256(store) == before


def test_req005_absent_list_is_empty_and_does_not_create_store(tmp_path: Path) -> None:
    # Given: no store.
    store = tmp_path / STORE

    # When: list runs.
    result = _run(tmp_path, "list")

    # Then: it is a successful empty read and no file exists afterwards.
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert not store.exists()


def test_req006_done_retains_record_and_later_add_uses_next_id(tmp_path: Path) -> None:
    # Given: one active record.
    _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))

    # When: it is completed and another item is added.
    completed = _run(tmp_path, "done", "1")
    added = _run(tmp_path, "add", "second")

    # Then: the hidden completed record remains and the new ID is not reused.
    assert completed.returncode == 0
    assert completed.stdout == "done #1: first\n"
    assert completed.stderr == ""
    assert added.returncode == 0
    assert added.stdout == "added #2: second\n"
    assert added.stderr == ""
    assert json.loads((tmp_path / STORE).read_text(encoding="utf-8")) == _valid_store(
        {"id": 1, "title": "first", "done": True},
        {"id": 2, "title": "second", "done": False},
    )


@pytest.mark.parametrize(
    ("store_value", "identifier", "diagnostic"),
    [
        (_valid_store({"id": 1, "title": "finished", "done": True}), "1", "error: task 1 is already done (finished)\n"),
        (_valid_store(), "0", "error: no task with id 0\n"),
        (_valid_store(), "9", "error: no task with id 9\n"),
    ],
)
def test_req007_illegal_completion_never_writes(
    tmp_path: Path,
    store_value: dict[str, list[dict[str, int | str | bool]] | int],
    identifier: str,
    diagnostic: str,
) -> None:
    # Given: a readable valid store and its original bytes.
    store = _write_store(tmp_path, store_value)
    before = _sha256(store)

    # When: an illegal state transition is requested.
    result = _run(tmp_path, "done", identifier)

    # Then: a user diagnostic exits 1 and preserves the store.
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == diagnostic
    assert _sha256(store) == before


@pytest.mark.parametrize("identifier", ("x", "1.5"))
def test_req007_non_integer_completion_is_argparse_error(tmp_path: Path, identifier: str) -> None:
    # Given: an invalid store that parser errors must not load.
    store = tmp_path / STORE
    store.write_text("not json", encoding="utf-8")

    # When: a non-integer ID is supplied.
    result = _run(tmp_path, "done", identifier)

    # Then: usage wins with exit 2 and untouched bytes.
    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr
    assert store.read_text(encoding="utf-8") == "not json"


def test_req008_rejects_closed_schema_and_isolates_cwds(tmp_path_factory: TempPathFactory) -> None:
    # Given: one invalid schema and two independent working directories.
    invalid_cwd = tmp_path_factory.mktemp("invalid")
    _write_store(invalid_cwd, {"schema_version": 1, "items": [], "extra": True})
    first_cwd = tmp_path_factory.mktemp("first")
    second_cwd = tmp_path_factory.mktemp("second")

    # When: invalid storage is listed and only the first cwd receives an add.
    invalid = _run(invalid_cwd, "list")
    added = _run(first_cwd, "add", "local")
    other = _run(second_cwd, "list")

    # Then: exact-schema rejection and cwd isolation both hold.
    assert invalid.returncode == 3
    assert invalid.stdout == ""
    assert invalid.stderr.startswith("error: .todo.json: invalid schema:")
    assert added.returncode == 0
    assert other.returncode == 0
    assert other.stdout == other.stderr == ""
    assert not (second_cwd / STORE).exists()


def test_req009_allocator_uses_maximum_including_completed(tmp_path: Path) -> None:
    # Given: a completed maximum ID and a lower active ID.
    _write_store(
        tmp_path,
        _valid_store(
            {"id": 2, "title": "active", "done": False},
            {"id": 7, "title": "retained", "done": True},
        ),
    )

    # When: a task is added.
    result = _run(tmp_path, "add", "next")

    # Then: max-plus-one is persisted without ID reuse.
    assert result.returncode == 0
    assert result.stdout == "added #8: next\n"
    assert result.stderr == ""
    assert json.loads((tmp_path / STORE).read_text(encoding="utf-8"))["items"][-1] == {
        "id": 8,
        "title": "next",
        "done": False,
    }


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"{", "malformed JSON"),
        (b'\xff', "not valid UTF-8"),
        (b'{"schema_version":1,"schema_version":1,"items":[]}', "malformed JSON"),
        (b'{"schema_version":1,"items":[],"items":[]}', "malformed JSON"),
        (b'{"schema_version":true,"items":[]}', "invalid schema:"),
        (b'{"schema_version":1,"items":[{"id":1,"title":"bad\\u0000","done":false}]}', "invalid schema:"),
        (b'{"schema_version":1,"items":[{"id":1,"title":"\\ud800","done":false}]}', "invalid schema:"),
    ],
)
def test_req010_corrupt_load_fails_closed(
    tmp_path: Path, payload: bytes, expected: str
) -> None:
    # Given: a corrupt on-disk store.
    store = tmp_path / STORE
    store.write_bytes(payload)
    before = _sha256(store)

    # When: the list reader loads it.
    result = _run(tmp_path, "list")

    # Then: the storage class exits 3 and does not repair or overwrite it.
    _assert_storage_failure_unchanged(result, store, before, expected)


def test_req010_deeply_nested_json_fails_closed(tmp_path: Path) -> None:
    # Given: JSON nesting deep enough for the decoder to exceed its recursion limit.
    store = tmp_path / STORE
    store.write_bytes(b"[" * 3000 + b"]" * 3000)
    before = _sha256(store)

    # When: list loads the deeply nested content through the installed CLI.
    result = _run(tmp_path, "list")

    # Then: recursion is classified as malformed JSON and bytes remain unchanged.
    _assert_storage_failure_unchanged(result, store, before, "malformed JSON")


def test_req010_rejects_symlink_and_nonregular_paths(tmp_path: Path) -> None:
    # Given: a symlink target and a directory target.
    target = tmp_path / "target.json"
    target.write_text('{"schema_version":1,"items":[]}', encoding="utf-8")
    symlink_cwd = tmp_path / "symlink"
    symlink_cwd.mkdir()
    (symlink_cwd / STORE).symlink_to(target)
    directory_cwd = tmp_path / "directory"
    directory_cwd.mkdir()
    (directory_cwd / STORE).mkdir()

    # When: list reads either invalid file type.
    symlink = _run(symlink_cwd, "list")
    directory = _run(directory_cwd, "list")

    # Then: both fail closed, and the external target remains untouched.
    assert symlink.returncode == directory.returncode == 3
    assert symlink.stdout == directory.stdout == ""
    assert symlink.stderr == directory.stderr == "error: .todo.json: invalid file type\n"
    assert target.read_text(encoding="utf-8") == '{"schema_version":1,"items":[]}'


def test_req010_rejects_symlink_when_nofollow_is_unavailable(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    # Given: a valid external store and a runtime without O_NOFOLLOW in its open flags.
    import todo_cli

    external = tmp_path / "external.json"
    external.write_bytes(_store_bytes(_valid_store({"id": 1, "title": "external", "done": False})))
    (tmp_path / STORE).symlink_to(external)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(todo_cli, "READ_OPEN_FLAGS", os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))

    # When: list loads the symlink on the no-follow fallback path.
    exit_code = todo_cli.main(["list"])
    captured = capsys.readouterr()

    # Then: the external regular file is never followed or printed.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err == "error: .todo.json: invalid file type\n"


def test_req010_list_reads_valid_unwritable_store_without_write_preflight(tmp_path: Path) -> None:
    # Given: a read-only store and directory.
    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "read", "done": False}))
    store.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)

    # When: list performs a read-only operation.
    try:
        result = _run(tmp_path, "list")
    finally:
        tmp_path.chmod(stat.S_IRWXU)
        store.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # Then: it succeeds without a write permission preflight.
    assert result.returncode == 0
    assert result.stdout == "1 read\n"
    assert result.stderr == ""


@pytest.mark.parametrize("arguments", (("add", "second"), ("done", "1")))
def test_req010_no_write_mode_bits_block_mutation_but_not_list(
    tmp_path: Path, arguments: tuple[str, str]
) -> None:
    # Given: a readable valid regular store whose write-mode bits are all clear.
    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))
    original_mode = store.stat().st_mode
    store.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    before = _sha256(store)

    # When: list reads it and a legal mutation runs with its parent still writable.
    listed = _run(tmp_path, "list")
    try:
        mutation = _run(tmp_path, *arguments)
    finally:
        store.chmod(original_mode)

    # Then: list succeeds, while mutation fails closed without replacing the file.
    assert listed.returncode == 0
    assert listed.stdout == "1 first\n"
    assert listed.stderr == ""
    _assert_storage_failure_unchanged(mutation, store, before, "write failed:")


@pytest.mark.parametrize("stage", ("temp", "write", "flush", "fsync", "replace"))
def test_req010_atomic_write_stage_failures_preserve_original_bytes(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str], stage: str
) -> None:
    # Given: a valid existing record and one injected write-stage failure.
    import todo_cli

    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))
    before = _sha256(store)
    monkeypatch.chdir(tmp_path)

    def fail(*_args: str, **_kwargs: str) -> None:
        raise OSError("injected stage failure")

    class BrokenWriter:
        def __init__(self, fail_at: str) -> None:
            self.fail_at = fail_at

        def __enter__(self) -> BrokenWriter:
            return self

        def __exit__(
            self,
            _exception_type: type[BaseException] | None,
            _exception: BaseException | None,
            _traceback: TracebackType | None,
        ) -> bool:
            return False

        def write(self, payload: str) -> int:
            if self.fail_at == "write":
                raise OSError("injected stage failure")
            return len(payload)

        def flush(self) -> None:
            if self.fail_at == "flush":
                raise OSError("injected stage failure")

        def fileno(self) -> int:
            return 1

    match stage:
        case "temp":
            monkeypatch.setattr(todo_cli.tempfile, "mkstemp", fail)
        case "write":
            monkeypatch.setattr(todo_cli.os, "fdopen", lambda *_args, **_kwargs: BrokenWriter("write"))
        case "flush":
            monkeypatch.setattr(todo_cli.os, "fdopen", lambda *_args, **_kwargs: BrokenWriter("flush"))
        case "fsync":
            monkeypatch.setattr(todo_cli.os, "fsync", fail)
        case "replace":
            monkeypatch.setattr(todo_cli.os, "replace", fail)
        case unexpected:
            raise AssertionError(f"unhandled stage {unexpected}")

    # When: an add reaches the injected persistence stage.
    exit_code = todo_cli.main(["add", "second"])
    captured = capsys.readouterr()

    # Then: the stable write class exits 3 and the original target stays byte-identical.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.startswith("error: .todo.json: write failed: injected stage failure")
    assert _sha256(store) == before


def test_req010_read_failure_is_storage_error_without_mutation(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    # Given: a target whose byte content is known and an injected read failure.
    import todo_cli

    store = _write_store(tmp_path, _valid_store())
    before = _sha256(store)
    monkeypatch.chdir(tmp_path)

    def denied(_descriptor: int, _length: int) -> bytes:
        raise OSError("injected read failure")

    monkeypatch.setattr(todo_cli.os, "read", denied)

    # When: list attempts to load it.
    exit_code = todo_cli.main(["list"])
    captured = capsys.readouterr()

    # Then: it exits 3 and preserves the original content.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err == "error: .todo.json: read failed: injected read failure\n"
    monkeypatch.undo()
    assert _sha256(store) == before


def test_req010_fdopen_failure_closes_raw_descriptor_and_cleans_temp(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    # Given: mkstemp has created a raw descriptor and fdopen fails before it owns that descriptor.
    import todo_cli

    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))
    before = _sha256(store)
    descriptor: int | None = None
    closed_descriptors: list[int] = []
    real_mkstemp = todo_cli.tempfile.mkstemp
    real_close = todo_cli.os.close
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(todo_cli, "load_store", lambda: todo_cli.Store(items=()))

    def record_mkstemp(*args: str, **kwargs: str) -> tuple[int, str]:
        nonlocal descriptor
        descriptor, temporary_name = real_mkstemp(*args, **kwargs)
        return descriptor, temporary_name

    def fail_fdopen(_descriptor: int, _mode: str, *, encoding: str, newline: str) -> None:
        del _descriptor, _mode, encoding, newline
        raise OSError("injected fdopen failure")

    def record_close(raw_descriptor: int) -> None:
        closed_descriptors.append(raw_descriptor)
        real_close(raw_descriptor)

    monkeypatch.setattr(todo_cli.tempfile, "mkstemp", record_mkstemp)
    monkeypatch.setattr(todo_cli.os, "fdopen", fail_fdopen)
    monkeypatch.setattr(todo_cli.os, "close", record_close)

    # When: add reaches fdopen before a file object has taken ownership.
    exit_code = todo_cli.main(["add", "second"])
    captured = capsys.readouterr()

    # Then: the raw descriptor closes once, the temporary file is removed, and the store is unchanged.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err == "error: .todo.json: write failed: injected fdopen failure\n"
    assert descriptor is not None
    assert closed_descriptors == [descriptor]
    assert list(tmp_path.glob(".todo.json.*.tmp")) == []
    assert _sha256(store) == before
    monkeypatch.undo()
    with pytest.raises(OSError):
        todo_cli.os.fstat(descriptor)


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="platform lacks AF_UNIX")
def test_req010_installed_list_rejects_unix_socket_without_mutation(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    # Given: the current-directory store path is an AF_UNIX socket.
    store = tmp_path / STORE
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    monkeypatch.chdir(tmp_path)
    try:
        listener.bind(STORE)

        # When: the installed console command loads that nonregular path.
        result = _run(tmp_path, "list")

        # Then: it fails closed with the file-type class and leaves the socket path in place.
        assert result.returncode == 3
        assert result.stdout == ""
        assert result.stderr == "error: .todo.json: invalid file type\n"
        assert stat.S_ISSOCK(store.lstat().st_mode)
    finally:
        listener.close()


def test_req010_descriptor_load_rejects_symlink_swapped_before_open(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    # Given: a valid store, an external target, and an open seam that swaps the path.
    import todo_cli

    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))
    external = tmp_path / "external.json"
    external.write_bytes(b"external bytes must remain unread")
    external_before = external.read_bytes()
    real_open = todo_cli.os.open
    real_read = todo_cli.os.read
    read_calls = 0
    monkeypatch.chdir(tmp_path)

    def swap_then_open(path: str | Path, flags: int) -> int:
        store.unlink()
        store.symlink_to(external)
        return real_open(path, flags)

    def record_read(descriptor: int, length: int) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return real_read(descriptor, length)

    monkeypatch.setattr(todo_cli.os, "open", swap_then_open)
    monkeypatch.setattr(todo_cli.os, "read", record_read)

    # When: list crosses the swap point before its file descriptor is opened.
    exit_code = todo_cli.main(["list"])
    captured = capsys.readouterr()

    # Then: it fails closed without reading or replacing the external target.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err == "error: .todo.json: invalid file type\n"
    assert read_calls == 0
    assert store.is_symlink()
    assert store.read_bytes() == external_before
    assert external.read_bytes() == external_before


@pytest.mark.parametrize("arguments", (("add", "second"), ("done", "1")))
def test_req010_save_rejects_symlink_swapped_after_load(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str], arguments: tuple[str, str]
) -> None:
    # Given: a valid store whose path is exchanged for a symlink immediately after loading.
    import todo_cli

    store = _write_store(tmp_path, _valid_store({"id": 1, "title": "first", "done": False}))
    external = tmp_path / "external.json"
    external.write_bytes(b"external bytes must remain unchanged")
    external_before = external.read_bytes()
    real_load = todo_cli.load_store
    monkeypatch.chdir(tmp_path)

    def swap_after_load() -> todo_cli.Store:
        loaded = real_load()
        store.unlink()
        store.symlink_to(external)
        return loaded

    monkeypatch.setattr(todo_cli, "load_store", swap_after_load)

    # When: a legal mutation reaches save after the target path has been swapped.
    exit_code = todo_cli.main(list(arguments))
    captured = capsys.readouterr()

    # Then: save refuses the nonregular target and leaves the symlink's target intact.
    assert exit_code == 3
    assert captured.out == ""
    assert captured.err == "error: .todo.json: invalid file type\n"
    assert store.is_symlink()
    assert store.read_bytes() == external_before
    assert external.read_bytes() == external_before


def test_req004_lone_surrogate_rejects_before_store_access(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    # Given: a lone surrogate input and a malformed store that must stay unread.
    import todo_cli

    store = tmp_path / STORE
    store.write_text("{", encoding="utf-8")
    before = _sha256(store)
    monkeypatch.chdir(tmp_path)

    # When: add receives a title that cannot be encoded as UTF-8.
    exit_code = todo_cli.main(["add", "\ud800"])
    captured = capsys.readouterr()

    # Then: it uses the input-error class and never reaches malformed storage.
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "error: title contains U+D800\n"
    assert _sha256(store) == before


def test_req011_requirement_matrix_is_complete() -> None:
    # Given: the source-owned requirement matrix.
    expected = {f"REQ-{number:03d}" for number in range(1, 12)}

    # When: its IDs and observable columns are evaluated.
    rows = set(REQUIREMENT_MATRIX)

    # Then: no REQ can be represented by a tag alone or a missing observable class.
    assert rows == expected
    assert all(len(row) == 5 and all(part for part in row) for row in REQUIREMENT_MATRIX.values())


def test_req011_forbidden_operations_use_installed_cli_without_store_access(tmp_path: Path) -> None:
    # Given: a malformed store that would expose any accidental post-parse access.
    store = tmp_path / STORE
    store.write_text("not json", encoding="utf-8")
    before = _sha256(store)
    forbidden = (
        ("priority",),
        ("due",),
        ("tag",),
        ("search",),
        ("edit",),
        ("delete",),
        ("history",),
        ("list", "--priority", "high"),
        ("list", "--due", "today"),
        ("list", "--tag", "home"),
        ("add", "--priority"),
        ("add", "--due"),
        ("add", "--tag"),
    )

    # When: each prohibited surface is run through the installed command.
    results = [_run(tmp_path, *arguments) for arguments in forbidden]

    # Then: argparse owns every rejection and the store has not been inspected or changed.
    assert all(result.returncode == 2 for result in results)
    assert all(result.stdout == "" and "usage:" in result.stderr for result in results)
    assert _sha256(store) == before


def test_req011_static_scope_readme_and_decision_log_are_traceable() -> None:
    # Given: the fixture's runtime source, docs, and required decision log.
    source = (PROJECT_ROOT / "todo_cli.py").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    log_lines = DECISION_LOG.read_text(encoding="utf-8").splitlines()
    tree = ast.parse(source)

    # When: imports, documented contract terms, and decision rows are inspected.
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    decisions = [json.loads(line) for line in log_lines]

    # Then: no external runtime surface exists, docs name contract facts, and decisions are usable.
    assert not imported & NETWORK_IMPORTS
    assert NETWORK_ENDPOINT_MARKER not in source
    assert all(
        forbidden not in document
        for document in (source, readme)
        for forbidden in (".ultimateinterview/", "handoff.md", "build-contract.json")
    )
    for phrase in ("todo add TITLE", "todo list", "todo done ID", ".todo.json", "schema_version", "stdout", "stderr", "exit 3", "pytest"):
        assert phrase in readme
    assert decisions
    assert all(isinstance(row["decision"], str) and row["decision"] for row in decisions)
    assert all(isinstance(row["reason"], str) and row["reason"] for row in decisions)


def test_req011_network_static_denylist_covers_stdlib_clients_and_all_uri_schemes() -> None:
    # Given: network client imports and a non-HTTP endpoint form.
    required_imports = {"ftplib", "imaplib", "poplib", "smtplib", "telnetlib", "xmlrpc"}

    # When: the fixture's static policy constants are inspected.

    # Then: stdlib network clients are denied and any URI scheme marker is forbidden.
    assert required_imports <= NETWORK_IMPORTS
    assert NETWORK_ENDPOINT_MARKER == "://"


def test_req011_pytest_hook_only_selects_fixture_from_harness_cwd(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    # Given: direct hook calls from the harness root and an unrelated directory.
    import todo_cli

    harness_arguments = ["-q"]
    unrelated_arguments = ["-q"]

    # When: each context asks pytest to collect without an explicit test path.
    monkeypatch.chdir(WORKSPACE_ROOT)
    todo_cli.pytest_load_initial_conftests(None, None, harness_arguments)
    monkeypatch.chdir(tmp_path)
    todo_cli.pytest_load_initial_conftests(None, None, unrelated_arguments)

    # Then: only the root-cwd invocation receives this fixture's test directory.
    assert harness_arguments == ["-q", str(PROJECT_ROOT / "tests")]
    assert unrelated_arguments == ["-q"]


def test_req011_project_manifest_has_only_pytest_development_dependency() -> None:
    # Given: the fixture manifest.
    manifest = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # When: declared runtime and development dependency lines are checked.
    runtime_line = next(line for line in manifest.splitlines() if line.startswith("dependencies ="))

    # Then: runtime remains empty, pytest is the only development dependency, and the console entry exists.
    assert runtime_line == "dependencies = []"
    assert 'dev = ["pytest' in manifest
    assert 'todo = "todo_cli:main"' in manifest


def test_req011_no_unrelated_fixture_or_generated_artifacts_are_needed() -> None:
    # Given: project-local files after a test session.
    allowed = {"pyproject.toml", "todo_cli.py", "README.md", "tests/test_todo.py", "tests/verify_real_surface.py"}

    # When: ordinary source files are enumerated without virtual environments or caches.
    observed = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and not {".venv", "__pycache__", ".pytest_cache", "todo_cli_ultimateinterview.egg-info"} & set(path.parts)
        and path.name != "uv.lock"
    }

    # Then: every source artifact belongs to the fixture contract.
    assert observed <= allowed
