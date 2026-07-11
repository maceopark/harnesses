#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent
ULTIMATEINTERVIEW_DIR: Final[Path] = SCRIPT_DIR.parents[1] / "ultimateinterview"
sys.path.insert(0, str(ULTIMATEINTERVIEW_DIR))

from execution_return import (  # noqa: E402
    ExecutionExpectation,
    ExecutionReturnContractError,
    ExpectedVerification,
    validate_execution_return,
)
from scripts import implementation_gate  # noqa: E402
from scripts.build_contract_schema import BuildContract  # noqa: E402

BUILD_CONTRACT_FILENAME: Final[str] = "build-contract.json"
EXECUTION_RETURN_FILENAME: Final[str] = "execution-return.json"
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class BundleV5Error(ValueError):
    artifact: str
    detail: str

    def __str__(self) -> str:
        return f"{self.artifact}: {self.detail}"


def _validated_contract(session_dir: Path, handoff_text: str) -> BuildContract | None:
    path = session_dir / BUILD_CONTRACT_FILENAME
    if not path.is_file():
        return None
    try:
        contract = BuildContract.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise BundleV5Error(BUILD_CONTRACT_FILENAME, str(error)) from error
    expected_source = implementation_gate.contract_digest(handoff_text)
    if contract.source_part1_sha256 != expected_source:
        raise BundleV5Error(
            BUILD_CONTRACT_FILENAME,
            "source_part1_sha256 does not match the current handoff Part 1",
        )
    expected_log = f".ultimateinterview/{session_dir.name}/decisions.jsonl"
    if contract.decision_log_path != expected_log:
        raise BundleV5Error(
            BUILD_CONTRACT_FILENAME,
            f"decision_log_path must be {expected_log!r}",
        )
    return contract


def _decision_refs(path: Path) -> tuple[str, ...]:
    lines = (
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    return tuple(f"decision#{index}" for index, _line in enumerate(lines, start=1))


def _validated_return(
    session_dir: Path,
    contract: BuildContract,
    artifact_ids: frozenset[str],
) -> dict[str, JsonValue] | None:
    path = session_dir / EXECUTION_RETURN_FILENAME
    if not path.is_file():
        return None
    decisions_path = session_dir / "decisions.jsonl"
    if not decisions_path.is_file():
        raise BundleV5Error(
            EXECUTION_RETURN_FILENAME,
            "cannot validate decision-log provenance because decisions.jsonl is absent",
        )
    decisions = decisions_path.read_bytes()
    expectation = ExecutionExpectation(
        contract_digest=contract.contract_digest,
        requirement_ids=tuple(requirement.id for requirement in contract.requirements),
        verifications=tuple(
            ExpectedVerification(id=row.id, command_action=row.command_action)
            for row in contract.verifications
        ),
        decision_log_path=contract.decision_log_path,
        decision_log_digest=hashlib.sha256(decisions).hexdigest(),
        decision_record_refs=_decision_refs(decisions_path),
    )
    try:
        parsed = validate_execution_return(path.read_bytes(), expectation)
    except (OSError, UnicodeDecodeError, ValidationError, ExecutionReturnContractError) as error:
        raise BundleV5Error(EXECUTION_RETURN_FILENAME, str(error)) from error
    claimed = frozenset((*parsed.capture_artifact_ids, *parsed.evidence_artifact_ids))
    if unknown := sorted(claimed - artifact_ids):
        raise BundleV5Error(
            EXECUTION_RETURN_FILENAME,
            "claims artifact id(s) absent from the observed evidence manifest: "
            + ", ".join(unknown),
        )
    return parsed.model_dump(mode="json")


def project_contract_evidence(
    session_dir: Path,
    handoff_text: str,
    artifact_ids: frozenset[str],
    missing_evidence: list[str],
) -> dict[str, JsonValue]:
    contract = _validated_contract(session_dir, handoff_text)
    return_path = session_dir / EXECUTION_RETURN_FILENAME
    if contract is None:
        if return_path.exists():
            raise BundleV5Error(
                EXECUTION_RETURN_FILENAME,
                f"is present but {BUILD_CONTRACT_FILENAME} is absent",
            )
        missing_evidence.append(
            f"{BUILD_CONTRACT_FILENAME} absent - bundle uses explicit legacy-v4 compatibility"
        )
        missing_evidence.append(
            f"{EXECUTION_RETURN_FILENAME} absent - execution conformance is process evidence missing"
        )
        return {
            "compatibility_mode": "legacy-v4",
            "build_contract_path": None,
            "build_contract": None,
            "execution_return_path": None,
            "execution_return": None,
        }
    execution_return = _validated_return(session_dir, contract, artifact_ids)
    if execution_return is None:
        missing_evidence.append(
            f"{EXECUTION_RETURN_FILENAME} absent - execution conformance is process evidence missing"
        )
    return {
        "compatibility_mode": "stable-v5",
        "build_contract_path": str((session_dir / BUILD_CONTRACT_FILENAME).resolve()),
        "build_contract": contract.model_dump(mode="json"),
        "execution_return_path": str(return_path.resolve()) if execution_return else None,
        "execution_return": execution_return,
    }
