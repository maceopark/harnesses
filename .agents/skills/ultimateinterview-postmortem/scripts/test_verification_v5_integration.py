#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verification_execution_lint as lint
from postmortem_bundle import JsonValue
from verification_legacy_lint import EvaluationInputError
from verification_return_lint import StableInputError, bundle_mode
from scripts.build_contract_schema import ContractBody, body_digest
from test_bundle_v5 import _contract, _pack, _return, _session


def _v5_session(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    session, artifacts = _session(tmp_path)
    (session / "execution-return.json").write_text(
        json.dumps(_return(_contract(), artifacts)), encoding="utf-8"
    )
    result = _pack(session)
    assert result.exit_code == 0, result.output
    return session, artifacts


def _report(rows: tuple[str, ...], *, stable: bool = True) -> str:
    identity = "VER-ID" if stable else "Spec row"
    return (
        "# Postmortem\n\n## Verification Execution\n\n"
        f"| {identity} | Check | Kind | Execution | Result | Captured artifact | Observed effect |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )


def _valid_report(session: Path, artifacts: dict[str, str]) -> None:
    rows = (
        f"| VER-001 | focused suite | test | exact | pass | {artifacts['ver-1.txt']} | passed |",
        f"| VER-002 | installed surface | real-surface | exact | pass | {artifacts['ver-2.txt']} | saved |",
    )
    (session / "postmortem.md").write_text(_report(rows), encoding="utf-8")


def _substitute_embedded_contract(session: Path) -> dict[str, JsonValue]:
    bundle_path = session / "evidence_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    embedded = bundle["contract"]["build_contract"]
    embedded["goal"] = "Substituted goal."
    body = ContractBody.model_validate(
        {key: value for key, value in embedded.items() if key != "contract_digest"}
    )
    embedded["contract_digest"] = body_digest(body)
    bundle["contract"]["execution_return"]["contract_digest"] = embedded[
        "contract_digest"
    ]
    return bundle


def test_v5_verification_joins_by_ver_id_when_rows_are_reordered(tmp_path: Path) -> None:
    # Given a v5 bundle whose return order differs from the report order
    session, artifacts = _v5_session(tmp_path)
    rows = (
        f"| VER-001 | focused suite | test | exact | pass | {artifacts['ver-1.txt']} | passed |",
        f"| VER-002 | installed surface | real-surface | exact | pass | {artifacts['ver-2.txt']} | saved |",
    )
    (session / "postmortem.md").write_text(_report(rows), encoding="utf-8")

    # When evaluated, Then stable IDs and the validated contract digest make order irrelevant
    assert lint.evaluate(session) == []


def test_v5_verification_rejects_artifact_from_another_ver(tmp_path: Path) -> None:
    # Given a report that swaps capture provenance between stable VER identities
    session, artifacts = _v5_session(tmp_path)
    rows = (
        f"| VER-001 | focused suite | test | exact | pass | {artifacts['ver-2.txt']} | passed |",
        f"| VER-002 | installed surface | real-surface | exact | pass | {artifacts['ver-1.txt']} | saved |",
    )
    (session / "postmortem.md").write_text(_report(rows), encoding="utf-8")

    # When evaluated, Then the return-to-report join fails
    violations = lint.evaluate(session)
    assert any("VER-001" in violation and "artifact" in violation for violation in violations)


def test_schema_v3_bundle_is_explicit_positional_compatibility(tmp_path: Path) -> None:
    # Given a historical v3 bundle and a non-pass legacy report row
    session = tmp_path / ".ultimateinterview" / "legacy"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text(
        """# Part 1

## Verification Commands
| Check | Command / action | Pass condition |
| --- | --- | --- |
| suite | `python3 -m pytest` | passes |

# Part 2
""",
        encoding="utf-8",
    )
    rows = ("| 1 | suite | test | not-run | not-run | | legacy evidence absent |",)
    (session / "postmortem.md").write_text(_report(rows, stable=False), encoding="utf-8")
    (session / "evidence_bundle.json").write_text(
        json.dumps({"schema_version": 3, "artifacts": {"files": []}}), encoding="utf-8"
    )

    # When evaluated, Then v3 remains readable without pretending captures exist
    assert lint.evaluate(session) == []


def test_v5_rejects_positional_report_shape(tmp_path: Path) -> None:
    # Given a new v5 bundle paired with a legacy positional report table
    session, _artifacts = _v5_session(tmp_path)
    rows = ("| 1 | focused suite | test | not-run | not-run | | not run |",)
    (session / "postmortem.md").write_text(_report(rows, stable=False), encoding="utf-8")

    # When evaluated, Then new evidence cannot silently fall back to row position
    violations = lint.evaluate(session)
    assert any("VER-ID" in violation for violation in violations)




def test_stable_bundle_rejects_substituted_embedded_contract_and_return(
    tmp_path: Path,
) -> None:
    session, artifacts = _v5_session(tmp_path)
    _valid_report(session, artifacts)
    bundle_path = session / "evidence_bundle.json"
    bundle = _substitute_embedded_contract(session)
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="current build-contract"):
        lint.evaluate(session)


def test_stable_bundle_rejects_joint_sidecar_and_embedded_contract_substitution(
    tmp_path: Path,
) -> None:
    session, artifacts = _v5_session(tmp_path)
    _valid_report(session, artifacts)
    bundle = _substitute_embedded_contract(session)
    (session / "evidence_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    contract = bundle["contract"]
    assert isinstance(contract, dict)
    build_contract = contract["build_contract"]
    (session / "build-contract.json").write_text(
        json.dumps(build_contract), encoding="utf-8"
    )

    with pytest.raises(EvaluationInputError, match="freshly compiled"):
        lint.evaluate(session)


def test_stable_bundle_rejects_embedded_return_substitution(tmp_path: Path) -> None:
    session, artifacts = _v5_session(tmp_path)
    _valid_report(session, artifacts)
    bundle_path = session / "evidence_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["contract"]["execution_return"]["changed_paths"] = ["substituted-benign.py"]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="current execution-return sidecar"):
        lint.evaluate(session)


def test_stable_bundle_rejects_artifact_manifest_substitution(tmp_path: Path) -> None:
    session, artifacts = _v5_session(tmp_path)
    _valid_report(session, artifacts)
    bundle_path = session / "evidence_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["artifacts"]["files"][0]["sha256"] = "0" * 64
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="artifact manifest"):
        lint.evaluate(session)


def test_unknown_future_bundle_versions_fail_closed(tmp_path: Path) -> None:
    bundle_path = tmp_path / "evidence_bundle.json"
    for version in (1, 2, 6, 999):
        bundle_path.write_text(
            json.dumps(
                {
                    "schema_version": version,
                    "contract": {"compatibility_mode": "stable-v5"},
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(StableInputError, match="unsupported bundle schema_version"):
            bundle_mode(bundle_path)
