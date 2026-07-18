#!/usr/bin/env python3
"""Score versioned interview traces against the clean-room case contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score(cases: dict, run: dict) -> dict:
    by_id = {item["id"]: item for item in run["cases"]}
    rows = []
    for case in cases["cases"]:
        observed = by_id[case["id"]]
        expected = set(case["material_decisions"])
        surfaced = set(observed["surfaced"])
        recall = len(expected & surfaced) / len(expected)
        invented = len(set(observed.get("invented", [])))
        questions = observed["questions"]
        excess = max(0, questions - case["question_budget"])
        one_at_a_time = observed.get("max_questions_per_turn", 1) <= 1
        closure = bool(observed.get("closure_reflection"))
        challenge = bool(observed.get("scenario_challenge"))
        authorization = bool(observed.get("authorization_boundary"))
        value = (
            60 * recall
            + 10 * one_at_a_time
            + 10 * closure
            + 10 * challenge
            + 10 * authorization
            - 12 * invented
            - 3 * excess
        )
        rows.append({
            "id": case["id"],
            "recall": round(recall, 4),
            "invented": invented,
            "questions": questions,
            "score": round(max(0, min(100, value)), 2),
        })
    return {
        "schema": "CleanRoomInterviewScore.v1",
        "version": run["version"],
        "case_scores": rows,
        "mean_score": round(sum(row["score"] for row in rows) / len(rows), 2),
        "mean_recall": round(sum(row["recall"] for row in rows) / len(rows), 4),
        "total_questions": sum(row["questions"] for row in rows),
        "total_invented": sum(row["invented"] for row in rows),
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: score.py CASES.json RUN.json")
    print(json.dumps(score(load(Path(sys.argv[1])), load(Path(sys.argv[2]))), indent=2))


if __name__ == "__main__":
    main()
