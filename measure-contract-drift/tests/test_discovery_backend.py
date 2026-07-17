import json
import subprocess
from pathlib import Path

import pytest

from driftbench.discovery import CellSpec, InterviewDecisionV2, OwnerCard, OwnerExchange
from driftbench.discovery_backend import (
    MUTATION_BOUNDARY, RUNTIME_CONTRACT, DirectCodexDiscoveryBackend, InvocationResult,
    _fixed_contract_surface,
    build_evaluator_prompt, build_evolution_prompt, build_generator_prompt,
    build_implementation_prompt, interview_blockers,
    _run_isolated, _tool_summary, normalize_compiler_inputs, parse_postmortem_markdown,
    parse_contract_draft, suppress_duplicate_owner_authority, unique_cell_decision_ids,
    validate_implementation_outcome, verify_compiled_selection_lineage,
)


def test_tool_summary_projects_only_short_progress_events() -> None:
    assert _tool_summary(json.dumps({
        "type": "item.started",
        "item": {"type": "command_execution", "command": "rg --files\nsecond line"},
    })) == "command: rg --files"
    assert _tool_summary(json.dumps({
        "type": "item.started",
        "item": {"type": "mcp_tool_call", "server": "repo", "tool": "search"},
    })) == "MCP repo.search"
    assert _tool_summary(json.dumps({
        "type": "item.completed",
        "item": {"type": "file_change", "changes": [{"path": "a.py"}]},
    })) == "file change: 1 path(s)"
    assert _tool_summary(json.dumps({
        "type": "item.completed",
        "item": {"type": "command_execution", "command": "rg --files"},
    })) is None


def test_timeout_kills_the_entire_model_process_group(monkeypatch) -> None:
    class Process:
        pid = 123
        returncode = -9
        calls = 0

        def poll(self):
            return None

        def communicate(self, *, input=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["codex"], timeout)
            return "", ""

    process = Process()
    popen_options = {}
    killed = []

    def fake_popen(argv, **options):
        popen_options.update(options)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("driftbench.discovery_backend.os.killpg",
                        lambda pid, signal_number: killed.append((pid, signal_number)))

    with pytest.raises(subprocess.TimeoutExpired):
        _run_isolated(["codex"], cwd=Path("."), input_text="prompt", timeout=1)

    assert popen_options["start_new_session"] is True
    assert killed and killed[0][0] == process.pid
    assert process.calls == 2


def test_interrupt_kills_the_entire_model_process_group(monkeypatch) -> None:
    class Process:
        pid = 456
        returncode = -9

        def poll(self):
            return None

        def communicate(self, *, input=None, timeout=None):
            if input is not None:
                raise KeyboardInterrupt
            return "", ""

    process = Process()
    killed = []
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr("driftbench.discovery_backend.os.killpg",
                        lambda pid, signal_number: killed.append((pid, signal_number)))

    with pytest.raises(KeyboardInterrupt):
        _run_isolated(["codex"], cwd=Path("."), input_text="prompt", timeout=1)

    assert killed and killed[0][0] == process.pid


def test_generator_input_contains_only_seed_and_runtime_contract() -> None:
    prompt = build_generator_prompt("# Interview\nAsk material questions.", "runtime-xyz")
    assert "Ask material questions" in prompt
    assert "runtime-xyz" in prompt
    assert MUTATION_BOUNDARY in prompt
    assert "Do not add or alter contract compilation" in prompt
    for forbidden in ("bookmarks", "validation finding", "postmortem score", "candidate rank"):
        assert forbidden not in prompt


def test_turn_local_decision_id_is_made_unique_across_the_cell() -> None:
    raw = {
        "schema": "StructuredInterviewTurn.v2", "action": "ask",
        "decisions": [{"decision_id": "DEC-001", "question": "Next?"}],
        "contract_draft": None,
    }

    normalized = unique_cell_decision_ids(
        raw, used_ids={"DEC-001"}, turn_number=3,
    )

    assert normalized["decisions"][0]["decision_id"] == "DEC-T03-01"
    assert raw["decisions"][0]["decision_id"] == "DEC-001"


def test_contract_draft_parser_repairs_only_duplicate_trailing_closing_braces() -> None:
    assert parse_contract_draft('{"status":"complete"}}') == {"status": "complete"}
    with pytest.raises(RuntimeError, match="malformed JSON"):
        parse_contract_draft('{"status":"complete"} trailing')
    with pytest.raises(RuntimeError, match="non-empty JSON object"):
        parse_contract_draft('[]')


def test_evolution_input_contains_parent_and_train_feedback_but_no_validation_surface() -> None:
    feedback = {"schema": "DiscoveryGenerationFeedback.v1", "generation": 0,
                "root_causes": ["decision-miss"], "evidence": ["duplicate policy escaped"]}
    intent = {"intent_id": "interaction-redesign", "label": "Redesign",
              "directive": "Change ordering and termination."}
    prompt = build_evolution_prompt(
        "# Interview\nImmutable seed.", "Ask precisely.", feedback, intent, "runtime-xyz"
    )
    assert "Immutable seed" in prompt and "Ask precisely" in prompt and "decision-miss" in prompt
    assert "duplicate policy escaped" in prompt and "runtime-xyz" in prompt
    assert "interaction-redesign" in prompt and "Change ordering and termination" in prompt
    assert MUTATION_BOUNDARY in prompt
    assert "fixed runtime infrastructure" in prompt
    assert "replaces the parent overlay; it is not a delta to append" in prompt
    assert "EDITABLE PARENT OVERLAY" in prompt and "IMMUTABLE SEED" in prompt
    for forbidden in ("fidelity_lcb", "pareto_archive", "validation score", "candidate_id"):
        assert forbidden not in prompt


def test_fixed_contract_surface_is_transplanted_from_current_skill_sections() -> None:
    skill = "intro\n## 5. Small Execution Contract\nfixed contract\n## 6. Compile the Candidate Contract\nfixed compiler\n## 7. Implementation Planning\nnot used"
    surface = _fixed_contract_surface(skill, "canonical JSON contracts")
    assert "fixed contract" in surface and "fixed compiler" in surface
    assert "canonical JSON contracts" in surface
    assert "Implementation Planning" not in surface


def test_evaluator_prompt_is_allowlist_built_and_blinded() -> None:
    prompt = build_evaluator_prompt(
        request="Support completing a todo.", transcript=[{"decision_id": "DEC-1"}],
        compiler_bundle={"contract_digest": "a" * 64},
        implementation_return={"status": "completed"}, implementation_diff="+done",
        execution_evidence=[{"command": "pytest", "result": "passed"}],
    )
    payload = json.loads(prompt.split("EVIDENCE:\n", 1)[1])
    assert set(payload) == {"request", "transcript", "compiler_evidence_bundle",
                            "implementation_return", "implementation_diff",
                            "direct_execution_evidence"}
    lowered = prompt.lower()
    for secret in ("candidate_id", "candidate skill", "ranking", "scoring formula", "self-score"):
        # They may appear only in the explicit statement that they are unavailable.
        assert lowered.count(secret) <= 1


def test_incomplete_or_unresolved_owner_authority_blocks_implementation() -> None:
    blockers = interview_blockers(
        {"status": "incomplete", "unresolved_material_decisions": ["Choose duplicate policy."]},
        {"applicable_item_ids": ["columns", "duplicates"],
         "resolved_item_ids": ["columns"], "ambiguous_decision_ids": ["collision"]},
    )
    assert blockers == (
        "contract-draft-status:incomplete",
        "unresolved-material-decision:Choose duplicate policy.",
        "unresolved-owner-item:duplicates",
        "ambiguous-owner-decision:collision",
    )
    assert interview_blockers(
        {"status": "complete", "unresolved_material_decisions": []},
        {"applicable_item_ids": ["columns"], "resolved_item_ids": ["columns"],
         "ambiguous_decision_ids": []},
    ) == ()


def test_resolved_owner_item_repetition_is_recorded_without_duplicate_authority(
    tmp_path: Path,
) -> None:
    backend = object.__new__(DirectCodexDiscoveryBackend)
    backend.workspace = tmp_path
    backend._invoke = lambda *_args, **_kwargs: InvocationResult({"exchanges": [{
        "decision_id": "DEC-2", "verdict": "matched", "item_id": "duplicates",
        "option_id": "reject", "answer": "Reject duplicates.",
    }]}, 9)
    card = OwnerCard.model_validate({
        "schema": "DiscoveryOwnerCard.v1", "case_id": "contacts-csv",
        "items": [{"item_id": "duplicates", "owner_statement": "Reject duplicates.",
                   "materiality": "critical", "forbidden_outcomes": []}],
        "probes": [], "source_markdown": "# Owner",
    })
    decision = InterviewDecisionV2.model_validate({
        "decision_id": "DEC-2", "question": "Again?",
        "options": [
            {"option_id": "reject", "label": "Reject", "normative_statement": "Reject.",
             "compatible": True},
            {"option_id": "merge", "label": "Merge", "normative_statement": "Merge.",
             "compatible": True},
        ],
        "recommended_option_id": "reject", "recommendation_rationale": "Safer.",
        "impact_boundary": "Duplicate rows.",
    })

    exchanges, tokens = backend._resolve_owner(
        card=card, decisions=[decision], resolved_item_ids={"duplicates"},
        cell_id="cell", turn_number=2,
    )

    assert tokens == 9
    assert exchanges[0].verdict == "irrelevant"
    assert exchanges[0].item_id is None and exchanges[0].option_id is None


def test_same_owner_item_is_granted_only_once_within_one_response_batch() -> None:
    exchanges = [
        OwnerExchange(decision_id="DEC-1", verdict="matched", item_id="amount",
                      option_id="positive", answer="Positive amount."),
        OwnerExchange(decision_id="DEC-2", verdict="matched", item_id="amount",
                      option_id="finite", answer="Positive amount."),
    ]

    normalized = suppress_duplicate_owner_authority(exchanges, set())

    assert normalized[0].verdict == "matched" and normalized[0].item_id == "amount"
    assert normalized[1].verdict == "irrelevant" and normalized[1].item_id is None


def test_implementation_prompt_requires_blocking_and_uses_an_exact_log_path() -> None:
    prompt = build_implementation_prompt(
        {"requirements": [], "bounded_implementation_delegations": []},
        ".ultimateinterview/cell-1/decision.jsonl",
    )
    assert "blocked-contract-gap" in prompt
    assert "do not modify the repository" in prompt
    assert ".ultimateinterview/cell-1/decision.jsonl" in prompt
    assert "decision log cannot authorize" in prompt


def test_implementation_outcome_fails_closed_on_gap_or_unbounded_log() -> None:
    contract = {"bounded_implementation_delegations": []}
    assert validate_implementation_outcome(
        implementation={"status": "completed", "contract_gaps": []},
        implementation_diff="+authorized", decisions=(), build_contract=contract,
    ) is False
    assert validate_implementation_outcome(
        implementation={"status": "blocked-contract-gap", "contract_gaps": ["duplicate policy"]},
        implementation_diff="", decisions=(), build_contract=contract,
    ) is True
    with pytest.raises(RuntimeError, match="modified"):
        validate_implementation_outcome(
            implementation={"status": "blocked-contract-gap", "contract_gaps": ["gap"]},
            implementation_diff="+unauthorized", decisions=(), build_contract=contract,
        )
    with pytest.raises(RuntimeError, match="bounded implementation delegation"):
        validate_implementation_outcome(
            implementation={"status": "completed", "contract_gaps": []},
            implementation_diff="+change", decisions=({"observable_impact": "none"},),
            build_contract=contract,
        )


def test_evaluate_preserves_incomplete_draft_and_never_starts_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = object.__new__(DirectCodexDiscoveryBackend)
    backend.protocol = tmp_path / "unused-protocol"
    backend.interview = lambda **_kwargs: (
        [{"schema": "StructuredInterviewTurn.v2", "action": "complete", "decisions": [],
          "contract_draft": {"status": "incomplete",
                             "unresolved_material_decisions": ["Choose duplicate policy."]}}],
        [{"decision_id": "columns", "option_id": "named",
          "normative_statement": "Use named columns.", "authority_id": "OWNER-columns"}],
        [{"decision_id": "columns", "verdict": "matched", "item_id": "columns",
          "option_id": "named", "answer": "Use named columns."}],
        {"status": "incomplete", "unresolved_material_decisions": ["Choose duplicate policy."]},
        17,
    )
    monkeypatch.setattr("driftbench.discovery_backend._initialize_git_worktree", lambda _repo: None)
    repo = tmp_path / "repo"; repo.mkdir()
    evidence = tmp_path / "evidence"; evidence.mkdir()
    card = OwnerCard.model_validate({
        "schema": "DiscoveryOwnerCard.v1", "case_id": "contacts-csv",
        "items": [
            {"item_id": "columns", "owner_statement": "Use named columns.",
             "materiality": "critical", "forbidden_outcomes": []},
            {"item_id": "duplicates", "owner_statement": "Last row wins.",
             "materiality": "material", "forbidden_outcomes": []},
        ], "probes": [], "source_markdown": "# Owner",
    })

    result = backend.evaluate(
        cell=CellSpec(candidate_id="g00-control", partition="train",
                      case_id="contacts-csv", repetition=1),
        prompt="Import contacts", skill="# Interview", repo=repo,
        attempt_dir=evidence, owner_card=card,
    )

    assert result["hard_veto"] is True and result["discovery_success"] is False
    marker = json.loads((evidence / "interview-blocked.json").read_text())
    assert marker["details"]["contract_draft"]["status"] == "incomplete"
    assert "unresolved-owner-item:duplicates" in marker["reasons"]
    assert not (evidence / "implementation.diff").exists()
    assert not list(evidence.rglob("build-contract.json"))


def test_parse_schema3_postmortem_counts_and_findings() -> None:
    report = """# Ultimateinterview Postmortem

postmortem_schema: 3
contract_digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
evaluator: independent
evaluated_at: 2026-07-15T00:00:00Z

## Conclusion

**Verdict:** one miss

**Counts:** 2 contract requirements — 1 fulfilled, 1 escaped, 0 scope-drift, 1 divergent, 0 deferred, 0 unverifiable.

## Findings

| ID | Class | Behavior | Evidence | Root cause | Owner action |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | fulfilled | a | pass | none | none |
| REQ-002 | divergent-implementation | b | fail | implementation-drift | fix |
| ESC-001 | escaped-requirement | c | diff | discovery-miss | decide |

## Verification

| VER-ID | Result | Evidence |
| --- | --- | --- |
| VER-001 | passed | pass |
"""
    parsed = parse_postmortem_markdown(report)
    assert parsed["counts"] == {"contract_requirements": 2, "fulfilled": 1, "escaped": 1,
                                 "scope_drift": 0, "divergent": 1, "deferred": 0,
                                 "unverifiable": 0}
    assert [row["id"] for row in parsed["findings"]] == ["REQ-001", "REQ-002", "ESC-001"]


def test_parser_rejects_inconsistent_requirement_counts() -> None:
    report = """# Ultimateinterview Postmortem
postmortem_schema: 3
contract_digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
## Conclusion
**Counts:** 2 contract requirements — 2 fulfilled, 0 escaped, 0 scope-drift, 1 divergent, 0 deferred, 0 unverifiable.
"""
    with pytest.raises(ValueError, match="inconsistent"):
        parse_postmortem_markdown(report)


def test_dynamic_authority_lineage_rejects_tamper() -> None:
    selection = {"authority_id": "OWNER-1", "normative_statement": "Reject duplicates."}
    register = {"authorities": [{"id": "OWNER-1", "statement": "Reject duplicates."}]}
    contract = {"requirements": [{"id": "REQ-1", "text": "Reject duplicates.",
                                   "authority_refs": ["OWNER-1"]}]}
    verify_compiled_selection_lineage([selection], register, contract)
    contract["requirements"][0]["text"] = "Accept duplicates."
    with pytest.raises(RuntimeError, match="lineage"):
        verify_compiled_selection_lineage([selection], register, contract)


def test_compiler_input_normalization_is_representation_only_and_deterministic() -> None:
    authority = {"id": "OWNER-1", "statement": "Reject duplicates.",
                 "scope": ["bookmark tag behavior"], "constraints": [],
                 "preserved_behaviors": []}
    reconciliation = {"authorities": [authority]}
    discovery = {"authorities": [authority],
                 "requirements": [{"scope": ["bookmark tag behavior"]}]}
    normalized_reconciliation, normalized_discovery = normalize_compiler_inputs(
        reconciliation, discovery)
    token = normalized_reconciliation["authorities"][0]["scope"][0]
    assert token.startswith("scope:")
    assert normalized_discovery["requirements"][0]["scope"] == [token]
    assert normalized_reconciliation["authorities"][0]["constraints"] == [
        "Reject duplicates."]
    assert authority["scope"] == ["bookmark tag behavior"]
