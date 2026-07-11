#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

import typer
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.probe_observations import ProbeAttempt, ProbeOutcome, ProbeResult, ProbeSequence, ProducerKind, ProducerLineage
from scripts.probe_types import AuthorizationScope, ProbeAuthorization, ProbeDecision, ProbeIntent, ProbeLevel, select_probe_level

__all__ = (
    "AuthorizationScope",
    "ProbeAttempt",
    "ProbeAuthorization",
    "ProbeDecision",
    "ProbeIntent",
    "ProbeLevel",
    "ProbeOutcome",
    "ProbeResult",
    "ProbeSequence",
    "ProducerKind",
    "ProducerLineage",
    "main",
    "select_probe_level",
)


def main() -> None:
    try:
        attempt = ProbeAttempt.model_validate_json(sys.stdin.read())
    except ValidationError as error:
        errors = error.errors(include_context=False, include_input=False, include_url=False)
        first = errors[0]
        location = ".".join(str(part) for part in first["loc"]) or "<root>"
        suffix = "" if len(errors) == 1 else f" (+{len(errors) - 1} more)"
        raise typer.BadParameter(f"invalid probe attempt at {location}: {first['msg']}{suffix}") from error
    typer.echo(attempt.model_dump_json(indent=2))


if __name__ == "__main__":
    typer.run(main)
