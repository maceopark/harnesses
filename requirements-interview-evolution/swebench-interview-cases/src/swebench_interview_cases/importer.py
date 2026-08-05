"""Import frozen SWE-bench rows into cache-backed source descriptors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .cache import CachedObject, ContentAddressedCache, sha256_bytes
from .schemas import artifact_digest


class ImportError(ValueError):
    """Raised when an upstream row is incomplete or not immutably identified."""


@dataclass(frozen=True)
class ImportedInstance:
    instance_id: str
    alias: str
    repository: str
    base_commit: str
    dataset_revision: str
    source_url: str
    objects: Mapping[str, CachedObject]

    def public_source_descriptor(self) -> dict[str, Any]:
        issue = self.objects["issue"]
        return {
            "dataset": "princeton-nlp/SWE-bench_Verified",
            "revision": self.dataset_revision,
            "instance_id_digest": sha256_bytes(self.instance_id.encode("utf-8")),
            "base_commit": self.base_commit,
            "source_url": self.source_url,
            "issue_digest": issue.sha256,
            "issue_cache_key": issue.key,
        }

    def sealed_inputs(self) -> dict[str, dict[str, str]]:
        return {
            name: {"cache_key": value.key, "digest": value.sha256}
            for name, value in self.objects.items()
        }


REQUIRED_COLUMNS = frozenset(
    {
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
        "patch",
        "test_patch",
        "FAIL_TO_PASS",
        "PASS_TO_PASS",
    }
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ImportError(f"{field} must be a string")
    return value


def _canonical_test_list(value: Any, field: str) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ImportError(f"{field} must be a JSON array or list") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ImportError(f"{field} must contain only test identifiers")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def source_url_for(instance_id: str, repository: str) -> str:
    # The official ID suffix is the solution pull-request number. The dataset does
    # not expose a separate issue URL, so preserve only the verifiable PR locator.
    prefix = repository.replace("/", "__") + "-"
    if not instance_id.startswith(prefix):
        raise ImportError("instance_id does not match repository")
    issue_number = instance_id[len(prefix) :]
    if not issue_number.isdigit():
        raise ImportError("instance_id has no numeric pull-request suffix")
    return f"https://github.com/{repository}/pull/{issue_number}"


def import_row(
    row: Mapping[str, Any], *, dataset_revision: str, cache: ContentAddressedCache
) -> ImportedInstance:
    if not dataset_revision or dataset_revision in {"main", "latest", "HEAD"}:
        raise ImportError("dataset_revision must identify an immutable revision")
    missing = REQUIRED_COLUMNS - set(row)
    if missing:
        raise ImportError(f"SWE-bench row is missing fields: {sorted(missing)}")
    instance_id = _text(row["instance_id"], "instance_id")
    repository = _text(row["repo"], "repo")
    base_commit = _text(row["base_commit"], "base_commit")
    if len(base_commit) < 7:
        raise ImportError("base_commit is not a plausible git object ID")
    issue = _text(row["problem_statement"], "problem_statement")
    payloads = {
        "issue": issue,
        "gold_patch": _text(row["patch"], "patch"),
        "test_patch": _text(row["test_patch"], "test_patch"),
        "fail_to_pass": _canonical_test_list(row["FAIL_TO_PASS"], "FAIL_TO_PASS"),
        "pass_to_pass": _canonical_test_list(row["PASS_TO_PASS"], "PASS_TO_PASS"),
    }
    objects = {name: cache.put_text(content) for name, content in payloads.items()}
    return ImportedInstance(
        instance_id=instance_id,
        alias=artifact_digest({"instance_id": instance_id, "revision": dataset_revision}),
        repository=repository,
        base_commit=base_commit,
        dataset_revision=dataset_revision,
        source_url=source_url_for(instance_id, repository),
        objects=objects,
    )


def import_rows(
    rows: Iterable[Mapping[str, Any]], *, dataset_revision: str, cache: ContentAddressedCache
) -> list[ImportedInstance]:
    seen: set[str] = set()
    imported: list[ImportedInstance] = []
    for row in rows:
        item = import_row(row, dataset_revision=dataset_revision, cache=cache)
        if item.instance_id in seen:
            raise ImportError(f"duplicate instance_id: {item.instance_id}")
        seen.add(item.instance_id)
        imported.append(item)
    return imported
