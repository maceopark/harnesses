import inspect

from swebench_interview_cases.casegen import (
    DERIVATION_SCHEMA,
    REVIEW_SCHEMA,
    _repository_context,
    derive_and_review_case,
)


def test_generation_and_review_schemas_are_closed():
    assert DERIVATION_SCHEMA["additionalProperties"] is False
    assert DERIVATION_SCHEMA["properties"]["material_decisions"]["minItems"] == 0
    assert REVIEW_SCHEMA["additionalProperties"] is False
    assert REVIEW_SCHEMA["properties"]["dispositions"]["minItems"] == 0


def test_prompts_distinguish_repository_facts_and_sealed_gold() -> None:
    source = inspect.getsource(derive_and_review_case)
    assert "fully determined by the issue-time repository" in source
    assert "no earlier than the latest knowledge_timing" in source
    assert "never invent a question merely" in source
    assert "intentionally sealed" in source
    assert "do not reject merely because" in source
    assert '"fail_to_pass": sources["fail_to_pass"]' in source
    assert '"pass_to_pass": sources["pass_to_pass"]' in source


def test_repository_context_is_discovered_audited_and_sealed(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "config.py").write_text("MODE = 'legacy'\n")
    class Fake:
        def __init__(self, *args, **kwargs): pass
        def generate(self, *, role, **kwargs):
            if role == "case-repository-discovery":
                return {"scope_summary": "config", "facts": [{"id": "mode", "statement": "Legacy mode exists.", "path": "config.py", "line_start": 1, "line_end": 1}], "unknowns": []}
            return {"accepted_fact_ids": ["mode"], "rejected": [], "summary": "supported"}
    monkeypatch.setattr("swebench_interview_cases.casegen.CodexJsonModel", Fake)
    facts, evidence = _repository_context(issue="change mode", repo_root=repo, record_root=tmp_path / "records")
    assert facts[0]["statement"] == "Legacy mode exists."
    assert evidence[0]["id"] == "repository:mode"
    assert evidence[0]["excerpt"] == "MODE = 'legacy'"
