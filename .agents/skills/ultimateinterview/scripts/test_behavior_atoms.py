#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import typer
from typer.testing import CliRunner

from scripts import ambiguity_ledger, build_contract, implementation_gate, session_update
from scripts.test_v2_session_manifest import status_app, v2_session

V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready"
V2_HIGH_WITHOUT_ATOMS = Path(__file__).parent / "integration_fixtures" / "v2-negative" / "high-without-atoms" / "handoff.md"
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def atoms_module() -> ModuleType:
    from scripts import behavior_atoms

    return behavior_atoms


def v2_entry() -> JsonObject:
    payload = json.loads((V2_READY / "ledger.json").read_text(encoding="utf-8"))
    return payload["entries"][0]


def atom_payload() -> JsonObject:
    return {
        "id": "ATOM-001",
        "condition": "The validation command is invoked.",
        "polarity": "must",
        "observable_response": "It exits with status zero.",
        "boundary_context": "Exit status is the boundary.",
        "temporal_context": None,
        "coercion_context": None,
    }


def validate_v2(entry: JsonObject) -> None:
    entries = ambiguity_ledger.parse_entries(json.dumps({"entries": [entry]}))
    atoms_module().validate_entries(entries, evidence_schema_version=2)


def v2_handoff() -> str:
    return (V2_READY / "handoff.md").read_text(encoding="utf-8")


def replace_once(source: str, old: str, new: str) -> str:
    assert old in source
    return source.replace(old, new, 1)


@pytest.mark.parametrize("class_value", (None, "unknown"))
def test_v2_material_entry_requires_known_assurance_class(class_value: str | None) -> None:
    # Given
    entry = v2_entry()
    if class_value is None:
        entry.pop("assurance_class", None)
    else:
        entry["assurance_class"] = class_value

    # When / Then
    with pytest.raises(ValueError, match="assurance class"):
        validate_v2(entry)


def test_v2_weight_five_cannot_downgrade_to_standard() -> None:
    # Given
    entry = v2_entry()
    entry["assurance_class"] = "standard"
    entry["behavior_atoms"] = [atom_payload()]

    # When / Then
    with pytest.raises(ValueError, match="high"):
        validate_v2(entry)


def test_v2_low_impact_entry_still_requires_an_assurance_class() -> None:
    # Given
    entry = v2_entry()
    entry["impact_weight"] = 1
    entry.pop("assurance_class")

    # When / Then
    with pytest.raises(ValueError, match="assurance class"):
        validate_v2(entry)


def test_v2_high_entry_requires_at_least_one_atom() -> None:
    # Given
    entry = v2_entry()
    entry["assurance_class"] = "high"
    entry["behavior_atoms"] = []

    # When / Then
    with pytest.raises(ValueError, match="high.*atom"):
        validate_v2(entry)


def test_v2_rejects_duplicate_atom_ids() -> None:
    # Given
    entry = v2_entry()
    entry["assurance_class"] = "high"
    entry["behavior_atoms"] = [atom_payload(), atom_payload()]

    # When / Then
    with pytest.raises(ValueError, match="duplicate behavior atom id"):
        validate_v2(entry)


@pytest.mark.parametrize("field", ("polarity", "observable_response"))
def test_atom_requires_polarity_and_observable_response(field: str) -> None:
    # Given
    payload = atom_payload()
    payload.pop(field)

    # When / Then
    with pytest.raises(ValueError, match=field):
        atoms_module().BehaviorAtom.model_validate(payload)


def test_v2_contract_rejects_an_unbound_normative_atom() -> None:
    # Given
    source = replace_once(
        v2_handoff(),
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | high | ATOM-001 |",
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | high | ATOM-404 |",
    )

    # When / Then
    with pytest.raises(ValueError, match="unknown behavior atom"):
        build_contract.compile_handoff(source)


def test_v2_high_handoff_requires_an_atom_citation() -> None:
    # Given
    source = V2_HIGH_WITHOUT_ATOMS.read_text(encoding="utf-8")

    # When / Then
    with pytest.raises(ValueError, match="high requirement requires at least one behavior atom"):
        build_contract.compile_handoff(source)


def test_v2_contract_rejects_a_high_requirement_bound_to_a_standard_atom() -> None:
    # Given
    source = replace_once(
        v2_handoff(),
        "| REQ-001 | high | ATOM-001 | The local validation command is invoked.",
        "| REQ-001 | standard | ATOM-001 | The local validation command is invoked.",
    )

    # When / Then
    with pytest.raises(ValueError, match="assurance class"):
        build_contract.compile_handoff(source)


def test_v2_contract_rejects_reordered_assurance_columns_instead_of_downgrading() -> None:
    # Given
    source = replace_once(
        v2_handoff(),
        "| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source | Assurance class | Atom IDs |",
        "| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source | Atom IDs | Assurance class |",
    )
    source = replace_once(
        source,
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | high | ATOM-001 |",
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | ATOM-001 | high |",
    )

    # When / Then
    with pytest.raises(build_contract.BuildContractCompileError, match="v2 behavior atom headers"):
        build_contract.compile_handoff(source)


def test_v2_contract_allows_standard_requirements_without_an_atom_catalog() -> None:
    # Given
    source = replace_once(
        v2_handoff(),
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | high | ATOM-001 |",
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 | standard |  |",
    )
    catalog_start = source.index("Behavior atom catalog:")
    catalog_end = source.index("## Change Impact & Preservation", catalog_start)
    source = source[:catalog_start] + source[catalog_end:]

    # When
    contract = build_contract.compile_handoff(source)

    # Then
    assert contract.schema_version == 2
    assert contract.requirements[0].assurance_class is not None
    assert contract.requirements[0].assurance_class.value == "standard"
    assert contract.behavior_atoms == ()


def test_valid_high_v2_contract_round_trips_atom_ids_and_digests() -> None:
    # Given
    source = v2_handoff()

    # When
    first = build_contract.compile_handoff(source)
    second = build_contract.compile_handoff(source)

    # Then
    assert first.schema_version == 2
    assert first.requirements[0].assurance_class is not None
    assert first.requirements[0].assurance_class.value == "high"
    assert first.requirements[0].atom_ids == ("ATOM-001",)
    assert first.behavior_atoms[0].atom.id == "ATOM-001"
    assert first.behavior_atoms[0].atom_digest == second.behavior_atoms[0].atom_digest
    assert build_contract.canonical_json(first) == build_contract.canonical_json(second)


def v1_handoff(source: str) -> str:
    v2_header = "| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source | Assurance class | Atom IDs |"
    start = source.index(v2_header)
    end = source.index("## Change Impact & Preservation", start)
    legacy_table = (
        "| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| REQ-001 | validation command executes | When invoked, the validation command shall exit successfully. | REQ-001 |\n\n"
    )
    return source[:start] + legacy_table + source[end:]


def test_v2_session_update_rejects_a_v1_compiled_contract(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    handoff_path = session / "handoff.md"
    handoff_path.write_text(v1_handoff(handoff_path.read_text(encoding="utf-8")), encoding="utf-8")
    delta = session_update.parse_delta(json.dumps({"build_contract_test": {"reviewer": "task6"}}))

    # When / Then
    with pytest.raises(typer.BadParameter, match="schema version"):
        session_update.update_session(session, delta)


def test_v2_gate_rejects_a_v1_sidecar_for_a_v2_protocol(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    handoff_path = session / "handoff.md"
    handoff = v1_handoff(handoff_path.read_text(encoding="utf-8"))
    handoff_path.write_text(handoff, encoding="utf-8")
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["build_contract_digest"] = implementation_gate.contract_digest(handoff)
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
    (session / "build-contract.json").write_text(
        build_contract.canonical_json(build_contract.compile_handoff(handoff)),
        encoding="utf-8",
    )

    # When
    result = CliRunner().invoke(status_app(), ["--format", "json", "--gate", str(session)])

    # Then
    assert result.exit_code == 1
    assert "schema version" in result.output


def test_v2_gate_rejects_a_ledger_atom_that_differs_from_the_contract(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    ledger_path = session / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["entries"][0]["behavior_atoms"][0]["observable_response"] = "The command writes a status line."
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    # When
    result = CliRunner().invoke(status_app(), ["--format", "json", "--gate", str(session)])

    # Then
    assert result.exit_code == 1
    assert "behavior atom" in result.output


def test_v2_session_update_rejects_atom_removal_and_invalidates_review(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    removed = session_update.parse_delta(
        json.dumps({"set": [{"id": "REQ-001", "behavior_atoms": []}]}),
    )
    replacement = atom_payload()
    replacement["observable_response"] = "The command reports a passing result."
    changed = session_update.parse_delta(
        json.dumps({"set": [{"id": "REQ-001", "behavior_atoms": [replacement]}]}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="high v2 entry"):
        session_update.update_session(session, removed)
    updated = session_update.update_session(session, changed)
    assert updated.protocol.material_revision == 1
    assert updated.protocol.build_contract_tested is False
