import json

import pytest

from swebench_interview_cases.batch import (
    _apply_edit, _strategy_history_summary, _validate_strategy_portfolio,
    batch_mutate,
)


STRATEGIES = [
    {
        "strategy_id": "admissible", "principle": "admissibility_first",
        "operation": "replace", "hypothesis": "h1", "target_selection": "t1",
        "admissibility_test": "a1", "preservation_invariant": "p1",
        "scope_boundary": "s1",
    },
    {
        "strategy_id": "local", "principle": "scope_locality",
        "operation": "replace", "hypothesis": "h2", "target_selection": "t2",
        "admissibility_test": "a2", "preservation_invariant": "p2",
        "scope_boundary": "s2",
    },
    {
        "strategy_id": "observable", "principle": "observable_contract",
        "operation": "add", "hypothesis": "h3", "target_selection": "t3",
        "admissibility_test": "a3", "preservation_invariant": "p3",
        "scope_boundary": "s3",
    },
]


def test_strategy_history_exposes_tradeoff_classes_without_case_details():
    summary = _strategy_history_summary({
        "source_partitions": ["development"],
        "evaluations": [{
            "strategy": STRATEGIES[0], "operation": "replace", "eligible": False,
            "improved_cases": ["secret-alias"], "regressed_cases": ["other-secret"],
            "case_deltas": [{"case_alias_sha256": "a" * 64, "deltas": {}}],
            "improvement_failure_counts": {"invented_requirements": 4},
            "regression_failure_counts": {"material_implementation_decisions": 3},
            "changed_words": 12,
        }],
    })
    assert summary[0]["improvement_failure_counts"] == {"invented_requirements": 4}
    assert summary[0]["regression_failure_counts"] == {"material_implementation_decisions": 3}
    assert "improved_cases" not in summary[0]
    assert "regressed_cases" not in summary[0]
    assert "case_deltas" not in summary[0]
    assert "secret-alias" not in json.dumps(summary)


def fake_result(kwargs, *, partial=False):
    if kwargs["role"] == "mutation-strategist":
        return {"strategies": STRATEGIES, "rationale": "bounded structural edits"}
    rows = kwargs["payload"]["development_signals"]
    if partial:
        rows = rows[:1]
    ids = [item["signal_id"] for item in rows]
    operation = kwargs["payload"]["strategy"]["operation"]
    replacement = {"replace": f"replaced-{kwargs['role'][-1]}", "delete": "", "add": "added"}[operation]
    return {
        "operation": operation, "anchor_exact_text": "base", "replacement_text": replacement,
        "change_summary": "minimal", "signal_reviews": [
            {"signal_id": item, "skill_gap": True, "reason": "must resolve"} for item in ids
        ], "addressed_signal_ids": ids,
    }


def decision(index):
    return {
        "timestamp": f"before-change-{index}",
        "gap": "unspecified behavior",
        "options_considered": ["preserve", "replace"],
        "choice": "preserve",
        "reason": "compatibility",
        "observable_impact": "existing callers retain behavior",
        "reversibility": "revert the patch",
    }


def make_run(root, index, *, decisions=(), invented=(), regressions=(), material=True):
    run = root / str(index); run.mkdir()
    (run / "run-manifest.json").write_text(
        json.dumps({"partition": "development", "alias": f"case-{index}"})
    )
    implementation = run / "implementation"; implementation.mkdir()
    rows = tuple(decisions)
    (implementation / "decision.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in rows)
    )
    (implementation / "implementation-manifest.json").write_text(
        json.dumps({"decision_count": len(rows), "material_decision_count": len(rows) if material else 0})
    )
    (implementation / "decision-materiality.json").write_text(json.dumps({
        "schema": "DecisionMaterialityReview.v1",
        "reviews": [
            {"decision_index": item, "material": material} for item in range(len(rows))
        ]
    }))
    (run / "judge.json").write_text(json.dumps({
        "invented_requirements": list(invented),
        "compatibility_regressions": list(regressions),
    }))
    return run


def test_batch_mutation_reviews_every_decision_exactly_once(tmp_path, monkeypatch):
    runs = [make_run(tmp_path, index, decisions=[decision(index)] if index < 2 else []) for index in range(8)]

    class Fake:
        def __init__(self, root, *args, **kwargs): self.root = root
        def generate(self, **kwargs):
            if kwargs["role"].startswith("development-mutator"):
                assert "Raw decision count is diagnostic only" in kwargs["instructions"]
                assert "do not refer to another candidate's rule" in kwargs["instructions"]
                assert "decision log" in kwargs["instructions"]
                assert "without embedding examples" in kwargs["instructions"]
            else:
                assert "normative authority from descriptive evidence" in kwargs["instructions"]
                assert "not to discovery" in kwargs["instructions"]
            self.root.mkdir(parents=True)
            (self.root / "001-development-mutator.json").write_text(
                json.dumps({"input": kwargs["payload"]})
            )
            return fake_result(kwargs)

    monkeypatch.setattr("swebench_interview_cases.batch.CodexJsonModel", Fake)
    result = batch_mutate(baseline_skill="base", development_run_dirs=runs, output_dir=tmp_path / "batch")
    assert result["signal_count"] == 2
    assert result["skill_gap_counts"] == [2, 2, 2]
    assert all(len(item) == 2 for item in result["reviewed_signal_ids_by_candidate"])
    assert result["candidate_count"] == 3
    assert result["mutation_calls"] == 4
    assert result["mutation_performed"] is True
    mutation = json.loads((tmp_path / "batch" / "mutation.json").read_text())
    assert {item["principle"] for item in mutation["portfolio"]["strategies"]} == {
        "admissibility_first", "scope_locality", "observable_contract",
    }
    assert [item["operation"] for item in mutation["portfolio"]["strategies"]].count(
        "replace"
    ) == 2


def test_batch_mutation_ignores_non_material_decisions(tmp_path):
    runs = [
        make_run(tmp_path, index, decisions=[decision(index)] if index == 0 else [], material=False)
        for index in range(8)
    ]
    result = batch_mutate(
        baseline_skill="base", development_run_dirs=runs, output_dir=tmp_path / "batch",
    )
    assert result["signal_count"] == 0


def test_batch_mutation_rejects_partial_review(tmp_path, monkeypatch):
    runs = [make_run(tmp_path, index, decisions=[decision(index)] if index < 2 else []) for index in range(8)]

    class Fake:
        def __init__(self, root, *args, **kwargs): self.root = root
        def generate(self, **kwargs):
            return fake_result(kwargs, partial=True)

    monkeypatch.setattr("swebench_interview_cases.batch.CodexJsonModel", Fake)
    with pytest.raises(RuntimeError, match="EVERY|every"):
        batch_mutate(baseline_skill="base", development_run_dirs=runs, output_dir=tmp_path / "batch")


def test_zero_decisions_skips_mutation_and_keeps_baseline(tmp_path):
    runs = [make_run(tmp_path, index) for index in range(8)]
    result = batch_mutate(baseline_skill="base", development_run_dirs=runs, output_dir=tmp_path / "batch")
    assert result["signal_count"] == result["mutation_calls"] == 0
    assert result["candidate_count"] == 1
    assert (tmp_path / "batch" / "candidate-SKILL.md").read_text() == "base"


def test_judge_findings_are_each_direct_mutation_signals(tmp_path, monkeypatch):
    runs = [
        make_run(
            tmp_path, index,
            invented=["invented behavior"] if index == 0 else [],
            regressions=["compatibility break"] if index == 1 else [],
        )
        for index in range(8)
    ]

    class Fake:
        def __init__(self, root, *args, **kwargs): self.root = root
        def generate(self, **kwargs):
            if kwargs["role"] != "mutation-strategist":
                signals = kwargs["payload"]["development_signals"]
                assert {item["source"] for item in signals} == {
                    "invented_requirement", "compatibility_regression",
                }
            self.root.mkdir(parents=True)
            (self.root / "001-development-mutator.json").write_text(
                json.dumps({"input": kwargs["payload"]})
            )
            return fake_result(kwargs)

    monkeypatch.setattr("swebench_interview_cases.batch.CodexJsonModel", Fake)
    result = batch_mutate(
        baseline_skill="base", development_run_dirs=runs, output_dir=tmp_path / "batch",
    )
    assert result["signal_count"] == 2
    assert result["signal_source_counts"] == {
        "material_decision": 0, "invented_requirement": 1, "compatibility_regression": 1,
    }


def test_structural_edits_change_only_the_exact_anchor():
    baseline = "before\nTARGET\nafter\n"
    assert _apply_edit(baseline, {
        "operation": "replace", "anchor_exact_text": "TARGET", "replacement_text": "NEW",
    }) == "before\nNEW\nafter\n"
    assert _apply_edit(baseline, {
        "operation": "delete", "anchor_exact_text": "TARGET\n", "replacement_text": "",
    }) == "before\nafter\n"
    assert _apply_edit(baseline, {
        "operation": "add", "anchor_exact_text": "TARGET", "replacement_text": "NEW",
    }) == "before\nTARGET\nNEW\nafter\n"


@pytest.mark.parametrize("edit", [
    {"operation": "replace", "anchor_exact_text": "missing", "replacement_text": "new"},
    {"operation": "delete", "anchor_exact_text": "target", "replacement_text": "not empty"},
    {"operation": "replace", "anchor_exact_text": "target", "replacement_text": ""},
    {"operation": "add", "anchor_exact_text": "target", "replacement_text": "```code```"},
    {"operation": "add", "anchor_exact_text": "target", "replacement_text": " ".join(["word"] * 121)},
])
def test_structural_edit_rejects_unsafe_or_unbounded_shapes(edit):
    with pytest.raises(RuntimeError, match="edit|replace|delete"):
        _apply_edit("target", edit)


@pytest.mark.parametrize("candidate_count", [0, 4])
def test_batch_mutation_caps_the_predeclared_candidate_pool(tmp_path, candidate_count):
    with pytest.raises(ValueError, match="between 1 and 3"):
        batch_mutate(
            baseline_skill="base", development_run_dirs=[],
            output_dir=tmp_path / "batch", candidate_count=candidate_count,
        )


def test_batch_mutation_rejects_strategy_history_from_validation(tmp_path):
    with pytest.raises(ValueError, match="development outcomes only"):
        batch_mutate(
            baseline_skill="base", development_run_dirs=[], output_dir=tmp_path / "batch",
            strategy_history={"source_partitions": ["validation"], "evaluations": []},
        )


def test_strategy_history_exposes_counts_not_case_identifiers():
    summary = _strategy_history_summary({
        "source_partitions": ["development"],
        "evaluations": [{
            "strategy": STRATEGIES[0], "operation": "replace", "eligible": False,
            "improved_cases": ["raw-case-a"], "regressed_cases": ["raw-case-b"],
            "changed_words": 12,
        }],
    })
    assert summary[0]["improved_case_count"] == summary[0]["regressed_case_count"] == 1
    assert "raw-case" not in json.dumps(summary)


def test_strategy_portfolio_requires_conceptual_not_operation_diversity():
    _validate_strategy_portfolio(STRATEGIES)
    duplicated_principle = [dict(item) for item in STRATEGIES]
    duplicated_principle[2]["principle"] = "scope_locality"
    with pytest.raises(RuntimeError, match="principle"):
        _validate_strategy_portfolio(duplicated_principle)
