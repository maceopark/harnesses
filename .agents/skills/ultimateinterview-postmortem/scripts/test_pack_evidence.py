#!/usr/bin/env -S uv run --script
# noqa: SIZE_OK  — behavior-facing CLI adapter tests share one fixture harness
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "pytest>=8.0",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/test_pack_evidence.py
# ──────────────────

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pack_evidence

runner = CliRunner()

LESSONS_MD = """# Lessons

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
| free-text input | misuse | enumeration-miss | e | 2026-07-01 | 4/4 |
| temporal word | domain/state | trigger-too-narrow | e | 2026-07-01 | 3/3 |

## Retired

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
"""


@pytest.fixture(autouse=True)
def _isolate_default_lessons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the real global lessons store out of every bundle test; tests that
    exercise snapshotting pass their own --lessons paths."""
    monkeypatch.setattr(
        pack_evidence, "GLOBAL_LESSONS_PATH", tmp_path / "no-such-global-lessons.md"
    )


VALID_LEDGER = {
    "entries": [
        {
            "id": "g1",
            "requirement": "todo shows today view",
            "ambiguity_score": 0,
            "impact_weight": 5,
            "status": "Triangulated",
            "evidence_channels": ["from-user", "from-code"],
        }
    ]
}

VALID_DECISION = {
    "decision": "used ISO dates in store",
    "reason": "spec named no serialization format",
    "spec_citation": "REQ-3",
    "alternatives": ["epoch seconds"],
    "impact": "store file format",
    "self_class": "spec_gap",
}


def make_session(tmp_path: Path) -> Path:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "handoff.md").write_text("# Part 1\nREQ-3 ...\n", encoding="utf-8")
    (session / "ledger.json").write_text(json.dumps(VALID_LEDGER), encoding="utf-8")
    return session


def make_ulw(tmp_path: Path, events: list[dict]) -> Path:
    ulw = tmp_path / ".omo" / "ulw-loop"
    ulw.mkdir(parents=True)
    (ulw / "brief.md").write_text("brief", encoding="utf-8")
    (ulw / "goals.json").write_text(json.dumps({"version": 1, "goals": []}), encoding="utf-8")
    (ulw / "ledger.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8"
    )
    return ulw


def make_evidence(tmp_path: Path, slug: str = "demo") -> Path:
    evidence = tmp_path / ".omo" / "evidence" / slug
    evidence.mkdir(parents=True)
    (evidence / "run.txt").write_text("command passed\n", encoding="utf-8")
    nested = evidence / "nested"
    nested.mkdir()
    (nested / "result.json").write_text('{"ok": true}\n', encoding="utf-8")
    return evidence


def read_bundle(session: Path) -> Any:
    return json.loads((session / "evidence_bundle.json").read_text(encoding="utf-8"))


def test_full_bundle_packs_all_sections(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    events = [
        {
            "kind": "evidence_captured",
            "goalId": "g1",
            "criterionId": "c1",
            "evidence": ".omo/evidence/demo/run.txt",
        },
        {"kind": "criterion_failed", "criterionId": "c2"},
        {"kind": "criteria_revised", "before": "a", "after": "b"},
        {"kind": "goal_needs_user_decision", "signature": "auth"},
        {"kind": "steering_received"},
    ]
    ulw = make_ulw(tmp_path, events)
    evidence = make_evidence(tmp_path)
    (session / "decisions.jsonl").write_text(
        json.dumps(VALID_DECISION) + "\n", encoding="utf-8"
    )
    diff_file = tmp_path / "impl.diff"
    diff_file.write_text("--- a/x\n+++ b/x\n", encoding="utf-8")

    result = runner.invoke(
        pack_evidence.app,
        [str(session), "--ulw-dir", str(ulw), "--diff-file", str(diff_file)],
    )
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["schema_version"] == 5
    assert bundle["lessons"]["stores"] == []  # default paths absent in tmp (global isolated)
    assert bundle["spec"]["interview_ledger"][0]["id"] == "g1"
    assert bundle["decisions"][0]["self_class"] == "spec_gap"
    assert bundle["execution"]["present"] is True
    assert len(bundle["execution"]["ledger_events"]) == 5
    assert [e["kind"] for e in bundle["execution"]["criterion_events"]] == [
        "evidence_captured",
        "criterion_failed",
    ]
    assert bundle["execution"]["revisions"][0]["kind"] == "criteria_revised"
    assert bundle["execution"]["user_decision_blockers"][0]["signature"] == "auth"
    assert bundle["execution"]["event_kind_counts"]["steering_received"] == 1
    assert bundle["sources"]["evidence_dir"] == str(evidence.resolve())
    assert [file["path"] for file in bundle["artifacts"]["files"]] == [
        ".omo/evidence/demo/nested/result.json",
        ".omo/evidence/demo/run.txt",
    ]
    assert bundle["artifacts"]["files"][0]["kind"] == "data"
    assert bundle["artifacts"]["files"][1]["id"] == pack_evidence.artifact_id(
        ".omo/evidence/demo/run.txt"
    )
    assert bundle["artifacts"]["files"][1]["kind"] == "log"
    assert bundle["artifacts"]["files"][1]["referenced_by"] == [
        {
            "source": "execution.criterion_events",
            "index": 0,
            "kind": "evidence_captured",
            "goal_id": "g1",
            "criterion_id": "c1",
        }
    ]
    assert bundle["artifacts"]["files"][1]["text"] == "command passed\n"
    assert len(bundle["artifacts"]["files"][1]["sha256"]) == 64
    assert bundle["diff"]["text"].startswith("--- a/x")
    assert bundle["contract"]["compatibility_mode"] == "legacy-v4"
    assert bundle["contract"]["build_contract"] is None
    assert bundle["contract"]["execution_return"] is None
    assert len(bundle["missing_evidence"]) == 2
    assert bundle["warnings"] == []


def test_explicit_evidence_dir_is_collected(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = make_evidence(tmp_path, "custom")
    result = runner.invoke(
        pack_evidence.app,
        [str(session), "--evidence-dir", str(evidence)],
    )
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["sources"]["evidence_dir"] == str(evidence.resolve())
    assert bundle["artifacts"]["present"] is True
    assert len(bundle["artifacts"]["files"]) == 2


def test_relative_evidence_dir_is_resolved_from_repo_root(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    make_evidence(tmp_path, "custom")
    result = runner.invoke(
        pack_evidence.app,
        [
            str(session),
            "--repo-root",
            str(tmp_path),
            "--evidence-dir",
            ".omo/evidence/custom",
        ],
    )
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["sources"]["evidence_dir"] == str(
        (tmp_path / ".omo" / "evidence" / "custom").resolve()
    )
    assert [file["path"] for file in bundle["artifacts"]["files"]] == [
        ".omo/evidence/custom/nested/result.json",
        ".omo/evidence/custom/run.txt",
    ]


def test_missing_decisions_is_recorded_not_fatal(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["decisions"] == []
    assert any("decisions.jsonl absent" in note for note in bundle["missing_evidence"])


def test_empty_decisions_file_is_valid_and_not_missing(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    (session / "decisions.jsonl").write_text("", encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["decisions"] == []
    assert not any("decisions.jsonl absent" in note for note in bundle["missing_evidence"])


def test_malformed_decision_line_fails_closed(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    (session / "decisions.jsonl").write_text(
        json.dumps(VALID_DECISION) + "\n" + json.dumps({"decision": "x"}) + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 1
    assert "line 2" in result.output
    assert not (session / "evidence_bundle.json").exists()


def test_camel_case_decision_field_is_rejected(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = dict(VALID_DECISION)
    record.pop("spec_citation")
    record["specCitation"] = "REQ-3"
    (session / "decisions.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 1
    assert "specCitation" in result.output
    assert "snake_case" in result.output


def test_unknown_self_class_is_rejected(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    record = dict(VALID_DECISION, self_class="vibes")
    (session / "decisions.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 1
    assert "self_class" in result.output


def test_missing_ulw_dir_marks_execution_absent(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["execution"]["present"] is False
    assert any("--ulw-dir" in note for note in bundle["missing_evidence"])
    assert any("diff" in note for note in bundle["missing_evidence"])


def test_malformed_ulw_ledger_line_is_warning_not_fatal(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    ulw = make_ulw(tmp_path, [{"kind": "evidence_captured"}])
    with (ulw / "ledger.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    result = runner.invoke(pack_evidence.app, [str(session), "--ulw-dir", str(ulw)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert len(bundle["execution"]["ledger_events"]) == 1
    assert any("line 2" in note for note in bundle["warnings"])


def test_missing_handoff_fails_closed(tmp_path: Path) -> None:
    session = tmp_path / ".ultimateinterview" / "demo"
    session.mkdir(parents=True)
    (session / "ledger.json").write_text(json.dumps(VALID_LEDGER), encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 1
    assert "handoff.md" in result.output




def captured_output_record(
    command: str = "bash -c 'echo hi'", stdout: str = "hi"
) -> dict[str, object]:
    full_stdout = b"hello"
    digest = pack_evidence.hashlib.sha256(" ".join(command.split()).encode("utf-8")).hexdigest()
    return {
        "marker": "CAPTURED-OUTPUT",
        "spec_row_number": 1,
        "check": "Output capture",
        "kind": "test",
        "exact_command": command,
        "command_digest": digest,
        "effective_heads": list(pack_evidence.effective_heads(command)),
        "cwd": "/repo",
        "started_at": "2026-07-10T00:00:00+00:00",
        "ended_at": "2026-07-10T00:00:01+00:00",
        "spawned": True,
        "timed_out": False,
        "timeout_seconds": 60,
        "exit_code": 0,
        "stdout": stdout,
        "stderr": "",
        "stdout_full_bytes": len(full_stdout),
        "stderr_full_bytes": 0,
        "stdout_sha256": hashlib.sha256(full_stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
    }


def test_captured_output_projects_with_recomputed_file_sha(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = make_evidence(tmp_path)
    capture_path = evidence / "captured-output-row-0001.json"
    capture_path.write_text(json.dumps(captured_output_record()), encoding="utf-8")

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 0, result.output
    projected = read_bundle(session)["artifacts"]["captured_outputs"]
    assert len(projected) == 1
    assert projected[0]["artifact_id"] == pack_evidence.artifact_id(
        ".omo/evidence/demo/captured-output-row-0001.json"
    )
    assert projected[0]["file_sha256"] == hashlib.sha256(capture_path.read_bytes()).hexdigest()
    assert projected[0]["stdout_full_bytes"] == 5
    assert projected[0]["stdout_sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_malformed_captured_output_marker_fails_closed(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = make_evidence(tmp_path)
    (evidence / "captured-output-row-0001.json").write_text(
        json.dumps({"marker": "CAPTURED-OUTPUT", "spec_row_number": 1}), encoding="utf-8"
    )

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 1
    assert "captured output" in result.output
    assert not (session / "evidence_bundle.json").exists()


def test_captured_output_truncation_fields_survive_projection(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = make_evidence(tmp_path)
    (evidence / "captured-output-row-0001.json").write_text(
        json.dumps(captured_output_record(stdout="he")), encoding="utf-8"
    )

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 0, result.output
    projected = read_bundle(session)["artifacts"]["captured_outputs"][0]
    assert projected["stdout"] == "he"
    assert projected["stdout_full_bytes"] == 5
    assert projected["stdout_sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_final_bundle_write_is_atomic(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 0, result.output
    assert (session / "evidence_bundle.json").is_file()
    assert not list(session.glob(".evidence_bundle.json.*.tmp"))

def test_invalid_interview_ledger_fails_closed(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    (session / "ledger.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 1
    assert "ledger.json invalid" in result.output


def make_ulw_subdir(tmp_path: Path, name: str, brief: str = "brief") -> Path:
    sub = tmp_path / ".omo" / "ulw-loop" / name
    sub.mkdir(parents=True)
    (sub / "brief.md").write_text(brief, encoding="utf-8")
    (sub / "goals.json").write_text(json.dumps({"version": 1, "goals": []}), encoding="utf-8")
    (sub / "ledger.jsonl").write_text(
        json.dumps({"kind": "evidence_captured"}) + "\n", encoding="utf-8"
    )
    return sub


def test_default_discovery_finds_base_ulw_state(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    ulw = make_ulw(tmp_path, [{"kind": "evidence_captured"}])
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["execution"]["present"] is True
    assert bundle["sources"]["ulw_dir"] == str(ulw.resolve())


def test_default_discovery_descends_into_session_id_subdir(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    sub = make_ulw_subdir(tmp_path, "codex-abc123")
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["execution"]["present"] is True
    assert bundle["sources"]["ulw_dir"] == str(sub.resolve())
    assert bundle["warnings"] == []


def test_discovery_prefers_brief_mentioning_slug(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    make_ulw_subdir(tmp_path, "codex-other", brief="Implement something unrelated")
    match = make_ulw_subdir(
        tmp_path, "codex-ours", brief="Implement .ultimateinterview/demo/handoff.md Part 1"
    )
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["sources"]["ulw_dir"] == str(match.resolve())
    assert bundle["warnings"] == []


def test_discovery_falls_back_to_newest_state_with_warning(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    stale = make_ulw_subdir(tmp_path, "codex-old")
    fresh = make_ulw_subdir(tmp_path, "codex-new")
    os.utime(stale / "ledger.jsonl", (1_000_000, 1_000_000))
    os.utime(stale / "goals.json", (1_000_000, 1_000_000))
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["sources"]["ulw_dir"] == str(fresh.resolve())
    assert any("--ulw-dir to override" in note for note in bundle["warnings"])


def test_explicit_ulw_dir_with_session_subdir_is_discovered(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    sub = make_ulw_subdir(tmp_path, "codex-abc123")
    result = runner.invoke(
        pack_evidence.app, [str(session), "--ulw-dir", str(tmp_path / ".omo" / "ulw-loop")]
    )
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["sources"]["ulw_dir"] == str(sub.resolve())


def test_no_ulw_skips_discovery_and_records_exclusion(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    make_ulw(tmp_path, [{"kind": "evidence_captured"}])
    result = runner.invoke(pack_evidence.app, [str(session), "--no-ulw"])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["execution"]["present"] is False
    assert any("--no-ulw" in note for note in bundle["missing_evidence"])
    result = runner.invoke(
        pack_evidence.app,
        [str(session), "--no-ulw", "--ulw-dir", str(tmp_path / ".omo" / "ulw-loop")],
    )
    assert result.exit_code == 1
    assert "not both" in result.output


def test_oversized_event_fields_are_digested(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    big_container = {"snapshot": ["x" * 500] * 40}
    events = [
        {
            "kind": "criteria_revised",
            "message": "m" * 3_000,
            "evidence": "small evidence",
            "goalId": "G1",
            "criterionId": "C1",
            "before": big_container,
            "after": big_container,
        }
    ]
    ulw = make_ulw(tmp_path, events)
    result = runner.invoke(pack_evidence.app, [str(session), "--ulw-dir", str(ulw)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    event = bundle["execution"]["ledger_events"][0]
    assert event["evidence"] == "small evidence"
    assert "truncated" in event["message"] and len(event["message"]) < 3_000
    stub = event["before"]
    assert stub["omitted"] == "oversized-value"
    assert stub["shape"] == "dict(1 keys)"
    assert stub["keys"] == ["snapshot"]
    assert stub["preview"].startswith('{"snapshot"')
    assert len(stub["sha256"]) == 12
    assert bundle["execution"]["revisions"][0]["before"]["omitted"] == "oversized-value"


def test_goals_are_compacted_per_goal_not_as_one_container(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    ulw = make_ulw(tmp_path, [{"kind": "evidence_captured"}])
    goals = {"version": 1, "goals": [{"id": "G1", "title": "t", "history": ["y" * 500] * 40}]}
    (ulw / "goals.json").write_text(json.dumps(goals), encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session), "--ulw-dir", str(ulw)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    packed = bundle["execution"]["goals"]
    assert packed["version"] == 1
    assert packed["goals"][0]["title"] == "t"
    assert packed["goals"][0]["history"]["omitted"] == "oversized-value"


def test_brief_identical_to_handoff_is_deduplicated(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    handoff_text = (session / "handoff.md").read_text(encoding="utf-8")
    ulw = make_ulw(tmp_path, [{"kind": "evidence_captured"}])
    (ulw / "brief.md").write_text(handoff_text, encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session), "--ulw-dir", str(ulw)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["execution"]["brief_md"].startswith("[identical to spec.handoff_md")


def test_artifact_text_budget_omits_after_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pack_evidence, "MAX_TOTAL_ARTIFACT_TEXT_BYTES", 15)
    session = make_session(tmp_path)
    make_evidence(tmp_path)
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    files = read_bundle(session)["artifacts"]["files"]
    assert files[0]["text"] == '{"ok": true}\n'
    assert "budget" in files[1]["text_omitted"]
    assert "text" not in files[1]


def test_oversized_bundle_appends_size_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pack_evidence, "BUNDLE_SIZE_WARN_BYTES", 10)
    session = make_session(tmp_path)
    result = runner.invoke(pack_evidence.app, [str(session)])
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert any("too large for its consumer" in note for note in bundle["warnings"])


def test_lessons_snapshot_captures_active_rows(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    store = tmp_path / "lessons.md"
    store.write_text(LESSONS_MD, encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session), "--lessons", str(store)])
    assert result.exit_code == 0, result.output
    stores = read_bundle(session)["lessons"]["stores"]
    assert len(stores) == 1
    assert stores[0]["name"] == "lessons.md"
    assert stores[0]["active_count"] == 2
    signals = [row["signal"] for row in stores[0]["active"]]
    assert "free-text input" in signals and "temporal word" in signals
    assert stores[0]["active"][0]["fired"] == 4


def test_explicit_missing_lessons_store_is_recorded(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    result = runner.invoke(
        pack_evidence.app, [str(session), "--lessons", str(tmp_path / "gone.md")]
    )
    assert result.exit_code == 0, result.output
    bundle = read_bundle(session)
    assert bundle["lessons"]["stores"] == []
    assert any("gone.md" in note for note in bundle["missing_evidence"])


def test_default_paths_snapshot_repo_docs_store(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ultimateinterview-lessons.md").write_text(LESSONS_MD, encoding="utf-8")
    result = runner.invoke(pack_evidence.app, [str(session), "--repo-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    stores = read_bundle(session)["lessons"]["stores"]
    assert [s["name"] for s in stores] == ["ultimateinterview-lessons.md"]
    assert stores[0]["active_count"] == 2


def test_diff_range_and_file_are_mutually_exclusive(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    diff_file = tmp_path / "impl.diff"
    diff_file.write_text("", encoding="utf-8")
    result = runner.invoke(
        pack_evidence.app,
        [str(session), "--diff-range", "main..HEAD", "--diff-file", str(diff_file)],
    )
    assert result.exit_code == 1
    assert "not both" in result.output


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
