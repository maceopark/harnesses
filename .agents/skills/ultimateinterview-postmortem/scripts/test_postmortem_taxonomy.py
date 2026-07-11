from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

import postmortem_taxonomy as taxonomy


def valid_fields(**overrides: str | None) -> dict[str, str | None]:
    fields: dict[str, str | None] = {
        "escape_id": "ESC-001",
        "failure_mode": "enumeration-miss",
        "requirement_structure": "item",
        "owning_frame": "viewpoint",
        "disposition": "new",
        "lesson_store": "project-lessons",
    }
    fields.update(overrides)
    return fields


@pytest.mark.parametrize(
    "raw, canonical",
    [
        ("item", "item"),
        ("boundary", "boundary"),
        ("interaction+runtime-only", "interaction+runtime-only"),
        ("system+negative-space", "system+negative-space"),
        (
            "system+runtime-only+negative-space",
            "system+negative-space+runtime-only",
        ),
        ("novel:feedback-loop", "novel:feedback-loop"),
    ],
)
def test_structure_canonicalizes_when_grammar_is_valid(
    raw: str, canonical: str
) -> None:
    # Given a structure containing exactly one base and unique modifiers
    # When the public parser receives it
    parsed = taxonomy.parse_requirement_structure(raw)

    # Then its dump order is stable
    assert parsed.canonical == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "item+system",
        "item+runtime-only+runtime-only",
        "negative-space",
        "novel:Feedback-Loop",
        "novel:feedback_loop",
        "novel:",
        "item+unknown",
    ],
)
def test_structure_rejects_when_grammar_is_malformed(raw: str) -> None:
    # Given a malformed structure token sequence
    # When parsing occurs, Then the boundary fails closed
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.parse_requirement_structure(raw)


@pytest.mark.parametrize(
    "failure_mode",
    [
        "trigger-too-narrow",
        "enumeration-miss",
        "scoring-starved",
        "answer-unpressured",
    ],
)
def test_v1_preserves_legacy_failure_modes_when_rows_are_well_formed(
    failure_mode: str,
) -> None:
    # Given a legacy report row using a historical failure mode
    fields = taxonomy.EscapeFields.model_validate(
        valid_fields(
            escape_id="REQ-7",
            failure_mode=failure_mode,
        )
    )

    # When it is bound to a report without a schema marker
    row = taxonomy.EscapeClassification.from_report("# Postmortem", fields)

    # Then it remains a v1 REQ-compatible row
    assert row.report_schema == 1
    assert row.escape_id == "REQ-7"


def test_v1_preserves_synthesis_core_path_when_nonrouting() -> None:
    # Given the historical synthesis transport-loss classification
    fields = taxonomy.EscapeFields.model_validate(
        valid_fields(
            escape_id="REQ-9",
            failure_mode="synthesis-loss",
            owning_frame="core-path",
            disposition="not-routing/synthesis-loss",
            lesson_store=None,
        )
    )

    # When it is parsed in compatibility mode
    row = taxonomy.EscapeClassification.from_report("# Legacy", fields)

    # Then the legacy core-path classification is retained without lesson routing
    assert row.failure_mode.value == "synthesis-loss"
    assert row.owning_frame.value == "core-path"
    assert row.lesson_store is None


@pytest.mark.parametrize(
    "owning_frame",
    [
        "viewpoint",
        "domain/state",
        "goal/obstacle",
        "misuse",
        "quality",
        "controlled-language",
        "core-path",
    ],
)
def test_existing_owning_frames_remain_routable_when_not_ontology(
    owning_frame: str,
) -> None:
    # Given a v2 row assigned to an existing lens or the always-on core path
    fields = taxonomy.EscapeFields.model_validate(
        valid_fields(owning_frame=owning_frame)
    )

    # When it is bound to the marked report
    row = taxonomy.EscapeClassification.from_report(
        "postmortem_schema: 2", fields
    )

    # Then the existing route remains available with a stable escape ID
    assert row.owning_frame.value == owning_frame
    assert row.escape_id == "ESC-001"


def test_schema_marker_selects_v2_and_missing_marker_selects_v1() -> None:
    # Given marked and unmarked report text
    # When schema detection runs
    marked = taxonomy.detect_report_schema("postmortem_schema: 2\n# Postmortem")
    unmarked = taxonomy.detect_report_schema("# Postmortem")

    # Then only the marked report opts into v2
    assert marked == 2
    assert unmarked == 1


@pytest.mark.parametrize(
    "report",
    [
        "postmortem_schema: 1",
        "postmortem_schema: 3",
        "postmortem_schema: 2\npostmortem_schema: 2",
    ],
)
def test_schema_marker_rejects_when_stale_or_duplicated(report: str) -> None:
    # Given an owned but unsupported or ambiguous marker
    # When schema detection runs, Then it fails closed
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.detect_report_schema(report)


@pytest.mark.parametrize(
    ("report", "escape_id"),
    [
        ("# Legacy", "ESC-001"),
        ("postmortem_schema: 2", "REQ-001"),
        ("postmortem_schema: 2", "ESC-1"),
    ],
)
def test_escape_id_rejects_when_incompatible_with_report_schema(
    report: str, escape_id: str
) -> None:
    # Given an identifier from the wrong schema or an unstable v2 identifier
    fields = taxonomy.EscapeFields.model_validate(valid_fields(escape_id=escape_id))

    # When the report version is bound, Then compatibility validation rejects it
    with pytest.raises(ValidationError):
        taxonomy.EscapeClassification.from_report(report, fields)


def test_ontology_miss_accepts_only_novel_no_owner_nonrouting_rows() -> None:
    # Given a genuinely novel finding with no owning frame or lesson target
    fields = taxonomy.EscapeFields.model_validate(
        valid_fields(
            failure_mode="ontology-miss",
            requirement_structure="novel:feedback-loop+runtime-only",
            owning_frame="none",
            disposition="not-routing/ontology-miss",
            lesson_store=None,
        )
    )

    # When it is bound to schema v2
    row = taxonomy.EscapeClassification.from_report(
        "postmortem_schema: 2", fields
    )

    # Then it is retained without automatic routing or ontology mutation
    assert row.requirement_structure == "novel:feedback-loop+runtime-only"
    assert row.owning_frame.value == "none"
    assert row.lesson_store is None


def test_canonical_dump_is_stable_when_modifiers_arrive_out_of_order() -> None:
    # Given a valid interaction row with reversed modifier input order
    fields = taxonomy.EscapeFields.model_validate(
        valid_fields(
            requirement_structure="interaction+runtime-only+negative-space"
        )
    )

    # When the marked classification is dumped twice
    row = taxonomy.EscapeClassification.from_report(
        "postmortem_schema: 2", fields
    )
    first = row.canonical_json()
    second = row.canonical_json()

    # Then output is byte-stable and contains canonical modifier order
    assert first == second
    assert '"requirement_structure":"interaction+negative-space+runtime-only"' in first


@pytest.mark.parametrize(
    "overrides",
    [
        {"failure_mode": "ontology-miss", "owning_frame": "quality"},
        {"failure_mode": "ontology-miss", "requirement_structure": "system"},
        {"failure_mode": "ontology-miss", "disposition": "new"},
        {"failure_mode": "ontology-miss", "lesson_store": "global-lessons"},
        {"owning_frame": "none"},
        {"disposition": "not-routing/ontology-miss"},
    ],
)
def test_ontology_miss_rejects_when_any_nonrouting_invariant_is_broken(
    overrides: dict[str, str | None],
) -> None:
    # Given a row that partially impersonates an ontology miss
    candidate = valid_fields(**overrides)

    # When the strict fields model parses it, Then no invalid state is constructed
    with pytest.raises(ValidationError):
        taxonomy.EscapeFields.model_validate(candidate)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda fields: {**fields, "extra": "forbidden"},
        lambda fields: {**fields, "lesson_store": ""},
    ],
)
def test_fields_reject_when_unknown_or_blank(
    mutate: Callable[[dict[str, str | None]], dict[str, str | None]],
) -> None:
    # Given malformed external row data
    candidate = mutate(valid_fields())

    # When it crosses the Pydantic boundary, Then strict parsing rejects it
    with pytest.raises(ValidationError):
        taxonomy.EscapeFields.model_validate(candidate)
