#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts import probe_policy

DIGEST = "a" * 64


def authorization(scope: str) -> dict[str, str | list[str]]:
    level = "L2" if scope.startswith("l2:") else "L3"
    return {
        "authorization_id": f"AUTH-{level}",
        "level": level,
        "scope": scope,
        "approved_by": "requirements-owner",
        "target_ledger_ids": ["REQ-001"],
        "contract_digest": DIGEST,
    }


def decision_payload(*, level: str, staged_only: bool | None = None) -> dict[str, object]:
    staged = level == "L3" and staged_only is True
    production = level == "L3" and not staged
    payload: dict[str, object] = {
        "probe_id": f"PROBE-{level}",
        "intent": "discovery",
        "discovery_probe_id": None,
        "selected_level": level,
        "target_ledger_ids": ["REQ-001"],
        "predicate": "The bounded behavior differs from the reviewed contract.",
        "contract_digest": DIGEST,
        "sandboxable_observable": level == "L1",
        "requires_runtime_observation": level == "L2",
        "production_only": production,
        "previous_level_insufficiency": None if level == "L0" else "Lower levels are insufficient.",
        "skipped_level_reason": None if level in {"L0", "L1"} else "The requested surface needs escalation.",
        "execution_scope": None if level in {"L0", "L1"} else ("l3:staged-telemetry" if staged else "l3:production-telemetry" if production else "l2:prototype+runtime-observation"),
        "authorization": None if level in {"L0", "L1"} else authorization("l3:staged-telemetry" if staged else "l3:production-telemetry" if production else "l2:prototype+runtime-observation"),
    }
    if staged_only is not None:
        payload["staged_only"] = staged_only
    return payload


def material_result_payload(level: str) -> dict[str, object]:
    return {
        "result_id": f"RESULT-{level}",
        "decision_id": f"PROBE-{level}",
        "intent": "discovery",
        "level": level,
        "target_ledger_ids": ["REQ-001"],
        "contract_digest": DIGEST,
        "producer_lineages": [
            {"producer_id": "prototype", "independence_key": "prototype", "kind": "executable-prototype"},
            {"producer_id": "observer", "independence_key": "observer", "kind": "user-runtime-observation"},
        ] if level == "L2" else [
            {"producer_id": "staged", "independence_key": "staged", "kind": "staged-telemetry"},
        ],
        "artifact_refs": ["artifacts/probe.json"],
        "outcome": "material-divergence",
        "evidence_credit": 1,
        "completeness_credit": 0,
        "reopen_required": True,
        "gap_origin": "origin:probe",
    }


@pytest.mark.parametrize("level", ("L0", "L1", "L2", "L3"))
def test_legacy_probe_decisions_default_staged_only_false(level: str) -> None:
    # Given
    payload = decision_payload(level=level)

    # When
    parsed = probe_policy.ProbeDecision.model_validate(payload)

    # Then
    assert parsed.staged_only is False


def test_staged_only_reaches_l3_staged_scope() -> None:
    # Given
    payload = decision_payload(level="L3", staged_only=True)

    # When
    parsed = probe_policy.ProbeDecision.model_validate(payload)

    # Then
    assert parsed.selected_level is probe_policy.ProbeLevel.L3
    assert parsed.execution_scope is probe_policy.AuthorizationScope.L3_STAGED_TELEMETRY


def test_staged_only_rejects_production_scope() -> None:
    # Given
    payload = decision_payload(level="L3", staged_only=True)
    payload["execution_scope"] = "l3:production-telemetry"
    payload["authorization"] = authorization("l3:production-telemetry")

    # When / Then
    with pytest.raises(ValidationError, match="staged"):
        probe_policy.ProbeDecision.model_validate(payload)


@pytest.mark.parametrize(
    "additional_signal",
    ("sandboxable_observable", "requires_runtime_observation", "production_only"),
)
def test_staged_only_rejects_all_competing_level_signals(additional_signal: str) -> None:
    # Given
    payload = decision_payload(level="L3", staged_only=True)
    payload[additional_signal] = True

    # When / Then
    with pytest.raises(ValidationError, match="distinct strict booleans"):
        probe_policy.ProbeDecision.model_validate(payload)


def test_staged_only_rejects_boolean_coercion() -> None:
    # Given
    payload = decision_payload(level="L0")
    payload["staged_only"] = "false"

    # When / Then
    with pytest.raises(ValidationError):
        probe_policy.ProbeDecision.model_validate(payload)


@pytest.mark.parametrize("level", ("L2", "L3"))
def test_declared_high_level_material_divergence_has_zero_credit(level: str) -> None:
    # Given
    payload = material_result_payload(level)

    # When / Then
    with pytest.raises(ValidationError, match="declared.*zero credit"):
        probe_policy.ProbeResult.model_validate(payload)
