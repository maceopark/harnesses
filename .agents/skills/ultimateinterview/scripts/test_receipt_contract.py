#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts import receipt_contract, session_manifest, validator_boundary
from scripts.receipt_test_support import (
    NOW,
    V2_READY,
    probe_receipt,
    receipt_contract_module,
    receipt_import_module,
    sealed_session,
    verification_receipt,
)


def test_task3_sealed_session_baseline_is_available_for_receipt_import(
    tmp_path: Path,
) -> None:
    # Given / When
    session, _, _ = sealed_session(tmp_path)

    # Then
    assert session_manifest.manifest_status(session).snapshot_complete is True


def test_receipt_directory_open_flags_preserve_posix_nofollow_and_pass_boundary(
    tmp_path: Path,
) -> None:
    # Given
    importer = receipt_import_module()
    changed_paths = tmp_path / "changed-paths.txt"
    _ = changed_paths.write_text(
        ".agents/skills/ultimateinterview/scripts/receipt_import.py\n",
        encoding="utf-8",
    )
    workspace_root = Path(__file__).resolve().parents[4]

    # When
    flags = importer._directory_open_flags()
    diagnostics = validator_boundary.validate(workspace_root, changed_paths)

    # Then
    assert flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    assert diagnostics == ()


def test_simulated_verification_receipt_imports_with_zero_settlement_credit(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)

    # When
    imported = receipt_import_module().import_receipt(
        session,
        json.dumps(payload),
        now=NOW,
    )

    # Then
    contract = receipt_contract_module()
    assert imported.trust_level is contract.TrustLevel.SIMULATED
    assert imported.settlement_credit == 0
    assert (session / "receipts" / f"{imported.receipt_digest}.json").is_file()
    assert session_manifest.manifest_status(session).snapshot_complete is True


def test_simulated_fixture_template_materializes_only_a_current_binding(
    tmp_path: Path,
) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)
    template = (V2_READY / "simulated-receipt.json").read_text(encoding="utf-8")

    # When
    imported = receipt_import_module().import_receipt(session, template, now=NOW)

    # Then
    assert imported.trust_level is receipt_contract_module().TrustLevel.SIMULATED
    assert imported.settlement_credit == 0


def test_import_rejects_absent_or_malformed_receipt_envelopes(tmp_path: Path) -> None:
    # Given
    session, _, _ = sealed_session(tmp_path)

    # When / Then
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="malformed receipt envelope"
    ):
        receipt_import_module().import_receipt(session, "{}", now=NOW)
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="malformed receipt envelope"
    ):
        receipt_import_module().import_receipt(session, "not-json", now=NOW)


@pytest.mark.parametrize("field", ("manifest_digest", "contract_digest"))
def test_import_rejects_receipt_with_wrong_seal_or_contract_binding(
    tmp_path: Path,
    field: str,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    payload[field] = "0" * 64

    # When / Then
    with pytest.raises(receipt_import_module().ReceiptImportError, match=field):
        receipt_import_module().import_receipt(session, json.dumps(payload), now=NOW)


def test_import_rejects_changed_verification_action_digest(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    payload["action_digest"] = "0" * 64

    # When / Then
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="action_digest"
    ):
        receipt_import_module().import_receipt(session, json.dumps(payload), now=NOW)


@pytest.mark.parametrize("value", (None, "0" * 64))
def test_probe_receipt_requires_canonical_observation_spec_digest(
    tmp_path: Path,
    value: str | None,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(
        tmp_path, with_probe=True
    )
    payload = probe_receipt(session, manifest_digest, contract_digest)
    payload["observation_spec_digest"] = value

    # When / Then
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="observation_spec_digest"
    ):
        receipt_import_module().import_receipt(session, json.dumps(payload), now=NOW)


def test_import_rejects_expired_and_replayed_nonces(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    expired = verification_receipt(session, manifest_digest, contract_digest)
    expired["expires_at"] = "2026-07-11T11:59:59Z"
    current = verification_receipt(session, manifest_digest, contract_digest)

    # When / Then
    with pytest.raises(receipt_import_module().ReceiptImportError, match="expired"):
        receipt_import_module().import_receipt(session, json.dumps(expired), now=NOW)
    receipt_import_module().import_receipt(session, json.dumps(current), now=NOW)
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="replayed nonce"
    ):
        receipt_import_module().import_receipt(session, json.dumps(current), now=NOW)


def test_import_rejects_replayed_nonce_after_receipts_swap_and_restore_during_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the first receipt occupies the pinned directory with its nonce.
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    importer = receipt_import_module()
    importer.import_receipt(session, json.dumps(payload), now=NOW)
    payload["receipt_id"] = "receipt-simulated-swap-duplicate"
    receipts = session / "receipts"
    displaced = tmp_path / "displaced-receipts"
    original_scandir = importer.os.scandir
    swapped = False

    def swap_receipts_during_scan(path: Path | int) -> os.ScandirIterator[str]:
        nonlocal swapped
        if not swapped:
            swapped = True
            os.replace(receipts, displaced)
            receipts.mkdir()
            try:
                return original_scandir(path)
            finally:
                os.rmdir(receipts)
                os.replace(displaced, receipts)
        return original_scandir(path)

    monkeypatch.setattr(importer.os, "scandir", swap_receipts_during_scan)

    # When / Then: the original pinned directory must still reject its nonce.
    with pytest.raises(importer.ReceiptImportError, match="replayed nonce"):
        importer.import_receipt(session, json.dumps(payload), now=NOW)

    assert swapped is True
    assert len(tuple(receipts.glob("*.json"))) == 1


def test_import_rejects_a_late_receipts_symlink_without_writing_outside_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a valid receipt and an attacker-controlled directory outside the session.
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    importer = receipt_import_module()
    outside = tmp_path / "outside-session"
    displaced = tmp_path / "displaced-receipts"
    outside.mkdir()
    original_render = importer._stored_json

    def replace_receipts_before_publish(record: receipt_contract.StoredReceipt) -> str:
        receipts = session / "receipts"
        receipts.rename(displaced)
        receipts.symlink_to(outside, target_is_directory=True)
        return original_render(record)

    monkeypatch.setattr(importer, "_stored_json", replace_receipts_before_publish)

    # When / Then: the late replacement is rejected before any target can be published.
    with pytest.raises(importer.ReceiptImportError, match="receipts directory changed"):
        importer.import_receipt(session, json.dumps(payload), now=NOW)

    assert not tuple(outside.iterdir())
    assert not tuple(displaced.iterdir())


def test_import_rejects_revoked_and_rotated_issuer_epochs(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    contract = receipt_contract_module()
    rotated = contract.StaticTrustRegistry(
        issuers=(
            contract.IssuerRecord(
                issuer_id="fixture-simulated",
                key_epoch="fixture-epoch-2",
                trust_level=contract.TrustLevel.SIMULATED,
                revoked=False,
            ),
        ),
        revoked_nonces=(),
    )
    revoked = contract.StaticTrustRegistry(
        issuers=(
            contract.IssuerRecord(
                issuer_id="fixture-simulated",
                key_epoch="fixture-epoch-1",
                trust_level=contract.TrustLevel.SIMULATED,
                revoked=True,
            ),
        ),
        revoked_nonces=(),
    )

    # When / Then
    with pytest.raises(receipt_import_module().ReceiptImportError, match="key epoch"):
        receipt_import_module().import_receipt(
            session, json.dumps(payload), now=NOW, registry=rotated
        )
    with pytest.raises(
        receipt_import_module().ReceiptImportError, match="issuer is revoked"
    ):
        receipt_import_module().import_receipt(
            session, json.dumps(payload), now=NOW, registry=revoked
        )


def test_mutated_stored_receipt_is_invalid(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    imported = receipt_import_module().import_receipt(
        session,
        json.dumps(verification_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )
    stored_path = session / "receipts" / f"{imported.receipt_digest}.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["artifact_digest"] = "e" * 64
    stored_path.write_text(json.dumps(stored), encoding="utf-8")

    # When
    invalid = receipt_import_module().receipt_status(session, now=NOW)

    # Then
    assert invalid.current is False
    assert "digest" in invalid.reason


def test_reseal_makes_an_imported_receipt_stale_by_manifest_digest(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    receipt_import_module().import_receipt(
        session,
        json.dumps(verification_receipt(session, manifest_digest, contract_digest)),
        now=NOW,
    )

    # When
    session_manifest.seal_session(session)
    stale = receipt_import_module().receipt_status(session, now=NOW)

    # Then
    assert stale.current is False
    assert "manifest_digest" in stale.reason


def test_receipt_status_reports_simulated_execution_as_current_but_noncreditable(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    evidence = verification_receipt(session, manifest_digest, contract_digest)
    evidence.update(
        {
            "receipt_id": "receipt-evidence-001",
            "kind": "evidence",
            "nonce": "nonce-evidence-001",
            "action_digest": None,
            "claim_digest": "e" * 64,
            "verification_id": None,
        },
    )
    execution = verification_receipt(session, manifest_digest, contract_digest)
    importer = receipt_import_module()
    importer.import_receipt(session, json.dumps(evidence), now=NOW)
    importer.import_receipt(session, json.dumps(execution), now=NOW)
    (session / ".session-update.lock").unlink(missing_ok=True)

    # When
    status = importer.receipt_status(session, now=NOW)

    # Then
    contract = receipt_contract_module()
    assert status.current is True
    assert status.creditable is False
    assert status.count == 2
    assert status.execution_kinds == (contract.ReceiptKind.VERIFICATION,)
    assert status.execution_outcomes == ()
    assert not (session / ".session-update.lock").exists()


def test_receipt_status_revalidates_duplicate_stored_nonces_after_mutation(
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
    status = importer.receipt_status(session, now=NOW)

    # Then
    assert status.current is False
    assert status.reason == "replayed nonce in stored receipts"


def test_injected_test_only_and_default_provider_free_trust_never_settle_high_impact(
    tmp_path: Path,
) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    contract = receipt_contract_module()
    registry = contract.StaticTrustRegistry(
        issuers=(
            contract.IssuerRecord(
                issuer_id="fixture-simulated",
                key_epoch="fixture-epoch-1",
                trust_level=contract.TrustLevel.TEST_ONLY,
                revoked=False,
            ),
        ),
        revoked_nonces=(),
    )

    # When
    default_import = receipt_import_module().import_receipt(
        session, json.dumps(payload), now=NOW
    )
    payload["receipt_id"] = "receipt-test-only-002"
    payload["nonce"] = "nonce-test-only-002"
    injected_import = receipt_import_module().import_receipt(
        session,
        json.dumps(payload),
        now=NOW,
        registry=registry,
    )

    # Then
    assert default_import.settlement_credit == 0
    assert injected_import.trust_level is contract.TrustLevel.TEST_ONLY
    assert injected_import.settlement_credit == 0
