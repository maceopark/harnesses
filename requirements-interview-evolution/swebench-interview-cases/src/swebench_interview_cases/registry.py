"""Fail-closed partition registry for approved interview cases."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping

from .selection import PARTITION_QUOTAS, holdout_alias, holdout_alias_metadata


class RegistryViolation(ValueError):
    """Raised when registration would contaminate a partition."""


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    instance_id: str
    repository_family: str
    partition: str
    case_digest: str
    status: str = "approved"


@dataclass(slots=True)
class PartitionRegistry:
    quotas: Mapping[str, int] = field(default_factory=lambda: dict(PARTITION_QUOTAS))
    _entries: dict[str, RegistryEntry] = field(default_factory=dict, init=False)
    _family_partition: dict[str, str] = field(default_factory=dict, init=False)

    def register(self, entry: RegistryEntry) -> None:
        if entry.partition not in self.quotas:
            raise RegistryViolation(f"unknown partition: {entry.partition}")
        if not entry.repository_family.strip():
            raise RegistryViolation("unresolved repository family is fail-closed")
        if entry.status != "approved":
            raise RegistryViolation("only approved cases may enter the registry")
        _require_sha256(entry.case_digest, "case digest")
        existing = self._entries.get(entry.instance_id)
        if existing is not None and existing != entry:
            raise RegistryViolation("instance already registered with different metadata")
        family_partition = self._family_partition.get(entry.repository_family)
        if family_partition is not None and family_partition != entry.partition:
            raise RegistryViolation(
                f"repository family crosses partitions: {family_partition} -> {entry.partition}"
            )
        current = sum(item.partition == entry.partition for item in self._entries.values())
        if existing is None and current >= self.quotas[entry.partition]:
            raise RegistryViolation(f"partition quota exceeded: {entry.partition}")
        self._entries[entry.instance_id] = entry
        self._family_partition[entry.repository_family] = entry.partition

    def validate_complete(self, minimum_repository_families: int = 6) -> None:
        counts = {name: 0 for name in self.quotas}
        for entry in self._entries.values():
            counts[entry.partition] += 1
        if counts != dict(self.quotas):
            raise RegistryViolation(f"registry is incomplete: {counts}")
        if len(self._family_partition) < minimum_repository_families:
            raise RegistryViolation("registry has too few canonical repository families")

    def manifest(self) -> dict[str, object]:
        entries = []
        for item in sorted(self._entries.values(), key=lambda value: value.instance_id):
            is_holdout = item.partition == "holdout"
            public_id = holdout_alias(item.instance_id) if is_holdout else item.instance_id
            entries.append(
                {
                    "id": public_id,
                    # Isolation is enforced internally, but the public holdout
                    # index must not reveal the repository identity.
                    "repository_family": None if is_holdout else item.repository_family,
                    "partition": item.partition,
                    "case_digest": item.case_digest,
                    "status": item.status,
                }
            )
        body: dict[str, object] = {
            "schema": "SWEbenchPartitionRegistry.v1",
            "holdout_alias": holdout_alias_metadata(),
            "entries": entries,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        body["registry_digest"] = hashlib.sha256(canonical).hexdigest()
        return body


def _require_sha256(value: str, label: str) -> None:
    digest = value.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise RegistryViolation(f"{label} must be a SHA-256 hex digest")
