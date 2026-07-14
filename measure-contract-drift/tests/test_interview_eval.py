from __future__ import annotations

import json
from pathlib import Path

import pytest

from driftbench import interview_eval

from driftbench.cli import CliError, build_parser


def test_interview_eval_parser_accepts_bounded_controls() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "interview-eval",
            "run",
            "--policy",
            "policy.json",
            "--max-cells",
            "1",
            "--max-parallel",
            "12",
        ]
    )
    assert args.policy == "policy.json"
    assert args.max_cells == 1
    assert args.max_parallel == 12


def test_interview_eval_resume_parser_uses_run_dir_only() -> None:
    parser = build_parser()
    args = parser.parse_args(["interview-eval", "resume", "--run-dir", "run"])
    assert args.run_dir == "run"
    assert args.max_parallel == 1


def test_baseline_manifest_binds_vendored_skill_files(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]

    baseline = interview_eval._baseline(project)

    assert baseline.name == "baseline-89db971"
    copied = tmp_path / "project"
    copied_baseline = copied / "protocol/ultimateinterview/baseline-89db971"
    import shutil

    shutil.copytree(baseline, copied_baseline)
    skill = copied_baseline / "frozen/.agents/skills/ultimateinterview/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="vendored skill baseline mismatch"):
        interview_eval._baseline(copied)


def test_artifact_inventory_excludes_git_internals(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git/index").write_bytes(b"index")
    (tmp_path / "postmortem.md").write_text("report", encoding="utf-8")

    assert interview_eval._artifact_files(tmp_path) == [tmp_path / "postmortem.md"]


def test_artifact_inventory_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("secret", encoding="utf-8")
    (tmp_path / "link").symlink_to(target)

    with pytest.raises(RuntimeError, match="artifact symlink"):
        interview_eval._artifact_files(tmp_path)


def test_artifact_inventory_rejects_oversized_files(tmp_path: Path) -> None:
    oversized = tmp_path / "large.bin"
    with oversized.open("wb") as handle:
        handle.seek(16 * 1024 * 1024)
        handle.write(b"x")

    with pytest.raises(RuntimeError, match="exceeds 16 MiB"):
        interview_eval._artifact_files(tmp_path)


def test_policy_rejects_any_model_other_than_gpt_5_6_sol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"codex": {"executable": "codex"}}), encoding="utf-8")
    enrollment = tmp_path / ".measurecontractdrift/live.toml"
    enrollment.parent.mkdir()
    enrollment.write_text(
        'model = "other"\nhome_selector = "/home"\ncodex_home_selector = "/codex"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(interview_eval, "_project", lambda _: tmp_path)

    with pytest.raises(RuntimeError, match="requires gpt-5.6-sol"):
        interview_eval._policy_selectors(policy)


def test_run_rejects_candidate_outside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "workspace/project"
    project.mkdir(parents=True)
    policy = project / "policy.json"
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    policy.write_text(
        json.dumps(
            {
                "candidate_skill": str(outside),
                "codex": {"executable": "codex"},
            }
        ),
        encoding="utf-8",
    )
    baseline = project / "baseline"
    baseline.mkdir()
    monkeypatch.setattr(interview_eval, "_project", lambda _: project)
    monkeypatch.setattr(interview_eval, "_baseline", lambda _: baseline)

    with pytest.raises(RuntimeError, match="inside the workspace"):
        interview_eval.run(policy, max_cells=1)


def test_run_limits_cells_writes_pretty_json_and_resumes_completed_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    corpus = project / "corpus/public"
    corpus.mkdir(parents=True)
    cases = []
    for index in range(3):
        starter = corpus / f"starter-{index}"
        starter.mkdir()
        (starter / "app.py").write_text("pass\n", encoding="utf-8")
        cases.append(
            {
                "case_id": f"case-{index}",
                "prompt": f"prompt {index}",
                "starter_tree": f"starter-{index}",
            }
        )
    (corpus / "cases.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    enrollment = project / ".measurecontractdrift/live.toml"
    enrollment.parent.mkdir()
    enrollment.write_text("model = 'gpt-5.6-sol'\n", encoding="utf-8")
    candidate = project / "candidate.md"
    candidate.write_text("# Candidate\n", encoding="utf-8")
    policy = project / "policy.json"
    policy.write_text(json.dumps({"candidate_skill": "candidate.md"}), encoding="utf-8")
    baseline = project / "baseline/frozen"
    baseline.mkdir(parents=True)
    (baseline.parent / "manifest.json").write_text("{}\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(interview_eval, "_project", lambda _: project)
    monkeypatch.setattr(
        interview_eval,
        "_policy_selectors",
        lambda *_: ("codex", "gpt-5.6-sol", "/home", "/codex"),
    )
    monkeypatch.setattr(interview_eval, "_baseline", lambda _: baseline.parent)

    def fake_cell(
        root: Path,
        cell: dict[str, object],
        selectors: tuple[str, str, str, str],
        frozen: Path,
    ) -> dict[str, object]:
        del selectors, frozen
        cell_id = str(cell["cell_id"])
        calls.append(cell_id)
        artifact = root / "cells" / cell_id / "result.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(cell_id, encoding="utf-8")
        return {
            "status": "completed",
            "cell_id": cell_id,
            "hashes": {"result.txt": interview_eval._sha(artifact)},
        }

    monkeypatch.setattr(interview_eval, "_cell", fake_cell)
    run_dir = interview_eval.run(policy, max_cells=2, max_parallel=2)

    assert set(calls) == {"case-0-baseline", "case-0-candidate"}
    assert json.loads((run_dir / "receipt.json").read_text())["status"] == "partial"
    assert (run_dir / "state.json").read_text().endswith("\n")
    assert '\n  "cells"' in (run_dir / "state.json").read_text()

    candidate_input = run_dir / "inputs/candidate-SKILL.md"
    candidate_bytes = candidate_input.read_bytes()
    candidate_input.write_text("# tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="artifact mismatch"):
        interview_eval.resume(run_dir, max_cells=2, max_parallel=2)
    candidate_input.write_bytes(candidate_bytes)

    interview_eval.resume(run_dir, max_cells=2, max_parallel=2)
    assert set(calls) == {
        "case-0-baseline",
        "case-0-candidate",
        "case-1-baseline",
        "case-1-candidate",
    }
    assert json.loads((run_dir / "receipt.json").read_text())["status"] == "partial"

    completed_artifact = run_dir / "cells/case-0-baseline/result.txt"
    completed_bytes = completed_artifact.read_bytes()
    completed_artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(RuntimeError, match="artifact mismatch"):
        interview_eval.resume(run_dir, max_cells=2, max_parallel=2)
    completed_artifact.write_bytes(completed_bytes)

    interview_eval.resume(run_dir, max_cells=2, max_parallel=2)
    assert set(calls[-2:]) == {"case-2-baseline", "case-2-candidate"}
    assert json.loads((run_dir / "receipt.json").read_text())["status"] == "completed"


@pytest.mark.parametrize(
    "arguments",
    [
        ["interview-eval", "run", "--policy", "policy.json", "--max-cells", "0"],
        ["interview-eval", "run", "--policy", "policy.json", "--max-cells", "13"],
        ["interview-eval", "resume", "--run-dir", "run", "--max-parallel", "0"],
        ["interview-eval", "resume", "--run-dir", "run", "--max-parallel", "13"],
    ],
)
def test_interview_eval_parser_rejects_out_of_range_controls(
    arguments: list[str],
) -> None:
    with pytest.raises(CliError):
        build_parser().parse_args(arguments)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("partial", 0), ("completed", 0), ("failed", 13)],
)
def test_interview_eval_receipt_status_controls_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], status: str, expected: int
) -> None:
    from driftbench import cli

    (tmp_path / "receipt.json").write_text(
        json.dumps({"status": status}), encoding="utf-8"
    )

    assert cli._interview_eval_exit(tmp_path) == expected
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_cli_translates_runtime_setup_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> Path:
        raise RuntimeError("setup failed")

    monkeypatch.setattr(interview_eval, "run", fail)

    from driftbench import cli

    assert (
        cli.main(["interview-eval", "run", "--policy", "policy.json"])
        == cli.EXIT_RUNTIME_FAILURE
    )
    assert "setup failed" in capsys.readouterr().err
