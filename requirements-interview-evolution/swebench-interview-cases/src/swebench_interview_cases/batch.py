"""One-shot mutation from every development implementation and judge signal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .implementer import read_decisions
from .model import CodexJsonModel
from .schemas import canonical_json_bytes


SIGNAL_REVIEW = {
    "type": "object", "additionalProperties": False,
    "required": ["signal_id", "skill_gap", "reason"],
    "properties": {
        "signal_id": {"type": "string"},
        "skill_gap": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

STRATEGY_ITEM = {
    "type": "object", "additionalProperties": False,
    "required": [
        "strategy_id", "principle", "operation", "hypothesis",
        "target_selection", "admissibility_test", "preservation_invariant",
        "scope_boundary",
    ],
    "properties": {
        "strategy_id": {"type": "string"},
        "principle": {
            "type": "string",
            "enum": [
                "admissibility_first", "scope_locality", "observable_contract",
            ],
        },
        "operation": {"type": "string", "enum": ["replace", "delete", "add"]},
        "hypothesis": {"type": "string"},
        "target_selection": {"type": "string"},
        "admissibility_test": {"type": "string"},
        "preservation_invariant": {"type": "string"},
        "scope_boundary": {"type": "string"},
    },
}

STRATEGY_PORTFOLIO_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["strategies", "rationale"],
    "properties": {
        "strategies": {
            "type": "array", "minItems": 3, "maxItems": 3, "items": STRATEGY_ITEM,
        },
        "rationale": {"type": "string"},
    },
}

MUTATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": [
        "operation", "anchor_exact_text", "replacement_text", "change_summary",
        "signal_reviews", "addressed_signal_ids",
    ],
    "properties": {
        "operation": {"type": "string", "enum": ["replace", "delete", "add"]},
        "anchor_exact_text": {"type": "string"},
        "replacement_text": {"type": "string"},
        "change_summary": {"type": "string"},
        "signal_reviews": {"type": "array", "items": SIGNAL_REVIEW},
        "addressed_signal_ids": {"type": "array", "items": {"type": "string"}},
    },
}


def _apply_edit(baseline_skill: str, edit: dict[str, Any]) -> str:
    operation = edit["operation"]
    anchor = edit["anchor_exact_text"]
    replacement = edit["replacement_text"]
    if not anchor or baseline_skill.count(anchor) != 1:
        raise RuntimeError("edit anchor must occur exactly once in the baseline")
    if len(anchor.split()) > 120 or len(replacement.split()) > 120:
        raise RuntimeError("edit anchor and replacement must each contain at most 120 words")
    if "```" in anchor or "```" in replacement:
        raise RuntimeError("edit must not introduce or target fenced code")
    if operation == "delete":
        if replacement:
            raise RuntimeError("delete edit replacement must be empty")
        candidate = baseline_skill.replace(anchor, "", 1)
    elif operation == "replace":
        if not replacement.strip():
            raise RuntimeError("replace edit requires replacement text")
        candidate = baseline_skill.replace(anchor, replacement, 1)
    elif operation == "add":
        if not replacement.strip():
            raise RuntimeError("add edit requires inserted text")
        candidate = baseline_skill.replace(anchor, anchor + "\n" + replacement, 1)
    else:
        raise RuntimeError("unsupported edit operation")
    if candidate == baseline_skill:
        raise RuntimeError("edit must change the baseline")
    return candidate


def development_signals(
    development_run_dirs: Iterable[Path],
) -> list[dict[str, Any]]:
    run_dirs = tuple(development_run_dirs)
    if len(run_dirs) != 8:
        raise ValueError("batch mutation requires exactly eight development runs")
    result: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
        if manifest["partition"] != "development":
            raise ValueError("mutation decisions must come only from development")
        implementation_dir = run_dir / "implementation"
        implementation_manifest = json.loads(
            (implementation_dir / "implementation-manifest.json").read_text(encoding="utf-8")
        )
        decisions = read_decisions(implementation_dir / "decision.jsonl")
        if implementation_manifest["decision_count"] != len(decisions):
            raise ValueError("implementation decision count drifted")
        materiality_path = implementation_dir / "decision-materiality.json"
        if materiality_path.is_file():
            materiality = json.loads(materiality_path.read_text(encoding="utf-8"))
            material_indexes = {
                item["decision_index"] for item in materiality["reviews"] if item["material"]
            }
        else:
            material_indexes = set(range(len(decisions)))
        alias_digest = hashlib.sha256(str(manifest["alias"]).encode()).hexdigest()
        judge = json.loads((run_dir / "judge.json").read_text(encoding="utf-8"))
        rows: list[tuple[str, str]] = [
            ("material_decision", canonical_json_bytes(item).decode())
            for index, item in enumerate(decisions) if index in material_indexes
        ]
        rows.extend(("invented_requirement", item) for item in judge["invented_requirements"])
        rows.extend(
            ("compatibility_regression", item)
            for item in judge["compatibility_regressions"]
        )
        for row_number, (source, text) in enumerate(rows, 1):
            signal_id = hashlib.sha256(
                alias_digest.encode() + b"\0" + source.encode() + b"\0"
                + str(row_number).encode() + b"\0" + text.encode()
            ).hexdigest()
            result.append({
                "signal_id": signal_id, "case_alias_sha256": alias_digest,
                "source": source, "text": text,
            })
    return sorted(result, key=lambda item: (item["case_alias_sha256"], item["signal_id"]))


def _validate_reviews(mutation: dict[str, Any], signals: list[dict[str, Any]]) -> None:
    expected = {item["signal_id"] for item in signals}
    review_ids = [item["signal_id"] for item in mutation["signal_reviews"]]
    if len(review_ids) != len(set(review_ids)) or set(review_ids) != expected:
        raise RuntimeError("Mutator must review every development signal exactly once")
    addressed = mutation["addressed_signal_ids"]
    if len(addressed) != len(set(addressed)) or not set(addressed).issubset(expected):
        raise RuntimeError("Mutator addressed signal IDs are invalid")
    skill_gap_ids = {
        item["signal_id"] for item in mutation["signal_reviews"] if item["skill_gap"]
    }
    if not set(addressed).issubset(skill_gap_ids):
        raise RuntimeError("Mutator may address only signals classified as skill gaps")


def _validate_strategy_history(history: dict[str, Any] | None) -> None:
    if history is None:
        return
    if history.get("source_partitions") != ["development"]:
        raise ValueError("strategy history must contain development outcomes only")

    def keys(value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key).lower()
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    if any("validation" in key or "holdout" in key for key in keys(history)):
        raise ValueError("strategy history must not contain validation or holdout fields")


def _validate_strategy_portfolio(strategies: list[dict[str, Any]]) -> None:
    required_principles = {
        "admissibility_first", "scope_locality", "observable_contract",
    }
    if len(strategies) != 3:
        raise RuntimeError("strategy portfolio must contain exactly three strategies")
    if {item["principle"] for item in strategies} != required_principles:
        raise RuntimeError(
            "strategy portfolio must cover each principle exactly once"
        )
    if len({item["strategy_id"] for item in strategies}) != len(strategies):
        raise RuntimeError("strategy IDs must be distinct")


def _strategy_history_summary(history: dict[str, Any] | None) -> list[dict[str, Any]]:
    if history is None:
        return []
    return [
        {
            "strategy": item.get("strategy", {}),
            "operation": item["operation"],
            "eligible": item["eligible"],
            "improved_case_count": len(item.get("improved_cases", [])),
            "regressed_case_count": len(item.get("regressed_cases", [])),
            "regression_failure_counts": item.get("regression_failure_counts", {}),
            "improvement_failure_counts": item.get("improvement_failure_counts", {}),
            "changed_words": item.get("changed_words", 0),
        }
        for item in history.get("evaluations", [])
    ]


def batch_mutate(
    *, baseline_skill: str, development_run_dirs: Iterable[Path], output_dir: Path,
    candidate_count: int = 3, strategy_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not 1 <= candidate_count <= 3:
        raise ValueError("candidate_count must be between 1 and 3")
    if candidate_count != 3:
        raise ValueError("strategy portfolio requires exactly 3 candidates")
    _validate_strategy_history(strategy_history)
    run_dirs = tuple(development_run_dirs)
    signals = development_signals(run_dirs)
    output_dir.mkdir(parents=True, exist_ok=False)
    mutations: list[dict[str, Any]] = []
    candidates: list[str] = []
    if signals:
        strategist = CodexJsonModel(output_dir / "calls" / "portfolio")
        portfolio = strategist.generate(
            role="mutation-strategist",
            instructions=(
                "Design exactly three bounded mutation strategies for improving the supplied interview skill. "
                "The only learning evidence is development_signals and prior_strategy_outcomes; never infer or "
                "request validation or holdout details. Treat prior outcomes as evidence about the mutation "
                "mechanism, not as contract facts. Build a principle-first portfolio with exactly one strategy for "
                "each required principle: admissibility_first, scope_locality, and observable_contract. First state "
                "the causal hypothesis, admissibility test, preservation invariant, and scope boundary; only then "
                "choose replace, delete, or add as the smallest edit mechanism. Operations may repeat because they "
                "are implementation details, not the source of candidate diversity. admissibility_first separates "
                "normative authority from descriptive evidence: an explicit owner decision, approved policy/default, "
                "or explicit delegation may authorize behavior, while repository facts may constrain feasibility or "
                "compatibility but never authorize new observable behavior by themselves. scope_locality applies to "
                "the prescribed behavior or implementation change, not to discovery: inspect broadly enough to find "
                "cross-cutting compatibility, security, migration, data, and integration constraints, then preserve "
                "behavior outside the narrowest authorized change boundary. observable_contract states externally "
                "observable behavior and independently verifiable material constraints, including internal security, "
                "data-integrity, migration, and compatibility obligations, while leaving reversible, non-material "
                "implementation choices to the implementer, who must record every choice in the decision log outside "
                "the contract; only material or explicitly authorized choices may become contract clauses. Every "
                "candidate edit must be "
                "self-contained; it may not rely on a definition introduced only by another candidate or only in "
                "strategy metadata. Prefer positive invariants over growing prohibition lists. Reject "
                "case-specific exceptions and strategies that improve one count by moving defects into material "
                "implementation decisions, authority changes, compatibility regressions, or readiness failures. "
                "Prior improvement_failure_counts identify effects worth preserving; prior "
                "regression_failure_counts identify causal tradeoffs to avoid. Strategy IDs must be distinct and "
                "repository-independent."
            ),
            payload={
                "baseline_skill": baseline_skill,
                "development_signals": signals,
                "prior_strategy_outcomes": _strategy_history_summary(strategy_history),
            },
            schema=STRATEGY_PORTFOLIO_SCHEMA,
        )
        strategies = portfolio["strategies"][:candidate_count]
        _validate_strategy_portfolio(strategies)
        for index, strategy in enumerate(strategies):
            model = CodexJsonModel(output_dir / "calls" / f"strategy-{index + 1}")
            mutation = model.generate(
                role=f"development-mutator-{index + 1}",
                instructions=(
                "Review EVERY development signal independently. Signals are either a material implementation decision, "
                "an invented contract requirement, or a compatibility regression. The target is a contract that "
                "is both correct and executable without creating decision.jsonl. A signal is a skill gap when "
                "the interview should have resolved it through an owner question, repository discovery, an "
                "explicit approved default, or an explicit delegation boundary. Technical choices count when "
                "another reasonable choice changes observable behavior, compatibility, safety, cost, data, "
                "acceptance, or reversibility. Apply the supplied strategy as exactly one bounded edit to the "
                "baseline skill. Treat its principle, admissibility_test, preservation_invariant, and "
                "scope_boundary as binding acceptance criteria for the edit. Raw decision count is diagnostic "
                "only; non-material recorded choices are not mutation signals and must not be optimized away. "
                "Encode every rule needed to apply the chosen principle in the candidate edit itself; do not refer "
                "to another candidate's rule or leave a critical definition only in strategy metadata. Repository "
                "facts constrain the contract but do not independently authorize new behavior. Scope locality must "
                "not reduce discovery needed to identify cross-cutting material constraints. Record every "
                "implementer choice in the decision log, but never promote a reversible non-material choice into "
                "the contract merely to make it traceable. Express the causal rule as a positive invariant without "
                "embedding examples copied from observed failures. "
                "The anchor_exact_text must be copied verbatim from one unique baseline passage. "
                "For replace, provide its replacement; for delete, replacement_text must be empty; for add, "
                "provide text inserted immediately after the anchor. Anchor and replacement are each limited to "
                "120 words. Do not add repository-specific names or solutions. Absence of evidence for broader "
                "behavior does not authorize narrower behavior, exclusions, preservation guarantees, or "
                "implementation boundaries. Preserve the skill's duty to ask about unresolved material choices "
                "even while suppressing unsupported inferred requirements. Do not grow a prohibition list or "
                "encode a repository-specific exception when a positive invariant can express the causal rule. "
                "Include exactly one signal_reviews "
                "item for every input signal and list every skill-gap signal ID in "
                "addressed_signal_ids that this single edit directly addresses."
                ),
                payload={
                    "baseline_skill": baseline_skill,
                    "development_signals": signals,
                    "strategy": strategy,
                },
                schema=MUTATION_SCHEMA,
            )
            _validate_reviews(mutation, signals)
            if mutation["operation"] != strategy["operation"]:
                raise RuntimeError("candidate edit operation drifted from its strategy")
            candidate = _apply_edit(baseline_skill, mutation)
            mutation["strategy"] = strategy
            mutations.append(mutation)
            candidates.append(candidate)
        if len(set(candidates)) != len(candidates):
            raise RuntimeError("mutator strategies must produce distinct candidates")
        performed = True
    else:
        portfolio = {"strategies": [], "rationale": "No development signals were recorded."}
        mutation = {
            "operation": "add", "anchor_exact_text": "", "replacement_text": "",
            "change_summary": "No development signals were recorded.",
            "signal_reviews": [], "addressed_signal_ids": [],
        }
        mutations = [mutation]
        candidates = [baseline_skill]
        performed = False
    audit = {
        "schema": "DevelopmentMutatorInputAudit.v5",
        "allowed_mutator_top_level_keys": ["baseline_skill", "development_signals", "strategy"],
        "allowed_strategist_top_level_keys": [
            "baseline_skill", "development_signals", "prior_strategy_outcomes",
        ],
        "allowed_signal_keys": ["case_alias_sha256", "signal_id", "source", "text"],
        "signal_rows_received": len(signals),
        "signal_rows_reviewed_per_strategy": [len(item["signal_reviews"]) for item in mutations],
        "raw_case_identifiers_exposed": False,
        "source_partitions": ["development"],
        "gold_or_test_or_oracle_payload_exposed": False,
        "prior_strategy_outcomes_exposed": strategy_history is not None,
    }
    if signals:
        portfolio_records = sorted((output_dir / "calls" / "portfolio").glob("*.json"))
        if len(portfolio_records) != 1:
            raise RuntimeError("mutation strategist recorded-call count drifted")
        portfolio_payload = json.loads(
            portfolio_records[0].read_text(encoding="utf-8")
        )["input"]
        if set(portfolio_payload) != {
            "baseline_skill", "development_signals", "prior_strategy_outcomes",
        }:
            raise RuntimeError("mutation strategist input crossed its allowlist")
        records = sorted((output_dir / "calls").glob("strategy-*/*.json"))
        if len(records) != candidate_count:
            raise RuntimeError("batch mutator recorded-call count drifted")
        for record in records:
            payload = json.loads(record.read_text(encoding="utf-8"))["input"]
            if set(payload) != {"baseline_skill", "development_signals", "strategy"}:
                raise RuntimeError("batch mutator input crossed its allowlist")
            if any(set(item) != set(audit["allowed_signal_keys"]) for item in payload["development_signals"]):
                raise RuntimeError("batch mutator signal crossed its allowlist")
    audit_path = output_dir / "mutation-input-audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for index, candidate in enumerate(candidates, 1):
        (output_dir / f"candidate-{index}-SKILL.md").write_text(candidate, encoding="utf-8")
    # Compatibility alias for the standalone mutation command; execution selects explicitly.
    (output_dir / "candidate-SKILL.md").write_text(candidates[0], encoding="utf-8")
    signal_corpus_sha256 = hashlib.sha256(canonical_json_bytes(signals)).hexdigest()
    source_counts = {
        source: sum(item["source"] == source for item in signals)
        for source in (
            "material_decision", "invented_requirement", "compatibility_regression",
        )
    }
    manifest = {
        "schema": "DevelopmentSignalMutation.v6",
        "development_cases": 8,
        "signal_count": len(signals),
        "signal_source_counts": source_counts,
        "candidate_count": len(candidates),
        "skill_gap_counts": [sum(row["skill_gap"] for row in item["signal_reviews"]) for item in mutations],
        "reviewed_signal_ids_by_candidate": [sorted(row["signal_id"] for row in item["signal_reviews"]) for item in mutations],
        "addressed_signal_ids_by_candidate": [sorted(item["addressed_signal_ids"]) for item in mutations],
        "signal_corpus_sha256": signal_corpus_sha256,
        "mutation_performed": performed,
        "baseline_sha256": hashlib.sha256(baseline_skill.encode()).hexdigest(),
        "candidate_sha256s": [hashlib.sha256(item.encode()).hexdigest() for item in candidates],
        "source_partitions": ["development"],
        "mutation_calls": candidate_count + 1 if signals else 0,
        "mutation_input_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
    }
    (output_dir / "mutation.json").write_text(
        json.dumps(
            {"portfolio": portfolio, "candidate_edits": mutations},
            ensure_ascii=False, indent=2,
        ) + "\n", encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return manifest
