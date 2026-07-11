#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run --python 3.14 test_claim_evidence_lineage.py
# 3. Or make executable and run:
#      chmod +x test_claim_evidence_lineage.py && ./test_claim_evidence_lineage.py
# ─────────────────

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ambiguity_ledger, claim_evidence, session_contracts  # noqa: E402

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def firsthand(evidence_id: str, group: str) -> dict[str, JsonValue]:
    return {
        "id": evidence_id,
        "channel": "from-code",
        "claim_kind": "observed-fact",
        "source_actor": "repository",
        "provenance_mode": "firsthand",
        "independence_group": group,
        "freshness": "current",
        "warrant": f"Observed {evidence_id}.",
        "epistemic_authority": "establishes",
        "decision_authority": "none",
    }


def hypothesis(
    evidence_id: str,
    group: str,
    provenance_mode: str = "model-prior",
) -> dict[str, JsonValue]:
    return {
        "id": evidence_id,
        "channel": "assumption",
        "claim_kind": "causal-hypothesis",
        "source_actor": "model",
        "provenance_mode": provenance_mode,
        "independence_group": group,
        "freshness": "current",
        "warrant": f"Hypothesized {evidence_id}.",
        "epistemic_authority": "hypothesis-only",
        "decision_authority": "none",
    }


def firsthand_hypothesis(evidence_id: str, group: str) -> dict[str, JsonValue]:
    record = hypothesis(evidence_id, group)
    record.update(
        channel="from-code",
        source_actor="repository",
        provenance_mode="firsthand",
    )
    return record


def derived(
    evidence_id: str,
    parents: list[str],
    group: str,
    *,
    hypothesis_only: bool = False,
) -> dict[str, JsonValue]:
    derived_from: list[JsonValue] = list(parents)
    derivation: dict[str, JsonValue] = {
        "derived_from": derived_from,
        "method": f"Derived {evidence_id}.",
    }
    return {
        "id": evidence_id,
        "channel": "from-code",
        "claim_kind": "causal-hypothesis" if hypothesis_only else "observed-fact",
        "source_actor": "repository",
        "provenance_mode": "derived",
        "derivation": derivation,
        "independence_group": group,
        "freshness": "current",
        "warrant": f"Derived warrant for {evidence_id}.",
        "epistemic_authority": "hypothesis-only" if hypothesis_only else "establishes",
        "decision_authority": "none",
    }


def parse_set(records: list[dict[str, JsonValue]]) -> claim_evidence.ClaimEvidenceSet:
    return claim_evidence.ClaimEvidenceSet.model_validate_json(
        json.dumps({"evidence_records": records}),
    )


@pytest.mark.parametrize(
    "root",
    [
        hypothesis("prior", "model-group"),
        hypothesis("prior", "model-group", "assumption"),
        firsthand_hypothesis("prior", "model-group"),
    ],
)
def test_direct_hypothesis_lineage_cannot_be_laundered(
    root: dict[str, JsonValue],
) -> None:
    # Given: an establishing derivative whose only parent is a model prior.
    records = [root, derived("restatement", ["prior"], "model-group")]

    # When / Then: collection parsing preserves the ancestor's hypothesis-only status.
    with pytest.raises(ValidationError, match="hypothesis-only lineage"):
        parse_set(records)


def test_transitive_hypothesis_lineage_cannot_be_laundered() -> None:
    # Given: a two-hop derivation that tries to establish a model prior as fact.
    records = [
        hypothesis("prior", "model-group"),
        derived("middle", ["prior"], "model-group", hypothesis_only=True),
        derived("laundered", ["middle"], "model-group"),
    ]

    # When / Then: transitive ancestry remains hypothesis-only.
    with pytest.raises(ValidationError, match="hypothesis-only lineage"):
        parse_set(records)


def test_missing_lineage_reference_is_rejected() -> None:
    # Given: a derived record referencing absent evidence.
    records = [derived("orphan", ["missing"], "repo-group")]

    # When / Then: the dangling lineage fails closed.
    with pytest.raises(ValidationError, match="unknown evidence id"):
        parse_set(records)


def test_duplicate_lineage_parent_is_rejected() -> None:
    # Given: a derived record repeating one immediate parent.
    records = [
        firsthand("root", "repo-group"),
        derived("duplicate", ["root", "root"], "repo-group"),
    ]

    # When / Then: duplicate lineage edges fail at the record boundary.
    with pytest.raises(ValidationError, match="derived_from evidence ids must be unique"):
        parse_set(records)


def test_self_referential_lineage_is_rejected() -> None:
    # Given: a derived record naming itself as its parent.
    records = [derived("self", ["self"], "repo-group")]

    # When / Then: the self-cycle is rejected as a graph cycle.
    with pytest.raises(ValidationError, match="Value error, evidence derivation cycle"):
        parse_set(records)


def test_cyclic_lineage_is_rejected() -> None:
    # Given: two derived records that reference each other.
    records = [
        derived("cycle-a", ["cycle-b"], "repo-group"),
        derived("cycle-b", ["cycle-a"], "repo-group"),
    ]

    # When / Then: graph validation reports the cycle.
    with pytest.raises(ValidationError, match="Value error, evidence derivation cycle"):
        parse_set(records)


def test_derived_record_cannot_rewrite_root_group() -> None:
    # Given: a derived record declaring a group different from its root.
    records = [firsthand("root", "repo-group"), derived("rewrite", ["root"], "new-group")]

    # When / Then: the causal group rewrite is rejected.
    with pytest.raises(ValidationError, match="root independence group"):
        parse_set(records)


def test_different_root_groups_cannot_collapse_into_one_source() -> None:
    # Given: one derivative combining two independent causal roots.
    records = [
        firsthand("root-a", "repo-a"),
        firsthand("root-b", "repo-b"),
        derived("collapsed", ["root-a", "root-b"], "synthetic-group"),
    ]

    # When / Then: the singular group cannot hide multiple independent roots.
    with pytest.raises(ValidationError, match="multiple root independence groups"):
        parse_set(records)


def test_legitimate_same_group_transitive_derivation_keeps_one_credit() -> None:
    # Given: a valid multi-hop restatement of one firsthand causal source.
    records = [
        firsthand("root", "repo-group"),
        derived("middle", ["root"], "repo-group"),
        derived("leaf", ["middle"], "repo-group"),
    ]

    # When: the structured lineage parses and eligibility is projected.
    evidence_set = parse_set(records)
    groups = claim_evidence.eligible_independence_groups(evidence_set.evidence_records)

    # Then: only the firsthand root contributes independence credit.
    assert groups == frozenset({"repo-group"})


def test_multiple_same_group_roots_remain_one_causal_source() -> None:
    # Given: two firsthand records already assigned to one causal group.
    records = [
        firsthand("root-a", "repo-group"),
        firsthand("root-b", "repo-group"),
        derived("joined", ["root-a", "root-b"], "repo-group"),
    ]

    # When / Then: the derivative is valid and still counts as one group.
    evidence_set = parse_set(records)
    assert claim_evidence.eligible_independence_groups(evidence_set.evidence_records) == frozenset(
        {"repo-group"},
    )


def test_hypothesis_only_chain_is_valid_but_ineligible() -> None:
    # Given: a transitive chain that honestly retains hypothesis-only authority.
    records = [
        hypothesis("prior", "model-group"),
        derived("middle", ["prior"], "model-group", hypothesis_only=True),
        derived("leaf", ["middle"], "model-group", hypothesis_only=True),
    ]

    # When / Then: the lineage parses without earning evidence credit.
    evidence_set = parse_set(records)
    assert claim_evidence.eligible_independence_groups(evidence_set.evidence_records) == frozenset()


def test_ledger_entry_rejects_laundered_lineage() -> None:
    # Given: a critical settled ledger entry backed only by a laundered prior.
    entry: dict[str, JsonValue] = {
        "id": "REQ-critical",
        "requirement": "A critical claim is settled.",
        "origin": "orientation",
        "status": "triangulated",
        "ambiguity_score": 0,
        "impact_weight": 5,
        "evidence_records": [
            hypothesis("prior", "model-group"),
            derived("restatement", ["prior"], "model-group"),
        ],
    }

    # When / Then: LedgerEntry parsing cannot reach a handoff-ready state.
    with pytest.raises(ValidationError, match="hypothesis-only lineage"):
        ambiguity_ledger.parse_entries(json.dumps([entry]))


def test_session_merge_rejects_missing_lineage_without_mutation() -> None:
    # Given: a persisted root and a derivative pointing elsewhere.
    entry: session_contracts.JsonObject = {"evidence_records": [firsthand("root", "repo-group")]}
    before = json.dumps(entry, sort_keys=True)
    addition = claim_evidence.ClaimEvidence.model_validate_json(
        json.dumps(derived("orphan", ["missing"], "repo-group")),
    )

    # When / Then: the merge fails before mutating persisted entry data.
    with pytest.raises(ValidationError, match="unknown evidence id"):
        session_contracts.merge_evidence_records(entry, (addition,))
    assert json.dumps(entry, sort_keys=True) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
