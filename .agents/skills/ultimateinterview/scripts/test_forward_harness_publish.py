#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from scripts import forward_harness, forward_harness_publish, session_status

CORPUS = Path(__file__).parent / "forward_fixtures" / "v2"
RUNNER = CliRunner()


def status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def corpus_bytes(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_status_reading_forward_source_preserves_reviewed_corpus(
    tmp_path: Path,
) -> None:
    # Given: the ready fixture's source is part of the sealed corpus.
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    before = corpus_bytes(corpus)

    # When: the read-only status command inspects that source session.
    result = RUNNER.invoke(status_app(), ["--format", "json", str(corpus / "source")])

    # Then: it leaves every reviewed member untouched and the ready fixture remains valid.
    assert result.exit_code == 0, result.output
    assert corpus_bytes(corpus) == before
    assert forward_harness.evaluate_fixture(corpus / "ready").verdicts.trace == "pass"


def test_regeneration_rolls_back_when_second_generated_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a regenerated corpus and a deterministic failure on its second
    # generated target publication.
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    first_target = corpus / "atom-narrowing" / "expected.json"
    _ = first_target.write_text(
        first_target.read_text(encoding="utf-8").replace(
            '"trace": "fail"', '"trace": "pass"'
        ),
        encoding="utf-8",
    )
    before = corpus_bytes(corpus)
    targets = tuple(
        sorted(path for path in corpus.rglob("expected.json") if path.is_file())
    ) + (corpus / "corpus-manifest.json",)
    identities = {
        path.relative_to(corpus): (path.stat().st_dev, path.stat().st_ino)
        for path in targets
    }
    write = forward_harness_publish.write_snapshot_target
    writes = 0

    def fail_second_generated_publish(
        path: Path,
        content: bytes,
        snapshot: forward_harness_publish.CorpusFileSnapshot,
    ) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise forward_harness.ForwardHarnessError("injected publish failure")
        write(path, content, snapshot)

    monkeypatch.setattr(
        forward_harness_publish,
        "write_snapshot_target",
        fail_second_generated_publish,
    )

    # When / Then: every generated target must retain its original bytes.
    with pytest.raises(forward_harness.ForwardHarnessError, match="injected publish"):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert writes == 2
    assert corpus_bytes(corpus) == before
    assert {
        path.relative_to(corpus): (path.stat().st_dev, path.stat().st_ino)
        for path in targets
    } == identities


def test_regeneration_rolls_back_target_when_publisher_raises_after_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a generated target whose reviewed bytes differ from the staged output
    # and a publisher that raises only after changing that target.
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    target = corpus / "atom-narrowing" / "expected.json"
    _ = target.write_text(
        target.read_text(encoding="utf-8").replace(
            '"trace": "fail"', '"trace": "pass"'
        ),
        encoding="utf-8",
    )
    before = corpus_bytes(corpus)
    targets = tuple(
        sorted(path for path in corpus.rglob("expected.json") if path.is_file())
    ) + (corpus / "corpus-manifest.json",)
    identities = {
        path.relative_to(corpus): (path.stat().st_dev, path.stat().st_ino)
        for path in targets
    }
    write = forward_harness_publish.write_snapshot_target

    def write_target_then_raise(
        path: Path,
        content: bytes,
        snapshot: forward_harness_publish.CorpusFileSnapshot,
    ) -> None:
        write(path, content, snapshot)
        if path == target:
            raise forward_harness.ForwardHarnessError("injected post-write failure")

    monkeypatch.setattr(
        forward_harness_publish,
        "write_snapshot_target",
        write_target_then_raise,
    )

    # When / Then: the failed write is itself rolled back, including identity.
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="injected post-write failure"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert corpus_bytes(corpus) == before
    assert {
        path.relative_to(corpus): (path.stat().st_dev, path.stat().st_ino)
        for path in targets
    } == identities


def test_regeneration_rejects_a_published_expected_mutated_by_a_later_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an earlier expected output and a later publisher write that corrupts it.
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    before = corpus_bytes(corpus)
    manifest_path = corpus / "corpus-manifest.json"
    manifest_identity = (manifest_path.stat().st_dev, manifest_path.stat().st_ino)
    earlier_target = corpus / "atom-narrowing" / "expected.json"
    later_target = corpus / "ready" / "expected.json"
    write = forward_harness_publish.write_snapshot_target
    corrupted = b'{"concurrently":"corrupted"}\n'
    mutated = False

    def mutate_earlier_output_after_later_write(
        path: Path,
        content: bytes,
        snapshot: forward_harness_publish.CorpusFileSnapshot,
    ) -> None:
        nonlocal mutated
        write(path, content, snapshot)
        if path == later_target:
            _ = earlier_target.write_bytes(corrupted)
            mutated = True

    monkeypatch.setattr(
        forward_harness_publish,
        "write_snapshot_target",
        mutate_earlier_output_after_later_write,
    )

    # When / Then: publication must not report success, and must leave the
    # concurrent write visible instead of concealing it with a stale rollback.
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="published generated output"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert mutated
    assert earlier_target.read_bytes() == corrupted
    assert manifest_path.read_bytes() == before[Path("corpus-manifest.json")]
    assert (manifest_path.stat().st_dev, manifest_path.stat().st_ino) == manifest_identity
    assert {
        path: content
        for path, content in corpus_bytes(corpus).items()
        if path.name not in {"expected.json", "corpus-manifest.json"}
    } == {
        path: content
        for path, content in before.items()
        if path.name not in {"expected.json", "corpus-manifest.json"}
    }
