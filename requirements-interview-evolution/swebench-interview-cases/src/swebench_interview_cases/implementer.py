"""Fresh implementation execution and decision-log evidence capture."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from . import MODEL_ID, MODEL_REASONING_EFFORT
from .model import CodexJsonModel, CodexWorkspaceImplementer
from .schemas import canonical_json_bytes


DECISION_KEYS = frozenset({
    "timestamp", "gap", "options_considered", "choice", "reason",
    "observable_impact", "reversibility",
})

DECISION_MATERIALITY_SCHEMA_VERSION = "DecisionMaterialityReview.v1"
DECISION_MATERIALITY_RUBRIC = (
    "Independently review every implementation decision. Logging a decision is never itself a "
    "defect. Mark it material only if the chosen option changes or contradicts an authorized "
    "initial user decision, crosses a product authority boundary by selecting user-visible "
    "behavior not delegated by the contract, or introduces high risk involving security, safety, "
    "data loss, irreversible migration, substantial cost, or broad compatibility. Internal, "
    "reversible, contract-admissible implementation choices are non-material. Set material to the "
    "logical OR of the three boundary flags and review every decision exactly once in input order."
)
DECISION_MATERIALITY_RUBRIC_SHA256 = hashlib.sha256(
    DECISION_MATERIALITY_RUBRIC.encode()
).hexdigest()

DECISION_MATERIALITY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["schema", "reviews", "summary"],
    "properties": {
        "schema": {
            "type": "string", "const": DECISION_MATERIALITY_SCHEMA_VERSION,
        },
        "reviews": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": [
                "decision_index", "changes_initial_decision", "crosses_authority_boundary",
                "high_risk", "material", "reason",
            ],
            "properties": {
                "decision_index": {"type": "integer", "minimum": 0},
                "changes_initial_decision": {"type": "boolean"},
                "crosses_authority_boundary": {"type": "boolean"},
                "high_risk": {"type": "boolean"},
                "material": {"type": "boolean"},
                "reason": {"type": "string", "minLength": 1},
            },
        }},
        "summary": {"type": "string"},
    },
}


def validate_decision_materiality(
    value: Any, *, decision_count: int,
) -> dict[str, Any]:
    if value.get("schema") != DECISION_MATERIALITY_SCHEMA_VERSION:
        raise ValueError("decision materiality schema version drifted")
    reviews = value["reviews"]
    if [item["decision_index"] for item in reviews] != list(range(decision_count)):
        raise ValueError("decision materiality review must cover every decision in order")
    for item in reviews:
        expected = any((
            item["changes_initial_decision"], item["crosses_authority_boundary"],
            item["high_risk"],
        ))
        if item["material"] is not expected:
            raise ValueError("decision materiality contradicts its boundary flags")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )


def validate_decision(value: Any, *, line_number: int) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != DECISION_KEYS:
        raise ValueError(f"decision.jsonl line {line_number} has invalid fields")
    for key in DECISION_KEYS - {"options_considered"}:
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"decision.jsonl line {line_number} has invalid {key}")
    options = value["options_considered"]
    if (
        not isinstance(options, list) or len(options) < 2
        or any(not isinstance(item, str) or not item.strip() for item in options)
    ):
        raise ValueError(
            f"decision.jsonl line {line_number} must contain at least two options"
        )
    return value


def read_decisions(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            raise ValueError(f"decision.jsonl line {line_number} is blank")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"decision.jsonl line {line_number} is invalid JSON") from exc
        decision = validate_decision(value, line_number=line_number)
        digest = hashlib.sha256(canonical_json_bytes(decision)).hexdigest()
        if digest in seen:
            raise ValueError("decision.jsonl contains a duplicate decision")
        seen.add(digest)
        decisions.append(decision)
    return tuple(decisions)


def review_decision_materiality(
    *, public_request: str, contract: Mapping[str, Any],
    audited_evidence: Mapping[str, Any], decisions: tuple[dict[str, Any], ...],
    output_dir: Path,
) -> dict[str, Any]:
    if decisions:
        materiality = CodexJsonModel(output_dir).generate(
            role="decision-materiality-review",
            instructions=DECISION_MATERIALITY_RUBRIC,
            payload={
                "public_request": public_request, "contract": contract,
                "audited_evidence": audited_evidence, "decisions": list(decisions),
            },
            schema=DECISION_MATERIALITY_SCHEMA,
        )
    else:
        materiality = {
            "schema": DECISION_MATERIALITY_SCHEMA_VERSION,
            "reviews": [], "summary": "No autonomous decisions recorded.",
        }
    validate_decision_materiality(materiality, decision_count=len(decisions))
    _write_json(output_dir / "decision-materiality.json", materiality)
    return materiality


def materialize_implementation_materiality(
    *, source_dir: Path, output_dir: Path, public_request: str,
    audited_evidence: Mapping[str, Any], contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a sealed overlay that reviews a legacy implementation symmetrically."""

    source_manifest = json.loads(
        (source_dir / "implementation-manifest.json").read_text(encoding="utf-8")
    )
    decisions = read_decisions(source_dir / "decision.jsonl")
    if source_manifest.get("decision_count") != len(decisions):
        raise ValueError("legacy implementation decision count drifted")
    output_dir.mkdir(parents=True, exist_ok=False)
    for source in sorted(source_dir.iterdir()):
        if source.name in {
            "implementation-manifest.json", "decision-materiality.json",
        } or source.name.endswith("-decision-materiality-review.json"):
            continue
        os.symlink(source.resolve(), output_dir / source.name, target_is_directory=source.is_dir())
    materiality = review_decision_materiality(
        public_request=public_request, contract=contract,
        audited_evidence=audited_evidence, decisions=decisions, output_dir=output_dir,
    )
    artifacts = dict(source_manifest.get("artifact_sha256", {}))
    artifacts["decision-materiality.json"] = _sha(
        output_dir / "decision-materiality.json"
    )
    for record in sorted(output_dir.glob("*-decision-materiality-review.json")):
        artifacts[record.name] = _sha(record)
    manifest = {
        **source_manifest,
        "material_decision_count": sum(item["material"] for item in materiality["reviews"]),
        "materiality_rubric_sha256": DECISION_MATERIALITY_RUBRIC_SHA256,
        "materiality_schema_version": DECISION_MATERIALITY_SCHEMA_VERSION,
        "materiality_reviewer_model": MODEL_ID,
        "materiality_reviewer_reasoning_effort": MODEL_REASONING_EFFORT,
        "decision_review_sha256": _sha(output_dir / "decision-materiality.json"),
        "artifact_sha256": artifacts,
    }
    _write_json(output_dir / "implementation-manifest.json", manifest)
    return manifest


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def run_fresh_implementation(
    *, source_repository: Path, base_commit: str, public_request: str,
    audited_evidence: Mapping[str, Any], contract: Mapping[str, Any], output_dir: Path,
) -> dict[str, Any]:
    """Implement one contract in a disposable clone and preserve every decision."""

    output_dir.mkdir(parents=True, exist_ok=False)
    checkout = output_dir / "checkout"
    clone = _run(["git", "clone", "--shared", "--no-checkout", str(source_repository), str(checkout)])
    if clone.returncode != 0:
        raise RuntimeError(f"fresh implementation clone failed: {clone.stderr[-2000:]}")
    switch = _run(["git", "switch", "--detach", base_commit], cwd=checkout)
    if switch.returncode != 0:
        raise RuntimeError(f"fresh implementation checkout failed: {switch.stderr[-2000:]}")
    head = _run(["git", "rev-parse", "HEAD"], cwd=checkout)
    status = _run(["git", "status", "--porcelain"], cwd=checkout)
    if head.stdout.strip() != base_commit or status.returncode != 0 or status.stdout:
        raise RuntimeError("fresh implementation did not start from the clean base commit")

    implementer = CodexWorkspaceImplementer(output_dir / "implementer-call.json")
    result = implementer.implement(
        repository=checkout, public_request=public_request,
        audited_evidence=audited_evidence, contract=contract,
    )
    decision_source = checkout / "decision.jsonl"
    decisions = read_decisions(decision_source)
    decision_output = output_dir / "decision.jsonl"
    decision_output.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in decisions),
        encoding="utf-8",
    )
    materiality = review_decision_materiality(
        public_request=public_request, contract=contract,
        audited_evidence=audited_evidence, decisions=decisions, output_dir=output_dir,
    )

    intent = _run(["git", "add", "-N", "--all"], cwd=checkout)
    if intent.returncode != 0:
        raise RuntimeError(f"failed to stage intent-to-add evidence: {intent.stderr[-2000:]}")
    diff = _run(
        ["git", "diff", "--binary", "--no-ext-diff", "--", ".", ":!decision.jsonl"],
        cwd=checkout,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"failed to capture implementation patch: {diff.stderr[-2000:]}")
    patch_path = output_dir / "implementation.patch"
    patch_path.write_text(diff.stdout, encoding="utf-8")
    final_status = _run(["git", "status", "--porcelain"], cwd=checkout)
    status_value = {
        "schema": "FreshImplementationStatus.v1",
        "base_commit": base_commit,
        "head": head.stdout.strip(),
        "decision_count": len(decisions),
        "completed": result["completed"],
        "summary": result["summary"],
        "tests": result["tests"],
        "worktree_status": final_status.stdout.splitlines(),
    }
    status_path = output_dir / "implementation-status.json"
    _write_json(status_path, status_value)
    artifacts = (
        "implementer-call.json", "decision.jsonl", "implementation.patch",
        "implementation-status.json", "decision-materiality.json",
    )
    artifacts += tuple(
        path.name for path in sorted(output_dir.glob("*-decision-materiality-review.json"))
    )
    manifest = {
        "schema": "FreshImplementationRun.v1",
        "model": MODEL_ID,
        "base_commit": base_commit,
        "contract_sha256": hashlib.sha256(canonical_json_bytes(contract)).hexdigest(),
        "public_request_sha256": hashlib.sha256(public_request.encode()).hexdigest(),
        "decision_count": len(decisions),
        "material_decision_count": sum(item["material"] for item in materiality["reviews"]),
        "materiality_rubric_sha256": DECISION_MATERIALITY_RUBRIC_SHA256,
        "materiality_schema_version": DECISION_MATERIALITY_SCHEMA_VERSION,
        "materiality_reviewer_model": MODEL_ID,
        "materiality_reviewer_reasoning_effort": MODEL_REASONING_EFFORT,
        "decision_review_sha256": _sha(output_dir / "decision-materiality.json"),
        "fresh_context": True,
        "sealed_inputs_exposed": False,
        "artifact_sha256": {name: _sha(output_dir / name) for name in artifacts},
    }
    _write_json(output_dir / "implementation-manifest.json", manifest)
    return manifest


def completed_implementation_matches(
    output_dir: Path, *, base_commit: str, public_request: str,
    contract: Mapping[str, Any],
) -> bool:
    manifest_path = output_dir / "implementation-manifest.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema": "FreshImplementationRun.v1",
        "model": MODEL_ID,
        "base_commit": base_commit,
        "contract_sha256": hashlib.sha256(canonical_json_bytes(contract)).hexdigest(),
        "public_request_sha256": hashlib.sha256(public_request.encode()).hexdigest(),
        "fresh_context": True,
        "sealed_inputs_exposed": False,
        "materiality_rubric_sha256": DECISION_MATERIALITY_RUBRIC_SHA256,
        "materiality_schema_version": DECISION_MATERIALITY_SCHEMA_VERSION,
        "materiality_reviewer_model": MODEL_ID,
        "materiality_reviewer_reasoning_effort": MODEL_REASONING_EFFORT,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError(f"completed implementation identity drifted: {output_dir}")
    decisions = read_decisions(output_dir / "decision.jsonl")
    if manifest.get("decision_count") != len(decisions):
        raise ValueError(f"completed implementation decision count drifted: {output_dir}")
    materiality = json.loads((output_dir / "decision-materiality.json").read_text(encoding="utf-8"))
    validate_decision_materiality(materiality, decision_count=len(decisions))
    if manifest.get("material_decision_count") != sum(
        item["material"] for item in materiality["reviews"]
    ):
        raise ValueError(f"completed implementation material decision count drifted: {output_dir}")
    if manifest.get("decision_review_sha256") != _sha(
        output_dir / "decision-materiality.json"
    ):
        raise ValueError(f"completed implementation decision review drifted: {output_dir}")
    for name, digest in manifest.get("artifact_sha256", {}).items():
        path = output_dir / name
        if not path.is_file() or _sha(path) != digest:
            raise ValueError(f"completed implementation artifact drifted: {path}")
    return True
