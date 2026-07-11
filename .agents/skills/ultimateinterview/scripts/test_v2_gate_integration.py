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
import typer
from typer.testing import CliRunner

from scripts import session_manifest, session_status
from scripts.receipt_test_support import (
    NOW,
    V2_READY,
    receipt_contract_module,
    receipt_import_module,
    sealed_session,
    verification_receipt,
)

V0_READY = Path(__file__).parent / "regression_fixtures" / "ready-minimal"
V1_READY = Path(__file__).parent / "integration_fixtures" / "v1-ready"
SAME_ACTOR_FIXTURE = (
    Path(__file__).parent
    / "integration_fixtures"
    / "v2-negative"
    / "same-actor-two-declared-groups"
    / "ledger.json"
)


def status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def status_json(session: Path, *options: str):
    result = CliRunner().invoke(
        status_app(),
        ["--format", "json", *options, str(session)],
    )
    return result, json.loads(result.output)


def import_current_receipt(session: Path) -> None:
    raw = (V2_READY / "verification-receipt.json").read_text(encoding="utf-8")
    receipt_import_module().import_receipt(session, raw, now=NOW)


def import_claim_receipt(
    session: Path,
    manifest_digest: str,
    contract_digest: str,
    *,
    kind: str,
) -> None:
    payload = verification_receipt(session, manifest_digest, contract_digest)
    payload.update(
        {
            "receipt_id": f"receipt-{kind}-001",
            "kind": kind,
            "session_id": session.name,
            "manifest_digest": manifest_digest,
            "nonce": f"nonce-{kind}-001",
            "action_digest": None,
            "claim_digest": "e" * 64,
            "verification_id": None,
            "probe_id": None,
            "observation_spec_digest": None,
        },
    )
    receipt_import_module().import_receipt(session, json.dumps(payload), now=NOW)


def test_unsealed_v2_exposes_separate_incomplete_snapshot_and_receipts(
    tmp_path: Path,
) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    (session / session_manifest.MANIFEST_NAME).unlink()

    # When
    result, payload = status_json(session)
    required = CliRunner().invoke(
        status_app(),
        ["--format", "json", "--require-manifest", str(session)],
    )

    # Then
    assert result.exit_code == 0, result.output
    assert payload["snapshot_complete"] is False
    assert payload["execution_receipts_current"] is False
    assert required.exit_code == 1


def test_sealed_v2_without_imported_receipt_is_not_a_gate_failure(
    tmp_path: Path,
) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)

    # When
    result, payload = status_json(session, "--gate")
    required, required_payload = status_json(session, "--require-execution-receipts")

    # Then
    assert result.exit_code == 0, result.output
    assert payload["snapshot_complete"] is True
    assert payload["execution_receipts_current"] is False
    assert payload["assurance"]["property"] == "not-run"
    assert required.exit_code == 1
    assert required_payload["execution_receipts_current"] is False
    assert required_payload["execution_receipts_reason"] == "no imported receipts"


def test_v2_same_identity_with_two_claimant_labels_fails_the_status_gate(
    tmp_path: Path,
) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    session.joinpath("ledger.json").write_text(
        SAME_ACTOR_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    session_manifest.seal_session(session)

    # When
    result, payload = status_json(session, "--gate", "--require-manifest")

    # Then
    assert result.exit_code == 1, result.output
    assert (
        "v2 untrusted/collapsed provenance: REQ-001"
        in payload["implementation_gate"]["failures"]
    )


def test_simulated_imported_receipt_cannot_promote_property_or_implementation_readiness(
    tmp_path: Path,
) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    import_current_receipt(session)

    # When
    result, payload = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )
    markdown = CliRunner().invoke(
        status_app(),
        [
            "--format",
            "markdown",
            "--gate",
            "--require-manifest",
            "--require-execution-receipts",
            str(session),
        ],
    )

    # Then
    assert result.exit_code == 1
    assert payload["snapshot_complete"] is True
    assert payload["execution_receipts_current"] is True
    assert payload["execution_receipts_creditable"] is False
    assert payload["assurance"]["property"] == "not-run"
    assert payload["assurance"]["adequacy"] == "not-assessed"
    assert payload["assurance"]["stakeholder"] == "not-sought"
    assert payload["implementation_gate"]["implementation_ready"] is False
    assert "creditable imported execution receipts are required" in payload[
        "implementation_gate"
    ]["failures"]
    assert markdown.exit_code == 1
    assert "- snapshot_complete: yes" in markdown.output
    assert "- execution_receipts_current: yes" in markdown.output
    assert "- execution_receipts_creditable: no" in markdown.output
    assert "- property: not-run" in markdown.output


@pytest.mark.parametrize("outcome", ("nonzero", "timeout", "failure"))
def test_simulated_non_success_execution_receipt_cannot_report_property_evidence(
    tmp_path: Path,
    outcome: str,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    payload.update(
        {
            "session_id": session.name,
            "manifest_digest": manifest_digest,
            "contract_digest": contract_digest,
            "outcome": outcome,
        },
    )
    receipt_import_module().import_receipt(session, json.dumps(payload), now=NOW)

    # When
    result, status = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )

    # Then
    assert result.exit_code == 1
    assert status["execution_receipts_current"] is True
    assert status["execution_receipts_creditable"] is False
    assert status["assurance"]["property"] == "not-run"


@pytest.mark.parametrize("kind", ("evidence", "authority"))
def test_non_execution_only_receipts_fail_the_execution_receipt_gate(
    tmp_path: Path,
    kind: str,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    import_claim_receipt(session, manifest_digest, contract_digest, kind=kind)

    # When
    result, status = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )

    # Then
    assert result.exit_code == 1
    assert status["execution_receipts_current"] is False
    assert status["execution_receipts_reason"] == "no imported execution receipts"
    assert status["assurance"]["property"] == "receipt-invalid"


def test_mixed_claim_and_simulated_execution_receipts_cannot_report_property_evidence(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    import_claim_receipt(session, manifest_digest, contract_digest, kind="evidence")
    import_current_receipt(session)

    # When
    result, status = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )

    # Then
    assert result.exit_code == 1
    assert status["execution_receipts_current"] is True
    assert status["execution_receipts_creditable"] is False
    assert status["assurance"]["property"] == "not-run"


def test_simulated_execution_outcomes_cannot_report_property_evidence(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    importer = receipt_import_module()
    successful = verification_receipt(session, manifest_digest, contract_digest)
    failing = verification_receipt(session, manifest_digest, contract_digest)
    failing.update(
        {
            "receipt_id": "receipt-simulated-nonzero",
            "nonce": "nonce-simulated-nonzero",
            "outcome": "nonzero",
        },
    )
    importer.import_receipt(session, json.dumps(successful), now=NOW)
    importer.import_receipt(session, json.dumps(failing), now=NOW)

    # When
    result, status = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )

    # Then
    assert result.exit_code == 1
    assert status["execution_receipts_current"] is True
    assert status["execution_receipts_creditable"] is False
    assert status["assurance"]["property"] == "not-run"


def test_duplicate_stored_nonce_fails_the_execution_receipt_gate(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    importer = receipt_import_module()
    imported = importer.import_receipt(
        session,
        json.dumps(verification_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )
    contract = receipt_contract_module()
    stored_path = session / "receipts" / f"{imported.receipt_digest}.json"
    stored = contract.StoredReceipt.model_validate_json(
        stored_path.read_text(encoding="utf-8")
    )
    duplicate_envelope = stored.envelope.model_copy(
        update={"receipt_id": "receipt-simulated-duplicate"}
    )
    duplicate = contract.StoredReceipt(
        envelope=duplicate_envelope,
        receipt_digest=contract.receipt_digest(duplicate_envelope),
        trust_level=stored.trust_level,
        settlement_credit=stored.settlement_credit,
    )
    (session / "receipts" / "duplicate-nonce.json").write_text(
        json.dumps(duplicate.model_dump(mode="json")),
        encoding="utf-8",
    )

    # When
    result, status = status_json(
        session,
        "--gate",
        "--require-manifest",
        "--require-execution-receipts",
    )

    # Then
    assert result.exit_code == 1
    assert status["execution_receipts_current"] is False
    assert status["execution_receipts_reason"] == "replayed nonce in stored receipts"
    assert status["assurance"]["property"] == "receipt-invalid"


def test_receipt_becomes_stale_after_a_new_seal(tmp_path: Path) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    import_current_receipt(session)
    decisions = session / "decisions.jsonl"
    decisions.write_text('{"decision":"reseal"}\n', encoding="utf-8")
    session_manifest.seal_session(session)

    # When
    result, payload = status_json(session, "--require-execution-receipts")

    # Then
    assert result.exit_code == 1
    assert payload["snapshot_complete"] is True
    assert payload["execution_receipts_current"] is False
    assert "manifest_digest" in payload["execution_receipts_reason"]


def test_malformed_imported_receipt_is_not_current(tmp_path: Path) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    import_current_receipt(session)
    stored = next((session / "receipts").glob("*.json"))
    stored.write_text('{"not":"a receipt"}\n', encoding="utf-8")

    # When
    result, payload = status_json(session, "--require-execution-receipts")

    # Then
    assert result.exit_code == 1
    assert payload["execution_receipts_current"] is False
    assert "invalid stored receipt" in payload["execution_receipts_reason"]
    assert payload["assurance"]["property"] == "receipt-invalid"


@pytest.mark.parametrize("fixture", (V0_READY, V1_READY))
@pytest.mark.parametrize(
    ("option", "message"),
    (
        (
            "--require-manifest",
            "a source manifest was requested, but this session is schema v0/v1; "
            "migrate through the v2 session lifecycle before requiring a source manifest",
        ),
        (
            "--require-execution-receipts",
            "execution receipts were requested, but this session is schema v0/v1; "
            "migrate through the v2 session lifecycle before requiring execution receipts",
        ),
    ),
)
def test_v0_v1_normal_status_is_unchanged_and_v2_flag_guides_migration(
    tmp_path: Path,
    fixture: Path,
    option: str,
    message: str,
) -> None:
    # Given
    session = tmp_path / fixture.name
    shutil.copytree(fixture, session)

    # When
    normal, payload = status_json(session)
    required, migration = status_json(session, option)

    # Then
    assert normal.exit_code == 0, normal.output
    assert "execution_receipts_current" not in payload
    assert required.exit_code == 1
    assert migration == {"migration_guidance": message}
