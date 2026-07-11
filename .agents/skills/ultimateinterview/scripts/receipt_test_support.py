#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from scripts import build_contract, build_contract_schema, implementation_gate, probe_policy, protocol_state, session_manifest

V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready"
NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def receipt_contract_module() -> ModuleType:
    from scripts import receipt_contract

    return receipt_contract


def receipt_import_module() -> ModuleType:
    from scripts import receipt_import

    return receipt_import


def sealed_session(tmp_path: Path, with_probe: bool = False) -> tuple[Path, str, str]:
    session = tmp_path / ".ultimateinterview" / "v2-ready"
    session.parent.mkdir()
    shutil.copytree(V2_READY, session)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8")
    contract = build_contract.compile_handoff(handoff)
    (session / "build-contract.json").write_text(
        build_contract.canonical_json(contract),
        encoding="utf-8",
    )
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["build_contract_digest"] = implementation_gate.contract_digest(handoff)
    if with_probe:
        decision = probe_policy.ProbeDecision.model_validate(
            {
                "probe_id": "PROBE-L0-receipt",
                "intent": "discovery",
                "discovery_probe_id": None,
                "selected_level": "L0",
                "target_ledger_ids": ["REQ-001"],
                "predicate": "The local validation command differs from the contract.",
                "contract_digest": contract.contract_digest,
                "sandboxable_observable": False,
                "requires_runtime_observation": False,
                "production_only": False,
                "previous_level_insufficiency": None,
                "skipped_level_reason": None,
                "execution_scope": None,
                "authorization": None,
            },
        )
        protocol["probe_decision"] = decision.model_dump(mode="json")
        protocol["probe_sequence"] = None
    protocol_state.parse_state(json.dumps(protocol))
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    manifest = session_manifest.seal_session(session)
    return session, manifest.manifest_digest, contract.contract_digest


def verification_receipt(
    session: Path,
    manifest_digest: str,
    contract_digest: str,
) -> dict[str, JsonValue]:
    contract = build_contract_schema.BuildContract.model_validate_json(
        (session / "build-contract.json").read_text(encoding="utf-8"),
    )
    action_digest = receipt_contract_module().verification_action_digest(contract, "VER-001")
    return {
        "schema_version": 2,
        "receipt_id": "receipt-simulated-001",
        "kind": "verification",
        "session_id": session.name,
        "manifest_digest": manifest_digest,
        "contract_digest": contract_digest,
        "policy_version": "v2-receipt-policy-1",
        "issuer_id": "fixture-simulated",
        "key_epoch": "fixture-epoch-1",
        "issued_at": "2026-07-11T11:00:00Z",
        "expires_at": "2026-07-12T11:00:00Z",
        "nonce": "nonce-simulated-001",
        "subject_digest": "a" * 64,
        "action_digest": action_digest,
        "claim_digest": None,
        "artifact_digest": "b" * 64,
        "stdout_digest": "c" * 64,
        "stderr_digest": "d" * 64,
        "verification_id": "VER-001",
        "probe_id": None,
        "observation_spec_digest": None,
        "outcome": "success",
        "impact_weight": 5,
        "declared_trust": "simulated",
    }


def probe_receipt(
    session: Path,
    manifest_digest: str,
    contract_digest: str,
) -> dict[str, JsonValue]:
    payload = verification_receipt(session, manifest_digest, contract_digest)
    decision = protocol_state.parse_state(
        (session / "protocol.json").read_text(encoding="utf-8"),
    ).probe_decision
    assert decision is not None
    observation_digest = receipt_contract_module().observation_spec_digest(decision)
    payload.update(
        {
            "receipt_id": "receipt-probe-001",
            "kind": "probe",
            "nonce": "nonce-probe-001",
            "action_digest": observation_digest,
            "verification_id": None,
            "probe_id": decision.probe_id,
            "observation_spec_digest": observation_digest,
        },
    )
    return payload
