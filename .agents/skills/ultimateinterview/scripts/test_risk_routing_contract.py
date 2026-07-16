#!/usr/bin/env python3
"""Static contract tests for Ultimateinterview risk-routed workflow rules."""

from pathlib import Path


SKILL = Path(__file__).parents[1] / "SKILL.md"
JSON_CONTRACTS = Path(__file__).parents[1] / "references" / "json-contracts.md"
POSTMORTEM_SKILL = Path(__file__).parents[2] / "ultimateinterview-postmortem" / "SKILL.md"


def test_lightweight_path_is_fail_closed_and_preserves_deterministic_gates() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "Use `lightweight` only when every condition below is established" in text
    assert "If any lightweight condition is unknown or false" in text
    assert "compilation, projection, plan binding, or final deterministic gates" in text
    assert "upgrade to `standard` before finalization" in text


def test_sensitive_or_cross_boundary_changes_are_high_risk() -> None:
    text = SKILL.read_text(encoding="utf-8")

    for trigger in (
        "authorization or security boundaries",
        "credentials or sensitive data",
        "irreversible data mutation",
        "migration or compatibility guarantees",
        "a public API or protocol",
        "multiple owning systems",
    ):
        assert trigger in text


def test_only_lightweight_skips_fresh_context_review() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "For `standard` and `high-risk`, run exactly one fresh-context reviewer" in text
    assert "For `lightweight`, do not run a reviewer" in text
    assert "All paths produce the same sealed Build Contract" in text


def test_routing_record_is_evidence_not_authority() -> None:
    text = JSON_CONTRACTS.read_text(encoding="utf-8")

    assert "Every new `evidence-map.md` starts with a `Workflow Path` record" in text
    assert "process evidence, not product authority" in text
    assert "Lightweight sessions skip only the fresh-context reviewer" in text


def test_every_path_remains_agent_agnostic_and_postmortem_auditable() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    contracts = JSON_CONTRACTS.read_text(encoding="utf-8")
    postmortem = POSTMORTEM_SKILL.read_text(encoding="utf-8")

    assert "required by `ultimateinterview-postmortem`" in skill
    assert "particular agent vendor, model, UI, or orchestration feature" in skill
    assert "Every path preserves the same session lineage" in contracts
    assert "Apply the same postmortem checks" in postmortem
    assert "routing path never changes the sealed authority or verdict classes" in postmortem
