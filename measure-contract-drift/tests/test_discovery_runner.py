from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from driftbench.discovery import canonical_digest
from driftbench.discovery_runner import (
    DiscoveryRunner, _hash_inventory, _short_evidence, _verify_inventory, load_manifest,
)


class FakeBackend:
    def __init__(self, fail_once: str | None = None, always_fail: str | None = None,
                 expect_feedback_at: Path | None = None,
                 prefer_mutations: bool = False) -> None:
        self.generations: list[str] = []
        self.evolutions: list[dict] = []
        self.calls: list[str] = []
        self.attempts: dict[str, int] = {}
        self.fail_once = fail_once
        self.always_fail = always_fail
        self.expect_feedback_at = expect_feedback_at
        self.prefer_mutations = prefer_mutations
        self.active = 0
        self.maximum_active = 0
        self.lock = threading.Lock()

    def generate(self, *, seed_skill: str, runtime_digest: str) -> str:
        self.generations.append(runtime_digest)
        return f"variant-{len(self.generations)}"

    def evolve(self, *, seed_skill: str, parent_overlay: str, train_feedback, mutation_intent,
               runtime_digest: str) -> str:
        self.evolutions.append({"seed_skill": seed_skill, "parent_overlay": parent_overlay,
                                "feedback": train_feedback,
                                "mutation_intent": mutation_intent,
                                "runtime_digest": runtime_digest})
        return f"complete-replacement-{len(self.evolutions)}"

    def summarize_skill_change(self, *, parent_skill: str, candidate_skill: str,
                               mutation_intent):
        return {"parent_summary": "Parent strategy.",
                "candidate_summary": "Candidate strategy.",
                "change_summary": f"Applied {mutation_intent['intent_id']}."}

    def evaluate(self, *, cell, prompt, skill, repo, attempt_dir, owner_card, pane=None):
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
            (attempt_dir / "owner-exchanges.json").write_text("{}\n")
            (attempt_dir / "discovery-result.json").write_text("{}\n")
            (attempt_dir / "implementation.diff").write_text("diff\n")
            (attempt_dir / "postmortem.md").write_text("# report\n")
            (attempt_dir / "postmortem-result.json").write_text("{}\n")
            session = attempt_dir / ".ultimateinterview" / cell.cell_id
            session.mkdir(parents=True)
            (session / "build-contract.json").write_text("{}\n")
            discovery_success = not (
                self.prefer_mutations and cell.candidate_id.endswith("control")
            )
            return {"fulfilled": 2, "contract_requirements": 2,
                    "escaped_requirements": 0, "material_decisions": 1,
                    "question_turns": 1, "discovery_success": discovery_success,
                    "hard_veto": False,
                    "failure_taxonomy": ["train-cause"] if cell.partition == "train" else ["secret-validation"],
                    "failure_evidence": ["train evidence"] if cell.partition == "train" else ["secret evidence"]}
        finally:
            with self.lock:
                self.active -= 1


def _manifest(tmp_path: Path) -> Path:
    seed = tmp_path / "seed.md"
    seed.write_text("# Interview\n")
    cases = []
    for partition, count in (("train", 8), ("validation", 4)):
        for index in range(count):
            case_id = f"{partition}-{index}"
            starter = tmp_path / "starters" / case_id
            starter.mkdir(parents=True)
            (starter / "cli.py").write_text("print('ok')\n")
            cases.append({"case_id": case_id, "partition": partition,
                          "prompt": f"Support {case_id}", "starter": f"starters/{case_id}"})
    oracle = tmp_path / "oracle"; oracle.mkdir()
    for case in cases:
        payload = json.dumps({
            "schema": "DiscoveryOwnerCard.v1", "case_id": case["case_id"],
            "items": [{"item_id": "material", "owner_statement": "Material owner policy.",
                       "materiality": "critical", "forbidden_outcomes": []}], "probes": []})
        (oracle / f"{case['case_id']}.md").write_text(
            f"# Test owner model\n\n```owner-card\n{payload}\n```\n")
    value = {"schema": "DiscoveryManifest.v3", "study_id": "test",
             "seed_skill": "seed.md", "owner_cards_dir": "oracle", "owner_responder_version": "test-v1", "runtime_digest": "a" * 64,
             "model": "test-model", "reasoning_effort": "medium", "cases": cases,
             "mutations": 4, "repetitions": 2, "workers": 12,
             "stopping": {"schema": "DiscoveryStoppingPolicy.v1",
                          "maximum_generation": 9, "minimum_generation": 2,
                          "patience": 2, "discovery_epsilon_ppm": 25000,
                          "decision_epsilon_milli": 500, "turn_epsilon_milli": 256,
                          "require_full_mutation_inventory": True,
                          "full_mutation_count": 4}}
    value["manifest_digest"] = canonical_digest(value)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    return path


def test_runner_completes_120_cells_with_independent_generation_parallelism_and_no_final(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    backend = FakeBackend(fail_once="g00-control--train--train-0--r1",
                          always_fail="g00-m00--train--train-0--r1",
                          expect_feedback_at=run_dir / "generation-feedback.json")
    runner = DiscoveryRunner(_manifest(tmp_path), run_dir, backend)
    result = runner.run()
    receipt = json.loads((result / "receipt.json").read_text())
    state = json.loads((result / "state.json").read_text())
    feedback = json.loads((result / "generation-feedback.json").read_text())
    assert len(backend.generations) == 4
    assert len(state["cells"]) == 120
    assert receipt["terminal_cells"] == 120
    assert receipt["runtime_digest"] == "a" * 64
    assert receipt["final_test_executed"] is False
    assert backend.maximum_active <= 12 and backend.maximum_active > 4
    assert state["cells"]["g00-control--train--train-0--r1"]["attempts"] == 2
    assert state["cells"]["g00-m00--train--train-0--r1"]["status"] == "invalid"
    assert "train-cause" in feedback["candidates"]["g00-control"]["root_causes"]
    assert "secret-validation" not in json.dumps(feedback)
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


def test_resume_rejects_cells_from_pre_gap_gate_backend_semantics(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    manifest = load_manifest(manifest_path)
    run_dir = tmp_path / "run"
    DiscoveryRunner(manifest_path, run_dir, FakeBackend()).run(
        max_candidates=1, max_parallel=1)
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text())
    state["manifest_digest"] = canonical_digest({
        "manifest": manifest.manifest_digest,
        "mutations": 1, "workers": 1, "repetitions": 2,
        "generation": 0, "evolution_context": None,
    })
    state_path.write_text(json.dumps(state))

    with pytest.raises(ValueError, match="effective manifest binding"):
        DiscoveryRunner(manifest_path, run_dir, FakeBackend()).run(
            max_candidates=1, max_parallel=1)


def test_generation_one_uses_train_feedback_and_runs_a_fresh_120_cell_cycle(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    parent = tmp_path / "g00"
    DiscoveryRunner(manifest, parent, FakeBackend(prefer_mutations=True)).run()
    child = tmp_path / "g01"
    backend = FakeBackend(expect_feedback_at=child / "generation-feedback.json")
    DiscoveryRunner(manifest, child, backend, generation=1, parent_run=parent).run()

    receipt = json.loads((child / "receipt.json").read_text())
    state = json.loads((child / "state.json").read_text())
    context = json.loads((child / "generation-context.json").read_text())
    lineage = json.loads((child / "candidate-lineage.json").read_text())
    parent_feedback = json.loads((parent / "generation-feedback.json").read_text())
    assert receipt["generation"] == 1 and receipt["terminal_cells"] == 120
    assert len(state["cells"]) == 120
    assert all(cell.startswith("g01-") for cell in state["cells"])
    assert len(backend.evolutions) == 4 and backend.generations == []
    reference_parent = context["reference_parent_candidate_id"]
    reference_feedback = parent_feedback["candidates"][reference_parent]
    assert all(call["feedback"] == {
        "schema": parent_feedback["schema"], "generation": parent_feedback["generation"],
        "root_causes": reference_feedback["root_causes"],
        "evidence": reference_feedback["evidence"],
    } for call in backend.evolutions)
    assert all("secret-validation" not in json.dumps(call["feedback"])
               for call in backend.evolutions)
    assert context["train_feedback"] == parent_feedback
    assert all(call["seed_skill"] == "# Interview\n" for call in backend.evolutions)
    parent_overlay = (parent / "candidates" / reference_parent / "overlay.md").read_text()
    assert parent_overlay
    assert all(call["parent_overlay"] == parent_overlay for call in backend.evolutions)
    assert all(call["mutation_intent"] == {
        "mode": "open", "operator": "parent-copy-then-edit-v1",
    } for call in backend.evolutions)
    assert {row["parent_candidate_id"] for row in context["assignments"]} == {reference_parent}
    assert len(lineage["candidates"]) == 4
    assert {row["parent_candidate_id"] for row in lineage["candidates"]} <= set(
        json.loads((parent / "pareto-archive.json").read_text())["archive"])
    assert all(row["operator"] == "parent-copy-then-edit-v1" for row in lineage["candidates"])
    assert all(row["parent_overlay_digest"] == hashlib.sha256(
        parent_overlay.encode()).hexdigest() for row in lineage["candidates"])
    control_overlay = (child / "candidates" / "g01-control" / "overlay.md").read_text()
    assert control_overlay == parent_overlay
    assert (child / "candidates" / "g01-control" / "SKILL.md").read_text() == (
        DiscoveryRunner._effective_skill("# Interview\n", parent_overlay))
    for index in range(4):
        candidate = child / "candidates" / f"g01-m{index:02d}"
        overlay = (candidate / "overlay.md").read_text()
        skill = (candidate / "SKILL.md").read_text()
        assert overlay == f"complete-replacement-{index + 1}"
        assert skill == DiscoveryRunner._effective_skill("# Interview\n", overlay)
        assert parent_overlay not in skill
    assert not (child / "generation-comparison.html").exists()


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
    feedback["candidates"]["g00-control"]["evidence"].append("tampered")
    feedback_path.write_text(json.dumps(feedback))
    with pytest.raises(ValueError, match="binding"):
        DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
            max_candidates=1, max_parallel=1)


def test_evolution_rejects_parent_from_a_different_runtime(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    parent = tmp_path / "g00"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    receipt_path = parent / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["runtime_digest"] = "b" * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="not eligible"):
        DiscoveryRunner(
            manifest, tmp_path / "g01", FakeBackend(), generation=1, parent_run=parent,
        ).run(max_candidates=1, max_parallel=1)


def test_evolution_rejects_an_old_cumulative_parent_skill(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    parent = tmp_path / "g00"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    archive = json.loads((parent / "pareto-archive.json").read_text())
    parent_id = archive["archive"][0]
    skill_path = parent / "candidates" / parent_id / "SKILL.md"
    skill_path.write_text(skill_path.read_text() + "\nlegacy appended delta\n")
    candidates_path = parent / "candidate-manifest.json"
    candidates = json.loads(candidates_path.read_text())
    candidates[parent_id] = hashlib.sha256(skill_path.read_bytes()).hexdigest()
    candidates_path.write_text(json.dumps(candidates))

    with pytest.raises(ValueError, match="not seed plus one complete overlay"):
        DiscoveryRunner(
            manifest, tmp_path / "g01", FakeBackend(), generation=1, parent_run=parent,
        ).run(max_candidates=1, max_parallel=1)


def test_resume_rejects_tampered_mutation_lineage(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path); parent = tmp_path / "g00"; child = tmp_path / "g01"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
        max_candidates=1, max_parallel=1)
    path = child / "candidate-lineage.json"; value = json.loads(path.read_text())
    value["candidates"][0]["mutation_id"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="lineage binding"):
        DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
            max_candidates=1, max_parallel=1)


def test_resume_rejects_tampered_complete_overlay(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path); parent = tmp_path / "g00"; child = tmp_path / "g01"
    DiscoveryRunner(manifest, parent, FakeBackend()).run(max_candidates=1, max_parallel=1)
    DiscoveryRunner(manifest, child, FakeBackend(), generation=1, parent_run=parent).run(
        max_candidates=1, max_parallel=1)
    (child / "candidates" / "g01-m00" / "overlay.md").write_text("tampered")
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


def test_blocked_cell_inventory_does_not_require_implementation_or_postmortem(tmp_path: Path) -> None:
    for name in ("transcript.json", "selections.json", "owner-exchanges.json",
                 "discovery-result.json", "interview-blocked.json"):
        (tmp_path / name).write_text("{}\n")
    session = tmp_path / ".ultimateinterview" / "cell"
    session.mkdir(parents=True)
    (session / "interview-blocked.json").write_text("{}\n")

    assert "interview-blocked.json" in _verify_inventory(tmp_path)


def test_generation_feedback_evidence_is_single_line_and_bounded() -> None:
    value = "\nRuntimeError: model at capacity\n" + "diagnostic " * 100
    assert _short_evidence(value) == "RuntimeError: model at capacity"
    assert len(_short_evidence("x" * 500)) == 240


def test_checked_in_manifest_binds_generation_zero_inventory() -> None:
    project = Path(__file__).resolve().parents[1]
    raw = json.loads((project / "discovery-study.json").read_text())
    assert raw["mutations"] == 4 and raw["repetitions"] == 2 and raw["workers"] == 12
    manifest = load_manifest(project / "discovery-study.json")
    assert len(manifest.cases) == 12
    protocol_manifest = project / "protocol/ultimateinterview/schema3-discovery/manifest.json"
    assert raw["runtime_digest"] == hashlib.sha256(protocol_manifest.read_bytes()).hexdigest()
    assert (project / raw["seed_skill"]).read_text(encoding="utf-8") == (
        "# Interview\n\nInspect the request and repository.\n"
        "Ask only questions whose answers can materially change the resulting contract.\n"
        "Produce the runtime-required contract without inventing unauthorized behavior.\n"
    )


def test_protocol_snapshot_matches_current_contract_and_postmortem_surface() -> None:
    project = Path(__file__).resolve().parents[1]
    workspace = project.parent
    snapshot = project / "protocol/ultimateinterview/schema3-discovery/.agents/skills"
    for skill, relative in (
        ("ultimateinterview", "SKILL.md"),
        ("ultimateinterview", "references/json-contracts.md"),
        ("ultimateinterview", "scripts/authority_compiler.py"),
        ("ultimateinterview", "scripts/authority_reconcile.py"),
        ("ultimateinterview", "scripts/projection_check.py"),
        ("ultimateinterview-postmortem", "SKILL.md"),
        ("ultimateinterview-postmortem", "references/postmortem-template.md"),
        ("ultimateinterview-postmortem", "scripts/compiler_session_check.py"),
        ("ultimateinterview-postmortem", "scripts/postmortem_report_check.py"),
    ):
        assert (snapshot / skill / relative).read_bytes() == (
            workspace / ".agents/skills" / skill / relative
        ).read_bytes()
