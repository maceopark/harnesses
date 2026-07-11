#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
from pathlib import Path

POSTMORTEM_SCRIPTS = Path(__file__).resolve().parent
ULTIMATEINTERVIEW = POSTMORTEM_SCRIPTS.parents[1] / "ultimateinterview"
ULTIMATEINTERVIEW_SCRIPTS = ULTIMATEINTERVIEW / "scripts"

from cross_skill_e2e_support import postmortem_report, ready_session, run  # noqa: E402
from cross_skill_return_support import prepare_execution  # noqa: E402


def test_v1_to_v5_contract_oracle_lifecycle(tmp_path: Path) -> None:
    # Given an empty temporary repository and one unresolved requirement
    repo = tmp_path / "repo"
    session = ready_session(repo)

    # When every interview state transition has run through the real update CLI
    protocol = json.loads((session / "protocol.json").read_text())
    assert protocol["build_contract_tested"] is True
    assert protocol["probe_decision"]["selected_level"] == "L1"
    assert [row["phase"] for row in protocol["open_world_records"]][-2:] == [
        "breadth",
        "breadth",
    ]
    ledger = json.loads((session / "ledger.json").read_text())
    evidence_ids = {row["id"] for row in ledger["entries"][0]["evidence_records"]}
    assert {"EV-code", "EV-owner"} <= evidence_ids

    # Then the executor return, v5 pack, and schema-v2 postmortem retain every join
    execution_return, artifact_ids, lessons = prepare_execution(session, repo)
    contract = json.loads((session / "build-contract.json").read_text(encoding="utf-8"))

    compiled = session / "compiled-build-contract.json"
    compile_result = run(
        ULTIMATEINTERVIEW_SCRIPTS / "build_contract.py",
        str(session / "handoff.md"),
        "--output",
        str(compiled),
    )
    gate_result = run(
        ULTIMATEINTERVIEW_SCRIPTS / "session_status.py",
        str(session),
        "--gate",
        "--format",
        "json",
    )
    pack_result = run(
        POSTMORTEM_SCRIPTS / "pack_evidence.py",
        str(session),
        "--no-ulw",
        "--repo-root",
        str(repo),
        "--lessons",
        str(lessons),
    )
    (session / "postmortem.md").write_text(
        postmortem_report(artifact_ids["ver-1.txt"], artifact_ids["ver-2.txt"]),
        encoding="utf-8",
    )
    lint_result = run(POSTMORTEM_SCRIPTS / "postmortem_lint.py", str(session))

    assert compile_result.returncode == 0, compile_result.stderr
    assert compiled.read_bytes() == (session / "build-contract.json").read_bytes()
    assert gate_result.returncode == 0, gate_result.stdout + gate_result.stderr
    assert json.loads(gate_result.stdout)["implementation_gate"]["implementation_ready"]
    assert pack_result.returncode == 0, pack_result.stderr
    bundle = json.loads((session / "evidence_bundle.json").read_text(encoding="utf-8"))
    assert bundle["schema_version"] == 5
    assert bundle["contract"]["execution_return"]["contract_digest"] == contract[
        "contract_digest"
    ]
    assert lint_result.returncode == 0, lint_result.stdout + lint_result.stderr
