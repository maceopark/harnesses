from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, assert_never

from scripts import (
    ambiguity_ledger,
    behavior_atoms,
    build_contract_schema,
    handoff_coverage,
    predicate_lint,
    probe_policy,
    protocol_state,
)
from scripts import verification_lint

REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "Goal",
    "Target Surface",
    "Behavior Contract",
    "Change Impact & Preservation",
    "Quality Bars",
    "Decision Boundaries",
    "Out Of Scope / Non-Goals",
    "Implementation Constraints",
    "Rollout & Recovery",
    "Guardrail Compile",
    "Verification Commands",
    "Deferred Risks",
    "Fresh-Implementer Test",
)
PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"<[^>\n]+>")
INLINE_CODE: Final[re.Pattern[str]] = re.compile(r"`[^`\n]*`")
PAIRED_MARKUP_TAG: Final[re.Pattern[str]] = re.compile(
    r"<(?P<tag>[A-Za-z][A-Za-z0-9-]*)(?:\s+[^<>]*)?>.*?</(?P=tag)\s*>",
    re.DOTALL,
)
SELF_CLOSING_MARKUP_TAG: Final[re.Pattern[str]] = re.compile(
    r"<[A-Za-z][A-Za-z0-9-]*(?:\s+[^<>]*)?/>",
)
VOID_MARKUP_TAG: Final[re.Pattern[str]] = re.compile(
    r"<(?:area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)\b[^<>]*>",
    re.IGNORECASE,
)
NO_FINDINGS: Final[frozenset[str]] = frozenset(
    {"none", "none.", "0", "no findings", "no findings."}
)
UNRESOLVED_LABELS: Final[frozenset[str]] = frozenset(
    {"", "tbd", "todo", "pending", "unknown", "n/a", "na", "none"},
)
NEGATED_RESOLUTION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not|never|unresolved|pending|ignored)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GateResult:
    failures: tuple[str, ...]
    snapshot_complete: bool | None = None
    execution_receipts_current: bool | None = None
    execution_receipts_creditable: bool | None = None

    @property
    def implementation_ready(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "implementation_ready": self.implementation_ready,
            "failures": list(self.failures),
        }
        if self.snapshot_complete is not None:
            payload["snapshot_complete"] = self.snapshot_complete
        if self.execution_receipts_current is not None:
            payload["execution_receipts_current"] = self.execution_receipts_current
        if self.execution_receipts_creditable is not None:
            payload["execution_receipts_creditable"] = self.execution_receipts_creditable
        return payload


def section_names(part1: str) -> frozenset[str]:
    return frozenset(
        match.group(1).strip()
        for match in re.finditer(r"^##+\s+(.+?)\s*$", part1, re.MULTILINE)
    )


def section_body(part1: str, name: str) -> str:
    heading = re.search(rf"^##+\s+{re.escape(name)}\s*$", part1, re.MULTILINE)
    if heading is None:
        return ""
    next_heading = re.search(r"^##+\s+", part1[heading.end() :], re.MULTILINE)
    end = len(part1) if next_heading is None else heading.end() + next_heading.start()
    return part1[heading.end() : end].strip()


def complete_table_rows(body: str, required_headers: frozenset[str]) -> tuple[tuple[str, ...], ...]:
    for headers, rows in verification_lint.tables(body):
        normalized = frozenset(header.lower() for header in headers)
        if required_headers <= normalized:
            if any(
                len(row) != len(headers)
                or not all(cell.strip() and not contains_unresolved_placeholder(cell) for cell in row)
                for row in rows
            ):
                return ()
            return tuple(tuple(row) for row in rows)
    return ()


def complete_table_records(
    body: str,
    required_headers: frozenset[str],
) -> tuple[dict[str, str], ...]:
    for headers, rows in verification_lint.tables(body):
        normalized = [header.lower() for header in headers]
        if required_headers <= frozenset(normalized):
            if any(
                len(row) != len(headers)
                or not all(cell.strip() and not contains_unresolved_placeholder(cell) for cell in row)
                for row in rows
            ):
                return ()
            return tuple(dict(zip(normalized, row, strict=False)) for row in rows)
    return ()


def has_reasoned_line(body: str, prefix: str) -> bool:
    return bool(re.fullmatch(rf"{re.escape(prefix)}[ \t]+\S[^\n]*", body.strip()))


def has_labeled_value(body: str, label: str) -> bool:
    return bool(
        re.search(
            rf"(?im)^[ \t]*[-*]?[ \t]*{re.escape(label)}:[ \t]*\S[^\n]*$",
            body,
        ),
    )


def has_decision_log_instruction(
    decision_body: str,
    *,
    schema_version: int = 0,
) -> bool:
    """Part 1 must tell the implementer to log unforced decisions to decisions.jsonl.
    Execution substrates (e.g. lazycodex ulw-loop) do not record it automatically."""
    normalized = " ".join(decision_body.lower().split())
    match schema_version:
        case 0:
            return "decisions.jsonl" in normalized
        case 1 | 2:
            pass
        case unexpected if unexpected < 0 or unexpected > 2:
            raise build_contract_schema.ContractValidationError(
                f"unknown BuildContract schema version {unexpected}",
            )
        case unreachable:
            assert_never(unreachable)
    if re.search(r"\b(?:do not|don't|never|must not|shall not)\b", normalized):
        return False
    affirmative = re.search(
        r"\b(?:append|log|record|write)\b.*\bdecisions\.jsonl\b",
        normalized,
    )
    scope = re.search(
        r"\bevery\b.*(?:\b(?:unforced|not forced)\b.*\bdecision\b|"
        r"\bdecision\b.*\bspec did not force\b)",
        normalized,
    )
    return affirmative is not None and scope is not None


def contract_digest(handoff_text: str) -> str:
    part1 = handoff_coverage.extract_part1(handoff_text).strip() + "\n"
    return hashlib.sha256(part1.encode("utf-8")).hexdigest()


def contains_unresolved_placeholder(part1: str) -> bool:
    visible = verification_lint.strip_fenced_blocks(part1)
    visible = INLINE_CODE.sub("", visible)
    visible = PAIRED_MARKUP_TAG.sub("", visible)
    visible = SELF_CLOSING_MARKUP_TAG.sub("", visible)
    visible = VOID_MARKUP_TAG.sub("", visible)
    return PLACEHOLDER.search(visible) is not None


def v2_atom_binding_failures(
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    contract: build_contract_schema.BuildContract,
) -> tuple[str, ...]:
    entries_by_id = {entry.id: entry for entry in entries}
    contract_atom_ids = {binding.atom.id for binding in contract.behavior_atoms}
    failures: list[str] = []
    for binding in contract.behavior_atoms:
        entry = entries_by_id.get(binding.source_id)
        if entry is None:
            failures.append(f"behavior atom {binding.atom.id} source is absent from the ledger")
            continue
        if entry.assurance_class is not binding.assurance_class:
            failures.append(f"behavior atom {binding.atom.id} assurance class does not match its ledger entry")
            continue
        ledger_atoms = {atom.id: atom for atom in entry.behavior_atoms}
        ledger_atom = ledger_atoms.get(binding.atom.id)
        if ledger_atom is None:
            failures.append(f"behavior atom {binding.atom.id} is absent from its ledger entry")
        elif behavior_atoms.atom_digest(ledger_atom) != binding.atom_digest:
            failures.append(f"behavior atom {binding.atom.id} does not match its ledger atom")
    ledger_atom_ids = {atom.id for entry in entries for atom in entry.behavior_atoms}
    if unbound := sorted(ledger_atom_ids - contract_atom_ids):
        failures.append(
            f"ledger behavior atom(s) absent from the BuildContract: {', '.join(unbound)}",
        )
    return tuple(failures)


def _probe_environment_scope(decision: probe_policy.ProbeDecision) -> str:
    match decision.selected_level:
        case probe_policy.ProbeLevel.L0:
            return "l0:local"
        case probe_policy.ProbeLevel.L1:
            return "l1:behavioral-stub"
        case probe_policy.ProbeLevel.L2 | probe_policy.ProbeLevel.L3:
            if decision.execution_scope is None:
                raise build_contract_schema.ContractValidationError(
                    "authorized ProbeDecision requires an execution scope",
                )
            return decision.execution_scope.value
        case unreachable:
            assert_never(unreachable)


def v2_consumer_binding_failures(
    protocol: protocol_state.ProtocolState,
    contract: build_contract_schema.BuildContract,
) -> tuple[str, ...]:
    decision = protocol.probe_decision
    if decision is None:
        return ("Consumer Verification requires a persisted ProbeDecision",)
    if decision.contract_digest != contract.contract_digest:
        return ("Consumer Verification ProbeDecision contract digest does not match BuildContract",)
    probe_rows = tuple(
        row
        for row in contract.consumer_verifications
        if row.grant_kind is build_contract_schema.ConsumerGrantKind.PROBE
    )
    matching_rows = tuple(row for row in probe_rows if row.required_id == decision.probe_id)
    if not matching_rows:
        return ("Consumer Verification lacks a receipt binding for the persisted ProbeDecision",)
    failures: list[str] = []
    expected_scope = _probe_environment_scope(decision)
    for row in matching_rows:
        if row.target_ids != decision.target_ledger_ids:
            failures.append(
                "Consumer Verification probe target does not match persisted ProbeDecision",
            )
        if row.environment_scope != expected_scope:
            failures.append(
                "Consumer Verification probe environment/scope does not match persisted ProbeDecision",
            )
    return tuple(dict.fromkeys(failures))


def v2_consumer_verification_failures(part1: str) -> tuple[str, ...]:
    body = section_body(part1, "Consumer Verification")
    if not body:
        return ("BuildContract v2 requires Consumer Verification",)
    required_headers = build_contract_schema.CONSUMER_VERIFICATION_HEADERS
    for headers, rows in verification_lint.tables(body):
        normalized = tuple(header.lower() for header in headers)
        if not (frozenset(normalized) & frozenset(required_headers)):
            continue
        if normalized != required_headers:
            return ("Consumer Verification headers must be the exact canonical ordered set",)
        if any(
            len(row) != len(required_headers)
            or any(not cell.strip() or contains_unresolved_placeholder(cell) for cell in row)
            for row in rows
        ):
            return ("Consumer Verification needs a complete required table",)
        return ()
    return ("Consumer Verification needs a complete required table",)


def evaluate(
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    handoff_text: str,
    search_path: str | None = None,
    workdir: Path | None = None,
    protocol: protocol_state.ProtocolState | None = None,
    contract_sidecar: build_contract_schema.BuildContract | None = None,
    raw_ledger_text: str | None = None,
    snapshot_complete: bool | None = None,
    execution_receipts_current: bool | None = None,
    execution_receipts_creditable: bool | None = None,
    require_manifest: bool = False,
    require_execution_receipts: bool = False,
) -> GateResult:
    evidence_schema_version = 0 if protocol is None else protocol.evidence_schema_version
    contract_schema_version = 0 if protocol is None else protocol.contract_schema_version
    failures = list(
        ambiguity_ledger.gate_failures(
            entries,
            evidence_schema_version=evidence_schema_version,
        ),
    )
    match evidence_schema_version:
        case 0:
            pass
        case 1 | 2:
            if raw_ledger_text is None:
                failures.append(
                    f"v{evidence_schema_version} composite gate requires the pre-normalization raw ledger",
                )
            else:
                bundle_ids = ambiguity_ledger.raw_legacy_bundle_origin_ids(raw_ledger_text)
                if bundle_ids:
                    failures.append(
                        f"v{evidence_schema_version} ledger uses legacy-only raw origin 'bundle': "
                        f"{', '.join(bundle_ids)}",
                    )
        case unexpected if unexpected < 0 or unexpected > 2:
            raise build_contract_schema.ContractValidationError(
                f"unknown evidence schema version {unexpected}",
            )
        case unreachable:
            assert_never(unreachable)
    if not ledger_summary.handoff_ready:
        failures.extend(ledger_summary.blockers)
    if not protocol_summary.protocol_ready:
        failures.extend(protocol_summary.handoff_blockers)
    if any(entry.assurance_class is not None or entry.behavior_atoms for entry in entries) and evidence_schema_version != 2:
        failures.append("v2 assurance declarations require evidence schema version 2")
    if protocol is not None and protocol.build_contract_tested:
        if protocol.build_contract_digest != contract_digest(handoff_text):
            failures.append("fresh-implementer evidence does not match the current Part 1 digest")
    if protocol is not None:
        match protocol.contract_schema_version:
            case 0:
                pass
            case 1 | 2:
                version_label = f"BuildContract v{protocol.contract_schema_version}"
                if contract_sidecar is None:
                    failures.append(f"{version_label} sidecar is missing or invalid")
                elif contract_sidecar.schema_version != protocol.contract_schema_version:
                    failures.append(f"{version_label} sidecar schema version does not match protocol")
                elif contract_sidecar.source_part1_sha256 != contract_digest(handoff_text):
                    failures.append(f"{version_label} sidecar is stale for the current Part 1")
                else:
                    from scripts import build_contract

                    try:
                        compiled_contract = build_contract.compile_handoff(handoff_text)
                    except (ValueError, build_contract.BuildContractCompileError) as error:
                        failures.append(f"{version_label} recompilation failed: {error}")
                    else:
                        if contract_sidecar != compiled_contract:
                            failures.append(
                                f"{version_label} sidecar does not exactly match compiled Part 1",
                            )
                        elif protocol.contract_schema_version == 2:
                            failures.extend(v2_atom_binding_failures(entries, contract_sidecar))
                            failures.extend(v2_consumer_binding_failures(protocol, contract_sidecar))
            case unexpected if unexpected < 0 or unexpected > 2:
                raise build_contract_schema.ContractValidationError(
                    f"unknown BuildContract schema version {unexpected}",
                )
            case unreachable:
                assert_never(unreachable)
    if protocol is not None and protocol.evidence_schema_version == 2:
        failures.extend(
            f"atom coverage: {mismatch.describe()}"
            for mismatch in handoff_coverage.v2_atom_coverage(entries, handoff_text).mismatches
        )

    raw_part1 = handoff_coverage.extract_part1(handoff_text)
    part1 = verification_lint.strip_fenced_blocks(raw_part1)
    names = section_names(part1)
    missing_sections = [name for name in REQUIRED_SECTIONS if name not in names]
    if missing_sections:
        failures.append(f"missing Build Contract section(s): {', '.join(missing_sections)}")
    empty_sections = [name for name in REQUIRED_SECTIONS if name in names and not section_body(part1, name)]
    if empty_sections:
        failures.append(f"empty Build Contract section(s): {', '.join(empty_sections)}")
    if contract_schema_version == 2:
        failures.extend(v2_consumer_verification_failures(part1))
    if contains_unresolved_placeholder(raw_part1):
        failures.append("Build Contract contains an unresolved <placeholder>")

    target_body = section_body(part1, "Target Surface")
    target_rows = complete_table_rows(
        target_body,
        frozenset({"file / module", "expected change"}),
    )
    if not target_rows:
        failures.append("Target Surface needs at least one complete file/module row")

    behavior_body = section_body(part1, "Behavior Contract")
    behavior_rows = ()
    for acceptance_header in ("acceptance check", "acceptance criterion (ears or given/when/then)"):
        behavior_rows = complete_table_rows(
            behavior_body,
            frozenset({"id", "requirement", "source", acceptance_header}),
        )
        if behavior_rows:
            break
    if not behavior_rows:
        v2_headers = {
            "id",
            "requirement",
            "source",
            "acceptance criterion (ears or given/when/then)",
            "assurance class",
            "atom ids",
        }
        for headers, rows in verification_lint.tables(behavior_body):
            normalized = {header.lower() for header in headers}
            if not v2_headers <= normalized:
                continue
            atom_index = [header.lower() for header in headers].index("atom ids")
            if any(
                len(row) != len(headers)
                or any(cell.strip() == "" for index, cell in enumerate(row) if index != atom_index)
                for row in rows
            ):
                continue
            behavior_rows = (tuple(),)
            break
    if not behavior_rows:
        failures.append("Behavior Contract needs at least one complete requirement row")

    change_common = {
        "source", "preserved invariant", "target difference", "code surface",
        "acceptance check", "runtime signal",
    }
    change_body = section_body(part1, "Change Impact & Preservation")
    change_rows = any(
        complete_table_rows(change_body, frozenset({*change_common, evidence_header}))
        for evidence_header in ("current evidence", "current evidence / behavior")
    )
    if not change_rows:
        failures.append("Change Impact & Preservation needs at least one complete trace row")

    quality_body = section_body(part1, "Quality Bars")
    quality_headers = frozenset(
        {"attribute", "bar (a number an implementer can verify)", "weight", "verification"},
    )
    quality_records = complete_table_records(quality_body, quality_headers)
    quality_valid = bool(quality_records) and all(
        re.search(r"\d", record["bar (a number an implementer can verify)"])
        and record["weight"].strip() in {"1", "2", "3", "5"}
        for record in quality_records
    )
    if not has_reasoned_line(quality_body, "No measurable quality bar applies -") and not quality_valid:
        failures.append("Quality Bars needs a complete measurable row or the exact reasoned none-applies line")

    rollout_headers = frozenset(
        {"activation", "compatibility / backfill", "rollback trigger", "rollback action", "observation metric + window", "owner"},
    )
    rollout_body = section_body(part1, "Rollout & Recovery")
    rollout_is_na = rollout_body.lstrip().startswith("N/A -")
    if (rollout_is_na and not has_reasoned_line(rollout_body, "N/A -")) or (
        not rollout_is_na and not complete_table_rows(rollout_body, rollout_headers)
    ):
        failures.append("Rollout & Recovery needs a complete row or an explicit N/A reason")

    constraints = section_body(part1, "Implementation Constraints")
    if not has_labeled_value(constraints, "Decision core") or not has_labeled_value(constraints, "Effects boundary"):
        failures.append("Implementation Constraints must separate Decision core and Effects boundary")

    decision_body = section_body(part1, "Decision Boundaries")
    decision_tables = verification_lint.tables(decision_body)
    if decision_tables and not complete_table_rows(
        decision_body,
        frozenset({"decision", "agent may decide?", "boundary"}),
    ):
        failures.append("Decision Boundaries contains no complete decision row")

    if not has_decision_log_instruction(
        decision_body,
        schema_version=contract_schema_version,
    ):
        failures.append(
            "Decision Boundaries must carry the standing instruction to append every unforced "
            "decision to .ultimateinterview/<slug>/decisions.jsonl (execution substrates like "
            "ulw-loop do not record it automatically)"
        )

    guardrail_body = section_body(part1, "Guardrail Compile")
    guardrail_headers = frozenset(
        {"risk", "class", "predicate / residual / substrate owner", "evidence"},
    )
    guardrail_records = complete_table_records(guardrail_body, guardrail_headers)
    guardrail_valid = bool(guardrail_records)
    for record in guardrail_records:
        risk_class = record["class"].strip().lower()
        predicate = record["predicate / residual / substrate owner"].lower()
        if risk_class == "stop-time predicate":
            valid = bool(re.search(r"\b(?:command|count|endpoint|exit|file|request|response|status|test|threshold)\b|[<>=]|\d", predicate))
        elif risk_class == "accepted residual":
            valid = "owner:" in predicate and "decision date:" in predicate
        elif risk_class == "fast/pre-action":
            valid = "substrate:" in predicate
        else:
            valid = False
        guardrail_valid = guardrail_valid and valid
    if not has_reasoned_line(guardrail_body, "No stop-time or pre-action guardrail applies -") and not guardrail_valid:
        failures.append("Guardrail Compile needs a complete classified row or the exact reasoned none-applies line")

    verification_body = section_body(part1, "Verification Commands")
    verification_headers = frozenset({"check", "kind", "command / action", "pass condition"})
    verification_records = complete_table_records(verification_body, verification_headers)
    kinds = {record["kind"].strip().lower() for record in verification_records}
    if not verification_records:
        failures.append("Verification Commands needs complete typed command rows")
    else:
        unknown_kinds = sorted(kinds - {"test", "real-surface"})
        if unknown_kinds:
            failures.append(f"Verification Commands has unknown Kind value(s): {', '.join(unknown_kinds)}")
        for required_kind in ("test", "real-surface"):
            if required_kind not in kinds:
                failures.append(f"Verification Commands needs at least one Kind={required_kind} row")
                continue
            kind_cells = [
                record["command / action"]
                for record in verification_records
                if record["kind"].strip().lower() == required_kind
            ]
            if not verification_lint.cell_head_status(kind_cells, search_path, workdir):
                failures.append(
                    f"Verification Commands Kind={required_kind} needs executable command evidence"
                )

    deferred_body = section_body(part1, "Deferred Risks")
    deferred_entries = tuple(entry for entry in entries if entry.is_deferred)
    if deferred_entries:
        deferred_headers = frozenset({"risk", "owner", "decision date", "mitigation"})
        deferred_records = complete_table_records(deferred_body, deferred_headers)
        missing_deferred = [
            entry.id for entry in deferred_entries if not handoff_coverage.id_is_cited(entry.id, deferred_body)
        ]
        if not deferred_records or missing_deferred:
            failures.append("Deferred Risks must list every deferred entry with owner, decision date, and mitigation")

    fresh_body = section_body(part1, "Fresh-Implementer Test")
    fresh_headers = frozenset(
        {
            "reviewer (fresh-context agent / self-audit)",
            '"would have to ask" items found',
            "gameable criteria found",
            "folded back / re-bound?",
            "unresolved after disposition",
        },
    )
    fresh_records = complete_table_records(fresh_body, fresh_headers)
    if not fresh_records:
        failures.append("Fresh-Implementer Test needs one complete structured review row")
    else:
        if any(
            record["reviewer (fresh-context agent / self-audit)"].strip().lower()
            in UNRESOLVED_LABELS
            for record in fresh_records
        ):
            failures.append("Fresh-Implementer Test needs a concrete reviewer identity")
        unresolved_review = any(
            record["unresolved after disposition"].strip().lower() not in NO_FINDINGS
            for record in fresh_records
        )
        if unresolved_review:
            failures.append("Fresh-Implementer Test contains unresolved asks or gameable criteria")
        findings_present = any(
            record['"would have to ask" items found'].strip().lower() not in NO_FINDINGS
            or record["gameable criteria found"].strip().lower() not in NO_FINDINGS
            for record in fresh_records
        )
        resolved_findings = any(
            re.search(
                r"(?:folded back|re-?bound)",
                record["folded back / re-bound?"],
                re.IGNORECASE,
            )
            and not NEGATED_RESOLUTION.search(record["folded back / re-bound?"])
            for record in fresh_records
        )
        if findings_present and not resolved_findings:
            failures.append("Fresh-Implementer Test findings lack a fold-back/re-bind disposition")
        if any(
            not re.search(
                r"(?:no fold-back required|folded back|re-?bound)",
                record["folded back / re-bound?"],
                re.IGNORECASE,
            )
            or NEGATED_RESOLUTION.search(record["folded back / re-bound?"])
            for record in fresh_records
        ):
            failures.append("Fresh-Implementer Test does not record fold-back/re-bind disposition")
        if protocol is not None and not any(
            protocol.build_contract_reviewer
            == record["reviewer (fresh-context agent / self-audit)"].strip()
            for record in fresh_records
        ):
            failures.append("Fresh-Implementer Test reviewer does not match protocol review evidence")

    uncovered = [
        entry.id
        for entry in entries
        if handoff_coverage.material_settled(entry, handoff_coverage.DEFAULT_MIN_WEIGHT)
        and not handoff_coverage.id_is_cited(entry.id, part1)
    ]
    if uncovered:
        failures.append(f"material settled entries absent from Part 1: {', '.join(uncovered)}")

    failures.extend(predicate_lint.findings(part1))
    failures.extend(verification_lint.command_parse_findings(verification_body))
    heads = verification_lint.command_head_status(verification_body, search_path, workdir)
    if not heads:
        failures.append("no executable verification command found in a command/verification table")
    missing_heads = sorted(head for head, present in heads.items() if not present)
    if missing_heads:
        failures.append(f"verification command head(s) missing on this host: {', '.join(missing_heads)}")
    if require_manifest and snapshot_complete is not True:
        failures.append("current source manifest is required")
    if require_execution_receipts and execution_receipts_creditable is not True:
        failures.append("creditable imported execution receipts are required")
    return GateResult(
        tuple(dict.fromkeys(failures)),
        snapshot_complete=snapshot_complete,
        execution_receipts_current=execution_receipts_current,
        execution_receipts_creditable=execution_receipts_creditable,
    )


def as_markdown(result: GateResult) -> str:
    lines = ["## Implementation Gate", ""]
    if result.implementation_ready:
        lines.append("- implementation_ready: yes")
    else:
        lines.append("- implementation_ready: no")
        lines.extend(f"- FAIL: {failure}" for failure in result.failures)
    return "\n".join(lines)
