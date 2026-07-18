from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_evolution", ROOT / "native-evolution" / "run_evolution.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


ORACLE = {
    "material_decisions": [
        {"id": "time-zone", "answer": "local", "why_material": "changes firing time"}
    ],
    "owner_rules": ["answer only what was asked"],
}

LENS = {
    "id": "synthesis-loss",
    "stage": "synthesis",
    "failure_description": "An owner-confirmed decision is absent from the final contract.",
    "observable_signal": "The transcript contains a decision that has no contract counterpart.",
    "why_material": "Implementers can produce a different observable result.",
    "minimal_test_shape": "Confirm one behavior, then compare it with the completed contract.",
}


class FakeBackend:
    def __init__(self) -> None:
        self.interviewer_calls = 0
        self.prompts: list[tuple[str, str]] = []

    def question(self) -> dict:
        return {
            "action": "question",
            "reason": "timezone is material",
            "open_material_decisions": ["time-zone"],
            "question": {
                "header": "Timezone",
                "prompt": "Which timezone?",
                "options": [
                    {"label": "Local", "description": "Use local time", "recommended": True},
                    {"label": "UTC", "description": "Use UTC", "recommended": False},
                ],
            },
            "contract": None,
        }

    def complete(self, ready: bool = True) -> dict:
        return {
            "action": "complete",
            "reason": "ready" if ready else "forced close",
            "open_material_decisions": [] if ready else ["time-zone"],
            "question": None,
            "contract": {
                "summary": "local reminder" if ready else "incomplete reminder",
                "implementation_ready": ready,
                "confirmed_decisions": ["timezone is local"] if ready else [],
                "open_material_decisions": [] if ready else ["time-zone"],
                "acceptance_checks": ["fires in local time"] if ready else [],
            },
        }

    def invoke(self, role: str, prompt: str, schema: dict) -> dict:
        self.prompts.append((role, prompt))
        if role == "failure-lens-proposer":
            return {"lenses": [LENS]}
        if role == "lens-auditor":
            return {"accepted_lens_ids": [LENS["id"]], "rejected_lenses": [], "audit_summary": "distinct"}
        if role == "lens-case-designer":
            repository = '"context_mode":"repository"' in prompt
            return {
                "public_request": (
                    "Add timezone support" if repository else "Add a compact reminder command."
                ),
                "target_lens_ids": ["synthesis-loss"],
                "objective_failure_signals": ["confirmed timezone is absent from the contract"],
                "oracle": None if repository else ORACLE,
            }
        if role == "discovery":
            return {
                "scope_summary": "one CLI",
                "facts": [{
                    "id": "cli-name", "claim": "The CLI is named reminder.",
                    "authority": "documentation",
                    "evidence": [{"path": "README.md", "line_start": 1, "line_end": 1}],
                }],
                "conflicts": [],
                "unknowns": ["timezone policy"],
            }
        if role == "evidence-auditor":
            return {
                "accepted_fact_ids": ["cli-name"], "rejected_facts": [],
                "resolved_conflicts": [], "unresolved_conflict_ids": [],
                "audit_summary": "directly supported",
            }
        if role == "owner-oracle-designer":
            return {"oracle": ORACLE}
        if role == "interviewer":
            if '"force_close":true' in prompt:
                return self.complete(False)
            self.interviewer_calls += 1
            return self.question() if self.interviewer_calls == 1 else self.complete()
        if role == "owner":
            return {"answer": "Local time."}
        if role == "judge":
            return {
                "implementation_ready": True,
                "repository_fidelity": 1.0,
                "owner_decision_recall": 1.0,
                "invented_requirements": [],
                "question_count": 1,
                "unnecessary_questions": [],
                "failures": [],
                "summary": "complete",
            }
        if role == "adversarial-reviewer":
            summary = "incomplete reminder" if "incomplete reminder" in prompt else "local reminder"
            return {
                "findings": [{
                    "id": "finding-1", "lens_id": "synthesis-loss",
                    "blocker_type": "synthesis-loss",
                    "description": "The contract summary does not carry the confirmed timezone.",
                    "why_material": "A fresh implementer could choose UTC.",
                    "citations": [{
                        "artifact": "contract", "pointer": "/summary",
                        "quoted_text": summary,
                    }],
                }],
                "review_summary": "one candidate blocker",
            }
        if role == "adjudicator":
            return {
                "verdicts": [{
                    "finding_id": "finding-1", "approved": True,
                    "evidence_supported": True, "lens_match": True,
                    "material": True, "oracle_conflict": False,
                    "reason": "The cited summary omits the confirmed decision.",
                }],
                "adjudication_summary": "approved",
            }
        if role == "mutator":
            return {
                "skill_md": "---\nname: x\ndescription: x\n---\n",
                "change_summary": "none", "addressed_failures": [],
            }
        raise AssertionError(role)


class NativeEvolutionTests(unittest.TestCase):
    def test_greenfield_role_boundaries_and_artifacts(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "run"
            result = MODULE.run("reminder", "candidate skill", run_dir, backend, 30)
            self.assertFalse(result["manifest"]["orca"])
            self.assertEqual(result["manifest"]["schema"], "NativeEvolutionRun.v3")
            self.assertEqual(result["manifest"]["termination_reason"], "completed")
            self.assertIn("not OS read-deny", result["manifest"]["isolation"])
            roles = [role for role, _ in backend.prompts]
            self.assertEqual(
                roles, [
                    "failure-lens-proposer", "lens-auditor", "lens-case-designer",
                    "interviewer", "owner", "interviewer", "adversarial-reviewer",
                    "judge", "adjudicator", "mutator",
                ]
            )
            interviewer_prompts = [prompt for role, prompt in backend.prompts if role == "interviewer"]
            self.assertTrue(all("why_material" not in prompt for prompt in interviewer_prompts))
            mutator_prompt = next(prompt for role, prompt in backend.prompts if role == "mutator")
            self.assertNotIn("changes firing time", mutator_prompt)
            self.assertIn("finding-1", mutator_prompt)
            owner_prompt = next(prompt for role, prompt in backend.prompts if role == "owner")
            self.assertNotIn("candidate skill", owner_prompt)
            proposer_prompt = next(
                prompt for role, prompt in backend.prompts if role == "failure-lens-proposer"
            )
            self.assertNotIn("candidate skill", proposer_prompt)
            case_prompt = next(
                prompt for role, prompt in backend.prompts if role == "lens-case-designer"
            )
            self.assertNotIn("candidate_skill_md", case_prompt)
            reviewer_prompt = next(
                prompt for role, prompt in backend.prompts if role == "adversarial-reviewer"
            )
            self.assertNotIn("why_material\":\"changes firing time", reviewer_prompt)
            self.assertEqual(result["manifest"]["lens_set_sha256"], json.loads(
                (run_dir / "lens-set.json").read_text()
            )["sha256"])
            self.assertEqual(
                result["manifest"]["lens_set_sha256"],
                result["manifest"]["case_identity"]["lens_set_sha256"],
            )

    def test_repository_ground_truth_is_discovered_audited_and_shared(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            (repo / "README.md").write_text("The CLI is named reminder.\n", encoding="utf-8")
            run_dir = root / "run"
            result = MODULE.run(
                "Add timezone support", "candidate skill", run_dir, backend, 30,
                context_mode="repository", repo_root=repo
            )
            roles = [role for role, _ in backend.prompts]
            self.assertEqual(roles[:6], [
                "failure-lens-proposer", "lens-auditor", "discovery", "evidence-auditor",
                "lens-case-designer", "owner-oracle-designer",
            ])
            self.assertEqual(result["manifest"]["context_mode"], "repository")
            evidence = json.loads((run_dir / "evidence-pack.json").read_text())
            self.assertEqual([fact["id"] for fact in evidence["facts"]], ["cli-name"])
            citation = evidence["facts"][0]["evidence"][0]
            self.assertEqual(citation["quoted_text"], "The CLI is named reminder.")
            self.assertEqual(len(citation["quoted_text_sha256"]), 64)
            self.assertEqual(len(evidence["repository_snapshot"]["cited_file_sha256"]["README.md"]), 64)
            interviewer_prompt = next(prompt for role, prompt in backend.prompts if role == "interviewer")
            self.assertIn("The CLI is named reminder", interviewer_prompt)
            self.assertNotIn("why_material", interviewer_prompt)

    def test_lens_auditor_must_disposition_every_lens_and_reject_tool_dependency(self) -> None:
        proposal = {"lenses": [LENS, {**LENS, "id": "second-lens"}]}
        audit = {"accepted_lens_ids": [LENS["id"]], "rejected_lenses": [], "audit_summary": "partial"}
        with self.assertRaisesRegex(ValueError, "disposition every"):
            MODULE.validate_lens_set(proposal, audit)
        named = {**LENS, "id": "named-tool", "failure_description": "Ultimateinterview fails"}
        with self.assertRaisesRegex(ValueError, "named tool"):
            MODULE.validate_lens_set(
                {"lenses": [named]},
                {"accepted_lens_ids": [named["id"]], "rejected_lenses": [], "audit_summary": "bad"},
            )

    def test_review_citations_and_adjudication_fail_closed(self) -> None:
        review = {
            "findings": [{
                "id": "f1", "lens_id": LENS["id"], "blocker_type": "synthesis-loss",
                "description": "missing", "why_material": "changes behavior",
                "citations": [{
                    "artifact": "contract", "pointer": "/summary", "quoted_text": "wrong"
                }],
            }],
            "review_summary": "x",
        }
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.validate_adversarial_review(
                review, [LENS], {"summary": "actual"}, [], {"facts": []}
            )
        review["findings"][0]["citations"][0]["quoted_text"] = "actual"
        MODULE.validate_adversarial_review(review, [LENS], {"summary": "actual"}, [], {"facts": []})
        review["findings"][0]["citations"][0]["pointer"] = "/final_contract/summary"
        MODULE.validate_adversarial_review(review, [LENS], {"summary": "actual"}, [], {"facts": []})
        review["findings"][0]["citations"][0]["quoted_text"] = "act"
        MODULE.validate_adversarial_review(review, [LENS], {"summary": "actual"}, [], {"facts": []})
        inconsistent = {
            "verdicts": [{
                "finding_id": "f1", "approved": True, "evidence_supported": False,
                "lens_match": True, "material": True, "oracle_conflict": False,
                "reason": "unsupported",
            }],
            "adjudication_summary": "x",
        }
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            MODULE.approved_findings(review, inconsistent)

    def test_unsafe_or_out_of_bounds_evidence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "README.md").write_text("one line\n")
            discovery = {
                "facts": [{
                    "id": "bad", "claim": "bad", "authority": "documentation",
                    "evidence": [{"path": "../escape", "line_start": 1, "line_end": 1}],
                }]
            }
            with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
                MODULE.validate_discovery(repo, discovery)
            discovery["facts"][0]["evidence"][0] = {
                "path": "README.md", "line_start": 1, "line_end": 2
            }
            with self.assertRaisesRegex(ValueError, "invalid evidence line bounds"):
                MODULE.validate_discovery(repo, discovery)

    def test_holdout_never_invokes_mutator(self) -> None:
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "run"
            result = MODULE.run("reminder", "candidate skill", run_dir, backend, 30, "holdout")
            self.assertNotIn("mutator", [role for role, _ in backend.prompts])
            self.assertFalse((run_dir / "candidate-SKILL.md").exists())
            self.assertIsNone(result["manifest"]["candidate_sha256"])

    def test_study_registry_rejects_holdout_reuse_for_development(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            registry = root / "registry.json"
            MODULE.run(
                "reminder", "candidate skill", root / "holdout", FakeBackend(), 30,
                "holdout", study_registry=registry
            )
            recorded = json.loads(registry.read_text())
            self.assertEqual(recorded["entries"][0]["status"], "completed")
            with self.assertRaisesRegex(ValueError, "partition contamination"):
                MODULE.run(
                    "reminder", "candidate skill", root / "development", FakeBackend(), 30,
                    "development", study_registry=registry
                )

    def test_study_registry_rejects_cross_partition_lens_set_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            registry = root / "registry.json"
            MODULE.reserve_study_run(registry, "development", {
                "seed_sha256": "dev-seed", "public_request_sha256": "dev-request",
                "lens_set_sha256": "shared-lenses", "lens_case_sha256": "dev-lens-case",
                "case_sha256": "dev-case",
            }, root / "dev")
            with self.assertRaisesRegex(ValueError, "lens_set_sha256"):
                MODULE.reserve_study_run(registry, "holdout", {
                    "seed_sha256": "holdout-seed", "public_request_sha256": "holdout-request",
                    "lens_set_sha256": "shared-lenses", "lens_case_sha256": "holdout-lens-case",
                    "case_sha256": "holdout-case",
                }, root / "holdout")

    def test_auditor_must_disposition_every_fact_and_preserve_conflicts(self) -> None:
        discovery = {
            "scope_summary": "x",
            "facts": [
                {"id": "a", "claim": "a", "authority": "code", "evidence": []},
                {"id": "b", "claim": "b", "authority": "test", "evidence": []},
            ],
            "conflicts": [{"id": "c1", "description": "code and docs disagree"}],
            "unknowns": [],
            "repository_snapshot": {},
        }
        audit = {
            "accepted_fact_ids": ["a"], "rejected_facts": [],
            "resolved_conflicts": [], "unresolved_conflict_ids": ["c1"],
            "audit_summary": "partial",
        }
        with self.assertRaisesRegex(ValueError, "disposition every"):
            MODULE.audited_evidence(discovery, audit)
        audit["rejected_facts"] = [{"id": "b", "reason": "unsupported"}]
        audit["unresolved_conflict_ids"] = []
        with self.assertRaisesRegex(ValueError, "disposition every discovery conflict"):
            MODULE.audited_evidence(discovery, audit)

    def test_safety_ceiling_forces_non_ready_contract_instead_of_normal_completion(self) -> None:
        class Endless(FakeBackend):
            def invoke(self, role: str, prompt: str, schema: dict) -> dict:
                if role == "interviewer" and '"force_close":true' not in prompt:
                    self.prompts.append((role, prompt))
                    return self.question()
                return super().invoke(role, prompt, schema)

        backend = Endless()
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "run"
            result = MODULE.run("reminder", "candidate skill", run_dir, backend, 2)
            self.assertEqual(result["manifest"]["termination_reason"], "safety_ceiling")
            transcript = json.loads((run_dir / "transcript.json").read_text())
            self.assertEqual(transcript[-1]["termination"], "safety_ceiling")
            self.assertFalse(transcript[-1]["interviewer"]["contract"]["implementation_ready"])

    def test_forced_close_rejects_false_ready_claim(self) -> None:
        class Dishonest(FakeBackend):
            def invoke(self, role: str, prompt: str, schema: dict) -> dict:
                if role == "interviewer":
                    self.prompts.append((role, prompt))
                    return self.complete() if '"force_close":true' in prompt else self.question()
                return super().invoke(role, prompt, schema)

        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "cannot claim implementation readiness"):
                MODULE.run("reminder", "candidate skill", Path(raw) / "run", Dishonest(), 2)

    def test_repeated_open_decisions_trigger_stagnation(self) -> None:
        class Endless(FakeBackend):
            def invoke(self, role: str, prompt: str, schema: dict) -> dict:
                if role == "interviewer" and '"force_close":true' not in prompt:
                    self.prompts.append((role, prompt))
                    return self.question()
                return super().invoke(role, prompt, schema)

        backend = Endless()
        with tempfile.TemporaryDirectory() as raw:
            run_dir = Path(raw) / "run"
            result = MODULE.run(
                "reminder", "candidate skill", run_dir, backend, 30,
                stagnation_patience=3
            )
            self.assertEqual(result["manifest"]["termination_reason"], "stagnation")


if __name__ == "__main__":
    unittest.main()
