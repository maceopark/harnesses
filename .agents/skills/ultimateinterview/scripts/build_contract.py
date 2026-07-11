#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

# ─── How to run ───
# uv run build_contract.py handoff.md --output build-contract.json
# ──────────────────

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Annotated, Final, Literal, Protocol, runtime_checkable

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import (  # noqa: E402
    ambiguity_ledger,
    atomic_write,
    handoff_coverage,
    protocol_state,
    verification_lint,
)
from scripts.build_contract_schema import (  # noqa: E402
    BuildContract,
    ContractBody,
    DecisionBoundary,
    DeferredRisk,
    FreshReviewEvidence,
    Guardrail,
    ImpactTrace,
    ImplementationConstraints,
    QualityBar,
    Requirement,
    RolloutRecovery,
    RunPolicy,
    TargetSurface,
    Verification,
    VerificationKind,
    body_digest,
)

DECISION_LOG: Final[re.Pattern[str]] = re.compile(
    r"`?(\.ultimateinterview/[^/\s`]+/decisions\.jsonl)`?",
)
PROBE_DECISION: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?Probe decision:\s*(\S[^\n]*)$",
)
LABEL: Final[re.Pattern[str]] = re.compile(r"(?im)^\s*[-*]\s*([^:]+):\s*(\S[^\n]*)$")
SOURCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"\s*(?:,|;)\s*|\s+")
QUALITY_WEIGHTS: Final[Mapping[int, Literal[1, 2, 3, 5]]] = {1: 1, 2: 2, 3: 3, 5: 5}
app = typer.Typer(add_completion=False, no_args_is_help=True)


class BuildContractCompileError(Exception):
    def __init__(self, section: str, detail: str) -> None:
        super().__init__(section, detail)
        self.section = section
        self.detail = detail

    def __str__(self) -> str:
        return f"cannot compile {self.section}: {self.detail}"


class _GateResult(Protocol):
    @property
    def failures(self) -> tuple[str, ...]: ...


@runtime_checkable
class _ImplementationGate(Protocol):
    REQUIRED_SECTIONS: tuple[str, ...]

    def complete_table_records(self, body: str, required_headers: frozenset[str]) -> tuple[Mapping[str, str], ...]: ...

    def section_body(self, part1: str, name: str) -> str: ...
    def has_reasoned_line(self, body: str, prefix: str) -> bool: ...
    def contains_unresolved_placeholder(self, part1: str) -> bool: ...
    def contract_digest(self, handoff_text: str) -> str: ...
    def evaluate(self, entries: tuple[ambiguity_ledger.LedgerEntry, ...], ledger_summary: ambiguity_ledger.AmbiguitySummary, protocol_summary: protocol_state.ProtocolSummary, handoff_text: str) -> _GateResult: ...


def _load_implementation_gate() -> _ImplementationGate:
    module = import_module("scripts.implementation_gate")
    if not isinstance(module, _ImplementationGate):
        raise BuildContractCompileError("Build Contract", "implementation gate contract is unavailable")
    return module


implementation_gate = _load_implementation_gate()


def _records(body: str, headers: frozenset[str], section: str) -> tuple[Mapping[str, str], ...]:
    records = implementation_gate.complete_table_records(body, headers)
    if not records:
        raise BuildContractCompileError(section, "missing or incomplete required table")
    return records


def _source_ids(cell: str) -> tuple[str, ...]:
    return tuple(item for item in SOURCE_SPLIT.split(cell.strip()) if item)


def _yes_no(cell: str) -> bool:
    normalized = cell.strip().lower()
    if normalized not in {"yes", "no"}:
        raise BuildContractCompileError("Decision Boundaries", "Agent may decide? must be yes or no")
    return normalized == "yes"


def _quality_weight(cell: str) -> Literal[1, 2, 3, 5]:
    try:
        parsed = int(cell)
        return QUALITY_WEIGHTS[parsed]
    except (KeyError, ValueError) as error:
        raise BuildContractCompileError("Quality Bars", "weight must be 1, 2, 3, or 5") from error


def _section(part1: str, name: str) -> str:
    body = implementation_gate.section_body(part1, name)
    if not body:
        raise BuildContractCompileError(name, "section is missing or empty")
    return body


def _behavior(body: str) -> tuple[Requirement, ...]:
    acceptance = "acceptance criterion (ears or given/when/then)"
    records = _records(body, frozenset({"id", "requirement", acceptance, "source"}), "Behavior Contract")
    return tuple(
        Requirement(
            id=row["id"],
            requirement=row["requirement"],
            acceptance_criterion=row[acceptance],
            source_ids=_source_ids(row["source"]),
        )
        for row in records
    )


def _constraints(body: str) -> ImplementationConstraints:
    labels = {match.group(1).strip().lower(): match.group(2).strip() for match in LABEL.finditer(body)}
    required = ("interfaces", "compatibility", "migration", "decision core", "effects boundary")
    if missing := tuple(key for key in required if key not in labels):
        raise BuildContractCompileError("Implementation Constraints", f"missing labels: {', '.join(missing)}")
    return ImplementationConstraints(
        interfaces=labels["interfaces"],
        compatibility=labels["compatibility"],
        migration=labels["migration"],
        decision_core=labels["decision core"],
        effects_boundary=labels["effects boundary"],
    )


def _reasoned_none(body: str, prefix: str) -> str | None:
    if implementation_gate.has_reasoned_line(body, prefix):
        return body.strip().removeprefix(prefix).strip()
    return None


def _shared_gate(handoff_text: str) -> None:
    ledger_summary = ambiguity_ledger.AmbiguitySummary(
        active_count=0, deferred_count=0, residual=0, denominator=0,
        ambiguity_percent=0.0, display_percent="0.0%", handoff_ready=True,
        blockers=(), triangulation_violations=(), triangulation_warnings=(),
        contested=(), top_drivers=(),
    )
    protocol_summary = protocol_state.ProtocolSummary(
        depth=protocol_state.Depth.MINIMAL,
        interactions_used=0, question_budget=0, interview_obligations=(),
        handoff_blockers=(), protocol_ready=True,
    )
    result = implementation_gate.evaluate((), ledger_summary, protocol_summary, handoff_text)
    if result.failures:
        raise BuildContractCompileError("Build Contract", result.failures[0])


def compile_handoff(handoff_text: str) -> BuildContract:
    """Compile authoritative Part 1 Markdown into the strict BuildContract v1 ABI."""
    raw_part1 = handoff_coverage.extract_part1(handoff_text)
    part1 = verification_lint.strip_fenced_blocks(raw_part1)
    if implementation_gate.contains_unresolved_placeholder(raw_part1):
        raise BuildContractCompileError("Build Contract", "unresolved placeholder")
    _shared_gate(handoff_text)
    for section_name in implementation_gate.REQUIRED_SECTIONS:
        _section(part1, section_name)

    target = _records(
        _section(part1, "Target Surface"),
        frozenset({"file / module", "expected change"}),
        "Target Surface",
    )
    impact_headers = frozenset(
        {"source", "current evidence / behavior", "preserved invariant", "target difference", "code surface", "acceptance check", "runtime signal"},
    )
    impacts = _records(_section(part1, "Change Impact & Preservation"), impact_headers, "Change Impact & Preservation")
    quality_body = _section(part1, "Quality Bars")
    quality_headers = frozenset(
        {"attribute", "bar (a number an implementer can verify)", "weight", "verification"},
    )
    quality_records = implementation_gate.complete_table_records(quality_body, quality_headers)
    quality_none = _reasoned_none(quality_body, "No measurable quality bar applies -")
    if not quality_records and quality_none is None:
        raise BuildContractCompileError("Quality Bars", "needs measurable rows or an exact reasoned none line")
    decision_body = _section(part1, "Decision Boundaries")
    decisions = _records(
        decision_body,
        frozenset({"decision", "agent may decide?", "boundary"}),
        "Decision Boundaries",
    )
    log_match = DECISION_LOG.search(decision_body)
    probe_match = PROBE_DECISION.search(decision_body)
    if log_match is None or probe_match is None:
        raise BuildContractCompileError("Decision Boundaries", "decision log path and probe decision are required")

    rollout_body = _section(part1, "Rollout & Recovery")
    rollout_headers = frozenset(
        {"activation", "compatibility / backfill", "rollback trigger", "rollback action", "observation metric + window", "owner"},
    )
    rollout_records = implementation_gate.complete_table_records(rollout_body, rollout_headers)
    rollout_none = _reasoned_none(rollout_body, "N/A -")
    if not rollout_records and rollout_none is None:
        raise BuildContractCompileError("Rollout & Recovery", "needs complete rows or an exact N/A reason")
    guardrail_body = _section(part1, "Guardrail Compile")
    guardrail_headers = frozenset({"risk", "class", "predicate / residual / substrate owner", "evidence"})
    guardrail_records = implementation_gate.complete_table_records(guardrail_body, guardrail_headers)
    guardrail_none = _reasoned_none(guardrail_body, "No stop-time or pre-action guardrail applies -")
    if not guardrail_records and guardrail_none is None:
        raise BuildContractCompileError("Guardrail Compile", "needs complete rows or an exact reasoned none line")
    verification_headers = frozenset(
        {"id", "covers", "check", "kind", "command / action", "pass condition", "run policy"},
    )
    verification_records = _records(
        _section(part1, "Verification Commands"), verification_headers, "Verification Commands",
    )
    deferred_headers = frozenset({"risk", "owner", "decision date", "mitigation"})
    deferred_body = _section(part1, "Deferred Risks")
    deferred_records = implementation_gate.complete_table_records(deferred_body, deferred_headers)
    deferred_none = _reasoned_none(deferred_body, "No deferred risks -")
    if not deferred_records and deferred_none is None:
        raise BuildContractCompileError("Deferred Risks", "needs complete rows or an exact reasoned none line")
    fresh_headers = frozenset(
        {"reviewer (fresh-context agent / self-audit)", '"would have to ask" items found', "gameable criteria found", "folded back / re-bound?", "unresolved after disposition"},
    )
    fresh_records = _records(_section(part1, "Fresh-Implementer Test"), fresh_headers, "Fresh-Implementer Test")
    non_goals = tuple(
        line.removeprefix("-").strip()
        for line in _section(part1, "Out Of Scope / Non-Goals").splitlines()
        if line.lstrip().startswith("-") and line.removeprefix("-").strip()
    )

    body = ContractBody(
        goal=_section(part1, "Goal"),
        target_surface=tuple(TargetSurface(file_module=row["file / module"], expected_change=row["expected change"]) for row in target),
        requirements=_behavior(_section(part1, "Behavior Contract")),
        change_impact_preservation=tuple(
            ImpactTrace(source_ids=_source_ids(row["source"]), current_evidence_behavior=row["current evidence / behavior"], preserved_invariant=row["preserved invariant"], target_difference=row["target difference"], code_surface=row["code surface"], acceptance_check=row["acceptance check"], runtime_signal=row["runtime signal"])
            for row in impacts
        ),
        quality_bars=tuple(QualityBar(attribute=row["attribute"], measurable_bar=row["bar (a number an implementer can verify)"], weight=_quality_weight(row["weight"]), verification=row["verification"]) for row in quality_records),
        quality_bars_none_reason=quality_none,
        decision_boundaries=tuple(DecisionBoundary(decision=row["decision"], agent_may_decide=_yes_no(row["agent may decide?"]), boundary=row["boundary"]) for row in decisions),
        decision_log_path=log_match.group(1),
        probe_decision=probe_match.group(1),
        out_of_scope=non_goals,
        implementation_constraints=_constraints(_section(part1, "Implementation Constraints")),
        rollout_recovery=tuple(RolloutRecovery(activation=row["activation"], compatibility_backfill=row["compatibility / backfill"], rollback_trigger=row["rollback trigger"], rollback_action=row["rollback action"], observation_metric_window=row["observation metric + window"], owner=row["owner"]) for row in rollout_records),
        rollout_na_reason=rollout_none,
        guardrails=tuple(Guardrail(risk=row["risk"], risk_class=row["class"], predicate_residual_owner=row["predicate / residual / substrate owner"], evidence=row["evidence"]) for row in guardrail_records),
        guardrails_none_reason=guardrail_none,
        verifications=tuple(Verification(id=row["id"], requirement_ids=_source_ids(row["covers"]), check=row["check"], kind=VerificationKind(row["kind"]), command_action=row["command / action"], pass_condition=row["pass condition"], run_policy=RunPolicy(row["run policy"])) for row in verification_records),
        deferred_risks=tuple(DeferredRisk(risk=row["risk"], owner=row["owner"], decision_date=row["decision date"], mitigation=row["mitigation"]) for row in deferred_records),
        deferred_risks_none_reason=deferred_none,
        fresh_review_evidence=tuple(FreshReviewEvidence(reviewer=row["reviewer (fresh-context agent / self-audit)"], ask_items_found=row['"would have to ask" items found'], gameable_criteria_found=row["gameable criteria found"], disposition=row["folded back / re-bound?"], unresolved_after_disposition=row["unresolved after disposition"]) for row in fresh_records),
        source_part1_sha256=implementation_gate.contract_digest(handoff_text),
    )
    return BuildContract.model_validate({**body.model_dump(), "contract_digest": body_digest(body)})


def is_current(contract: BuildContract, handoff_text: str) -> bool:
    return contract.source_part1_sha256 == implementation_gate.contract_digest(handoff_text)


def canonical_json(contract: BuildContract) -> str:
    return json.dumps(contract.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@app.command()
def main(
    handoff: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    contract = compile_handoff(handoff.read_text(encoding="utf-8"))
    atomic_write.commit_text_files({output: canonical_json(contract)})
    typer.echo(contract.contract_digest)


if __name__ == "__main__":
    app()
