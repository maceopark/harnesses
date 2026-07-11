#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ambiguity_ledger

type JsonValue = None | bool | int | float | str | Sequence[JsonValue] | Mapping[str, JsonValue]


def evidence(
    evidence_id: str,
    channel: str,
    group: str,
    *,
    decision_authority: str = "none",
) -> dict[str, JsonValue]:
    return {
        "id": evidence_id,
        "channel": channel,
        "claim_kind": "observed-fact",
        "source_actor": "repository",
        "provenance_mode": "firsthand",
        "independence_group": group,
        "freshness": "current",
        "warrant": f"Observed {evidence_id}",
        "epistemic_authority": "establishes",
        "decision_authority": decision_authority,
    }


def entry(
    records: Sequence[Mapping[str, JsonValue]],
    channels: Sequence[str] | None = None,
) -> str:
    payload: dict[str, JsonValue] = {
        "id": "REQ-critical",
        "requirement": "A critical behavior is fixed",
        "origin": "orientation",
        "status": "triangulated",
        "ambiguity_score": 0,
        "impact_weight": 5,
        "evidence_records": records,
    }
    if channels is not None:
        payload["evidence_channels"] = channels
    return json.dumps([payload])


def test_v1_same_group_channels_count_once() -> None:
    # Given
    records = [
        evidence("E-code", "from-code", "repo-lineage"),
        evidence("E-docs", "from-docs", "repo-lineage"),
    ]

    # When
    entries = ambiguity_ledger.parse_entries(entry(records))
    summary = ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1)

    # Then
    assert entries[0].evidence_channels == ("from-code", "from-docs")
    assert not summary.handoff_ready
    assert summary.triangulation_violations == ("REQ-critical",)


def test_v1_same_channel_independent_groups_count_twice() -> None:
    # Given
    records = [
        evidence("E-code-a", "from-code", "repo-a"),
        evidence("E-code-b", "from-code", "repo-b"),
    ]

    # When
    entries = ambiguity_ledger.parse_entries(entry(records))
    summary = ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1)

    # Then
    assert entries[0].evidence_channels == ("from-code",)
    assert summary.handoff_ready


def test_v1_single_source_acceptance_requires_decision_authority() -> None:
    # Given
    owner_record = evidence(
        "E-owner",
        "from-user",
        "user-dependency:REQ-critical",
        decision_authority="owner",
    )

    # When
    entries = ambiguity_ledger.parse_entries(
        entry([owner_record]).replace('"triangulated"', '"accepted"'),
    )
    summary = ambiguity_ledger.summarize_ambiguity(entries, evidence_schema_version=1)

    # Then
    assert summary.handoff_ready


def test_v1_model_prior_cannot_settle_an_entry() -> None:
    # Given
    model_prior = {
        "id": "E-prior",
        "channel": "assumption",
        "claim_kind": "causal-hypothesis",
        "source_actor": "model",
        "provenance_mode": "model-prior",
        "independence_group": "model-prior:one",
        "freshness": "current",
        "warrant": "A plausible model prior",
        "epistemic_authority": "hypothesis-only",
        "decision_authority": "none",
    }

    # When
    entries = ambiguity_ledger.parse_entries(entry([model_prior]))
    failures = ambiguity_ledger.gate_failures(entries, evidence_schema_version=1)

    # Then
    assert failures == ("v1 settled entries without eligible structured evidence: REQ-critical",)


def test_v1_projection_is_exact_and_bundle_origin_is_legacy_alias() -> None:
    # Given
    record = evidence("E-code", "from-code", "repo-a")
    aliased = json.loads(entry([record], ["from-code"]))
    aliased[0]["origin"] = "bundle"

    # When
    entries = ambiguity_ledger.parse_entries(json.dumps(aliased))

    # Then
    assert entries[0].origin == "batch"
