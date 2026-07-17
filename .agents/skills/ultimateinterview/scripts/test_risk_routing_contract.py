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


def test_lightweight_is_zero_follow_up_and_upgrades_before_questions() -> None:
    text = SKILL.read_text(encoding="utf-8")

    zero_follow_up = "Lightweight is a zero-follow-up path."
    upgrade_before_asking = (
        "If any confirmation, material-decision question, or pressure test is needed, "
        "upgrade to `standard` or `high-risk` before asking and never downgrade."
    )
    assert zero_follow_up in text
    assert upgrade_before_asking in text
    assert text.index(zero_follow_up) < text.index(upgrade_before_asking)


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


def test_pre_compilation_check_preserves_owner_stated_obligations() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "Before compilation, perform one bounded blind-spot check" in text
    assert "testable owner-stated obligations already present" in text
    assert "observable outcomes, boundaries and explicit non-goals" in text
    assert "Preserve each in the contract or record it as explicitly out of scope" in text
    assert "without claiming discovery completeness" in text


def test_projection_preserves_decision_bearing_owner_language() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "Do not reinterpret decision-bearing owner language" in text
    assert "Preserve its modality, scope, exceptions, failure result, and verification meaning" in text
    assert "Ask for correction only if faithful projection is not possible" in text
    assert "on `lightweight`, upgrade before asking" in text


def test_standard_and_high_risk_share_bounded_pressure_rule() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "For `standard` and `high-risk`, resolve safety or irreversibility gaps first" in text
    assert "then interface or ownership gaps" in text
    assert "then choose among remaining gaps by dependency leverage" in text
    assert "ask at most one conditional pressure test per material owner decision" in text
    assert "only when the accepted answer could hide a material exception, boundary, or failure case" in text
    assert "After the pressure test, immediately reapply the termination test below" in text
    assert "Do not add ambiguity scores, mandatory rounds, ledgers, panels, extra artifacts, or runtime state" in text
    assert "could two plausibly compliant implementations differ" in text
    assert "finish as `incomplete` rather than guessing" in text


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
