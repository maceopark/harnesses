#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///
# (pydantic/rich are pulled in by the shared handoff_coverage/postmortem_lint imports.)

# ─── How to run ───
#      uv run scripts/audit_scan.py <session-dir> \
#        [--diff-file <patch>] [--bundle <evidence_bundle.json>] \
#        [--decisions <decisions.jsonl>] [--tests <dir-or-file>] \
#        [--repo-root <dir>] [--strict]
# ──────────────────
#
# Pre-classification audit scanner for the postmortem (advisory).
#
# Six deterministic scans the three-arm benchmark (claudeplan / codexplan /
# app-5) showed the manual audit does by eye - and sometimes misses:
#
#   A. REQ->test coverage   - which Part-1 REQ ids have a test that names them.
#      Mechanical only if the executor followed the test-naming contract
#      (`test_reqNNN_*` or a `REQ-NNN` reference); low coverage is itself a
#      signal that the contract was not honored. Replaces the hand-inventoried
#      "unasserted REQ" list (app-5 postmortem section C3).
#   B. decision-shape coverage - diff hunks that look like a forced decision
#      (runtime version floor, canonicalization, dependency pin, exit-code
#      taxonomy) checked against decisions.jsonl. app-5's version floor and
#      control-char definition were real decisions that never reached the log
#      (escape E2); this surfaces the same shape.
#   C. scope-creep          - non-goal keywords from Part 1 appearing in ADDED
#      diff lines (a forbidden capability that got built anyway). codexplan's
#      Must-NOT block is the model; this is the negative check on it.
#   D. promised-artifact existence - files/paths the spec names (Target Surface,
#      Verification Commands) that do not exist in the tree. codexplan promised
#      a test file and evidence paths that never materialized.
#   E. reward-hacking support - test/doc-only changed paths or fulfilled-REQ
#      support mappings. A human still determines whether this is gaming.
#   F. cooperation-free intent signals - deterministic signal presence for each
#      Part-1 REQ plus a session-level decision-shape list. It never assigns an
#      intent or class; a REQ-named test is never an owned intent signal.
#
# Every section is a CANDIDATE list for the auditor to classify, never a verdict:
# the detectors are keyword/pattern heuristics with false positives, so the tool
# is advisory (exit 0) by default; --strict exits 1 when an existing finding
# section has hits. It never writes files and never classifies - classification
# stays with the postmortem author.

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import Annotated, Final

import typer
from pydantic import ValidationError

# Reuse the sibling ultimateinterview + postmortem_lint helpers.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_coverage import extract_part1  # noqa: E402
from pack_evidence import DecisionRecord  # noqa: E402
from postmortem_lint import first_table, section_body, split_sections  # noqa: E402
from postmortem_bundle import JsonValue  # noqa: E402
from verification_contract import (  # noqa: E402
    CapturedOutput,
    captured_output_matches,
    parse_verification_rows,
)

REQ_ID: Final[re.Pattern[str]] = re.compile(r"REQ-\d+")
BUNDLE_FILENAME: Final[str] = "evidence_bundle.json"

# --- section B: decision-shaped diff patterns ---
# Each (category, regex, decisions-keyword) - a hit in an added diff line whose
# category keyword is absent from decisions.jsonl is a candidate unlogged decision.
DECISION_SHAPES: Final[tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...]] = (
    (
        "runtime version floor",
        re.compile(
            r"requires-python|python_requires|rust-version|\bedition\s*=|"
            r'"node"\s*:|"engines"|go\s+1\.\d|--target|lang(?:uage)?[-_ ]version',
            re.IGNORECASE,
        ),
        ("version", "requires-python", "python_requires", "runtime", "floor", "3.1", "engine"),
    ),
    (
        "canonicalization / normalization",
        re.compile(
            r"str\(int\(|isdecimal|isdigit\(|fromisoformat|casefold|"
            r"canonical|normali[sz]e|\.strip\(\)|unicodedata",
            re.IGNORECASE,
        ),
        ("canonical", "normali", "strip", "leading zero", "coerce", "isdecimal", "isoformat"),
    ),
    (
        "exit-code / error taxonomy",
        re.compile(
            r"sys\.exit\(|raise\s+\w*Error|EXIT_[A-Z]+|return\s+[1-9]\b|exit\s+[1-9]\b",
            re.IGNORECASE,
        ),
        ("exit", "error", "taxonomy", "exit code", "exit-code", "status code"),
    ),
    (
        "dependency pin",
        re.compile(r"(?:>=|==|~=|\^)\s*\d+\.\d", re.IGNORECASE),
        ("depend", "pin", "requirement", "library", "package"),
    ),
)

# Words never counted as a non-goal capability keyword (section C).
SCOPE_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "no", "not", "nor", "and", "or", "the", "a", "an", "of", "to", "for",
        "with", "without", "any", "all", "this", "that", "these", "those", "will",
        "does", "do", "support", "reuse", "consult", "prior", "existing", "other",
        "such", "add", "adds", "adding", "use", "using", "via", "from", "into",
        "app", "apps", "cli", "spec", "specs", "code", "implementation", "behavior",
        "todo", "tasks", "task", "them", "their", "its", "it", "as", "on", "in",
        "new", "same", "than", "only", "must", "should", "shall", "server",
    }
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def load_diff(diff_file: Path | None, bundle: Path | None) -> tuple[str, str]:
    """Return (diff_text, source-label). Empty text when no diff is available."""
    if diff_file is not None:
        if not diff_file.is_file():
            raise typer.BadParameter(f"--diff-file {diff_file} not found")
        return diff_file.read_text(encoding="utf-8"), str(diff_file)
    if bundle is not None and bundle.is_file():
        try:
            data = json.loads(bundle.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "", f"{bundle} (unreadable)"
        diff = data.get("diff")
        if isinstance(diff, dict) and isinstance(diff.get("text"), str):
            return diff["text"], diff.get("source", str(bundle))
    return "", "none"


def added_lines(diff_text: str) -> list[tuple[str, str]]:
    """(current-file, added-line-content) for every `+` line that is not a `+++` header."""
    out: list[tuple[str, str]] = []
    current = "?"
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            current = line[4:].strip()
            if current.startswith("b/"):
                current = current[2:]
            continue
        if line.startswith("+") and not line.startswith("+++"):
            out.append((current, line[1:]))
    return out
_TEST_PATH_COMPONENTS: Final[frozenset[str]] = frozenset({"test", "tests", "spec", "specs"})
_SUPPORT_PATH: Final[re.Pattern[str]] = re.compile(
    r"(?:(?:[A-Za-z]:)?[\\/]|(?:\.\.?[\\/]))?"
    r"(?:[A-Za-z0-9_.-]+[\\/])*[A-Za-z0-9_-]+\.[A-Za-z0-9]{1,10}"
)
_DOC_BASENAME: Final[re.Pattern[str]] = re.compile(
    r"^(?:readme|changelog|license)", re.IGNORECASE
)


def _normalized_changed_path(path: str) -> str | None:
    """Return a safe, repo-relative slash-separated path, or None."""
    candidate = path.strip().replace("\\", "/")
    if candidate in {"/dev/null", ""}:
        return None
    if candidate.startswith(("a/", "b/")):
        candidate = candidate[2:]
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:/", candidate):
        return None
    components = candidate.split("/")
    if any(component in {"", ".."} for component in components):
        return None
    return "/".join(component for component in components if component != ".")


def classify_changed_path(path: str) -> str:
    """Classify a safe changed path as test, doc, or production."""
    normalized = _normalized_changed_path(path)
    if normalized is None:
        return "production"
    components = [component.lower() for component in normalized.split("/")]
    basename = components[-1]
    if (
        any(component in _TEST_PATH_COMPONENTS for component in components)
        or re.match(r"^test_[^.]+\.[^.]+$", basename) is not None
        or re.match(r"^.+_test\.[^.]+$", basename) is not None
        or ".spec." in basename
        or ".test." in basename
    ):
        return "test"
    if (
        "docs" in components
        or _DOC_BASENAME.match(basename) is not None
        or basename.endswith((".md", ".rst"))
    ):
        return "doc"
    return "production"


def changed_paths(diff_text: str) -> set[str]:
    """Return safe repo-relative paths named by unified-diff file headers."""
    paths: set[str] = set()
    for line in diff_text.splitlines():
        candidates: list[str] = []
        if line.startswith("diff --git "):
            try:
                parts = shlex.split(line)
            except ValueError:
                continue
            candidates = parts[2:4]
        elif line.startswith(("--- ", "+++ ")):
            candidates = [line[4:].split("\t", 1)[0].strip()]
        for candidate in candidates:
            normalized = _normalized_changed_path(candidate)
            if normalized is not None:
                paths.add(normalized)
    return paths


def _support_paths(value: str) -> list[str] | None:
    """Extract safe path references from a Divergence Table support cell."""
    references = re.findall(r"`([^`]+)`", value)
    if references:
        raw_paths = [
            reference.strip()
            for references_cell in references
            for reference in re.split(r"[,;\n]", references_cell)
            if reference.strip()
        ]
    else:
        raw_paths = [match.group() for match in _SUPPORT_PATH.finditer(value)]
    paths: list[str] = []
    for raw_path in raw_paths:
        path = re.sub(r":\d+(?:-\d+)?$", "", raw_path)
        normalized = _normalized_changed_path(path)
        if (
            normalized is None
            or any(character.isspace() for character in normalized)
        ):
            return None
        if normalized not in paths:
            paths.append(normalized)
    return paths or None


def _fulfilled_support_mapping(
    postmortem_text: str | None,
) -> list[tuple[str, list[str] | None]] | None:
    if postmortem_text is None:
        return None
    body = section_body(split_sections(postmortem_text), "divergence table")
    table = first_table(body) if body is not None else None
    if table is None:
        return None
    headers, rows = table
    class_column = next(
        (index for index, header in enumerate(headers) if "class" in header.lower()),
        None,
    )
    support_column = next(
        (
            index
            for index, header in enumerate(headers)
            if "supporting diff paths" in header.lower()
        ),
        None,
    )
    if class_column is None or support_column is None:
        return None
    mapping: list[tuple[str, list[str] | None]] = []
    for number, row in enumerate(rows, start=1):
        class_value = row[class_column] if class_column < len(row) else ""
        if re.match(r"^[*_`~\s]*fulfilled\b", class_value, re.IGNORECASE) is None:
            continue
        req_ids = REQ_ID.findall(row[0] if row else "")
        label = ", ".join(req_ids) if req_ids else f"row {number}"
        support_value = row[support_column] if support_column < len(row) else ""
        mapping.append((label, _support_paths(support_value)))
    return mapping


def scan_test_doc_only_support(
    part1: str, diff_paths: set[str], postmortem_text: str | None
) -> tuple[list[str], list[str]]:
    """Return reward-hacking candidates and separately insufficient mappings."""
    mapping = _fulfilled_support_mapping(postmortem_text)
    if mapping is None:
        if diff_paths and all(
            classify_changed_path(path) in {"test", "doc"} for path in diff_paths
        ):
            req_ids = sorted(set(REQ_ID.findall(part1)), key=lambda req: int(req.split("-")[1]))
            return [
                "global candidate: every changed diff path is test/doc-only; "
                f"Part-1 REQs requiring human review: {', '.join(req_ids) or 'none'}"
            ], []
        return [], []

    candidates: list[str] = []
    insufficient: list[str] = []
    for label, support_paths in mapping:
        if not support_paths:
            insufficient.append(
                f"{label}: fulfilled row has insufficient supporting diff-path mapping "
                "(not evidence of verification gaming)"
            )
            continue
        categories = {classify_changed_path(path) for path in support_paths}
        if categories <= {"test", "doc"}:
            candidates.append(
                f"{label}: fulfilled row cites only test/doc supporting paths "
                f"({', '.join(support_paths)}) - candidate, not a verdict"
            )
    return candidates, insufficient


def test_reference_tokens(req_id: str) -> tuple[str, ...]:
    """Forms a REQ-001 reference can take in a test name/body."""
    number = req_id.split("-", 1)[1]
    return (req_id, req_id.replace("-", "_"), req_id.replace("-", "").lower(),
            f"req{number}", f"req_{number}", f"req-{number}")


def scan_req_tests(part1: str, tests_text: str) -> tuple[list[str], list[str]]:
    req_ids = sorted(set(REQ_ID.findall(part1)), key=lambda s: int(s.split("-")[1]))
    lowered = tests_text.lower()
    mapped, unmapped = [], []
    for req in req_ids:
        if any(token.lower() in lowered for token in test_reference_tokens(req)):
            mapped.append(req)
        else:
            unmapped.append(req)
    return mapped, unmapped
def _part1_req_ids(part1: str) -> list[str]:
    return sorted(set(REQ_ID.findall(part1)), key=lambda req: int(req.split("-")[1]))


def _req_cited(req_id: str, text: str) -> bool:
    return re.search(
        rf"(?<![0-9A-Za-z_-]){re.escape(req_id)}(?![0-9A-Za-z_-])",
        text,
        re.IGNORECASE,
    ) is not None


def _bundle_data(path: Path) -> dict[str, JsonValue]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _owned_decision_refs(
    decisions_text: str, bundle_data: dict[str, JsonValue]
) -> list[tuple[str, DecisionRecord]]:
    """Validated decision records with a stable human-reference label."""
    records: list[tuple[str, DecisionRecord]] = []
    for number, line in enumerate(decisions_text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append((f"decision#{number}", DecisionRecord.model_validate_json(line)))
        except ValidationError:
            continue
    bundled = bundle_data.get("decisions")
    if isinstance(bundled, list):
        for number, raw in enumerate(bundled, start=1):
            try:
                record = DecisionRecord.model_validate(raw)
            except ValidationError:
                continue
            if not any(existing == record for _, existing in records):
                records.append((f"decision#{number}", record))
    return records


def _owned_capture_refs(
    part1: str, bundle_data: dict[str, JsonValue]
) -> dict[str, list[str]]:
    """Return REQ ids explicitly named by a provenance-matched capture check."""
    version = bundle_data.get("schema_version")
    artifacts = bundle_data.get("artifacts")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version < 4
        or not isinstance(artifacts, dict)
    ):
        return {}
    projections = artifacts.get("captured_outputs")
    if not isinstance(projections, list):
        return {}

    refs: dict[str, list[str]] = {}
    verification_rows = parse_verification_rows(part1)
    for projection in projections:
        if not isinstance(projection, dict):
            continue
        artifact_id = projection.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            continue
        envelope = {
            key: value
            for key, value in projection.items()
            if key not in {"artifact_id", "file_sha256"}
        }
        try:
            # Validate through the JSON path: projections serialize tuple fields
            # (effective_heads) as arrays, and CapturedOutput is strict, so
            # model_validate on the parsed dict would reject the list. Round-trip
            # via JSON so the array coerces back to the tuple the model requires.
            capture = CapturedOutput.model_validate_json(json.dumps(envelope))
        except ValidationError:
            continue
        for row in verification_rows:
            if not captured_output_matches(row, capture):
                continue
            for req_id in _part1_req_ids(part1):
                if _req_cited(req_id, row.check):
                    refs.setdefault(req_id, []).append(f"capture:{artifact_id.strip()}")
    return refs


def scan_intent_signals(
    part1: str,
    tests_text: str,
    decisions_text: str,
    bundle_data: dict[str, JsonValue],
) -> list[str]:
    """Presence-only, cooperation-free signals; no intent classification."""
    named_tests, _ = scan_req_tests(part1, tests_text)
    named_test_ids = set(named_tests)
    decision_refs = _owned_decision_refs(decisions_text, bundle_data)
    capture_refs = _owned_capture_refs(part1, bundle_data)
    lines: list[str] = []
    for req_id in _part1_req_ids(part1):
        owned_refs = [
            ref
            for ref, record in decision_refs
            if record.spec_citation is not None and _req_cited(req_id, record.spec_citation)
        ]
        owned_refs.extend(capture_refs.get(req_id, []))
        test_present = req_id in named_test_ids
        owned_present = bool(owned_refs)
        lines.append(
            f"{req_id}: req_named_test={str(test_present).lower()} "
            f"(provenance: {'tests source' if test_present else 'none'}); "
            f"owned_intent_signal={str(owned_present).lower()} "
            f"(provenance: {', '.join(owned_refs) if owned_refs else 'none'})"
        )
    return lines


def unlogged_decision_shape_hits(
    adds: list[tuple[str, str]], decisions_text: str
) -> list[tuple[str, list[tuple[str, str]], tuple[str, ...]]]:
    """Decision-shape hits that section B found absent from the decision log."""
    log = decisions_text.lower()
    findings: list[tuple[str, list[tuple[str, str]], tuple[str, ...]]] = []
    for category, pattern, keywords in DECISION_SHAPES:
        hits = [(fname, line.strip()) for fname, line in adds if pattern.search(line)]
        if hits and not any(keyword in log for keyword in keywords):
            findings.append((category, hits, keywords))
    return findings


def decision_shape_hunk_count(
    adds: list[tuple[str, str]], decisions_text: str
) -> int:
    return len(
        {
            hit
            for _, hits, _ in unlogged_decision_shape_hits(adds, decisions_text)
            for hit in hits
        }
    )


def scan_decision_shapes(
    adds: list[tuple[str, str]], decisions_text: str
) -> list[str]:
    findings: list[str] = []
    for category, hits, keywords in unlogged_decision_shape_hits(adds, decisions_text):
        sample_file, sample_line = hits[0]
        findings.append(
            f"{category}: {len(hits)} added line(s) look like this decision "
            f"(e.g. {sample_file}: {sample_line[:70]!r}) but decisions.jsonl mentions none of "
            f"{list(keywords)[:3]}... - confirm it was a forced choice and log it, or dismiss"
        )
    return findings


def non_goal_keywords(part1: str) -> list[str]:
    sections = split_sections(part1)
    body = section_body(sections, "out of scope") or section_body(sections, "non-goal")
    if not body:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z/-]{2,}", body.lower())
    seen: list[str] = []
    for word in words:
        token = word.strip("/-")
        if token and token not in SCOPE_STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def _stem(word: str) -> str:
    """Light morphological stem so a non-goal ('priorities') matches its code
    form ('priority'). English plural rules only; recall over precision (advisory)."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def scan_scope_creep(part1: str, adds: list[tuple[str, str]]) -> list[str]:
    keywords = non_goal_keywords(part1)
    findings: list[str] = []
    for keyword in keywords:
        stem = _stem(keyword)
        if len(stem) < 3:
            continue
        # Prefix match at a word boundary so singular/plural/verb forms all hit.
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(stem)}[A-Za-z]*", re.IGNORECASE)
        hits = [(fname, line.strip()) for fname, line in adds if pattern.search(line)]
        # Skip pure test/doc/comment noise-heavy hits by requiring a code-ish line.
        code_hits = [(f, ln) for f, ln in hits if not f.endswith((".md", ".txt"))]
        if code_hits:
            sample_file, sample_line = code_hits[0]
            findings.append(
                f"non-goal {keyword!r} appears in {len(code_hits)} added code line(s) "
                f"(e.g. {sample_file}: {sample_line[:70]!r}) - confirm the forbidden capability "
                "was not built"
            )
    return findings


PATHISH: Final[re.Pattern[str]] = re.compile(r"[\w./-]+\.[A-Za-z0-9]{1,6}")


def promised_paths(part1: str) -> list[str]:
    sections = split_sections(part1)
    paths: list[str] = []
    for name in ("target surface", "verification"):
        body = section_body(sections, name)
        if not body:
            continue
        table = first_table(body)
        cells = (
            [cell for _headers, rows in [table] for row in rows for cell in row]
            if table
            else [body]
        )
        for cell in cells:
            for token in PATHISH.findall(cell.replace("`", " ")):
                token = token.strip(".,()`\"' ")
                # A committed deliverable, not a runtime/observation path: has a
                # slash or a source/doc suffix, and is NOT an absolute path, a
                # temp/home path, or a shell-interpolated one (`/tmp/...`,
                # `$tmp/store.json`, `~/.todo.json` are runtime artifacts a user
                # touches, not files the spec promises to ship).
                is_runtime = (
                    token.startswith(("/", "~"))
                    or "$" in token
                    or "tmp" in token.lower()
                )
                looks_deliverable = "/" in token or token.endswith(
                    (".py", ".toml", ".md", ".json", ".sh", ".js", ".ts", ".cfg", ".txt")
                )
                if looks_deliverable and not is_runtime and token not in paths:
                    paths.append(token)
    return paths


def scan_artifacts(part1: str, repo_root: Path) -> list[str]:
    findings: list[str] = []
    for rel in promised_paths(part1):
        candidate = (repo_root / rel).resolve()
        # Treat directory-shaped targets (trailing slash or no suffix) leniently.
        if not candidate.exists() and not list(repo_root.glob(f"**/{Path(rel).name}"))[:1]:
            findings.append(f"promised path not found in tree: {rel}")
    return findings


@app.command()
def main(
    session_dir: Annotated[Path, typer.Argument(help="Session dir with handoff.md")],
    diff_file: Annotated[Path | None, typer.Option("--diff-file", help="Unified diff to scan")] = None,
    bundle: Annotated[
        Path | None,
        typer.Option("--bundle", help=f"evidence_bundle.json (default <session-dir>/{BUNDLE_FILENAME}); its diff.text is used when --diff-file is absent"),
    ] = None,
    decisions: Annotated[
        Path | None, typer.Option("--decisions", help="decisions.jsonl (default <session-dir>/decisions.jsonl)")
    ] = None,
    tests: Annotated[
        Path | None,
        typer.Option("--tests", help="Test file or dir to scan for REQ references; falls back to the diff text"),
    ] = None,
    repo_root: Annotated[
        Path | None, typer.Option("--repo-root", help="Repo root for artifact existence (default <session-dir>/../..)")
    ] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Exit 1 when any section has findings.")] = False,
) -> None:
    handoff_path = session_dir / "handoff.md"
    if not handoff_path.is_file():
        typer.echo(f"error: missing handoff.md at {handoff_path}", err=True)
        raise typer.Exit(2)
    part1 = extract_part1(handoff_path.read_text(encoding="utf-8"))

    resolved_bundle = bundle or (session_dir / BUNDLE_FILENAME)
    diff_text, diff_source = load_diff(diff_file, resolved_bundle)
    adds = added_lines(diff_text)
    diff_paths = changed_paths(diff_text)

    decisions_path = decisions or (session_dir / "decisions.jsonl")
    decisions_text = decisions_path.read_text(encoding="utf-8") if decisions_path.is_file() else ""

    if tests is not None and tests.exists():
        if tests.is_dir():
            tests_text = "\n".join(
                p.read_text(encoding="utf-8", errors="replace")
                for p in tests.rglob("*.py")
            )
        else:
            tests_text = tests.read_text(encoding="utf-8", errors="replace")
        tests_source = str(tests)
    else:
        tests_text = diff_text
        tests_source = f"diff ({diff_source})"

    resolved_root = repo_root or session_dir.resolve().parents[1]

    mapped, unmapped = scan_req_tests(part1, tests_text)
    decision_findings = scan_decision_shapes(adds, decisions_text) if diff_text else []
    decision_hunk_count = decision_shape_hunk_count(adds, decisions_text) if diff_text else 0
    creep_findings = scan_scope_creep(part1, adds) if diff_text else []
    artifact_findings = scan_artifacts(part1, resolved_root)
    postmortem_path = session_dir / "postmortem.md"
    postmortem_text = (
        postmortem_path.read_text(encoding="utf-8") if postmortem_path.is_file() else None
    )
    support_candidates, insufficient_support = scan_test_doc_only_support(
        part1, diff_paths, postmortem_text
    )
    intent_signal_lines = scan_intent_signals(
        part1, tests_text, decisions_text, _bundle_data(resolved_bundle)
    )
    from audit_open_world import candidates as open_world_candidates

    open_candidates = open_world_candidates(
        frozenset(
            path for path in diff_paths if classify_changed_path(path) == "production"
        ),
        frozenset(promised_paths(part1)),
        resolved_bundle,
    )

    typer.echo("## Postmortem Audit Scan (advisory)\n")

    typer.echo(f"### A. REQ -> test coverage  (source: {tests_source})")
    typer.echo(f"- REQ ids in Part 1: {len(mapped) + len(unmapped)}; referenced by a test: {len(mapped)}")
    if unmapped:
        typer.echo(f"- unmapped (no test names/references them): {', '.join(unmapped)}")
        typer.echo(
            "  Either the acceptance test does not follow the `test_reqNNN_*` / `REQ-NNN` "
            "naming contract, or the REQ is unasserted - confirm coverage in the divergence walk."
        )
    else:
        typer.echo("- req_test_ok: yes")

    typer.echo(f"\n### B. decision-shape coverage  (diff: {diff_source})")
    if not diff_text:
        typer.echo("- no diff/bundle available; skipped")
    elif decision_findings:
        for note in decision_findings:
            typer.echo(f"- {note}")
        typer.echo(
            f"- execution_process_gap candidate: {decision_hunk_count} decision-shaped "
            "hunk(s) not logged in decisions.jsonl (session-level advisory only)"
        )
    else:
        typer.echo("- decisions_ok: yes (no decision-shaped diff hunk is missing from the log)")

    typer.echo(f"\n### C. scope-creep vs non-goals  (diff: {diff_source})")
    if not diff_text:
        typer.echo("- no diff/bundle available; skipped")
    elif creep_findings:
        for note in creep_findings:
            typer.echo(f"- {note}")
    else:
        typer.echo("- scope_ok: yes (no non-goal keyword appears in added code)")

    typer.echo(f"\n### D. promised-artifact existence  (repo root: {resolved_root})")
    if artifact_findings:
        for note in artifact_findings:
            typer.echo(f"- {note}")
    else:
        typer.echo("- artifacts_ok: yes (every spec-named path exists)")
    typer.echo(f"\n### E. reward-hacking support candidates  (diff: {diff_source})")
    if support_candidates:
        for note in support_candidates:
            typer.echo(f"- {note}")
    else:
        typer.echo("- no test/doc-only support candidate detected")
    for note in insufficient_support:
        typer.echo(f"- insufficient mapping: {note}")
    typer.echo("\n### F. cooperation-free intent signals (advisory)")
    if decision_findings:
        for note in decision_findings:
            typer.echo(
                "- decision_shape_present=true "
                f"(provenance: section B: {note}; session-level only because "
                "diff-to-REQ association is not reliably deterministic)"
            )
    else:
        typer.echo(
            "- decision_shape_present=false "
            "(provenance: section B; no unlogged decision-shaped hunk; "
            "session-level only because diff-to-REQ association is not reliably deterministic)"
        )
    for note in intent_signal_lines:
        typer.echo(f"- {note}")
    typer.echo(
        "- Signal presence only: no signal assigns an intent or a postmortem class; "
        "req_named_test never lifts the run-blind floor."
    )
    typer.echo("\n### G. open-world candidates (advisory only)")
    if open_candidates:
        for note in open_candidates:
            typer.echo(f"- {note}")
    else:
        typer.echo("- no negative-space, ontology, runtime-only, or evidence-missing signal detected")
    typer.echo("- Candidate generation never classifies a row or assigns no-owner.")


    total = (
        len(unmapped)
        + len(decision_findings)
        + len(creep_findings)
        + len(artifact_findings)
        + len(support_candidates)
        + len(insufficient_support)
    )
    typer.echo(f"\n- findings: {total} (advisory - classify each in the postmortem, do not auto-fail)")
    if total and strict:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
