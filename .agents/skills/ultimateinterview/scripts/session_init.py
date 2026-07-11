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
#      uv run scripts/session_init.py <repo-root> <slug> --depth focused \
#          --entries '<initial ledger entries JSON array>'
# ──────────────────

# Deterministic ORIENT-phase initializer: creates .ultimateinterview/<slug>/
# with an already-valid ledger.json, protocol.json (all six lenses pending,
# every counter 0), questions.json, and the transcript skeleton; applies the
# fresh-suffix rule for completed sessions and ensures .gitignore coverage.
# Removes the whole class of hand-written-initial-state validation errors.

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import ValidationError

from scripts import ambiguity_ledger, atomic_write, protocol_state, session_status

STATE_DIR_NAME: Final[str] = ".ultimateinterview"
MAX_SUFFIX: Final[int] = 20
SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def resolve_session_dir(root: Path, slug: str) -> tuple[Path, str]:
    """Fresh-suffix rule: a slug whose session already has a handoff gets
    <slug>-2 (then -3, ...); an unfinished session must be resumed, not
    silently re-initialized."""
    if not SLUG_PATTERN.fullmatch(slug):
        raise typer.BadParameter("slug must be lowercase kebab-case")
    base = root / STATE_DIR_NAME
    if base.is_symlink():
        raise typer.BadParameter(f"state root must not be a symlink: {base}")
    if base.exists() and not base.is_dir():
        raise typer.BadParameter(f"state root is not a directory: {base}")
    resolved_root = root.resolve()
    if not base.resolve(strict=False).is_relative_to(resolved_root):
        raise typer.BadParameter(f"state root escapes repository: {base}")
    candidate_slug = slug
    for suffix in range(2, MAX_SUFFIX + 1):
        directory = base / candidate_slug
        if directory.is_symlink():
            raise typer.BadParameter(f"session path must not be a symlink: {directory}")
        if not directory.resolve(strict=False).is_relative_to(resolved_root):
            raise typer.BadParameter(f"session path escapes repository: {directory}")
        if not directory.exists():
            return directory, candidate_slug
        if (directory / "handoff.md").is_file():
            candidate_slug = f"{slug}-{suffix}"
            continue
        raise typer.BadParameter(
            f"session {directory} exists without a handoff.md; resume it "
            "(ORIENT offers this) or pick a different slug",
        )
    raise typer.BadParameter(f"too many suffixed sessions for slug {slug!r}")


def initial_protocol(depth: protocol_state.Depth, budget: int | None) -> dict[str, object]:
    return {
        "depth": depth.value,
        "evidence_schema_version": 1,
        "contract_schema_version": 1,
        "material_revision": 0,
        "question_budget": budget or protocol_state.DEPTH_BUDGET_CAPS[depth],
        "interactions_used": 0,
        "answers_since_sweep": 0,
        "sweeps_run": 0,
        "dry_sweeps_in_row": 0,
        "contrarian_probes_run": 0,
        "falsification_checkpoints_run": 0,
        "checkpoint_since_last_material_change": False,
        "framing_challenged": False,
        "brain_dump_done": False,
        "build_contract_tested": False,
        "build_contract_digest": "",
        "build_contract_reviewer": "",
        "implementer_scout_run": False,
        "pressure_followups_by_parent": {},
        "due_now_corrections": 0,
        "lenses": {
            name: {"state": "pending", "reason": ""}
            for name in sorted(protocol_state.LENS_NAMES)
        },
        "residual_history": [],
        "gap_count_history": [],
        "recent_question_tracks": [],
        "open_world_records": [],
        "probe_decision": None,
        "probe_sequence": None,
    }


def ensure_gitignore(root: Path) -> str:
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        lines = gitignore.read_text(encoding="utf-8").splitlines()
        if any(line.strip().rstrip("/") == STATE_DIR_NAME for line in lines):
            return f".gitignore already covers {STATE_DIR_NAME}"
        with gitignore.open("a", encoding="utf-8") as handle:
            if lines and lines[-1].strip():
                handle.write("\n")
            handle.write(f"{STATE_DIR_NAME}\n")
        return f"appended {STATE_DIR_NAME} to .gitignore"
    gitignore.write_text(f"{STATE_DIR_NAME}\n", encoding="utf-8")
    return f"created .gitignore with {STATE_DIR_NAME}"


def json_text(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(
    repo_root: Annotated[
        Path,
        typer.Argument(help="Repository root (parent of .ultimateinterview/)."),
    ],
    slug: Annotated[str, typer.Argument(help="Kebab-case session slug.")],
    entries: Annotated[
        str,
        typer.Option(
            "--entries",
            help="Initial ledger entries as a JSON array (use '-' for stdin); "
            "the ledger rejects empty, so orientation must supply them.",
        ),
    ],
    depth: Annotated[
        protocol_state.Depth,
        typer.Option("--depth", help="Interview depth (sets the budget cap)."),
    ] = protocol_state.Depth.FOCUSED,
    budget: Annotated[
        int | None,
        typer.Option("--budget", min=1, help="Override the depth-default budget."),
    ] = None,
    classification: Annotated[
        str,
        typer.Option("--classification", help="One-line work classification for the transcript."),
    ] = "",
) -> None:
    if not repo_root.is_dir():
        raise typer.BadParameter(f"repo root not found: {repo_root}")
    raw_entries = sys.stdin.read() if entries == "-" else entries
    try:
        parsed = ambiguity_ledger.parse_entries(
            json.dumps({"entries": json.loads(raw_entries)}),
        )
    except (ValueError, ValidationError) as error:
        raise typer.BadParameter(
            f"invalid --entries: {ambiguity_ledger.summarize_validation_error(error)}",
        ) from error

    protocol_doc = initial_protocol(depth, budget)
    try:
        state = protocol_state.parse_state(json.dumps(protocol_doc))
    except ValidationError as error:
        raise typer.BadParameter(
            f"initial protocol invalid: {protocol_state.summarize_validation_error(error)}",
        ) from error

    session_dir, final_slug = resolve_session_dir(repo_root, slug)
    session_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{final_slug}.init-", dir=session_dir.parent),
    )
    stamp = datetime.now().strftime("%Y-%m-%d")
    header = [f"# Interview Transcript — {final_slug}", ""]
    if final_slug != slug:
        header.append(
            f"Slug suffixed per the fresh-folder rule (completed `{slug}` sessions exist); no continuity implied.",
        )
    if classification:
        header.append(f"Classification: {classification}")
    header.extend([f"Session initialized {stamp} (depth: {depth.value}).", ""])
    canonical_entries = [entry.model_dump(mode="json") for entry in parsed]
    try:
        atomic_write.commit_text_files(
            {
                staging_dir / "ledger.json": json_text({"entries": canonical_entries}),
                staging_dir / "protocol.json": json_text(protocol_doc),
                staging_dir / "questions.json": json_text({"questions": []}),
                staging_dir / "transcript.md": "\n".join(header),
            }
        )
        os.replace(staging_dir, session_dir)
        atomic_write.fsync_directory(session_dir.parent)
    except BaseException:
        cleanup_dir = staging_dir if staging_dir.exists() else session_dir
        for name in (
            "ledger.json",
            "protocol.json",
            "questions.json",
            "transcript.md",
            atomic_write.JOURNAL_NAME,
            atomic_write.LOCK_NAME,
        ):
            (cleanup_dir / name).unlink(missing_ok=True)
        cleanup_dir.rmdir()
        raise

    gitignore_note = ensure_gitignore(repo_root)
    ledger_summary = ambiguity_ledger.summarize_ambiguity(parsed)
    protocol_summary = protocol_state.summarize_protocol(state)
    ready = session_status.is_ready(ledger_summary, protocol_summary)
    typer.echo(f"- session created: {session_dir}")
    typer.echo(f"- {gitignore_note}")
    typer.echo("")
    typer.echo(session_status.render_markdown(ledger_summary, protocol_summary, ready))


if __name__ == "__main__":
    typer.run(main)
