#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0"]
# ///

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never

import pytest

from scripts import ambiguity_ledger, behavior_atoms, claim_evidence, evidence_identity, protocol_state, session_contracts

NOW = datetime(2026, 7, 11, 12, tzinfo=UTC)
SAME_ACTOR_FIXTURE = Path(__file__).parent / "integration_fixtures" / "v2-negative" / "same-actor-two-declared-groups" / "ledger.json"


def assertion(*, as_of: datetime = NOW, locator: str = "repo://artifact", artifact_digest: str = "a" * 64) -> evidence_identity.ClaimantAssertion:
    return evidence_identity.ClaimantAssertion(
        locator=locator,
        revision="revision-1",
        artifact_digest=artifact_digest,
        observer="reviewer",
        method="bounded-check",
        environment="test",
        as_of=as_of,
        ttl_seconds=3600,
        dependency_roots=("declared-shared-root",),
        authority_scope=("high-settlement",),
        issuer_id="claimant-issuer",
        key_epoch="key-1",
        revocation_epoch="epoch-1",
    )


def record(*, evidence_id: str, group: str, identity: evidence_identity.ClaimantAssertion, warrant: str = "The repository exposes the bounded claim.") -> claim_evidence.ClaimEvidence:
    return claim_evidence.ClaimEvidence(
        id=evidence_id,
        channel=claim_evidence.EvidenceChannel.FROM_CODE,
        claim_kind=claim_evidence.ClaimKind.OBSERVED_FACT,
        source_actor=claim_evidence.SourceActor.REPOSITORY,
        provenance_mode=claim_evidence.ProvenanceMode.FIRSTHAND,
        independence_group=group,
        observed_at=None,
        environment=None,
        freshness=claim_evidence.Freshness.CURRENT,
        warrant=warrant,
        epistemic_authority=claim_evidence.EpistemicAuthority.ESTABLISHES,
        decision_authority=claim_evidence.DecisionAuthority.NONE,
        identity_assertion=identity,
    )


def simulated_adapter(record: claim_evidence.ClaimEvidence) -> evidence_identity.StaticVerifierAdapter:
    request = evidence_identity.verification_request(record)
    return evidence_identity.StaticVerifierAdapter(
        evidence_identity.VerifierResult(
            trust=evidence_identity.VerifierTrust.SIMULATED,
            binding_digest=request.binding_digest,
            dependency_roots=("verified-shared-root",),
            authority_scope=("high-settlement",),
            issuer_id="claimant-issuer",
            key_epoch="key-1",
            revocation_epoch="epoch-1",
            revoked=False,
        ),
    )


def test_same_actor_and_dependencies_with_two_claimant_labels_cannot_create_creditable_roots() -> None:
    # Given
    identity = assertion()
    first = record(evidence_id="EV-001", group="label-a", identity=identity)
    second = record(evidence_id="EV-002", group="label-b", identity=identity)
    adapter = simulated_adapter(first)

    # When
    roots = evidence_identity.verifier_roots((first, second), adapter=adapter, now=NOW)

    # Then
    assert roots == frozenset()


def test_claimant_observation_from_year_2000_cannot_self_declare_current() -> None:
    # Given
    record_2000 = record(
        evidence_id="EV-2000",
        group="old-label",
        identity=assertion(as_of=datetime(2000, 1, 1, tzinfo=UTC)),
    )

    # When
    assessment = evidence_identity.assess(
        evidence_identity.verification_request(record_2000),
        adapter=simulated_adapter(record_2000),
        now=NOW,
        impact_weight=5,
    )

    # Then
    assert assessment.current is False
    assert assessment.settlement_credit == 0


def test_future_claimant_observation_cannot_self_declare_current() -> None:
    # Given
    future = record(
        evidence_id="EV-future",
        group="future-label",
        identity=assertion(as_of=NOW + timedelta(days=1)),
    )

    # When
    assessment = evidence_identity.assess(
        evidence_identity.verification_request(future),
        adapter=simulated_adapter(future),
        now=NOW,
        impact_weight=5,
    )

    # Then
    assert assessment.current is False
    assert assessment.settlement_credit == 0


def test_from_code_claim_cannot_name_a_user_as_its_actor() -> None:
    # Given
    payload = record(evidence_id="EV-conflict", group="group", identity=assertion()).model_dump()
    payload["source_actor"] = claim_evidence.SourceActor.USER

    # When / Then
    with pytest.raises(ValueError, match="from-code"):
        claim_evidence.ClaimEvidence.model_validate(payload)


def test_owner_label_cannot_waive_high_credit_without_verifier_authority() -> None:
    # Given
    claimant = record(evidence_id="EV-owner", group="owner-label", identity=assertion()).model_copy(
        update={"decision_authority": claim_evidence.DecisionAuthority.OWNER},
    )

    # When
    assessment = evidence_identity.assess(
        evidence_identity.verification_request(claimant),
        adapter=evidence_identity.ProviderFreeVerifierAdapter(),
        now=NOW,
        impact_weight=5,
    )

    # Then
    assert assessment.settlement_credit == 0


@pytest.mark.parametrize(
    "changed",
    (
        "warrant",
        "locator",
        "artifact_digest",
    ),
)
def test_changed_claim_binding_coordinate_invalidates_verifier_result(
    changed: Literal["warrant", "locator", "artifact_digest"],
) -> None:
    # Given
    original = record(evidence_id="EV-binding", group="binding", identity=assertion())
    adapter = simulated_adapter(original)
    match changed:
        case "warrant":
            mutated = original.model_copy(update={"warrant": "Changed warrant."})
        case "locator":
            mutated = original.model_copy(update={"identity_assertion": assertion(locator="repo://other")})
        case "artifact_digest":
            mutated = original.model_copy(update={"identity_assertion": assertion(artifact_digest="b" * 64)})
        case unreachable:
            assert_never(unreachable)

    # When
    assessment = evidence_identity.assess(
        evidence_identity.verification_request(mutated),
        adapter=adapter,
        now=NOW,
        impact_weight=5,
    )

    # Then
    assert assessment.binding_valid is False
    assert assessment.settlement_credit == 0


def test_revoked_verifier_epoch_is_rejected() -> None:
    # Given
    claimant = record(evidence_id="EV-revoked", group="revoked", identity=assertion())
    request = evidence_identity.verification_request(claimant)
    adapter = evidence_identity.StaticVerifierAdapter(
        evidence_identity.VerifierResult(
            trust=evidence_identity.VerifierTrust.SIMULATED,
            binding_digest=request.binding_digest,
            dependency_roots=("root",),
            authority_scope=("high-settlement",),
            issuer_id="claimant-issuer",
            key_epoch="key-1",
            revocation_epoch="epoch-1",
            revoked=True,
        ),
    )

    # When / Then
    with pytest.raises(evidence_identity.EvidenceIdentityError, match="revoked"):
        evidence_identity.assess(request, adapter=adapter, now=NOW, impact_weight=5)


def test_empty_and_simulated_verifiers_cannot_settle_high_claims() -> None:
    # Given
    claimant = record(evidence_id="EV-high", group="high-label", identity=assertion())

    # When
    untrusted = evidence_identity.assess(
        evidence_identity.verification_request(claimant),
        adapter=evidence_identity.ProviderFreeVerifierAdapter(),
        now=NOW,
        impact_weight=5,
    )
    simulated = evidence_identity.assess(
        evidence_identity.verification_request(claimant),
        adapter=simulated_adapter(claimant),
        now=NOW,
        impact_weight=5,
    )

    # Then
    assert untrusted.trust is evidence_identity.VerifierTrust.UNTRUSTED
    assert simulated.trust is evidence_identity.VerifierTrust.SIMULATED
    assert untrusted.settlement_credit == simulated.settlement_credit == 0


def test_injected_policy_adapter_serializes_as_non_authentic() -> None:
    # Given
    claimant = record(evidence_id="EV-fixture", group="fixture", identity=assertion())

    # When
    assessment = evidence_identity.assess(
        evidence_identity.verification_request(claimant),
        adapter=simulated_adapter(claimant),
        now=NOW + timedelta(minutes=1),
        impact_weight=5,
    )

    # Then
    assert assessment.model_dump(mode="json")["trust"] == "simulated"
    assert assessment.settlement_credit == 0


def test_ledger_credit_excludes_simulated_verifier_roots() -> None:
    # Given
    identity = assertion()
    entry = ambiguity_ledger.LedgerEntry(
        id="REQ-identity",
        requirement="Verifier roots remain authoritative.",
        origin="orientation",
        status="triangulated",
        ambiguity_score=0,
        impact_weight=5,
        evidence_records=(
            record(evidence_id="EV-ledger", group="claimant-label", identity=identity),
        ),
    )

    # When
    credit = entry.verifier_credit(adapter=simulated_adapter(entry.evidence_records[0]), now=NOW)

    # Then
    assert credit.roots == frozenset()
    assert credit.settlement_credit == 0


def test_v2_default_ledger_credit_does_not_treat_claimant_labels_as_roots() -> None:
    # Given
    identity = assertion()
    entry = ambiguity_ledger.LedgerEntry(
        id="REQ-untrusted-identity",
        requirement="Claimant labels require verifier roots.",
        origin="orientation",
        status="triangulated",
        ambiguity_score=0,
        impact_weight=5,
        assurance_class=behavior_atoms.AssuranceClass.HIGH,
        behavior_atoms=(
            behavior_atoms.BehaviorAtom(
                id="ATOM-901",
                condition="A claimant identity is declared.",
                polarity=behavior_atoms.AtomPolarity.MUST,
                observable_response="Verifier roots are required for settlement.",
            ),
        ),
        evidence_records=(
            record(evidence_id="EV-label-a", group="label-a", identity=identity),
            record(evidence_id="EV-label-b", group="label-b", identity=identity),
        ),
    )

    # When
    summary = ambiguity_ledger.summarize_ambiguity((entry,), evidence_schema_version=2)

    # Then
    assert entry.distinct_evidence_groups == frozenset()
    assert any("untrusted/collapsed provenance" in blocker for blocker in summary.blockers)


def test_same_actor_fixture_reports_untrusted_collapsed_provenance() -> None:
    # Given
    entries = ambiguity_ledger.parse_entries(SAME_ACTOR_FIXTURE.read_text(encoding="utf-8"))

    # When
    summary = ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=2)

    # Then
    assert summary.handoff_ready is False
    assert any("untrusted/collapsed provenance: REQ-001" in blocker for blocker in summary.blockers)


def test_protocol_exposes_identity_policy_only_for_v2() -> None:
    # Given
    v2 = protocol_state.parse_state(json.dumps({
        "depth": "minimal", "evidence_schema_version": 2, "contract_schema_version": 2,
        "assurance_result": {"abi": "fail", "trace": "fail", "property": "not-run", "adequacy": "not-assessed", "stakeholder": "not-sought"},
        "question_budget": 1, "interactions_used": 0, "answers_since_sweep": 0, "sweeps_run": 0,
        "contrarian_probes_run": 0, "falsification_checkpoints_run": 0, "lenses": {name: {"state": "skipped", "reason": "test"} for name in protocol_state.LENS_NAMES},
    }))
    v1 = v2.model_copy(update={"evidence_schema_version": 1, "contract_schema_version": 1, "assurance_result": None})

    # When / Then
    assert protocol_state.evidence_identity_policy_version(v2) == evidence_identity.POLICY_VERSION
    assert protocol_state.evidence_identity_policy_version(v1) is None


def test_session_contracts_preserve_identity_assertions_without_backfilling_legacy_records() -> None:
    # Given
    legacy: session_contracts.JsonObject = {"evidence_records": [], "evidence_channels": []}
    identified: session_contracts.JsonObject = {"evidence_records": [], "evidence_channels": []}
    plain_record = record(evidence_id="EV-plain", group="plain", identity=assertion()).model_copy(
        update={"identity_assertion": None},
    )
    identified_record = record(evidence_id="EV-identified", group="identified", identity=assertion())

    # When
    session_contracts.replace_evidence_records(legacy, (plain_record,), None)
    session_contracts.replace_evidence_records(identified, (identified_record,), None)

    # Then
    assert "identity_assertion" not in json.dumps(legacy)
    stored_identity = session_contracts.evidence_records(identified)[0].identity_assertion
    assert stored_identity is not None
    assert stored_identity.locator == "repo://artifact"
    assert session_contracts.material_signature(legacy) != session_contracts.material_signature(identified)
