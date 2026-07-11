#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from postmortem_bundle import JsonValue

POSTMORTEM_SCRIPTS = Path(__file__).resolve().parent
ULTIMATEINTERVIEW_SCRIPTS = POSTMORTEM_SCRIPTS.parents[1] / "ultimateinterview" / "scripts"
FIXTURE = ULTIMATEINTERVIEW_SCRIPTS / "integration_fixtures" / "v1-ready"


def run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def update(session: Path, payload: dict[str, JsonValue]) -> subprocess.CompletedProcess[str]:
    return run(
        ULTIMATEINTERVIEW_SCRIPTS / "session_update.py",
        str(session),
        "--delta",
        json.dumps(payload),
        "--format",
        "json",
    )


def exact(subject_id: str, command: str, capture: str) -> dict[str, JsonValue]:
    return {
        "subject_id": subject_id,
        "result": "exact-pass",
        "actual_command": command,
        "capture_artifact_id": capture,
    }


def ready_session(repo: Path) -> Path:
    session = repo / ".ultimateinterview" / "v1-ready"
    repo.mkdir()
    entry: dict[str, JsonValue] = {
        "id": "REQ-001",
        "requirement": "The local validation command remains executable",
        "origin": "orientation",
        "status": "draft",
        "ambiguity_score": 3,
        "impact_weight": 5,
        "evidence_records": [],
    }
    entries: list[JsonValue] = [entry]
    initialized = run(
        ULTIMATEINTERVIEW_SCRIPTS / "session_init.py",
        str(repo),
        "v1-ready",
        "--entries",
        json.dumps(entries),
        "--depth",
        "minimal",
    )
    assert initialized.returncode == 0, initialized.stderr
    assert json.loads((session / "protocol.json").read_text())["open_world_records"] == []
    for event in ("brain-dump", "framing"):
        result = update(session, {"event": event, "append_history": True})
        assert result.returncode == 0, result.stderr
    orientation: dict[str, JsonValue] = {
        "sweep_id": "OW-initial",
        "phase": "orientation",
        "precedes": "lens-selection",
        "interaction_cost": 0,
        "material_revision_binding": 0,
        "candidates": [],
    }
    assert update(session, {"open_world_sweep": orientation}).returncode == 0
    evidence_records: list[JsonValue] = [
        {
            "id": "EV-code",
            "channel": "from-code",
            "claim_kind": "observed-fact",
            "source_actor": "repository",
            "provenance_mode": "firsthand",
            "independence_group": "repo-command",
            "freshness": "current",
            "warrant": "The repository exposes the validation command.",
            "epistemic_authority": "establishes",
            "decision_authority": "none",
        },
        {
            "id": "EV-owner",
            "channel": "from-user",
            "claim_kind": "normative-decision",
            "source_actor": "user",
            "provenance_mode": "firsthand",
            "independence_group": "user-dependency:REQ-001",
            "freshness": "current",
            "warrant": "The owner requires the command to remain executable.",
            "epistemic_authority": "establishes",
            "decision_authority": "owner",
        },
    ]
    settlement_entry: dict[str, JsonValue] = {
        "id": "REQ-001",
        "status": "triangulated",
        "ambiguity_score": 0,
        "add_evidence_records": evidence_records,
    }
    settlement: dict[str, JsonValue] = {"set": [settlement_entry]}
    assert update(session, settlement).returncode == 0
    decision: dict[str, JsonValue] = {
        "probe_id": "PROBE-L1-e2e",
        "intent": "discovery",
        "selected_level": "L1",
        "target_ledger_ids": ["REQ-001"],
        "predicate": "Behavioral stubs differ from the reviewed requirement.",
        "contract_digest": "a" * 64,
        "sandboxable_observable": True,
        "requires_runtime_observation": False,
        "production_only": False,
        "previous_level_insufficiency": "L0 cannot observe the behavioral boundary.",
        "skipped_level_reason": None,
        "execution_scope": None,
        "authorization": None,
    }
    assert update(session, {"probe_decision": decision}).returncode == 0
    probe_result: dict[str, JsonValue] = {
        "result_id": "RESULT-L1-e2e",
        "decision_id": "PROBE-L1-e2e",
        "intent": "discovery",
        "level": "L1",
        "target_ledger_ids": ["REQ-001"],
        "contract_digest": "a" * 64,
        "producer_lineages": [
            {"producer_id": "stub-a", "independence_key": "stub-a", "kind": "behavioral-stub"},
            {"producer_id": "stub-b", "independence_key": "stub-b", "kind": "behavioral-stub"},
        ],
        "artifact_refs": ["artifacts/stub-a.json", "artifacts/stub-b.json"],
        "outcome": "no-material-divergence",
        "evidence_credit": 0,
        "completeness_credit": 0,
        "reopen_required": False,
        "gap_origin": None,
    }
    assert update(session, {"probe_attempt": {"decision": decision, "result": probe_result}}).returncode == 0
    protocol = json.loads((session / "protocol.json").read_text())
    revision = protocol["material_revision"]
    fresh_orientation: dict[str, JsonValue] = orientation | {
        "sweep_id": "OW-fresh",
        "material_revision_binding": revision,
    }
    assert update(session, {"open_world_sweep": fresh_orientation}).returncode == 0
    lenses = json.loads((FIXTURE / "protocol.json").read_text())["lenses"]
    assert update(session, {"protocol": {"lenses": lenses}}).returncode == 0
    for number in (1, 2):
        breadth: dict[str, JsonValue] = {
            "sweep_id": f"OW-breadth-{number}",
            "phase": "breadth",
            "precedes": "dry-sweep",
            "interaction_cost": 0,
            "material_revision_binding": revision,
            "candidates": [],
        }
        result = update(
            session,
            {"event": "sweep-free", "sweep_result": "dry", "open_world_sweep": breadth},
        )
        assert result.returncode == 0, result.stderr
    checkpoint = update(
        session,
        {"checkpoint_confirm": {"ids": ["REQ-001"], "fatigue": False}, "append_history": True},
    )
    assert checkpoint.returncode == 0, checkpoint.stderr
    (session / "handoff.md").write_bytes((FIXTURE / "handoff.md").read_bytes())
    (session / "decisions.jsonl").write_bytes((FIXTURE / "decisions.jsonl").read_bytes())
    review = update(session, {"build_contract_test": {"reviewer": "fixture-review"}})
    assert review.returncode == 0, review.stderr
    return session


def postmortem_report(ver_1: str, ver_2: str) -> str:
    return f"""# Postmortem: v1-ready

postmortem_schema: 2

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| execution return | build contract | REQ-001 |

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | Behavior Contract | execution-return.json | exact |

## Escaped Requirements

| ESC-ID | Behavior found in code | Failure mode | Requirement structure | Owning frame | Weight | Intent attribution | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Wonder Generalization

| Escape ID | Unknown class | Interview-time observable signal | Owning frame | Disposition | Store | Evidence |
| --- | --- | --- | --- | --- | --- | --- |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

| VER-ID | Check | Kind | Execution | Result | Captured artifact | Observed effect |
| --- | --- | --- | --- | --- | --- | --- |
| VER-002 | installed surface | real-surface | exact | pass | {ver_2} | uv version observed |
| VER-001 | unit command | test | exact | pass | {ver_1} | focused suite passed |

## Reward-Hacking Review

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | no | no | no | cleared | executor captures |

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

### Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 1 |
| escaped-requirement | 0 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

| Failure mode | Count |
| --- | --- |
| trigger-too-narrow | 0 |
| enumeration-miss | 0 |
| scoring-starved | 0 |
| answer-unpressured | 0 |
| synthesis-loss | 0 |
| ontology-miss | 0 |

| Structure / modifier / owner | Count |
| --- | --- |
| item | 0 |
| boundary | 0 |
| interaction | 0 |
| system | 0 |
| modifier:negative-space | 0 |
| modifier:runtime-only | 0 |
| owning-frame:none | 0 |

Rates: interview-discovery 100.0%, handoff-fidelity 100.0%.
"""
