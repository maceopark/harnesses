#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
#      uv run scripts/test_predicate_lint.py
# ──────────────────

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import predicate_lint

runner = CliRunner()
CASES = Path(__file__).resolve().parent / "regression_fixtures" / "predicate_cases"


def lint(session: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(predicate_lint.app, [str(session), *extra])
    return result.exit_code, result.output


# --- cross-arm fixture cases (committed under regression_fixtures/predicate_cases) ---


def test_case_a_bool_int_fires_numeric_coercion() -> None:
    code, out = lint(CASES / "a-bool-int")
    assert code == 0  # advisory by default
    assert "predicate_ok: no" in out
    assert "numeric-coercion" in out
    assert "reject-category" not in out  # no reject word in this handoff
    assert "version-floor" not in out


def test_case_a_bool_int_clean_suppresses_coercion() -> None:
    code, out = lint(CASES / "a-bool-int-clean")
    assert code == 0
    assert "numeric-coercion" not in out
    assert "predicate_ok: yes" in out


def test_case_a_version_floor_fires() -> None:
    code, out = lint(CASES / "a-version-floor")
    assert code == 0
    assert "version-floor" in out
    assert "numeric-coercion" not in out


def test_case_b_invalid_id_fires_reject_category() -> None:
    code, out = lint(CASES / "b-invalid-id")
    assert code == 0
    assert "reject-category" in out
    assert "numeric-coercion" not in out


def test_case_b_invalid_id_clean_suppresses_reject_category() -> None:
    code, out = lint(CASES / "b-invalid-id-clean")
    assert code == 0
    assert "predicate_ok: yes" in out


def test_case_c_next_id_fires_both() -> None:
    """The real app-5 escape shape: int-typed store + bare 'invalid next_id'."""
    code, out = lint(CASES / "c-next-id")
    assert code == 0
    assert "reject-category" in out
    assert "numeric-coercion" in out


def test_all_clean_control_passes() -> None:
    code, out = lint(CASES / "all-clean")
    assert code == 0
    assert "predicate_ok: yes" in out


# --- gate behavior ---


def test_strict_blocks_on_finding() -> None:
    code, out = lint(CASES / "a-bool-int", "--strict")
    assert code == 1
    assert "numeric-coercion" in out


def test_strict_passes_when_clean() -> None:
    code, out = lint(CASES / "all-clean", "--strict")
    assert code == 0, out


def test_missing_handoff_exits_two(tmp_path: Path) -> None:
    session = tmp_path / "empty"
    session.mkdir()
    code, _ = lint(session)
    assert code == 2


# --- detector unit precision (guards against the "is not overwritten" false suppression) ---


def test_reject_signal_not_over_suppressed_by_boilerplate() -> None:
    # 'is not overwritten' must NOT count as a predicate signal.
    part1_table = (
        "| ID | Req | Crit | Src |\n"
        "| --- | --- | --- | --- |\n"
        "| REQ-1 | Invalid store data is a storage error and is not overwritten "
        "| Given a corrupt shape, exit 3 | g1 |\n"
    )
    findings = predicate_lint.reject_findings(part1_table)
    assert any("reject-category" in f for f in findings)


def test_modal_rejection_does_not_define_category_membership() -> None:
    part1_table = (
        "| ID | Requirement | Acceptance | Source |\n"
        "| --- | --- | --- | --- |\n"
        "| REQ-1 | invalid identifier must be rejected | exits 2 | g1 |\n"
    )
    findings = predicate_lint.reject_findings(part1_table)
    assert any("reject-category" in finding for finding in findings)


def test_coercion_suppressed_when_boundary_discussed() -> None:
    typed = "next_id: int counter"
    assert predicate_lint.coercion_finding(typed) is not None
    pinned = "next_id: int counter; a JSON boolean is not a valid integer here"
    assert predicate_lint.coercion_finding(pinned) is None


def test_version_floor_only_one_sided() -> None:
    upper_only = "store version greater than 1 exits 1"
    assert predicate_lint.version_floor_finding(upper_only) is not None
    both = "store version greater than 1 exits 1; version below 1 is corrupt"
    assert predicate_lint.version_floor_finding(both) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
