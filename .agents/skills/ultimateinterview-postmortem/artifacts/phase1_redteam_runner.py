from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SKILL = REPO / ".agents/skills/ultimateinterview-postmortem"
SCRIPTS = SKILL / "scripts"
ARTIFACTS = SKILL / "artifacts"
SCRATCH = Path(tempfile.mkdtemp(prefix="phase1-redteam-", dir=ARTIFACTS))
PREFIX = [
    "uv", "run", "--python", "3.13", "--with", "pytest", "--with", "typer",
    "--with", "pydantic", "--with", "rich", "python",
]
COLUMNS = "Spec row | Check | Kind | Execution | Result | Captured artifact | Observed effect"
DIV_CLASSES = ("fulfilled", "escaped-requirement", "scope-drift", "divergent-implementation", "deferred-outcome")


def exact_command(argv: list[str]) -> str:
    return shlex.join(argv)


def run(argv: list[str]) -> dict[str, object]:
    result = subprocess.run(argv, cwd=REPO, text=True, capture_output=True, check=False)
    output = (result.stdout + result.stderr).strip()
    return {
        "command": exact_command(argv),
        "exitCode": result.returncode,
        "outputSnippet": output[:1400],
    }


def digest(command: str) -> str:
    return hashlib.sha256(" ".join(command.split()).encode()).hexdigest()


def capture(**changes: object) -> dict[str, object]:
    command = "python -m pytest"
    record: dict[str, object] = {
        "artifact_id": "capture-1",
        "file_sha256": "f" * 64,
        "marker": "CAPTURED-OUTPUT",
        "spec_row_number": 1,
        "check": "Exact capture check",
        "kind": "test",
        "exact_command": command,
        "command_digest": digest(command),
        "effective_heads": ["python"],
        "cwd": "/repo",
        "started_at": "2026-07-10T00:00:00Z",
        "ended_at": "2026-07-10T00:00:01Z",
        "spawned": True,
        "timed_out": False,
        "timeout_seconds": 60,
        "exit_code": 0,
        "stdout": "1 passed\n",
        "stderr": "",
        "stdout_full_bytes": 9,
        "stderr_full_bytes": 0,
        "stdout_sha256": hashlib.sha256(b"1 passed\n").hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
    }
    record.update(changes)
    return record


def handoff() -> str:
    return """# Part 1 - Build Contract

| ID | Requirement |
| --- | --- |
| REQ-001 | Capture provenance must be exact. |

## Verification Commands

| Check | Kind | Command / action |
| --- | --- | --- |
| Exact capture check | test | python -m pytest |

# Part 2 - Audit Trail
"""


def verification_report(*, execution: str = "exact", result: str = "pass", artifact: str = "capture-1") -> str:
    return f"""# Postmortem

## Verification Execution

| {COLUMNS} |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Exact capture check | test | {execution} | {result} | {artifact} | pytest passed |
"""


def full_report(*, gaming: bool = False) -> str:
    disposition = "confirmed-gaming" if gaming else "cleared"
    mock = "yes" if gaming else "no"
    return f"""# Postmortem

## Implementation Evidence

| Source | Reference | Range |
| --- | --- | --- |
| working tree | fixture | a..b |

## Divergence Table

| ID / Behavior | Class | Spec reference | Implementation reference | Note |
| --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | handoff | fixture | |

## Escaped Requirements

| Behavior found in code | Owning lens | Failure class | Weight | Evidence |
| --- | --- | --- | --- | --- |

## Deferred Outcomes

| Deferred risk | Owner / date | Materialized? | Consequence |
| --- | --- | --- | --- |
| none | n/a | no | n/a |

## Verification Execution

| {COLUMNS} |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Exact capture check | test | exact | pass | capture-1 | pytest passed |

## Reward-Hacking Review

| REQ-ID | Divergence class | Production-source-support | Mock-substitution | Tautological-assertion | Hardcoded-expected | Disposition | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | yes | {mock} | no | no | {disposition} | fixture review |

## Scope Drift / Divergent Implementations

None.

## Lessons Appended Or Updated

None appended.

### Lessons Fire-Tracking

| Store | Row | Signal | Fired this run? | Caught? |
| --- | --- | --- | --- | --- |
| lessons.md | 1 | fixture signal | no-signal | - |

## Calibration Summary

| Divergence class | Count |
| --- | --- |
| fulfilled | 1 |
| escaped-requirement | 0 |
| scope-drift | 0 |
| divergent-implementation | 0 |
| deferred-outcome | 0 |

Rates: interview-discovery 100.0%, handoff-fidelity 100.0%.
"""


def lessons() -> str:
    return """# Lessons

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
| fixture signal | core-path | enumeration-miss | fixture | 2026-07-10 | 0/0 |

## Retired

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
"""


def make_session(name: str, report: str, bundle: dict[str, object] | None) -> Path:
    session = SCRATCH / name
    session.mkdir()
    (session / "handoff.md").write_text(handoff(), encoding="utf-8")
    (session / "postmortem.md").write_text(report, encoding="utf-8")
    if bundle is not None:
        (session / "evidence_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    return session


def bundle(record: dict[str, object] | None, *, lessons_snapshot: bool = False) -> dict[str, object]:
    out: dict[str, object] = {
        "schema_version": 4,
        "artifacts": {"captured_outputs": [] if record is None else [record]},
    }
    if lessons_snapshot:
        out["lessons"] = {"stores": [{"name": "lessons.md", "active_count": 1}]}
    return out


def cli(script: str, session: Path, *extra: str) -> dict[str, object]:
    return run([*PREFIX, str(SCRIPTS / script), str(session), *extra])


def verdict(result: dict[str, object], expected: int, required: str | None = None) -> str:
    if result["exitCode"] != expected:
        return "failed"
    if required is not None and required.lower() not in str(result["outputSnippet"]).lower():
        return "failed"
    return "passed"


def main() -> None:
    results: list[dict[str, object]] = []

    # 1: pass claim with no capture must fail closed.
    s1 = make_session("g1-missing-capture", verification_report(), bundle(None))
    r1 = cli("verification_execution_lint.py", s1)
    results.append({"id": "guarantee-1", "guarantee": "Exact pass without a matching CAPTURED-OUTPUT fails closed.", "adversarialInput": "Schema-v4 bundle has an empty captured_outputs list while the report claims exact/pass.", "runs": [r1], "verdict": verdict(r1, 1, "no matching captured-output")})

    # 2: confirmed gaming cannot remain fulfilled.
    s2 = make_session("g2-gaming-fulfilled", full_report(gaming=True), bundle(capture(), lessons_snapshot=True))
    r2 = cli("postmortem_lint.py", s2)
    results.append({"id": "guarantee-2", "guarantee": "confirmed-gaming reward-hacking rows cannot be classed fulfilled.", "adversarialInput": "Canonical Reward-Hacking Review marks REQ-001 confirmed-gaming and mock-substitution=yes while its divergence class remains fulfilled.", "runs": [r2], "verdict": verdict(r2, 1, "confirmed-gaming but not classed")})

    # 3: classify names that used to risk substring false hits.
    classify_argv = [*PREFIX, "-c", "import sys; sys.path.insert(0, r'" + str(SCRIPTS) + "'); from audit_scan import classify_changed_path; got=[classify_changed_path(p) for p in ('src/contest.py','src/docs_adapter.py','tests/test_real.py')]; print(got); assert got == ['production','production','test']"]
    r3 = run(classify_argv)
    results.append({"id": "guarantee-3", "guarantee": "Path classification uses components/basenames, not substring hits.", "adversarialInput": "Paths contain contest/docs substrings but are production paths; a conventional tests/ path is the control.", "runs": [r3], "verdict": verdict(r3, 0, "['production', 'production', 'test']")})

    # 4: both dishonest non-exact statuses must not satisfy exact pass capture.
    s4a = make_session("g4-adapted", verification_report(execution="adapted", result="adapted-pass"), bundle(capture()))
    r4a = cli("verification_execution_lint.py", s4a)
    s4b = make_session("g4-skipped", verification_report(execution="skipped", result="pass"), bundle(capture()))
    r4b = cli("verification_execution_lint.py", s4b)
    results.append({"id": "guarantee-4", "guarantee": "adapted-pass and skipped rows cannot satisfy an exact-pass requirement.", "adversarialInput": "Both rows cite a valid exact capture: one claims adapted-pass, the other skipped/pass.", "runs": [r4a, r4b], "verdict": "passed" if verdict(r4a, 1, "adapted command") == "passed" and verdict(r4b, 1, "Execution 'skipped'") == "passed" else "failed"})

    # 5: absent bundle must reach the explicit live-store fallback, not be an input error.
    s5 = make_session("g5-live-fallback", full_report(), None)
    live_lessons = s5 / "lessons.md"
    live_lessons.write_text(lessons(), encoding="utf-8")
    r5 = cli("postmortem_lint.py", s5, "--lessons", str(live_lessons))
    results.append({"id": "guarantee-5", "guarantee": "Absent bundle still executes live-store fire-tracking fallback.", "adversarialInput": "No evidence_bundle.json; explicit live lessons store contains one active row and report includes its fire-tracking row.", "runs": [r5], "verdict": verdict(r5, 1, "LIVE lessons store")})

    # 7: packer must reject a partial CAPTURED-OUTPUT artifact instead of emitting a bundle.
    s7 = SCRATCH / "g7-malformed-capture"
    s7.mkdir()
    (s7 / "handoff.md").write_text("# Part 1\n", encoding="utf-8")
    (s7 / "ledger.json").write_text(json.dumps({"entries": [{"id": "g1", "requirement": "fixture", "ambiguity_score": 0, "impact_weight": 5, "status": "Triangulated", "evidence_channels": ["from-user"]}]}), encoding="utf-8")
    evidence = s7 / "evidence"
    evidence.mkdir()
    (evidence / "captured-output-row-0001.json").write_text(json.dumps({"marker": "CAPTURED-OUTPUT", "spec_row_number": 1}), encoding="utf-8")
    r7 = cli("pack_evidence.py", s7, "--repo-root", str(SCRATCH), "--evidence-dir", str(evidence))
    results.append({"id": "guarantee-7", "guarantee": "Malformed CAPTURED-OUTPUT artifacts fail closed during packing.", "adversarialInput": "Evidence file has CAPTURED-OUTPUT marker but omits all required capture fields.", "runs": [r7], "verdict": verdict(r7, 1, "captured output")})

    # Bypasses use a pass claim and valid-looking capture except for the tampered field.
    sb1 = make_session("bypass-wrong-digest", verification_report(), bundle(capture(command_digest=digest("python -m unittest"))))
    rb1 = cli("verification_execution_lint.py", sb1)
    results.append({"id": "bypass-1", "bypass": "Tampered command digest", "adversarialInput": "Capture points at the cited row/artifact but command_digest is for python -m unittest.", "runs": [rb1], "verdict": verdict(rb1, 2, "did not validate")})

    sb2 = make_session("bypass-wrong-artifact", verification_report(), bundle(capture(artifact_id="different-artifact")))
    rb2 = cli("verification_execution_lint.py", sb2)
    results.append({"id": "bypass-2", "bypass": "Cited artifact id differs from capture artifact id", "adversarialInput": "Bundle has a valid capture under different-artifact while report cites capture-1.", "runs": [rb2], "verdict": verdict(rb2, 1, "no matching captured-output")})

    sb3a = make_session("bypass-spawned-false", verification_report(), bundle(capture(spawned=False)))
    rb3a = cli("verification_execution_lint.py", sb3a)
    sb3b = make_session("bypass-timed-out", verification_report(), bundle(capture(timed_out=True)))
    rb3b = cli("verification_execution_lint.py", sb3b)
    results.append({"id": "bypass-3", "bypass": "Non-executed or timed-out capture", "adversarialInput": "Two valid-schema captures vary spawned=false and timed_out=true while a report claims exact/pass.", "runs": [rb3a, rb3b], "verdict": "passed" if verdict(rb3a, 1, "no matching captured-output") == "passed" and verdict(rb3b, 1, "no matching captured-output") == "passed" else "failed"})

    # Guarantee 6 is populated after the native repository search in the report; runner records no fabricated search result.
    report = {
        "schemaVersion": 1,
        "kind": "black-box/test-report",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "scope": "Frozen Phase 1 deterministic guarantees red-team",
        "fixtureRoot": str(SCRATCH),
        "interpreter": "uv run --python 3.13 --with pytest --with typer --with pydantic --with rich python",
        "results": results,
        "cliReplays": [{
            "schemaVersion": 1,
            "kind": "cli-replay",
            "replaySafe": True,
            "argv": [*PREFIX, str(SCRIPTS / "verification_execution_lint.py"), str(s1)],
            "expectedExitCode": 1,
            "recordedStdout": r1["outputSnippet"],
            "invariants": ["A pass claim without a matching capture exits 1."]
        }],
    }
    (ARTIFACTS / "phase1-redteam-partial.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixtureRoot": str(SCRATCH), "partialReport": str(ARTIFACTS / "phase1-redteam-partial.json")}, indent=2))


if __name__ == "__main__":
    main()
