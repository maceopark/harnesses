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

from scripts import assurance_schema, forward_harness

CORPUS = Path(__file__).parent / "forward_fixtures" / "v2"
READY = CORPUS / "ready"


def corpus_bytes(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def forward_app() -> typer.Typer:
    app = typer.Typer()
    _ = app.command()(forward_harness.main)
    return app


def trace_mutated_expected(expected_path: Path) -> str:
    expected = forward_harness.ForwardResult.model_validate_json(expected_path.read_text(encoding="utf-8"))
    return expected.model_copy(
        update={
            "verdicts": forward_harness.ForwardVerdicts(
                abi=expected.verdicts.abi,
                trace=assurance_schema.TraceVerdict.FAIL if expected.verdicts.trace is assurance_schema.TraceVerdict.PASS else assurance_schema.TraceVerdict.PASS,
                property=expected.verdicts.property,
                adequacy=expected.verdicts.adequacy,
                stakeholder=expected.verdicts.stakeholder,
            )
        }
    ).model_dump_json()


def test_forward_harness_reports_noncreditable_simulated_receipts_without_writes() -> None:
    # Given
    before = corpus_bytes(CORPUS)

    # When
    result = forward_harness.evaluate_fixture(READY)

    # Then
    assert result.verdicts.abi == "pass"
    assert result.verdicts.trace == "pass"
    assert result.verdicts.property == "not-run"
    assert result.verdicts.adequacy == "not-assessed"
    assert result.verdicts.stakeholder == "not-sought"
    assert result.gate.implementation_ready is False
    assert result.gate.failures == (
        "creditable imported execution receipts are required",
    )
    assert before == corpus_bytes(CORPUS)


@pytest.mark.parametrize(
    "fixture_name",
    (
        "same-actor-two-declared-groups",
        "stale-observation",
        "session-mutation-after-review",
        "atom-narrowing",
        "declaration-without-receipt",
        "failed-command-receipt",
        "consumer-replay",
    ),
)
def test_forward_harness_matches_each_reviewed_negative_fixture(fixture_name: str) -> None:
    # Given
    fixture = CORPUS / fixture_name

    # When
    result = forward_harness.evaluate_fixture(fixture)

    # Then
    expected = forward_harness.ForwardResult.model_validate_json(
        (fixture / "expected.json").read_text(encoding="utf-8")
    )
    assert result == expected


def test_forward_harness_rejects_a_mutated_expected_golden(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    expected_path = corpus / "ready" / "expected.json"
    _ = expected_path.write_text(trace_mutated_expected(expected_path), encoding="utf-8")

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="corpus"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_cli_rejects_a_mutated_expected_golden(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    expected_path = corpus / "ready" / "expected.json"
    _ = expected_path.write_text(trace_mutated_expected(expected_path), encoding="utf-8")

    # When
    result = CliRunner().invoke(forward_app(), [str(corpus / "ready")])

    # Then
    assert result.exit_code == 1
    assert "corpus member digest" in result.output


def test_expected_member_preimage_omits_only_its_corpus_digest(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    expected_path = corpus / "ready" / "expected.json"
    expected = forward_harness.ForwardResult.model_validate_json(expected_path.read_text(encoding="utf-8"))
    changed_digest = forward_harness.ForwardResult(
        corpus_digest="f" * 64,
        verdicts=expected.verdicts,
        gate=expected.gate,
    )
    _ = expected_path.write_text(changed_digest.model_dump_json(), encoding="utf-8")

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="reviewed golden"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


@pytest.mark.parametrize("member", ("ready/input.json", "ready/expected.json"))
def test_forward_harness_rejects_renamed_corpus_members(
    tmp_path: Path,
    member: str,
) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    source = corpus / member
    _ = source.rename(source.with_name(f"renamed-{source.name}"))

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="member set"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_rejects_removed_corpus_member(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    (corpus / "ready" / "input.json").unlink()

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="member set"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_rejects_added_corpus_member(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    _ = (corpus / "ready" / "unexpected.json").write_text("{}\n", encoding="utf-8")

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="member set"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_rejects_changed_corpus_member(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    input_path = corpus / "ready" / "input.json"
    _ = input_path.write_text(input_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="member digest"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_rejects_a_nested_manifest_member(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    _ = (corpus / "ready" / "corpus-manifest.json").write_text("{}\n", encoding="utf-8")

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="manifest"):
        _ = forward_harness.evaluate_fixture(corpus / "ready")


def test_forward_harness_rejects_a_symlinked_corpus_root(tmp_path: Path) -> None:
    # Given
    corpus = tmp_path / "v2"
    _ = shutil.copytree(CORPUS, corpus)
    linked_corpus = tmp_path / "linked-v2"
    linked_corpus.symlink_to(corpus, target_is_directory=True)

    # When / Then
    with pytest.raises(forward_harness.ForwardHarnessError, match="corpus root"):
        _ = forward_harness.evaluate_fixture(linked_corpus / "ready")


def test_forward_harness_cli_is_read_only_and_prints_five_verdicts() -> None:
    # Given
    before = corpus_bytes(CORPUS)

    # When
    result = CliRunner().invoke(forward_app(), [str(READY)])

    # Then
    assert result.exit_code == 0, result.output
    verdicts = forward_harness.ForwardResult.model_validate_json(result.output).verdicts
    assert verdicts.abi.value == "pass"
    assert verdicts.trace.value == "pass"
    assert verdicts.property.value == "not-run"
    assert verdicts.adequacy.value == "not-assessed"
    assert verdicts.stakeholder.value == "not-sought"
    assert corpus_bytes(CORPUS) == before
