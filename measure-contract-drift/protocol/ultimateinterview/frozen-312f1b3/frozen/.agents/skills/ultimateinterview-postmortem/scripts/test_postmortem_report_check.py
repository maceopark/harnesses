from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).with_name("postmortem_report_check.py")
CONTRACT_DIGEST = "a" * 64


def _bundle(path: Path) -> Path:
    bundle = {
        "schema": "ultimateinterview.compiler-postmortem-evidence.v1",
        "contract_digest": CONTRACT_DIGEST,
        "ids": {
            "requirements": ["REQ-001"],
            "acceptances": ["ACC-001"],
            "verifications": ["VER-001"],
            "authorities": ["AUTH-001"],
        },
    }
    path.write_text(json.dumps(bundle), encoding="utf-8")
    return path


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _report(
    *,
    counts: str = "**Counts:** 1 contract requirements — 1 fulfilled, 0 escaped, 0 scope-drift, 0 divergent, 0 deferred, 0 unverifiable.",
    divergence_rows: list[list[str]] | None = None,
    verification_rows: list[list[str]] | None = None,
    proposal_rows: list[list[str]] | None = None,
    finding_rows: list[list[str]] | None = None,
    lesson_rows: list[list[str]] | None = None,
) -> str:
    divergence_rows = divergence_rows or [
        [
            "REQ-001",
            "Tasks are listed.",
            "fulfilled",
            "REQ-001 / ACC-001 / VER-001",
            "scoped diff",
            "VER-001 run",
            "no",
        ]
    ]
    verification_rows = verification_rows if verification_rows is not None else [
        [
            "VER-001",
            "Create alpha, then list tasks.",
            "run",
            "passed",
            "command output",
            "agrees",
        ]
    ]
    proposal_rows = proposal_rows if proposal_rows is not None else [
        [
            "No skill change recommended",
            "implementation/evaluator noncompliance",
            "Existing rule was sufficient",
            "No new general rule is needed",
            "Current audit rule",
        ]
    ]
    finding_rows = finding_rows or []
    lesson_rows = lesson_rows or []
    return "\n".join(
        [
            "# Ultimateinterview Postmortem",
            "",
            "postmortem_schema: 2",
            f"contract_digest: {CONTRACT_DIGEST}",
            "evaluator: independent-reviewer",
            "evaluated_at: 2026-07-14T12:00:00Z",
            "",
            "## Conclusion",
            "",
            "**Verdict:** The implementation fulfilled the sealed contract.",
            "",
            counts,
            "",
            "**Root causes:**",
            "",
            "1. No divergence identified.",
            "",
            "### Ultimateinterview improvement proposals",
            "",
            _table(
                [
                    "Proposal",
                    "Prevents",
                    "Rule to add or strengthen",
                    "Cross-domain reason",
                    "Compatible existing rule",
                ],
                proposal_rows,
            ),
            "",
            "## Implementation Evidence",
            "",
            _table(
                ["Source", "Scope", "Digest / revision", "Notes"],
                [
                    ["Build Contract", "session", CONTRACT_DIGEST, "sole normative source"],
                    ["Repository evidence", "scoped diff", "diff hash", "contract scope"],
                    ["Verification", "VER-001", "passed", "direct evidence"],
                    ["Implementation return", "session", CONTRACT_DIGEST, "self-report only"],
                    ["Decision log", "session", "absent", "evidence only"],
                ],
            ),
            "",
            "## Divergence Table",
            "",
            _table(
                [
                    "ID",
                    "Behavior",
                    "Class",
                    "Contract mapping",
                    "Implementation evidence",
                    "Verification evidence",
                    "Owner decision needed?",
                ],
                divergence_rows,
            ),
            "",
            "## Finding Details",
            "",
            _table(
                [
                    "ID",
                    "Behavior",
                    "Class / failure mode",
                    "Structure / owning frame",
                    "Intent attribution",
                    "Evidence",
                    "Owner action",
                ],
                finding_rows,
            ),
            "",
            "## Verification Execution",
            "",
            _table(
                ["VER-ID", "Procedure", "Direct execution", "Result", "Evidence", "Return agreement"],
                verification_rows,
            ),
            "",
            "## Lessons",
            "",
            _table(
                ["Store", "Signal", "Action", "Pre-state", "Post-state", "Evidence"],
                lesson_rows,
            ),
            "",
            "## Process Gaps and Missing Evidence",
            "",
            _table(
                ["Item", "Evidence", "Authority impact", "Required action"],
                [],
            ),
            "",
            "## Resolution Addendum",
            "",
            "No owner response was required.",
            "",
        ]
    )


def _run(report: Path, bundle: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(report), "--bundle", str(bundle), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def test_report_checker_accepts_valid_report(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    report.write_text(_report(), encoding="utf-8")

    result = _run(report, bundle)

    assert result.returncode == 0, result.stderr


def test_report_checker_rejects_count_mismatch(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    report.write_text(
        _report(
            counts="**Counts:** 1 contract requirements — 0 fulfilled, 0 escaped, 0 scope-drift, 0 divergent, 0 deferred, 0 unverifiable."
        ),
        encoding="utf-8",
    )

    result = _run(report, bundle)

    assert result.returncode == 1
    assert "fulfilled count does not match" in result.stderr


def test_report_checker_rejects_duplicate_escape(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    report.write_text(
        _report(
            counts="**Counts:** 1 contract requirements — 1 fulfilled, 2 escaped, 0 scope-drift, 0 divergent, 0 deferred, 0 unverifiable.",
            divergence_rows=[
                ["REQ-001", "Tasks are listed.", "fulfilled", "REQ-001", "diff", "run", "no"],
                ["ESC-001", "Fallback behavior.", "escaped-requirement", "absent", "diff", "run", "yes"],
                ["ESC-001", "Another fallback.", "escaped-requirement", "absent", "diff", "run", "yes"],
            ],
        ),
        encoding="utf-8",
    )

    result = _run(report, bundle)

    assert result.returncode == 1
    assert "duplicate escape row ESC-001" in result.stderr


def test_report_checker_rejects_missing_verification(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    report.write_text(_report(verification_rows=[]), encoding="utf-8")

    result = _run(report, bundle)

    assert result.returncode == 1
    assert "missing rows: VER-001" in result.stderr


def test_report_checker_rejects_four_proposals(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    proposal = ["Rule", "ESC-001", "Add check", "Reusable", "Existing rule"]
    report.write_text(_report(proposal_rows=[proposal, proposal, proposal, proposal]), encoding="utf-8")

    result = _run(report, bundle)

    assert result.returncode == 1
    assert "more than three" in result.stderr


def test_report_checker_rejects_invalid_divergence_class(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    report = tmp_path / "postmortem.md"
    report.write_text(
        _report(
            divergence_rows=[
                ["REQ-001", "Tasks are listed.", "invented-class", "REQ-001", "diff", "run", "no"]
            ]
        ),
        encoding="utf-8",
    )

    result = _run(report, bundle)

    assert result.returncode == 1
    assert "invalid requirement class" in result.stderr


def test_report_checker_rejects_lesson_claim_without_delta(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle.json")
    lessons = tmp_path / "lessons.md"
    lessons.write_text("# Lessons\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(lessons.read_bytes()).hexdigest()
    report = tmp_path / "postmortem.md"
    report.write_text(
        _report(
            lesson_rows=[
                ["repo", "scheduled path", "appended", digest, digest, "audit evidence"]
            ]
        ),
        encoding="utf-8",
    )

    result = _run(report, bundle, "--lesson-store", "repo", str(lessons), str(lessons))

    assert result.returncode == 1
    assert "claims appended without a lesson-state delta" in result.stderr
