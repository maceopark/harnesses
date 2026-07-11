#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Literal, assert_never

import pytest

from cross_skill_e2e_support import POSTMORTEM_SCRIPTS, ULTIMATEINTERVIEW_SCRIPTS
from cross_skill_e2e_support import ready_session, run, update
from cross_skill_return_support import pack, prepare_execution
from postmortem_bundle import JsonValue
from test_postmortem_v2_integration import _report as v2_report

type InterviewCase = Literal[
    "malformed-evidence", "model-prior", "stale-inventory", "unauthorized-probe", "tampered-sidecar"
]
type ReturnCase = Literal["foreign-return", "malformed-return", "adapted-exact", "unknown-decision"]
type TaxonomyCase = Literal["ontology-routed", "missing-structure", "calibration-mismatch"]


def _gate(session: Path) -> subprocess.CompletedProcess[str]:
    return run(
        ULTIMATEINTERVIEW_SCRIPTS / "session_status.py",
        str(session),
        "--gate",
        "--format",
        "json",
    )


def _write_return(session: Path, payload: dict[str, JsonValue]) -> None:
    (session / "execution-return.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "case",
    ("malformed-evidence", "model-prior", "stale-inventory", "unauthorized-probe", "tampered-sidecar"),
)
def test_interview_gate_rejects_cross_skill_negative(
    tmp_path: Path,
    case: InterviewCase,
) -> None:
    # Given a session produced by the complete real CLI lifecycle
    session = ready_session(tmp_path / case)

    # When one interview-side contract coordinate is invalidated
    match case:
        case "malformed-evidence":
            before = (session / "ledger.json").read_bytes()
            result = update(
                session,
                {"set": [{"id": "REQ-001", "evidence_records": [{"id": "EV-bad"}]}]},
            )
            assert result.returncode == 2
            assert (session / "ledger.json").read_bytes() == before
            output = result.stdout + result.stderr
        case "model-prior":
            prior: dict[str, JsonValue] = {
                "id": "EV-prior",
                "channel": "assumption",
                "claim_kind": "causal-hypothesis",
                "source_actor": "model",
                "provenance_mode": "model-prior",
                "independence_group": "model-prior:e2e",
                "freshness": "current",
                "warrant": "Plausible but unobserved model knowledge.",
                "epistemic_authority": "hypothesis-only",
                "decision_authority": "none",
            }
            records: list[JsonValue] = [prior]
            set_operation: dict[str, JsonValue] = {
                "id": "REQ-001", "evidence_records": records
            }
            delta: dict[str, JsonValue] = {"set": [set_operation]}
            changed = update(session, delta)
            assert changed.returncode == 0, changed.stderr
            result = _gate(session)
            assert result.returncode == 1
            output = result.stdout
        case "stale-inventory":
            protocol_path = session / "protocol.json"
            protocol = json.loads(protocol_path.read_text())
            protocol["open_world_records"] = protocol["open_world_records"][:1]
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            handoff = session / "handoff.md"
            handoff.write_text(
                handoff.read_text().replace("Preserve an executable", "Preserve a changed", 1),
                encoding="utf-8",
            )
            result = _gate(session)
            assert result.returncode == 1
            output = result.stdout
        case "unauthorized-probe":
            before = (session / "protocol.json").read_bytes()
            raw = json.loads(
                (ULTIMATEINTERVIEW_SCRIPTS / "integration_fixtures/v1-negative/cases.json").read_text()
            )
            result = update(session, raw["unauthorized_l3_delta"])
            assert result.returncode == 2
            assert (session / "protocol.json").read_bytes() == before
            output = result.stdout + result.stderr
        case "tampered-sidecar":
            sidecar = session / "build-contract.json"
            contract = json.loads(sidecar.read_text())
            contract["contract_digest"] = "f" * 64
            sidecar.write_text(json.dumps(contract), encoding="utf-8")
            result = _gate(session)
            assert result.returncode != 0
            output = result.stdout + result.stderr
        case unreachable:
            assert_never(unreachable)

    # Then the real boundary exits nonzero with its owned diagnostic
    expected = {
        "malformed-evidence": "evidence",
        "model-prior": "eligible structured evidence",
        "stale-inventory": "stale",
        "unauthorized-probe": "authorization",
        "tampered-sidecar": "contract_digest",
    }[case]
    assert expected in output
    if case == "stale-inventory":
        assert "fresh breadth" in output


@pytest.mark.parametrize(
    "case",
    ("foreign-return", "malformed-return", "adapted-exact", "unknown-decision"),
)
def test_v5_pack_rejects_cross_skill_return_negative(
    tmp_path: Path,
    case: ReturnCase,
) -> None:
    # Given a validated lifecycle, contract, decision log, and observed artifacts
    repo = tmp_path / case
    session = ready_session(repo)
    valid, _artifacts, lessons = prepare_execution(session, repo)
    payload: dict[str, JsonValue] = copy.deepcopy(valid)

    # When the executor-owned return breaks one foreign-provenance rule
    match case:
        case "foreign-return":
            payload["contract_digest"] = "f" * 64
        case "malformed-return":
            payload = {"marker": "EXECUTION-RETURN", "schema_version": 1}
        case "adapted-exact" | "unknown-decision":
            outcomes = payload["verification_outcomes"]
            assert isinstance(outcomes, list)
            row = outcomes[0]
            assert isinstance(row, dict)
            row["result"] = "adapted-pass"
            row["adaptation_reason"] = "The original selector was unavailable."
            row["decision_record_ref"] = "decision#1" if case == "adapted-exact" else "decision#999"
            if case == "unknown-decision":
                row["actual_command"] = "uv --version --adapted"
        case unreachable:
            assert_never(unreachable)
    _write_return(session, payload)
    result = pack(session, repo, lessons)

    # Then packing fails before a v5 projection can legitimize the return
    assert result.exit_code == 1
    expected = {
        "foreign-return": "contract_digest",
        "malformed-return": "execution-return.json",
        "adapted-exact": "adapted_command",
        "unknown-decision": "decision_record",
    }[case]
    assert expected in result.output


@pytest.mark.parametrize(
    "case",
    ("ontology-routed", "missing-structure", "calibration-mismatch"),
)
def test_postmortem_v2_rejects_cross_skill_taxonomy_negative(
    tmp_path: Path,
    case: TaxonomyCase,
) -> None:
    # Given a packed v5 return produced from the complete interview lifecycle
    repo = tmp_path / case
    session = ready_session(repo)
    _payload, artifacts, lessons = prepare_execution(session, repo)
    assert pack(session, repo, lessons).exit_code == 0
    report = v2_report().replace("artifact-generic", artifacts["requirement.txt"])
    old_table = "| Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect |\n| --- | --- | --- | --- | --- | --- | --- |"
    new_table = (
        "| VER-ID | Check | Kind | Execution | Result | Captured artifact | Observed effect |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        f"| VER-002 | installed surface | real-surface | exact | pass | {artifacts['ver-2.txt']} | observed |\n"
        f"| VER-001 | unit command | test | exact | pass | {artifacts['ver-1.txt']} | passed |"
    )
    report = report.replace(old_table, new_table)

    # When one taxonomy coordinate is made non-causal or internally inconsistent
    match case:
        case "ontology-routed":
            report = report.replace("novel:feedback-loop+negative-space | none", "novel:feedback-loop+negative-space | misuse")
        case "missing-structure":
            report = report.replace("novel:feedback-loop+negative-space | none", " | none")
        case "calibration-mismatch":
            report = report.replace("| modifier:runtime-only | 1 |", "| modifier:runtime-only | 0 |")
        case unreachable:
            assert_never(unreachable)
    (session / "postmortem.md").write_text(report, encoding="utf-8")
    result = run(POSTMORTEM_SCRIPTS / "postmortem_lint.py", str(session))

    # Then schema-v2 lint rejects the routed, missing, or mismatched coordinate
    assert result.returncode == 1
    expected = {
        "ontology-routed": "ontology",
        "missing-structure": "structure",
        "calibration-mismatch": "modifier:runtime-only",
    }[case]
    assert expected in result.stdout
