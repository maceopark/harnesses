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
from pydantic import TypeAdapter, ValidationError
import typer
from typer.testing import CliRunner

from scripts import assurance_schema, build_contract_schema, protocol_state, session_status

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

V1_READY_PROTOCOL = Path(__file__).parent / "integration_fixtures" / "v1-ready" / "protocol.json"
V1_READY_SESSION = V1_READY_PROTOCOL.parent
V0_READY_SESSION = Path(__file__).parent / "regression_fixtures" / "ready-minimal"
BASE_ASSURANCE_INPUTS = assurance_schema.AssuranceInputs(
    manifest=assurance_schema.ArtifactState.VALID,
    sidecar=assurance_schema.ArtifactState.VALID,
    requirements_covered=True,
    atoms_covered=True,
    receipt=assurance_schema.ReceiptState.BOUND_SUCCESS,
)


def ready_protocol() -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        json.loads(V1_READY_PROTOCOL.read_text(encoding="utf-8")),
    )


def derive_assurance(
    inputs: assurance_schema.AssuranceInputs,
) -> assurance_schema.AssuranceResult:
    return assurance_schema.derive_assurance_result(inputs)


def write_v2_atom_policy(session: Path) -> None:
    payload = json.loads((session / "ledger.json").read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    entry["assurance_class"] = "high"
    entry["behavior_atoms"] = [
        {
            "id": "ATOM-001",
            "condition": "The local validation command is invoked.",
            "polarity": "must",
            "observable_response": "The command exits successfully.",
            "boundary_context": None,
            "temporal_context": None,
            "coercion_context": None,
        },
    ]
    (session / "ledger.json").write_text(json.dumps(payload), encoding="utf-8")


def session_status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def test_v2_protocol_requires_the_complete_assurance_result() -> None:
    # Given
    payload = ready_protocol()
    payload["evidence_schema_version"] = 2
    payload["contract_schema_version"] = 2

    # When / Then
    with pytest.raises(ValidationError, match="schema v2 requires assurance_result"):
        protocol_state.parse_state(json.dumps(payload))


def test_unknown_schema_version_has_a_stable_rejection() -> None:
    # Given
    payload = ready_protocol()
    payload["evidence_schema_version"] = 3
    payload["contract_schema_version"] = 3

    # When / Then
    with pytest.raises(ValidationError, match="unknown schema version"):
        protocol_state.parse_state(json.dumps(payload))


@pytest.mark.parametrize(
    ("result", "expected_abi", "expected_trace", "expected_property"),
    (
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"manifest": assurance_schema.ArtifactState.MISSING})),
            assurance_schema.AbiVerdict.FAIL,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"manifest": assurance_schema.ArtifactState.INVALID})),
            assurance_schema.AbiVerdict.FAIL,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"sidecar": assurance_schema.ArtifactState.STALE})),
            assurance_schema.AbiVerdict.FAIL,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"requirements_covered": False})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.FAIL,
            assurance_schema.PropertyVerdict.OBSERVED_PASS,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"atoms_covered": False})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.FAIL,
            assurance_schema.PropertyVerdict.OBSERVED_PASS,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.ABSENT})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.NOT_RUN,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.MALFORMED})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.STALE})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.REPLAYED})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.RECEIPT_INVALID,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.BOUND_NONZERO})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.OBSERVED_FAIL,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.BOUND_TIMEOUT})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.OBSERVED_FAIL,
        ),
        (
            derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.BOUND_FAILURE})),
            assurance_schema.AbiVerdict.PASS,
            assurance_schema.TraceVerdict.PASS,
            assurance_schema.PropertyVerdict.OBSERVED_FAIL,
        ),
    ),
)
def test_assurance_mapping_has_only_the_allowed_precedence(
    result: assurance_schema.AssuranceResult,
    expected_abi: assurance_schema.AbiVerdict,
    expected_trace: assurance_schema.TraceVerdict,
    expected_property: assurance_schema.PropertyVerdict,
) -> None:
    # Given / When / Then
    assert result.abi is expected_abi
    assert result.trace is expected_trace
    assert result.property is expected_property


def test_structural_only_assurance_cannot_claim_an_observed_property() -> None:
    # Given / When
    result = derive_assurance(BASE_ASSURANCE_INPUTS.model_copy(update={"receipt": assurance_schema.ReceiptState.ABSENT}))

    # Then
    assert result.property is assurance_schema.PropertyVerdict.NOT_RUN


def test_assurance_serialization_always_includes_five_independent_verdicts() -> None:
    # Given / When
    result = derive_assurance(BASE_ASSURANCE_INPUTS)

    # Then
    assert set(result.model_dump(mode="json")) == {
        "schema_version",
        "abi",
        "trace",
        "property",
        "adequacy",
        "stakeholder",
    }
    assert result.adequacy is assurance_schema.AdequacyVerdict.NOT_ASSESSED
    assert result.stakeholder is assurance_schema.StakeholderVerdict.NOT_SOUGHT


def test_v2_protocol_and_cli_report_assurance_without_changing_v1_rendering(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "v2-ready"
    shutil.copytree(V1_READY_SESSION, session)
    write_v2_atom_policy(session)
    payload = ready_protocol()
    payload["evidence_schema_version"] = 2
    payload["contract_schema_version"] = 2
    claimant_safe_result = derive_assurance(
        BASE_ASSURANCE_INPUTS.model_copy(
            update={"receipt": assurance_schema.ReceiptState.ABSENT},
        ),
    )
    payload["assurance_result"] = claimant_safe_result.model_dump(mode="json")
    (session / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")

    # When
    result = CliRunner().invoke(
        session_status_app(),
        ["--format", "json", str(session)],
    )

    # Then
    assert result.exit_code == 0
    rendered = json.loads(result.output)
    assert rendered["assurance"] == claimant_safe_result.model_dump(mode="json")


@pytest.mark.parametrize(
    ("abi", "expected_error"),
    (
        ("pass", "receipt-backed import"),
        ("fail", ""),
    ),
)
def test_v2_cli_rejects_claimant_authored_observed_pass(
    tmp_path: Path,
    abi: str,
    expected_error: str,
) -> None:
    # Given
    session = tmp_path / f"v2-claimant-{abi}"
    shutil.copytree(V1_READY_SESSION, session)
    write_v2_atom_policy(session)
    payload = ready_protocol()
    payload["evidence_schema_version"] = 2
    payload["contract_schema_version"] = 2
    payload["assurance_result"] = {
        "schema_version": 2,
        "abi": abi,
        "trace": "pass",
        "property": "observed-pass",
        "adequacy": "not-assessed",
        "stakeholder": "not-sought",
    }
    (session / "protocol.json").write_text(json.dumps(payload), encoding="utf-8")

    # When
    result = CliRunner().invoke(session_status_app(), ["--format", "json", str(session)])

    # Then
    assert result.exit_code != 0
    if expected_error:
        assert expected_error in result.output


@pytest.mark.parametrize("fixture", (V0_READY_SESSION, V1_READY_SESSION))
def test_legacy_sessions_emit_migration_guidance_only_for_the_v2_flag(
    tmp_path: Path,
    fixture: Path,
) -> None:
    # Given
    session = tmp_path / fixture.name
    shutil.copytree(fixture, session)

    # When
    result = CliRunner().invoke(
        session_status_app(),
        ["--format", "json", "--require-assurance-v2", str(session)],
    )

    # Then
    assert result.exit_code == 1
    assert set(json.loads(result.output)) == {"migration_guidance"}


def test_v1_json_has_no_v2_assurance_claims(tmp_path: Path) -> None:
    # Given
    session = tmp_path / "v1-ready"
    shutil.copytree(V1_READY_SESSION, session)

    # When
    result = CliRunner().invoke(session_status_app(), ["--format", "json", str(session)])

    # Then
    assert result.exit_code == 0
    assert "assurance" not in json.loads(result.output)


def test_v2_build_contract_rejects_an_unclassified_v1_projection() -> None:
    # Given
    payload = json.loads((V1_READY_SESSION / "build-contract.json").read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    # When / Then
    with pytest.raises(ValueError, match="v2 requirements require an assurance class"):
        build_contract_schema.ContractBody.model_validate(
            {key: value for key, value in payload.items() if key != "contract_digest"},
        )
