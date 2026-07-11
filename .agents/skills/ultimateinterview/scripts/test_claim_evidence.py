#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run --python 3.14 test_claim_evidence.py
# 3. Or make executable and run:
#      chmod +x test_claim_evidence.py && ./test_claim_evidence.py
# ─────────────────

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claim_evidence import (  # noqa: E402
    ClaimEvidence,
    ClaimEvidenceSet,
    ClaimKind,
    DecisionAuthority,
    Derivation,
    EpistemicAuthority,
    EvidenceChannel,
    EvidenceDelta,
    Freshness,
    ProvenanceMode,
    SourceActor,
    accepts_explicit_single_source,
    compatibility_independence_groups,
    eligible_independence_groups,
)


def firsthand(
    *,
    evidence_id: str = "ev-1",
    channel: EvidenceChannel = EvidenceChannel.FROM_CODE,
    group: str = "repo-state",
    decision: DecisionAuthority = DecisionAuthority.NONE,
    authority: EpistemicAuthority = EpistemicAuthority.ESTABLISHES,
    freshness: Freshness = Freshness.CURRENT,
) -> ClaimEvidence:
    return ClaimEvidence(
        id=evidence_id,
        channel=channel,
        claim_kind=ClaimKind.OBSERVED_FACT,
        source_actor=SourceActor.REPOSITORY,
        provenance_mode=ProvenanceMode.FIRSTHAND,
        derivation=None,
        independence_group=group,
        observed_at=None,
        environment=None,
        freshness=freshness,
        warrant="The repository content directly exhibits the claim.",
        counterevidence=(),
        epistemic_authority=authority,
        decision_authority=decision,
    )


def test_claim_evidence_rejects_unknown_fields() -> None:
    # Given: an otherwise valid evidence record with an undeclared field.
    payload = firsthand().model_dump(mode="json")
    payload["confidence"] = 1

    # When / Then: boundary parsing fails closed.
    with pytest.raises(ValidationError, match="confidence"):
        ClaimEvidence.model_validate(payload)


def test_public_models_reject_python_coercion() -> None:
    # Given: coercible primitives at each public model boundary.
    derivation = {"derived_from": [1], "method": "summary"}
    record = firsthand().model_dump()
    record["observed_at"] = 0

    # When / Then: strict parsing rejects rather than normalizing them.
    with pytest.raises(ValidationError):
        Derivation.model_validate(derivation)
    with pytest.raises(ValidationError):
        ClaimEvidence.model_validate(record)
    with pytest.raises(ValidationError):
        ClaimEvidenceSet.model_validate({"schema_version": True})
    with pytest.raises(ValidationError):
        EvidenceDelta.model_validate({"schema_version": True})


def test_evidence_set_rejects_duplicate_ids() -> None:
    # Given: two records with the same stable identity.
    records = (firsthand(), firsthand(channel=EvidenceChannel.FROM_DOCS, group="docs"))

    # When / Then: collection parsing rejects the ambiguous lineage.
    with pytest.raises(ValidationError, match="duplicate evidence id"):
        ClaimEvidenceSet(evidence_records=records)


def test_supplied_channel_projection_must_match_records_exactly() -> None:
    # Given: a v1 record whose supplied legacy projection names another channel.
    records = (firsthand(),)

    # When / Then: records remain authoritative and the stale projection fails.
    with pytest.raises(ValidationError, match="projected channels"):
        ClaimEvidenceSet(
            evidence_records=records,
            evidence_channels=(EvidenceChannel.FROM_USER,),
        )


def test_omitted_channel_projection_is_derived_from_records() -> None:
    # Given: v1 evidence records without a compatibility projection.
    evidence = ClaimEvidenceSet(
        evidence_records=(
            firsthand(channel=EvidenceChannel.FROM_USER),
            firsthand(
                evidence_id="ev-2",
                channel=EvidenceChannel.FROM_CODE,
                group="repo-state-2",
            ),
        ),
    )

    # When: the projected channel view is requested.
    projected = evidence.projected_channels

    # Then: it is deterministically derived from authoritative records.
    assert projected == (EvidenceChannel.FROM_CODE, EvidenceChannel.FROM_USER)


def test_derived_record_requires_derivation() -> None:
    # Given: a record marked derived without a lineage edge.
    payload = firsthand(evidence_id="derived").model_dump()
    payload["provenance_mode"] = ProvenanceMode.DERIVED

    # When / Then: the record is rejected at its trust boundary.
    with pytest.raises(ValidationError, match="requires derivation"):
        ClaimEvidence.model_validate(payload)


def test_derived_record_must_keep_root_independence_group() -> None:
    # Given: a derived restatement claiming a new causal group.
    root = firsthand()
    derived = ClaimEvidence.model_validate(
        {
            **root.model_dump(),
            "id": "ev-derived",
            "provenance_mode": ProvenanceMode.DERIVED,
            "derivation": Derivation(derived_from=(root.id,), method="summary"),
            "independence_group": "invented-independent-group",
        },
    )

    # When / Then: collection validation rejects independence inflation.
    with pytest.raises(ValidationError, match="root independence group"):
        ClaimEvidenceSet(evidence_records=(root, derived))


@pytest.mark.parametrize("missing", ["observed_at", "environment"])
def test_runtime_observation_requires_time_and_environment(missing: str) -> None:
    # Given: a firsthand runtime observation missing one context coordinate.
    payload = firsthand().model_dump()
    payload.update(
        source_actor=SourceActor.RUNTIME,
        observed_at=datetime(2026, 7, 10, 12, tzinfo=UTC),
        environment="staging",
    )
    payload[missing] = None

    # When / Then: the context-free runtime claim is rejected.
    with pytest.raises(ValidationError, match="runtime observation"):
        ClaimEvidence.model_validate(payload)


@pytest.mark.parametrize("field", ["source_actor", "warrant", "independence_group"])
def test_required_text_coordinates_reject_blank(field: str) -> None:
    # Given: a required evidentiary coordinate containing only whitespace.
    payload = firsthand().model_dump()
    payload[field] = "   "

    # When / Then: strict parsing rejects the malformed record.
    with pytest.raises(ValidationError):
        ClaimEvidence.model_validate(payload)


@pytest.mark.parametrize(
    ("freshness", "authority"),
    [
        (Freshness.STALE, EpistemicAuthority.ESTABLISHES),
        (Freshness.UNKNOWN, EpistemicAuthority.ESTABLISHES),
        (Freshness.CURRENT, EpistemicAuthority.CORROBORATES),
        (Freshness.CURRENT, EpistemicAuthority.HYPOTHESIS_ONLY),
    ],
)
def test_only_current_establishing_records_are_eligible(
    freshness: Freshness,
    authority: EpistemicAuthority,
) -> None:
    # Given: evidence lacking either currentness or establishing authority.
    record = firsthand(freshness=freshness, authority=authority)

    # When: causal independence credit is computed.
    groups = eligible_independence_groups((record,))

    # Then: the record contributes no group.
    assert groups == frozenset()


def test_same_group_across_channels_counts_once() -> None:
    # Given: code and docs records derived from the same causal source.
    records = (
        firsthand(channel=EvidenceChannel.FROM_CODE, group="shared-spec"),
        firsthand(
            evidence_id="ev-2",
            channel=EvidenceChannel.FROM_DOCS,
            group="shared-spec",
        ),
    )

    # When / Then: channel diversity does not inflate independence.
    assert eligible_independence_groups(records) == frozenset({"shared-spec"})


def test_same_channel_with_independent_groups_counts_twice() -> None:
    # Given: two independent operators reported through the user channel.
    records = (
        firsthand(channel=EvidenceChannel.FROM_USER, group="operator-a"),
        firsthand(
            evidence_id="ev-2",
            channel=EvidenceChannel.FROM_USER,
            group="operator-b",
        ),
    )

    # When / Then: causal routes, not channel names, determine the count.
    assert eligible_independence_groups(records) == frozenset({"operator-a", "operator-b"})


def test_derived_model_prior_cannot_launder_eligible_group() -> None:
    # Given: a model prior restated as derived establishing evidence.
    root = ClaimEvidence(
        id="prior",
        channel=EvidenceChannel.ASSUMPTION,
        claim_kind=ClaimKind.CAUSAL_HYPOTHESIS,
        source_actor=SourceActor.MODEL,
        provenance_mode=ProvenanceMode.MODEL_PRIOR,
        independence_group="model-prior",
        freshness=Freshness.CURRENT,
        warrant="Model prior only.",
        epistemic_authority=EpistemicAuthority.HYPOTHESIS_ONLY,
    )
    derived = ClaimEvidence(
        id="derived",
        channel=EvidenceChannel.FROM_CODE,
        claim_kind=ClaimKind.OBSERVED_FACT,
        source_actor=SourceActor.REPOSITORY,
        provenance_mode=ProvenanceMode.DERIVED,
        derivation=Derivation(derived_from=(root.id,), method="Restated prior"),
        independence_group=root.independence_group,
        freshness=Freshness.CURRENT,
        warrant="Derived restatement.",
        epistemic_authority=EpistemicAuthority.ESTABLISHES,
    )
    # When / Then: the derived restatement is rejected before eligibility.
    with pytest.raises(ValidationError, match="hypothesis-only lineage"):
        ClaimEvidenceSet(evidence_records=(root, derived))


@pytest.mark.parametrize(
    "authority",
    [DecisionAuthority.OWNER, DecisionAuthority.DELEGATED],
)
def test_explicit_single_source_acceptance_requires_decision_authority(
    authority: DecisionAuthority,
) -> None:
    # Given: one eligible causal group accepted by a legitimate decider.
    records = (firsthand(decision=authority),)

    # When / Then: the explicit waiver is recognized without triangulation.
    assert accepts_explicit_single_source(records)


def test_decision_authority_never_creates_epistemic_credit() -> None:
    # Given: an owner-endorsed record that only supports a hypothesis.
    record = firsthand(
        decision=DecisionAuthority.OWNER,
        authority=EpistemicAuthority.CORROBORATES,
    )

    # When / Then: authority cannot manufacture an eligible evidence group.
    assert eligible_independence_groups((record,)) == frozenset()
    assert not accepts_explicit_single_source((record,))


@pytest.mark.parametrize("mode", [ProvenanceMode.MODEL_PRIOR, ProvenanceMode.ASSUMPTION])
def test_model_prior_and_assumption_are_hypothesis_only(mode: ProvenanceMode) -> None:
    # Given: a model-only source incorrectly marked as establishing an observed fact.
    payload = firsthand().model_dump()
    payload.update(
        channel=EvidenceChannel.ASSUMPTION,
        claim_kind=ClaimKind.OBSERVED_FACT,
        source_actor=SourceActor.MODEL,
        provenance_mode=mode,
        epistemic_authority=EpistemicAuthority.ESTABLISHES,
    )

    # When / Then: the claim cannot cross the evidence boundary.
    with pytest.raises(ValidationError, match="hypothesis-only"):
        ClaimEvidence.model_validate(payload)


@pytest.mark.parametrize("authority", ["establishes", "corroborates"])
def test_assumption_channel_is_hypothesis_only_regardless_of_provenance(
    authority: str,
) -> None:
    # Given: a firsthand observed-fact claim placed in the assumption channel.
    payload = firsthand().model_dump(mode="json")
    payload.update(channel="assumption", epistemic_authority=authority)

    # When / Then: the channel itself forces hypothesis-only treatment.
    with pytest.raises(ValidationError, match="assumption channel is hypothesis-only"):
        ClaimEvidence.model_validate_json(json.dumps(payload))


def test_corroborating_non_assumption_record_parses_without_establishing_credit() -> None:
    # Given: current firsthand code evidence that corroborates but does not establish.
    payload = firsthand().model_dump(mode="json")
    payload["epistemic_authority"] = "corroborates"

    # When: the record crosses the JSON boundary.
    record = ClaimEvidence.model_validate_json(json.dumps(payload))

    # Then: it parses but contributes no establishing independence group.
    assert eligible_independence_groups((record,)) == frozenset()


def test_v0_channels_map_to_one_compatibility_group_each() -> None:
    # Given: aliased and repeated legacy channels plus an assumption.
    channels = ("code", "from-code", "from-user", "assumption")

    # When: v0 compatibility groups are projected.
    groups = compatibility_independence_groups(channels)

    # Then: each real channel contributes exactly one synthetic group.
    assert groups == frozenset({"compat:from-code", "compat:from-user"})


def test_evidence_delta_enforces_versioned_update_surface() -> None:
    # Given / When / Then: legacy uses add_channels and v1 uses structured records.
    assert EvidenceDelta(schema_version=0, add_channels=(EvidenceChannel.FROM_CODE,))
    assert EvidenceDelta(schema_version=1, add_evidence_records=(firsthand(),))
    with pytest.raises(ValidationError, match="legacy-only"):
        EvidenceDelta(schema_version=1, add_channels=(EvidenceChannel.FROM_CODE,))
    with pytest.raises(ValidationError, match="v1"):
        EvidenceDelta(schema_version=0, add_evidence_records=(firsthand(),))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
