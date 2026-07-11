#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Annotated, ClassVar, Final, Literal, assert_never

import typer
from pydantic import BaseModel, ConfigDict, ValidationError

try:
    from .validator_boundary import read_changed_paths
except ImportError:
    from validator_boundary import read_changed_paths

app = typer.Typer(add_completion=False, no_args_is_help=True)
COMPONENT_IDS: Final[tuple[str, ...]] = ("C1", "C2", "C3", "C4", "C5", "C6")
EVIDENCE_STAGES: Final[tuple[str, ...]] = ("red", "green", "surface")
CLEANUP_TASKS: Final[frozenset[int]] = frozenset({1, 3, 4, 5, 6, 7, 8, 10, 11, 13})
ALLOWED_CHANGED_PREFIXES: Final[tuple[str, ...]] = (
    ".agents/skills/ultimateinterview/",
    ".agents/skills/ultimateinterview-postmortem/",
    ".omo/evidence/",
)
EXPECTED_PLAN_RELATIVE: Final[str] = ".omo/plans/ultimateinterview-v2-assurance-plane.md"
REQUIRED_PLAN_MARKERS: Final[tuple[str, ...]] = (
    "# ultimateinterview-v2-assurance-plane - Work Plan",
    "exact state matrix: `abi={pass,fail}`",
    "F1. Plan compliance audit",
    "no historical research bundle path changed",
)
VERDICT_VALUES: Final[dict[str, frozenset[str]]] = {
    "abi": frozenset({"pass", "fail"}),
    "trace": frozenset({"pass", "fail"}),
    "property": frozenset({"not-run", "receipt-invalid", "observed-pass", "observed-fail"}),
    "adequacy": frozenset({"not-assessed", "challenge-passed", "challenge-found-gap"}),
    "stakeholder": frozenset({"not-sought", "attestation-invalid", "accepted", "rejected"}),
}
VERDICT_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w-])(?P<verdict>abi|trace|property|adequacy|stakeholder)`?\s*(?:=|:)\s*`?(?P<value>[a-z]+(?:-[a-z]+)*)`?",
    re.IGNORECASE,
)
CANONICAL_COMPONENTS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("C1", (
        ".agents/skills/ultimateinterview/SKILL.md", ".agents/skills/ultimateinterview/references/output-template.md",
        ".agents/skills/ultimateinterview/references/state-files.md", ".agents/skills/ultimateinterview/references/assurance-*.md",
        ".agents/skills/ultimateinterview/references/boundary-coverage.md", ".agents/skills/ultimateinterview/scripts/assurance_schema.py",
        ".agents/skills/ultimateinterview/scripts/protocol_state.py", ".agents/skills/ultimateinterview/scripts/session_contracts.py",
        ".agents/skills/ultimateinterview/scripts/build_contract_schema.py", ".agents/skills/ultimateinterview/scripts/test_assurance_*.py",
        ".agents/skills/ultimateinterview/scripts/test_v0_integration_compatibility.py", ".agents/skills/ultimateinterview/scripts/test_v1_protocol_integration.py",
    )),
    ("C2", (
        ".agents/skills/ultimateinterview/references/orientation.md",
        ".agents/skills/ultimateinterview/scripts/session_init.py", ".agents/skills/ultimateinterview/scripts/session_update.py",
        ".agents/skills/ultimateinterview/scripts/session_manifest.py", ".agents/skills/ultimateinterview/scripts/session_seal.py",
        ".agents/skills/ultimateinterview/scripts/session_status.py", ".agents/skills/ultimateinterview/scripts/test_v1_session_integration.py",
        ".agents/skills/ultimateinterview/scripts/atomic_write.py", ".agents/skills/ultimateinterview/scripts/test_atomic_write.py",
        ".agents/skills/ultimateinterview/scripts/test_deterministic_helpers.py",
        ".agents/skills/ultimateinterview/scripts/test_session_status_path_boundary.py",
        ".agents/skills/ultimateinterview/scripts/test_v2_session_manifest.py", ".agents/skills/ultimateinterview/scripts/integration_fixtures/v*-*/**",
    )),
    ("C3", (
        ".agents/skills/ultimateinterview/scripts/behavior_atoms.py", ".agents/skills/ultimateinterview/scripts/handoff_coverage.py",
        ".agents/skills/ultimateinterview/scripts/probe_*.py", ".agents/skills/ultimateinterview/scripts/test_atom_*.py",
        ".agents/skills/ultimateinterview/scripts/test_behavior_atoms.py", ".agents/skills/ultimateinterview/scripts/test_probe_*.py",
        ".agents/skills/ultimateinterview/scripts/test_v1_probe_integration.py", ".agents/skills/ultimateinterview/scripts/test_v2_probe_integration.py",
    )),
    ("C4", (
        ".agents/skills/ultimateinterview/scripts/receipt_*.py", ".agents/skills/ultimateinterview/scripts/evidence_identity.py",
        ".agents/skills/ultimateinterview/scripts/claim_evidence.py", ".agents/skills/ultimateinterview/scripts/ambiguity_ledger.py",
        ".agents/skills/ultimateinterview/scripts/test_receipt_*.py", ".agents/skills/ultimateinterview/scripts/test_evidence_identity.py",
        ".agents/skills/ultimateinterview/scripts/test_claim_evidence*.py",
    )),
    ("C5", (
        ".agents/skills/ultimateinterview/scripts/implementation_gate.py", ".agents/skills/ultimateinterview/scripts/build_contract.py",
        ".agents/skills/ultimateinterview/references/consumer-verification.md", ".agents/skills/ultimateinterview/scripts/test_consumer_contract.py",
        ".agents/skills/ultimateinterview/scripts/test_output_template_consumer_contract.py",
        ".agents/skills/ultimateinterview/scripts/test_build_contract*.py", ".agents/skills/ultimateinterview/scripts/test_v2_gate_integration.py",
    )),
    ("C6", (
        ".agents/skills/ultimateinterview/scripts/forward_*.py", ".agents/skills/ultimateinterview/scripts/forward_fixtures/**",
        ".agents/skills/ultimateinterview/scripts/validator_boundary*.py", ".agents/skills/ultimateinterview/scripts/release_audit.py",
        ".agents/skills/ultimateinterview/scripts/release_audit_map.json", ".agents/skills/ultimateinterview/scripts/test_v2_validator_boundary.py",
        ".agents/skills/ultimateinterview/scripts/test_release_audit.py", ".agents/skills/ultimateinterview/scripts/test_release_audit_plan_binding.py",
        ".agents/skills/ultimateinterview/scripts/test_forward_harness*.py",
        ".agents/skills/ultimateinterview-postmortem/references/postmortem-template.md", ".agents/skills/ultimateinterview-postmortem/references/synthetic-calibration.md",
        ".agents/skills/ultimateinterview-postmortem/scripts/postmortem_lint.py", ".agents/skills/ultimateinterview-postmortem/scripts/postmortem_v2_calibration.py",
        ".agents/skills/ultimateinterview-postmortem/scripts/postmortem_v2_lint.py", ".agents/skills/ultimateinterview-postmortem/scripts/postmortem_v2_markdown.py",
        ".agents/skills/ultimateinterview-postmortem/scripts/validator_boundary.py",
        ".agents/skills/ultimateinterview-postmortem/scripts/test_postmortem_v2_calibration.py", ".agents/skills/ultimateinterview-postmortem/scripts/test_postmortem_v2_markdown.py",
        ".agents/skills/ultimateinterview-postmortem/scripts/test_postmortem_v2_integration.py",
        ".agents/skills/ultimateinterview-postmortem/scripts/test_v2_validator_boundary.py", ".agents/skills/ultimateinterview-postmortem/scripts/regression_fixtures/v2-calibration-*/**",
        ".omo/evidence/task-1-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-2-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-3-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-4-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-5-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-6-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-7-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-8-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-9-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-10-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-11-ultimateinterview-v2-assurance-plane.*", ".omo/evidence/task-12-ultimateinterview-v2-assurance-plane.*",
        ".omo/evidence/task-13-ultimateinterview-v2-assurance-plane.*",
    )),
)


class Component(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    id: Literal["C1", "C2", "C3", "C4", "C5", "C6"]
    paths: tuple[str, ...]


class AuditMap(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    components: tuple[Component, ...]


def load_map(path: Path | None = None) -> tuple[Component, ...]:
    map_path = path or Path(__file__).with_name("release_audit_map.json")
    try:
        parsed = AuditMap.model_validate_json(map_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        raise typer.BadParameter(f"invalid release audit map: {error}") from error
    actual = tuple((component.id, component.paths) for component in parsed.components)
    if tuple(component.id for component in parsed.components) != COMPONENT_IDS:
        raise typer.BadParameter("invalid release audit map: components must be exactly C1 through C6")
    if actual != CANONICAL_COMPONENTS:
        raise typer.BadParameter("invalid release audit map: path families must match the canonical C1 through C6 map")
    return parsed.components


def _components_for(relative: str, components: tuple[Component, ...]) -> tuple[str, ...]:
    return tuple(
        component.id for component in components if any(fnmatch.fnmatchcase(relative, pattern) for pattern in component.paths)
    )


def _required_evidence(evidence_dir: Path) -> tuple[str, ...]:
    diagnostics: list[str] = []
    for task in range(1, 14):
        for stage in EVIDENCE_STAGES:
            if not (evidence_dir / f"task-{task}-ultimateinterview-v2-assurance-plane.{stage}.txt").is_file():
                diagnostics.append(f"missing-evidence: task-{task}: {stage}")
        if task in CLEANUP_TASKS and not (evidence_dir / f"task-{task}-ultimateinterview-v2-assurance-plane.cleanup.txt").is_file():
            diagnostics.append(f"missing-evidence: task-{task}: cleanup")
    return tuple(diagnostics)


def _workspace_path(workspace_root: Path, supplied: Path, option: Literal["evidence-dir", "plan"]) -> Path:
    candidate = supplied if supplied.is_absolute() else workspace_root / supplied
    resolved = candidate.resolve()
    if not resolved.is_relative_to(workspace_root):
        raise typer.BadParameter(f"{option} must be inside --workspace-root")
    match option:
        case "evidence-dir":
            if not resolved.is_dir():
                raise typer.BadParameter("evidence-dir must be a directory")
        case "plan":
            if not resolved.is_file():
                raise typer.BadParameter("plan must be a file")
        case unreachable:
            assert_never(unreachable)
    return resolved


def _validated_plan(workspace_root: Path, supplied: Path) -> Path:
    resolved = _workspace_path(workspace_root, supplied, "plan")
    if resolved.relative_to(workspace_root).as_posix() != EXPECTED_PLAN_RELATIVE:
        raise typer.BadParameter(f"plan must be {EXPECTED_PLAN_RELATIVE}")
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise typer.BadParameter(f"plan is unreadable: {error}") from error
    if any(marker not in content for marker in REQUIRED_PLAN_MARKERS):
        raise typer.BadParameter("plan is missing assurance-plane contract markers")
    return resolved


def _verdict_wording(path: Path, relative: str) -> tuple[str, ...]:
    if path.suffix != ".md":
        return ()
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return (f"unreadable-document: {relative}: {error}",)
    diagnostics: list[str] = []
    for assignment in VERDICT_ASSIGNMENT.finditer(content):
        verdict = assignment["verdict"].lower()
        value = assignment["value"].lower()
        if value not in VERDICT_VALUES[verdict]:
            diagnostics.append(f"invalid-verdict-value: {verdict}={value}")
    return tuple(diagnostics)


def audit(workspace_root: Path, changed_paths: Path, evidence_dir: Path | None = None) -> tuple[str, ...]:
    paths, diagnostics = read_changed_paths(workspace_root, changed_paths)
    results = list(diagnostics)
    components = load_map()
    for path in paths:
        if not path.relative.startswith(ALLOWED_CHANGED_PREFIXES):
            results.append(f"outside-release-scope: {path.relative}")
            continue
        matches = _components_for(path.relative, components)
        if not matches:
            results.append(f"unmapped-path: {path.relative}")
        elif len(matches) > 1:
            results.append(f"ambiguous-path: {path.relative}")
        results.extend(_verdict_wording(path.absolute, path.relative))
    selected_evidence = evidence_dir if evidence_dir is not None else workspace_root / ".omo" / "evidence"
    return tuple(sorted(set(results + list(_required_evidence(selected_evidence)))))


@app.command()
def main(
    workspace_root: Annotated[Path, typer.Option("--workspace-root")],
    changed_paths: Annotated[Path, typer.Option("--changed-paths")],
    evidence_dir: Annotated[Path | None, typer.Option("--evidence-dir")] = None,
    plan: Annotated[Path | None, typer.Option("--plan")] = None,
) -> None:
    root = workspace_root.resolve()
    selected_evidence = _workspace_path(root, evidence_dir, "evidence-dir") if evidence_dir is not None else None
    selected_plan = plan if plan is not None else Path(EXPECTED_PLAN_RELATIVE)
    _ = _validated_plan(root, selected_plan)
    diagnostics = audit(root, changed_paths, selected_evidence)
    if diagnostics:
        typer.echo("\n".join(diagnostics))
        raise typer.Exit(1)
    typer.echo("release-audit: ok")


if __name__ == "__main__":
    app()
