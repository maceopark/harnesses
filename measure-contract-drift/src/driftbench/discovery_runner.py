"""Standalone generational discovery scheduler.

The runner deliberately has no dependency on the legacy evolution runtime. Backends
own model interaction; workers own isolated cell directories; only the coordinator
mutates state.json and generation-level artifacts.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from .discovery import (
    CellReceipt, CellSpec, ClosedModel, CoordinatorState, OwnerCard, canonical_digest,
    load_owner_card_markdown,
    merge_receipt, pareto_archive, summarize_candidate,
    write_coordinator_state,
)
from .evolution import convergence_decision


REQUIRED_COMMON_CELL_ARTIFACTS = (
    "transcript.json", "selections.json", "owner-exchanges.json", "discovery-result.json",
)
REQUIRED_IMPLEMENTED_CELL_ARTIFACTS = (
    "implementation.diff", "postmortem.md", "postmortem-result.json",
)
BLOCKED_CELL_ARTIFACTS = ("interview-blocked.json", "implementation-blocked.json")
OVERLAY_BOUNDARY = "<!-- DISCOVERY OVERLAY: controller-owned boundary -->"
BACKEND_SEMANTICS_VERSION = "fail-closed-contract-gaps-v4"


class DiscoveryCase(ClosedModel):
    case_id: str = Field(min_length=1)
    partition: Literal["train", "validation"]
    prompt: str = Field(min_length=1)
    starter: str = Field(min_length=1)


class MutationIntent(ClosedModel):
    intent_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    label: str = Field(min_length=1)
    directive: str = Field(min_length=1)


class StoppingPolicy(ClosedModel):
    schema_: Literal["DiscoveryStoppingPolicy.v1"] = Field(
        default="DiscoveryStoppingPolicy.v1", alias="schema", serialization_alias="schema")
    maximum_generation: int = Field(ge=2, le=30)
    minimum_generation: int = Field(ge=2)
    patience: int = Field(ge=2)
    discovery_epsilon_ppm: int = Field(ge=0, le=1_000_000)
    decision_epsilon_milli: int = Field(ge=0)
    turn_epsilon_milli: int = Field(ge=0)
    require_full_mutation_inventory: bool = True
    full_mutation_count: Literal[4] = 4

    @model_validator(mode="after")
    def validate_window(self) -> "StoppingPolicy":
        if self.minimum_generation > self.maximum_generation:
            raise ValueError("minimum generation exceeds generation limit")
        return self


class DiscoveryManifest(ClosedModel):
    schema_: Literal["DiscoveryManifest.v3"] = Field(
        default="DiscoveryManifest.v3", alias="schema", serialization_alias="schema"
    )
    study_id: str = Field(min_length=1)
    seed_skill: str = Field(min_length=1)
    owner_cards_dir: str = Field(min_length=1)
    owner_responder_version: str = Field(min_length=1)
    runtime_digest: str = Field(pattern=r"[0-9a-f]{64}")
    model: str = Field(min_length=1)
    reasoning_effort: Literal["low", "medium", "high"]
    cases: tuple[DiscoveryCase, ...]
    mutations: int = Field(default=4, ge=1, le=4)
    repetitions: Literal[2] = 2
    workers: int = Field(default=12, ge=1, le=12)
    stopping: StoppingPolicy
    manifest_digest: str = Field(pattern=r"[0-9a-f]{64}")

    @model_validator(mode="after")
    def validate_inventory(self) -> "DiscoveryManifest":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        if sum(case.partition == "train" for case in self.cases) != 8:
            raise ValueError("manifest requires eight train cases")
        if sum(case.partition == "validation" for case in self.cases) != 4:
            raise ValueError("manifest requires four validation cases")
        return self


def load_manifest(path: Path) -> DiscoveryManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    manifest = DiscoveryManifest.model_validate(raw)
    payload = dict(raw)
    payload.pop("manifest_digest", None)
    if manifest.manifest_digest != canonical_digest(payload):
        raise ValueError("discovery manifest digest is invalid")
    root = path.parent
    for relative in (manifest.seed_skill, manifest.owner_cards_dir,
                     *(case.starter for case in manifest.cases)):
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root.resolve()) or target.is_symlink():
            raise ValueError(f"manifest path is unsafe: {relative}")
    cards_root = root / manifest.owner_cards_dir
    for case in manifest.cases:
        card = cards_root / f"{case.case_id}.md"
        if not card.is_file():
            raise ValueError(f"fixed owner world model is absent: {card.relative_to(root)}")
        parsed = load_owner_card_markdown(card)
        if parsed.case_id != case.case_id:
            raise ValueError(f"owner card case binding is invalid: {case.case_id}")
    return manifest


class DiscoveryBackend(Protocol):
    def generate(self, *, seed_skill: str, runtime_digest: str) -> str: ...

    def evolve(self, *, seed_skill: str, parent_overlay: str,
               train_feedback: Mapping[str, Any],
               mutation_intent: Mapping[str, Any], runtime_digest: str) -> str: ...

    def evaluate(self, *, cell: CellSpec, prompt: str, skill: str, repo: Path,
                 attempt_dir: Path, owner_card: OwnerCard, pane: Any | None = None
                 ) -> Mapping[str, Any]: ...


class WorkerResult(ClosedModel):
    cell_id: str
    input_digest: str = Field(pattern=r"[0-9a-f]{64}")
    status: Literal["completed", "invalid"]
    attempts: int = Field(ge=1, le=2)
    fulfilled: int = Field(ge=0)
    contract_requirements: int = Field(ge=0)
    escaped_requirements: int = Field(ge=0)
    material_decisions: int = Field(ge=0, le=6)
    tokens: int = Field(ge=0)
    wall_clock_ms: int = Field(ge=0)
    authority_expansion: bool = False
    lineage_valid: bool = True
    discovery_success: bool = False
    hard_veto: bool = False
    critical_misses: tuple[str, ...] = ()
    question_turns: int = Field(ge=0)
    failure_taxonomy: tuple[str, ...] = ()
    failure_evidence: tuple[str, ...] = ()
    artifact_hashes: dict[str, str]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _short_evidence(value: str, limit: int = 240) -> str:
    line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"


def _hash_inventory(root: Path, *, exclude_receipt: bool = True) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root)
        if ".git" in relative_path.parts:
            continue
        if path.is_symlink():
            raise ValueError("cell artifacts may not contain symlinks")
        if path.is_file():
            relative = str(relative_path)
            if exclude_receipt and relative == "receipt.json":
                continue
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _verify_inventory(cell_root: Path) -> dict[str, str]:
    hashes = _hash_inventory(cell_root)
    missing = set(REQUIRED_COMMON_CELL_ARTIFACTS) - set(hashes)
    blocked = [name for name in BLOCKED_CELL_ARTIFACTS if name in hashes]
    if len(blocked) > 1:
        raise ValueError("cell artifact inventory has conflicting blocked states")
    if not blocked:
        missing |= set(REQUIRED_IMPLEMENTED_CELL_ARTIFACTS) - set(hashes)
    if missing:
        raise ValueError(f"cell artifact inventory is incomplete: {sorted(missing)}")
    if not any(name.startswith(".ultimateinterview/") for name in hashes):
        raise ValueError("cell session artifact is absent")
    return hashes


class DiscoveryRunner:
    def __init__(self, manifest_path: Path, run_dir: Path,
                 backend: DiscoveryBackend, dashboard: Any | None = None, *,
                 generation: int = 0, parent_run: Path | None = None) -> None:
        self.manifest_path = manifest_path.resolve(strict=True)
        self.manifest = load_manifest(self.manifest_path)
        self.source_root = self.manifest_path.parent
        self.run_dir = run_dir.resolve()
        self.backend = backend
        self.dashboard = dashboard
        if generation < 0 or (generation == 0) != (parent_run is None):
            raise ValueError("generation zero must not have a parent; evolved generations require one")
        self.generation = generation
        self.parent_run = parent_run.resolve(strict=True) if parent_run is not None else None
        self.state_path = self.run_dir / "state.json"
        self._candidate_lock = threading.Lock()

    def _skill_path(self, candidate_id: str) -> Path:
        return self.run_dir / "candidates" / candidate_id / "SKILL.md"

    def _overlay_path(self, candidate_id: str) -> Path:
        return self.run_dir / "candidates" / candidate_id / "overlay.md"

    def _owner_card(self, case_id: str) -> OwnerCard:
        path = self.source_root / self.manifest.owner_cards_dir / f"{case_id}.md"
        card = load_owner_card_markdown(path)
        if card.case_id != case_id:
            raise ValueError("owner card case binding changed")
        return card

    @staticmethod
    def _effective_skill(seed: str, overlay: str) -> str:
        if not overlay.strip():
            return seed
        return seed + "\n\n" + OVERLAY_BOUNDARY + "\n" + overlay.strip() + "\n"

    @staticmethod
    def _validated_overlay(seed: str, overlay: str) -> str:
        if not isinstance(overlay, str) or not overlay.strip() or len(overlay.encode()) > 8192:
            raise ValueError("generator output must be one non-empty overlay up to 8 KiB")
        normalized = overlay.strip()
        if OVERLAY_BOUNDARY in normalized:
            raise ValueError("generator output must not contain the controller overlay boundary")
        if seed.strip() in normalized:
            raise ValueError("generator output must not repeat the immutable seed")
        return normalized

    def _evolution_context(self, effective_candidates: int) -> dict[str, Any] | None:
        if self.generation == 0:
            return None
        assert self.parent_run is not None
        required = ("receipt.json", "generation-feedback.json", "pareto-archive.json",
                    "candidate-manifest.json")
        documents = {}
        for name in required:
            path = self.parent_run / name
            if not path.is_file():
                raise ValueError(f"parent generation artifact is absent: {name}")
            documents[name] = json.loads(path.read_text(encoding="utf-8"))
        receipt = documents["receipt.json"]
        feedback = documents["generation-feedback.json"]
        archive = documents["pareto-archive.json"]
        candidates = documents["candidate-manifest.json"]
        if (receipt.get("status") != "generation-complete"
                or receipt.get("resumable") is not True
                or receipt.get("final_test_executed") is not False
                or receipt.get("generation") != self.generation - 1
                or receipt.get("runtime_digest") != self.manifest.runtime_digest):
            raise ValueError("parent generation receipt is not eligible for evolution")
        convergence_path = self.parent_run / "convergence.json"
        if convergence_path.is_file():
            parent_convergence = json.loads(convergence_path.read_text(encoding="utf-8"))
            expected = receipt.get("convergence_decision_digest")
            actual = hashlib.sha256(convergence_path.read_bytes()).hexdigest()
            if expected != actual:
                raise ValueError("parent convergence binding is invalid")
            if parent_convergence.get("stop") is True:
                raise ValueError(f"parent generation requested stop: {parent_convergence.get('reason')}")
        if self.generation > self.manifest.stopping.maximum_generation:
            raise ValueError("generation limit reached")
        if feedback.get("generation") != self.generation - 1:
            raise ValueError("parent train feedback generation is invalid")
        allowed_feedback = {"schema", "generation", "candidates"}
        if set(feedback) != allowed_feedback:
            raise ValueError("parent feedback contains non-train evolution inputs")
        parent_ids = archive.get("archive")
        if archive.get("generation") != self.generation - 1 or not isinstance(parent_ids, list) \
                or not parent_ids:
            raise ValueError("parent Pareto archive is invalid")
        if not isinstance(candidates, dict):
            raise ValueError("parent candidate manifest is invalid")
        feedback_candidates = feedback.get("candidates")
        if not isinstance(feedback_candidates, dict):
            raise ValueError("parent candidate feedback is invalid")
        seed = (self.source_root / self.manifest.seed_skill).read_text(encoding="utf-8")
        parent_skills: dict[str, str] = {}
        parent_overlays: dict[str, str] = {}
        for candidate_id in parent_ids:
            path = self.parent_run / "candidates" / candidate_id / "SKILL.md"
            overlay_path = self.parent_run / "candidates" / candidate_id / "overlay.md"
            if candidate_id not in candidates or not path.is_file() or not overlay_path.is_file():
                raise ValueError(f"parent candidate is absent: {candidate_id}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if candidates[candidate_id] != digest:
                raise ValueError(f"parent candidate binding is invalid: {candidate_id}")
            overlay = overlay_path.read_text(encoding="utf-8")
            if overlay.strip():
                self._validated_overlay(seed, overlay)
            if path.read_text(encoding="utf-8") != self._effective_skill(seed, overlay):
                raise ValueError(f"parent candidate is not seed plus one complete overlay: {candidate_id}")
            candidate_feedback = feedback_candidates.get(candidate_id)
            if (not isinstance(candidate_feedback, dict)
                    or set(candidate_feedback) != {"root_causes", "evidence"}
                    or any(not isinstance(candidate_feedback[name], list)
                           or any(not isinstance(item, str) for item in candidate_feedback[name])
                           for name in ("root_causes", "evidence"))):
                raise ValueError(f"parent candidate feedback is invalid: {candidate_id}")
            parent_skills[candidate_id] = digest
            parent_overlays[candidate_id] = hashlib.sha256(overlay.encode()).hexdigest()
        reference_parent = parent_ids[0]
        assignments = []
        for index in range(effective_candidates):
            mutation_id = f"m{index:02d}"
            assignments.append({
                "slot_index": index, "candidate_id": f"g{self.generation:02d}-{mutation_id}",
                "parent_candidate_id": reference_parent,
                "mutation_id": mutation_id,
            })
        artifact_digests = {
            name: hashlib.sha256((self.parent_run / name).read_bytes()).hexdigest()
            for name in required
        }
        return {
            "schema": "DiscoveryEvolutionContext.v3", "generation": self.generation,
            "parent_generation": self.generation - 1,
            "parent_run": str(self.parent_run), "parent_artifact_digests": artifact_digests,
            "train_feedback": feedback, "train_feedback_digest": canonical_digest(feedback),
            "parent_archive": parent_ids, "reference_parent_candidate_id": reference_parent,
            "parent_skill_digests": parent_skills,
            "parent_overlay_digests": parent_overlays,
            "effective_mutations": effective_candidates,
            "assignments": assignments,
        }

    def _initialize_candidates(self, effective_candidates: int,
                               context: Mapping[str, Any] | None) -> dict[str, str]:
        candidates: dict[str, str] = {}
        seed = (self.source_root / self.manifest.seed_skill).read_text(encoding="utf-8")
        if not seed.strip():
            raise ValueError("seed skill must not be empty")
        control_id = f"g{self.generation:02d}-control"
        if self.generation == 0:
            control_skill = seed
            control_overlay = ""
        else:
            assert context is not None and self.parent_run is not None
            parent_id = context["reference_parent_candidate_id"]
            control_overlay = (self.parent_run / "candidates" / parent_id / "overlay.md").read_text(
                encoding="utf-8")
            control_skill = self._effective_skill(seed, control_overlay)
        control_path = self._skill_path(control_id)
        control_path.parent.mkdir(parents=True, exist_ok=False)
        control_path.write_text(control_skill, encoding="utf-8")
        self._overlay_path(control_id).write_text(control_overlay, encoding="utf-8")
        candidates[control_id] = hashlib.sha256(control_skill.encode()).hexdigest()
        if self.dashboard is not None:
            self.dashboard.broadcast(
                f"control ready; generating mutation 1/{effective_candidates}"
            )
        overlay_digests: set[str] = set()
        for index in range(effective_candidates):
            candidate_id = f"g{self.generation:02d}-m{index:02d}"
            if self.generation == 0:
                overlay = self.backend.generate(seed_skill=seed, runtime_digest=self.manifest.runtime_digest)
                parent_overlay = None
            else:
                assert context is not None and self.parent_run is not None
                assignment = context["assignments"][index]
                parent_id = assignment["parent_candidate_id"]
                parent_overlay = (self.parent_run / "candidates" / parent_id / "overlay.md").read_text(
                    encoding="utf-8")
                feedback_by_candidate = context["train_feedback"].get("candidates", {})
                candidate_feedback = feedback_by_candidate.get(parent_id, {})
                bound_feedback = {
                    "schema": context["train_feedback"].get("schema"),
                    "generation": context["train_feedback"].get("generation"),
                    "root_causes": candidate_feedback.get("root_causes", []),
                    "evidence": candidate_feedback.get("evidence", []),
                }
                overlay = self.backend.evolve(
                    seed_skill=seed, parent_overlay=parent_overlay,
                    train_feedback=bound_feedback,
                    mutation_intent={"mode": "open", "operator": "parent-copy-then-edit-v1"},
                    runtime_digest=self.manifest.runtime_digest,
                )
            overlay = self._validated_overlay(seed, overlay)
            overlay_digest = hashlib.sha256(overlay.encode()).hexdigest()
            if overlay_digest in overlay_digests:
                raise ValueError("open mutations must not be byte-identical siblings")
            if parent_overlay is not None and overlay_digest == hashlib.sha256(
                    parent_overlay.strip().encode()).hexdigest():
                raise ValueError("evolved overlay must edit its parent")
            overlay_digests.add(overlay_digest)
            skill = self._effective_skill(seed, overlay)
            path = self._skill_path(candidate_id)
            path.parent.mkdir(parents=True, exist_ok=False)
            path.write_text(skill, encoding="utf-8")
            self._overlay_path(candidate_id).write_text(overlay, encoding="utf-8")
            candidates[candidate_id] = hashlib.sha256(skill.encode()).hexdigest()
            if self.dashboard is not None:
                completed = index + 1
                message = f"mutation {completed}/{effective_candidates} ready"
                if completed < effective_candidates:
                    message += f"; generating mutation {completed + 1}/{effective_candidates}"
                else:
                    message += "; preparing worker cells"
                self.dashboard.broadcast(message)
        return candidates

    def _load_or_initialize(self, effective_candidates: int,
                            effective_workers: int) -> tuple[CoordinatorState, dict[str, str]]:
        context = self._evolution_context(effective_candidates)
        context_digest = canonical_digest(context) if context is not None else None
        binding = canonical_digest({
            "manifest": self.manifest.manifest_digest,
            "backend_semantics": BACKEND_SEMANTICS_VERSION,
            "mutations": effective_candidates, "workers": effective_workers,
            "repetitions": self.manifest.repetitions,
            "generation": self.generation, "evolution_context": context_digest,
        })
        candidate_manifest_path = self.run_dir / "candidate-manifest.json"
        if self.state_path.exists():
            state = CoordinatorState.model_validate_json(self.state_path.read_text())
            if state.manifest_digest != binding:
                raise ValueError("resume effective manifest binding is invalid")
            candidates = json.loads(candidate_manifest_path.read_text())
            if not isinstance(candidates, dict) or len(candidates) != effective_candidates + 1:
                raise ValueError("resume candidate inventory is invalid")
            context_path = self.run_dir / "generation-context.json"
            if context is None:
                if context_path.exists():
                    raise ValueError("generation-zero resume has an unexpected parent context")
            elif (not context_path.is_file()
                  or json.loads(context_path.read_text(encoding="utf-8")) != context):
                raise ValueError("resume evolution context binding is invalid")
            lineage_path = self.run_dir / "candidate-lineage.json"
            if context is not None:
                if not lineage_path.is_file():
                    raise ValueError("resume candidate lineage is absent")
                lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
                lineage_rows = lineage.get("candidates")
                if (lineage.get("schema") != "DiscoveryCandidateLineage.v3"
                        or not isinstance(lineage_rows, list)
                        or len(lineage_rows) != len(context["assignments"])):
                    raise ValueError("resume candidate lineage binding is invalid")
                for assignment, row in zip(context["assignments"], lineage_rows):
                    for key in ("candidate_id", "parent_candidate_id", "mutation_id"):
                        if row.get(key) != assignment[key]:
                            raise ValueError("resume candidate lineage binding is invalid")
                    parent_id = assignment["parent_candidate_id"]
                    candidate_id = assignment["candidate_id"]
                    overlay_path = self._overlay_path(candidate_id)
                    if (row.get("operator") != "parent-copy-then-edit-v1"
                            or row.get("parent_skill_digest")
                            != context["parent_skill_digests"][parent_id]
                            or row.get("parent_overlay_digest")
                            != context["parent_overlay_digests"][parent_id]
                            or row.get("skill_digest") != candidates.get(candidate_id)
                            or not overlay_path.is_file()
                            or row.get("overlay_digest")
                            != hashlib.sha256(overlay_path.read_bytes()).hexdigest()):
                        raise ValueError("resume candidate lineage binding is invalid")
            seed = (self.source_root / self.manifest.seed_skill).read_text(encoding="utf-8")
            for candidate_id, digest in candidates.items():
                skill_path = self._skill_path(candidate_id)
                overlay_path = self._overlay_path(candidate_id)
                if (not skill_path.is_file() or not overlay_path.is_file()
                        or hashlib.sha256(skill_path.read_bytes()).hexdigest() != digest):
                    raise ValueError(f"resume candidate binding is invalid: {candidate_id}")
                overlay = overlay_path.read_text(encoding="utf-8")
                if skill_path.read_text(encoding="utf-8") != self._effective_skill(seed, overlay):
                    raise ValueError(f"resume overlay binding is invalid: {candidate_id}")
            return state, candidates
        if self.run_dir.exists() and any(self.run_dir.iterdir()):
            raise ValueError("new discovery run directory is not empty")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if context is not None:
            _write_json(self.run_dir / "generation-context.json", context)
        candidates = self._initialize_candidates(effective_candidates, context)
        _write_json(candidate_manifest_path, candidates)
        if context is not None:
            _write_json(self.run_dir / "candidate-lineage.json", {
                "schema": "DiscoveryCandidateLineage.v3", "generation": self.generation,
                "train_feedback_digest": context["train_feedback_digest"],
                "candidates": [{
                    "candidate_id": f"g{self.generation:02d}-m{index:02d}",
                    "parent_candidate_id": parent_id,
                    "parent_skill_digest": context["parent_skill_digests"][parent_id],
                    "parent_overlay_digest": context["parent_overlay_digests"][parent_id],
                    "overlay_digest": hashlib.sha256(self._overlay_path(
                        f"g{self.generation:02d}-m{index:02d}").read_bytes()).hexdigest(),
                    "skill_digest": candidates[f"g{self.generation:02d}-m{index:02d}"],
                    "mutation_id": assignment["mutation_id"],
                    "operator": "parent-copy-then-edit-v1",
                } for index, assignment in enumerate(context["assignments"])
                  for parent_id in (assignment["parent_candidate_id"],)],
            })
        state = CoordinatorState(manifest_digest=binding, cells={})
        write_coordinator_state(self.state_path, state)
        return state, candidates

    def _input_digest(self, cell: CellSpec, skill_digest: str) -> str:
        case = next(row for row in self.manifest.cases if row.case_id == cell.case_id)
        starter = self.source_root / case.starter
        starter_hashes = _hash_inventory(starter, exclude_receipt=False)
        return canonical_digest({
            "manifest": self.manifest.manifest_digest, "cell": cell.model_dump(),
            "backend_semantics": BACKEND_SEMANTICS_VERSION,
            "skill": skill_digest, "prompt": case.prompt, "starter": starter_hashes,
            "owner_card": canonical_digest(self._owner_card(cell.case_id).model_dump(mode="json")),
            "owner_responder_version": self.manifest.owner_responder_version,
        })

    def _work(self, cell: CellSpec, skill_digest: str, pane: Any | None = None) -> WorkerResult:
        started = time.monotonic()
        input_digest = self._input_digest(cell, skill_digest)
        case = next(row for row in self.manifest.cases if row.case_id == cell.case_id)
        if pane is not None:
            pane.start_cell(candidate=cell.candidate_id, case=cell.case_id,
                            repetition=cell.repetition)
        cell_root = self.run_dir / "cells" / cell.cell_id
        if cell_root.exists():
            shutil.rmtree(cell_root)
        attempts_root = cell_root / "attempts"
        attempts_root.mkdir(parents=True)
        last_error = "unknown failure"
        for attempt in (1, 2):
            attempt_dir = attempts_root / f"attempt-{attempt}"
            repo = attempt_dir / "repo"
            shutil.copytree(self.source_root / case.starter, repo)
            evidence = attempt_dir / "evidence"
            evidence.mkdir()
            try:
                if pane is not None:
                    pane.stage(f"attempt-{attempt}")
                raw = dict(self.backend.evaluate(
                    cell=cell, prompt=case.prompt,
                    skill=self._skill_path(cell.candidate_id).read_text(encoding="utf-8"),
                    repo=repo, attempt_dir=evidence, owner_card=self._owner_card(cell.case_id),
                    pane=pane,
                ))
                required_numbers = ("fulfilled", "contract_requirements", "escaped_requirements",
                                    "material_decisions", "question_turns")
                if any(type(raw.get(name)) is not int for name in required_numbers):
                    raise ValueError("backend requirement counts are invalid")
                if raw["material_decisions"] > 6:
                    raise ValueError("backend exceeded the material decision limit")
                _verify_inventory(evidence)
                for source in evidence.iterdir():
                    target = cell_root / source.name
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copy2(source, target)
                hashes = _verify_inventory(cell_root)
                return WorkerResult(
                    cell_id=cell.cell_id, input_digest=input_digest, status="completed",
                    attempts=attempt, fulfilled=raw["fulfilled"],
                    contract_requirements=raw["contract_requirements"],
                    escaped_requirements=raw["escaped_requirements"],
                    material_decisions=raw["material_decisions"],
                    tokens=int(raw.get("tokens", 0)),
                    wall_clock_ms=int((time.monotonic() - started) * 1000),
                    authority_expansion=bool(raw.get("authority_expansion", False)),
                    lineage_valid=bool(raw.get("lineage_valid", True)),
                    discovery_success=bool(raw.get("discovery_success", False)),
                    hard_veto=bool(raw.get("hard_veto", False)),
                    critical_misses=tuple(map(str, raw.get("critical_misses", ()))),
                    question_turns=int(raw["question_turns"]),
                    failure_taxonomy=tuple(map(str, raw.get("failure_taxonomy", ()))),
                    failure_evidence=tuple(map(str, raw.get("failure_evidence", ()))),
                    artifact_hashes=hashes,
                )
            except Exception as error:  # a malformed cell is an experimental result
                last_error = f"{type(error).__name__}: {error}"
                (attempt_dir / "error.txt").write_text(last_error + "\n", encoding="utf-8")
        # Preserve attempts and create deterministic minimum evidence for the invalid receipt.
        (cell_root / "transcript.json").write_text("{}\n")
        (cell_root / "selections.json").write_text("{}\n")
        (cell_root / "owner-exchanges.json").write_text("{}\n")
        (cell_root / "discovery-result.json").write_text("{}\n")
        (cell_root / "implementation.diff").write_text("")
        (cell_root / "postmortem.md").write_text("# Invalid cell\n\n" + last_error + "\n")
        (cell_root / "postmortem-result.json").write_text(
            json.dumps({"status": "invalid", "error": last_error}) + "\n")
        session = cell_root / ".ultimateinterview" / cell.cell_id
        session.mkdir(parents=True)
        (session / "invalid.txt").write_text(last_error + "\n")
        return WorkerResult(
            cell_id=cell.cell_id, input_digest=input_digest, status="invalid", attempts=2,
            fulfilled=0, contract_requirements=1, escaped_requirements=0,
            material_decisions=0, tokens=0,
            wall_clock_ms=int((time.monotonic() - started) * 1000),
            question_turns=0, hard_veto=True, critical_misses=("invalid-cell",),
            failure_taxonomy=("invalid-cell",), failure_evidence=(last_error,),
            artifact_hashes=_verify_inventory(cell_root),
        )

    def _validate_reusable(self, receipt: CellReceipt) -> bool:
        root = self.run_dir / "cells" / receipt.cell_id
        if not root.is_dir():
            return False
        actual = _hash_inventory(root)
        recorded = {
            name: digest for name, digest in receipt.artifact_hashes.items()
            if ".git" not in Path(name).parts
        }
        return actual == recorded

    def run(self, *, max_candidates: int | None = None,
            max_parallel: int | None = None) -> Path:
        # This limit is the number of open mutations.  The immutable control is
        # always added, so a normal run has five treatments across twelve case panes.
        effective_candidates = min(max_candidates or self.manifest.mutations,
                                   self.manifest.mutations)
        effective_workers = min(max_parallel or self.manifest.workers,
                                self.manifest.workers, 12)
        if effective_candidates < 1 or effective_workers < 1:
            raise ValueError("effective limits must be positive")
        if self.dashboard is not None:
            self.dashboard.broadcast(
                f"run initialized; loading seed and preparing {effective_candidates} mutations"
            )
        state, candidates = self._load_or_initialize(effective_candidates, effective_workers)
        candidate_ids = tuple(sorted(candidates))
        # One stable pane per case. Each round starts one cell for every case before
        # scheduling the next candidate/repetition, so all twelve cases can progress
        # concurrently without sharing a pane.
        schedule = tuple(
            CellSpec(candidate_id=candidate_id, partition=case.partition,
                     case_id=case.case_id, repetition=repetition)
            for repetition in range(1, self.manifest.repetitions + 1)
            for candidate_id in candidate_ids
            for case in self.manifest.cases
        )
        results: dict[str, WorkerResult] = {}
        pending = []
        for cell in schedule:
            digest = self._input_digest(cell, candidates[cell.candidate_id])
            receipt = state.cells.get(cell.cell_id)
            if (receipt is not None and receipt.input_digest == digest
                    and self._validate_reusable(receipt)):
                result_path = self.run_dir / "cells" / cell.cell_id / "normalized-result.json"
                result = json.loads(result_path.read_text())
                results[cell.cell_id] = WorkerResult(
                    cell_id=cell.cell_id, input_digest=digest, status=receipt.status,
                    attempts=receipt.attempts, fulfilled=int(result.get("fulfilled", 0)),
                    contract_requirements=int(result.get("contract_requirements", 1)),
                    escaped_requirements=int(result.get("escaped_requirements", 0)),
                    material_decisions=int(result.get("material_decisions", 0)),
                    tokens=int(result.get("tokens", 0)),
                    wall_clock_ms=int(result.get("wall_clock_ms", 0)),
                    authority_expansion=bool(result.get("authority_expansion", False)),
                    lineage_valid=bool(result.get("lineage_valid", receipt.status == "completed")),
                    discovery_success=bool(result.get("discovery_success", False)),
                    hard_veto=bool(result.get("hard_veto", receipt.status != "completed")),
                    critical_misses=tuple(result.get("critical_misses", ())),
                    question_turns=int(result.get("question_turns", 0)),
                    failure_taxonomy=tuple(result.get("failure_taxonomy", ())),
                    failure_evidence=tuple(result.get("failure_evidence", ())),
                    artifact_hashes=receipt.artifact_hashes,
                )
            else:
                pending.append(cell)
        case_indices = {case.case_id: index for index, case in enumerate(self.manifest.cases)}
        case_locks = {case.case_id: threading.Lock() for case in self.manifest.cases}
        if self.dashboard is not None:
            self.dashboard.broadcast(
                f"worker cells ready; starting {min(effective_workers, len(pending))} concurrent cells"
            )
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as pool:
            def assigned(cell: CellSpec) -> WorkerResult:
                pane = (self.dashboard.worker(case_indices[cell.case_id])
                        if self.dashboard is not None else None)
                with case_locks[cell.case_id]:
                    return self._work(cell, candidates[cell.candidate_id], pane)

            futures = {pool.submit(assigned, cell): cell for cell in pending}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                # Persist a complete result payload before hashing it into the receipt.
                result_path = self.run_dir / "cells" / result.cell_id / "normalized-result.json"
                payload = result.model_dump(mode="json", exclude={"artifact_hashes"})
                _write_json(result_path, payload)
                hashes = _verify_inventory(result_path.parent)
                result = result.model_copy(update={"artifact_hashes": hashes})
                receipt = CellReceipt(
                    cell_id=result.cell_id, input_digest=result.input_digest,
                    status=result.status, attempts=result.attempts, artifact_hashes=hashes,
                )
                _write_json(result_path.parent / "receipt.json",
                            receipt.model_dump(mode="json", by_alias=True))
                state = merge_receipt(state, receipt)
                write_coordinator_state(self.state_path, state)
                results[result.cell_id] = result
        feedback = [result for cell_id, result in results.items() if "--train--" in cell_id]
        _write_json(self.run_dir / "generation-feedback.json", {
            "schema": "DiscoveryGenerationFeedback.v2", "generation": self.generation,
            "candidates": {
                candidate_id: {
                    "root_causes": sorted({item for row in feedback
                                           if row.cell_id.startswith(candidate_id + "--")
                                           for item in (*row.failure_taxonomy, *row.critical_misses)}),
                    "evidence": sorted({shortened for row in feedback
                                        if row.cell_id.startswith(candidate_id + "--")
                                        for item in row.failure_evidence
                                        if (shortened := _short_evidence(item))}),
                } for candidate_id in candidate_ids
            },
        })
        summaries = []
        for candidate_id in candidate_ids:
            rows = [result for result in results.values()
                    if result.cell_id.startswith(candidate_id + "--validation--")]
            summaries.append(summarize_candidate(
                candidate_id,
                [1.0 if row.discovery_success and not row.hard_veto else 0.0 for row in rows],
                [row.material_decisions for row in rows],
                skill_bytes=self._skill_path(candidate_id).stat().st_size,
                total_tokens=sum(row.tokens for row in rows),
                wall_clock_ms=sum(row.wall_clock_ms for row in rows),
            ))
        archive = pareto_archive(summaries)
        _write_json(self.run_dir / "pareto-archive.json", {
            "schema": "DiscoveryParetoArchive.v1", "generation": self.generation,
            "candidates": [row.model_dump(mode="json") for row in summaries],
            "archive": [row.candidate_id for row in archive],
        })
        convergence = convergence_decision(
            self.run_dir, self.manifest.stopping.model_dump(mode="json", by_alias=True),
            effective_candidates=effective_candidates + 1, terminal_cells=len(state.cells),
            expected_cells=(effective_candidates + 1) * len(self.manifest.cases) * self.manifest.repetitions,
        )
        _write_json(self.run_dir / "convergence.json", convergence)
        comparison_digest = None
        convergence_digest = hashlib.sha256(
            (self.run_dir / "convergence.json").read_bytes()).hexdigest()
        _write_json(self.run_dir / "receipt.json", {
            "schema": "DiscoveryGenerationReceipt.v1", "status": "generation-complete",
            "generation": self.generation, "resumable": True, "final_test_executed": False,
            "runtime_digest": self.manifest.runtime_digest,
            "backend_semantics": BACKEND_SEMANTICS_VERSION,
            "effective_mutations": effective_candidates,
            "effective_candidates": effective_candidates + 1,
            "effective_workers": effective_workers, "terminal_cells": len(state.cells),
            "pareto_archive": [row.candidate_id for row in archive],
            "convergence_decision_digest": convergence_digest,
            "stop_requested": convergence["stop"], "stop_reason": convergence["reason"],
            "comparison_report_digest": comparison_digest,
            "mutation_operator": ("independent-overlay-v1" if self.generation == 0
                                  else "parent-copy-then-edit-v1"),
        })
        if self.dashboard is not None:
            self.dashboard.finish(
                pareto=[row.candidate_id for row in archive],
                run_directory=self.run_dir,
            )
        return self.run_dir
