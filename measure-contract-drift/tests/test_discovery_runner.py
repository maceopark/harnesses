from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from driftbench.discovery import canonical_digest
from driftbench.discovery_runner import (
    DiscoveryRunner, _hash_inventory, _short_evidence, load_manifest,
)


class FakeBackend:
    def __init__(self, fail_once: str | None = None, always_fail: str | None = None,
                 expect_feedback_at: Path | None = None) -> None:
        self.generations: list[str] = []
        self.evolutions: list[dict] = []
        self.calls: list[str] = []
        self.attempts: dict[str, int] = {}
        self.fail_once = fail_once
        self.always_fail = always_fail
        self.expect_feedback_at = expect_feedback_at
        self.active = 0
        self.maximum_active = 0
        self.lock = threading.Lock()

    def generate(self, *, seed_skill: str, runtime_digest: str) -> str:
        self.generations.append(runtime_digest)
        return seed_skill + f"\nvariant-{len(self.generations)}\n"

    def evolve(self, *, parent_skill: str, train_feedback, mutation_intent,
               runtime_digest: str) -> str:
        self.evolutions.append({"parent_skill": parent_skill, "feedback": train_feedback,
                                "mutation_intent": mutation_intent,
                                "runtime_digest": runtime_digest})
        return parent_skill + f"\nevolved-{len(self.evolutions)}\n"

    def summarize_skill_change(self, *, parent_skill: str, candidate_skill: str,
                               mutation_intent):
        return {"parent_summary": "Parent strategy.",
                "candidate_summary": "Candidate strategy.",
                "change_summary": f"Applied {mutation_intent['intent_id']}."}

    def evaluate(self, *, cell, prompt, skill, repo, attempt_dir, answer_seed, pane=None):
        if cell.partition == "validation" and self.expect_feedback_at is not None:
            assert self.expect_feedback_at.is_file()
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.calls.append(cell.cell_id)
            self.attempts[cell.cell_id] = self.attempts.get(cell.cell_id, 0) + 1
        try:
            time.sleep(.002)
            if cell.cell_id == self.always_fail:
                raise RuntimeError("always")
            if cell.cell_id == self.fail_once and self.attempts[cell.cell_id] == 1:
                raise RuntimeError("once")
            (attempt_dir / "transcript.json").write_text("{}\n")
            (attempt_dir / "selections.json").write_text("{}\n")
            (attempt_dir / "implementation.diff").write_text("diff\n")
            (attempt_dir / "postmortem.md").write_text("# report\n")
            (attempt_dir / "postmortem-result.json").write_text("{}\n")
            session = attempt_dir / ".ultimateinterview" / cell.cell_id
            session.mkdir(parents=True)
            (session / "build-contract.json").write_text("{}\n")
            return {"fulfilled": 2, "contract_requirements": 2,
                    "escaped_requirements": 0, "material_decisions": 1,
                    "failure_taxonomy": ["train-cause"] if cell.partition == "train" else ["secret-validation"],
                    "failure_evidence": ["train evidence"] if cell.partition == "train" else ["secret evidence"]}
        finally:
            with self.lock:
                self.active -= 1


def _manifest(tmp_path: Path) -> Path:
    seed = tmp_path / "seed.md"
    seed.write_text("# Interview\n")
    cases = []
    for partition, count in (("train", 6), ("validation", 3)):
        for index in range(count):
            case_id = f"{partition}-{index}"
            starter = tmp_path / "starters" / case_id
            starter.mkdir(parents=True)
            (starter / "cli.py").write_text("print('ok')\n")
            cases.append({"case_id": case_id, "partition": partition,
                          "prompt": f"Support {case_id}", "starter": f"starters/{case_id}"})
    value = {"schema": "DiscoveryManifest.v2", "study_id": "test", "answer_seed": "seed",
             "seed_skill": "seed.md", "runtime_digest": "a" * 64,
             "model": "test-model", "reasoning_effort": "medium", "cases": cases,
             "candidates": 4, "repetitions": 2, "workers": 4,
             "mutation_intents": [
                 {"intent_id": value, "label": value, "directive": f"Change {value}"}
                 for value in ("fidelity-repair", "question-compression",
                               "interaction-redesign", "novel-structure")],
             "stopping": {"schema": "DiscoveryStoppingPolicy.v1",
                          "maximum_generation": 9, "minimum_generation": 2,
                          "patience": 2, "fidelity_epsilon_ppm": 25000,
                          "decision_epsilon_milli": 500, "skill_bytes_epsilon": 256,
                          "require_full_candidate_inventory": True,
                          "full_candidate_count": 4}}
    value["manifest_digest"] = canonical_digest(value)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    return path


def test_runner_completes_72_cells_with_independent_generation_parallelism_and_no_final(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    backend = FakeBackend(fail_once="g00-c00--train--train-0--r1",
                          always_fail="g00-c01--train--train-0--r1",
                          expect_feedback_at=run_dir / "generation-feedback.json")
    runner = DiscoveryRunner(_manifest(tmp_path), run_dir, backend)
    result = runner.run()
    receipt = json.loads((result / "receipt.json").read_text())
    state = json.loads((result / "state.json").read_text())
    feedback = json.loads((result / "generation-feedback.json").read_text())
    assert len(backend.generations) == 3
    assert len(state["cells"]) == 72
    assert receipt["terminal_cells"] == 72
    assert receipt["final_test_executed"] is False and receipt["champion_id"] is None
    assert backend.maximum_active <= 4 and backend.maximum_active > 1
    assert state["cells"]["g00-c00--train--train-0--r1"]["attempts"] == 2
    assert state["cells"]["g00-c01--train--train-0--r1"]["status"] == "invalid"
    assert "train-cause" in feedback["root_causes"]
    assert "secret-validation" not in feedback["root_causes"]
    first_validation = next(index for index, cell in enumerate(backend.calls) if "--validation--" in cell)
    assert all("--train--" in cell for cell in backend.calls[:first_validation])


def test_resume_reuses_digest_bound_terminal_cells(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    run_dir = tmp_path / "run"
    DiscoveryRunner(manifest, run_dir, FakeBackend()).run(max_candidates=1, max_parallel=1)
    backend = FakeBackend()
    DiscoveryRunner(manifest, run_dir, backend).run(max_candidates=1, max_parallel=1)
    assert backend.calls == []
    assert backend.generations == []


def test_generation_one_uses_train_feedback_and_runs_a_fresh_72_cell_cycle(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    parent = tmp_path / "g00"
    DiscoveryRunner(manifest, parent, FakeBackend()).run()
    child = tmp_path / "g01"
    backend = FakeBackend(expect_feedback_at=child / "generation-feedback.json")
    DiscoveryRunner(manifest, child, backend, generation=1, parent_run=parent).run()

    receipt = json.loads((child / "receipt.json").read_text())
    state = json.loads((child / "state.json").read_text())
    context = json.loads((child / "generation-context.json").read_text())
    lineage = json.loads((child / "candidate-lineage.json").read_text())
    parent_feedback = json.loads((parent / "generation-feedback.json").read_text())
    assert receipt["generation"] == 1 and receipt["terminal_cells"] == 72
    assert len(state["cells"]) == 72
    assert all(cell.startswith("g01-c") for cell in state["cells"])
    assert len(backend.evolutions) == 4 and backend.generations == []
    assert all(call["feedback"] == parent_feedback for call in backend.evolutions)
    assert all("secret-validation" not in json.dumps(call["feedback"])
               for call in backend.evolutions)
    assert context["train_feedback"] == parent_feedback
    assert [call["mutation_intent"]["intent_id"] for call in backend.evolutions] == [
        "fidelity-repair", "question-compression", "interaction-redesign", "novel-structure"]
    assert [row["parent_candidate_id"] for row in context["assignments"]] == [
        context["parent_archive"][index % len(context["parent_archive"])] for index in range(4)]
    assert len(lineage["candidates"]) == 4
    assert {row["parent_candidate_id"] for row in lineage["candidates"]} <= set(
        json.loads((parent / "pareto-archive.json").read_text())["archive"])
    assert (child / "generation-comparison.html").is_file()
    assert (child / "generation-comparison.json").is_file()
    summaries = json.loads((child / "skill-change-summaries.json").read_text())
    assert summaries["summaries"]["g01-c00"]["change_summary"] == "Applied fidelity-repair."
    assert json.loads((child / "receipt.json").read_text())["comparison_report_digest"]


def test_generation_one_resume_reuses_cells_and_rejects_parent_feedback_drift(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    parent = tmp_path / "g00"
    child = tmp_path / "g01"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
        max_candidates=1, max_parallel=1)
    backend = FakeBackend()
    DiscoveryRunner(manifest, child, backend, generation=1, parent_run=parent).run(
        max_candidates=1, max_parallel=1)
    assert backend.calls == [] and backend.evolutions == []

    feedback_path = parent / "generation-feedback.json"
    feedback = json.loads(feedback_path.read_text())
    feedback["evidence"].append("tampered")
    feedback_path.write_text(json.dumps(feedback))
    with pytest.raises(ValueError, match="binding"):
        DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
            max_candidates=1, max_parallel=1)


def test_resume_rejects_tampered_mutation_lineage(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path); parent = tmp_path / "g00"; child = tmp_path / "g01"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
        max_candidates=1, max_parallel=1)
    path = child / "candidate-lineage.json"; value = json.loads(path.read_text())
    value["candidates"][0]["mutation_intent_id"] = "novel-structure"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="lineage binding"):
        DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
            max_candidates=1, max_parallel=1)


def test_artifact_inventory_ignores_ephemeral_git_metadata(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text("{}\n")
    metadata = tmp_path / "attempts" / "attempt-1" / "repo" / ".git"
    metadata.mkdir(parents=True)
    (metadata / "HEAD").write_text("ref: refs/heads/main\n")

    assert _hash_inventory(tmp_path) == {
        "result.json": hashlib.sha256(b"{}\n").hexdigest()
    }


def test_generation_feedback_evidence_is_single_line_and_bounded() -> None:
    value = "\nRuntimeError: model at capacity\n" + "diagnostic " * 100
    assert _short_evidence(value) == "RuntimeError: model at capacity"
    assert len(_short_evidence("x" * 500)) == 240


def test_checked_in_manifest_binds_generation_zero_inventory() -> None:
    project = Path(__file__).resolve().parents[1]
    manifest = load_manifest(project / "discovery-study.json")
    assert manifest.candidates == 4 and manifest.repetitions == 2 and manifest.workers == 4
    assert [row.intent_id for row in manifest.mutation_intents] == [
        "fidelity-repair", "question-compression", "interaction-redesign", "novel-structure"]
    assert manifest.stopping.patience == 2 and manifest.stopping.maximum_generation == 9
    assert [case.case_id for case in manifest.cases if case.partition == "train"] == [
        "bookmarks", "contacts-csv", "expense", "inventory-transfer",
        "feature-flags", "playlist-reorder",
    ]
    assert [case.case_id for case in manifest.cases if case.partition == "validation"] == [
        "config-merge", "reminder", "order-cancel",
    ]
