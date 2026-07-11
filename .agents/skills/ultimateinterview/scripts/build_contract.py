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
from pathlib import Path
from typing import Annotated, Final, Literal

import typer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import (  # noqa: E402
    ambiguity_ledger,
    atomic_write,
    behavior_atoms,
    handoff_coverage,
    implementation_gate,  # pyright: ignore[reportImportCycles] -- gate recompiles contracts only after this module loads.
    protocol_state,
    verification_lint,
)
from scripts.build_contract_schema import (  # noqa: E402
    BuildContract,
    BehaviorAtomBinding,
    ConsumerGrantKind,
    ConsumerOutcome,
    ConsumerReceiptKind,
    CONSUMER_VERIFICATION_HEADERS,
    ConsumerVerification,
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
    canonical_body_payload,
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


def _v2_behavior_records(body: str) -> tuple[Mapping[str, str], ...] | None:
    acceptance = "acceptance criterion (ears or given/when/then)"
    headers = ("id", "requirement", acceptance, "source", "assurance class", "atom ids")
    for table_headers, rows in verification_lint.tables(body):
        normalized = tuple(header.lower() for header in table_headers)
        if normalized != headers:
            if "assurance class" in normalized or "atom ids" in normalized:
                raise BuildContractCompileError(
                    "Behavior Contract",
                    "v2 behavior atom headers must use the canonical order",
                )
            continue
        records: list[Mapping[str, str]] = []
        for row in rows:
            if len(row) != len(headers):
                raise BuildContractCompileError("Behavior Contract", "v2 behavior atom row has wrong column count")
            record = dict(zip(headers, row, strict=True))
            if any(not record[header] for header in headers[:-1]):
                raise BuildContractCompileError("Behavior Contract", "v2 behavior atom row has an empty required field")
            records.append(record)
        if not records:
            raise BuildContractCompileError("Behavior Contract", "v2 behavior atom table needs one requirement")
        return tuple(records)
    return None


def _v2_atom_bindings(body: str, *, required: bool) -> tuple[BehaviorAtomBinding, ...]:
    headers = (
        "source",
        "assurance class",
        "atom id",
        "condition",
        "polarity",
        "observable response",
        "boundary context",
        "temporal context",
        "coercion context",
    )
    for table_headers, rows in verification_lint.tables(body):
        normalized = tuple(header.lower() for header in table_headers)
        if normalized != headers:
            continue
        bindings: list[BehaviorAtomBinding] = []
        for row in rows:
            if len(row) != len(headers):
                raise BuildContractCompileError("Behavior Atoms", "atom row has wrong column count")
            record = dict(zip(headers, row, strict=True))
            if any(not record[header] for header in headers[:6]):
                raise BuildContractCompileError("Behavior Atoms", "atom row needs source, id, condition, polarity, and observable response")
            atom = behavior_atoms.BehaviorAtom(
                id=record["atom id"],
                condition=record["condition"],
                polarity=behavior_atoms.AtomPolarity(record["polarity"]),
                observable_response=record["observable response"],
                boundary_context=record["boundary context"] or None,
                temporal_context=record["temporal context"] or None,
                coercion_context=record["coercion context"] or None,
            )
            bindings.append(
                BehaviorAtomBinding(
                    source_id=record["source"],
                    assurance_class=behavior_atoms.AssuranceClass(record["assurance class"]),
                    atom=atom,
                    atom_digest=behavior_atoms.atom_digest(atom),
                ),
            )
        if not bindings:
            raise BuildContractCompileError("Behavior Atoms", "v2 needs an atom catalog")
        return tuple(bindings)
    if required:
        raise BuildContractCompileError("Behavior Atoms", "v2 requires an explicit behavior atom catalog")
    return ()


def _behavior(body: str) -> tuple[int, tuple[Requirement, ...], tuple[BehaviorAtomBinding, ...]]:
    acceptance = "acceptance criterion (ears or given/when/then)"
    v2_records = _v2_behavior_records(body)
    if v2_records is not None:
        requirements = tuple(
            Requirement(
                id=row["id"],
                requirement=row["requirement"],
                acceptance_criterion=row[acceptance],
                source_ids=_source_ids(row["source"]),
                assurance_class=behavior_atoms.AssuranceClass(row["assurance class"]),
                atom_ids=_source_ids(row["atom ids"]),
            )
            for row in v2_records
        )
        return 2, requirements, _v2_atom_bindings(
            body,
            required=any(requirement.atom_ids for requirement in requirements),
        )
    records = _records(body, frozenset({"id", "requirement", acceptance, "source"}), "Behavior Contract")
    requirements = tuple(
        Requirement(
            id=row["id"],
            requirement=row["requirement"],
            acceptance_criterion=row[acceptance],
            source_ids=_source_ids(row["source"]),
        )
        for row in records
    )
    return 1, requirements, ()


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


def _consumer_verifications(body: str) -> tuple[ConsumerVerification, ...]:
    consumer_headers = frozenset(CONSUMER_VERIFICATION_HEADERS)
    records: tuple[Mapping[str, str], ...] | None = None
    for table_headers, rows in verification_lint.tables(body):
        normalized = tuple(header.lower() for header in table_headers)
        if not (consumer_headers & frozenset(normalized)):
            continue
        if normalized != CONSUMER_VERIFICATION_HEADERS:
            raise BuildContractCompileError(
                "Consumer Verification",
                "headers must be the exact canonical ordered set",
            )
        if any(
            len(row) != len(CONSUMER_VERIFICATION_HEADERS)
            or any(not cell.strip() for cell in row)
            for row in rows
        ):
            raise BuildContractCompileError(
                "Consumer Verification",
                "row has the wrong column count or an empty required value",
            )
        records = tuple(
            dict(zip(CONSUMER_VERIFICATION_HEADERS, row, strict=True))
            for row in rows
        )
        break
    if not records:
        raise BuildContractCompileError("Consumer Verification", "missing or incomplete required table")
    return tuple(
        ConsumerVerification(
            grant_kind=ConsumerGrantKind(row["grant kind"]),
            receipt_kind=ConsumerReceiptKind(row["receipt kind"]),
            required_id=row["required id"],
            target_ids=_source_ids(row["target"]),
            environment_scope=row["environment / scope"],
            outcome=ConsumerOutcome(row["outcome"]),
            expected_exit=int(row["expected exit"]),
            run_policy=RunPolicy(row["run policy"]),
            auto_execute=_yes_no(row["auto execute"]),
        )
        for row in records
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

    schema_version, requirements, atom_bindings = _behavior(_section(part1, "Behavior Contract"))
    consumer_verifications = (
        ()
        if schema_version == 1
        else _consumer_verifications(_section(part1, "Consumer Verification"))
    )
    body = ContractBody(
        schema_version=schema_version,
        goal=_section(part1, "Goal"),
        target_surface=tuple(TargetSurface(file_module=row["file / module"], expected_change=row["expected change"]) for row in target),
        requirements=requirements,
        behavior_atoms=atom_bindings,
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
        consumer_verifications=consumer_verifications,
        deferred_risks=tuple(DeferredRisk(risk=row["risk"], owner=row["owner"], decision_date=row["decision date"], mitigation=row["mitigation"]) for row in deferred_records),
        deferred_risks_none_reason=deferred_none,
        fresh_review_evidence=tuple(FreshReviewEvidence(reviewer=row["reviewer (fresh-context agent / self-audit)"], ask_items_found=row['"would have to ask" items found'], gameable_criteria_found=row["gameable criteria found"], disposition=row["folded back / re-bound?"], unresolved_after_disposition=row["unresolved after disposition"]) for row in fresh_records),
        source_part1_sha256=implementation_gate.contract_digest(handoff_text),
    )
    return BuildContract.model_validate({**body.model_dump(), "contract_digest": body_digest(body)})


def is_current(contract: BuildContract, handoff_text: str) -> bool:
    return contract.source_part1_sha256 == implementation_gate.contract_digest(handoff_text)


def canonical_json(contract: BuildContract) -> str:
    body = ContractBody.model_validate(contract.model_dump(exclude={"contract_digest"}))
    payload = canonical_body_payload(body)
    payload["contract_digest"] = contract.contract_digest
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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
