#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from typer.testing import CliRunner

from scripts import ambiguity_ledger, build_contract, handoff_coverage, implementation_gate, protocol_state
from scripts.test_v2_session_manifest import v2_session

ATOM_BASE = Path(__file__).parent / "integration_fixtures" / "v2-negative" / "atom-base"
ATOM_MUTANTS = tuple(sorted((ATOM_BASE.parent).glob("atom-*/mutation.json")))


def mutation_values(path: Path) -> tuple[str, str, str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        str(payload["atom_id"]),
        str(payload["expected"]),
        str(payload["actual"]),
        str(payload["expected_message"]),
    )


def mutant_session(tmp_path: Path, mutation_path: Path) -> tuple[Path, str]:
    session = tmp_path / mutation_path.parent.name
    shutil.copytree(ATOM_BASE, session)
    _, expected, actual, expected_message = mutation_values(mutation_path)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    assert expected in handoff
    handoff_path.write_text(handoff.replace(expected, actual, 1), encoding="utf-8")
    return session, expected_message


def coverage_app():
    app = handoff_coverage.typer.Typer()
    app.command()(handoff_coverage.main)
    return app


def test_v2_atom_base_reports_explicit_atom_coverage(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "atom-base"
    shutil.copytree(ATOM_BASE, session)

    # When
    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    # Then
    assert result.exit_code == 0, result.output
    assert payload["coverage_ok"] is True
    assert payload["atom_coverage_ok"] is True
    assert payload["atom_mismatches"] == []


def test_v2_atom_coverage_rejects_a_catalog_hidden_in_a_fenced_example(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "fenced-catalog"
    shutil.copytree(ATOM_BASE, session)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    catalog_start = handoff.index("Behavior atom catalog:")
    catalog_end = handoff.index("# Part 2", catalog_start)
    handoff_path.write_text(
        handoff[:catalog_start] + "```markdown\n" + handoff[catalog_start:catalog_end] + "```\n\n" + handoff[catalog_end:],
        encoding="utf-8",
    )

    # When
    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    # Then
    assert result.exit_code == 1, result.output
    assert payload["coverage_ok"] is True
    assert payload["atom_coverage_ok"] is False
    assert "<catalog> catalog mismatch" in "\n".join(payload["atom_mismatches"])


def test_v2_atom_coverage_rejects_a_catalog_hidden_by_longer_closing_fence(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "long-fenced-catalog"
    shutil.copytree(ATOM_BASE, session)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    catalog_start = handoff.index("Behavior atom catalog:")
    catalog_end = handoff.index("# Part 2", catalog_start)
    handoff_path.write_text(
        handoff[:catalog_start] + "````markdown\n" + handoff[catalog_start:catalog_end] + "`````\n\n" + handoff[catalog_end:],
        encoding="utf-8",
    )

    # When
    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    # Then
    assert result.exit_code == 1, result.output
    assert payload["atom_coverage_ok"] is False
    assert "<catalog> catalog mismatch" in "\n".join(payload["atom_mismatches"])


def test_v2_atom_coverage_rejects_duplicate_ledger_atom_ids(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "duplicate-ledger-atom"
    shutil.copytree(ATOM_BASE, session)
    ledger_path = session / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["entries"][0]["behavior_atoms"].append(ledger["entries"][0]["behavior_atoms"][0])
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    # When
    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    # Then
    assert result.exit_code == 1, result.output
    assert payload["atom_coverage_ok"] is False
    assert "ATOM-101 id mismatch: expected 'unique', got 'duplicate'" in "\n".join(payload["atom_mismatches"])


def test_v2_atom_coverage_rejects_protocol_downgrade_and_unknown_version(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "downgraded-protocol"
    shutil.copytree(ATOM_BASE, session)
    protocol_path = session / "protocol.json"
    protocol_path.write_text('{"evidence_schema_version": 1}', encoding="utf-8")

    # When
    downgraded = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    downgraded_payload = json.loads(downgraded.output)
    ledger = json.loads((session / "ledger.json").read_text(encoding="utf-8"))
    ledger["entries"][0]["behavior_atoms"] = []
    (session / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    declared_without_atoms = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    declared_without_atoms_payload = json.loads(declared_without_atoms.output)
    protocol_path.write_text('{"evidence_schema_version": 3}', encoding="utf-8")
    unknown = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])

    # Then
    assert downgraded.exit_code == 1, downgraded.output
    assert downgraded_payload["atom_coverage_ok"] is False
    assert "<protocol> evidence_schema_version mismatch: expected '2', got '1'" in "\n".join(downgraded_payload["atom_mismatches"])
    assert declared_without_atoms.exit_code == 1, declared_without_atoms.output
    assert declared_without_atoms_payload["atom_coverage_ok"] is False
    assert "<protocol> evidence_schema_version mismatch: expected '2', got '1'" in "\n".join(declared_without_atoms_payload["atom_mismatches"])
    assert unknown.exit_code != 0
    assert "evidence_schema_version must be 0, 1, or 2" in unknown.output


def test_implementation_gate_rejects_declared_atoms_after_protocol_downgrade(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    handoff = (session / "handoff.md").read_text(encoding="utf-8")
    ledger_text = (session / "ledger.json").read_text(encoding="utf-8")
    entries = ambiguity_ledger.parse_entries(ledger_text)
    protocol = protocol_state.parse_state((session / "protocol.json").read_text(encoding="utf-8"))
    downgraded = protocol.model_copy(
        update={"evidence_schema_version": 1, "contract_schema_version": 1, "assurance_result": None},
    )

    # When
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1),
        protocol_state.summarize_protocol(downgraded),
        handoff,
        protocol=downgraded,
        raw_ledger_text=ledger_text,
    )

    # Then
    assert "v2 assurance declarations require evidence schema version 2" in result.failures

    # Given an assurance declaration with no atoms
    atomless_entries = tuple(entry.model_copy(update={"behavior_atoms": ()}) for entry in entries)

    # When
    atomless = implementation_gate.evaluate(
        atomless_entries,
        ambiguity_ledger.summarize_ambiguity(atomless_entries, evidence_schema_version=1),
        protocol_state.summarize_protocol(downgraded),
        handoff,
        protocol=downgraded,
        raw_ledger_text=ledger_text,
    )

    # Then
    assert "v2 assurance declarations require evidence schema version 2" in atomless.failures


@pytest.mark.parametrize("mutation_path", ATOM_MUTANTS, ids=lambda path: path.parent.name)
def test_v2_atom_mutants_fail_even_when_source_id_coverage_passes(
    tmp_path: Path,
    mutation_path: Path,
) -> None:
    # Given
    session, expected_message = mutant_session(tmp_path, mutation_path)

    # When
    result = CliRunner().invoke(coverage_app(), ["--format", "json", str(session)])
    payload = json.loads(result.output)

    # Then
    assert result.exit_code == 1, result.output
    assert payload["coverage_ok"] is True
    assert payload["atom_coverage_ok"] is False
    assert expected_message in "\n".join(payload["atom_mismatches"])


def test_v2_implementation_gate_reports_raw_atom_polarity_mutation(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    handoff = (session / "handoff.md").read_text(encoding="utf-8")
    mutated = handoff.replace(
        "| REQ-001 | high | ATOM-001 | The local validation command is invoked. | must |",
        "| REQ-001 | high | ATOM-001 | The local validation command is invoked. | must-not |",
        1,
    )
    ledger_text = (session / "ledger.json").read_text(encoding="utf-8")
    entries = ambiguity_ledger.parse_entries(ledger_text)
    protocol = protocol_state.parse_state((session / "protocol.json").read_text(encoding="utf-8"))
    protocol = protocol.model_copy(
        update={"build_contract_digest": implementation_gate.contract_digest(mutated)},
    )
    contract = build_contract.compile_handoff(mutated)

    # When
    result = implementation_gate.evaluate(
        entries,
        ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=2),
        protocol_state.summarize_protocol(protocol),
        mutated,
        protocol=protocol,
        contract_sidecar=contract,
        raw_ledger_text=ledger_text,
    )

    # Then
    assert any("atom coverage: ATOM-001 polarity mismatch" in failure for failure in result.failures)
