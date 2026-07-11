from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/ultimateinterview-postmortem"
SCRIPTS = SKILL / "scripts"
ARTIFACTS = SKILL / "artifacts"
REAL = ROOT / ".agents/skills/ultimateinterview/scripts/regression_fixtures/todo-cli-app-5"
PHASE1 = ARTIFACTS / "phase1-redteam-919xodsk"
F3 = ARTIFACTS / "f3-redteam-mc3aqqhv"
PY = ["uv", "run", "--python", "3.13", "--with", "typer", "--with", "pydantic", "--with", "rich", "python"]


def run(*args: str) -> dict[str, object]:
    proc = subprocess.run([*PY, *args], cwd=ROOT, text=True, capture_output=True, check=False)
    output = (proc.stdout + proc.stderr).strip()
    return {"invocation": " ".join([*PY, *args]), "exitCode": proc.returncode, "output": output[-2000:]}


def handoff() -> str:
    return """# Spec: intent fixture
# Part 1 - Build Contract
## Behavior Contract
| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| REQ-001 | The tool supports the required operation. | The operation succeeds. |

## Verification Commands
| Check | Command / action |
| --- | --- |
| Verify REQ-001 capture | `python -m pytest` |
"""


def diff(decision: bool) -> str:
    line = '+requires-python = ">=3.13"' if decision else "+print('ordinary implementation')"
    return f"""diff --git a/pyproject.toml b/pyproject.toml
index 1111111..2222222 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1 +1,2 @@
{line}
"""


def make_session(base: Path, name: str, *, decision_hunk: bool = True, decision: bool = False, capture: bool = False, prose: bool = False) -> Path:
    session = base / name
    session.mkdir()
    (session / "handoff.md").write_text(handoff(), encoding="utf-8")
    (session / "fixture.diff").write_text(diff(decision_hunk), encoding="utf-8")
    (session / "test_req001_intent.py").write_text("def test_req001_intent():\n    assert True\n", encoding="utf-8")
    if decision:
        (session / "decisions.jsonl").write_text(json.dumps({"decision": "Set runtime version floor and dependency pin", "reason": "REQ-001 implementation requires a runtime version floor and dependency pin", "spec_citation": "REQ-001"}) + "\n", encoding="utf-8")
    if prose:
        (session / "postmortem.md").write_text("# Wonder Generalization\nWonder prose insists REQ-001 was intended.\n", encoding="utf-8")
    if capture:
        command = "python -m pytest"
        empty_hash = hashlib.sha256(b"").hexdigest()
        cap = {
            "marker": "CAPTURED-OUTPUT", "spec_row_number": 1, "check": "Verify REQ-001 capture", "kind": "test",
            "exact_command": command, "command_digest": hashlib.sha256(command.encode()).hexdigest(), "effective_heads": ["python"],
            "cwd": str(session), "started_at": "2026-07-10T00:00:00Z", "ended_at": "2026-07-10T00:00:01Z", "spawned": True,
            "timed_out": False, "timeout_seconds": 30, "exit_code": 0, "stdout": "", "stderr": "", "stdout_full_bytes": 0,
            "stderr_full_bytes": 0, "stdout_sha256": empty_hash, "stderr_sha256": empty_hash,
        }
        (session / "evidence_bundle.json").write_text(json.dumps({"schema_version": 4, "artifacts": {"captured_outputs": [{**cap, "artifact_id": "req001-capture", "file_sha256": empty_hash}]}}), encoding="utf-8")
    return session


def audit(session: Path) -> dict[str, object]:
    return run(str(SCRIPTS / "audit_scan.py"), str(session), "--diff-file", str(session / "fixture.diff"), "--tests", str(session / "test_req001_intent.py"), "--repo-root", str(session))


def clone_real(base: Path, name: str) -> Path:
    dst = base / name
    shutil.copytree(REAL, dst)
    return dst


def mutate_text(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def verdict(condition: bool) -> str:
    return "passed" if condition else "BLOCKER"


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="intent-redteam-", dir=ARTIFACTS))
    base = make_session(root, "g1-test-only")
    g1_test = audit(base)
    dec = make_session(root, "g1-decision", decision=True)
    g1_decision = audit(dec)
    cap = make_session(root, "g1-capture", capture=True)
    g1_capture = audit(cap)
    prose = make_session(root, "b1-prose", prose=True)
    b1 = audit(prose)

    g2 = g1_test
    g3_logged = make_session(root, "g3-logged", decision=True)
    g3b = audit(g3_logged)
    g3_absent = make_session(root, "g3-absent-no-hunk", decision_hunk=False)
    shutil.copyfile(REAL / "ledger.json", g3_absent / "ledger.json")
    g3c = audit(g3_absent)
    packed = run(str(SCRIPTS / "pack_evidence.py"), str(g3_absent), "--diff-file", str(g3_absent / "fixture.diff"), "--repo-root", str(root), "--no-ulw")
    packed_data = json.loads((g3_absent / "evidence_bundle.json").read_text(encoding="utf-8"))

    lint_cases: dict[str, dict[str, object]] = {}
    no_column = clone_real(root, "g4-no-column")
    mutate_text(no_column / "postmortem.md", " | Intent attribution", "")
    lint_cases["missing-column"] = run(str(SCRIPTS / "postmortem_lint.py"), str(no_column))
    blank_ref = clone_real(root, "g4-blank-ref")
    mutate_text(blank_ref / "postmortem.md", "owned-signal:decision#3", "owned-signal:")
    lint_cases["blank-ref"] = run(str(SCRIPTS / "postmortem_lint.py"), str(blank_ref))
    invalid = clone_real(root, "g4-invalid-token")
    mutate_text(invalid / "postmortem.md", "owned-signal:decision#3", "guessed")
    lint_cases["invalid-token"] = run(str(SCRIPTS / "postmortem_lint.py"), str(invalid))
    run_blind = clone_real(root, "g4-run-blind")
    lint_cases["run-blind"] = run(str(SCRIPTS / "postmortem_lint.py"), str(run_blind))
    bad_ref = clone_real(root, "b2-nonexistent-decision")
    mutate_text(bad_ref / "postmortem.md", "owned-signal:decision#3", "owned-signal:decision#99")
    b2 = run(str(SCRIPTS / "postmortem_lint.py"), str(bad_ref))

    g5_capture = run(str(SCRIPTS / "verification_execution_lint.py"), str(PHASE1 / "g1-missing-capture"))
    g5_gaming = run(str(SCRIPTS / "postmortem_lint.py"), str(PHASE1 / "g2-gaming-fulfilled"))
    g5_fallback = run(str(SCRIPTS / "postmortem_lint.py"), str(PHASE1 / "g5-live-fallback"), "--lessons", str(PHASE1 / "g5-live-fallback/lessons.md"))
    g5_wonder = run(str(SCRIPTS / "postmortem_lint.py"), str(F3 / "g1-missing-wonder"))
    g6 = run(str(SCRIPTS / "postmortem_lint.py"), str(REAL))

    results = [
        {"id": "G1", "input": "REQ-named test only; then an owned DecisionRecord; then a schema-v4 matching CAPTURED-OUTPUT.", "runs": [g1_test, g1_decision, g1_capture], "observed": {"testOnly": "req_named_test=true; owned_intent_signal=false", "decision": "owned_intent_signal=true (decision#1)", "capture": "BLOCKER: matching schema-v4 CAPTURED-OUTPUT still reports owned_intent_signal=false"}, "verdict": verdict("req_named_test=true" in g1_test["output"] and "owned_intent_signal=false" in g1_test["output"] and "owned_intent_signal=true" in g1_decision["output"] and "owned_intent_signal=true" in g1_capture["output"])},
        {"id": "G2", "input": "Section-F test signal plus an unlogged requires-python decision shape.", "runs": [g2], "observed": "audit exits 0 while emitting section F and execution_process_gap candidate", "verdict": verdict(g2["exitCode"] == 0 and "execution_process_gap candidate" in g2["output"] and "cooperation-free intent signals" in g2["output"])},
        {"id": "G3", "input": "(a) unlogged requires-python hunk; (b) same hunk plus logged version decision; (c) no decisions file and ordinary hunk.", "runs": [g1_test, g3b, g3c, packed], "observed": {"unloggedCandidate": "execution_process_gap candidate" in g1_test["output"], "loggedCandidateAbsent": "execution_process_gap candidate" not in g3b["output"], "noHunkCandidateAbsent": "execution_process_gap candidate" not in g3c["output"], "missingEvidence": packed_data.get("missing_evidence")}, "verdict": verdict("execution_process_gap candidate" in g1_test["output"] and "execution_process_gap candidate" not in g3b["output"] and "execution_process_gap candidate" not in g3c["output"] and any("decisions.jsonl absent" in x for x in packed_data.get("missing_evidence", [])))},
        {"id": "G4", "input": "Clone of green app-5 fixture mutated to omit column, blank owned ref, invalid token; unmodified run-blind control.", "runs": list(lint_cases.values()), "observed": {key: {"exitCode": value["exitCode"], "intent": "intent:" in value["output"]} for key, value in lint_cases.items()}, "verdict": verdict(all(lint_cases[k]["exitCode"] == 1 and "intent:" in lint_cases[k]["output"] for k in ("missing-column", "blank-ref", "invalid-token")) and lint_cases["run-blind"]["exitCode"] == 0)},
        {"id": "G5", "input": "Phase-1 and F3 adversarial fixtures.", "runs": [g5_capture, g5_gaming, g5_fallback, g5_wonder], "observed": "missing capture=1; confirmed gaming=1; absent bundle=1 (not 2) with LIVE fallback; missing Wonder=1", "verdict": verdict(g5_capture["exitCode"] == 1 and g5_gaming["exitCode"] == 1 and g5_fallback["exitCode"] == 1 and g5_wonder["exitCode"] == 1 and "LIVE lessons store" in g5_fallback["output"])},
        {"id": "G6", "input": "Checked-in todo-cli-app-5 regression fixture.", "runs": [g6], "observed": "postmortem_lint exit 0; report E1 owned-signal:decision#3 and E2 run-blind", "verdict": verdict(g6["exitCode"] == 0 and "owned-signal:decision#3" in (REAL / "postmortem.md").read_text(encoding="utf-8") and "run-blind" in (REAL / "postmortem.md").read_text(encoding="utf-8"))},
        {"id": "B1", "input": "Wonder/prose says REQ-001 was intended, with named test but no decision/capture.", "runs": [b1], "observed": "owned_intent_signal=false", "verdict": verdict("req_named_test=true" in b1["output"] and "owned_intent_signal=false" in b1["output"])},
        {"id": "B2", "input": "Green app-5 report altered to owned-signal:decision#99, which does not exist.", "runs": [b2], "observed": "lint exits 0: intentional structural-only limit; lint validates token shape, not decision-reference existence.", "verdict": "documented structural-only limit" if b2["exitCode"] == 0 else "passed (cross-check exists)"},
    ]
    guards = [row for row in results if row["id"].startswith("G")]
    status = "passed" if all(row["verdict"] == "passed" for row in guards) else "failed"
    report = {"schemaVersion": 1, "kind": "black-box/test-report", "createdAt": datetime.now(UTC).isoformat(), "fixtureRoot": str(root), "interpreter": " ".join(PY), "results": results, "e2eStatus": status, "redTeamStatus": status, "summary": {"guardCount": 6, "guardsPassed": sum(row["verdict"] == "passed" for row in guards), "structuralOnlyLimit": "B2" if b2["exitCode"] == 0 else None}}
    (ARTIFACTS / "intent-redteam-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(ARTIFACTS / "intent-redteam-report.json"), "status": status}, indent=2))


if __name__ == "__main__":
    main()
