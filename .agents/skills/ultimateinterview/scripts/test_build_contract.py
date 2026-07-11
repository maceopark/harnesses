#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_contract
from scripts.build_contract_schema import BuildContract, Verification

UNSAFE_SAFE_AUTO_COMMANDS = (
    "git reset --hard",
    "git checkout -- .",
    "pytest --reruns 5",
    "python3 -m pytest --count 10",
    "tail -f app.log",
    "python3 -m http.server",
    "curl https://example.test/health",
    "TOKEN=secret python3 verify.py",
)


def handoff(*, command: str = "python3 -m pytest", run_policy: str = "safe-auto") -> str:
    return f"""# Spec: Minimal

# Part 1 - Build Contract

## Goal
Ship deterministic behavior. (source: g1)

## Target Surface
| File / module | Expected change |
| --- | --- |
| app.py | Add behavior |

## Behavior Contract
| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 | Save a value | When invoked, the app shall persist it. | g1 |

## Change Impact & Preservation
| Source | Current evidence / behavior | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |
| --- | --- | --- | --- | --- | --- | --- |
| g1 | Value is absent | Existing values survive | Value is saved | app.py | REQ-001 | saved row |

## Quality Bars
| Attribute | Bar (a number an implementer can verify) | Weight | Verification |
| --- | --- | --- | --- |
| latency | under 100 ms | 2 | VER-001 |

## Decision Boundaries
Decision log: `.ultimateinterview/minimal/decisions.jsonl`
Probe decision: L0 - static contract is sufficient.
| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| naming | yes | Preserve public API |

## Out Of Scope / Non-Goals
- No remote service - negative: dependency remains absent.

## Implementation Constraints
- Interfaces: CLI
- Compatibility: Existing data
- Migration: None
- Decision core: Parsed input to result
- Effects boundary: Atomic file write

## Rollout & Recovery
| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |
| --- | --- | --- | --- | --- | --- |
| release | none | failing test | revert | failures for 1 day | maintainer |

## Guardrail Compile
| Risk | Class | Predicate / residual / substrate owner | Evidence |
| --- | --- | --- | --- |
| regression | Stop-time predicate | test exit status | VER-001 |

## Verification Commands
| ID | Covers | Check | Kind | Command / action | Pass condition | Run policy |
| --- | --- | --- | --- | --- | --- | --- |
| VER-001 | REQ-001 | focused suite | test | {command} | exit code = 0; output reports 1 passed | {run_policy} |
| VER-002 | REQ-001 | installed surface | real-surface | python3 app.py --check | output contains saved row | manual |

## Deferred Risks
| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| scale | maintainer | 2026-08-01 | Revisit after metrics |

## Fresh-Implementer Test
| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? | Unresolved after disposition |
| --- | --- | --- | --- | --- |
| reviewer-1 | none | none | no fold-back required | none |

# Part 2 - Audit Trail
ignored
"""


def test_compile_complete_part1_when_source_is_valid() -> None:
    # Given a complete Part 1 authored in Markdown
    source = handoff()

    # When it is compiled
    contract = build_contract.compile_handoff(source)

    # Then all sections and coverage bindings survive in the typed ABI
    assert contract.schema_version == 1
    assert contract.goal == "Ship deterministic behavior. (source: g1)"
    assert contract.requirements[0].id == "REQ-001"
    assert contract.verifications[0].requirement_ids == ("REQ-001",)
    assert contract.decision_log_path == ".ultimateinterview/minimal/decisions.jsonl"
    assert contract.probe_decision.startswith("L0")
    assert build_contract.is_current(contract, source)


def test_canonical_output_is_byte_stable_when_compiled_twice() -> None:
    # Given identical Markdown inputs
    source = handoff()

    # When each is compiled and rendered
    first = build_contract.canonical_json(build_contract.compile_handoff(source))
    second = build_contract.canonical_json(build_contract.compile_handoff(source))

    # Then canonical JSON and the self-excluding digest are identical
    assert first == second
    assert json.loads(first)["contract_digest"] == json.loads(second)["contract_digest"]


def test_canonical_output_round_trips_without_projection_loss() -> None:
    # Given a compiled contract
    contract = build_contract.compile_handoff(handoff())

    # When canonical JSON is parsed through the public schema
    parsed = BuildContract.model_validate_json(build_contract.canonical_json(contract))

    # Then every typed field projects identically
    assert parsed == contract


def test_current_check_fails_when_part1_changes_one_character() -> None:
    # Given a compiled contract
    source = handoff()
    contract = build_contract.compile_handoff(source)

    # When one source character changes
    changed = source.replace("Ship deterministic", "ship deterministic", 1)

    # Then stale state is detected
    assert not build_contract.is_current(contract, changed)


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("VER-002", "VER-001", "duplicate verification id"),
        ("REQ-001 | focused", "REQ-999 | focused", "unknown requirement id"),
        ("| VER-002 | REQ-001 | installed", "| VER-002 | REQ-999 | installed", "unknown requirement id"),
        ("| VER-002 | REQ-001 |", "| VER-002 | REQ-002 |", "unknown requirement id"),
    ],
)
def test_compile_fails_closed_when_ids_are_invalid(
    needle: str,
    replacement: str,
    message: str,
) -> None:
    # Given malformed cross-references
    source = handoff().replace(needle, replacement, 1)

    # When compilation parses the contract, Then it fails closed
    with pytest.raises(ValidationError, match=message):
        build_contract.compile_handoff(source)


def test_compile_requires_test_and_real_surface_verification() -> None:
    # Given a contract with its real-surface row removed
    source = handoff().replace(
        "| VER-002 | REQ-001 | installed surface | real-surface | python3 app.py --check | output contains saved row | manual |\n",
        "",
    )

    # When compiled, Then the coverage floor rejects it
    with pytest.raises((build_contract.BuildContractCompileError, ValidationError), match="real-surface"):
        build_contract.compile_handoff(source)


def test_compile_preserves_reasoned_none_applicable_sections() -> None:
    # Given valid Part 1 sections whose grammar permits a reasoned empty case
    source = handoff()
    source = source.replace(
        "| Attribute | Bar (a number an implementer can verify) | Weight | Verification |\n| --- | --- | --- | --- |\n| latency | under 100 ms | 2 | VER-001 |",
        "No measurable quality bar applies - local deterministic fixture.",
    ).replace(
        "| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |\n| --- | --- | --- | --- | --- | --- |\n| release | none | failing test | revert | failures for 1 day | maintainer |",
        "N/A - local fixture has no release boundary.",
    ).replace(
        "| Risk | Class | Predicate / residual / substrate owner | Evidence |\n| --- | --- | --- | --- |\n| regression | Stop-time predicate | test exit status | VER-001 |",
        "No stop-time or pre-action guardrail applies - tests are read-only.",
    ).replace(
        "| Risk | Owner | Decision date | Mitigation |\n| --- | --- | --- | --- |\n| scale | maintainer | 2026-08-01 | Revisit after metrics |",
        "No deferred risks - no accepted ambiguity remains.",
    )

    # When compiled, Then the typed mirror keeps reasons and no invented rows
    contract = build_contract.compile_handoff(source)
    assert contract.quality_bars_none_reason == "local deterministic fixture."
    assert contract.rollout_na_reason == "local fixture has no release boundary."
    assert contract.guardrails_none_reason == "tests are read-only."
    assert contract.deferred_risks == ()
    assert contract.deferred_risks_none_reason == "no accepted ambiguity remains."


def test_compile_rejects_uncovered_requirement() -> None:
    # Given a second requirement with no verification binding
    row = "| REQ-002 | Delete a value | When invoked, the app shall delete it. | g2 |\n"
    source = handoff().replace(
        "| REQ-001 | Save a value | When invoked, the app shall persist it. | g1 |\n",
        "| REQ-001 | Save a value | When invoked, the app shall persist it. | g1 |\n" + row,
    )

    # When compiled, Then every REQ must have a VER
    with pytest.raises(ValidationError, match="lacks verification coverage"):
        build_contract.compile_handoff(source)


def test_compile_rejects_dangling_verification_reference() -> None:
    # Given a section citing a nonexistent verification
    source = handoff().replace("| latency | under 100 ms | 2 | VER-001 |", "| latency | under 100 ms | 2 | VER-999 |")

    # When compiled, Then VER references are closed over known IDs
    with pytest.raises(ValidationError, match="unknown verification id"):
        build_contract.compile_handoff(source)


@pytest.mark.parametrize(
    "command",
    UNSAFE_SAFE_AUTO_COMMANDS,
)
def test_safe_auto_rejects_destructive_flaky_or_hanging_commands(command: str) -> None:
    # Given unsafe work mislabeled as automatically safe
    source = handoff(command=command)

    # When compiled, Then policy validation rejects the misleading label
    with pytest.raises(
        (build_contract.BuildContractCompileError, ValidationError),
        match="safe-auto|executable command evidence",
    ):
        build_contract.compile_handoff(source)


@pytest.mark.parametrize("command", UNSAFE_SAFE_AUTO_COMMANDS)
def test_typed_run_policy_rejects_unsafe_safe_auto(command: str) -> None:
    # Given a schema payload that bypasses Markdown compilation
    payload = {
        "id": "VER-001", "requirement_ids": ["REQ-001"], "check": "check",
        "kind": "test", "command_action": command,
        "pass_condition": "one named assertion passes", "run_policy": "safe-auto",
    }

    # When parsed directly, Then the typed policy still rejects unsafe automation
    with pytest.raises(ValidationError, match="safe-auto"):
        Verification.model_validate(payload)


def test_schema_rejects_unknown_fields_and_invalid_run_policy() -> None:
    # Given a valid compiled payload with boundary corruption
    payload = build_contract.compile_handoff(handoff()).model_dump(mode="json")
    payload["unknown"] = True
    payload["verifications"][0]["run_policy"] = "sometimes"

    # When parsed, Then strict schema validation rejects it
    with pytest.raises(ValidationError):
        BuildContract.model_validate(payload)


def test_schema_rejects_tampered_contract_digest() -> None:
    # Given a canonical payload whose self-digest was altered
    payload = build_contract.compile_handoff(handoff()).model_dump(mode="json")
    payload["contract_digest"] = "0" * 64

    # When parsed, Then the self-excluding digest is verified
    with pytest.raises(ValidationError, match="canonical self-excluding"):
        BuildContract.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("run_policy", ["expensive", "destructive", "credentialed", "manual"])
def test_nonautomatic_run_policies_round_trip(run_policy: str) -> None:
    # Given explicitly classified nonautomatic work
    source = handoff(command="python3 -m pytest", run_policy=run_policy)

    # When compiled, Then the closed policy vocabulary is preserved
    assert build_contract.compile_handoff(source).verifications[0].run_policy == run_policy


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("| naming | yes |", "| naming | maybe |", "must be yes or no"),
        ("exit code = 0; output reports 1 passed", "process returns zero", "observable"),
        ("exit code = 0; output reports 1 passed", "command succeeds", "observable"),
        ("2026-08-01", "2026-99-99", "decision_date"),
    ],
)
def test_malformed_or_misleading_contract_input_fails_closed(
    needle: str,
    replacement: str,
    message: str,
) -> None:
    # Given malformed authored state
    source = handoff().replace(needle, replacement, 1)

    # When compiled, Then the boundary reports the contract defect
    with pytest.raises((build_contract.BuildContractCompileError, ValidationError), match=message):
        build_contract.compile_handoff(source)


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("under 100 ms", "fast enough", "measurable"),
        ("under 100 ms | 2", "under 100 ms | 4", "Quality Bars"),
        ("no fold-back required | none", "no fold-back required | one open ask", "unresolved"),
        (
            "| scale | maintainer | 2026-08-01 | Revisit after metrics |",
            "Risk accepted informally.",
            "Deferred Risks",
        ),
        (
            "python3 app.py --check | output contains saved row | manual",
            "inspect installed behavior manually | operator says it worked | manual",
            "executable command evidence",
        ),
    ],
)
def test_plan_breaking_section_semantics_fail_closed(
    needle: str,
    replacement: str,
    message: str,
) -> None:
    # Given a structurally present but semantically weak Part 1 section
    source = handoff().replace(needle, replacement, 1)

    # When compiled, Then shared gate semantics reject the bypass
    with pytest.raises((build_contract.BuildContractCompileError, ValidationError), match=message):
        build_contract.compile_handoff(source)


def test_cli_atomically_replaces_output(tmp_path: Path) -> None:
    # Given an input handoff and a pre-existing output
    source = tmp_path / "handoff.md"
    output = tmp_path / "build-contract.json"
    source.write_text(handoff(), encoding="utf-8")
    output.write_text("old\n", encoding="utf-8")

    # When the real CLI exports the contract
    result = subprocess.run(
        [sys.executable, str(Path(build_contract.__file__)), str(source), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Then a complete canonical document replaces the old generation
    assert result.returncode == 0, result.stderr
    assert BuildContract.model_validate_json(output.read_text(encoding="utf-8"))
    assert not tuple(tmp_path.glob(".build-contract.json.*"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
