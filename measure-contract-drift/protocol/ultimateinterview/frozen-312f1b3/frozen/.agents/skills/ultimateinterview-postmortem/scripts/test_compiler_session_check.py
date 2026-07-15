from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


SCRIPT = Path(__file__).with_name("compiler_session_check.py")
REPO_ROOT = Path.cwd().resolve()
ULTIMATEINTERVIEW_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts"
)
sys.path.insert(0, str(ULTIMATEINTERVIEW_SCRIPTS))
from authority_compiler import (  # noqa: E402
    acceptance_binding_digest,
    compile_discovery_record,
    reconcile_authority_register,
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _source(uri: str) -> dict[str, str]:
    return {"uri": uri, "version": "2026-07-14"}


def _clause(
    text: str,
    decision_class: str,
    authority_refs: list[str],
    *,
    identifier: str | None = None,
) -> dict[str, Any]:
    clause: dict[str, Any] = {
        "text": text,
        "decision_class": decision_class,
        "scope": ["benchmark/todo-cli-app-6"],
        "constraints": ["Keep all task data local."],
        "preserved_behaviors": ["Existing local task data remains local."],
        "authority_refs": authority_refs,
        "evidence_refs": [],
    }
    if identifier is not None:
        clause["id"] = identifier
    return clause


def _discovery() -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": "ultimateinterview.discovery-record.v1",
        "goal": _clause("Provide a local task CLI.", "goal", ["AUTH-001"]),
        "scope": [
            _clause(
                "Support locally stored task changes.",
                "scope",
                ["AUTH-001"],
                identifier="SCOPE-001",
            )
        ],
        "non_goals": [
            _clause(
                "Do not synchronize task data over a network.",
                "non-goals",
                ["AUTH-001"],
                identifier="NON-GOAL-001",
            )
        ],
        "authorities": [
            {
                "id": "AUTH-001",
                "kind": "owner-decision",
                "status": "active",
                "source": _source("conversation://owner/1"),
                "scope": ["benchmark/todo-cli-app-6"],
                "constraints": ["Keep all task data local."],
                "decision_classes": ["goal", "scope", "non-goals", "observable-behavior"],
                "preserved_behaviors": ["Existing local task data remains local."],
                "statement": "The owner approves a local-only task CLI.",
                "supersedes": [],
                "conflicts_with": [],
                "owner": "product-owner",
            }
        ],
        "evidence": [],
        "requirements": [
            _clause(
                "Listing tasks shows every locally created task.",
                "observable-behavior",
                ["AUTH-001"],
                identifier="REQ-001",
            )
        ],
        "acceptance_predicates": [
            {
                "id": "ACC-001",
                "requirement_ref": "REQ-001",
                "precondition": "The local task store is empty.",
                "input": "Create one task named alpha.",
                "action": "Run the list command.",
                "observable_result": "The command shows alpha exactly once.",
                "failure_result": "Invalid input exits nonzero and stores no task.",
            }
        ],
        "verifications": [
            {
                "id": "VER-001",
                "requirement_ref": "REQ-001",
                "acceptance_refs": ["ACC-001"],
                "method": "scenario",
                "procedure": "Create alpha, then list tasks.",
                "expected_result": "The command shows alpha exactly once.",
            }
        ],
        "trace": [
            {
                "authority_ref": "AUTH-001",
                "requirement_ref": "REQ-001",
                "acceptance_ref": "ACC-001",
                "verification_ref": "VER-001",
            }
        ],
        "unresolved_decisions": [],
        "conflicts": [],
    }
    record["requirements"][0]["acceptance_bindings"] = [
        {
            "acceptance_ref": "ACC-001",
            "digest": acceptance_binding_digest(
                record["requirements"][0], record["acceptance_predicates"][0]
            ),
        }
    ]
    return record
def _authority_reconciliation(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "ultimateinterview.authority-reconciliation-input.v1",
        "owner_approval": {
            "id": "AR-APPROVAL-001",
            "owner": "product-owner",
            "source": _source("conversation://owner/2"),
            "statement": "The owner approves this complete Authority Register.",
            "approval_authority_ref": "AUTH-001",
            "approved_authority_refs": [
                authority["id"] for authority in record["authorities"]
            ],
            "approved_conflict_refs": [
                conflict["id"] for conflict in record["conflicts"]
            ],
        },
        "authorities": record["authorities"],
        "conflicts": record["conflicts"],
        "unresolved_decisions": [],
    }




def _implementation_return(contract_digest: str) -> dict[str, Any]:
    return {
        "schema": "ultimateinterview.implementation-return.v1",
        "contract_digest": contract_digest,
        "status": "implemented",
        "changed_repository_paths": ["benchmark/todo-cli-app-6/todo_cli.py"],
        "requirement_outcomes": {"REQ-001": "passed"},
        "verification_outcomes": {"VER-001": "passed"},
        "commands": [
            {
                "command": "python -m pytest tests/test_todo_cli.py",
                "result": "passed",
            }
        ],
        "existing_evidence_artifacts": ["benchmark/todo-cli-app-6/tests/test_todo_cli.py"],
        "non_contract_implementation_decisions": [],
        "not_run": [],
        "blocked": [],
        "failed": [],
    }


def _write_session(root: Path) -> Path:
    session = root / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    discovery = _discovery()
    authority_register = reconcile_authority_register(
        _authority_reconciliation(discovery)
    )
    discovery["authority_register_digest"] = authority_register[
        "authority_register_digest"
    ]
    contract = compile_discovery_record(discovery, authority_register)
    (session / "discovery-record.json").write_text(
        json.dumps(discovery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (session / "authority-register.json").write_text(
        json.dumps(authority_register, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (session / "build-contract.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (session / "implementation-return.json").write_text(
        json.dumps(_implementation_return(contract["contract_digest"]), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return session


def _run(session: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(session),
            "--repo-root",
            str(REPO_ROOT),
            "--diff-range",
            "HEAD",
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_compiler_session_bundle_accepts_complete_digest_bound_artifacts(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    output = session / "bundle.json"

    result = _run(session, "--output", str(output))

    assert result.returncode == 0, result.stderr
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert bundle["schema"] == "ultimateinterview.compiler-postmortem-evidence.v1"
    assert bundle["contract_digest"] == json.loads(
        (session / "build-contract.json").read_text(encoding="utf-8")
    )["contract_digest"]
    assert bundle["ids"]["requirements"] == ["REQ-001"]
    assert bundle["implementation_return"]["requirement_outcomes"] == {"REQ-001": "passed"}
    assert bundle["input_artifacts"]["discovery-record.json"]["byte_length"] > 0
    assert bundle["input_artifacts"]["authority-register.json"]["sha256"] == hashlib.sha256(
        (session / "authority-register.json").read_bytes()
    ).hexdigest()
    assert bundle["input_artifacts"]["implementation-return.json"]["sha256"] == hashlib.sha256(
        (session / "implementation-return.json").read_bytes()
    ).hexdigest()

def test_compiler_session_requires_authority_register(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    (session / "authority-register.json").unlink()

    result = _run(session)

    assert result.returncode == 1
    assert "authority-register.json not found" in result.stderr


def test_compiler_session_requires_discovery_record(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    (session / "discovery-record.json").unlink()

    result = _run(session)

    assert result.returncode == 1
    assert "discovery-record.json not found" in result.stderr


def test_compiler_session_rejects_partial_implementation_return(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    implementation_return = json.loads((session / "implementation-return.json").read_text())
    del implementation_return["verification_outcomes"]
    (session / "implementation-return.json").write_text(json.dumps(implementation_return), encoding="utf-8")

    result = _run(session)

    assert result.returncode == 1
    assert "implementation-return.json is invalid" in result.stderr


def test_compiler_session_rejects_unbound_implementation_return(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    implementation_return = json.loads((session / "implementation-return.json").read_text())
    implementation_return["contract_digest"] = "f" * 64
    (session / "implementation-return.json").write_text(json.dumps(implementation_return), encoding="utf-8")

    result = _run(session)

    assert result.returncode == 1
    assert "implementation-return.json is invalid" in result.stderr


def test_compiler_session_rejects_contract_recompile_drift(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    contract = json.loads((session / "build-contract.json").read_text())
    contract["goal"]["text"] = "A different sealed goal."
    digest_payload = copy.deepcopy(contract)
    digest_payload.pop("contract_digest")
    contract["contract_digest"] = hashlib.sha256(_canonical(digest_payload).encode()).hexdigest()
    (session / "build-contract.json").write_text(json.dumps(contract), encoding="utf-8")
    implementation_return = _implementation_return(contract["contract_digest"])
    (session / "implementation-return.json").write_text(json.dumps(implementation_return), encoding="utf-8")

    result = _run(session)

    assert result.returncode == 1
    assert "differs from a fresh compile" in result.stderr


def test_compiler_session_rejects_malformed_decision_log(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    (session / "decision.jsonl").write_text('{"contract_digest":\n', encoding="utf-8")

    result = _run(session)

    assert result.returncode == 1
    assert "decision.jsonl line 1 is malformed JSON" in result.stderr


def test_compiler_session_rejects_invalid_git_diff_boundary(tmp_path: Path) -> None:
    session = _write_session(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(session),
            "--repo-root",
            str(REPO_ROOT),
            "--diff-range",
            "not-a-git-revision",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "git diff --binary not-a-git-revision" in result.stderr
