#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

import pack_evidence
from cross_skill_e2e_support import exact
from postmortem_bundle import JsonValue

RUNNER = CliRunner()


def prepare_execution(
    session: Path,
    repo: Path,
) -> tuple[dict[str, JsonValue], dict[str, str], Path]:
    evidence = repo / ".omo" / "evidence" / "v1-ready"
    evidence.mkdir(parents=True)
    artifacts: dict[str, str] = {}
    for name in ("requirement.txt", "ver-1.txt", "ver-2.txt"):
        path = evidence / name
        path.write_text("captured\n", encoding="utf-8")
        artifacts[name] = pack_evidence.artifact_id(str(path.relative_to(repo)))
    contract = json.loads((session / "build-contract.json").read_text(encoding="utf-8"))
    decisions = (session / "decisions.jsonl").read_bytes()
    payload: dict[str, JsonValue] = {
        "marker": "EXECUTION-RETURN",
        "schema_version": 1,
        "contract_digest": contract["contract_digest"],
        "status": "completed",
        "changed_paths": ["fixture.txt"],
        "requirement_outcomes": [
            exact("REQ-001", "preserved fixture behavior", artifacts["requirement.txt"])
        ],
        "verification_outcomes": [
            exact("VER-002", "uv --version", artifacts["ver-2.txt"]),
            exact("VER-001", "python3 -m pytest -q", artifacts["ver-1.txt"]),
        ],
        "decision_log": {
            "path": ".ultimateinterview/v1-ready/decisions.jsonl",
            "sha256": hashlib.sha256(decisions).hexdigest(),
        },
        "blocker_reasons": [],
        "deviations": [],
        "capture_artifact_ids": list(artifacts.values()),
        "evidence_artifact_ids": [],
    }
    (session / "execution-return.json").write_text(json.dumps(payload), encoding="utf-8")
    lessons = repo / "lessons.md"
    lessons.write_text("# Lessons\n\n| Signal | Lens |\n| --- | --- |\n", encoding="utf-8")
    return payload, artifacts, lessons


def pack(session: Path, repo: Path, lessons: Path):
    return RUNNER.invoke(
        pack_evidence.app,
        [str(session), "--no-ulw", "--repo-root", str(repo), "--lessons", str(lessons)],
    )
