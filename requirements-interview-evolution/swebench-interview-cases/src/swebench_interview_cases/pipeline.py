"""End-to-end approval pipeline for the frozen pilot corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cache import ContentAddressedCache
from .casegen import derive_and_review_case
from .harness import HarnessError, OfficialHarness, docker_fingerprint, sha256_file
from .importer import import_row
from .registry import PartitionRegistry, RegistryEntry
from .schemas import artifact_digest, validate_case_pair, validate_partition_index
from .selection import holdout_alias
from .repository import prepare_checkout
from .licensing import pilot_license_policy, repository_license_evidence


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_approved_corpus(
    *, harness: OfficialHarness, rows: list[dict[str, Any]], sealed_selection: dict[str, Any],
    cache: ContentAddressedCache, corpus_root: Path, record_root: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Fill all quotas; harness or review failures advance within the same stratum."""

    by_id = {str(row["instance_id"]): row for row in rows}
    registry = PartitionRegistry()
    exclusions: list[dict[str, Any]] = []
    approved_records: list[dict[str, Any]] = []
    license_entries: dict[tuple[str, str], dict[str, Any]] = {}
    used: set[str] = set()
    for slot_number, original in enumerate(sealed_selection["cases"], 1):
        accepted = False
        candidates = [original["instance_id"], *original["replacement_instance_ids"]]

        # A prior run may have approved a replacement after rejecting the
        # original candidate. Resume that completed slot before retrying any
        # earlier candidates; otherwise every restart repeats expensive Docker
        # evaluations that are already known to fail.
        def has_approved_artifacts(instance_id: str) -> bool:
            alias = holdout_alias(instance_id) if original["partition"] == "holdout" else instance_id
            case_dir = (
                record_root / "holdout-cases" / alias
                if original["partition"] == "holdout"
                else corpus_root / "cases" / alias
            )
            return (case_dir / "run-manifest.json").is_file()

        candidates.sort(key=lambda instance_id: not has_approved_artifacts(instance_id))
        for instance_id in candidates:
            if instance_id in used:
                continue
            row = by_id.get(instance_id)
            if row is None:
                raise ValueError(f"replacement row missing: {instance_id}")
            alias = holdout_alias(instance_id) if original["partition"] == "holdout" else instance_id
            case_dir = (
                record_root / "holdout-cases" / alias
                if original["partition"] == "holdout"
                else corpus_root / "cases" / alias
            )
            existing_manifest = case_dir / "run-manifest.json"
            if existing_manifest.is_file():
                public = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
                sealed = json.loads((case_dir / "sealed-source.json").read_text(encoding="utf-8"))
                audit = json.loads((case_dir / "audit.json").read_text(encoding="utf-8"))
                prep_manifest = json.loads(existing_manifest.read_text(encoding="utf-8"))
                validate_case_pair(public, sealed)
                if (
                    not audit.get("approved")
                    or prep_manifest.get("slot") != slot_number
                    or prep_manifest.get("partition") != original["partition"]
                    or prep_manifest.get("case_sha256") != artifact_digest(public)
                    or prep_manifest.get("sealed_source_sha256") != artifact_digest(sealed)
                ):
                    raise ValueError(f"existing approved case is invalid or drifted: {alias}")
                harness_evidence = harness.validate_instance(row)
                if prep_manifest.get("harness_evidence_sha256") != artifact_digest(harness_evidence):
                    raise ValueError(f"existing harness evidence drifted: {instance_id}")
                checkout = prepare_checkout(
                    repository=original["repository_family"], base_commit=str(row["base_commit"]),
                    alias=alias, root=repository_root,
                )
                license_entries.setdefault(
                    (original["repository_family"], str(row["base_commit"])),
                    repository_license_evidence(
                        original["repository_family"], str(row["base_commit"]),
                        repository_root / checkout["alias"],
                    ),
                )
                case_digest = artifact_digest(public)
                registry.register(RegistryEntry(instance_id, original["repository_family"], original["partition"], case_digest))
                approved_records.append({
                    "partition": original["partition"], "alias": alias, "instance_id": instance_id,
                    "repository_family": original["repository_family"], "base_commit": row["base_commit"],
                    "case_digest": case_digest,
                    "case_storage": "sealed-cache" if original["partition"] == "holdout" else "committed-corpus",
                })
                used.add(instance_id)
                accepted = True
                break
            attempt_root = record_root / f"slot-{slot_number:02d}" / instance_id
            try:
                harness_evidence = harness.validate_instance(row)
            except HarnessError as exc:
                failed_run = harness.output_root / instance_id.replace("/", "_")
                process_evidence = [
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in sorted(failed_run.glob("*.process.json"))
                ] if failed_run.is_dir() else []
                log_sha256 = {
                    path.name: sha256_file(path) for path in sorted(failed_run.glob("*.log"))
                } if failed_run.is_dir() else {}
                attempt_path = failed_run / "attempt.json"
                exclusions.append({
                    "slot": slot_number, "instance_id": instance_id,
                    "repository_family": original["repository_family"],
                    "stratum": [original["repository_family"], original["difficulty"], original["size_bucket"]],
                    "stage": "official-harness", "reason": str(exc),
                    "environment": docker_fingerprint(harness.output_root),
                    "attempt": json.loads(attempt_path.read_text(encoding="utf-8")) if attempt_path.is_file() else None,
                    "processes": process_evidence, "log_sha256": log_sha256,
                })
                continue
            imported = import_row(row, dataset_revision=original["public_source"]["revision"], cache=cache)
            slot = {
                **original, "instance_id": instance_id, "alias": alias,
                "public_source": imported.public_source_descriptor(), "sealed_inputs": imported.sealed_inputs(),
            }
            checkout = prepare_checkout(
                repository=original["repository_family"], base_commit=str(row["base_commit"]),
                alias=alias, root=repository_root,
            )
            license_entries.setdefault(
                (original["repository_family"], str(row["base_commit"])),
                repository_license_evidence(
                    original["repository_family"], str(row["base_commit"]),
                    repository_root / checkout["alias"],
                ),
            )
            try:
                public, sealed, review_a, review_b, audit = derive_and_review_case(
                    slot=slot, cache=cache, record_root=attempt_root,
                    repo_root=repository_root / checkout["alias"],
                )
            except ValueError as exc:
                exclusions.append({
                    "slot": slot_number, "instance_id": instance_id,
                    "stage": "independent-review", "reason": str(exc),
                })
                continue
            if not audit["approved"]:
                exclusions.append({"slot": slot_number, "instance_id": instance_id, "stage": "independent-review", "reason": "human_review_required", "review_a_sha256": artifact_digest(review_a), "review_b_sha256": artifact_digest(review_b)})
                continue
            validate_case_pair(public, sealed)
            case_digest = artifact_digest(public)
            registry.register(RegistryEntry(instance_id, original["repository_family"], original["partition"], case_digest))
            _write(case_dir / "case.json", public)
            _write(case_dir / "sealed-source.json", sealed)
            _write(case_dir / "review-a.json", review_a)
            _write(case_dir / "review-b.json", review_b)
            _write(case_dir / "audit.json", audit)
            prep_manifest = {
                "schema": "SWEbenchApprovedCasePreparation.v1", "slot": slot_number,
                "partition": original["partition"], "case_sha256": case_digest,
                "sealed_source_sha256": artifact_digest(sealed),
                "harness_evidence_sha256": artifact_digest(harness_evidence),
                "model": "gpt-5.6-sol", "reviewers": 2,
            }
            _write(case_dir / "run-manifest.json", prep_manifest)
            approved_records.append({
                "partition": original["partition"], "alias": alias, "instance_id": instance_id,
                "repository_family": original["repository_family"], "base_commit": row["base_commit"],
                "case_digest": case_digest,
                "case_storage": "sealed-cache" if original["partition"] == "holdout" else "committed-corpus",
            })
            used.add(instance_id)
            accepted = True
            break
        if not accepted:
            raise RuntimeError(f"same-stratum candidate pool exhausted at slot {slot_number}")
    registry.validate_complete(minimum_repository_families=6)
    indexes = []
    for partition in ("development", "validation", "holdout"):
        cases = []
        for item in approved_records:
            if item["partition"] != partition:
                continue
            cases.append({
                "alias": item["alias"],
                "repository_family": item["repository_family"] if partition != "holdout" else f"holdout-{item['alias'][:12]}",
                "case_digest": item["case_digest"], "status": "approved",
            })
        index = {"schema": "SWEbenchPartitionIndex.v1", "partition": partition, "cases": cases}
        validate_partition_index(index)
        _write(corpus_root / partition / "index.json", index)
        indexes.append(index)
    manifest = {
        "schema": "SWEbenchApprovedPilot.v1", "approved_total": len(approved_records),
        "counts": {name: sum(item["partition"] == name for item in approved_records) for name in ("development", "validation", "holdout")},
        "repository_families": len({item["repository_family"] for item in approved_records}),
        "registry": registry.manifest(), "exclusions": exclusions,
    }
    _write(record_root / "approved-pilot-sealed.json", {
        "schema": "SWEbenchApprovedPilotSealed.v1", "cases": approved_records,
        "public_manifest_sha256": artifact_digest(manifest),
    })
    _write(corpus_root / "pilot-manifest.json", manifest)
    _write(corpus_root / "license-policy.json", pilot_license_policy(list(license_entries.values())))
    return manifest
