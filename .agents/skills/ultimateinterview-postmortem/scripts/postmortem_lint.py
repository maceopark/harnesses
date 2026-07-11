#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
# (pydantic/rich are pulled in by the shared handoff_coverage/lessons imports.)

# ─── How to run ───
#      uv run scripts/postmortem_lint.py <session-dir> \
#        [--lessons <lessons.md>]... [--advisory]
# ──────────────────
#
# Report-contract gate for postmortem.md.
#
# The first executor-authored postmortem (todo-cli-app-5) skipped whole
# Output-Contract sections, aggregated REQ ranges into single divergence rows
# ("REQ-001 through REQ-006" - which silently corrupts the discovery-rate
# denominator), reported one informal rate instead of the two required ones,
# and never walked the lessons stores for fire-tracking. Every one of those
# failures is mechanical, so this gate owns them: section completeness, row
# granularity, class vocabulary, calibration arithmetic recomputed FROM the
# divergence table (the table IS the denominator), and one fire-tracking row
# per active lesson. Semantic quality (correct classification, honest
# evidence) stays with the auditor - a lint cannot judge it.
#
# Fail-closed like its siblings: exit 1 on any violation unless --advisory;
# exit 2 when an input file is missing or unparseable.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

# Deterministic helpers shared with the sibling ultimateinterview skill.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)

import lessons as lessons_store  # noqa: E402
from handoff_coverage import extract_part1  # noqa: E402

DIVERGENCE_CLASSES: Final[tuple[str, ...]] = (
    "fulfilled",
    "escaped-requirement",
    "scope-drift",
    "divergent-implementation",
    "deferred-outcome",
)
FAILURE_CLASSES: Final[tuple[str, ...]] = (
    "trigger-too-narrow",
    "enumeration-miss",
    "scoring-starved",
    "answer-unpressured",
    "synthesis-loss",
)
ESCAPE_WEIGHTS: Final[frozenset[int]] = frozenset({1, 2, 3, 5})
BUNDLE_FILENAME: Final[str] = "evidence_bundle.json"
REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "implementation evidence",
    "divergence table",
    "escaped requirements",
    "wonder generalization",
    "deferred outcomes",
    "verification execution",
    "reward-hacking review",
    "scope drift",
    "lessons appended",
    "lessons fire-tracking",
    "calibration summary",
)
WONDER_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"new", "strengthened", "deduped", "not-routing/synthesis-loss"}
)
REQ_ID: Final[re.Pattern[str]] = re.compile(r"REQ-\d+")
REQ_RANGE: Final[re.Pattern[str]] = re.compile(
    r"REQ-\d+\s*(?:through|to|[–—~]|\.\.)\s*(?:REQ-)?\d+", re.IGNORECASE
)
HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+(.*)$")
PERCENT: Final[re.Pattern[str]] = re.compile(r"(\d+(?:\.\d+)?)\s*%")
RATE_TOLERANCE: Final[float] = 0.55
INTENT_ATTRIBUTION: Final[re.Pattern[str]] = re.compile(
    r"^(?:run-blind|owned-signal:\S+)$"
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def split_sections(text: str) -> list[tuple[str, str]]:
    """(normalized heading, body-until-next-heading) pairs, any heading level."""
    sections: list[tuple[str, str]] = []
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            if current is not None:
                sections.append((current, "\n".join(body)))
            current = match.group(1).strip().lower()
            body = []
        else:
            body.append(line)
    if current is not None:
        sections.append((current, "\n".join(body)))
    return sections


def section_body(sections: list[tuple[str, str]], key: str) -> str | None:
    for heading, body in sections:
        if key in heading:
            return body
    return None


def first_table(body: str) -> tuple[list[str], list[list[str]]] | None:
    lines = [line.strip() for line in body.splitlines()]
    start = next(
        (index for index, line in enumerate(lines) if line.startswith("|")), None
    )
    if start is None or start + 1 >= len(lines):
        return None
    if not lines[start + 1].startswith("|") or "---" not in lines[start + 1]:
        return None

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    headers = cells(lines[start])
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(cells(line))
    return headers, rows


def column_index(headers: list[str], needle: str) -> int | None:
    for index, header in enumerate(headers):
        if needle in header.lower():
            return index
    return None


def cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def whole_token(needle: str, haystack: str) -> bool:
    pattern = re.compile(rf"(?<![0-9A-Za-z_-]){re.escape(needle)}(?![0-9A-Za-z_-])")
    return pattern.search(haystack) is not None


def strip_md(value: str) -> str:
    """Drop leading markdown emphasis/backticks so a bolded class cell
    (`**escaped-requirement**`) still matches its class token."""
    return value.strip().lstrip("*_`~ ").lower()


def leading_class(value: str, vocabulary: tuple[str, ...]) -> str | None:
    lowered = strip_md(value)
    for token in vocabulary:
        if lowered.startswith(token):
            return token
    return None
REWARD_HACKING_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"cleared", "legitimate-test-doc-only", "confirmed-gaming"}
)
REWARD_HACKING_GAMING_COLUMNS: Final[tuple[str, ...]] = (
    "mock-substitution",
    "tautological-assertion",
    "hardcoded-expected",
)


def reward_hacking_violation(message: str) -> str:
    return f"reward-hacking: {message}"


def check_reward_hacking(
    body: str | None,
    part1: str,
    divergence_body: str | None,
    violations: list[str],
) -> None:
    """Check human-entered anti-gaming dispositions for internal consistency.

    This intentionally does not inspect changed paths. `audit_scan` owns that
    heuristic and its candidates stay advisory; this gate only checks what the
    reviewer recorded in the report.
    """
    if body is None:
        violations.append(reward_hacking_violation("missing Reward-Hacking Review section"))
        return
    table = first_table(body)
    if table is None:
        violations.append(reward_hacking_violation("section has no markdown table"))
        return
    headers, rows = table
    required_columns = (
        "req-id",
        "divergence class",
        "production-source-support",
        *REWARD_HACKING_GAMING_COLUMNS,
        "disposition",
        "evidence",
    )
    columns: dict[str, int] = {}
    for name in required_columns:
        index = column_index(headers, name)
        if index is None:
            violations.append(
                reward_hacking_violation(f"table has no {name!r} column")
            )
        else:
            columns[name] = index
    if len(columns) != len(required_columns):
        return

    divergence_classes: dict[str, str] = {}
    divergence_table = first_table(divergence_body) if divergence_body is not None else None
    if divergence_table is not None:
        divergence_headers, divergence_rows = divergence_table
        class_column = column_index(divergence_headers, "class")
        if class_column is not None:
            for divergence_row in divergence_rows:
                ids = REQ_ID.findall(cell(divergence_row, 0))
                token = leading_class(
                    cell(divergence_row, class_column), DIVERGENCE_CLASSES
                )
                if len(ids) == 1 and token is not None:
                    divergence_classes[ids[0]] = token

    expected_ids = set(REQ_ID.findall(part1))
    seen: set[str] = set()
    for number, row in enumerate(rows, start=1):
        req_cell = cell(row, columns["req-id"])
        ids = REQ_ID.findall(req_cell)
        if REQ_RANGE.search(req_cell):
            violations.append(
                reward_hacking_violation(
                    f"row {number} aggregates a REQ range ({req_cell!r}); use one Part-1 REQ-ID"
                )
            )
        if len(ids) != 1:
            violations.append(
                reward_hacking_violation(
                    f"row {number} must name exactly one REQ-ID ({req_cell!r})"
                )
            )
            continue
        req_id = ids[0]
        if req_id in seen:
            violations.append(
                reward_hacking_violation(f"duplicate review row for {req_id}")
            )
        seen.add(req_id)
        if req_id not in expected_ids:
            violations.append(
                reward_hacking_violation(f"row {number} names non-Part-1 {req_id}")
            )

        values = {
            name: strip_md(cell(row, index))
            for name, index in columns.items()
        }
        for name in (
            "production-source-support",
            *REWARD_HACKING_GAMING_COLUMNS,
        ):
            if values[name] not in {"yes", "no"}:
                violations.append(
                    reward_hacking_violation(
                        f"row {number} has invalid {name} value {cell(row, columns[name])!r}; expected yes/no"
                    )
                )
        divergence_class = leading_class(
            cell(row, columns["divergence class"]), DIVERGENCE_CLASSES
        )
        if divergence_class is None:
            violations.append(
                reward_hacking_violation(
                    f"row {number} has unknown divergence class "
                    f"{cell(row, columns['divergence class'])!r}"
                )
            )
        elif divergence_classes.get(req_id) not in {None, divergence_class}:
            violations.append(
                reward_hacking_violation(
                    f"{req_id} is {divergence_classes[req_id]!r} in the Divergence Table "
                    f"but {divergence_class!r} in this review"
                )
            )
        disposition = values["disposition"]
        if disposition not in REWARD_HACKING_DISPOSITIONS:
            violations.append(
                reward_hacking_violation(
                    f"row {number} has invalid disposition {cell(row, columns['disposition'])!r}"
                )
            )
        if not cell(row, columns["evidence"]).strip():
            violations.append(
                reward_hacking_violation(f"row {number} has blank evidence/rationale")
            )
        gaming_yes = any(
            values[name] == "yes" for name in REWARD_HACKING_GAMING_COLUMNS
        )
        if gaming_yes and disposition != "confirmed-gaming":
            violations.append(
                reward_hacking_violation(
                    f"{req_id} has a gaming condition marked yes but disposition is {disposition!r}"
                )
            )
        if disposition == "confirmed-gaming" and divergence_class != "divergent-implementation":
            violations.append(
                reward_hacking_violation(
                    f"{req_id} is confirmed-gaming but not classed divergent-implementation"
                )
            )
        if disposition == "legitimate-test-doc-only" and not cell(
            row, columns["evidence"]
        ).strip():
            violations.append(
                reward_hacking_violation(
                    f"{req_id} legitimate-test-doc-only disposition needs rationale/evidence"
                )
            )

    missing = sorted(expected_ids - seen)
    if missing:
        violations.append(
            reward_hacking_violation(
                "Part-1 requirement(s) absent from review: " + ", ".join(missing)
            )
        )


def check_divergence(
    body: str, part1: str, violations: list[str]
) -> dict[str, int]:
    counts = dict.fromkeys(DIVERGENCE_CLASSES, 0)
    table = first_table(body)
    if table is None:
        violations.append("Divergence Table section has no markdown table")
        return counts
    headers, rows = table
    class_column = column_index(headers, "class")
    if class_column is None:
        violations.append("Divergence Table has no Class column")
        return counts
    if not rows:
        violations.append("Divergence Table has no rows - the audit has no denominator")

    table_ids: set[str] = set()
    for number, row in enumerate(rows, start=1):
        id_cell = cell(row, 0)
        if REQ_RANGE.search(id_cell):
            violations.append(
                f"Divergence Table row {number} aggregates a REQ range ({id_cell!r}) - "
                "one row per requirement; ranges corrupt the discovery-rate denominator"
            )
        table_ids.update(REQ_ID.findall(id_cell))
        token = leading_class(cell(row, class_column), DIVERGENCE_CLASSES)
        if token is None:
            violations.append(
                f"Divergence Table row {number} has unknown class "
                f"{cell(row, class_column)!r} (expected one of {', '.join(DIVERGENCE_CLASSES)})"
            )
        else:
            counts[token] += 1

    missing = sorted(set(REQ_ID.findall(part1)) - table_ids)
    if missing:
        violations.append(
            "Part-1 requirement(s) absent from the Divergence Table: " + ", ".join(missing)
        )
    return counts
def intent_violation(message: str) -> str:
    return f"intent: {message}"




def check_escapes(
    body: str | None,
    escaped_count: int,
    violations: list[str],
    *,
    require_intent: bool = True,
) -> int:
    """Validate the Escaped Requirements table; return the synthesis-loss row count."""
    table = first_table(body) if body is not None else None
    if table is None:
        if escaped_count:
            violations.append(
                f"Divergence Table counts {escaped_count} escaped-requirement row(s) "
                "but the Escaped Requirements section has no table"
            )
        return 0
    headers, rows = table
    if len(rows) != escaped_count:
        violations.append(
            f"Escaped Requirements table has {len(rows)} row(s) but the Divergence Table "
            f"counts {escaped_count} escaped-requirement row(s) - they must match 1:1"
        )
    if not rows:
        return 0
    failure_column = column_index(headers, "failure")
    weight_column = column_index(headers, "weight")
    intent_column = column_index(headers, "intent attribution")
    if failure_column is None:
        violations.append("Escaped Requirements table has no failure-class column")
    if weight_column is None:
        violations.append("Escaped Requirements table has no Weight column (1/2/3/5)")
    if intent_column is None and require_intent:
        violations.append(intent_violation("Escaped Requirements table has no Intent attribution column"))
    synthesis = 0
    for number, row in enumerate(rows, start=1):
        if failure_column is not None:
            token = leading_class(cell(row, failure_column), FAILURE_CLASSES)
            if token is None:
                violations.append(
                    f"Escaped Requirements row {number} has unknown failure class "
                    f"{cell(row, failure_column)!r}"
                )
            elif token == "synthesis-loss":
                synthesis += 1
        if weight_column is not None:
            digits = re.search(r"\d+", cell(row, weight_column))
            if digits is None or int(digits.group()) not in ESCAPE_WEIGHTS:
                violations.append(
                    f"Escaped Requirements row {number} weight "
                    f"{cell(row, weight_column)!r} is not one of 1/2/3/5"
                )
        if intent_column is not None:
            attribution = cell(row, intent_column).strip()
            if not INTENT_ATTRIBUTION.fullmatch(attribution):
                violations.append(
                    intent_violation(
                        f"Escaped Requirements row {number} has invalid Intent attribution "
                        f"{attribution!r}; expected run-blind or owned-signal:<ref>"
                    )
                )
    return synthesis
def wonder_violation(message: str) -> str:
    return f"wonder: {message}"


def normalize_lesson_value(value: str) -> str:
    """Normalize presentation-only markdown differences for report linkage."""
    return " ".join(strip_md(value).casefold().split())


def check_wonder(
    body: str | None,
    escapes_body: str | None,
    lessons_body: str | None,
    violations: list[str],
) -> None:
    """Validate only the deterministic Wonder-to-escape/report linkage."""
    if body is None:
        return  # REQUIRED_SECTIONS already reports the missing section.
    wonder_table = first_table(body)
    if wonder_table is None:
        violations.append(wonder_violation("section has no markdown table"))
        return
    escape_table = first_table(escapes_body) if escapes_body is not None else None
    if escape_table is None:
        violations.append(
            wonder_violation("cannot join rows: Escaped Requirements has no markdown table")
        )
        return

    escape_headers, escape_rows = escape_table
    escape_req_column = column_index(escape_headers, "req-id")
    escape_failure_column = column_index(escape_headers, "failure")
    if escape_req_column is None:
        violations.append(
            wonder_violation("Escaped Requirements has no REQ-ID column for the join")
        )
        return
    if escape_failure_column is None:
        violations.append(
            wonder_violation("Escaped Requirements has no failure-class column for attribution")
        )
        return

    escapes: dict[str, str] = {}
    for number, row in enumerate(escape_rows, start=1):
        ids = REQ_ID.findall(cell(row, escape_req_column))
        if len(ids) != 1:
            violations.append(
                wonder_violation(
                    f"Escaped Requirements row {number} must name exactly one REQ-ID"
                )
            )
            continue
        req_id = ids[0]
        if req_id in escapes:
            violations.append(wonder_violation(f"duplicate escaped requirement {req_id}"))
            continue
        failure = leading_class(cell(row, escape_failure_column), FAILURE_CLASSES)
        if failure is None:
            violations.append(
                wonder_violation(
                    f"Escaped Requirements row {number} has no recognized failure class"
                )
            )
            continue
        escapes[req_id] = failure

    wonder_headers, wonder_rows = wonder_table
    required_columns = (
        "escape req-id",
        "unknown class",
        "interview-time observable signal",
        "lens",
        "disposition",
        "store",
        "evidence",
    )
    columns: dict[str, int] = {}
    for name in required_columns:
        index = column_index(wonder_headers, name)
        if index is None:
            violations.append(wonder_violation(f"table has no {name!r} column"))
        else:
            columns[name] = index
    if len(columns) != len(required_columns):
        return

    lessons: set[tuple[str, str]] = set()
    lessons_table = first_table(lessons_body) if lessons_body is not None else None
    if lessons_table is not None:
        lesson_headers, lesson_rows = lessons_table
        signal_column = column_index(lesson_headers, "signal")
        lens_column = column_index(lesson_headers, "lens to trigger")
        if signal_column is not None and lens_column is not None:
            lessons = {
                (
                    normalize_lesson_value(cell(row, signal_column)),
                    normalize_lesson_value(cell(row, lens_column)),
                )
                for row in lesson_rows
            }

    seen: set[str] = set()
    for number, row in enumerate(wonder_rows, start=1):
        req_cell = cell(row, columns["escape req-id"])
        ids = REQ_ID.findall(req_cell)
        if len(ids) != 1:
            violations.append(
                wonder_violation(f"row {number} must name exactly one escape REQ-ID")
            )
            continue
        req_id = ids[0]
        if req_id in seen:
            violations.append(wonder_violation(f"duplicate Wonder row for {req_id}"))
        seen.add(req_id)
        if req_id not in escapes:
            violations.append(wonder_violation(f"row {number} names non-escaped {req_id}"))

        for name in (
            "unknown class",
            "interview-time observable signal",
            "lens",
            "store",
            "evidence",
        ):
            if not cell(row, columns[name]).strip():
                violations.append(wonder_violation(f"row {number} has blank {name}"))

        disposition = normalize_lesson_value(cell(row, columns["disposition"]))
        if disposition not in WONDER_DISPOSITIONS:
            violations.append(
                wonder_violation(
                    f"row {number} has invalid disposition "
                    f"{cell(row, columns['disposition'])!r}"
                )
            )
            continue
        if disposition == "not-routing/synthesis-loss":
            if escapes.get(req_id) != "synthesis-loss":
                violations.append(
                    wonder_violation(
                        f"{req_id} is not attributed synthesis-loss but is marked "
                        "not-routing/synthesis-loss"
                    )
                )
        elif disposition in {"new", "strengthened"}:
            lesson_key = (
                normalize_lesson_value(
                    cell(row, columns["interview-time observable signal"])
                ),
                normalize_lesson_value(cell(row, columns["lens"])),
            )
            if lesson_key not in lessons:
                violations.append(
                    wonder_violation(
                        f"{req_id} is {disposition} but Lessons Appended Or Updated "
                        "has no row with the same normalized signal and lens"
                    )
                )

    missing = sorted(set(escapes) - seen)
    if missing:
        violations.append(
            wonder_violation("escaped requirement(s) lack Wonder row(s): " + ", ".join(missing))
        )


def check_calibration(
    body: str | None,
    counts: dict[str, int],
    synthesis: int,
    violations: list[str],
) -> None:
    if body is None:
        return  # section-presence check already reported it
    table = first_table(body)
    if table is None:
        violations.append("Calibration Summary has no divergence-class count table")
    else:
        _, rows = table
        for token in DIVERGENCE_CLASSES:
            declared = next(
                (row for row in rows if cell(row, 0).lower().startswith(token)), None
            )
            if declared is None:
                violations.append(f"Calibration Summary is missing a count row for {token}")
                continue
            digits = re.search(r"\d+", cell(declared, 1))
            if digits is None or int(digits.group()) != counts[token]:
                violations.append(
                    f"Calibration Summary declares {token} = {cell(declared, 1)!r} "
                    f"but the Divergence Table counts {counts[token]}"
                )

    fulfilled = counts["fulfilled"]
    escaped = counts["escaped-requirement"]
    divergent = counts["divergent-implementation"]
    lowered = body.lower()
    for label in ("interview-discovery", "handoff-fidelity"):
        if label not in lowered:
            violations.append(f"Calibration Summary never states the {label} rate")
    if escaped and "weighted" not in lowered:
        violations.append(
            "Calibration Summary has escapes but no weighted rate beside the raw one"
        )

    denominator = fulfilled + escaped + divergent
    if denominator == 0:
        return
    stated = [float(match.group(1)) for match in PERCENT.finditer(body)]
    expected = {
        "interview-discovery": 100.0 * fulfilled / (fulfilled + (escaped - synthesis) + divergent),
        "handoff-fidelity": 100.0 * fulfilled / denominator,
    }
    for label, rate in expected.items():
        if not any(abs(value - rate) <= RATE_TOLERANCE for value in stated):
            violations.append(
                f"Calibration Summary states no percentage within {RATE_TOLERANCE} "
                f"of the recomputed {label} rate {rate:.1f}%"
            )


def load_bundle_lessons(bundle_path: Path) -> list[dict] | None:
    """The bundle's audit-start lessons snapshot (schema v3+), or None when the
    bundle is absent/old/unparseable - the caller then falls back to the live store."""
    if not bundle_path.is_file():
        return None
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    lessons = bundle.get("lessons")
    if not isinstance(lessons, dict):
        return None
    stores = lessons.get("stores")
    return stores if isinstance(stores, list) else None


def lessons_anchors(
    bundle_stores: list[dict] | None,
    lessons_paths: list[Path],
    violations: list[str],
) -> list[tuple[str, int]]:
    """(store-name, audit-start-active-count) pairs to enforce fire-tracking against.

    Prefer the bundle's audit-start snapshot: the run may empty the live store
    before the lint sees it (bulk absorption), so counting the live file would
    make the check pass vacuously - the app-5 blind spot. Fall back to the live
    file only when no snapshot exists, and say so.
    """
    if bundle_stores is not None:
        return [(s.get("name", ""), int(s.get("active_count", 0))) for s in bundle_stores]
    anchors: list[tuple[str, int]] = []
    for path in lessons_paths:
        try:
            anchors.append((path.name, len(lessons_store.parse_file(path).rows)))
        except typer.BadParameter as error:
            violations.append(f"lessons store {path} did not parse: {error}")
    if anchors:
        violations.append(
            "fire-tracking validated against the LIVE lessons store(s), not an "
            "audit-start snapshot - unreliable if this run mutated the store; pass "
            "--bundle (or run pack_evidence first) so the count is anchored to audit start"
        )
    return anchors


def check_fire_tracking(
    body: str | None,
    bundle_stores: list[dict] | None,
    lessons_paths: list[Path],
    violations: list[str],
) -> None:
    if bundle_stores is None and not lessons_paths:
        return
    anchors = lessons_anchors(bundle_stores, lessons_paths, violations)
    table = first_table(body) if body is not None else None
    for name, active_count in anchors:
        if active_count == 0:
            continue
        if table is None:
            violations.append(
                f"Lessons Fire-Tracking has no table but {name} had "
                f"{active_count} active row(s) at audit start to walk"
            )
            continue
        _, rows = table
        for index in range(1, active_count + 1):
            hit = any(
                whole_token(name, cell(row, 0)) and whole_token(str(index), cell(row, 1))
                for row in rows
            )
            if not hit:
                violations.append(
                    f"Lessons Fire-Tracking is missing a row for {name} "
                    f"active lesson #{index} - every lesson active at audit start gets a "
                    "fired/no-signal verdict, every run"
                )


@app.command()
def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Session dir with postmortem.md and handoff.md")
    ],
    lessons: Annotated[
        list[Path] | None,
        typer.Option(
            "--lessons",
            help="Lessons store to enforce fire-tracking against (repeatable). "
            "Used only as a fallback when the bundle carries no lessons snapshot.",
        ),
    ] = None,
    bundle: Annotated[
        Path | None,
        typer.Option(
            "--bundle",
            help="evidence_bundle.json holding the audit-start lessons snapshot; "
            f"default <session-dir>/{BUNDLE_FILENAME}. The snapshot is the reliable "
            "fire-tracking anchor (the live store may have been emptied this run).",
        ),
    ] = None,
    advisory: Annotated[
        bool, typer.Option(help="Report only; never exit non-zero.")
    ] = False,
) -> None:
    report_path = session_dir / "postmortem.md"
    handoff_path = session_dir / "handoff.md"
    for path, label in ((report_path, "postmortem.md"), (handoff_path, "handoff.md")):
        if not path.is_file():
            typer.echo(f"error: missing {label} at {path}", err=True)
            raise typer.Exit(2)

    report = report_path.read_text(encoding="utf-8")
    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))
    sections = split_sections(report)
    bundle_path = bundle or (session_dir / BUNDLE_FILENAME)
    from legacy_v3_report import is_legacy_v3_report

    legacy_v3 = is_legacy_v3_report(bundle_path, report)
    from postmortem_taxonomy import TaxonomyError, detect_report_schema

    try:
        report_schema = detect_report_schema(report)
    except TaxonomyError as error:
        typer.echo(f"postmortem_lint: error: {error}", err=True)
        raise typer.Exit(2) from error

    bundle_stores = load_bundle_lessons(bundle_path)

    violations: list[str] = []
    for key in REQUIRED_SECTIONS:
        if legacy_v3 and key in {"wonder generalization", "reward-hacking review"}:
            continue
        if section_body(sections, key) is None:
            violations.append(f"required section missing: a heading containing {key!r}")

    divergence_body = section_body(sections, "divergence table")
    if report_schema == 2:
        from postmortem_v2_lint import evaluate as evaluate_v2

        v2 = evaluate_v2(report, part1, bundle or (session_dir / BUNDLE_FILENAME))
        counts = v2.counts
        synthesis = v2.synthesis_count
        violations.extend(v2.violations)
    else:
        counts = dict.fromkeys(DIVERGENCE_CLASSES, 0)
        if divergence_body is not None:
            counts = check_divergence(divergence_body, part1, violations)
        synthesis = check_escapes(
            section_body(sections, "escaped requirements"),
            counts["escaped-requirement"],
            violations,
            require_intent=not legacy_v3,
        )
        if not legacy_v3:
            check_wonder(
                section_body(sections, "wonder generalization"),
                section_body(sections, "escaped requirements"),
                section_body(sections, "lessons appended"),
                violations,
            )
    if not legacy_v3:
        check_reward_hacking(
            section_body(sections, "reward-hacking review"),
            part1,
            divergence_body,
            violations,
        )
    check_calibration(
        section_body(sections, "calibration summary"), counts, synthesis, violations
    )
    check_fire_tracking(
        section_body(sections, "lessons fire-tracking"),
        bundle_stores,
        list(lessons or []),
        violations,
    )
    # Import at call time: verification_execution_lint reuses this module's
    # Markdown helpers, so a module-level import would create a circular import.
    from verification_execution_lint import EvaluationInputError, evaluate

    try:
        violations.extend(evaluate(session_dir))
    except EvaluationInputError as error:
        typer.echo(f"postmortem_lint: error: verification-execution: {error}", err=True)
        raise typer.Exit(2) from error

    if violations:
        typer.echo(f"postmortem_lint: {len(violations)} violation(s)")
        for note in violations:
            typer.echo(f"- {note}")
        if not advisory:
            raise typer.Exit(1)
    else:
        typer.echo(
            "postmortem_lint: ok - sections complete, divergence and reward-hacking "
            "rows well-formed, calibration and verification provenance match"
        )


if __name__ == "__main__":
    app()
