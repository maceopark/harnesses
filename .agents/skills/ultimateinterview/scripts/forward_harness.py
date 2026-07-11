#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import ValidationError

from scripts.forward_harness_contract import (
    CORPUS_MANIFEST,
    EXPECTED_NAME,
    INPUT_NAME,
    ZERO_DIGEST,
    CorpusManifest,
    CorpusVersionProbe,
    ForwardHarnessError,
    ForwardVerdicts,
    ForwardResult,
    corpus_files,
    corpus_root,
    digest,
    fixture_input,
    manifest,
    manifest_preimage,
)
from scripts.forward_harness_runtime import computed_result
from scripts.forward_harness_publish import (
    commit_staged_corpus,
    corpus_snapshot,
    safe_write,
)

__all__ = (
    "ForwardHarnessError",
    "ForwardResult",
    "ForwardVerdicts",
    "evaluate_fixture",
    "main",
    "regenerate_goldens",
    "safe_write",
)

RECEIPT_NOW: Final[datetime] = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def evaluate_fixture(fixture: Path) -> ForwardResult:
    root = corpus_root(fixture)
    reviewed_manifest = manifest(root)
    try:
        expected = ForwardResult.model_validate_json(
            (fixture / EXPECTED_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as error:
        raise ForwardHarnessError(
            f"invalid reviewed expected result: {fixture.name}"
        ) from error
    result = computed_result(
        root, fixture_input(fixture), reviewed_manifest.corpus_digest
    )
    if result != expected:
        raise ForwardHarnessError(
            f"computed result does not match reviewed golden: {fixture.name}"
        )
    return result


def _regeneration_version(root: Path) -> Literal["v2"]:
    try:
        return CorpusVersionProbe.model_validate_json(
            (root / CORPUS_MANIFEST).read_text(encoding="utf-8")
        ).corpus_version
    except (OSError, ValidationError) as error:
        raise ForwardHarnessError(
            "cannot read corpus version for regeneration"
        ) from error


def _member_digests_with_results(
    root: Path, results: dict[Path, ForwardResult]
) -> dict[str, str]:
    members: dict[str, str] = {}
    for path in corpus_files(root):
        relative = path.relative_to(root).as_posix()
        result = results.get(path)
        if result is None:
            members[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            members[relative] = digest(
                result.model_dump(mode="json", exclude={"corpus_digest"})
            )
    return members


def regenerate_goldens(corpus_root: Path, *, confirm: str) -> CorpusManifest:
    if corpus_root.is_symlink() or not corpus_root.is_dir():
        raise ForwardHarnessError("corpus root is not a regular directory")
    version = _regeneration_version(corpus_root)
    if confirm != version:
        raise ForwardHarnessError("regeneration confirmation must match corpus version")
    manifest_path = corpus_root / CORPUS_MANIFEST
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.stat().st_nlink != 1
    ):
        raise ForwardHarnessError("corpus manifest must be a regular unlinked file")
    _ = corpus_files(corpus_root)
    fixtures = tuple(
        sorted(path for path in corpus_root.iterdir() if (path / INPUT_NAME).is_file())
    )
    if not fixtures or any(
        fixture.is_symlink()
        or (fixture / INPUT_NAME).is_symlink()
        or not (fixture / INPUT_NAME).is_file()
        or (fixture / EXPECTED_NAME).is_symlink()
        or not (fixture / EXPECTED_NAME).is_file()
        or (fixture / EXPECTED_NAME).stat().st_nlink != 1
        for fixture in fixtures
    ):
        raise ForwardHarnessError(
            "corpus regeneration requires regular unlinked fixture files"
        )
    snapshot = corpus_snapshot(corpus_root)
    provisional = {
        fixture / EXPECTED_NAME: computed_result(
            corpus_root, fixture_input(fixture), ZERO_DIGEST
        )
        for fixture in fixtures
    }
    members = _member_digests_with_results(corpus_root, provisional)
    corpus_digest = digest(manifest_preimage(version, members))
    final = {
        path: computed_result(corpus_root, fixture_input(path.parent), corpus_digest)
        for path in provisional
    }
    reviewed_manifest = CorpusManifest(
        corpus_version=version, members=members, corpus_digest=corpus_digest
    )
    stage = Path(
        tempfile.mkdtemp(prefix=f".{corpus_root.name}-stage-", dir=corpus_root.parent)
    )
    try:
        for path, result in final.items():
            staged = stage / path.relative_to(corpus_root)
            _ = staged.parent.mkdir(parents=True, exist_ok=True)
            _ = staged.write_text(
                json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        _ = (stage / CORPUS_MANIFEST).write_text(
            json.dumps(
                reviewed_manifest.model_dump(mode="json"), indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        commit_staged_corpus(corpus_root, stage, snapshot)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return reviewed_manifest


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    fixture: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, readable=True)
    ],
    regenerate_goldens_option: Annotated[
        bool, typer.Option("--regenerate-goldens")
    ] = False,
    confirm: Annotated[str, typer.Option("--confirm")] = "",
) -> None:
    try:
        if regenerate_goldens_option:
            corpus_root = (
                fixture if (fixture / CORPUS_MANIFEST).is_file() else fixture.parent
            )
            typer.echo(regenerate_goldens(corpus_root, confirm=confirm).corpus_digest)
        else:
            typer.echo(evaluate_fixture(fixture).model_dump_json(indent=2))
    except ForwardHarnessError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


if __name__ == "__main__":
    app()
