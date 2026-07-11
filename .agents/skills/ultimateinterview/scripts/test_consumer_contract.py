#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts import (
    ambiguity_ledger,
    build_contract,
    build_contract_schema,
    implementation_gate,
    protocol_state,
    receipt_contract,
)

V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready" / "handoff.md"
V2_PROTOCOL = V2_READY.with_name("protocol.json")
MISSING_RECEIPT_BINDING = (
    Path(__file__).parent
    / "integration_fixtures"
    / "v2-negative"
    / "consumer-missing-receipt-binding"
    / "handoff.md"
)

CONSUMER_ROWS = """## Consumer Verification

| Grant kind | Receipt kind | Required ID | Target | Environment / scope | Outcome | Expected exit | Run policy | Auto execute |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| implementation-readiness | verification | VER-001 | REQ-001 | local | success | 0 | safe-auto | yes |
| implementation-readiness | verification | VER-002 | REQ-001 | local | success | 0 | manual | no |
| probe | probe | PROBE-L0-fixture | REQ-001 | l0:local | success | 0 | manual | no |

"""


def handoff_with_consumer_rows() -> str:
    handoff = V2_READY.read_text(encoding="utf-8")
    if "## Consumer Verification\n" in handoff:
        return handoff
    return handoff.replace("## Deferred Risks\n", CONSUMER_ROWS + "## Deferred Risks\n", 1)


def test_v2_contract_requires_consumer_verification_rows() -> None:
    # Given
    handoff = handoff_with_consumer_rows().replace(CONSUMER_ROWS, "", 1)

    # When / Then
    with pytest.raises(build_contract.BuildContractCompileError, match="Consumer Verification"):
        build_contract.compile_handoff(handoff)


def test_v2_gate_requires_consumer_verification_section() -> None:
    handoff = handoff_with_consumer_rows().replace(CONSUMER_ROWS, "", 1)

    assert implementation_gate.v2_consumer_verification_failures(handoff) == (
        "BuildContract v2 requires Consumer Verification",
    )


def test_v2_gate_reports_consumer_recompilation_failure_without_raising() -> None:
    handoff = handoff_with_consumer_rows().replace(CONSUMER_ROWS, "", 1)
    source_part1_sha256 = implementation_gate.contract_digest(handoff)
    contract = consumer_contract()
    body = build_contract_schema.ContractBody.model_validate(
        {
            **contract.model_dump(exclude={"contract_digest"}),
            "source_part1_sha256": source_part1_sha256,
        },
    )
    sidecar = build_contract_schema.BuildContract.model_validate(
        {
            **body.model_dump(),
            "contract_digest": build_contract_schema.body_digest(body),
        },
    )
    protocol = fixture_protocol().model_copy(
        update={"build_contract_digest": source_part1_sha256},
    )
    ledger_summary = ambiguity_ledger.AmbiguitySummary(
        active_count=0,
        deferred_count=0,
        residual=0,
        denominator=0,
        ambiguity_percent=0.0,
        display_percent="0.0%",
        handoff_ready=True,
        blockers=(),
        triangulation_violations=(),
        triangulation_warnings=(),
        contested=(),
        top_drivers=(),
    )
    protocol_summary = protocol_state.ProtocolSummary(
        depth=protocol_state.Depth.MINIMAL,
        interactions_used=0,
        question_budget=0,
        interview_obligations=(),
        handoff_blockers=(),
        protocol_ready=True,
    )

    result = implementation_gate.evaluate(
        (),
        ledger_summary,
        protocol_summary,
        handoff,
        protocol=protocol,
        contract_sidecar=sidecar,
        raw_ledger_text="{}",
    )

    assert any("BuildContract v2 recompilation failed" in failure for failure in result.failures)


def test_consumer_verification_requires_exact_canonical_headers() -> None:
    handoff = handoff_with_consumer_rows().replace(
        "| Grant kind | Receipt kind | Required ID | Target | Environment / scope | Outcome | Expected exit | Run policy | Auto execute |",
        "| Grant kind | Receipt kind | Required ID | Target | Environment / scope | Outcome | Expected exit | Run policy | Auto execute | Auto execute |",
        1,
    )

    with pytest.raises(build_contract.BuildContractCompileError, match="exact canonical"):
        build_contract.compile_handoff(handoff)

    assert implementation_gate.v2_consumer_verification_failures(handoff) == (
        "Consumer Verification headers must be the exact canonical ordered set",
    )


def test_v2_contract_rejects_a_missing_verification_receipt_binding() -> None:
    handoff = MISSING_RECEIPT_BINDING.read_text(encoding="utf-8")

    with pytest.raises(ValidationError, match="lack implementation-readiness"):
        build_contract.compile_handoff(handoff)


def test_v2_contract_compiles_implementation_and_probe_grant_requirements() -> None:
    # Given
    handoff = handoff_with_consumer_rows()

    # When
    contract = build_contract.compile_handoff(handoff)

    # Then
    assert tuple(row.grant_kind.value for row in contract.consumer_verifications) == (
        "implementation-readiness",
        "implementation-readiness",
        "probe",
    )


@pytest.mark.parametrize("run_policy", ("manual", "credentialed", "destructive"))
def test_non_safe_consumer_verification_cannot_be_auto_executable(run_policy: str) -> None:
    # Given
    handoff = handoff_with_consumer_rows().replace(
        "| implementation-readiness | verification | VER-002 | REQ-001 | local | success | 0 | manual | no |",
        f"| implementation-readiness | verification | VER-002 | REQ-001 | local | success | 0 | {run_policy} | yes |",
        1,
    )

    # When / Then
    with pytest.raises((build_contract.BuildContractCompileError, ValueError), match="auto"):
        build_contract.compile_handoff(handoff)


@pytest.mark.parametrize(
    ("outcome", "expected_exit"),
    (
        ("success", "1"),
        ("nonzero", "0"),
        ("timeout", "0"),
        ("failure", "0"),
    ),
)
def test_consumer_outcome_has_a_coherent_expected_exit(
    outcome: str,
    expected_exit: str,
) -> None:
    handoff = handoff_with_consumer_rows().replace(
        "| implementation-readiness | verification | VER-002 | REQ-001 | local | success | 0 | manual | no |",
        "| implementation-readiness | verification | VER-002 | REQ-001 | local "
        f"| {outcome} | {expected_exit} | manual | no |",
        1,
    )

    with pytest.raises(ValidationError, match="expected exit"):
        build_contract.compile_handoff(handoff)


NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
MANIFEST_DIGEST = "a" * 64
SESSION_ID = "v2-ready"


def consumer_contract() -> build_contract_schema.BuildContract:
    return build_contract.compile_handoff(handoff_with_consumer_rows())


def fixture_protocol() -> protocol_state.ProtocolState:
    return protocol_state.parse_state(V2_PROTOCOL.read_text(encoding="utf-8"))


def test_v2_consumer_contract_binds_probe_requirement_to_persisted_decision() -> None:
    # Given
    contract = consumer_contract()
    protocol = fixture_protocol()

    # When / Then
    assert implementation_gate.v2_consumer_binding_failures(protocol, contract) == ()

    probe = contract.consumer_verifications[-1]
    wrong_scope = probe.model_copy(update={"environment_scope": "l1:behavioral-stub"})
    mismatched = contract.model_copy(
        update={
            "consumer_verifications": (
                *contract.consumer_verifications[:-1],
                wrong_scope,
            ),
        },
    )
    assert implementation_gate.v2_consumer_binding_failures(protocol, mismatched) == (
        "Consumer Verification probe environment/scope does not match persisted ProbeDecision",
    )


def implementation_grant_payload(
    contract: build_contract_schema.BuildContract,
) -> dict[str, object]:
    return {
        "session_id": SESSION_ID,
        "manifest_digest": MANIFEST_DIGEST,
        "source_part1_sha256": contract.source_part1_sha256,
        "contract_digest": contract.contract_digest,
        "policy_version": "v2-receipt-policy-1",
        "verification_id": "VER-001",
        "action_digest": receipt_contract.verification_action_digest(contract, "VER-001"),
        "target_ids": ("REQ-001",),
        "environment_scope": "local",
        "issuer_id": "fixture-issuer",
        "subject_digest": "b" * 64,
        "issued_at": "2026-07-11T11:00:00Z",
        "expires_at": "2026-07-12T11:00:00Z",
        "nonce": "nonce-consumer-verification",
        "outcome": build_contract_schema.ConsumerOutcome.SUCCESS,
        "exit_code": 0,
        "artifact_digest": "c" * 64,
        "stdout_digest": "d" * 64,
        "stderr_digest": "e" * 64,
    }


def probe_grant_payload(contract: build_contract_schema.BuildContract) -> dict[str, object]:
    decision = fixture_protocol().probe_decision
    assert decision is not None
    observation_spec_digest = receipt_contract.observation_spec_digest(decision)
    payload = implementation_grant_payload(contract)
    payload.pop("verification_id")
    return {
        **payload,
        "probe_id": "PROBE-L0-fixture",
        "environment_scope": "l0:local",
        "observation_spec_digest": observation_spec_digest,
        "action_digest": observation_spec_digest,
    }


def fixture_observation_spec_digest() -> str:
    decision = fixture_protocol().probe_decision
    assert decision is not None
    return receipt_contract.observation_spec_digest(decision)


def test_implementation_readiness_grant_binds_every_receipt_coordinate() -> None:
    # Given
    contract = consumer_contract()
    consumer = contract.consumer_verifications[0]
    grant = build_contract_schema.ImplementationReadinessGrant.model_validate(
        implementation_grant_payload(contract),
    )

    # When
    build_contract_schema.validate_consumer_grant(
        grant,
        consumer,
        session_id=SESSION_ID,
        manifest_digest=MANIFEST_DIGEST,
        contract=contract,
        now=NOW,
        consumed_nonces=frozenset(),
    )

    # Then
    assert grant.verification_id == "VER-001"


def test_grant_rejects_a_consumer_requirement_not_in_the_compiled_allowlist() -> None:
    contract = consumer_contract()
    grant = build_contract_schema.ImplementationReadinessGrant.model_validate(
        implementation_grant_payload(contract),
    )
    forged_consumer = contract.consumer_verifications[0].model_copy(
        update={"environment_scope": "forged-scope"},
    )

    with pytest.raises(build_contract_schema.ContractValidationError, match="not allowlisted"):
        build_contract_schema.validate_consumer_grant(
            grant,
            forged_consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("manifest_digest", "0" * 64, "manifest_digest"),
        ("contract_digest", "0" * 64, "contract_digest"),
        ("action_digest", "0" * 64, "action_digest"),
        ("verification_id", "VER-999", "verification_id"),
    ),
)
def test_implementation_grant_rejects_changed_receipt_bindings(
    field: str,
    value: str,
    message: str,
) -> None:
    # Given
    contract = consumer_contract()
    consumer = contract.consumer_verifications[0]
    payload = implementation_grant_payload(contract)
    payload[field] = value
    grant = build_contract_schema.ImplementationReadinessGrant.model_validate(payload)

    # When / Then
    with pytest.raises(build_contract_schema.ContractValidationError, match=message):
        build_contract_schema.validate_consumer_grant(
            grant,
            consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset(),
        )


def test_probe_grant_rejects_wrong_id_expiry_replay_and_missing_artifact() -> None:
    # Given
    contract = consumer_contract()
    consumer = contract.consumer_verifications[-1]
    payload = probe_grant_payload(contract)
    payload["probe_id"] = "PROBE-other"
    wrong_probe = build_contract_schema.ProbeGrant.model_validate(payload)

    # When / Then
    with pytest.raises(build_contract_schema.ContractValidationError, match="probe_id"):
        build_contract_schema.validate_consumer_grant(
            wrong_probe,
            consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset(),
            expected_probe_observation_spec_digest=fixture_observation_spec_digest(),
        )

    expired_payload = probe_grant_payload(contract)
    expired_payload["expires_at"] = "2026-07-11T11:30:00Z"
    expired = build_contract_schema.ProbeGrant.model_validate(expired_payload)
    with pytest.raises(build_contract_schema.ContractValidationError, match="expired"):
        build_contract_schema.validate_consumer_grant(
            expired,
            consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset(),
            expected_probe_observation_spec_digest=fixture_observation_spec_digest(),
        )

    current = build_contract_schema.ProbeGrant.model_validate(probe_grant_payload(contract))
    with pytest.raises(build_contract_schema.ContractValidationError, match="replayed"):
        build_contract_schema.validate_consumer_grant(
            current,
            consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset({current.nonce}),
            expected_probe_observation_spec_digest=fixture_observation_spec_digest(),
        )

    missing_artifact = probe_grant_payload(contract)
    del missing_artifact["artifact_digest"]
    with pytest.raises(ValidationError, match="artifact_digest"):
        build_contract_schema.ProbeGrant.model_validate(missing_artifact)


def test_probe_grant_requires_the_exact_task4_observation_spec_digest() -> None:
    contract = consumer_contract()
    consumer = contract.consumer_verifications[-1]
    payload = probe_grant_payload(contract)
    payload["action_digest"] = "f" * 64
    payload["observation_spec_digest"] = "f" * 64
    changed_spec = build_contract_schema.ProbeGrant.model_validate(payload)

    with pytest.raises(build_contract_schema.ContractValidationError, match="observation_spec_digest"):
        build_contract_schema.validate_consumer_grant(
            changed_spec,
            consumer,
            session_id=SESSION_ID,
            manifest_digest=MANIFEST_DIGEST,
            contract=contract,
            now=NOW,
            consumed_nonces=frozenset(),
            expected_probe_observation_spec_digest=fixture_observation_spec_digest(),
        )
