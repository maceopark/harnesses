#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from typer.testing import CliRunner

POSTMORTEM_SCRIPTS = Path(__file__).resolve().parent
ULTIMATEINTERVIEW = POSTMORTEM_SCRIPTS.parents[1] / "ultimateinterview"
sys.path.insert(0, str(POSTMORTEM_SCRIPTS))
sys.path.insert(0, str(ULTIMATEINTERVIEW))

import pack_evidence  # noqa: E402
from postmortem_bundle import JsonValue  # noqa: E402
from scripts import build_contract  # noqa: E402
from scripts.build_contract_schema import BuildContract  # noqa: E402

RUNNER = CliRunner()
FIXTURE_HANDOFF = ULTIMATEINTERVIEW / "scripts" / "integration_fixtures" / "v1-ready" / "handoff.md"
HANDOFF = (
    FIXTURE_HANDOFF.read_text(encoding="utf-8")
    .replace(".ultimateinterview/v1-ready/", ".ultimateinterview/demo/")
    .replace("unit command", "focused suite")
    .replace("python3 -m pytest -q", "python3 -m pytest")
    .replace("uv --version", "python3 app.py --check")
)
LEDGER = {
    "entries": [
        {
            "id": "g1",
            "requirement": "save a value",
            "ambiguity_score": 0,
            "impact_weight": 2,
            "status": "Triangulated",
            "evidence_channels": ["from-user", "from-code"],
        }
    ]
}


def _contract() -> BuildContract:
    return build_contract.compile_handoff(HANDOFF)


def _session(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(HANDOFF, encoding="utf-8")
    (session / "ledger.json").write_text(json.dumps(LEDGER), encoding="utf-8")
    (session / "decisions.jsonl").write_text("", encoding="utf-8")
    contract = _contract()
    (session / "build-contract.json").write_text(
        contract.model_dump_json(indent=2), encoding="utf-8"
    )
    evidence = tmp_path / ".omo" / "evidence" / "demo"
    evidence.mkdir(parents=True)
    artifact_ids: dict[str, str] = {}
    for name in ("requirement.txt", "ver-1.txt", "ver-2.txt"):
        path = evidence / name
        path.write_text("captured\n", encoding="utf-8")
        rel = str(path.relative_to(tmp_path))
        artifact_ids[name] = pack_evidence.artifact_id(rel)
    return session, artifact_ids


def _return(contract: BuildContract, artifacts: dict[str, str]) -> dict[str, JsonValue]:
    captures = tuple(artifacts.values())
    return {
        "marker": "EXECUTION-RETURN",
        "schema_version": 1,
        "contract_digest": contract.contract_digest,
        "status": "completed",
        "changed_paths": ["app.py"],
        "requirement_outcomes": [
            {
                "subject_id": "REQ-001",
                "result": "exact-pass",
                "actual_command": "implemented",
                "capture_artifact_id": artifacts["requirement.txt"],
            }
        ],
        "verification_outcomes": [
            {
                "subject_id": "VER-002",
                "result": "exact-pass",
                "actual_command": "python3 app.py --check",
                "capture_artifact_id": artifacts["ver-2.txt"],
            },
            {
                "subject_id": "VER-001",
                "result": "exact-pass",
                "actual_command": "python3 -m pytest",
                "capture_artifact_id": artifacts["ver-1.txt"],
            },
        ],
        "decision_log": {
            "path": ".ultimateinterview/demo/decisions.jsonl",
            "sha256": hashlib.sha256(b"").hexdigest(),
        },
        "blocker_reasons": [],
        "deviations": [],
        "capture_artifact_ids": list(captures),
        "evidence_artifact_ids": [],
    }


def _pack(session: Path, *extra: str):
    return RUNNER.invoke(pack_evidence.app, [str(session), "--no-ulw", *extra])


def test_v5_projects_validated_contract_and_reordered_return(tmp_path: Path) -> None:
    # Given a valid BuildContract and an executor return whose VER outcomes are reordered
    session, artifacts = _session(tmp_path)
    contract = _contract()
    (session / "execution-return.json").write_text(
        json.dumps(_return(contract, artifacts)), encoding="utf-8"
    )

    # When the postmortem adapter packs the session
    result = _pack(session)

    # Then v5 retains foreign execution state beside stable, digest-bound sidecars
    assert result.exit_code == 0, result.output
    bundle = json.loads((session / "evidence_bundle.json").read_text(encoding="utf-8"))
    assert bundle["schema_version"] == 5
    assert bundle["execution"]["present"] is False
    assert bundle["contract"]["compatibility_mode"] == "stable-v5"
    assert bundle["contract"]["build_contract"]["contract_digest"] == contract.contract_digest
    assert [
        row["subject_id"] for row in bundle["contract"]["execution_return"]["verification_outcomes"]
    ] == ["VER-002", "VER-001"]


def test_absent_return_is_auditable_missing_evidence(tmp_path: Path) -> None:
    # Given a valid contract with no executor-owned return
    session, _ = _session(tmp_path)

    # When it is packed
    result = _pack(session)

    # Then packing succeeds but the process evidence hole is explicit
    assert result.exit_code == 0, result.output
    bundle = json.loads((session / "evidence_bundle.json").read_text(encoding="utf-8"))
    assert bundle["contract"]["execution_return"] is None
    assert any("execution-return.json absent" in note for note in bundle["missing_evidence"])


def test_present_malformed_owned_return_fails_closed(tmp_path: Path) -> None:
    # Given a file at the owned return path with an incomplete owned marker
    session, _ = _session(tmp_path)
    (session / "execution-return.json").write_text(
        '{"marker":"EXECUTION-RETURN","schema_version":1}', encoding="utf-8"
    )

    # When packed, Then no bundle is written
    result = _pack(session)
    assert result.exit_code == 1
    assert "execution-return.json" in result.output
    assert not (session / "evidence_bundle.json").exists()


def test_foreign_contract_digest_fails_closed(tmp_path: Path) -> None:
    # Given a structurally valid return bound to a different contract
    session, artifacts = _session(tmp_path)
    payload = _return(_contract(), artifacts)
    payload["contract_digest"] = "f" * 64
    (session / "execution-return.json").write_text(json.dumps(payload), encoding="utf-8")

    # When packed, Then the digest join rejects it
    result = _pack(session)
    assert result.exit_code == 1
    assert "contract_digest" in result.output


def test_undeclared_external_artifact_fails_closed(tmp_path: Path) -> None:
    # Given a return that invents an artifact id not present in the evidence manifest
    session, artifacts = _session(tmp_path)
    payload = _return(_contract(), artifacts)
    payload["capture_artifact_ids"] = [*artifacts.values(), "artifact-missing"]
    (session / "execution-return.json").write_text(json.dumps(payload), encoding="utf-8")

    # When packed, Then executor claims cannot outrun observed files
    result = _pack(session)
    assert result.exit_code == 1
    assert "artifact-missing" in result.output


def test_stale_build_contract_fails_closed(tmp_path: Path) -> None:
    # Given a valid sidecar whose source handoff changed after compilation
    session, _artifacts = _session(tmp_path)
    changed = HANDOFF.replace("# Part 2", "material change\n\n# Part 2", 1)
    (session / "handoff.md").write_text(changed, encoding="utf-8")

    # When packed, Then stale contract state cannot be projected as current
    result = _pack(session)
    assert result.exit_code == 1
    assert "source_part1_sha256" in result.output


def test_failed_repack_preserves_prior_atomic_bundle(tmp_path: Path) -> None:
    # Given a prior bundle and a newly malformed return after an interruption
    session, _artifacts = _session(tmp_path)
    bundle_path = session / "evidence_bundle.json"
    bundle_path.write_text("prior-complete-bundle\n", encoding="utf-8")
    (session / "execution-return.json").write_text("{malformed", encoding="utf-8")

    # When repacking fails, Then the prior completed artifact is not truncated or replaced
    result = _pack(session)
    assert result.exit_code == 1
    assert bundle_path.read_text(encoding="utf-8") == "prior-complete-bundle\n"
