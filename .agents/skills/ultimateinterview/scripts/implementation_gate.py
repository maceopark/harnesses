from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts import (
    ambiguity_ledger,
    build_contract_schema,
    handoff_coverage,
    predicate_lint,
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

    @property
    def implementation_ready(self) -> bool:
        return not self.failures

    def as_dict(self) -> dict[str, object]:
        return {
            "implementation_ready": self.implementation_ready,
            "failures": list(self.failures),
        }


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
    if schema_version == 0:
        return "decisions.jsonl" in normalized
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
) -> GateResult:
    evidence_schema_version = 0 if protocol is None else protocol.evidence_schema_version
    contract_schema_version = 0 if protocol is None else protocol.contract_schema_version
    failures = list(
        ambiguity_ledger.gate_failures(
            entries,
            evidence_schema_version=evidence_schema_version,
        ),
    )
    if evidence_schema_version == 1:
        if raw_ledger_text is None:
            failures.append("v1 composite gate requires the pre-normalization raw ledger")
        else:
            bundle_ids = ambiguity_ledger.raw_legacy_bundle_origin_ids(raw_ledger_text)
            if bundle_ids:
                failures.append(
                    "v1 ledger uses legacy-only raw origin 'bundle': "
                    f"{', '.join(bundle_ids)}",
                )
    if not ledger_summary.handoff_ready:
        failures.extend(ledger_summary.blockers)
    if not protocol_summary.protocol_ready:
        failures.extend(protocol_summary.handoff_blockers)
    if protocol is not None and protocol.build_contract_tested:
        if protocol.build_contract_digest != contract_digest(handoff_text):
            failures.append("fresh-implementer evidence does not match the current Part 1 digest")
    if protocol is not None and protocol.contract_schema_version == 1:
        if contract_sidecar is None:
            failures.append("BuildContract v1 sidecar is missing or invalid")
        elif contract_sidecar.source_part1_sha256 != contract_digest(handoff_text):
            failures.append("BuildContract v1 sidecar is stale for the current Part 1")
        else:
            from scripts import build_contract

            try:
                compiled_contract = build_contract.compile_handoff(handoff_text)
            except ValueError as error:
                failures.append(f"BuildContract v1 recompilation failed: {error}")
            else:
                if contract_sidecar != compiled_contract:
                    failures.append(
                        "BuildContract v1 sidecar does not exactly match compiled Part 1",
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
    return GateResult(tuple(dict.fromkeys(failures)))


def as_markdown(result: GateResult) -> str:
    lines = ["## Implementation Gate", ""]
    if result.implementation_ready:
        lines.append("- implementation_ready: yes")
    else:
        lines.append("- implementation_ready: no")
        lines.extend(f"- FAIL: {failure}" for failure in result.failures)
    return "\n".join(lines)
