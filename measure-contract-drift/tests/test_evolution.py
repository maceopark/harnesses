from __future__ import annotations

import json
from pathlib import Path

from driftbench.evolution import convergence_decision, render_comparison_html


POLICY = {"schema": "DiscoveryStoppingPolicy.v1", "maximum_generation": 9,
          "minimum_generation": 2, "patience": 2, "fidelity_epsilon_ppm": 25000,
          "decision_epsilon_milli": 500, "skill_bytes_epsilon": 256,
          "require_full_candidate_inventory": True, "full_candidate_count": 4}


def _archive(root: Path, generation: int, lcb: float, decisions: float, size: int,
             parent: Path | None = None) -> None:
    root.mkdir()
    candidate = f"g{generation:02d}-c00"
    (root / "pareto-archive.json").write_text(json.dumps({
        "generation": generation, "archive": [candidate], "candidates": [{
            "candidate_id": candidate, "fidelity_lcb": lcb, "fidelity_ucb": 1.0,
            "median_material_decisions": decisions, "skill_bytes": size,
            "total_tokens": 0, "wall_clock_ms": 0}]}))
    if parent is not None:
        (root / "generation-context.json").write_text(json.dumps({"parent_run": str(parent)}))


def test_convergence_stops_after_two_epsilon_covered_generations(tmp_path: Path) -> None:
    g0 = tmp_path / "g0"; g1 = tmp_path / "g1"; g2 = tmp_path / "g2"
    _archive(g0, 0, .60, 3, 1000)
    _archive(g1, 1, .61, 3.5, 1200, g0)
    _archive(g2, 2, .60, 3, 1100, g1)
    result = convergence_decision(g2, POLICY, effective_candidates=4,
                                  terminal_cells=72, expected_cells=72)
    assert result["consecutive_stagnant_generations"] == 2
    assert result["stop"] is True and result["reason"] == "frontier-stagnation"


def test_convergence_novel_frontier_resets_streak_and_reduced_run_is_ineligible(tmp_path: Path) -> None:
    g0 = tmp_path / "g0"; g1 = tmp_path / "g1"; g2 = tmp_path / "g2"
    _archive(g0, 0, .60, 3, 1000)
    _archive(g1, 1, .61, 3.5, 1200, g0)
    _archive(g2, 2, .70, 2, 800, g1)
    result = convergence_decision(g2, POLICY, effective_candidates=2,
                                  terminal_cells=36, expected_cells=36)
    assert result["eligible"] is False
    assert result["consecutive_stagnant_generations"] == 0
    assert result["stop"] is False


def test_html_report_is_deterministic_self_contained_and_escaped() -> None:
    payload = {"parent_generation": 1, "generation": 2, "best_lcb_parent": .5,
               "best_lcb_current": .6, "parent_stats": {"invalid": 1, "retried": 2},
               "current_stats": {"invalid": 0, "retried": 1},
               "candidates": [{"candidate_id": "<script>alert(1)</script>",
                                "parent_candidate_id": "p&1",
                                "parent_skill_summary": "Parent <skill>",
                                "candidate_skill_summary": "Candidate & contract",
                                "skill_change_summary": "Added <ledger> & reordered checks.",
                                "parent_mutation_theme": "minimal-seed",
                                "parent_mutation_label": "Minimal <seed>",
                                "parent_mutation_description": "Original & unchanged.",
                                "mutation_intent_id": "novel-structure",
                                "mutation_intent_label": "Novel <structure>",
                                "mutation_directive": "Change <structure> & terminate.",
                                "fidelity_lcb": .6, "fidelity_lcb_delta": .1,
                                "median_material_decisions": 2.0, "decision_delta": -1.0,
                                "skill_bytes": 100, "skill_bytes_delta": -20,
                                "pareto": True}],
               "root_causes": {"persisted": ["a&b"], "new": [], "resolved": []},
               "convergence": {"reason": "continue",
                               "consecutive_stagnant_generations": 0, "stop": False}}
    first = render_comparison_html(payload); second = render_comparison_html(payload)
    assert first == second
    assert "Content-Security-Policy" in first and "<script" not in first
    assert "&lt;script&gt;" in first and "p&amp;1" in first and "a&amp;b" in first
    assert "Change &lt;structure&gt; &amp; terminate." in first
    assert "Parent &lt;skill&gt;" in first and "Candidate &amp; contract" in first
    assert "Added &lt;ledger&gt; &amp; reordered checks." in first
    assert "http://" not in first and "https://" not in first
