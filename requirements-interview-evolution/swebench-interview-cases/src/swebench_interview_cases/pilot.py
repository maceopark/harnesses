"""Reproducible preparation of the frozen 15-instance pilot."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from datasets import Dataset

from . import DATASET_ID, DATASET_PARQUET_SHA256, DATASET_REVISION
from .cache import ContentAddressedCache
from .importer import ImportedInstance, import_row, import_rows
from .schemas import artifact_digest
from .selection import Candidate, Selection, candidate_order, holdout_alias, stratified_select


def changed_lines(diff: str) -> int:
    return sum(
        1
        for line in diff.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


def candidate_from_row(row: Mapping[str, Any]) -> Candidate:
    return Candidate(
        instance_id=str(row["instance_id"]),
        repository_family=str(row["repo"]),
        difficulty=str(row["difficulty"]),
        patch_lines=changed_lines(str(row["patch"])),
        test_lines=changed_lines(str(row["test_patch"])),
    )


def _replacement_map(
    candidates: list[Candidate], selections: list[Selection]
) -> dict[str, list[str]]:
    selected_ids = {item.ranked.candidate.instance_id for item in selections}
    ranked = candidate_order(candidates, DATASET_PARQUET_SHA256)
    by_stratum: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for item in ranked:
        by_stratum[item.stratum].append(item)
    result: dict[str, list[str]] = {}
    for selection in selections:
        current = selection.ranked
        members = by_stratum[current.stratum]
        current_index = next(
            index for index, item in enumerate(members)
            if item.candidate.instance_id == current.candidate.instance_id
        )
        # Continue after the selected candidate and wrap once so every unused
        # candidate in the frozen stratum remains available before exhaustion.
        continuation = members[current_index + 1 :] + members[:current_index]
        result[current.candidate.instance_id] = [
            item.candidate.instance_id
            for item in continuation
            if item.candidate.instance_id not in selected_ids
        ]
    return result


def prepare_pilot(parquet_path: Path, cache: ContentAddressedCache) -> tuple[dict[str, Any], dict[str, Any]]:
    if artifact_digest_bytes(parquet_path) != DATASET_PARQUET_SHA256:
        raise ValueError("pilot parquet digest does not match the Build Contract")
    rows = [dict(row) for row in Dataset.from_parquet(str(parquet_path))]
    imported = import_rows(rows, dataset_revision=DATASET_REVISION, cache=cache)
    imported_by_id: dict[str, ImportedInstance] = {item.instance_id: item for item in imported}
    candidates = [candidate_from_row(row) for row in rows]
    selections = stratified_select(candidates, DATASET_PARQUET_SHA256)
    replacements = _replacement_map(candidates, selections)
    public_cases = []
    sealed_cases = []
    for selection in selections:
        candidate = selection.ranked.candidate
        imported_case = imported_by_id[candidate.instance_id]
        common = {
            "partition": selection.partition,
            "alias": selection.alias,
            "repository_family": candidate.repository_family,
            "difficulty": candidate.difficulty,
            "size_bucket": selection.ranked.size_bucket,
            "stratum_rank": selection.ranked.rank,
        }
        public_cases.append(
            {
                **common,
                "repository_family": None if selection.partition == "holdout" else candidate.repository_family,
                "instance_id": None if selection.partition == "holdout" else candidate.instance_id,
            }
        )
        sealed_cases.append(
            {
                **common,
                "instance_id": candidate.instance_id,
                "public_source": imported_case.public_source_descriptor(),
                "sealed_inputs": imported_case.sealed_inputs(),
                "replacement_instance_ids": replacements[candidate.instance_id],
            }
        )
    public = {
        "schema": "SWEbenchPilotSelection.v1",
        "dataset": {"id": DATASET_ID, "revision": DATASET_REVISION, "parquet_sha256": DATASET_PARQUET_SHA256},
        "quotas": {"development": 8, "validation": 3, "holdout": 4},
        "minimum_repository_families": 6,
        "actual_repository_families": len({item.ranked.candidate.repository_family for item in selections}),
        "cases": public_cases,
    }
    sealed = {
        "schema": "SWEbenchPilotSelectionSealed.v1",
        "public_selection_digest": artifact_digest(public),
        "cases": sealed_cases,
    }
    return public, sealed


def reseed_exhausted_slot(
    *, public: dict[str, Any], sealed: dict[str, Any], rows: list[dict[str, Any]],
    slot_number: int, excluded_instance_ids: set[str], cache: ContentAddressedCache,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deterministically freeze a new stratum after the prior one is exhausted.

    This is not a cross-stratum replacement. The exhausted slot is discarded and
    re-frozen from an unused stratum whose repository family is already confined
    to the same partition. Every later replacement remains inside that new
    stratum. At least two unused members are required so the amended slot retains
    a deterministic replacement path.
    """
    index = slot_number - 1
    if index < 0 or index >= len(sealed["cases"]):
        raise ValueError("slot_number is outside the frozen pilot")
    partition = sealed["cases"][index]["partition"]
    family_partitions = {
        item["repository_family"]: item["partition"] for item in sealed["cases"]
    }
    reserved = {
        instance_id
        for item in sealed["cases"]
        for instance_id in [item["instance_id"], *item["replacement_instance_ids"]]
    }
    ranked = candidate_order([candidate_from_row(row) for row in rows], DATASET_PARQUET_SHA256)
    groups: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for item in ranked:
        candidate = item.candidate
        if (
            family_partitions.get(candidate.repository_family) == partition
            and candidate.instance_id not in reserved
            and candidate.instance_id not in excluded_instance_ids
        ):
            groups[item.stratum].append(item)
    eligible = [members for members in groups.values() if len(members) >= 2]
    if not eligible:
        raise ValueError("no deterministic replacement-capable stratum remains in partition")
    members = eligible[0]
    selected = members[0]
    candidate = selected.candidate
    row = next(row for row in rows if str(row["instance_id"]) == candidate.instance_id)
    imported = import_row(row, dataset_revision=DATASET_REVISION, cache=cache)
    alias = holdout_alias(candidate.instance_id) if partition == "holdout" else candidate.instance_id
    common = {
        "partition": partition,
        "alias": alias,
        "repository_family": candidate.repository_family,
        "difficulty": candidate.difficulty,
        "size_bucket": selected.size_bucket,
        "stratum_rank": selected.rank,
    }
    public["cases"][index] = {
        **common,
        "repository_family": None if partition == "holdout" else candidate.repository_family,
        "instance_id": None if partition == "holdout" else candidate.instance_id,
    }
    sealed["cases"][index] = {
        **common,
        "instance_id": candidate.instance_id,
        "public_source": imported.public_source_descriptor(),
        "sealed_inputs": imported.sealed_inputs(),
        "replacement_instance_ids": [item.candidate.instance_id for item in members[1:]],
        "reseeded_after_exhaustion": {
            "excluded_instance_ids": sorted(excluded_instance_ids),
            "policy": "new-stratum-within-bound-partition",
        },
    }
    sealed["public_selection_digest"] = artifact_digest(public)
    return public, sealed


def artifact_digest_bytes(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
