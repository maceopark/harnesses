#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from scripts import session_manifest


def main(
    session_dir: Annotated[Path, typer.Argument(help="Schema-v2 session directory to seal.")],
) -> None:
    try:
        manifest = session_manifest.seal_session(session_dir)
    except session_manifest.SessionManifestError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "manifest_digest": manifest.manifest_digest,
                "snapshot_complete": True,
            },
            indent=2,
            sort_keys=True,
        ),
    )


if __name__ == "__main__":
    typer.run(main)
