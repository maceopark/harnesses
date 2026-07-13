from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name("compiler_session_check.py")
REPO_ROOT = Path(__file__).resolve().parents[4]


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _contract() -> dict[str, object]:
    contract: dict[str, object] = {
        "implementation_decision_policy": {
            "log_path": ".ultimateinterview/<session>/decision.jsonl",
            "instruction": "log gaps",
            "required_fields": [
                "contract_digest",
                "requirement_refs",
                "gap",
                "decision",
                "rationale",
                "alternatives",
                "affected_paths",
                "observable_impact",
            ],
            "authority_boundary": "evidence, not authority",
        },
        "schema": "ultimateinterview.build-contract.v1",
        "source_discovery_digest": "0" * 64,
        "goal": {},
        "scope": [{"id": "SCOPE-001", "scope": ["benchmark/todo-cli-app-6"]}],
        "non_goals": [],
        "authorities": [{"id": "AUTH-001"}],
        "requirements": [{"id": "REQ-001", "scope": ["benchmark/todo-cli-app-6"]}],
        "bounded_implementation_delegations": [],
        "acceptance_predicates": [{"id": "ACC-001"}],
        "verifications": [{"id": "VER-001"}],
        "trace": [
            {
                "authority_ref": "AUTH-001",
                "requirement_ref": "REQ-001",
                "acceptance_ref": "ACC-001",
                "verification_ref": "VER-001",
            }
        ],
        "unresolved_decisions": [],
    }
    contract["contract_digest"] = hashlib.sha256(_canonical(contract).encode()).hexdigest()
    return contract


def _write_session(root: Path, *, wrong_decision_digest: bool = False) -> Path:
    session = root / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    contract = _contract()
    digest = str(contract["contract_digest"])
    (session / "build-contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (session / "implementation-return.json").write_text(
        json.dumps(
            {
                "schema": "ultimateinterview.implementation-return.v1",
                "contract_digest": digest,
                "status": "implemented",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decision = {
        "contract_digest": "f" * 64 if wrong_decision_digest else digest,
        "requirement_refs": ["REQ-001"],
        "gap": "collection mechanism unspecified",
        "decision": "use a project-local hook",
        "rationale": "required by verification",
        "alternatives": ["change cwd"],
        "affected_paths": ["benchmark/todo-cli-app-6/pyproject.toml"],
        "observable_impact": "test collection only",
    }
    (session / "decision.jsonl").write_text(json.dumps(decision) + "\n", encoding="utf-8")
    return session


def test_compiler_session_bundle_accepts_digest_bound_artifacts(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    output = session / "bundle.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(session),
            "--repo-root",
            str(REPO_ROOT),
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert bundle["schema"] == "ultimateinterview.compiler-postmortem-evidence.v1"
    assert bundle["contract_digest"] == _contract()["contract_digest"]
    assert bundle["ids"]["requirements"] == ["REQ-001"]
    assert len(bundle["decisions"]) == 1
    assert any("discovery-record.json absent" in item for item in bundle["missing_evidence"])


def test_compiler_session_bundle_rejects_wrong_decision_digest(tmp_path: Path) -> None:
    session = _write_session(tmp_path, wrong_decision_digest=True)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(session), "--repo-root", str(REPO_ROOT)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "wrong contract digest" in result.stderr
    assert not (session / "compiler-evidence-bundle.json").exists()
