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
# Four deterministic scans the three-arm benchmark (claudeplan / codexplan /
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
#
# Every section is a CANDIDATE list for the auditor to classify, never a verdict:
# the detectors are keyword/pattern heuristics with false positives, so the tool
# is advisory (exit 0) by default; --strict exits 1 when any section has hits.
# It never writes files and never classifies - classification stays with the
# postmortem author.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Annotated, Final

import typer

# Reuse the sibling ultimateinterview + postmortem_lint helpers.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "ultimateinterview" / "scripts")
)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from handoff_coverage import extract_part1  # noqa: E402
from postmortem_lint import first_table, section_body, split_sections  # noqa: E402

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


def scan_decision_shapes(
    adds: list[tuple[str, str]], decisions_text: str
) -> list[str]:
    log = decisions_text.lower()
    findings: list[str] = []
    for category, pattern, keywords in DECISION_SHAPES:
        hits = [(fname, line.strip()) for fname, line in adds if pattern.search(line)]
        if not hits:
            continue
        logged = any(keyword in log for keyword in keywords)
        if logged:
            continue
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
    creep_findings = scan_scope_creep(part1, adds) if diff_text else []
    artifact_findings = scan_artifacts(part1, resolved_root)

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

    total = len(unmapped) + len(decision_findings) + len(creep_findings) + len(artifact_findings)
    typer.echo(f"\n- findings: {total} (advisory - classify each in the postmortem, do not auto-fail)")
    if total and strict:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
