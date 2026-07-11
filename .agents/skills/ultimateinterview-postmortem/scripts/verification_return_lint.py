#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import json
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, assert_never

from pydantic import ValidationError

ULTIMATEINTERVIEW: Final[Path] = Path(__file__).resolve().parents[2] / "ultimateinterview"
sys.path.insert(0, str(ULTIMATEINTERVIEW))

from execution_return import (  # noqa: E402
    AdaptedPass,
    ExactPass,
    ExecutionExpectation,
    ExecutionReturn,
    ExecutionReturnContractError,
    ExpectedVerification,
    Failed,
    NotRun,
    validate_execution_return,
)
from evidence_artifacts import (  # noqa: E402
    EvidenceArtifactError,
    validate_manifest_ids,
)
from postmortem_bundle import JsonValue, artifact_ids  # noqa: E402
from postmortem_lint import first_table, section_body, split_sections  # noqa: E402
from scripts.build_contract_schema import BuildContract  # noqa: E402
from scripts import build_contract, implementation_gate  # noqa: E402

type BundleMode = Literal["absent", "legacy", "stable-v5"]
PREFIX: Final[str] = "verification-execution:"
COLUMNS: Final[tuple[str, ...]] = (
    "VER-ID", "Check", "Kind", "Execution", "Result", "Captured artifact", "Observed effect",
)


@dataclass(frozen=True, slots=True)
class StableInputError(ValueError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class StableReportRow:
    verification_id: str
    check: str
    kind: str
    execution: str
    result: str
    artifact_id: str
    observed_effect: str


def _bundle(path: Path) -> dict[str, JsonValue]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StableInputError(f"evidence_bundle.json did not parse: {error}") from error
    if not isinstance(value, dict):
        raise StableInputError("evidence_bundle.json root is not an object")
    return value


def bundle_mode(path: Path) -> BundleMode:
    if not path.exists():
        return "absent"
    data = _bundle(path)
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise StableInputError(f"invalid bundle schema_version {version!r}")
    if version in {3, 4}:
        return "legacy"
    if version != 5:
        raise StableInputError(f"unsupported bundle schema_version {version!r}")
    projection = data.get("contract")
    if not isinstance(projection, dict):
        raise StableInputError("schema v5 bundle has no contract projection")
    mode = projection.get("compatibility_mode")
    if mode == "legacy-v4":
        return "legacy"
    if mode != "stable-v5":
        raise StableInputError(f"unknown contract compatibility_mode {mode!r}")
    return "stable-v5"


def _current_contract(path: Path, projected: BuildContract) -> BuildContract:
    session_dir = path.parent
    sidecar = session_dir / "build-contract.json"
    handoff = session_dir / "handoff.md"
    try:
        current = BuildContract.model_validate_json(sidecar.read_bytes())
        handoff_text = handoff.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as error:
        raise StableInputError(f"current build-contract inputs did not validate: {error}") from error
    if current.source_part1_sha256 != implementation_gate.contract_digest(handoff_text):
        raise StableInputError("current build-contract is not bound to current handoff Part 1")
    try:
        compiled = build_contract.compile_handoff(handoff_text)
    except build_contract.BuildContractCompileError as error:
        raise StableInputError(f"current handoff Part 1 cannot compile: {error}") from error
    if current != compiled:
        raise StableInputError("current build-contract differs from freshly compiled handoff Part 1")
    if current != projected:
        raise StableInputError("embedded contract differs from current build-contract sidecar")
    return current


def _decision_refs(path: Path) -> tuple[str, ...]:
    lines = (line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return tuple(f"decision#{index}" for index, _line in enumerate(lines, start=1))


def _validated_return(
    path: Path,
    contract: BuildContract,
    raw_return: JsonValue,
    observed_artifact_ids: frozenset[str],
) -> ExecutionReturn | None:
    if raw_return is None:
        if (path.parent / "execution-return.json").exists():
            raise StableInputError("embedded execution return is absent but current sidecar exists")
        return None
    decisions_path = path.parent / "decisions.jsonl"
    try:
        decisions = decisions_path.read_bytes()
        expectation = ExecutionExpectation(
            contract_digest=contract.contract_digest,
            requirement_ids=tuple(item.id for item in contract.requirements),
            verifications=tuple(
                ExpectedVerification(id=item.id, command_action=item.command_action)
                for item in contract.verifications
            ),
            decision_log_path=contract.decision_log_path,
            decision_log_digest=hashlib.sha256(decisions).hexdigest(),
            decision_record_refs=_decision_refs(decisions_path),
        )
        parsed = validate_execution_return(json.dumps(raw_return), expectation)
        current = validate_execution_return(
            (path.parent / "execution-return.json").read_bytes(), expectation
        )
    except (
        OSError,
        UnicodeDecodeError,
        ValidationError,
        ValueError,
        ExecutionReturnContractError,
    ) as error:
        raise StableInputError(f"current execution-return inputs did not validate: {error}") from error
    if parsed != current:
        raise StableInputError("embedded execution return differs from current execution-return sidecar")
    claimed = frozenset((*parsed.capture_artifact_ids, *parsed.evidence_artifact_ids))
    if unknown := sorted(claimed - observed_artifact_ids):
        raise StableInputError(
            "execution return claims artifacts absent from current manifest: " + ", ".join(unknown)
        )
    return parsed


def _current_manifest_ids(path: Path, data: dict[str, JsonValue]) -> frozenset[str]:
    artifacts = data.get("artifacts")
    files = artifacts.get("files") if isinstance(artifacts, dict) else None
    if not isinstance(files, list):
        raise StableInputError("schema v5 bundle has no artifact manifest")
    try:
        return validate_manifest_ids(files, path.parent.parent.parent.resolve())
    except (OSError, EvidenceArtifactError) as error:
        raise StableInputError(f"current artifact manifest: {error}") from error


def _inputs(path: Path) -> tuple[BuildContract, ExecutionReturn | None]:
    data = _bundle(path)
    projection = data.get("contract")
    if not isinstance(projection, dict):
        raise StableInputError("schema v5 bundle has no contract projection")
    try:
        projected = BuildContract.model_validate_json(
            json.dumps(projection.get("build_contract"))
        )
        contract = _current_contract(path, projected)
        observed_artifacts = _current_manifest_ids(path, data)
        execution_return = _validated_return(
            path, contract, projection.get("execution_return"), observed_artifacts
        )
    except (TypeError, ValidationError, ValueError) as error:
        raise StableInputError(f"schema v5 contract projection did not validate: {error}") from error
    return contract, execution_return


def _rows(report: str, violations: list[str]) -> tuple[StableReportRow, ...]:
    body = section_body(split_sections(report), "verification execution")
    table = first_table(body) if body is not None else None
    if table is None:
        violations.append(f"{PREFIX} stable-v5: missing Verification Execution table")
        return ()
    headers, rows = table
    if tuple(headers) != COLUMNS:
        violations.append(
            f"{PREFIX} stable-v5: columns must start with VER-ID, not positional Spec row"
        )
        return ()
    parsed: list[StableReportRow] = []
    for number, row in enumerate(rows, start=1):
        if len(row) != len(COLUMNS):
            violations.append(f"{PREFIX} stable-v5: row {number} has {len(row)} cells")
            continue
        parsed.append(StableReportRow(*row))
    return tuple(parsed)


def _expected_outcome(outcome: ExactPass | AdaptedPass | Failed | NotRun) -> tuple[str, str, str]:
    match outcome:
        case ExactPass(capture_artifact_id=artifact_id):
            return "exact", "pass", artifact_id
        case AdaptedPass(capture_artifact_id=artifact_id):
            return "adapted", "adapted-pass", artifact_id
        case Failed(capture_artifact_id=artifact_id):
            return "exact", "fail", artifact_id
        case NotRun():
            return "not-run", "not-run", ""
        case unreachable:
            assert_never(unreachable)


def evaluate_stable(session_dir: Path, report: str) -> list[str]:
    bundle_path = session_dir / "evidence_bundle.json"
    contract, execution_return = _inputs(bundle_path)
    if execution_return is None:
        return [
            f"{PREFIX} process-evidence: execution-return.json absent; execution conformance is missing evidence"
        ]
    violations: list[str] = []
    rows = _rows(report, violations)
    report_by_id: dict[str, list[StableReportRow]] = {}
    for row in rows:
        report_by_id.setdefault(row.verification_id, []).append(row)
    contract_by_id = {row.id: row for row in contract.verifications}
    outcomes = {row.subject_id: row for row in execution_return.verification_outcomes}
    if set(outcomes) != set(contract_by_id):
        raise StableInputError("execution return verification coverage differs from BuildContract")
    observed_artifacts = artifact_ids(bundle_path)
    for verification_id, contract_row in contract_by_id.items():
        matches = report_by_id.get(verification_id, [])
        if len(matches) != 1:
            violations.append(
                f"{PREFIX} stable-v5: {verification_id} requires exactly one report row"
            )
            continue
        row = matches[0]
        if row.check != contract_row.check or row.kind != contract_row.kind.value:
            violations.append(f"{PREFIX} stable-v5: {verification_id} check/kind differs from contract")
        expected_execution, expected_result, expected_artifact = _expected_outcome(
            outcomes[verification_id]
        )
        if (row.execution, row.result) != (expected_execution, expected_result):
            violations.append(f"{PREFIX} stable-v5: {verification_id} result differs from return")
        if row.artifact_id != expected_artifact:
            violations.append(f"{PREFIX} stable-v5: {verification_id} cites the wrong artifact")
        if expected_artifact and expected_artifact not in observed_artifacts:
            raise StableInputError(f"{verification_id} return artifact is absent from the bundle")
        if expected_result in {"pass", "adapted-pass"} and not row.observed_effect.strip():
            violations.append(f"{PREFIX} stable-v5: {verification_id} has no observed effect")
    for verification_id in sorted(set(report_by_id) - set(contract_by_id)):
        violations.append(f"{PREFIX} stable-v5: unknown report row {verification_id}")
    return violations
