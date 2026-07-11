#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7"]
# ///

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from postmortem_taxonomy import (
    FailureMode,
    NovelBase,
    OwningFrame,
    RequirementBase,
    RequirementModifier,
    parse_requirement_structure,
)


@dataclass(frozen=True, slots=True)
class CalibrationEscape:
    failure_mode: FailureMode
    structure: str
    owning_frame: OwningFrame


def evaluate_calibration(
    declared: dict[str, int], escapes: tuple[CalibrationEscape, ...]
) -> tuple[str, ...]:
    expected = {
        **{mode.value: 0 for mode in FailureMode},
        **{base.value: 0 for base in RequirementBase},
        **{f"modifier:{modifier.value}": 0 for modifier in RequirementModifier},
        "owning-frame:none": 0,
    }
    for escape in escapes:
        expected[escape.failure_mode.value] += 1
        structure = parse_requirement_structure(escape.structure)
        match structure.base:
            case RequirementBase() as base:
                base_key = base.value
            case NovelBase(slug=slug):
                base_key = f"novel:{slug}"
            case unreachable:
                assert_never(unreachable)
        expected[base_key] = expected.get(base_key, 0) + 1
        for modifier in structure.modifiers:
            key = f"modifier:{modifier.value}"
            expected[key] = expected.get(key, 0) + 1
        if escape.owning_frame is OwningFrame.NONE:
            expected["owning-frame:none"] = expected.get("owning-frame:none", 0) + 1
    return tuple(
        f"v2 calibration: {key} declares {declared.get(key)!r}; escape rows derive {count}"
        for key, count in expected.items()
        if declared.get(key) != count
    )
