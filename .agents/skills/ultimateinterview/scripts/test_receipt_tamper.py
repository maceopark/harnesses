#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.receipt_test_support import NOW, receipt_import_module, sealed_session, verification_receipt


def test_stored_evidence_claim_digest_tampering_is_rejected(tmp_path: Path) -> None:
    # Given
    session, manifest_digest, contract_digest = sealed_session(tmp_path)
    payload = verification_receipt(session, manifest_digest, contract_digest)
    payload.update(
        {
            "receipt_id": "receipt-evidence-001",
            "kind": "evidence",
            "nonce": "nonce-evidence-001",
            "action_digest": None,
            "claim_digest": "f" * 64,
            "verification_id": None,
        },
    )
    importer = receipt_import_module()
    imported = importer.import_receipt(session, json.dumps(payload), now=NOW)
    stored_path = session / "receipts" / f"{imported.receipt_digest}.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))
    stored["envelope"]["claim_digest"] = "0" * 64
    stored_path.write_text(json.dumps(stored), encoding="utf-8")

    # When
    status = importer.receipt_status(session, now=NOW)

    # Then
    assert status.current is False
    assert "digest" in status.reason
