#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts import assurance_schema, forward_harness, forward_harness_publish

CORPUS = Path(__file__).parent / "forward_fixtures" / "v2"


def corpus_bytes(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def trace_mutated_expected(expected_path: Path) -> str:
    expected = forward_harness.ForwardResult.model_validate_json(
        expected_path.read_text(encoding="utf-8")
    )
    return expected.model_copy(
        update={
            "verdicts": forward_harness.ForwardVerdicts(
                abi=expected.verdicts.abi,
                trace=assurance_schema.TraceVerdict.FAIL
                if expected.verdicts.trace is assurance_schema.TraceVerdict.PASS
                else assurance_schema.TraceVerdict.PASS,
                property=expected.verdicts.property,
                adequacy=expected.verdicts.adequacy,
                stakeholder=expected.verdicts.stakeholder,
            )
        }
    ).model_dump_json()


def mutate_source_member(corpus: Path) -> None:
    source = corpus / "source" / "ledger.json"
    _ = source.write_bytes(source.read_bytes() + b"\n")


def mutate_fixture_input(corpus: Path) -> None:
    input_path = corpus / "ready" / "input.json"
    _ = input_path.write_bytes(input_path.read_bytes() + b"\n")


def mutate_receipt(corpus: Path) -> None:
    receipt = corpus / "source" / "verification-receipt.json"
    _ = receipt.write_bytes(receipt.read_bytes() + b"\n")


def add_corpus_member(corpus: Path) -> None:
    _ = (corpus / "source" / "race-added.json").write_text("{}\n", encoding="utf-8")


def mutate_expected_in_place(corpus: Path) -> None:
    expected = corpus / "ready" / "expected.json"
    inode = expected.stat().st_ino
    _ = expected.write_text(trace_mutated_expected(expected), encoding="utf-8")
    assert expected.stat().st_ino == inode


@pytest.mark.parametrize("link_kind", ("symlink", "hardlink"))
def test_regeneration_rejects_linked_expected_files_before_writing(
    tmp_path: Path,
    link_kind: str,
) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    external = tmp_path / "outside.json"
    original = b'{"outside":"must-not-change"}\n'
    _ = external.write_bytes(original)
    expected_path = corpus / "ready" / "expected.json"
    expected_path.unlink()
    if link_kind == "symlink":
        expected_path.symlink_to(external)
    else:
        os.link(external, expected_path)

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="link|regular"):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert external.read_bytes() == original


def test_regeneration_requires_explicit_matching_confirmation(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="confirmation"):
        _ = forward_harness.regenerate_goldens(corpus, confirm="wrong-version")

    _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert forward_harness.evaluate_fixture(corpus / "ready").corpus_digest


def test_regeneration_is_failure_atomic_for_later_invalid_fixtures(
    tmp_path: Path,
) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    before = corpus_bytes(corpus)
    _ = (corpus / "stale-observation" / "input.json").write_text(
        "{}\n", encoding="utf-8"
    )

    # When / Then
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="invalid forward fixture input"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert {
        path: content
        for path, content in corpus_bytes(corpus).items()
        if path.name in {"expected.json", "corpus-manifest.json"}
    } == {
        path: content
        for path, content in before.items()
        if path.name in {"expected.json", "corpus-manifest.json"}
    }


@pytest.mark.parametrize(
    "mutation",
    (
        mutate_source_member,
        mutate_fixture_input,
        mutate_receipt,
        add_corpus_member,
        mutate_expected_in_place,
    ),
    ids=("source", "input", "receipt", "added-member", "same-inode-expected"),
)
def test_regeneration_rejects_any_corpus_mutation_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Callable[[Path], None],
) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    commit = forward_harness.commit_staged_corpus
    mutated: dict[Path, bytes] = {}

    def mutate_before_commit(
        root: Path, stage: Path, snapshot: forward_harness_publish.CorpusSnapshot
    ) -> None:
        mutation(root)
        mutated.update(corpus_bytes(root))
        commit(root, stage, snapshot)

    monkeypatch.setattr(forward_harness, "commit_staged_corpus", mutate_before_commit)

    # When / Then
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="changed after preflight"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert corpus_bytes(corpus) == mutated


def test_regeneration_preserves_a_source_mutation_made_in_the_commit_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a reviewed corpus and a mutation that lands immediately after the
    # commit path verifies its source snapshot.
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    before = corpus_bytes(corpus)
    source = corpus / "source" / "ledger.json"
    verify = forward_harness_publish._verify_corpus_snapshot
    mutated = False

    def mutate_after_first_snapshot(
        root: Path, snapshot: forward_harness_publish.CorpusSnapshot
    ) -> None:
        nonlocal mutated
        verify(root, snapshot)
        if not mutated:
            mutate_source_member(root)
            mutated = True

    monkeypatch.setattr(
        forward_harness_publish, "_verify_corpus_snapshot", mutate_after_first_snapshot
    )

    # When / Then: regeneration must fail closed and preserve the concurrent
    # source write rather than replacing the corpus directory with its stage.
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="changed after preflight"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert mutated
    assert source.read_bytes() == before[Path("source/ledger.json")] + b"\n"
    assert {
        path: content
        for path, content in corpus_bytes(corpus).items()
        if path.name in {"expected.json", "corpus-manifest.json"}
    } == {
        path: content
        for path, content in before.items()
        if path.name in {"expected.json", "corpus-manifest.json"}
    }


@pytest.mark.parametrize("swap_kind", ("symlink", "hardlink"))
def test_regeneration_rejects_a_target_swapped_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    swap_kind: str,
) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    earlier_target = corpus / "ready" / "expected.json"
    _ = earlier_target.write_text('{"corrupt": true}\n', encoding="utf-8")
    earlier_before = earlier_target.read_bytes()
    external = tmp_path / "outside.json"
    original = b'{"outside":"must-not-change"}\n'
    _ = external.write_bytes(original)
    expected_path = corpus / "atom-narrowing" / "expected.json"
    commit = forward_harness.commit_staged_corpus

    def swap_before_commit(
        root: Path, stage: Path, snapshot: forward_harness_publish.CorpusSnapshot
    ) -> None:
        assert root == corpus
        expected_path.unlink()
        if swap_kind == "symlink":
            expected_path.symlink_to(external)
        else:
            os.link(external, expected_path)
        commit(root, stage, snapshot)

    monkeypatch.setattr(forward_harness, "commit_staged_corpus", swap_before_commit)

    # When / Then
    with pytest.raises(
        forward_harness.ForwardHarnessError, match="target changed|regular unlinked"
    ):
        _ = forward_harness.regenerate_goldens(corpus, confirm="v2")
    assert earlier_target.read_bytes() == earlier_before
    assert external.read_bytes() == original


def test_safe_write_refuses_a_hardlink_without_truncating_its_peer(
    tmp_path: Path,
) -> None:
    # Given
    external = tmp_path / "outside.json"
    original = b'{"outside":"must-not-change"}\n'
    _ = external.write_bytes(original)
    target = tmp_path / "target.json"
    os.link(external, target)

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="unlinked"):
        forward_harness.safe_write(target, "{}\n")
    assert external.read_bytes() == original
