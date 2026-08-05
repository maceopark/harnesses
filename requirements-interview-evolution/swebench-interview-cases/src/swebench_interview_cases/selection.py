"""Deterministic, stratified selection for the SWE-bench interview pilot."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import random
from typing import Iterable, Mapping, Sequence


PARTITION_QUOTAS: Mapping[str, int] = {
    "development": 8,
    "validation": 3,
    "holdout": 4,
}


class SelectionError(ValueError):
    """Raised when a deterministic selection cannot satisfy its contract."""


@dataclass(frozen=True, slots=True)
class Candidate:
    instance_id: str
    repository_family: str
    difficulty: str
    patch_lines: int
    test_lines: int

    @property
    def change_size(self) -> int:
        return self.patch_lines + self.test_lines


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: Candidate
    size_bucket: str
    stratum: tuple[str, str, str]
    rank: int


@dataclass(frozen=True, slots=True)
class Selection:
    partition: str
    ranked: RankedCandidate
    alias: str


def derive_seed(dataset_revision_digest: str) -> int:
    """Derive a stable PRNG seed from an immutable SHA-256 revision digest."""
    digest = dataset_revision_digest.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise SelectionError("dataset revision digest must be a SHA-256 hex digest")
    return int.from_bytes(hashlib.sha256(bytes.fromhex(digest)).digest()[:16], "big")


def holdout_alias(instance_id: str) -> str:
    """Return enumeration-vulnerable pseudonymization, not confidentiality."""
    return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()


def holdout_alias_metadata() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "classification": "pseudonymization",
        "confidential": False,
        "enumeration_resistant": False,
        "warning": "The 500 known SWE-bench instance IDs can be enumerated.",
    }


def _quantile_boundaries(values: Sequence[int]) -> tuple[int, int]:
    if not values:
        raise SelectionError("at least one candidate is required")
    ordered = sorted(values)

    def nearest_rank(q: float) -> int:
        return ordered[max(0, math.ceil(q * len(ordered)) - 1)]

    return nearest_rank(1 / 3), nearest_rank(2 / 3)


def size_buckets(candidates: Sequence[Candidate]) -> dict[str, str]:
    low, high = _quantile_boundaries([item.change_size for item in candidates])
    buckets: dict[str, str] = {}
    for item in candidates:
        if item.change_size <= low:
            bucket = "small"
        elif item.change_size <= high:
            bucket = "medium"
        else:
            bucket = "large"
        buckets[item.instance_id] = bucket
    return buckets


def candidate_order(
    candidates: Iterable[Candidate], dataset_revision_digest: str
) -> list[RankedCandidate]:
    """Produce the stable initial and replacement order within each stratum."""
    materialized = list(candidates)
    ids = [item.instance_id for item in materialized]
    if len(ids) != len(set(ids)):
        raise SelectionError("candidate instance IDs must be unique")
    if any(not item.repository_family.strip() for item in materialized):
        raise SelectionError("repository family must be resolved before selection")
    buckets = size_buckets(materialized)
    groups: dict[tuple[str, str, str], list[Candidate]] = defaultdict(list)
    for item in materialized:
        stratum = (item.repository_family, item.difficulty, buckets[item.instance_id])
        groups[stratum].append(item)

    master_seed = derive_seed(dataset_revision_digest)
    result: list[RankedCandidate] = []
    for stratum in sorted(groups):
        encoded = json.dumps(stratum, ensure_ascii=False, separators=(",", ":"))
        local_seed = int.from_bytes(
            hashlib.sha256(f"{master_seed}:{encoded}".encode()).digest()[:16], "big"
        )
        ordered = sorted(groups[stratum], key=lambda item: item.instance_id)
        random.Random(local_seed).shuffle(ordered)
        result.extend(
            RankedCandidate(item, buckets[item.instance_id], stratum, rank)
            for rank, item in enumerate(ordered)
        )
    return result


def stratified_select(
    candidates: Iterable[Candidate],
    dataset_revision_digest: str,
    quotas: Mapping[str, int] = PARTITION_QUOTAS,
) -> list[Selection]:
    """Assign families to one partition and fill quotas in deterministic rounds.

    A canonical repository family is indivisible: once the first candidate from a
    family is assigned, all later candidates from that family can only be used as
    replacements in that same partition.
    """
    if any(value < 0 for value in quotas.values()):
        raise SelectionError("partition quotas cannot be negative")
    ranked = candidate_order(candidates, dataset_revision_digest)
    by_family: dict[str, list[RankedCandidate]] = defaultdict(list)
    for item in ranked:
        by_family[item.candidate.repository_family].append(item)
    master_seed = derive_seed(dataset_revision_digest)
    for family, family_candidates in by_family.items():
        by_secondary_stratum: dict[tuple[str, str], list[RankedCandidate]] = defaultdict(list)
        for item in family_candidates:
            by_secondary_stratum[(item.candidate.difficulty, item.size_bucket)].append(item)
        strata = sorted(
            by_secondary_stratum,
            key=lambda stratum: hashlib.sha256(
                f"{master_seed}:{family}:{stratum}".encode()
            ).digest(),
        )
        interleaved: list[RankedCandidate] = []
        offset = 0
        while True:
            appended = False
            for stratum in strata:
                members = by_secondary_stratum[stratum]
                if offset < len(members):
                    interleaved.append(members[offset])
                    appended = True
            if not appended:
                break
            offset += 1
        by_family[family] = interleaved
    family_order = sorted(
        by_family,
        key=lambda family: hashlib.sha256(
            f"{master_seed}:{family}".encode()
        ).digest(),
    )

    remaining = dict(quotas)
    assignments: list[Selection] = []
    family_partition: dict[str, str] = {}
    next_offset: dict[str, int] = {}

    # Diversity pass: take one deterministically randomized candidate per family
    # before taking a second from any family. This makes repository family a real
    # stratum instead of allowing the first large family to consume a partition.
    for family in family_order:
        eligible = [name for name, count in remaining.items() if count > 0]
        if not eligible:
            break
        partition = max(eligible, key=lambda name: (remaining[name], name))
        item = by_family[family][0]
        alias = (
            holdout_alias(item.candidate.instance_id)
            if partition == "holdout"
            else item.candidate.instance_id
        )
        assignments.append(Selection(partition, item, alias))
        family_partition[family] = partition
        next_offset[family] = 1
        remaining[partition] -= 1

    # Capacity pass: fill any remaining quota only from families already bound to
    # that partition. The per-family list retains deterministic stratum/rank order
    # and therefore also defines the replacement sequence.
    while any(remaining.values()):
        progressed = False
        for family in family_order:
            partition = family_partition.get(family)
            if partition is None or remaining[partition] == 0:
                continue
            offset = next_offset[family]
            if offset >= len(by_family[family]):
                continue
            item = by_family[family][offset]
            alias = (
                holdout_alias(item.candidate.instance_id)
                if partition == "holdout"
                else item.candidate.instance_id
            )
            assignments.append(Selection(partition, item, alias))
            next_offset[family] += 1
            remaining[partition] -= 1
            progressed = True
        if not progressed:
            break

    if any(remaining.values()):
        raise SelectionError(f"candidate pool cannot fill partition quotas: {remaining}")
    return assignments
