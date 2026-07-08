#!/usr/bin/env -S uv run --script
# noqa: SIZE_OK  — single self-contained evidence adapter; splitting would leak executor layout knowledge across modules
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
#      uv run scripts/pack_evidence.py <session-dir> --diff-range main..HEAD
#      (ulw-loop state auto-discovered under <repo-root>/.omo/ulw-loop; --ulw-dir overrides)
# ──────────────────
#
# ExecutionEvidenceBundle adapter (docs/ultimateinterview-postmortem-closed-loop-handoff.md §14.3).
#
# Projects scattered execution evidence into ONE schema-versioned JSON the
# postmortem consumes, so the postmortem never reads executor-internal formats
# directly. This file is the ONLY code allowed to know the ulw-loop file
# layout; everything downstream knows only the bundle schema, which this
# script owns. ulw-loop's ledger is append-only JSONL with NO schema version
# (lazycodex plan-io.ts), so upstream drift must break HERE, loudly, not
# silently inside a postmortem judgment.
#
# Fail-closed boundary: files whose schema WE own (interview ledger,
# decisions.jsonl) abort on any invalid content - exit 1, one-line error.
# Files owned by the executor (ulw-loop goals/ledger) are foreign: malformed
# lines are collected into `warnings`, absent inputs into `missing_evidence`,
# and both surface in the bundle - never silently dropped.

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, ClassVar, Final

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# The interview ledger parser lives in the sibling ultimateinterview skill;
# import the module directly (not as a `scripts` package) so this skill's own
# scripts/ dir never shadows it.
_INTERVIEW_SCRIPTS: Final[Path] = (
    Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts"
)
sys.path.insert(0, str(_INTERVIEW_SCRIPTS))

import lessons as lessons_store  # noqa: E402
from ambiguity_ledger import parse_entries  # noqa: E402

BUNDLE_SCHEMA_VERSION: Final[int] = 3
BUNDLE_FILENAME: Final[str] = "evidence_bundle.json"
DECISIONS_FILENAME: Final[str] = "decisions.jsonl"
DEFAULT_ULW_RELPATH: Final[str] = ".omo/ulw-loop"
DEFAULT_EVIDENCE_RELPATH: Final[str] = ".omo/evidence"
DEFAULT_REPO_LESSONS_RELPATH: Final[str] = "docs/ultimateinterview-lessons.md"
GLOBAL_LESSONS_PATH: Final[Path] = _INTERVIEW_SCRIPTS.parent / "lessons.md"
MAX_ARTIFACT_TEXT_BYTES: Final[int] = 128_000
# The bundle is consumed by a model context, not replayed by a machine; these
# bounds keep it readable end-to-end. Raw executor state stays on disk at
# sources.ulw_dir - the bundle carries digests, never the snapshots.
MAX_EVENT_STRING_CHARS: Final[int] = 2_000
MAX_EVENT_VALUE_BYTES: Final[int] = 8_192
MAX_TOTAL_ARTIFACT_TEXT_BYTES: Final[int] = 262_144
BUNDLE_SIZE_WARN_BYTES: Final[int] = 786_432
PREVIEW_CHARS: Final[int] = 280
IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".gif", ".jpeg", ".jpg", ".png", ".webp"})

# ulw-loop ledger event kinds this adapter projects (verified against
# lazycodex/plugins/omo/components/ulw-loop/src/constants.ts, v4.16.0).
CRITERION_EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {"evidence_captured", "criterion_failed", "criterion_blocked"}
)
REVISION_EVENT_KINDS: Final[frozenset[str]] = frozenset({"criteria_revised"})
USER_DECISION_EVENT_KINDS: Final[frozenset[str]] = frozenset({"goal_needs_user_decision"})


class PostmortemClass(StrEnum):
    SPEC_GAP = "spec_gap"
    IMPLEMENTATION_DEVIATION = "implementation_deviation"
    EVALUATION_UNCERTAINTY = "evaluation_uncertainty"
    EXECUTION_PROCESS_GAP = "execution_process_gap"
    LEGITIMATE_SPEC_EVOLUTION = "legitimate_spec_evolution"


class DecisionRecord(BaseModel):
    """One implementer decision/assumption made during execution.

    `self_class` is the implementer's own guess at the postmortem class; the
    postmortem may overrule it - it is evidence, not a verdict.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    spec_citation: str | None = None
    alternatives: tuple[str, ...] = ()
    impact: str | None = None
    self_class: PostmortemClass | None = None
    ts: str | None = None


def fail(message: str) -> typer.Exit:
    typer.secho(f"pack_evidence: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def read_required(path: Path, label: str) -> str:
    if not path.is_file():
        raise fail(f"{label} not found at {path} - a postmortem needs it; nothing was written")
    return path.read_text(encoding="utf-8")


def parse_decisions(path: Path, missing: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        missing.append(
            f"{DECISIONS_FILENAME} absent - implementer decisions were not logged; "
            "spec_gap attribution will lean on the diff alone"
        )
        return []
    decisions: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = DecisionRecord.model_validate_json(line)
        except ValidationError as error:
            first = error.errors()[0]
            location = ".".join(str(part) for part in first["loc"]) or "<record>"
            raise fail(
                f"{DECISIONS_FILENAME} line {lineno}: {location}: {first['msg']} - "
                "schema: decision, reason (required); spec_citation, alternatives, "
                f"impact, self_class ({'|'.join(PostmortemClass)}), ts (optional; snake_case)"
            ) from error
        decisions.append(record.model_dump(mode="json"))
    return decisions


def compact_field(value: Any) -> Any:
    """Bound one record field: truncate long strings inline, stub oversized
    containers with shape + sha256 + preview.

    ulw-loop steering events embed full goals-state snapshots (`steering`,
    `before`, `after`, tens of KB each); packed verbatim they made a real
    bundle 5 MB - unreadable by the consumer the bundle exists for. The
    narrative fields (`message`, `evidence`, ids) stay verbatim; a stub names
    the source when a snapshot genuinely needs hand inspection.
    """
    if isinstance(value, str):
        if len(value) <= MAX_EVENT_STRING_CHARS:
            return value
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return (
            value[:MAX_EVENT_STRING_CHARS]
            + f" …[truncated: {len(value):,} chars total, sha256 {digest}]"
        )
    if isinstance(value, (dict, list)):
        serialized = json.dumps(value, ensure_ascii=False)
        if len(serialized) <= MAX_EVENT_VALUE_BYTES:
            return value
        stable = json.dumps(value, ensure_ascii=False, sort_keys=True)
        stub: dict[str, Any] = {
            "omitted": "oversized-value",
            "bytes": len(serialized),
            "sha256": hashlib.sha256(stable.encode("utf-8")).hexdigest()[:12],
            "shape": (
                f"dict({len(value)} keys)"
                if isinstance(value, dict)
                else f"list({len(value)} items)"
            ),
            "preview": serialized[:PREVIEW_CHARS],
        }
        if isinstance(value, dict):
            stub["keys"] = sorted(value)[:20]
        return stub
    return value


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: compact_field(value) for key, value in record.items()}


def compact_goals(goals: Any) -> Any:
    """Compact goals.json per goal, not as one container - the goals list is
    the one field whose total size legitimately grows with goal count."""
    if not isinstance(goals, dict):
        return compact_field(goals)
    compacted: dict[str, Any] = {}
    for key, value in goals.items():
        if key == "goals" and isinstance(value, list):
            compacted[key] = [
                compact_record(item) if isinstance(item, dict) else compact_field(item)
                for item in value
            ]
        else:
            compacted[key] = compact_field(value)
    return compacted


def snapshot_lessons(
    lessons_paths: list[Path] | None,
    repo_root: Path,
    missing: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """Snapshot each lessons store's ACTIVE rows at pack time (= audit start).

    postmortem_lint validates the report's fire-tracking table against THIS
    snapshot, not the live store: a bulk-absorption run empties the active
    table before the lint sees it, so validating against the live file would
    pass vacuously - the exact blind spot the app-5 run exposed. Pack runs
    first in the audit, so the snapshot is the audit-start truth.
    """
    explicit = lessons_paths is not None
    candidates = (
        list(lessons_paths)
        if explicit
        else [repo_root / DEFAULT_REPO_LESSONS_RELPATH, GLOBAL_LESSONS_PATH]
    )
    stores: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.is_file():
            if explicit:
                missing.append(
                    f"lessons store {path} not found - fire-tracking cannot be anchored to it"
                )
            continue
        try:
            parsed = lessons_store.parse_file(path)
        except Exception as error:  # noqa: BLE001 - degrade, don't abort the whole bundle
            warnings.append(f"lessons store {path} did not parse ({error}) - snapshot skipped")
            continue
        stores.append(
            {
                "path": resolved,
                "name": path.name,
                "active_count": len(parsed.rows),
                "active": [
                    {
                        "signal": row.signal[:120],
                        "lens": row.lens,
                        "fired": row.fired,
                        "caught": row.caught,
                    }
                    for row in parsed.rows
                ],
            }
        )
    return {"stores": stores}


def has_ulw_state(directory: Path) -> bool:
    return (directory / "ledger.jsonl").is_file() or (directory / "goals.json").is_file()


def newest_state_mtime(directory: Path) -> float:
    return max(
        path.stat().st_mtime
        for name in ("ledger.jsonl", "goals.json")
        if (path := directory / name).is_file()
    )


def discover_ulw_state(
    root: Path, slug: str, missing: list[str], warnings: list[str]
) -> Path | None:
    """Locate the ulw-loop state dir at `root` or one subdir level below it.

    ulw-loop scopes its state to `<root>/<session-id>/` whenever a Codex
    session id is set (OMO_ULW_LOOP_SESSION_ID / CODEX_SESSION_ID), so the
    advertised directory is often just a container. Among candidates, a
    brief.md that mentions the interview slug wins; otherwise the newest
    ledger/goals mtime does, with a warning naming the losers.
    """
    if not root.is_dir():
        missing.append(
            f"no ulw-loop state at {root} - execution ledger absent from the bundle "
            "(pass --ulw-dir if it lives elsewhere)"
        )
        return None
    subdirs = sorted(path for path in root.iterdir() if path.is_dir())
    candidates = [d for d in (root, *subdirs) if has_ulw_state(d)]
    if not candidates:
        missing.append(
            f"{root} holds no goals.json/ledger.jsonl (one subdir level checked) - "
            "execution ledger absent from the bundle (pass --ulw-dir if it lives elsewhere)"
        )
        return None
    if len(candidates) == 1:
        return candidates[0]
    briefed = [
        d
        for d in candidates
        if (brief := d / "brief.md").is_file()
        and slug in brief.read_text(encoding="utf-8")
    ]
    if len(briefed) == 1:
        return briefed[0]
    pool = briefed or candidates
    chosen = max(pool, key=newest_state_mtime)
    losers = ", ".join(str(d) for d in pool if d != chosen)
    warnings.append(
        f"multiple ulw-loop state dirs; chose {chosen} by newest state mtime "
        f"over {losers} - pass --ulw-dir to override"
    )
    return chosen


def resolve_ulw_dir(
    ulw_dir: Path | None,
    no_ulw: bool,
    repo_root: Path,
    slug: str,
    missing: list[str],
    warnings: list[str],
) -> Path | None:
    if no_ulw:
        if ulw_dir is not None:
            raise fail("give --ulw-dir or --no-ulw, not both")
        missing.append("--no-ulw given - execution evidence deliberately excluded")
        return None
    if ulw_dir is not None:
        if not ulw_dir.is_dir():
            raise fail(f"--ulw-dir {ulw_dir} is not a directory")
        return discover_ulw_state(ulw_dir, slug, missing, warnings)
    return discover_ulw_state(repo_root / DEFAULT_ULW_RELPATH, slug, missing, warnings)


def parse_ulw_dir(
    ulw_dir: Path | None, missing: list[str], warnings: list[str]
) -> dict[str, Any]:
    absent: dict[str, Any] = {
        "present": False,
        "brief_md": None,
        "goals": None,
        "ledger_events": [],
        "criterion_events": [],
        "revisions": [],
        "user_decision_blockers": [],
        "event_kind_counts": {},
    }
    if ulw_dir is None:
        return absent

    execution = dict(absent, present=True)

    brief = ulw_dir / "brief.md"
    execution["brief_md"] = brief.read_text(encoding="utf-8") if brief.is_file() else None

    goals_path = ulw_dir / "goals.json"
    if goals_path.is_file():
        try:
            execution["goals"] = compact_goals(json.loads(goals_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as error:
            warnings.append(f"goals.json is not valid JSON ({error}) - carried as absent")
    else:
        missing.append("ulw-loop goals.json absent")

    ledger_path = ulw_dir / "ledger.jsonl"
    events: list[dict[str, Any]] = []
    if ledger_path.is_file():
        for lineno, line in enumerate(
            ledger_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(
                    f"ulw ledger.jsonl line {lineno} is not valid JSON - "
                    "kept out of projections; inspect it by hand"
                )
                continue
            if not isinstance(event, dict):
                warnings.append(f"ulw ledger.jsonl line {lineno} is not an object - skipped")
                continue
            events.append(compact_record(event))
    else:
        missing.append("ulw-loop ledger.jsonl absent")

    counts: dict[str, int] = {}
    for event in events:
        kind = str(event.get("kind", "<no-kind>"))
        counts[kind] = counts.get(kind, 0) + 1
    execution["ledger_events"] = events
    execution["event_kind_counts"] = counts
    execution["criterion_events"] = [e for e in events if e.get("kind") in CRITERION_EVENT_KINDS]
    execution["revisions"] = [e for e in events if e.get("kind") in REVISION_EVENT_KINDS]
    execution["user_decision_blockers"] = [
        e for e in events if e.get("kind") in USER_DECISION_EVENT_KINDS
    ]
    return execution


def collect_diff(
    diff_range: str | None,
    diff_file: Path | None,
    repo_root: Path,
    missing: list[str],
) -> dict[str, str] | None:
    if diff_range is not None and diff_file is not None:
        raise fail("give --diff-range or --diff-file, not both")
    if diff_file is not None:
        if not diff_file.is_file():
            raise fail(f"--diff-file {diff_file} not found")
        return {"source": str(diff_file), "text": diff_file.read_text(encoding="utf-8")}
    if diff_range is not None:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", diff_range],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise fail(f"git diff {diff_range} failed: {result.stderr.strip()}")
        return {"source": f"git diff {diff_range}", "text": result.stdout}
    missing.append(
        "no implementation diff (--diff-range/--diff-file) - "
        "the divergence audit cannot run without one"
    )
    return None


def resolve_evidence_dir(
    evidence_dir: Path | None,
    repo_root: Path,
    slug: str,
    missing: list[str],
) -> Path | None:
    if evidence_dir is not None:
        resolved = evidence_dir if evidence_dir.is_absolute() else repo_root / evidence_dir
        if not resolved.is_dir():
            raise fail(f"--evidence-dir {evidence_dir} is not a directory")
        return resolved
    root = repo_root / DEFAULT_EVIDENCE_RELPATH
    slug_dir = root / slug
    if slug_dir.is_dir():
        return slug_dir
    if root.is_dir():
        missing.append(
            f"no evidence artifact dir at {slug_dir} - pass --evidence-dir if artifacts "
            "live under a different .omo/evidence subdirectory"
        )
    else:
        missing.append(
            f"no evidence artifact root at {root} - manual/runtime artifacts absent "
            "from the bundle"
        )
    return None


def collect_evidence_artifacts(
    evidence_dir: Path | None,
    repo_root: Path,
    execution: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    artifact_bundle: dict[str, Any] = {
        "present": False,
        "root": None,
        "files": [],
    }
    if evidence_dir is None:
        return artifact_bundle

    files: list[dict[str, Any]] = []
    text_budget = MAX_TOTAL_ARTIFACT_TEXT_BYTES
    for path in sorted(item for item in evidence_dir.rglob("*") if item.is_file()):
        try:
            content = path.read_bytes()
        except OSError as error:
            warnings.append(f"could not read evidence artifact {path}: {error}")
            continue

        rel_path = str(path.relative_to(repo_root))
        record: dict[str, Any] = {
            "id": artifact_id(rel_path),
            "kind": artifact_kind(path),
            "path": rel_path,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "referenced_by": artifact_references(rel_path, execution),
        }
        if len(content) > MAX_ARTIFACT_TEXT_BYTES:
            record["text_omitted"] = f"larger than {MAX_ARTIFACT_TEXT_BYTES} bytes"
        elif len(content) > text_budget:
            record["text_omitted"] = (
                f"total artifact text budget ({MAX_TOTAL_ARTIFACT_TEXT_BYTES} bytes) exhausted"
            )
        else:
            try:
                record["text"] = content.decode("utf-8")
                text_budget -= len(content)
            except UnicodeDecodeError:
                record["text_omitted"] = "non-utf8"
        files.append(record)

    artifact_bundle["present"] = True
    artifact_bundle["root"] = str(evidence_dir.resolve())
    artifact_bundle["files"] = files
    return artifact_bundle


def artifact_id(rel_path: str) -> str:
    normalized = "".join(char if char.isalnum() else "-" for char in rel_path.lower())
    return "artifact-" + "-".join(part for part in normalized.split("-") if part)


def artifact_kind(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if "screenshot" in name or "screen-shot" in name:
        return "screenshot"
    if "http" in name and ("dump" in name or "response" in name):
        return "http-dump"
    if "transcript" in name or "tmux" in name or "cli" in name:
        return "cli-transcript"
    if suffix in {".diff", ".patch"} or "diff" in name:
        return "data-diff"
    if suffix in {".json", ".jsonl", ".yaml", ".yml"}:
        return "data"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".log", ".out", ".txt"}:
        return "log"
    return "binary"


def artifact_references(rel_path: str, execution: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for index, event in enumerate(execution.get("criterion_events", [])):
        if not isinstance(event, dict):
            continue
        serialized = json.dumps(event, ensure_ascii=False, sort_keys=True)
        if rel_path not in serialized:
            continue
        references.append(
            {
                "source": "execution.criterion_events",
                "index": index,
                "kind": event.get("kind"),
                "goal_id": event.get("goalId"),
                "criterion_id": event.get("criterionId"),
            }
        )
    return references


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help=".ultimateinterview/<slug>/ session directory")
    ],
    ulw_dir: Annotated[
        Path | None,
        typer.Option(
            "--ulw-dir",
            help="ulw-loop state dir; default: auto-discover under "
            f"<repo-root>/{DEFAULT_ULW_RELPATH} (session-id subdirs included)",
        ),
    ] = None,
    no_ulw: Annotated[
        bool,
        typer.Option("--no-ulw", help="skip ulw-loop discovery; pack without execution evidence"),
    ] = False,
    diff_range: Annotated[
        str | None,
        typer.Option("--diff-range", help="git range for the implementation diff (e.g. main..HEAD)"),
    ] = None,
    diff_file: Annotated[
        Path | None,
        typer.Option("--diff-file", help="pre-saved diff file (alternative to --diff-range)"),
    ] = None,
    evidence_dir: Annotated[
        Path | None,
        typer.Option(
            "--evidence-dir",
            help="manual/runtime evidence artifact dir; default: <repo-root>/.omo/evidence/<slug>",
        ),
    ] = None,
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", help="repo for git diff; default session-dir/../.."),
    ] = None,
    lessons: Annotated[
        list[Path] | None,
        typer.Option(
            "--lessons",
            help="lessons store(s) to snapshot as the audit-start fire-tracking anchor "
            f"(repeatable); default: <repo-root>/{DEFAULT_REPO_LESSONS_RELPATH} + the global store",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help=f"output path; default <session-dir>/{BUNDLE_FILENAME}"),
    ] = None,
) -> None:
    """Pack interview spec + execution evidence + decisions + diff into one bundle."""
    if not session_dir.is_dir():
        raise fail(f"session dir {session_dir} is not a directory")
    resolved_root = (repo_root or session_dir.parent.parent).resolve()

    missing: list[str] = []
    warnings: list[str] = []

    handoff_text = read_required(session_dir / "handoff.md", "handoff.md")
    ledger_raw = read_required(session_dir / "ledger.json", "ledger.json")
    try:
        entries = parse_entries(ledger_raw)
    except (ValidationError, ValueError) as error:
        raise fail(f"ledger.json invalid: {error}") from error

    decisions = parse_decisions(session_dir / DECISIONS_FILENAME, missing)
    resolved_ulw = resolve_ulw_dir(
        ulw_dir, no_ulw, resolved_root, session_dir.resolve().name, missing, warnings
    )
    execution = parse_ulw_dir(resolved_ulw, missing, warnings)
    if execution["brief_md"] is not None and execution["brief_md"] == handoff_text:
        digest = hashlib.sha256(handoff_text.encode("utf-8")).hexdigest()[:12]
        execution["brief_md"] = f"[identical to spec.handoff_md - sha256 {digest}]"
    diff = collect_diff(diff_range, diff_file, resolved_root, missing)
    resolved_evidence_dir = resolve_evidence_dir(
        evidence_dir, resolved_root, session_dir.resolve().name, missing
    )
    artifacts = collect_evidence_artifacts(resolved_evidence_dir, resolved_root, execution, warnings)
    lessons_snapshot = snapshot_lessons(lessons, resolved_root, missing, warnings)

    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "sources": {
            "session_dir": str(session_dir.resolve()),
            "ulw_dir": str(resolved_ulw.resolve()) if resolved_ulw else None,
            "evidence_dir": str(resolved_evidence_dir.resolve()) if resolved_evidence_dir else None,
            "repo_root": str(resolved_root),
        },
        "spec": {
            "handoff_md": handoff_text,
            "interview_ledger": [entry.model_dump(mode="json") for entry in entries],
        },
        "decisions": decisions,
        "execution": execution,
        "artifacts": artifacts,
        "lessons": lessons_snapshot,
        "diff": diff,
        "warnings": warnings,
        "missing_evidence": missing,
    }

    serialized = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"
    bundle_bytes = len(serialized.encode("utf-8"))
    if bundle_bytes > BUNDLE_SIZE_WARN_BYTES:
        warnings.append(
            f"bundle is {bundle_bytes:,} bytes (> {BUNDLE_SIZE_WARN_BYTES:,}) - "
            "too large for its consumer; an executor input probably dwarfs the digest bounds"
        )
        serialized = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"
        bundle_bytes = len(serialized.encode("utf-8"))

    out_path = out or (session_dir / BUNDLE_FILENAME)
    out_path.write_text(serialized, encoding="utf-8")

    typer.echo(
        f"bundle written: {out_path} | schema v{BUNDLE_SCHEMA_VERSION} | "
        f"{bundle_bytes:,} bytes | "
        f"ledger entries {len(entries)} | decisions {len(decisions)} | "
        f"execution events {len(execution['ledger_events'])} | "
        f"artifacts {len(artifacts['files'])} | "
        f"lessons {sum(s['active_count'] for s in lessons_snapshot['stores'])} active "
        f"in {len(lessons_snapshot['stores'])} store(s) | "
        f"warnings {len(warnings)} | missing {len(missing)}"
    )
    for note in warnings:
        typer.secho(f"  warning: {note}", fg=typer.colors.YELLOW)
    for note in missing:
        typer.secho(f"  missing: {note}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
