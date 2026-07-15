#!/usr/bin/env python3
"""Validate and pack a sealed Ultimateinterview session for postmortem audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


BUILD_SCHEMA = "ultimateinterview.build-contract.v1"
BUNDLE_SCHEMA = "ultimateinterview.compiler-postmortem-evidence.v1"
BUNDLE_FILENAME = "compiler-evidence-bundle.json"
DISCOVERY_FILENAME = "discovery-record.json"
AUTHORITY_REGISTER_FILENAME = "authority-register.json"
CONTRACT_FILENAME = "build-contract.json"
EXECUTION_CONTRACT_FILENAME = "execution-contract.md"
DECISION_FILENAME = "decision.jsonl"
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
    """A stable diagnostic for an unauditable postmortem session."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n"


def digest_contract(contract: Mapping[str, Any]) -> str:
    payload = dict(contract)
    payload.pop("contract_digest", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _strict_json_loads(text: str) -> Any:
    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite JSON value {token}")

    def reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = item
        return result

    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_object_keys,
    )


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise SessionError(f"{label} not found")
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SessionError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise SessionError(f"{label} must be a JSON object")
    return value


def file_descriptor(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise SessionError(f"{path.name} not found")
        return {"state": "absent"}
    try:
        content = path.read_bytes()
    except OSError as error:
        raise SessionError(f"{path.name} cannot be read") from error
    return {
        "state": "present",
        "byte_length": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


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


def validate_trace(contract: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
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


def native_compiler() -> Any:
    sibling_scripts = Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts"
    if not sibling_scripts.is_dir():
        raise SessionError("native authority compiler scripts are unavailable")
    sibling_path = str(sibling_scripts)
    if sibling_path not in sys.path:
        sys.path.insert(0, sibling_path)
    try:
        import authority_compiler
    except ImportError as error:
        raise SessionError("native authority compiler cannot be imported") from error
    for name in (
        "CompilerError",
        "compile_discovery_record",
        "validate_authority_register",
    ):
        if not hasattr(authority_compiler, name):
            raise SessionError(f"native authority compiler lacks {name}")
    return authority_compiler


def native_projection_checker() -> Any:
    sibling_scripts = Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts"
    sibling_path = str(sibling_scripts)
    if sibling_path not in sys.path:
        sys.path.insert(0, sibling_path)
    try:
        import projection_check
    except ImportError as error:
        raise SessionError("native projection checker cannot be imported") from error
    for name in ("ProjectionError", "validate_projection"):
        if not hasattr(projection_check, name):
            raise SessionError(f"native projection checker lacks {name}")
    return projection_check


def validate_execution_projection(
    path: Path,
    discovery: Mapping[str, Any],
    authority_register: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SessionError(f"{EXECUTION_CONTRACT_FILENAME} is not valid UTF-8") from error
    checker = native_projection_checker()
    try:
        return checker.validate_projection(text, discovery, authority_register, contract)
    except checker.ProjectionError as error:
        raise SessionError(f"{EXECUTION_CONTRACT_FILENAME} projection is invalid: {error}") from error


def native_error(error: BaseException) -> str:
    return f"{error.code}: {error.path}: {error.detail}"


def recompile_discovery(
    discovery: Mapping[str, Any],
    authority_register: Mapping[str, Any],
    contract: Mapping[str, Any],
    compiler: Any,
) -> None:
    try:
        rebuilt = compiler.compile_discovery_record(discovery, authority_register)
    except compiler.CompilerError as error:
        raise SessionError(f"discovery-record.json is invalid: {native_error(error)}") from error
    if rebuilt != contract:
        raise SessionError("build-contract.json differs from a fresh compile of discovery-record.json")


def parse_decisions(
    path: Path, contract_digest: str, requirement_ids: set[str]
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SessionError(f"{DECISION_FILENAME} is not valid UTF-8 JSONL") from error
    if raw and not raw.endswith("\n"):
        raise SessionError(f"{DECISION_FILENAME} must end with a newline")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = _strict_json_loads(line)
        except (json.JSONDecodeError, ValueError) as error:
            raise SessionError(f"{DECISION_FILENAME} line {line_number} is malformed JSON") from error
        if not isinstance(row, dict) or set(row) != REQUIRED_DECISION_FIELDS:
            raise SessionError(
                f"{DECISION_FILENAME} line {line_number} must contain exactly {sorted(REQUIRED_DECISION_FIELDS)}"
            )
        if row["contract_digest"] != contract_digest:
            raise SessionError(f"{DECISION_FILENAME} line {line_number} has the wrong contract digest")
        refs = row["requirement_refs"]
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or ref not in requirement_ids for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise SessionError(f"{DECISION_FILENAME} line {line_number} has invalid requirement_refs")
        for field in ("gap", "decision", "rationale", "observable_impact"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise SessionError(f"{DECISION_FILENAME} line {line_number}.{field} must be non-empty")
        for field in ("alternatives", "affected_paths"):
            if not isinstance(row[field], list) or any(
                not isinstance(item, str) or not item.strip() for item in row[field]
            ):
                raise SessionError(f"{DECISION_FILENAME} line {line_number}.{field} must be a string array")
        for index, affected_path in enumerate(row["affected_paths"]):
            if not normalized_repository_path(affected_path):
                raise SessionError(
                    f"{DECISION_FILENAME} line {line_number}.affected_paths[{index}] is not normalized"
                )
        rows.append(row)
    return rows


def normalized_repository_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path != PurePosixPath(".") and ".." not in path.parts


def scope_paths(contract: Mapping[str, Any]) -> tuple[str, ...]:
    values: set[str] = set()
    for group in (contract.get("scope", []), contract.get("requirements", [])):
        if not isinstance(group, list):
            continue
        for row in group:
            if not isinstance(row, dict) or not isinstance(row.get("scope"), list):
                continue
            for item in row["scope"]:
                if isinstance(item, str) and normalized_repository_path(item):
                    values.add(item)
    if not values:
        raise SessionError("build-contract.json has no normalized repository scope paths")
    return tuple(sorted(values))


def git_output(repo_root: Path, arguments: Iterable[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SessionError(f"git {' '.join(arguments)} failed")
    return result.stdout


def repository_root(path: Path) -> None:
    if not path.is_dir():
        raise SessionError("--repo-root must name an existing directory")
    top_level = git_output(path, ["rev-parse", "--show-toplevel"]).strip()
    if not top_level or Path(top_level).resolve() != path.resolve():
        raise SessionError("--repo-root must name the Git worktree root")


def repository_file_evidence(repo_root: Path, names: Sequence[str]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for name in sorted(set(names)):
        if not normalized_repository_path(name):
            raise SessionError("git diff returned a non-normalized repository path")
        path = repo_root / name
        entry: dict[str, Any] = {"path": name}
        if not path.is_file():
            entry["state"] = "absent"
            files.append(entry)
            continue
        content = path.read_bytes()
        entry.update(
            {
                "state": "present",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
        if len(content) <= MAX_TEXT_BYTES:
            try:
                entry["text"] = content.decode("utf-8")
            except UnicodeDecodeError:
                entry["text"] = None
        files.append(entry)
    return files


def collect_repository_evidence(
    repo_root: Path, scopes: tuple[str, ...], diff_range: str | None, diff_file: Path | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (diff_range is None) == (diff_file is None):
        raise SessionError("provide exactly one of --diff-range and --diff-file")
    repository_root(repo_root)
    if diff_file is not None:
        if not diff_file.is_file():
            raise SessionError("--diff-file must name an existing regular file")
        try:
            diff_bytes = diff_file.read_bytes()
            diff = diff_bytes.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise SessionError("--diff-file must be UTF-8 text") from error
        source = "diff-file"
        boundary: dict[str, Any] = {
            "kind": "diff-file",
            "path": str(diff_file.resolve()),
            "scope_paths": list(scopes),
        }
        diff_input = {
            "state": "present",
            "byte_length": len(diff_bytes),
            "sha256": hashlib.sha256(diff_bytes).hexdigest(),
        }
        changed_names: list[str] = []
    else:
        assert diff_range is not None
        if not diff_range.strip():
            raise SessionError("--diff-range must not be empty")
        diff = git_output(repo_root, ["diff", "--binary", diff_range, "--", *scopes])
        names = git_output(repo_root, ["diff", "--name-only", "-z", diff_range, "--", *scopes])
        changed_names = [name for name in names.split("\0") if name]
        diff_bytes = diff.encode("utf-8")
        source = "git-diff-range"
        boundary = {
            "kind": "git-diff-range",
            "range": diff_range,
            "scope_paths": list(scopes),
        }
        diff_input = {
            "state": "present",
            "byte_length": len(diff_bytes),
            "sha256": hashlib.sha256(diff_bytes).hexdigest(),
        }
    status = git_output(
        repo_root, ["status", "--short", "--untracked-files=all", "--", *scopes]
    )
    status_bytes = status.encode("utf-8")
    repository = {
        "source": source,
        "repo_root": str(repo_root.resolve()),
        "boundary": boundary,
        "diff": diff,
        "diff_sha256": hashlib.sha256(diff_bytes).hexdigest(),
        "diff_byte_length": len(diff_bytes),
        "status": status,
        "status_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "status_byte_length": len(status_bytes),
        "files": repository_file_evidence(repo_root, changed_names),
    }
    return repository, {"repository-diff": diff_input}


def write_bundle(path: Path, value: Mapping[str, Any]) -> None:
    if not path.parent.is_dir():
        raise SessionError("bundle output parent directory does not exist")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--diff-range")
    parser.add_argument("--diff-file", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        session_dir = arguments.session_dir.resolve()
        if not session_dir.is_dir():
            raise SessionError("session directory not found")
        if (arguments.diff_range is None) == (arguments.diff_file is None):
            raise SessionError("provide exactly one of --diff-range and --diff-file")

        discovery_path = session_dir / DISCOVERY_FILENAME
        contract_path = session_dir / CONTRACT_FILENAME
        authority_register_path = session_dir / AUTHORITY_REGISTER_FILENAME
        execution_contract_path = session_dir / EXECUTION_CONTRACT_FILENAME
        decision_path = session_dir / DECISION_FILENAME
        input_artifacts = {
            DISCOVERY_FILENAME: file_descriptor(discovery_path, required=True),
            AUTHORITY_REGISTER_FILENAME: file_descriptor(authority_register_path, required=True),
            CONTRACT_FILENAME: file_descriptor(contract_path, required=True),
            EXECUTION_CONTRACT_FILENAME: file_descriptor(execution_contract_path, required=False),
            DECISION_FILENAME: file_descriptor(decision_path, required=False),
        }
        discovery = load_object(discovery_path, DISCOVERY_FILENAME)
        authority_register = load_object(authority_register_path, AUTHORITY_REGISTER_FILENAME)
        contract = load_object(contract_path, CONTRACT_FILENAME)
        if next(iter(contract), None) != "implementation_decision_policy":
            raise SessionError("build-contract.json must begin with implementation_decision_policy")
        if contract.get("schema") != BUILD_SCHEMA:
            raise SessionError(f"build-contract.json schema must be {BUILD_SCHEMA}")
        claimed_digest = contract.get("contract_digest")
        actual_digest = digest_contract(contract)
        if claimed_digest != actual_digest:
            raise SessionError("build-contract.json contract_digest is invalid")

        compiler = native_compiler()
        try:
            authority_register = compiler.validate_authority_register(authority_register)
        except compiler.CompilerError as error:
            raise SessionError(
                f"{AUTHORITY_REGISTER_FILENAME} is invalid: {native_error(error)}"
            ) from error
        recompile_discovery(discovery, authority_register, contract, compiler)
        projection = validate_execution_projection(
            execution_contract_path,
            discovery,
            authority_register,
            contract,
        )
        ids = validate_trace(contract)
        decisions = parse_decisions(decision_path, claimed_digest, set(ids["requirements"]))
        scopes = scope_paths(contract)
        repository, repository_inputs = collect_repository_evidence(
            arguments.repo_root.resolve(), scopes, arguments.diff_range, arguments.diff_file
        )
        input_artifacts.update(repository_inputs)
        missing_evidence: list[str] = []
        if not decision_path.is_file():
            missing_evidence.append("decision.jsonl absent - no implementation gap decisions were recorded")
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "session_dir": str(session_dir),
            "contract_digest": claimed_digest,
            "input_artifacts": input_artifacts,
            "contract_sha256": input_artifacts[CONTRACT_FILENAME]["sha256"],
            "discovery_sha256": input_artifacts[DISCOVERY_FILENAME]["sha256"],
            "authority_register_sha256": input_artifacts[AUTHORITY_REGISTER_FILENAME]["sha256"],
            "projection_gate": projection,
            "ids": ids,
            "scope_paths": scopes,
            "build_contract": contract,
            "decisions": decisions,
            "repository_evidence": repository,
            "missing_evidence": missing_evidence,
        }
        output = arguments.output or session_dir / BUNDLE_FILENAME
        write_bundle(output, bundle)
        print(
            f"compiler session valid: {claimed_digest} | requirements {len(ids['requirements'])} | "
            f"verifications {len(ids['verifications'])} | decisions {len(decisions)}"
        )
        return 0
    except (OSError, UnicodeError, SessionError, ValueError) as error:
        print(f"compiler_session_check: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
