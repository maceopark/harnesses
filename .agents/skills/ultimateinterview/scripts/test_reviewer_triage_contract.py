#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pytest>=8.0"]
# ///

from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
HANDOFF = (SKILL_ROOT / "references" / "handoff-sequence.md").read_text(encoding="utf-8")
AUDIT = (SKILL_ROOT / "references" / "audit-checklists.md").read_text(encoding="utf-8")
OUTPUT = (SKILL_ROOT / "references" / "output-template.md").read_text(encoding="utf-8")


def test_reviewer_findings_require_three_way_triage_before_contract_edits() -> None:
    for label in ("repo-answerable", "delegable-implementation", "owner-decision"):
        assert label in SKILL
        assert label in HANDOFF
    assert "BEFORE changing the ledger, handoff, Build Contract" in SKILL
    assert "BEFORE editing Part 1" in HANDOFF


def test_owner_decisions_return_endgame_to_loop_instead_of_guessing() -> None:
    assert "ENDGAME is not a one-way state" in SKILL
    assert "same-turn handoff obligation is suspended" in SKILL
    assert "stop ENDGAME" in HANDOFF
    assert "return to LOOP" in HANDOFF
    assert "Direct-patch prohibition" in HANDOFF


def test_normative_reviewer_values_cannot_be_silently_folded_back() -> None:
    for signal in (
        "retention/deletion",
        "authorization",
        "numeric quality threshold",
        "irreversible migration/data loss",
    ):
        assert signal in SKILL
    assert "retention period, timeout, threshold, enum member, permission rule" in HANDOFF
    assert "new normative value absent from the ledger" in AUDIT


def test_fresh_implementer_table_requires_triage_provenance() -> None:
    assert "triage classification" in OUTPUT
    assert "settled ledger id" in OUTPUT
    assert "current owner/delegated evidence" in OUTPUT
    assert "launder a reviewer or model recommendation" in OUTPUT
