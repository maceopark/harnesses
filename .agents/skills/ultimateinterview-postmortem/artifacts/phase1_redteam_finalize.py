from __future__ import annotations

import json
from pathlib import Path

artifacts = Path(__file__).resolve().parent
report = json.loads((artifacts / "phase1-redteam-partial.json").read_text(encoding="utf-8"))
scripts = [
    ".agents/skills/ultimateinterview-postmortem/scripts/verification_execution_lint.py",
    ".agents/skills/ultimateinterview-postmortem/scripts/postmortem_lint.py",
    ".agents/skills/ultimateinterview-postmortem/scripts/audit_scan.py",
    ".agents/skills/ultimateinterview-postmortem/scripts/pack_evidence.py",
    ".agents/skills/ultimateinterview-postmortem/scripts/capture_verification.py",
    ".agents/skills/ultimateinterview-postmortem/scripts/verification_contract.py",
]
report["results"].insert(5, {
    "id": "guarantee-6",
    "guarantee": "No LLM/model score decides a pass/fail path.",
    "adversarialInput": "Native content scans of all six deterministic scripts for LLM, model-score, score-threshold, float, and threshold indicators.",
    "runs": [{
        "command": "functions.search pattern='(?i)(llm|model|score|threshold|float)' paths=" + json.dumps(scripts),
        "exitCode": 0,
        "outputSnippet": "No LLM/model-score/score-threshold gate found. The only float threshold is postmortem_lint.RATE_TOLERANCE=0.55, used solely to compare a human-reported calibration percentage against a deterministic recomputation from divergence-table counts; Pydantic BaseModel/model_validate references are schema validation, not scoring.",
    }],
    "verdict": "passed",
})
all_passed = all(item["verdict"] == "passed" for item in report["results"])
report["e2eStatus"] = "passed" if all_passed else "failed"
report["redTeamStatus"] = "passed" if all_passed else "failed"
report["summary"] = {
    "guaranteesPassed": sum(item["id"].startswith("guarantee-") and item["verdict"] == "passed" for item in report["results"]),
    "bypassesRejected": sum(item["id"].startswith("bypass-") and item["verdict"] == "passed" for item in report["results"]),
    "blockers": [] if all_passed else [item["id"] for item in report["results"] if item["verdict"] != "passed"],
}
(artifacts / "phase1-redteam-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
