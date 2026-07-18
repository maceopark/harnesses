from __future__ import annotations

import importlib.util
import json
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("score", ROOT / "eval" / "score.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class EvolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = read(ROOT / "eval" / "cases.json")
        self.v3 = read(ROOT / "eval" / "runs" / "v3.json")

    def test_scores_improve_monotonically(self) -> None:
        scores = []
        for version in ("v0", "v1", "v2", "v3"):
            run = read(ROOT / "eval" / "runs" / f"{version}.json")
            scores.append(MODULE.score(self.cases, run)["mean_score"])
        self.assertEqual(scores, sorted(scores))
        self.assertEqual(scores, [22.67, 67.0, 90.0, 100.0])

    def test_scorer_penalizes_missing_decision(self) -> None:
        mutated = deepcopy(self.v3)
        mutated["cases"][0]["surfaced"].pop()
        self.assertLess(
            MODULE.score(self.cases, mutated)["mean_score"],
            MODULE.score(self.cases, self.v3)["mean_score"],
        )

    def test_scorer_penalizes_invention_batching_and_excess(self) -> None:
        baseline = MODULE.score(self.cases, self.v3)["mean_score"]
        for mutation in ("invented", "batch", "excess"):
            run = deepcopy(self.v3)
            if mutation == "invented":
                run["cases"][0]["invented"] = ["silent-default"]
            elif mutation == "batch":
                run["cases"][0]["max_questions_per_turn"] = 2
            else:
                run["cases"][0]["questions"] = 20
            self.assertLess(MODULE.score(self.cases, run)["mean_score"], baseline)

    def test_frozen_v3_passes_post_freeze_holdout(self) -> None:
        cases = read(ROOT / "eval" / "holdout-cases.json")
        run = read(ROOT / "eval" / "runs" / "v3-holdout.json")
        result = MODULE.score(cases, run)
        self.assertEqual(result["mean_score"], 100.0)
        self.assertEqual(result["total_invented"], 0)

    def test_packaged_skill_is_frozen_v4(self) -> None:
        current = (ROOT / "clarify-requirements" / "SKILL.md").read_bytes()
        frozen = (ROOT / "evolution" / "v4" / "SKILL.md").read_bytes()
        self.assertEqual(current, frozen)

    def test_v4_contains_runtime_and_handoff_guards(self) -> None:
        skill = (ROOT / "clarify-requirements" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "structured question UI",
            "recommended defaults",
            "build-contract.json",
            "implementation_agent_directive",
            "decision.jsonl",
            "implementation-start prompt",
            "do not ask the user to approve whether the specification is sufficient",
        ):
            self.assertIn(required, skill)

    def test_todo_contract_starts_with_agent_directive(self) -> None:
        path = ROOT / "artifacts" / "todo-cli" / "build-contract.json"
        contract = read(path)
        self.assertEqual(next(iter(contract)), "implementation_agent_directive")
        self.assertEqual(contract["status"], "implementation_ready")
        self.assertEqual(contract["readiness"]["decision"], "ready")
        self.assertEqual(
            contract["implementation_agent_directive"]["specification_gap_protocol"]["log_path"],
            "decision.jsonl",
        )


if __name__ == "__main__":
    unittest.main()
