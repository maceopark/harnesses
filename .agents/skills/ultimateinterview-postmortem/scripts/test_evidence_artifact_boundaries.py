from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pack_evidence
from test_pack_evidence import make_session

runner = CliRunner()


@pytest.mark.parametrize(
    ("left", "right"),
    (
        (".omo/evidence/demo/a-b.txt", ".omo/evidence/demo/a_b.txt"),
        (".omo/evidence/demo/A.txt", ".omo/evidence/demo/a.txt"),
        (".omo/evidence/demo/a..b.txt", ".omo/evidence/demo/a--b.txt"),
    ),
)
def test_schema_v5_artifact_ids_distinguish_canonical_paths(left: str, right: str) -> None:
    assert pack_evidence.artifact_id(left) != pack_evidence.artifact_id(right)


def test_pack_rejects_duplicate_final_artifact_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path)
    evidence = tmp_path / ".omo" / "evidence" / "demo"
    evidence.mkdir(parents=True)
    (evidence / "one.txt").write_text("one", encoding="utf-8")
    (evidence / "two.txt").write_text("two", encoding="utf-8")
    monkeypatch.setattr(pack_evidence, "artifact_id", lambda _path: "artifact-collision")

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 1
    assert "duplicate artifact id" in result.output
    assert not (session / "evidence_bundle.json").exists()


def test_pack_rejects_symlinked_evidence_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    session = make_session(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside", encoding="utf-8")
    link = repo / "linked-evidence"
    link.symlink_to(outside, target_is_directory=True)

    result = runner.invoke(pack_evidence.app, [str(session), "--evidence-dir", str(link)])

    assert result.exit_code == 1
    assert "symlink" in result.output.lower()
    assert not (session / "evidence_bundle.json").exists()


def test_pack_rejects_symlinked_evidence_file(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = tmp_path / ".omo" / "evidence" / "demo"
    evidence.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (evidence / "linked.txt").symlink_to(outside)

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 1
    assert "symlink" in result.output.lower()
    assert not (session / "evidence_bundle.json").exists()


def test_pack_rejects_symlinked_parent_below_evidence_root(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = tmp_path / ".omo" / "evidence" / "demo"
    evidence.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("outside", encoding="utf-8")
    (evidence / "linked-parent").symlink_to(outside, target_is_directory=True)

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 1
    assert "symlink" in result.output.lower()


@pytest.mark.parametrize("kind", ("outside", "missing", "file"))
def test_evidence_dir_input_errors_are_typed_without_traceback(
    tmp_path: Path, kind: str
) -> None:
    repo = tmp_path / "repo"
    session = make_session(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    candidate = outside
    if kind == "missing":
        candidate = repo / "missing"
    elif kind == "file":
        candidate = repo / "evidence.txt"
        candidate.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(
        pack_evidence.app, [str(session), "--evidence-dir", str(candidate)]
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Traceback" not in result.output
    assert "evidence-dir" in result.output


def test_packed_collision_prone_names_have_unique_ids(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    evidence = tmp_path / ".omo" / "evidence" / "demo"
    evidence.mkdir(parents=True)
    for name in ("a-b.txt", "a_b.txt", "a..b.txt", "a--b.txt"):
        (evidence / name).write_text(name, encoding="utf-8")

    result = runner.invoke(pack_evidence.app, [str(session)])

    assert result.exit_code == 0, result.output
    bundle = json.loads((session / "evidence_bundle.json").read_text(encoding="utf-8"))
    ids = [record["id"] for record in bundle["artifacts"]["files"]]
    assert len(ids) == len(set(ids)) == 4
