"""Freeze an unexposed validation extension without consulting holdout outcomes."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping

from . import DATASET_ID, DATASET_PARQUET_SHA256, DATASET_REVISION
from .cache import ContentAddressedCache
from .importer import import_row
from .pilot import candidate_from_row
from .schemas import artifact_digest
from .selection import RankedCandidate, candidate_order


FRESH_VALIDATION_COUNT = 3


def prepare_fresh_validation(
    rows: Iterable[Mapping[str, Any]],
    *,
    exposed_instance_ids: set[str],
    cache: ContentAddressedCache,
    forbidden_repository_families: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze three validation slots and every same-stratum replacement.

    Selection happens before any harness or model outcome is available.  Callers
    should pass every previously selected or attempted ID as exposed, and the
    development/holdout families as forbidden to retain partition isolation.
    """

    forbidden = forbidden_repository_families or set()
    materialized = [
        dict(row)
        for row in rows
        if str(row["instance_id"]) not in exposed_instance_ids
        and str(row["repo"]) not in forbidden
    ]
    ranked = candidate_order(
        [candidate_from_row(row) for row in materialized], DATASET_PARQUET_SHA256
    )
    by_stratum: dict[tuple[str, str, str], list[RankedCandidate]] = defaultdict(list)
    for item in ranked:
        by_stratum[item.stratum].append(item)

    # A slot without a replacement is not eligible.  The digest ordering is
    # independent of input row order and is sealed before downstream outcomes.
    eligible = [members for members in by_stratum.values() if len(members) >= 2]
    eligible.sort(
        key=lambda members: hashlib.sha256(
            json.dumps(members[0].stratum, separators=(",", ":")).encode()
        ).digest()
    )
    selected: list[list[RankedCandidate]] = []
    selected_families: set[str] = set()
    for members in eligible:
        family = members[0].candidate.repository_family
        if family in selected_families:
            continue
        selected.append(members)
        selected_families.add(family)
        if len(selected) == FRESH_VALIDATION_COUNT:
            break
    if len(selected) != FRESH_VALIDATION_COUNT:
        raise ValueError("cannot freeze three replacement-capable validation strata")

    by_id = {str(row["instance_id"]): row for row in materialized}
    public_cases: list[dict[str, Any]] = []
    sealed_cases: list[dict[str, Any]] = []
    for members in selected:
        primary = members[0]
        candidate = primary.candidate
        imported = import_row(
            by_id[candidate.instance_id], dataset_revision=DATASET_REVISION, cache=cache
        )
        common = {
            "partition": "validation",
            "alias": candidate.instance_id,
            "repository_family": candidate.repository_family,
            "difficulty": candidate.difficulty,
            "size_bucket": primary.size_bucket,
            "stratum_rank": primary.rank,
        }
        public_cases.append({**common, "instance_id": candidate.instance_id})
        sealed_cases.append(
            {
                **common,
                "instance_id": candidate.instance_id,
                "public_source": imported.public_source_descriptor(),
                "sealed_inputs": imported.sealed_inputs(),
                "replacement_instance_ids": [
                    item.candidate.instance_id for item in members[1:]
                ],
            }
        )

    public = {
        "schema": "SWEbenchFreshValidationSelection.v1",
        "dataset": {
            "id": DATASET_ID,
            "revision": DATASET_REVISION,
            "parquet_sha256": DATASET_PARQUET_SHA256,
        },
        "quota": FRESH_VALIDATION_COUNT,
        "exposed_instance_ids_sha256": artifact_digest(sorted(exposed_instance_ids)),
        "cases": public_cases,
    }
    sealed = {
        "schema": "SWEbenchFreshValidationSelectionSealed.v1",
        "public_selection_digest": artifact_digest(public),
        "cases": sealed_cases,
    }
    return public, sealed


def splice_fresh_validation(
    *,
    pilot_public: dict[str, Any],
    pilot_sealed: dict[str, Any],
    fresh_public: dict[str, Any],
    fresh_sealed: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replace only validation slots in a frozen 8/3/4 pilot selection."""

    if fresh_sealed.get("public_selection_digest") != artifact_digest(fresh_public):
        raise ValueError("fresh validation public/sealed selection drifted")
    fresh_cases = fresh_sealed.get("cases", [])
    if len(fresh_cases) != FRESH_VALIDATION_COUNT or any(
        item.get("partition") != "validation" for item in fresh_cases
    ):
        raise ValueError("fresh selection must contain exactly three validation cases")
    public = deepcopy(pilot_public)
    sealed = deepcopy(pilot_sealed)
    def replace_in_place(cases: list[dict[str, Any]], replacements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pending = iter(deepcopy(replacements))
        return [next(pending) if item["partition"] == "validation" else item for item in cases]

    public["cases"] = replace_in_place(public["cases"], fresh_public["cases"])
    sealed["cases"] = replace_in_place(sealed["cases"], fresh_cases)
    counts = {
        name: sum(item["partition"] == name for item in sealed["cases"])
        for name in ("development", "validation", "holdout")
    }
    if counts != {"development": 8, "validation": 3, "holdout": 4}:
        raise ValueError(f"spliced pilot does not satisfy 8/3/4 quotas: {counts}")
    sealed["public_selection_digest"] = artifact_digest(public)
    return public, sealed


def copy_corpus_without_old_validation(source: Path, destination: Path) -> None:
    """Copy a corpus for rebuilding while removing only prior validation cases."""

    if destination.exists():
        raise FileExistsError(destination)
    validation_index = json.loads(
        (source / "validation" / "index.json").read_text(encoding="utf-8")
    )
    aliases = [str(item["alias"]) for item in validation_index["cases"]]
    shutil.copytree(source, destination)
    for alias in aliases:
        case_dir = destination / "cases" / alias
        if case_dir.exists():
            shutil.rmtree(case_dir)
    (destination / "validation" / "index.json").unlink()
    for generated in ("pilot-manifest.json", "completion-verification.json"):
        path = destination / generated
        if path.exists():
            path.unlink()
