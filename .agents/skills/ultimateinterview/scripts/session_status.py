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
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from scripts import ambiguity_ledger, atomic_write, implementation_gate, protocol_state

# The one protocol blocker that does not veto the stop condition: the Build
# Contract is drafted and tested inside the Handoff sequence itself.
BUILD_CONTRACT_BLOCKER_PREFIX: Final[str] = "build contract has not passed"


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


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
) -> str:
    return "\n".join(
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


def next_action(
    entries: tuple[ambiguity_ledger.LedgerEntry, ...],
    state: protocol_state.ProtocolState,
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deterministic routing of the Per-Round Loop: (action queue, advisories).
    Obligations resolve in the SKILL.md order (residual lag -> budget ->
    sweep -> stagnation), then stop condition, then pre-handoff sequence,
    then critical-path question vs batch flush. Mechanical approximation only:
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
    if state.falsification_checkpoints_run < 1 or not state.checkpoint_since_last_material_change:
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
    queue, advisories = next_action(entries, state, ledger_summary, protocol_summary, ready)
    lines = ["## Next Action", ""]
    lines.append(f"- next: {queue[0]}")
    lines.extend(f"- then: {item}" for item in queue[1:])
    lines.extend(f"- advisory: {item}" for item in advisories)
    return "\n".join(lines)


def render_json(
    ledger_summary: ambiguity_ledger.AmbiguitySummary,
    protocol_summary: protocol_state.ProtocolSummary,
    ready: bool,
) -> str:
    payload = {
        "ledger": json.loads(ambiguity_ledger.summary_as_json(ledger_summary)),
        "protocol": json.loads(protocol_state.summary_as_json(protocol_summary)),
        "interview_converged": ready,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(
    session_dir: Annotated[
        Path | None,
        typer.Argument(help="Session directory containing ledger.json and protocol.json."),
    ] = None,
    ledger_path: Annotated[
        Path | None,
        typer.Option("--ledger", help="Explicit ledger.json path (overrides the session directory)."),
    ] = None,
    protocol_path: Annotated[
        Path | None,
        typer.Option("--protocol", help="Explicit protocol.json path (overrides the session directory)."),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
    top: Annotated[int, typer.Option("--top", min=1, help="Number of top drivers.")] = 3,
    show_next: Annotated[
        bool,
        typer.Option("--next", help="Append the deterministic next-action routing."),
    ] = False,
    gate: Annotated[
        bool,
        typer.Option("--gate", help="Run the composite implementation gate (exit 1 on failure)."),
    ] = False,
) -> None:
    if session_dir is None and (ledger_path is None or protocol_path is None):
        raise typer.BadParameter(
            "pass a session directory, or both --ledger and --protocol",
        )
    if gate and session_dir is None:
        raise typer.BadParameter("--gate requires a session directory containing handoff.md")
    if gate and (ledger_path is not None or protocol_path is not None):
        raise typer.BadParameter("--gate does not accept --ledger or --protocol overrides")
    if session_dir is not None and (not session_dir.is_dir() or session_dir.is_symlink()):
        raise typer.BadParameter(
            f"session directory not found or not a directory: {session_dir}",
        )
    handoff_text: str | None = None
    if session_dir is None:
        assert ledger_path is not None and protocol_path is not None
        resolved_ledger = ledger_path
        resolved_protocol = protocol_path
        if resolved_ledger.parent.resolve() != resolved_protocol.parent.resolve():
            raise typer.BadParameter("--ledger and --protocol must share one session directory")
        with atomic_write.session_transaction(resolved_ledger.parent):
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
    else:
        resolved_ledger = ledger_path if ledger_path is not None else session_dir / "ledger.json"
        resolved_protocol = protocol_path if protocol_path is not None else session_dir / "protocol.json"
        with atomic_write.session_transaction(session_dir):
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
            if gate:
                handoff_path = session_dir / "handoff.md"
                if not handoff_path.is_file():
                    raise typer.BadParameter(f"handoff.md not found: {handoff_path}")
                handoff_text = handoff_path.read_text(encoding="utf-8")
    ledger_summary = ambiguity_ledger.summarize_ambiguity(entries, top=top)
    protocol_summary = protocol_state.summarize_protocol(state)
    ready = is_ready(ledger_summary, protocol_summary)
    renderers: dict[
        OutputFormat,
        Callable[
            [ambiguity_ledger.AmbiguitySummary, protocol_state.ProtocolSummary, bool],
            str,
        ],
    ] = {
        OutputFormat.JSON: render_json,
        OutputFormat.MARKDOWN: render_markdown,
    }
    output = renderers[output_format](ledger_summary, protocol_summary, ready)
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
        )
    if output_format is OutputFormat.MARKDOWN:
        if show_next:
            output += "\n\n" + render_next_action(
                entries, state, ledger_summary, protocol_summary, ready,
            )
        if gate_result is not None:
            output += "\n\n" + implementation_gate.as_markdown(gate_result)
    elif gate_result is not None:
        payload = json.loads(output)
        payload["implementation_gate"] = gate_result.as_dict()
        output = json.dumps(payload, indent=2, sort_keys=True)
    typer.echo(output)
    if gate_result is not None and not gate_result.implementation_ready:
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
