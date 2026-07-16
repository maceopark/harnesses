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
import queue
import shutil
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from .discovery import (
    CellReceipt, CellSpec, ClosedModel, CoordinatorState, canonical_digest, fidelity,
    merge_receipt, pareto_archive, schedule_cells, summarize_candidate,
    write_coordinator_state,
)


REQUIRED_CELL_ARTIFACTS = (
    "transcript.json", "selections.json", "implementation.diff", "postmortem.md",
    "postmortem-result.json",
)


class DiscoveryCase(ClosedModel):
    case_id: str = Field(min_length=1)
    partition: Literal["train", "validation"]
    prompt: str = Field(min_length=1)
    starter: str = Field(min_length=1)


class DiscoveryManifest(ClosedModel):
    schema_: Literal["DiscoveryManifest.v1"] = Field(
        default="DiscoveryManifest.v1", alias="schema", serialization_alias="schema"
    )
    study_id: str = Field(min_length=1)
    answer_seed: str = Field(min_length=1)
    seed_skill: str = Field(min_length=1)
    runtime_digest: str = Field(pattern=r"[0-9a-f]{64}")
    model: str = Field(min_length=1)
    reasoning_effort: Literal["low", "medium", "high"]
    cases: tuple[DiscoveryCase, ...]
    candidates: int = Field(default=4, ge=1, le=4)
    repetitions: Literal[2] = 2
    workers: int = Field(default=4, ge=1, le=4)
    manifest_digest: str = Field(pattern=r"[0-9a-f]{64}")

    @model_validator(mode="after")
    def validate_inventory(self) -> "DiscoveryManifest":
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        if sum(case.partition == "train" for case in self.cases) != 6:
            raise ValueError("manifest requires six train cases")
        if sum(case.partition == "validation" for case in self.cases) != 3:
            raise ValueError("manifest requires three validation cases")
        return self


def load_manifest(path: Path) -> DiscoveryManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    manifest = DiscoveryManifest.model_validate(raw)
    payload = dict(raw)
    payload.pop("manifest_digest", None)
    if manifest.manifest_digest != canonical_digest(payload):
        raise ValueError("discovery manifest digest is invalid")
    root = path.parent
    for relative in (manifest.seed_skill, *(case.starter for case in manifest.cases)):
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root.resolve()) or target.is_symlink():
            raise ValueError(f"manifest path is unsafe: {relative}")
    return manifest


class DiscoveryBackend(Protocol):
    def generate(self, *, seed_skill: str, runtime_digest: str) -> str: ...

    def evolve(self, *, parent_skill: str, train_feedback: Mapping[str, Any],
               runtime_digest: str) -> str: ...

    def evaluate(self, *, cell: CellSpec, prompt: str, skill: str, repo: Path,
                 attempt_dir: Path, answer_seed: str, pane: Any | None = None
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
    missing = set(REQUIRED_CELL_ARTIFACTS) - set(hashes)
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
                or receipt.get("generation") != self.generation - 1):
            raise ValueError("parent generation receipt is not eligible for evolution")
        if feedback.get("generation") != self.generation - 1:
            raise ValueError("parent train feedback generation is invalid")
        allowed_feedback = {"schema", "generation", "root_causes", "evidence"}
        if set(feedback) != allowed_feedback:
            raise ValueError("parent feedback contains non-train evolution inputs")
        parent_ids = archive.get("archive")
        if archive.get("generation") != self.generation - 1 or not isinstance(parent_ids, list) \
                or not parent_ids:
            raise ValueError("parent Pareto archive is invalid")
        if not isinstance(candidates, dict):
            raise ValueError("parent candidate manifest is invalid")
        parent_skills: dict[str, str] = {}
        for candidate_id in parent_ids:
            path = self.parent_run / "candidates" / candidate_id / "SKILL.md"
            if candidate_id not in candidates or not path.is_file():
                raise ValueError(f"parent candidate is absent: {candidate_id}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if candidates[candidate_id] != digest:
                raise ValueError(f"parent candidate binding is invalid: {candidate_id}")
            parent_skills[candidate_id] = digest
        assignments = [parent_ids[index % len(parent_ids)] for index in range(effective_candidates)]
        artifact_digests = {
            name: hashlib.sha256((self.parent_run / name).read_bytes()).hexdigest()
            for name in required
        }
        return {
            "schema": "DiscoveryEvolutionContext.v1", "generation": self.generation,
            "parent_generation": self.generation - 1,
            "parent_run": str(self.parent_run), "parent_artifact_digests": artifact_digests,
            "train_feedback": feedback, "train_feedback_digest": canonical_digest(feedback),
            "parent_archive": parent_ids, "parent_skill_digests": parent_skills,
            "assignments": assignments,
        }

    def _initialize_candidates(self, effective_candidates: int,
                               context: Mapping[str, Any] | None) -> dict[str, str]:
        candidates: dict[str, str] = {}
        seed = (self.source_root / self.manifest.seed_skill).read_text(encoding="utf-8")
        if not seed.strip():
            raise ValueError("seed skill must not be empty")
        for index in range(effective_candidates):
            candidate_id = f"g{self.generation:02d}-c{index:02d}"
            if self.generation == 0:
                skill = seed if index == 0 else self.backend.generate(
                    seed_skill=seed, runtime_digest=self.manifest.runtime_digest
                )
            else:
                assert context is not None and self.parent_run is not None
                parent_id = context["assignments"][index]
                parent_skill = (self.parent_run / "candidates" / parent_id / "SKILL.md").read_text(
                    encoding="utf-8")
                skill = self.backend.evolve(
                    parent_skill=parent_skill, train_feedback=context["train_feedback"],
                    runtime_digest=self.manifest.runtime_digest,
                )
            if not isinstance(skill, str) or not skill.strip() or len(skill.encode()) > 8192:
                raise ValueError("generator output must be one non-empty SKILL.md up to 8 KiB")
            path = self._skill_path(candidate_id)
            path.parent.mkdir(parents=True, exist_ok=False)
            path.write_text(skill, encoding="utf-8")
            candidates[candidate_id] = hashlib.sha256(skill.encode()).hexdigest()
        return candidates

    def _load_or_initialize(self, effective_candidates: int,
                            effective_workers: int) -> tuple[CoordinatorState, dict[str, str]]:
        context = self._evolution_context(effective_candidates)
        context_digest = canonical_digest(context) if context is not None else None
        binding = canonical_digest({
            "manifest": self.manifest.manifest_digest,
            "candidates": effective_candidates, "workers": effective_workers,
            "repetitions": self.manifest.repetitions,
            "generation": self.generation, "evolution_context": context_digest,
        })
        candidate_manifest_path = self.run_dir / "candidate-manifest.json"
        if self.state_path.exists():
            state = CoordinatorState.model_validate_json(self.state_path.read_text())
            if state.manifest_digest != binding:
                raise ValueError("resume effective manifest binding is invalid")
            candidates = json.loads(candidate_manifest_path.read_text())
            if not isinstance(candidates, dict) or len(candidates) != effective_candidates:
                raise ValueError("resume candidate inventory is invalid")
            context_path = self.run_dir / "generation-context.json"
            if context is None:
                if context_path.exists():
                    raise ValueError("generation-zero resume has an unexpected parent context")
            elif (not context_path.is_file()
                  or json.loads(context_path.read_text(encoding="utf-8")) != context):
                raise ValueError("resume evolution context binding is invalid")
            for candidate_id, digest in candidates.items():
                if hashlib.sha256(self._skill_path(candidate_id).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"resume candidate binding is invalid: {candidate_id}")
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
                "schema": "DiscoveryCandidateLineage.v1", "generation": self.generation,
                "train_feedback_digest": context["train_feedback_digest"],
                "candidates": [{
                    "candidate_id": f"g{self.generation:02d}-c{index:02d}",
                    "parent_candidate_id": parent_id,
                    "parent_skill_digest": context["parent_skill_digests"][parent_id],
                    "skill_digest": candidates[f"g{self.generation:02d}-c{index:02d}"],
                } for index, parent_id in enumerate(context["assignments"])],
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
            "skill": skill_digest, "prompt": case.prompt, "starter": starter_hashes,
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
                    repo=repo, attempt_dir=evidence, answer_seed=self.manifest.answer_seed,
                    pane=pane,
                ))
                required_numbers = ("fulfilled", "contract_requirements", "escaped_requirements",
                                    "material_decisions")
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
        effective_candidates = min(max_candidates or self.manifest.candidates,
                                   self.manifest.candidates)
        effective_workers = min(max_parallel or self.manifest.workers,
                                self.manifest.workers, 4)
        if effective_candidates < 1 or effective_workers < 1:
            raise ValueError("effective limits must be positive")
        state, candidates = self._load_or_initialize(effective_candidates, effective_workers)
        candidate_ids = tuple(sorted(candidates))
        train = tuple(case.case_id for case in self.manifest.cases if case.partition == "train")
        validation = tuple(case.case_id for case in self.manifest.cases
                           if case.partition == "validation")
        schedule = schedule_cells(candidate_ids, (("train", train), ("validation", validation)), 2)
        results: dict[str, WorkerResult] = {}
        for partition in ("train", "validation"):
            pending = []
            for cell in (row for row in schedule if row.partition == partition):
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
                        tokens=int(result.get("tokens", 0)), wall_clock_ms=0,
                        authority_expansion=bool(result.get("authority_expansion", False)),
                        lineage_valid=bool(result.get("lineage_valid", receipt.status == "completed")),
                        failure_taxonomy=tuple(result.get("failure_taxonomy", ())),
                        failure_evidence=tuple(result.get("failure_evidence", ())),
                        artifact_hashes=receipt.artifact_hashes,
                    )
                else:
                    pending.append(cell)
            with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as pool:
                panes: queue.SimpleQueue[Any | None] = queue.SimpleQueue()
                for index in range(effective_workers):
                    panes.put(self.dashboard.worker(index) if self.dashboard is not None else None)

                def assigned(cell: CellSpec) -> WorkerResult:
                    pane = panes.get()
                    try:
                        return self._work(cell, candidates[cell.candidate_id], pane)
                    finally:
                        panes.put(pane)

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
            if partition == "train":
                feedback = [result for cell_id, result in results.items()
                            if "--train--" in cell_id]
                _write_json(self.run_dir / "generation-feedback.json", {
                    "schema": "DiscoveryGenerationFeedback.v1", "generation": self.generation,
                    "root_causes": sorted({item for row in feedback
                                           for item in row.failure_taxonomy}),
                    "evidence": sorted({shortened for row in feedback
                                        for item in row.failure_evidence
                                        if (shortened := _short_evidence(item))}),
                })
        summaries = []
        for candidate_id in candidate_ids:
            rows = [result for result in results.values()
                    if result.cell_id.startswith(candidate_id + "--validation--")]
            summaries.append(summarize_candidate(
                candidate_id,
                [fidelity(row.fulfilled, row.contract_requirements, row.escaped_requirements,
                          invalid=row.status == "invalid",
                          authority_expansion=row.authority_expansion,
                          lineage_valid=row.lineage_valid) for row in rows],
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
        _write_json(self.run_dir / "receipt.json", {
            "schema": "DiscoveryGenerationReceipt.v1", "status": "generation-complete",
            "generation": self.generation, "resumable": True, "final_test_executed": False,
            "champion_id": None, "effective_candidates": effective_candidates,
            "effective_workers": effective_workers, "terminal_cells": len(state.cells),
            "pareto_archive": [row.candidate_id for row in archive],
        })
        if self.dashboard is not None:
            self.dashboard.finish(
                pareto=[row.candidate_id for row in archive],
                run_directory=self.run_dir,
            )
        return self.run_dir
