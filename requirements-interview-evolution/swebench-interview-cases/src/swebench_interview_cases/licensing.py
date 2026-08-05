"""Conservative redistribution policy for upstream-derived material."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def repository_license_evidence(repository: str, base_commit: str, repo_root: Path) -> dict[str, Any]:
    candidates = sorted({
        path for pattern in ("LICENSE*", "COPYING*", "NOTICE*")
        for path in repo_root.glob(pattern) if path.is_file()
    })
    return {
        "repository": repository, "base_commit": base_commit,
        "license_files": [
            {"path": str(path.relative_to(repo_root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in candidates
        ],
        "license_interpretation": "not_performed",
        "raw_redistribution": "forbidden",
        "storage_policy": "raw upstream content remains only in the gitignored cache",
    }


def pilot_license_policy(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "SWEbenchPilotLicensePolicy.v1",
        "dataset_license_declaration": "not present in pinned SWE-bench Verified dataset card",
        "harness_license": "MIT",
        "legal_conclusion": "none; this is an engineering redistribution safeguard, not legal advice",
        "raw_dataset_and_repository_redistribution": "forbidden",
        "committed_material": "identifiers, digests, bounded excerpts, derived cases, manifests, and reports only",
        "repositories": entries,
    }
