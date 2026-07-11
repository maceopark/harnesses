#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest>=8.0"]
# ///

# ─── How to run ───
# uv run --python 3.13 --with 'pytest>=8.0' pytest -q scripts/test_assurance_reference_routing.py

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = SKILL_ROOT / "SKILL.md"
ROUTING_HEADING = "## ENDGAME Assurance Routing"
LINK_PATTERN = re.compile(r"\[[^\]]+\]\((references/[a-z-]+\.md)\)")
PROHIBITED_CATEGORICAL_CLAIMS = (
    "independently verified",
    "cryptographically sound",
    "proves knowledge",
    "bft-safe",
    "semantically complete",
    "externally fresh",
)


@dataclass(frozen=True, slots=True)
class Route:
    path: str
    trigger: str


REQUIRED_ROUTES = (
    Route(
        "references/assurance-boundaries.md",
        "When a v2 assurance result is requested or reported.",
    ),
    Route(
        "references/boundary-coverage.md",
        "When high-impact or enumerated behavior crosses an actor, system, or handoff boundary.",
    ),
    Route(
        "references/consumer-verification.md",
        "When a downstream consumer receives a contract, grant, or receipt.",
    ),
)
REQUIRED_SKILL_TEXT = (
    "v0/v1 are historical structural-only results and must not claim v2 verdicts.",
    "v2 records five explicit verdicts: abi, trace, property, adequacy, stakeholder.",
    "Boundary coverage is conditional ENDGAME coverage, not a seventh mandatory lens.",
)
REQUIRED_BOUNDARY_TEXT = (
    "`abi` does not imply",
    "`trace` does not imply",
    "`property` does not imply",
    "`adequacy` does not imply",
    "`stakeholder` does not imply",
)
REQUIRED_RELEASE_AUDIT_OPERATOR_TEXT = (
    "## Release-audit operator invocation",
    "git -C \"$ROOT\" diff --name-only \"$BASE\"...HEAD > \"$PATHS\"",
    "scripts/release_audit.py",
    "--workspace-root \"$ROOT\"",
    "--changed-paths \"$PATHS\"",
    "--evidence-dir \"$ROOT/.omo/evidence\"",
    "--plan \"$ROOT/.omo/plans/ultimateinterview-v2-assurance-plane.md\"",
    "explicit generated workspace input, not an assumption",
    "intentionally assigns\n`references/orientation.md` to C2 because that reference routes lifecycle\ninitialization",
)
REQUIRED_CONSUMER_TEXT = "Consumer execution, authentication, and policy enforcement remain downstream."
REQUIRED_ORIENTATION_V2_TEXT = (
    "Before the normal v1 initializer, determine whether the requester explicitly asked for an assurance-v2 result.",
    "`scripts/session_init.py <repo-root> <slug> --depth <depth> --entries '<json array>' --schema-version 2`",
    "Otherwise run the existing command without `--schema-version`; its default remains v1.",
)
V2_LIFECYCLE_STEPS = (
    "scripts/session_seal.py <session-dir>",
    "scripts/receipt_import.py <session-dir> < <receipt.json>",
    "scripts/session_status.py <session-dir> --format markdown --gate --require-assurance-v2 --require-manifest --require-execution-receipts",
)


def routing_section(skill_text: str) -> str:
    start = skill_text.find(ROUTING_HEADING)
    assert start >= 0, "missing ENDGAME assurance routing table"
    end = skill_text.find("\n## ", start + len(ROUTING_HEADING))
    if end < 0:
        return skill_text[start:]
    return skill_text[start:end]


def validate_assurance_routing(skill_path: Path) -> None:
    skill_text = skill_path.read_text(encoding="utf-8")
    section = routing_section(skill_text)
    links = tuple(LINK_PATTERN.findall(section))
    expected_paths = tuple(route.path for route in REQUIRED_ROUTES)
    assert links == expected_paths, f"unexpected assurance routes: {links}"
    root = skill_path.parent.resolve()
    for route in REQUIRED_ROUTES:
        assert route.trigger in section, f"missing assurance route trigger: {route.trigger}"
        target = (skill_path.parent / route.path).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise AssertionError(f"assurance route escapes skill root: {route.path}") from error
        assert target.is_file(), f"assurance route target missing: {route.path}"
    for required in REQUIRED_SKILL_TEXT:
        assert required in section, f"missing assurance routing statement: {required}"
    assurance_boundaries = (skill_path.parent / REQUIRED_ROUTES[0].path).read_text(encoding="utf-8")
    for required in REQUIRED_BOUNDARY_TEXT:
        assert required in assurance_boundaries, f"missing verdict boundary: {required}"
    for required in REQUIRED_RELEASE_AUDIT_OPERATOR_TEXT:
        assert required in assurance_boundaries, f"missing release-audit operator guidance: {required}"
    consumer_verification = (skill_path.parent / REQUIRED_ROUTES[2].path).read_text(encoding="utf-8")
    assert REQUIRED_CONSUMER_TEXT in consumer_verification
    orientation = (skill_path.parent / "references" / "orientation.md").read_text(encoding="utf-8")
    for required in REQUIRED_ORIENTATION_V2_TEXT:
        assert required in orientation, f"missing v2 orientation route: {required}"
    lifecycle_positions = tuple(section.find(step) for step in V2_LIFECYCLE_STEPS)
    assert all(position >= 0 for position in lifecycle_positions), "missing v2 lifecycle command"
    assert lifecycle_positions == tuple(sorted(lifecycle_positions)), "v2 lifecycle commands are out of order"
    combined = "\n".join(
        [
            skill_text,
            assurance_boundaries,
            (skill_path.parent / REQUIRED_ROUTES[1].path).read_text(encoding="utf-8"),
            consumer_verification,
        ],
    ).lower()
    for prohibited in PROHIBITED_CATEGORICAL_CLAIMS:
        assert prohibited not in combined, f"prohibited categorical claim: {prohibited}"


def copied_skill(tmp_path: Path) -> Path:
    copied_root = tmp_path / "ultimateinterview"
    copied_root.mkdir()
    shutil.copy2(SKILL_PATH, copied_root / "SKILL.md")
    shutil.copytree(SKILL_ROOT / "references", copied_root / "references")
    return copied_root / "SKILL.md"


def test_canonical_assurance_routes_are_complete() -> None:
    validate_assurance_routing(SKILL_PATH)


@pytest.mark.parametrize("route", REQUIRED_ROUTES)
def test_missing_direct_route_is_rejected(tmp_path: Path, route: Route) -> None:
    skill_copy = copied_skill(tmp_path)
    text = skill_copy.read_text(encoding="utf-8")
    skill_copy.write_text(text.replace(route.path, "references/missing.md", 1), encoding="utf-8")

    with pytest.raises(AssertionError, match="unexpected assurance routes"):
        validate_assurance_routing(skill_copy)


def test_missing_link_target_is_rejected(tmp_path: Path) -> None:
    skill_copy = copied_skill(tmp_path)
    (skill_copy.parent / REQUIRED_ROUTES[0].path).unlink()

    with pytest.raises(AssertionError, match="assurance route target missing"):
        validate_assurance_routing(skill_copy)


def test_prohibited_claim_inserted_into_temporary_copy_is_rejected(tmp_path: Path) -> None:
    skill_copy = copied_skill(tmp_path)
    skill_copy.write_text(
        skill_copy.read_text(encoding="utf-8") + "\nindependently verified\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="prohibited categorical claim"):
        validate_assurance_routing(skill_copy)


def test_missing_release_audit_operator_guidance_is_rejected(tmp_path: Path) -> None:
    skill_copy = copied_skill(tmp_path)
    assurance_boundaries = skill_copy.parent / REQUIRED_ROUTES[0].path
    assurance_boundaries.write_text(
        assurance_boundaries.read_text(encoding="utf-8").replace(
            "`--evidence-dir` is an explicit generated workspace input, not an assumption\n",
            "",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="missing release-audit operator guidance"):
        validate_assurance_routing(skill_copy)


def test_missing_v2_orientation_route_is_rejected(tmp_path: Path) -> None:
    skill_copy = copied_skill(tmp_path)
    orientation = skill_copy.parent / "references" / "orientation.md"
    orientation.write_text(
        orientation.read_text(encoding="utf-8").replace("--schema-version 2", "--schema-version 3", 1),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="missing v2 orientation route"):
        validate_assurance_routing(skill_copy)


def test_out_of_order_v2_lifecycle_is_rejected(tmp_path: Path) -> None:
    skill_copy = copied_skill(tmp_path)
    text = skill_copy.read_text(encoding="utf-8")
    first, second, third = V2_LIFECYCLE_STEPS
    lifecycle = "\n".join((first, second, third))
    skill_copy.write_text(text.replace(lifecycle, "\n".join((second, first, third)), 1), encoding="utf-8")

    with pytest.raises(AssertionError, match="v2 lifecycle commands are out of order"):
        validate_assurance_routing(skill_copy)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
