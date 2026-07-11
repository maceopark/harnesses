#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import pytest
from typer.testing import CliRunner

from scripts import probe_policy, protocol_state, session_manifest, session_status
from scripts.receipt_test_support import NOW, probe_receipt, receipt_import_module, sealed_session

V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready"
V2_NEGATIVE = Path(__file__).parent / "integration_fixtures" / "v2-negative"


def probe_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(probe_policy.main)
    return app


def status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def test_staged_probe_cli_normalizes_declared_attempt() -> None:
    # Given
    raw = (V2_READY / "staged-probe.json").read_text(encoding="utf-8")

    # When
    result = CliRunner().invoke(probe_app(), input=raw)

    # Then
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["decision"]["execution_scope"] == "l3:staged-telemetry"


def test_staged_probe_cli_rejects_production_receipt_scope() -> None:
    # Given
    raw = (V2_NEGATIVE / "staged-with-production-receipt.json").read_text(encoding="utf-8")

    # When
    result = CliRunner().invoke(probe_app(), input=raw)

    # Then
    assert result.exit_code != 0
    assert "staged" in result.output


def test_probe_cli_does_not_echo_rejected_input_values() -> None:
    # Given
    payload = json.loads((V2_READY / "staged-probe.json").read_text(encoding="utf-8"))
    canary = "task9-review-canary-not-a-real-secret"
    payload["api_token"] = canary

    # When
    result = CliRunner().invoke(probe_app(), input=json.dumps(payload))

    # Then
    assert result.exit_code != 0
    assert canary not in result.output


def test_probe_receipt_status_revalidates_task4_bindings_without_state_writes(
    tmp_path: Path,
) -> None:
    # Given
    session, _, contract_digest = sealed_session(tmp_path)
    staged_payload = json.loads((V2_READY / "staged-probe.json").read_text(encoding="utf-8"))
    staged_payload["decision"]["contract_digest"] = contract_digest
    staged_payload["decision"]["authorization"]["contract_digest"] = contract_digest
    staged_payload["result"]["contract_digest"] = contract_digest
    attempt = probe_policy.ProbeAttempt.model_validate(staged_payload)
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["probe_decision"] = attempt.decision.model_dump(mode="json")
    protocol["probe_sequence"] = {"attempts": [attempt.model_dump(mode="json")]}
    protocol_state.parse_state(json.dumps(protocol))
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    manifest = session_manifest.seal_session(session)
    importer = receipt_import_module()
    before_receipt = importer.probe_receipt_status(session, now=NOW)

    # When
    receipt = probe_receipt(session, manifest.manifest_digest, contract_digest)
    imported = importer.import_receipt(session, json.dumps(receipt), now=NOW)
    (session / ".session-update.lock").unlink(missing_ok=True)
    protocol_before_status = protocol_path.read_bytes()
    status = importer.probe_receipt_status(session, now=NOW)

    # Then
    assert before_receipt.verified is False
    assert status.verified is True
    assert status.receipt_digest == imported.receipt_digest
    assert protocol_path.read_bytes() == protocol_before_status
    assert not (session / ".session-update.lock").exists()


def test_probe_receipt_status_fails_closed_for_replayed_nonce(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path, with_probe=True)
    importer = receipt_import_module()
    imported = importer.import_receipt(
        session,
        json.dumps(probe_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )
    stored = session / "receipts" / f"{imported.receipt_digest}.json"
    shutil.copyfile(stored, session / "receipts" / "replayed-nonce.json")

    # When
    status = importer.probe_receipt_status(session, now=NOW)

    # Then
    assert status.verified is False
    assert "replayed nonce" in status.reason


def test_probe_receipt_status_fails_closed_when_source_manifest_is_stale(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path, with_probe=True)
    importer = receipt_import_module()
    importer.import_receipt(
        session,
        json.dumps(probe_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )
    ledger_path = session / "ledger.json"
    ledger_path.write_text(ledger_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    # When
    status = importer.probe_receipt_status(session, now=NOW)

    # Then
    assert status.verified is False
    assert "manifest" in status.reason


def test_probe_receipt_status_rejects_a_persisted_contract_mismatch(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path, with_probe=True)
    importer = receipt_import_module()
    importer.import_receipt(
        session,
        json.dumps(probe_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["probe_decision"]["contract_digest"] = "f" * 64
    protocol_state.parse_state(json.dumps(protocol))
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    session_manifest.seal_session(session)

    # When
    status = importer.probe_receipt_status(session, now=NOW)

    # Then
    assert status.verified is False
    assert "ProbeDecision contract_digest" in status.reason


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("observation_spec_digest", "0" * 64, "observation_spec_digest"),
        ("policy_version", "unexpected-policy", "policy_version"),
    ],
)
def test_probe_receipt_import_rejects_bad_spec_or_policy(
    tmp_path: Path,
    field: str,
    value: str,
    expected: str,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path, with_probe=True)
    receipt = probe_receipt(session, manifest_digest, contract_digest)
    receipt[field] = value
    if field == "observation_spec_digest":
        receipt["action_digest"] = value

    # When / Then
    with pytest.raises(ValueError, match=expected):
        receipt_import_module().import_receipt(session, json.dumps(receipt), now=NOW)


def test_session_status_reports_derived_probe_receipt_verification(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path, with_probe=True)
    importer = receipt_import_module()
    receipt = probe_receipt(session, manifest_digest, contract_digest)
    receipt["expires_at"] = "2099-07-12T11:00:00Z"
    imported = importer.import_receipt(
        session,
        json.dumps(receipt),
        now=NOW,
    )

    # When
    result = CliRunner().invoke(status_app(), [str(session), "--format", "json"])

    # Then
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["probe_receipt_verified"] is True
    assert payload["probe_receipt_digest"] == imported.receipt_digest
