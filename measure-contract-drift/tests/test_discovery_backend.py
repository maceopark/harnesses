import json
import subprocess
from pathlib import Path

import pytest

from driftbench.discovery_backend import (
    RUNTIME_CONTRACT, build_evaluator_prompt, build_evolution_prompt, build_generator_prompt,
    _run_isolated, normalize_compiler_inputs, parse_postmortem_markdown,
    verify_compiled_selection_lineage,
)


def test_timeout_kills_the_entire_model_process_group(monkeypatch) -> None:
    class Process:
        pid = 123
        returncode = -9
        calls = 0

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


def test_generator_input_contains_only_seed_and_runtime_contract() -> None:
    prompt = build_generator_prompt("# Interview\nAsk material questions.", "runtime-xyz")
    assert "Ask material questions" in prompt
    assert "runtime-xyz" in prompt
    for forbidden in ("bookmarks", "validation finding", "postmortem score", "candidate rank"):
        assert forbidden not in prompt


def test_evolution_input_contains_parent_and_train_feedback_but_no_validation_surface() -> None:
    feedback = {"schema": "DiscoveryGenerationFeedback.v1", "generation": 0,
                "root_causes": ["decision-miss"], "evidence": ["duplicate policy escaped"]}
    prompt = build_evolution_prompt("# Parent\nAsk precisely.", feedback, "runtime-xyz")
    assert "Ask precisely" in prompt and "decision-miss" in prompt
    assert "duplicate policy escaped" in prompt and "runtime-xyz" in prompt
    for forbidden in ("fidelity_lcb", "pareto_archive", "validation score", "candidate_id"):
        assert forbidden not in prompt


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
