import json
import subprocess

import pytest

from swebench_interview_cases.implementer import (
    DECISION_MATERIALITY_SCHEMA,
    DECISION_MATERIALITY_SCHEMA_VERSION,
    materialize_implementation_materiality, read_decisions,
    run_fresh_implementation, validate_decision_materiality,
)
from swebench_interview_cases.model import CodexWorkspaceImplementer


def valid_decision():
    return {
        "timestamp": "before editing config.py",
        "gap": "default mode is unspecified",
        "options_considered": ["strict", "compatible"],
        "choice": "compatible",
        "reason": "preserve callers",
        "observable_impact": "invalid input remains accepted",
        "reversibility": "change the default later",
    }


def test_missing_decision_log_means_zero_decisions(tmp_path):
    assert read_decisions(tmp_path / "decision.jsonl") == ()


def test_every_decision_row_is_parsed_in_order(tmp_path):
    path = tmp_path / "decision.jsonl"
    first = valid_decision()
    second = {**valid_decision(), "choice": "strict", "reason": "request wording"}
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n")
    assert read_decisions(path) == (first, second)


def test_decision_log_rejects_malformed_or_duplicate_rows(tmp_path):
    path = tmp_path / "decision.jsonl"
    value = valid_decision()
    path.write_text(json.dumps(value) + "\n" + json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_decisions(path)

    value["options_considered"] = ["only one"]
    path.write_text(json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="at least two"):
        read_decisions(path)


def test_implementer_logs_all_autonomous_implementation_choices(
    tmp_path, monkeypatch,
):
    captured = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["prompt"] = kwargs["input"]
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump({"completed": True, "summary": "done", "tests": []}, output)
        return Completed()

    monkeypatch.setattr("swebench_interview_cases.model.subprocess.run", fake_run)
    implementer = CodexWorkspaceImplementer(tmp_path / "call.json")
    implementer.implement(
        repository=tmp_path, public_request="fix it", audited_evidence={},
        contract={"summary": "observable behavior"},
    )

    prompt = captured["prompt"]
    assert "ANY autonomous implementation decision" in prompt
    assert "Logging is mandatory evidence" in prompt


def test_decision_materiality_is_exactly_the_boundary_flag_union():
    minor = {
        "decision_index": 0, "changes_initial_decision": False,
        "crosses_authority_boundary": False, "high_risk": False,
        "material": False, "reason": "internal choice",
    }
    material = {
        "decision_index": 1, "changes_initial_decision": True,
        "crosses_authority_boundary": False, "high_risk": False,
        "material": True, "reason": "reversed owner choice",
    }
    value = {
        "schema": DECISION_MATERIALITY_SCHEMA_VERSION,
        "reviews": [minor, material], "summary": "reviewed",
    }
    assert validate_decision_materiality(value, decision_count=2) is value
    with pytest.raises(ValueError, match="contradicts"):
        validate_decision_materiality(
            {
                "schema": DECISION_MATERIALITY_SCHEMA_VERSION,
                "reviews": [minor, {**material, "material": False}], "summary": "bad",
            },
            decision_count=2,
        )


def test_decision_materiality_schema_declares_schema_field_type():
    schema_field = DECISION_MATERIALITY_SCHEMA["properties"]["schema"]
    assert schema_field == {
        "type": "string", "const": DECISION_MATERIALITY_SCHEMA_VERSION,
    }


def test_fresh_implementation_seals_raw_and_material_decision_counts(
    tmp_path, monkeypatch,
):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=source, check=True)
    (source / "value.txt").write_text("before\n")
    subprocess.run(["git", "add", "value.txt"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=source, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout.strip()

    class FakeImplementer:
        def __init__(self, record_path): self.record_path = record_path
        def implement(self, *, repository, **kwargs):
            self.record_path.write_text("{}")
            (repository / "value.txt").write_text("after\n")
            (repository / "decision.jsonl").write_text(json.dumps(valid_decision()) + "\n")
            return {"completed": True, "summary": "done", "tests": []}

    class FakeReviewer:
        def __init__(self, record_root): self.record_root = record_root
        def generate(self, **kwargs):
            return {"schema": DECISION_MATERIALITY_SCHEMA_VERSION, "reviews": [{
                "decision_index": 0, "changes_initial_decision": False,
                "crosses_authority_boundary": False, "high_risk": False,
                "material": False, "reason": "internal reversible choice",
            }], "summary": "one minor decision"}

    monkeypatch.setattr("swebench_interview_cases.implementer.CodexWorkspaceImplementer", FakeImplementer)
    monkeypatch.setattr("swebench_interview_cases.implementer.CodexJsonModel", FakeReviewer)
    manifest = run_fresh_implementation(
        source_repository=source, base_commit=base, public_request="change value",
        audited_evidence={}, contract={"summary": "value changes"},
        output_dir=tmp_path / "implementation",
    )
    assert manifest["decision_count"] == 1
    assert manifest["material_decision_count"] == 0
    assert (tmp_path / "implementation" / "decision-materiality.json").is_file()


def test_legacy_implementation_materiality_is_overlayed_without_mutating_source(
    tmp_path, monkeypatch,
):
    source = tmp_path / "source"
    source.mkdir()
    decision = valid_decision()
    (source / "decision.jsonl").write_text(json.dumps(decision) + "\n")
    (source / "implementation.patch").write_text("patch\n")
    (source / "implementation-manifest.json").write_text(json.dumps({
        "schema": "FreshImplementationRun.v1", "decision_count": 1,
        "artifact_sha256": {},
    }))

    class FakeReviewer:
        def __init__(self, record_root): self.record_root = record_root
        def generate(self, **kwargs):
            return {"schema": DECISION_MATERIALITY_SCHEMA_VERSION, "reviews": [{
                "decision_index": 0, "changes_initial_decision": False,
                "crosses_authority_boundary": False, "high_risk": False,
                "material": False, "reason": "internal reversible choice",
            }], "summary": "minor"}

    monkeypatch.setattr("swebench_interview_cases.implementer.CodexJsonModel", FakeReviewer)
    output = tmp_path / "overlay"
    manifest = materialize_implementation_materiality(
        source_dir=source, output_dir=output, public_request="fix it",
        audited_evidence={}, contract={"summary": "fix"},
    )
    assert manifest["decision_count"] == 1
    assert manifest["material_decision_count"] == 0
    assert (output / "decision.jsonl").is_symlink()
    assert not (source / "decision-materiality.json").exists()
