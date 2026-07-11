#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import TypeAlias

import typer

from scripts import claim_evidence, open_world, probe_policy

JsonObject: TypeAlias = dict[str, object]


def evidence_records(entry: JsonObject) -> tuple[claim_evidence.ClaimEvidence, ...]:
    raw = entry.get("evidence_records", [])
    if not isinstance(raw, list):
        raise typer.BadParameter("ledger evidence_records must be an array")
    return tuple(
        claim_evidence.ClaimEvidence.model_validate_json(json.dumps(record))
        for record in raw
    )


def merge_evidence_records(
    entry: JsonObject,
    additions: Iterable[claim_evidence.ClaimEvidence],
) -> None:
    merged = (*evidence_records(entry), *additions)
    evidence_set = claim_evidence.ClaimEvidenceSet(evidence_records=merged)
    entry["evidence_records"] = [
        record.model_dump(mode="json") for record in evidence_set.evidence_records
    ]
    entry.pop("channels", None)
    entry["evidence_channels"] = [
        channel.value for channel in evidence_set.projected_channels
    ]


def replace_evidence_records(
    entry: JsonObject,
    records: Iterable[claim_evidence.ClaimEvidence],
    supplied_channels: tuple[str, ...] | None,
) -> None:
    materialized = tuple(records)
    projected = None
    if supplied_channels is not None:
        projected = tuple(
            claim_evidence.CHANNEL_ALIASES[channel.strip().lower()]
            for channel in supplied_channels
        )
    evidence_set = claim_evidence.ClaimEvidenceSet(
        evidence_records=materialized,
        evidence_channels=projected,
    )
    entry.pop("channels", None)
    entry["evidence_records"] = [
        record.model_dump(mode="json") for record in evidence_set.evidence_records
    ]
    entry["evidence_channels"] = [
        channel.value for channel in evidence_set.projected_channels
    ]


def checkpoint_evidence(entry_id: str) -> claim_evidence.ClaimEvidence:
    return claim_evidence.ClaimEvidence(
        id=f"checkpoint:user:{entry_id}",
        channel=claim_evidence.EvidenceChannel.FROM_USER,
        claim_kind=claim_evidence.ClaimKind.NORMATIVE_DECISION,
        source_actor=claim_evidence.SourceActor.USER,
        provenance_mode=claim_evidence.ProvenanceMode.FIRSTHAND,
        independence_group=f"user-dependency:{entry_id}",
        freshness=claim_evidence.Freshness.CURRENT,
        warrant=f"The user confirmed the settled requirement {entry_id} at checkpoint.",
        epistemic_authority=claim_evidence.EpistemicAuthority.ESTABLISHES,
        decision_authority=claim_evidence.DecisionAuthority.OWNER,
    )


def material_signature(entry: JsonObject) -> str:
    fields = {
        key: entry.get(key)
        for key in (
            "requirement",
            "origin",
            "status",
            "deferred",
            "ambiguity_score",
            "ambiguity",
            "impact_weight",
            "weight",
            "evidence_records",
        )
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def append_open_world_sweep(
    protocol: JsonObject,
    sweep: open_world.OpenWorldSweep,
) -> None:
    revision = protocol.get("material_revision", 0)
    if sweep.material_revision_binding != revision:
        raise typer.BadParameter("open-world sweep binding is stale")
    raw_records = protocol.get("open_world_records", [])
    if not isinstance(raw_records, list):
        raise typer.BadParameter("protocol open_world_records must be an array")
    records = tuple(
        open_world.OpenWorldSweep.model_validate(record) for record in raw_records
    )
    if sweep.phase is open_world.OpenWorldPhase.ORIENTATION:
        records = tuple(
            record
            for record in records
            if record.phase is not open_world.OpenWorldPhase.ORIENTATION
        )
        records = (sweep, *records)
    else:
        records = (*records, sweep)
    history = open_world.OpenWorldHistory(records=records)
    protocol["open_world_records"] = [
        record.model_dump(mode="json") for record in history.records
    ]


def record_probe_decision(
    protocol: JsonObject,
    decision: probe_policy.ProbeDecision,
) -> None:
    protocol["probe_decision"] = decision.model_dump(mode="json")
    protocol["probe_sequence"] = None


def append_probe_attempt(
    protocol: JsonObject,
    attempt: probe_policy.ProbeAttempt,
) -> probe_policy.ProbeOutcome:
    persisted = protocol.get("probe_decision")
    if persisted is None:
        raise typer.BadParameter("probe attempt requires a persisted probe decision")
    decision = probe_policy.ProbeDecision.model_validate(persisted)
    if attempt.decision != decision:
        raise typer.BadParameter(
            "probe attempt decision must exactly match the persisted probe decision",
        )
    current = protocol.get("probe_sequence")
    attempts: tuple[probe_policy.ProbeAttempt, ...] = ()
    if current is not None:
        attempts = probe_policy.ProbeSequence.model_validate(current).attempts
    sequence = probe_policy.ProbeSequence(attempts=(*attempts, attempt))
    protocol["probe_sequence"] = sequence.model_dump(mode="json")
    return attempt.result.outcome
