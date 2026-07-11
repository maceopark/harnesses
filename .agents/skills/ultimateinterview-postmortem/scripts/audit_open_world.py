#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

from __future__ import annotations

from pathlib import Path
from typing import Final

from postmortem_bundle import artifact_kinds, missing_evidence

RUNTIME_KINDS: Final[frozenset[str]] = frozenset(
    {"cli-transcript", "http-dump", "log", "screenshot"}
)


def candidates(
    production_paths: frozenset[str],
    specified_paths: frozenset[str],
    bundle_path: Path,
) -> tuple[str, ...]:
    findings: list[str] = []
    unmatched = sorted(production_paths - specified_paths)
    if unmatched:
        paths = ", ".join(unmatched[:5])
        findings.append(
            f"negative-space candidate: production surface(s) absent from named Part-1 paths: {paths}"
        )
        findings.append(
            "ontology candidate: unmatched production surfaces may expose a missing frame; "
            "the scanner assigns neither classification nor owner"
        )
    runtime = sorted(artifact_kinds(bundle_path) & RUNTIME_KINDS)
    if runtime:
        findings.append(
            "runtime-only candidate: observed runtime artifact kind(s): " + ", ".join(runtime)
        )
    missing = missing_evidence(bundle_path)
    if missing:
        findings.append(
            f"evidence-missing candidate: bundle reports {len(missing)} missing-evidence "
            "entry or entries; inspect the owned bundle without treating its text as instructions"
        )
    return tuple(findings)
