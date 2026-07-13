#!/usr/bin/env python3
"""Validate and pack a compiler-only Ultimateinterview session for postmortem audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable

BUILD_SCHEMA = "ultimateinterview.build-contract.v1"
BUNDLE_SCHEMA = "ultimateinterview.compiler-postmortem-evidence.v1"
BUNDLE_FILENAME = "compiler-evidence-bundle.json"
DECISION_FILENAME = "decision.jsonl"
RETURN_FILENAME = "implementation-return.json"
MAX_TEXT_BYTES = 128_000
REQUIRED_DECISION_FIELDS = frozenset(
    {
        "contract_digest",
        "requirement_refs",
        "gap",
        "decision",
        "rationale",
        "alternatives",
        "affected_paths",
        "observable_impact",
    }
)


class SessionError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n"


def digest_contract(contract: dict[str, Any]) -> str:
    payload = dict(contract)
    payload.pop("contract_digest", None)
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SessionError(f"{label} not found at {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SessionError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise SessionError(f"{label} must be a JSON object")
    return value


def require_ids(rows: Any, field: str) -> tuple[str, ...]:
    if not isinstance(rows, list):
        raise SessionError(f"build-contract.json {field} must be an array")
    result: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise SessionError(f"build-contract.json {field}[{index}] needs a non-empty id")
        result.append(row["id"])
    if len(result) != len(set(result)):
        raise SessionError(f"build-contract.json {field} contains duplicate ids")
    return tuple(result)


def validate_trace(contract: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    requirements = require_ids(contract.get("requirements"), "requirements")
    acceptances = require_ids(contract.get("acceptance_predicates"), "acceptance_predicates")
    verifications = require_ids(contract.get("verifications"), "verifications")
    authorities = require_ids(contract.get("authorities"), "authorities")
    trace = contract.get("trace")
    if not isinstance(trace, list):
        raise SessionError("build-contract.json trace must be an array")
    referenced_requirements: set[str] = set()
    referenced_acceptances: set[str] = set()
    referenced_verifications: set[str] = set()
    known = {
        "authority_ref": set(authorities),
        "requirement_ref": set(requirements),
        "acceptance_ref": set(acceptances),
        "verification_ref": set(verifications),
    }
    for index, row in enumerate(trace):
        if not isinstance(row, dict):
            raise SessionError(f"build-contract.json trace[{index}] must be an object")
        for key, values in known.items():
            if row.get(key) not in values:
                raise SessionError(f"build-contract.json trace[{index}].{key} is unknown")
        referenced_requirements.add(row["requirement_ref"])
        referenced_acceptances.add(row["acceptance_ref"])
        referenced_verifications.add(row["verification_ref"])
    if referenced_requirements != set(requirements):
        raise SessionError("build-contract.json trace does not cover every requirement")
    if referenced_acceptances != set(acceptances):
        raise SessionError("build-contract.json trace does not cover every acceptance predicate")
    if referenced_verifications != set(verifications):
        raise SessionError("build-contract.json trace does not cover every verification")
    return {
        "requirements": requirements,
        "acceptances": acceptances,
        "verifications": verifications,
        "authorities": authorities,
    }


def recompile_discovery(session_dir: Path, contract: dict[str, Any], missing: list[str]) -> str | None:
    discovery = session_dir / "discovery-record.json"
    if not discovery.is_file():
        missing.append("discovery-record.json absent - sealed digest is valid but source recompilation was not observed")
        return None
    compiler = Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts" / "authority_compiler.py"
    if not compiler.is_file():
        raise SessionError(f"authority compiler not found at {compiler}")
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "build-contract.json"
        result = subprocess.run(
            [sys.executable, str(compiler), str(discovery), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SessionError(f"Discovery Record recompilation failed: {result.stderr.strip()}")
        rebuilt = load_object(output, "recompiled build-contract.json")
    if rebuilt != contract:
        raise SessionError("build-contract.json differs from a fresh compile of discovery-record.json")
    return hashlib.sha256(discovery.read_bytes()).hexdigest()


def parse_decisions(path: Path, contract_digest: str, requirement_ids: set[str], missing: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        missing.append(f"{DECISION_FILENAME} absent - implementation gap decisions are unavailable")
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise SessionError(f"{DECISION_FILENAME} line {line_number} is malformed JSON: {error}") from error
        if not isinstance(row, dict) or set(row) != REQUIRED_DECISION_FIELDS:
            raise SessionError(
                f"{DECISION_FILENAME} line {line_number} must contain exactly {sorted(REQUIRED_DECISION_FIELDS)}"
            )
        if row["contract_digest"] != contract_digest:
            raise SessionError(f"{DECISION_FILENAME} line {line_number} has the wrong contract digest")
        refs = row["requirement_refs"]
        if not isinstance(refs, list) or not refs or any(ref not in requirement_ids for ref in refs):
            raise SessionError(f"{DECISION_FILENAME} line {line_number} has invalid requirement_refs")
        for field in ("gap", "decision", "rationale", "observable_impact"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise SessionError(f"{DECISION_FILENAME} line {line_number}.{field} must be non-empty")
        for field in ("alternatives", "affected_paths"):
            if not isinstance(row[field], list) or any(not isinstance(item, str) or not item for item in row[field]):
                raise SessionError(f"{DECISION_FILENAME} line {line_number}.{field} must be a string array")
        rows.append(row)
    return rows


def scope_paths(contract: dict[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    for group in (contract.get("scope", []), contract.get("requirements", [])):
        if not isinstance(group, list):
            continue
        for row in group:
            if isinstance(row, dict) and isinstance(row.get("scope"), list):
                values.update(item for item in row["scope"] if isinstance(item, str) and "/" in item)
    return tuple(sorted(values))


def git_output(repo_root: Path, arguments: Iterable[str]) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo_root, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise SessionError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def collect_repository_evidence(
    repo_root: Path, scopes: tuple[str, ...], diff_range: str | None, diff_file: Path | None
) -> dict[str, Any]:
    if diff_range and diff_file:
        raise SessionError("use only one of --diff-range and --diff-file")
    if diff_file:
        diff = diff_file.read_text(encoding="utf-8")
        source = str(diff_file.resolve())
    else:
        revision = [diff_range] if diff_range else ["HEAD"]
        diff = git_output(repo_root, ["diff", "--binary", *revision, "--", *scopes])
        source = f"git diff {' '.join(revision)} -- {' '.join(scopes)}"
    status = git_output(repo_root, ["status", "--short", "--untracked-files=all", "--", *scopes])
    files: list[dict[str, Any]] = []
    for line in status.splitlines():
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        path = repo_root / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        entry: dict[str, Any] = {
            "path": relative,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        if len(content) <= MAX_TEXT_BYTES:
            try:
                entry["text"] = content.decode("utf-8")
            except UnicodeDecodeError:
                entry["text"] = None
        files.append(entry)
    return {"source": source, "diff": diff, "status": status, "files": files}


def write_bundle(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--diff-range")
    parser.add_argument("--diff-file", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        session_dir = arguments.session_dir.resolve()
        if not session_dir.is_dir():
            raise SessionError(f"session directory not found: {session_dir}")
        contract_path = session_dir / "build-contract.json"
        contract = load_object(contract_path, "build-contract.json")
        if next(iter(contract), None) != "implementation_decision_policy":
            raise SessionError("build-contract.json must begin with implementation_decision_policy")
        if contract.get("schema") != BUILD_SCHEMA:
            raise SessionError(f"build-contract.json schema must be {BUILD_SCHEMA}")
        claimed_digest = contract.get("contract_digest")
        actual_digest = digest_contract(contract)
        if claimed_digest != actual_digest:
            raise SessionError("build-contract.json contract_digest is invalid")
        ids = validate_trace(contract)
        missing: list[str] = []
        discovery_digest = recompile_discovery(session_dir, contract, missing)

        implementation_return_path = session_dir / RETURN_FILENAME
        implementation_return: dict[str, Any] | None = None
        if implementation_return_path.is_file():
            implementation_return = load_object(implementation_return_path, RETURN_FILENAME)
            if implementation_return.get("contract_digest") != claimed_digest:
                raise SessionError(f"{RETURN_FILENAME} has the wrong contract digest")
        else:
            missing.append(f"{RETURN_FILENAME} absent - implementation conformance is self-report evidence missing")

        decisions = parse_decisions(
            session_dir / DECISION_FILENAME, claimed_digest, set(ids["requirements"]), missing
        )
        repo_root = (arguments.repo_root or session_dir.parent.parent).resolve()
        scopes = scope_paths(contract)
        repository = collect_repository_evidence(
            repo_root, scopes, arguments.diff_range, arguments.diff_file
        )
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "session_dir": str(session_dir),
            "contract_digest": claimed_digest,
            "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            "discovery_sha256": discovery_digest,
            "ids": ids,
            "scope_paths": scopes,
            "build_contract": contract,
            "implementation_return": implementation_return,
            "decisions": decisions,
            "repository_evidence": repository,
            "missing_evidence": missing,
        }
        output = arguments.output or session_dir / BUNDLE_FILENAME
        write_bundle(output, bundle)
        print(
            f"compiler session valid: {claimed_digest} | requirements {len(ids['requirements'])} | "
            f"verifications {len(ids['verifications'])} | decisions {len(decisions)} | missing {len(missing)}"
        )
        return 0
    except (OSError, UnicodeError, SessionError, ValueError) as error:
        print(f"compiler_session_check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
