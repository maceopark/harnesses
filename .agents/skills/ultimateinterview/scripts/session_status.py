#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/session_status.py --format markdown .ultimateinterview/<session>/
#      uv run scripts/session_status.py --ledger ledger.json --protocol protocol.json
# 3. Or make executable and run:
#      chmod +x session_status.py && ./session_status.py <session-dir>
# ──────────────────

# Combined status runner: one call instead of ambiguity_ledger.py +
# protocol_state.py back to back. Additive - it reuses their parsing and
# derivation logic unchanged and does not replace their CLIs.

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, Final, assert_never

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from scripts import (
    assurance_schema,
    ambiguity_ledger,
    atomic_write,
    build_contract_schema,
    handoff_coverage,
    implementation_gate,
    protocol_state,
    receipt_contract,
    receipt_import,
    session_manifest,
)

# The one protocol blocker that does not veto the stop condition: the Build
# Contract is drafted and tested inside the Handoff sequence itself.
BUILD_CONTRACT_BLOCKER_PREFIX: Final[str] = "build contract has not passed"


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass(frozen=True, slots=True)
class LocalityDrift:
    repeated_keys: tuple[tuple[str, tuple[str, ...]], ...]
    sibling_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionReadPaths:
    root: Path
    ledger_path: Path
    protocol_path: Path
    gate: bool


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    entries: tuple[ambiguity_ledger.LedgerEntry, ...]
    state: protocol_state.ProtocolState
    handoff_text: str
    raw_ledger_text: str | None
    contract_sidecar: build_contract_schema.BuildContract | None
    manifest: session_manifest.ManifestStatus | None
    receipts: receipt_import.ReceiptStatus | None
    probe_receipt: receipt_import.ProbeReceiptStatus | None


def _resolve_session_member_path(root: Path, path: Path, option: str) -> Path:
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise typer.BadParameter(f"{option} cannot resolve path: {path}") from error
    if not resolved.is_relative_to(root):
        raise typer.BadParameter(
            f"{option} must resolve within the session directory: {path}",
        )
    return resolved


def parse_json_file[T](
    path: Path,
    parser: Callable[[str], T],
    error_summarizer: Callable[[Exception], str],
) -> T:
    if not path.exists():
        raise typer.BadParameter(f"input file not found: {path}")
    if not path.is_file():
        raise typer.BadParameter(f"input path is not a file: {path}")
    try:
        return parser(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise typer.BadParameter(f"{path}: {error_summarizer(error)}") from error


def capture_session_snapshot(paths: SessionReadPaths) -> SessionSnapshot:
    handoff_text = ""
    raw_ledger_text: str | None = None
    contract_sidecar: build_contract_schema.BuildContract | None = None
    manifest: session_manifest.ManifestStatus | None = None
    receipts: receipt_import.ReceiptStatus | None = None
    probe_receipt: receipt_import.ProbeReceiptStatus | None = None
    with atomic_write.session_read_transaction(paths.root):
        entries = parse_json_file(
            paths.ledger_path,
            ambiguity_ledger.parse_entries,
            ambiguity_ledger.summarize_validation_error,
        )
        state = parse_json_file(
            paths.protocol_path,
            protocol_state.parse_state,
            protocol_state.summarize_validation_error,
        )
        if paths.gate:
            raw_ledger_text = paths.ledger_path.read_text(encoding="utf-8")
            handoff_path = paths.root / "handoff.md"
            if not handoff_path.is_file():
                raise typer.BadParameter(f"handoff.md not found: {handoff_path}")
            handoff_text = handoff_path.read_text(encoding="utf-8")
            sidecar_path = paths.root / "build-contract.json"
            match state.contract_schema_version:
                case 0:
                    pass
                case 1 | 2:
                    if sidecar_path.is_file():
                        contract_sidecar = parse_json_file(
                            sidecar_path,
                            build_contract_schema.BuildContract.model_validate_json,
                            lambda error: str(error),
                        )
                case unexpected if unexpected < 0 or unexpected > 2:
                    raise typer.BadParameter(
                        f"unknown BuildContract schema version {unexpected}",
                    )
                case unreachable:
                    assert_never(unreachable)
        if state.evidence_schema_version == 2:
            handoff_path = paths.root / "handoff.md"
            if not handoff_text and handoff_path.is_file():
                handoff_text = handoff_path.read_text(encoding="utf-8")
            try:
                manifest = session_manifest._manifest_status_locked(paths.root)
            except session_manifest.SessionManifestError as error:
                manifest = session_manifest.ManifestStatus(False, None, str(error))
            snapshot_now = datetime.now(UTC)
            receipts = receipt_import._receipt_status_locked(
                paths.root,
                now=snapshot_now,
            )
            probe_receipt = receipt_import._probe_receipt_status_locked(
                paths.root,
                now=snapshot_now,
            )
    return SessionSnapshot(
        entries=entries,
        state=state,
        handoff_text=handoff_text,
        raw_ledger_text=raw_ledger_text,
        contract_sidecar=contract_sidecar,
        manifest=manifest,
        receipts=receipts,
        probe_receipt=probe_receipt,
    )


def is_ready(
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
) -> bool:
    # The documented stop condition: handoff_ready, while the protocol is
    # ready or blocked only by the not-yet-tested Build Contract.
    return ledger_summary.handoff_ready and all(
        blocker.startswith(BUILD_CONTRACT_BLOCKER_PREFIX)
        for blocker in protocol_summary.handoff_blockers
    )


def ready_line(ready: bool) -> str:
    if ready:
        return (
            "- interview_converged: yes (stop condition met: handoff_ready, and protocol blockers "
            "empty or only the build contract; run the Handoff sequence this turn)"
        )
    return "- interview_converged: no (see the ledger blockers and protocol handoff blockers above)"


def render_markdown(
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
    assurance_result: assurance_schema.AssuranceResult | None = None,
    manifest: session_manifest.ManifestStatus | None = None,
    receipts: receipt_import.ReceiptStatus | None = None,
    probe_receipt: receipt_import.ProbeReceiptStatus | None = None,
) -> str:
    output = "\n".join(
        [
            ambiguity_ledger.summary_as_markdown(ledger_summary),
            "",
            protocol_state.summary_as_markdown(protocol_summary),
            "",
            "## Combined",
            "",
            ready_line(ready),
        ],
    )
    match assurance_result:
        case None:
            pass
        case assurance_schema.AssuranceResult() as result:
            output = "\n".join(
                (
                    output,
                    "",
                    "## Assurance",
                    "",
                    f"- abi: {result.abi.value}",
                    f"- trace: {result.trace.value}",
                    f"- property: {result.property.value}",
                    f"- adequacy: {result.adequacy.value}",
                    f"- stakeholder: {result.stakeholder.value}",
                ),
            )
        case unreachable:
            assert_never(unreachable)
    match manifest:
        case None:
            pass
        case session_manifest.ManifestStatus() as status:
            lines = [
                output,
                "",
                "## Source Snapshot",
                "",
                f"- manifest_digest: {status.manifest_digest or 'none'}",
                f"- snapshot_complete: {'yes' if status.snapshot_complete else 'no'}",
            ]
            if status.reason is not None:
                lines.append(f"- snapshot_reason: {status.reason}")
            output = "\n".join(lines)
        case unreachable:
            assert_never(unreachable)
    match receipts:
        case None:
            pass
        case receipt_import.ReceiptStatus() as status:
            lines = [
                output,
                "",
                "## Execution Receipts",
                "",
                f"- execution_receipts_current: {'yes' if status.current else 'no'}",
                f"- execution_receipts_creditable: {'yes' if status.creditable else 'no'}",
            ]
            if not status.current:
                lines.append(f"- execution_receipts_reason: {status.reason}")
            output = "\n".join(lines)
        case unreachable:
            assert_never(unreachable)
    match probe_receipt:
        case None:
            pass
        case receipt_import.ProbeReceiptStatus() as status:
            lines = [
                output,
                "",
                "## Probe Receipt",
                "",
                f"- probe_receipt_verified: {'yes' if status.verified else 'no'}",
            ]
            if status.receipt_digest is not None:
                lines.append(f"- probe_receipt_digest: {status.receipt_digest}")
            if not status.verified:
                lines.append(f"- probe_receipt_reason: {status.reason}")
            output = "\n".join(lines)
        case unreachable:
            assert_never(unreachable)
    return output


def locality_drift(
    state: protocol_state.ProtocolState,
    ledger_entries: tuple[ambiguity_ledger.LedgerEntry, ...],
) -> LocalityDrift | None:
    """Return repeated question locality and unresolved ledger siblings, if any."""
    repeated = protocol_state.locality_repeated_keys(state.recent_question_tracks)
    if not repeated:
        return None
    sibling_ids: list[str] = []
    for entry in ledger_entries:
        if entry.is_deferred or entry.ambiguity_score not in {1, 2, 3}:
            continue
        track_keys = ambiguity_ledger.entry_track_keys(entry)
        if any(
            any(key not in repeated_keys for key in track_keys[dimension])
            for dimension, repeated_keys in repeated.items()
        ):
            sibling_ids.append(entry.id)
    sibling_ids_tuple = tuple(sorted(sibling_ids))
    if not sibling_ids_tuple:
        return None
    return LocalityDrift(
        repeated_keys=tuple((dimension, keys) for dimension, keys in repeated.items()),
        sibling_ids=sibling_ids_tuple,
    )


def locality_drift_action(drift: LocalityDrift) -> str:
    repeated = "; ".join(
        f"{dimension}={', '.join(keys)}" for dimension, keys in drift.repeated_keys
    )
    siblings = ", ".join(drift.sibling_ids)
    return (
        f"locality zoom-out: repeated {repeated} across the last "
        f"{protocol_state.LOCALITY_WINDOW} scored questions; unresolved sibling ledger ids: "
        f"{siblings}; enumerate/confirm those sibling tracks with a free ledger-derived "
        "sweep, else ask one breadth question; bypass the raw score queue"
    )


def next_action(
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    state: protocol_state.ProtocolState,
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deterministic routing of the Per-Round Loop: (action queue, advisories).
    Obligations resolve in the SKILL.md order (residual lag -> budget ->
    locality zoom-out -> sweep -> stagnation), then stop condition, then
    pre-handoff sequence, then critical-path question vs batch flush. Mechanical
    approximation only:
    the semantic critical-path arms (branches implementation, contradicts
    evidence, narrows scope) stay with the model."""
    if ready:
        return (
            (
                "ENDGAME: read references/handoff-sequence.md and run the canonical "
                "pre-handoff sequence this turn",
            ),
            (),
        )
    queue: list[str] = []
    lag = state.interactions_used - len(state.residual_history)
    if lag >= protocol_state.RESIDUAL_LAG_THRESHOLD:
        queue.append(
            f"bookkeeping: residual_history lags interactions_used by {lag}; "
            "include append_history in the next session_update call (free)",
        )
    if state.interactions_used >= state.question_budget:
        queue.append(
            "budget exhausted: stop ordinary questioning; present remaining gaps "
            "and ask the user to defer (owner/date) or explicitly extend the budget",
        )
    drift = locality_drift(state, entries)
    if drift is not None:
        queue.append(locality_drift_action(drift))
    if state.answers_since_sweep >= protocol_state.SWEEP_CADENCE:
        queue.append("breadth sweep (before the next scored question)")
    if protocol_state.is_stagnant(
        state.residual_history,
        state.gap_count_history,
        escalated_at=state.stagnation_escalated_at,
    ):
        queue.append(
            "stagnation escalation: contrarian probe or falsification checkpoint "
            "instead of a scored question",
        )
    active = tuple(entry for entry in entries if not entry.is_deferred)
    critical = tuple(entry.id for entry in active if entry.is_critical_path_candidate)
    batchable = tuple(entry.id for entry in active if entry.is_batchable)
    if not queue:
        if ledger_summary.handoff_ready:
            queue.append(pre_handoff_step(state, batchable))
        elif ledger_summary.triangulation_violations:
            queue.append(
                "triangulate or record explicit acceptance for weight-5 settlements: "
                f"{', '.join(ledger_summary.triangulation_violations)}",
            )
        elif critical:
            line = (
                f"scored-question targeting a critical-path gap ({', '.join(critical)})"
            )
            if 2 <= len(critical) <= 3:
                line += (
                    "; bundle eligible IF mutually independent + evidenced options "
                    "+ recommended defaults (semantic check stays with you)"
                )
            queue.append(line)
        elif batchable:
            queue.append(f"smart-default batch flush ({', '.join(batchable)})")
        else:
            queue.append(
                "no mechanical route: re-check the ledger blockers above "
                "(semantic critical-path judgment stays with you)",
            )
    advisories: list[str] = []
    has_score_3 = any(entry.ambiguity_score == 3 for entry in active)
    if not has_score_3 and not ready and not state.implementer_scout_run:
        advisories.append(
            "implementer-scout lane armed (once per interview): dispatch it with "
            "the settled-requirements extract on the next question round-trip",
        )
    return tuple(queue), tuple(advisories)


def pre_handoff_step(
    state: protocol_state.ProtocolState,
    batchable: tuple[str, ...],
) -> str:
    """First missing pre-handoff obligation in the canonical order:
    flush -> sweep -> probe -> checkpoint -> lenses -> build contract."""
    if batchable:
        return f"flush the pending smart-default batch first ({', '.join(batchable)})"
    if state.sweeps_run < 1:
        return "pre-handoff breadth sweep (none has run)"
    if state.dry_sweeps_in_row < 2:
        return "pre-handoff breadth sweep until two consecutive sweeps are dry"
    if state.contrarian_probes_run < 1:
        return "contrarian probe (pair it with the mandatory pre-handoff checkpoint)"
    if (
        state.falsification_checkpoints_run < 1
        or not state.checkpoint_since_last_material_change
    ):
        return "mandatory pre-handoff falsification checkpoint"
    undecided = sorted(
        name
        for name, lens in state.lenses.items()
        if lens.state
        in (protocol_state.LensState.PENDING, protocol_state.LensState.TRIGGERED)
    )
    if undecided:
        return f"decide/complete lens(es): {', '.join(undecided)}"
    return (
        "build-contract sequence: draft Part 1, run the fresh-implementer test, "
        "fold back, set build_contract_tested"
    )


def render_next_action(
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    state: protocol_state.ProtocolState,
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
) -> str:
    queue, advisories = next_action(
        entries, state, ledger_summary, protocol_summary, ready
    )
    lines = ["## Next Action", ""]
    lines.append(f"- next: {queue[0]}")
    lines.extend(f"- then: {item}" for item in queue[1:])
    lines.extend(f"- advisory: {item}" for item in advisories)
    return "\n".join(lines)


def render_json(
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
    assurance_result: assurance_schema.AssuranceResult | None = None,
    manifest: session_manifest.ManifestStatus | None = None,
    receipts: receipt_import.ReceiptStatus | None = None,
    probe_receipt: receipt_import.ProbeReceiptStatus | None = None,
) -> str:
    payload = {
        "ledger": json.loads(ambiguity_ledger.summary_as_json(ledger_summary)),
        "protocol": json.loads(protocol_state.summary_as_json(protocol_summary)),
        "interview_converged": ready,
    }
    match assurance_result:
        case None:
            pass
        case assurance_schema.AssuranceResult() as result:
            payload["assurance"] = result.model_dump(mode="json")
        case unreachable:
            assert_never(unreachable)
    match manifest:
        case None:
            pass
        case session_manifest.ManifestStatus() as status:
            payload["manifest_digest"] = status.manifest_digest
            payload["snapshot_complete"] = status.snapshot_complete
            if status.reason is not None:
                payload["snapshot_reason"] = status.reason
        case unreachable:
            assert_never(unreachable)
    match receipts:
        case None:
            pass
        case receipt_import.ReceiptStatus() as status:
            payload["execution_receipts_current"] = status.current
            payload["execution_receipts_creditable"] = status.creditable
            if not status.current:
                payload["execution_receipts_reason"] = status.reason
        case unreachable:
            assert_never(unreachable)
    match probe_receipt:
        case None:
            pass
        case receipt_import.ProbeReceiptStatus() as status:
            payload["probe_receipt_verified"] = status.verified
            if status.receipt_digest is not None:
                payload["probe_receipt_digest"] = status.receipt_digest
            if not status.verified:
                payload["probe_receipt_reason"] = status.reason
        case unreachable:
            assert_never(unreachable)
    return json.dumps(payload, indent=2, sort_keys=True)


def v2_migration_guidance(output_format: OutputFormat) -> str:
    message = (
        "v2 assurance was requested, but this session is schema v0/v1; "
        "migrate through the v2 session lifecycle before requesting v2 assurance"
    )
    match output_format:
        case OutputFormat.JSON:
            return json.dumps({"migration_guidance": message}, indent=2, sort_keys=True)
        case OutputFormat.MARKDOWN:
            return f"- migration_guidance: {message}"
        case unreachable:
            assert_never(unreachable)


def v2_manifest_migration_guidance(output_format: OutputFormat) -> str:
    message = (
        "a source manifest was requested, but this session is schema v0/v1; "
        "migrate through the v2 session lifecycle before requiring a source manifest"
    )
    match output_format:
        case OutputFormat.JSON:
            return json.dumps({"migration_guidance": message}, indent=2, sort_keys=True)
        case OutputFormat.MARKDOWN:
            return f"- migration_guidance: {message}"
        case unreachable:
            assert_never(unreachable)


def v2_execution_receipts_migration_guidance(output_format: OutputFormat) -> str:
    message = (
        "execution receipts were requested, but this session is schema v0/v1; "
        "migrate through the v2 session lifecycle before requiring execution receipts"
    )
    match output_format:
        case OutputFormat.JSON:
            return json.dumps({"migration_guidance": message}, indent=2, sort_keys=True)
        case OutputFormat.MARKDOWN:
            return f"- migration_guidance: {message}"
        case unreachable:
            assert_never(unreachable)


def receipt_state(
    status: receipt_import.ReceiptStatus,
) -> assurance_schema.ReceiptState:
    if status.current:
        if not status.creditable:
            return assurance_schema.ReceiptState.NON_CREDITABLE
        outcomes = status.execution_outcomes
        if not outcomes:
            return assurance_schema.ReceiptState.MALFORMED
        if receipt_contract.ReceiptOutcome.FAILURE in outcomes:
            return assurance_schema.ReceiptState.BOUND_FAILURE
        if receipt_contract.ReceiptOutcome.TIMEOUT in outcomes:
            return assurance_schema.ReceiptState.BOUND_TIMEOUT
        if receipt_contract.ReceiptOutcome.NONZERO in outcomes:
            return assurance_schema.ReceiptState.BOUND_NONZERO
        if all(
            outcome is receipt_contract.ReceiptOutcome.SUCCESS for outcome in outcomes
        ):
            return assurance_schema.ReceiptState.BOUND_SUCCESS
        return assurance_schema.ReceiptState.MALFORMED
    if "manifest_digest" in status.reason or "stale" in status.reason:
        return assurance_schema.ReceiptState.STALE
    if "replay" in status.reason or "revoked" in status.reason:
        return assurance_schema.ReceiptState.REPLAYED
    return assurance_schema.ReceiptState.MALFORMED


def runtime_assurance_result(
    persisted: assurance_schema.AssuranceResult,
    manifest: session_manifest.ManifestStatus | None,
    receipts: receipt_import.ReceiptStatus | None,
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    handoff_text: str,
) -> assurance_schema.AssuranceResult:
    if manifest is None or not manifest.snapshot_complete or receipts is None:
        return persisted
    if receipts.reason == "no imported receipts":
        return persisted
    requirements_covered, atoms_covered = handoff_coverage.v2_trace_coverage(
        entries, handoff_text
    )
    return assurance_schema.derive_assurance_result(
        assurance_schema.AssuranceInputs(
            manifest=assurance_schema.ArtifactState.VALID,
            sidecar=assurance_schema.ArtifactState.VALID,
            requirements_covered=requirements_covered,
            atoms_covered=atoms_covered,
            receipt=receipt_state(receipts),
            adequacy=persisted.adequacy,
            stakeholder=persisted.stakeholder,
        ),
    )


def main(
    session_dir: Annotated[
        Path | None,
        typer.Argument(
            help="Session directory containing ledger.json and protocol.json."
        ),
    ] = None,
    ledger_path: Annotated[
        Path | None,
        typer.Option(
            "--ledger",
            help="Explicit ledger.json path (must resolve within the session directory).",
        ),
    ] = None,
    protocol_path: Annotated[
        Path | None,
        typer.Option(
            "--protocol",
            help="Explicit protocol.json path (must resolve within the session directory).",
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
    top: Annotated[
        int, typer.Option("--top", min=1, help="Number of top drivers.")
    ] = 3,
    show_next: Annotated[
        bool,
        typer.Option("--next", help="Append the deterministic next-action routing."),
    ] = False,
    gate: Annotated[
        bool,
        typer.Option(
            "--gate", help="Run the composite implementation gate (exit 1 on failure)."
        ),
    ] = False,
    require_assurance_v2: Annotated[
        bool,
        typer.Option(
            "--require-assurance-v2",
            help="Require a schema-v2 assurance result or emit migration guidance.",
        ),
    ] = False,
    require_manifest: Annotated[
        bool,
        typer.Option(
            "--require-manifest",
            help="Require a current schema-v2 source manifest (exit 1 when stale or absent).",
        ),
    ] = False,
    require_execution_receipts: Annotated[
        bool,
        typer.Option(
            "--require-execution-receipts",
            help="Require current schema-v2 imported execution receipts (exit 1 when absent or stale).",
        ),
    ] = False,
) -> None:
    if session_dir is None and (ledger_path is None or protocol_path is None):
        raise typer.BadParameter(
            "pass a session directory, or both --ledger and --protocol",
        )
    if gate and session_dir is None:
        raise typer.BadParameter(
            "--gate requires a session directory containing handoff.md"
        )
    if gate and (ledger_path is not None or protocol_path is not None):
        raise typer.BadParameter(
            "--gate does not accept --ledger or --protocol overrides"
        )
    if require_manifest and session_dir is None:
        raise typer.BadParameter("--require-manifest requires a session directory")
    if require_execution_receipts and session_dir is None:
        raise typer.BadParameter(
            "--require-execution-receipts requires a session directory"
        )
    if session_dir is not None and (
        not session_dir.is_dir() or session_dir.is_symlink()
    ):
        raise typer.BadParameter(
            f"session directory not found or not a directory: {session_dir}",
        )
    handoff_text = ""
    raw_ledger_text: str | None = None
    contract_sidecar: build_contract_schema.BuildContract | None = None
    manifest: session_manifest.ManifestStatus | None = None
    receipts: receipt_import.ReceiptStatus | None = None
    probe_receipt: receipt_import.ProbeReceiptStatus | None = None
    if session_dir is None:
        assert ledger_path is not None and protocol_path is not None
        resolved_ledger = ledger_path
        resolved_protocol = protocol_path
        if resolved_ledger.parent.resolve() != resolved_protocol.parent.resolve():
            raise typer.BadParameter(
                "--ledger and --protocol must share one session directory"
            )
        try:
            with atomic_write.session_read_transaction(resolved_ledger.parent):
                entries = parse_json_file(
                    resolved_ledger,
                    ambiguity_ledger.parse_entries,
                    ambiguity_ledger.summarize_validation_error,
                )
                state = parse_json_file(
                    resolved_protocol,
                    protocol_state.parse_state,
                    protocol_state.summarize_validation_error,
                )
        except atomic_write.SessionLockError as error:
            raise typer.BadParameter(str(error)) from error
    else:
        root = session_dir.resolve()
        resolved_ledger = _resolve_session_member_path(
            root,
            ledger_path if ledger_path is not None else root / "ledger.json",
            "--ledger",
        )
        resolved_protocol = _resolve_session_member_path(
            root,
            protocol_path
            if protocol_path is not None
            else root / "protocol.json",
            "--protocol",
        )
        try:
            snapshot = capture_session_snapshot(
                SessionReadPaths(
                    root=root,
                    ledger_path=resolved_ledger,
                    protocol_path=resolved_protocol,
                    gate=gate,
                )
            )
        except atomic_write.SessionLockError as error:
            raise typer.BadParameter(str(error)) from error
        entries = snapshot.entries
        state = snapshot.state
        handoff_text = snapshot.handoff_text
        raw_ledger_text = snapshot.raw_ledger_text
        contract_sidecar = snapshot.contract_sidecar
        manifest = snapshot.manifest
        receipts = snapshot.receipts
        probe_receipt = snapshot.probe_receipt
    if require_assurance_v2:
        match state.evidence_schema_version:
            case 2:
                pass
            case 0 | 1:
                typer.echo(v2_migration_guidance(output_format))
                raise typer.Exit(1)
            case unexpected:
                assert_never(unexpected)
    if require_manifest:
        match state.evidence_schema_version:
            case 2:
                pass
            case 0 | 1:
                typer.echo(v2_manifest_migration_guidance(output_format))
                raise typer.Exit(1)
            case unexpected:
                assert_never(unexpected)
    if require_execution_receipts:
        match state.evidence_schema_version:
            case 2:
                pass
            case 0 | 1:
                typer.echo(v2_execution_receipts_migration_guidance(output_format))
                raise typer.Exit(1)
            case unexpected:
                assert_never(unexpected)
    match state.evidence_schema_version:
        case 0 | 1:
            assurance_result = None
        case 2:
            match state.assurance_result:
                case assurance_schema.AssuranceResult() as result:
                    assurance_result = runtime_assurance_result(
                        result, manifest, receipts, entries, handoff_text
                    )
                case None:
                    raise typer.BadParameter("schema v2 requires assurance_result")
                case unreachable:
                    assert_never(unreachable)
        case unexpected:
            assert_never(unexpected)
    ledger_summary = ambiguity_ledger.summarize_ambiguity(
        entries,
        top=top,
        evidence_schema_version=state.evidence_schema_version,
    )
    protocol_summary = protocol_state.summarize_protocol(state)
    ready = is_ready(ledger_summary, protocol_summary)
    renderers: dict[
        OutputFormat,
        Callable[
            [
                ambiguity_ledger.AmbiguitySummary,
                protocol_state.ProtocolSummary,
                bool,
                assurance_schema.AssuranceResult | None,
                session_manifest.ManifestStatus | None,
                receipt_import.ReceiptStatus | None,
                receipt_import.ProbeReceiptStatus | None,
            ],
            str,
        ],
    ] = {
        OutputFormat.JSON: render_json,
        OutputFormat.MARKDOWN: render_markdown,
    }
    output = renderers[output_format](
        ledger_summary,
        protocol_summary,
        ready,
        assurance_result,
        manifest,
        receipts,
        probe_receipt,
    )
    gate_result: implementation_gate.GateResult | None = None
    if gate:
        assert session_dir is not None
        assert handoff_text is not None
        gate_result = implementation_gate.evaluate(
            entries,
            ledger_summary,
            protocol_summary,
            handoff_text,
            workdir=(
                session_dir.parents[1]
                if session_dir.parent.name == ".ultimateinterview"
                else session_dir.parent
            ),
            protocol=state,
            contract_sidecar=contract_sidecar,
            raw_ledger_text=raw_ledger_text,
            snapshot_complete=(
                manifest.snapshot_complete if manifest is not None else None
            ),
            execution_receipts_current=(
                receipts.current if receipts is not None else None
            ),
            execution_receipts_creditable=(
                receipts.creditable if receipts is not None else None
            ),
            require_manifest=require_manifest,
            require_execution_receipts=require_execution_receipts,
        )
    if output_format is OutputFormat.MARKDOWN:
        if show_next:
            output += "\n\n" + render_next_action(
                entries,
                state,
                ledger_summary,
                protocol_summary,
                ready,
            )
        if gate_result is not None:
            output += "\n\n" + implementation_gate.as_markdown(gate_result)
    elif gate_result is not None:
        payload = json.loads(output)
        payload["implementation_gate"] = gate_result.as_dict()
        output = json.dumps(payload, indent=2, sort_keys=True)
    typer.echo(output)
    if require_manifest and (manifest is None or not manifest.snapshot_complete):
        raise typer.Exit(1)
    if require_execution_receipts and (receipts is None or not receipts.creditable):
        raise typer.Exit(1)
    if gate_result is not None and not gate_result.implementation_ready:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
