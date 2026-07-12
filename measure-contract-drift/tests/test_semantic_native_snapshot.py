from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from driftbench.native_snapshot import NativeSnapshotValidationError, validate_native_snapshot
from driftbench.semantic import Atom, Assertion, compare_assertions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = PROJECT_ROOT / "protocol" / "ultimateinterview" / "ui-native-77b0327-r4"


def _atom() -> dict[str, str]:
    return {
        "guard": "a bookmark ID is known",
        "effect": "one tag is added to that bookmark",
        "polarity": "must",
        "boundary": "the URL and title remain unchanged",
        "temporal": "after a successful tag command",
    }


def test_semantic_atom_requires_exact_five_dimension_equivalence() -> None:
    expected = {"atoms": [_atom()]}
    assert compare_assertions(expected, {"atoms": [_atom()]}).model_dump() == {
        "relation": "exact",
        "primary_credit": 1,
    }

    for field, value in (
        ("guard", "a bookmark ID is unknown"),
        ("effect", "all bookmark tags are replaced"),
        ("polarity", "must-not"),
        ("boundary", "the URL may change"),
        ("temporal", "before command validation"),
    ):
        actual = _atom()
        actual[field] = value
        result = compare_assertions(expected, {"atoms": [actual]})
        assert result.primary_credit == 0, field
        assert result.exact_equivalent is False, field


def test_semantic_atom_rejects_incoherent_polarities_and_noncanonical_text() -> None:
    positive = _atom()
    negative = {**positive, "polarity": "must-not"}
    with pytest.raises(ValueError, match="both polarities"):
        Assertion.model_validate({"atoms": [positive, negative]}, strict=True)
    with pytest.raises(ValueError, match="trimmed"):
        Atom.model_validate({**positive, "effect": " one tag is added "}, strict=True)


def test_frozen_native_snapshot_validates_without_workspace_agents() -> None:
    result = validate_native_snapshot(SNAPSHOT)

    assert result.snapshot_id == "ui-native-77b0327-r4"
    assert result.record_count == 40
    assert result.source_tree_digest == "81895c0131ab843b2ffbfb9ba85b3e608ec8d9e3667a0ca540d808858194c152"

    fixture = json.loads((SNAPSHOT / "fixtures" / "native-v1-structural-valid.json").read_text(encoding="utf-8"))
    working_directory = SNAPSHOT / fixture["invocation"]["working_directory"]
    assert working_directory.is_dir()
    assert all((SNAPSHOT / path).is_file() for path in fixture["source_fixture"]["required_paths"])

def test_frozen_native_v1_fixture_passes_without_workspace_agents(tmp_path: Path) -> None:
    copied_snapshot = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT, copied_snapshot)
    fixture = json.loads(
        (copied_snapshot / "fixtures" / "native-v1-structural-valid.json").read_text(encoding="utf-8")
    )
    invocation = fixture["invocation"]
    completed = subprocess.run(
        invocation["argv"],
        cwd=copied_snapshot / invocation["working_directory"],
        check=False,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
    )

    assert completed.returncode == fixture["expected"]["exit_code"], completed.stderr
    receipt = json.loads(completed.stdout)
    assert (
        receipt["implementation_gate"]["implementation_ready"]
        == fixture["expected"]["implementation_gate"]["implementation_ready"]
    )
    assert validate_native_snapshot(copied_snapshot).record_count == 40



def test_frozen_native_snapshot_rejects_substituted_bytes(tmp_path: Path) -> None:
    copied_snapshot = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT, copied_snapshot)
    target = copied_snapshot / "frozen" / ".agents" / "skills" / "ultimateinterview" / "SKILL.md"
    target.write_bytes(target.read_bytes() + b"\nsubstituted\n")

    with pytest.raises(NativeSnapshotValidationError, match="digest mismatch"):
        validate_native_snapshot(copied_snapshot)


def test_v2_fixture_remains_an_unscored_expected_failure() -> None:
    fixture = json.loads((SNAPSHOT / "fixtures" / "v2-noncreditable-expected-fail.json").read_text(encoding="utf-8"))

    assert fixture["expected"]["exit_code"] == 1
    assert fixture["scored"] is False
    assert fixture["scorecard_eligible"] is False
    assert "success" in fixture["assertions_not_made"][0]
