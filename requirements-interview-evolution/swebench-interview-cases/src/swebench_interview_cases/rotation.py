"""Auditable repartitioning of an already approved non-holdout pilot corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .schemas import artifact_digest, validate_no_cross_partition_family_overlap


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def rotate_non_holdout_partitions(
    *, corpus_root: Path, sealed_approved: Path, assignments: Mapping[str, str],
) -> dict[str, Any]:
    """Apply a predeclared 8/3 non-holdout rotation and refresh every binding."""

    approved = _read(sealed_approved)
    cases = approved["cases"]
    non_holdout = {item["alias"] for item in cases if item["partition"] != "holdout"}
    if set(assignments) != non_holdout:
        raise ValueError("rotation must assign every and only non-holdout alias")
    if any(value not in {"development", "validation"} for value in assignments.values()):
        raise ValueError("rotation assignments must be development or validation")
    counts = {
        name: sum(value == name for value in assignments.values())
        for name in ("development", "validation")
    }
    if counts != {"development": 8, "validation": 3}:
        raise ValueError("rotation must preserve the 8/3 non-holdout quotas")

    case_digests: dict[str, str] = {}
    families: dict[str, str] = {}
    for alias, partition in assignments.items():
        case_dir = corpus_root / "cases" / alias
        public = _read(case_dir / "case.json")
        public["metadata"]["partition"] = partition
        _write(case_dir / "case.json", public)
        digest = artifact_digest(public)
        case_digests[alias] = digest
        families[alias] = public["metadata"]["repository_family"]
        preparation = _read(case_dir / "run-manifest.json")
        preparation["partition"] = partition
        preparation["case_sha256"] = digest
        _write(case_dir / "run-manifest.json", preparation)

    for item in cases:
        alias = item["alias"]
        if alias in assignments:
            item["partition"] = assignments[alias]
            item["case_digest"] = case_digests[alias]

    pilot = _read(corpus_root / "pilot-manifest.json")
    for entry in pilot["registry"]["entries"]:
        alias = entry["id"]
        if alias in assignments:
            entry["partition"] = assignments[alias]
            entry["case_digest"] = case_digests[alias]
    registry_body = {key: value for key, value in pilot["registry"].items() if key != "registry_digest"}
    pilot["registry"]["registry_digest"] = hashlib.sha256(
        json.dumps(registry_body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    _write(corpus_root / "pilot-manifest.json", pilot)
    approved["public_manifest_sha256"] = artifact_digest(pilot)
    _write(sealed_approved, approved)

    indexes = []
    for partition in ("development", "validation", "holdout"):
        selected = [item for item in cases if item["partition"] == partition]
        index = {
            "schema": "SWEbenchPartitionIndex.v1", "partition": partition,
            "cases": [{
                "alias": item["alias"],
                "repository_family": item["repository_family"],
                "case_digest": item["case_digest"], "status": "approved",
            } for item in sorted(selected, key=lambda value: value["alias"])],
        }
        _write(corpus_root / partition / "index.json", index)
        indexes.append(index)
    validate_no_cross_partition_family_overlap(indexes)
    return {
        "schema": "SWEbenchPartitionRotation.v1", "assignments": dict(assignments),
        "counts": {"development": 8, "validation": 3, "holdout": 4},
        "holdout_unchanged": True,
    }
