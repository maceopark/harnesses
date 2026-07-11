#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "typer>=0.12"]
# ///

# ─── How to run ───
# uv run --python 3.14 --with 'pydantic>=2.7' --with 'pytest>=8.0' --with 'typer>=0.12' pytest -q scripts/test_output_template_consumer_contract.py

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts import build_contract, implementation_gate, protocol_state


SKILL_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_TEMPLATE = SKILL_ROOT / "references" / "output-template.md"
V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready" / "handoff.md"
V2_PROTOCOL = V2_READY.with_name("protocol.json")
CONSUMER_SECTION = re.compile(
    r"^## Consumer Verification\n.*?(?=^## Deferred Risks\n)",
    re.MULTILINE | re.DOTALL,
)
CANONICAL_HEADERS = (
    "| Grant kind | Receipt kind | Required ID | Target | Environment / scope | "
    "Outcome | Expected exit | Run policy | Auto execute |"
)


def consumer_section(markdown: str) -> str:
    match = CONSUMER_SECTION.search(markdown)
    assert match is not None, "missing Consumer Verification table"
    return match.group(0)


def handoff_with_template_consumer_section() -> str:
    template_section = consumer_section(OUTPUT_TEMPLATE.read_text(encoding="utf-8"))
    fixture = V2_READY.read_text(encoding="utf-8")
    rendered, replacements = CONSUMER_SECTION.subn(template_section, fixture, count=1)
    assert replacements == 1
    return rendered


def template_protocol(contract_digest: str) -> protocol_state.ProtocolState:
    protocol = protocol_state.parse_state(V2_PROTOCOL.read_text(encoding="utf-8"))
    decision = protocol.probe_decision
    assert decision is not None
    return protocol.model_copy(
        update={
            "probe_decision": decision.model_copy(
                update={
                    "probe_id": "PROBE-L0-template",
                    "contract_digest": contract_digest,
                },
            ),
        },
    )


def test_output_template_consumer_section_compiles_and_binds_a_v2_gate() -> None:
    # Given the output template's unmodified Consumer Verification section
    handoff = handoff_with_template_consumer_section()

    # When it is rendered into an otherwise complete v2 handoff and compiled
    contract = build_contract.compile_handoff(handoff)

    # Then the compiler and consumer gate accept its canonical contract shape
    assert CANONICAL_HEADERS in consumer_section(handoff)
    assert implementation_gate.v2_consumer_verification_failures(handoff) == ()
    assert implementation_gate.v2_consumer_binding_failures(
        template_protocol(contract.contract_digest),
        contract,
    ) == ()


@pytest.mark.parametrize(
    ("replacement", "gate_failure"),
    (
        ("", "BuildContract v2 requires Consumer Verification"),
        (
            "## Consumer Verification\n\n"
            "| Grant category | Receipt kind | Required ID | Target | Environment / scope | "
            "Outcome | Expected exit | Run policy | Auto execute |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| implementation-readiness | verification | VER-001 | REQ-001 | local | success | 0 | safe-auto | yes |\n\n",
            "Consumer Verification headers must be the exact canonical ordered set",
        ),
    ),
)
def test_output_template_consumer_section_rejects_missing_or_malformed_rows(
    replacement: str,
    gate_failure: str,
) -> None:
    # Given a completed v2 handoff built from the template section
    handoff = handoff_with_template_consumer_section()
    malformed, replacements = CONSUMER_SECTION.subn(replacement, handoff, count=1)
    assert replacements == 1

    # When the required section is removed or its canonical header is changed
    # Then both compiler and gate fail closed with the matching contract error
    with pytest.raises(build_contract.BuildContractCompileError, match="Consumer Verification"):
        build_contract.compile_handoff(malformed)
    assert implementation_gate.v2_consumer_verification_failures(malformed) == (gate_failure,)
