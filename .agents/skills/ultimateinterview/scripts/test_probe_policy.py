#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
# ]
# ///

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_policy  # noqa: E402

DIGEST = "a" * 64


def authorization(level: str = "L2") -> probe_policy.ProbeAuthorization:
    scope = "l2:prototype+runtime-observation" if level == "L2" else "l3:production-telemetry"
    return probe_policy.ProbeAuthorization.model_validate(
        {
            "authorization_id": f"AUTH-{level}",
            "level": level,
            "scope": scope,
            "approved_by": "requirements-owner",
            "target_ledger_ids": ["g7"],
            "contract_digest": DIGEST,
        }
    )


def decision(level: str = "L0", intent: str = "discovery") -> probe_policy.ProbeDecision:
    flags = {
        "sandboxable_observable": level == "L1",
        "requires_runtime_observation": level == "L2",
        "production_only": level == "L3",
    }
    return probe_policy.ProbeDecision.model_validate(
        {
            "probe_id": f"PROBE-{level}-{intent}",
            "intent": intent,
            "discovery_probe_id": None if intent == "discovery" else f"PROBE-{level}-discovery",
            "selected_level": level,
            "target_ledger_ids": ["g7"],
            "predicate": "Observed ordering differs from the reviewed contract.",
            "contract_digest": DIGEST,
            **flags,
            "previous_level_insufficiency": None if level == "L0" else "The prior level cannot observe the disputed behavior.",
            "skipped_level_reason": None
            if level in {"L0", "L1"}
            else "Lower probes cannot supply the required runtime surface.",
            "execution_scope": None if level in {"L0", "L1"} else authorization(level).scope,
            "authorization": None if level in {"L0", "L1"} else authorization(level),
        }
    )


def lineages(level: str) -> tuple[probe_policy.ProducerLineage, ...]:
    kinds = {
        "L0": ("repo-docs", "fresh-implementer"),
        "L1": ("behavioral-stub", "behavioral-stub"),
        "L2": ("executable-prototype", "user-runtime-observation"),
        "L3": ("production-telemetry",),
    }[level]
    return tuple(
        probe_policy.ProducerLineage(
            producer_id=f"producer-{number}",
            independence_key=f"lineage-{number}",
            kind=probe_policy.ProducerKind(kind),
        )
        for number, kind in enumerate(kinds, start=1)
    )


def result(
    selected: probe_policy.ProbeDecision,
    outcome: str = "no-material-divergence",
) -> probe_policy.ProbeResult:
    material = outcome == "material-divergence"
    return probe_policy.ProbeResult.model_validate(
        {
            "result_id": f"RESULT-{selected.probe_id}",
            "decision_id": selected.probe_id,
            "intent": selected.intent,
            "level": selected.selected_level,
            "target_ledger_ids": selected.target_ledger_ids,
            "contract_digest": selected.contract_digest,
            "producer_lineages": lineages(selected.selected_level.value),
            "artifact_refs": [f"artifacts/{selected.probe_id}.json"],
            "outcome": outcome,
            "evidence_credit": 1 if material else 0,
            "completeness_credit": 0,
            "reopen_required": material,
            "gap_origin": "origin:probe" if material else None,
        }
    )


def test_level_selection_is_deterministic_from_l0_through_l3() -> None:
    # Given / When: each escalation signal is parsed into a decision.
    decisions = [decision(level) for level in ("L0", "L1", "L2", "L3")]

    # Then: the default and increasingly costly surfaces are selected exactly.
    assert [item.selected_level.value for item in decisions] == ["L0", "L1", "L2", "L3"]


def test_selected_level_cannot_disagree_with_inputs() -> None:
    # Given: L1 is claimed without sandboxable observable behavior.
    payload = decision().model_dump(mode="json") | {"selected_level": "L1"}

    # When / Then: deterministic routing rejects the claim.
    with pytest.raises(ValidationError, match="selected_level"):
        probe_policy.ProbeDecision.model_validate(payload)


def test_escalation_requires_reasons_and_authorization() -> None:
    # Given: an L2 decision with no reason or scoped authorization.
    payload = decision("L2").model_dump(mode="json")
    payload.update(
        previous_level_insufficiency=None,
        skipped_level_reason=None,
        execution_scope=None,
        authorization=None,
    )

    # When / Then: executable probing is rejected before execution.
    with pytest.raises(ValidationError, match="authorization|insufficiency"):
        probe_policy.ProbeDecision.model_validate(payload)


def test_authorization_is_bound_to_scope_targets_and_digest() -> None:
    # Given: an L3 authorization carrying a stale contract digest.
    payload = decision("L3").model_dump(mode="json")
    payload["authorization"]["contract_digest"] = "b" * 64

    # When / Then: scope binding rejects it.
    with pytest.raises(ValidationError, match="authorization"):
        probe_policy.ProbeDecision.model_validate(payload)


def test_authorization_level_and_scope_are_coherent_standalone() -> None:
    payload = authorization().model_dump(mode="json") | {
        "scope": "l3:production-telemetry"
    }

    with pytest.raises(ValidationError, match="scope"):
        probe_policy.ProbeAuthorization.model_validate(payload)


def test_production_only_l3_rejects_staged_authorization_scope() -> None:
    # Given: a production-only decision carrying only staged authority.
    payload = decision("L3").model_dump(mode="json")
    payload["execution_scope"] = "l3:staged-telemetry"
    payload["authorization"]["scope"] = "l3:staged-telemetry"

    # When / Then: staged authority cannot authorize production-only observation.
    with pytest.raises(ValidationError, match="production"):
        probe_policy.ProbeDecision.model_validate(payload)


def test_production_only_l3_rejects_staged_result_lineage() -> None:
    # Given: a production-only decision and a result from staged telemetry.
    selected = decision("L3")
    payload = result(selected).model_dump(mode="json")
    payload["producer_lineages"][0]["kind"] = "staged-telemetry"
    staged = probe_policy.ProbeResult.model_validate(payload)

    # When / Then: the bound attempt rejects the lower observation surface.
    with pytest.raises(ValidationError, match="production"):
        probe_policy.ProbeAttempt(decision=selected, result=staged)


def test_l1_requires_two_independent_behavioral_stub_producers() -> None:
    # Given: two L1 results produced by the same causal lineage.
    selected = decision("L1")
    payload = result(selected).model_dump(mode="json")
    payload["producer_lineages"][1]["independence_key"] = "lineage-1"

    # When / Then: repeated claims do not masquerade as independent stubs.
    with pytest.raises(ValidationError, match="independent"):
        probe_policy.ProbeResult.model_validate(payload)


def test_each_level_requires_its_producer_lineage_shape() -> None:
    # Given / When: valid producer sets are parsed at every level.
    results = [result(decision(level)) for level in ("L0", "L1", "L2", "L3")]

    # Then: repo/docs, dual stubs, prototype+observation, and telemetry survive.
    assert [item.level.value for item in results] == ["L0", "L1", "L2", "L3"]


def test_result_must_match_decision_digest_and_identity() -> None:
    # Given: a result with a stale digest.
    selected = decision("L0")
    stale = result(selected).model_copy(update={"contract_digest": "b" * 64})

    # When / Then: the decision/result attempt rejects stale evidence.
    with pytest.raises(ValidationError, match="digest"):
        probe_policy.ProbeAttempt(decision=selected, result=stale)


def test_no_divergence_has_zero_evidence_and_completeness_effect() -> None:
    # Given: a no-divergence result that claims evidence credit.
    payload = result(decision("L0")).model_dump(mode="json")
    payload["evidence_credit"] = 1

    # When / Then: misleading success credit is rejected.
    with pytest.raises(ValidationError, match="zero"):
        probe_policy.ProbeResult.model_validate(payload)


def test_material_divergence_reopens_with_probe_origin() -> None:
    # Given / When: a material-divergence observation is parsed.
    observed = result(decision("L2"), "material-divergence")

    # Then: it explicitly reopens the requirements model as probe-originated.
    assert observed.reopen_required is True
    assert observed.gap_origin == "origin:probe"


def test_inconclusive_is_a_valid_zero_credit_result() -> None:
    assert result(decision(), "inconclusive").outcome is probe_policy.ProbeOutcome.INCONCLUSIVE


def test_sequence_allows_one_discovery_and_one_targeted_confirmation() -> None:
    # Given: one discovery followed by one confirmation for the same target.
    discovery = decision("L0")
    confirmation = decision("L0", "targeted-confirmation")
    attempts = (
        probe_policy.ProbeAttempt(decision=discovery, result=result(discovery)),
        probe_policy.ProbeAttempt(decision=confirmation, result=result(confirmation)),
    )

    # When / Then: the bounded sequence is valid, but a second confirmation is not.
    sequence = probe_policy.ProbeSequence(attempts=attempts)
    assert len(sequence.attempts) == 2
    with pytest.raises(ValidationError):
        probe_policy.ProbeSequence(attempts=(*attempts, attempts[1]))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("discovery_probe_id", "PROBE-other", "reference"),
        ("predicate", "A different predicate.", "predicate"),
        ("target_ledger_ids", ("g8",), "target"),
        ("contract_digest", "b" * 64, "digest"),
    ],
)
def test_confirmation_binds_discovery_contract(
    field: str,
    value: str | tuple[str, ...],
    error: str,
) -> None:
    # Given: a confirmation that silently changes one discovery binding.
    discovery = decision("L0")
    confirmation = decision("L0", "targeted-confirmation").model_copy(
        update={field: value}
    )
    attempts = (
        probe_policy.ProbeAttempt(decision=discovery, result=result(discovery)),
        probe_policy.ProbeAttempt(decision=confirmation, result=result(confirmation)),
    )

    # When / Then: confirmation cannot drift from the referenced discovery.
    with pytest.raises(ValidationError, match=error):
        probe_policy.ProbeSequence(attempts=attempts)
    assert decision("L0", "targeted-confirmation").discovery_probe_id == discovery.probe_id


def test_sequence_rejects_duplicate_probe_ids() -> None:
    # Given: confirmation reuses the discovery decision identity.
    discovery = decision("L0")
    confirmation = decision("L0", "targeted-confirmation").model_copy(
        update={"probe_id": discovery.probe_id}
    )
    confirmation_result = result(confirmation).model_copy(
        update={"result_id": "RESULT-confirmation-unique"}
    )
    attempts = (
        probe_policy.ProbeAttempt(decision=discovery, result=result(discovery)),
        probe_policy.ProbeAttempt(decision=confirmation, result=confirmation_result),
    )

    # When / Then: sequence identity remains unambiguous.
    with pytest.raises(ValidationError, match="probe_id"):
        probe_policy.ProbeSequence(attempts=attempts)


def test_sequence_rejects_duplicate_result_ids() -> None:
    # Given: confirmation reuses the discovery result identity.
    discovery = decision("L0")
    confirmation = decision("L0", "targeted-confirmation")
    discovery_result = result(discovery)
    confirmation_result = result(confirmation).model_copy(
        update={"result_id": discovery_result.result_id}
    )
    attempts = (
        probe_policy.ProbeAttempt(decision=discovery, result=discovery_result),
        probe_policy.ProbeAttempt(decision=confirmation, result=confirmation_result),
    )

    # When / Then: sequence result identity remains unambiguous.
    with pytest.raises(ValidationError, match="result_id"):
        probe_policy.ProbeSequence(attempts=attempts)


def test_unknown_fields_fail_closed() -> None:
    # Given: a valid result carrying an undeclared success marker.
    payload = result(decision()).model_dump(mode="json") | {"passed": True}

    # When / Then: strict boundary parsing rejects it.
    with pytest.raises(ValidationError):
        probe_policy.ProbeResult.model_validate(payload)


@pytest.mark.parametrize(("field", "value"), [("sandboxable_observable", "false"), ("requires_runtime_observation", "true"), ("production_only", "false")])
def test_decision_boolean_scalars_reject_coercion(field: str, value: str | int) -> None:
    payload = decision().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        probe_policy.ProbeDecision.model_validate(payload)


@pytest.mark.parametrize(("field", "value"), [("evidence_credit", "0"), ("completeness_credit", "0"), ("reopen_required", "false")])
def test_result_scalar_effects_reject_coercion(field: str, value: str | bool | int) -> None:
    payload = result(decision()).model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError):
        probe_policy.ProbeResult.model_validate(payload)


@pytest.mark.parametrize(
    ("sandboxable", "runtime", "production"),
    [("false", False, False), (True, True, False), (False, True, True)],
)
def test_selector_rejects_coercive_or_contradictory_signals(
    sandboxable: bool | str,
    runtime: bool,
    production: bool,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        probe_policy.select_probe_level(
            sandboxable_observable=sandboxable,
            requires_runtime_observation=runtime,
            production_only=production,
        )


def test_nested_result_instances_are_revalidated() -> None:
    selected = decision()
    tainted = result(selected).model_copy(update={"reopen_required": 0})

    with pytest.raises(ValidationError):
        probe_policy.ProbeAttempt(decision=selected, result=tainted)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
