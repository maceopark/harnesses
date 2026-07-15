from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from driftbench import interview_eval

from driftbench.cli import CliError, build_parser


class _StopAfterInterview(BaseException):
    pass


class _RecordingPane:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def create(self) -> None:
        self.events.append("pane:create")

    def exchange(self, question: object, answer: object) -> None:
        self.events.append(("pane:exchange", question, answer))

    def stage(self, name: str) -> None:
        self.events.append(("pane:stage", name))

    def activity_line(self, line: str) -> None:
        self.events.append(("pane:activity", line))


class _RecordingPresentation:
    def __init__(self, pane: _RecordingPane) -> None:
        self.pane = pane

    def pane_for(self, cell: object) -> _RecordingPane:
        del cell
        return self.pane

    def cell_succeeded(self, cell: object) -> None:
        del cell
        self.pane.events.append("pane:succeeded")

    def cell_failed(self, cell: object, error: BaseException) -> None:
        del cell
        self.pane.events.append(("pane:failed", type(error).__name__))


def _cell_fixture(tmp_path: Path) -> tuple[Path, dict[str, object], Path]:
    root = tmp_path / "run"
    starter = tmp_path / "starter"
    starter.mkdir()
    (starter / "app.py").write_text("pass\n", encoding="utf-8")
    skill = tmp_path / "candidate-SKILL.md"
    skill.write_text("# Candidate\n", encoding="utf-8")
    frozen = tmp_path / "baseline/frozen"
    (frozen / ".agents/skills/ultimateinterview-postmortem/references").mkdir(
        parents=True
    )
    (frozen / ".agents/skills/ultimateinterview/scripts").mkdir(parents=True)
    (frozen / ".agents/skills/ultimateinterview/references").mkdir(parents=True)
    (frozen / ".agents/skills/ultimateinterview-postmortem/SKILL.md").write_text(
        "postmortem", encoding="utf-8"
    )
    (
        frozen
        / ".agents/skills/ultimateinterview-postmortem/references/postmortem-template.md"
    ).write_text("template", encoding="utf-8")
    (
        frozen / ".agents/skills/ultimateinterview/references/json-contracts.md"
    ).write_text("contracts", encoding="utf-8")
    cell = {
        "cell_id": "case-1-candidate",
        "case_id": "case-1",
        "treatment": "candidate",
        "skill": skill,
        "prompt": "prompt",
        "starter": starter,
    }
    (frozen.parent / "public-authority.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case-1",
                        "starter_digest": interview_eval.starter_tree_digest(starter),
                        "reconciliation": {
                            "authorities": [
                                {
                                    "kind": "owner-decision",
                                    "constraints": ["prompt"],
                                }
                            ]
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return root, cell, frozen


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


def test_codex_uses_medium_reasoning_effort_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        argv: list[str],
        cwd: Path,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, prompt, env
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(interview_eval, "_run", fake_run)

    interview_eval._codex(
        "codex",
        "gpt-5.6-sol",
        "medium",
        "/home",
        "/codex-home",
        ["exec", "--json"],
        tmp_path,
        "prompt",
    )

    assert len(commands) == 1
    assert 'model="gpt-5.6-sol"' in commands[0]
    assert 'model_reasoning_effort="medium"' in commands[0]


def test_run_streams_stdout_while_preserving_complete_stdout_and_stderr(
    tmp_path: Path,
) -> None:
    seen: list[str] = []
    program = (
        "import sys; data=sys.stdin.read(); "
        'sys.stdout.write(\'{"type":"turn.started"}\\n\'+data); '
        "sys.stderr.write('diagnostic\\n')"
    )

    result = interview_eval._run(
        [sys.executable, "-c", program],
        tmp_path,
        prompt="tail-without-newline",
        activity_line=seen.append,
    )

    assert result.stdout == '{"type":"turn.started"}\ntail-without-newline'
    assert result.stderr == "diagnostic\n"
    assert seen == ['{"type":"turn.started"}\n', "tail-without-newline"]


def test_run_ignores_activity_callback_failure_without_losing_output(
    tmp_path: Path,
) -> None:
    def broken(_line: str) -> None:
        raise KeyboardInterrupt

    result = interview_eval._run(
        [sys.executable, "-c", "print('complete')"],
        tmp_path,
        activity_line=broken,
    )

    assert result.stdout == "complete\n"


@pytest.mark.parametrize(
    ("setting", "expected"), [(None, "medium"), ("low", "low"), ("high", "high")]
)
def test_live_enrollment_configures_reasoning_effort(
    tmp_path: Path,
    setting: str | None,
    expected: str,
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"codex": {"executable": "codex"}}), encoding="utf-8")
    enrollment = tmp_path / "live.toml"
    effort = "" if setting is None else f'model_reasoning_effort = "{setting}"\n'
    enrollment.write_text(
        'model = "gpt-5.6-sol"\n'
        f"{effort}"
        'home_selector = "/home"\n'
        'codex_home_selector = "/codex"\n',
        encoding="utf-8",
    )

    assert interview_eval._policy_selectors(policy, enrollment)[2] == expected


def test_live_enrollment_rejects_invalid_reasoning_effort(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"codex": {"executable": "codex"}}), encoding="utf-8")
    enrollment = tmp_path / "live.toml"
    enrollment.write_text(
        'model = "gpt-5.6-sol"\n'
        'model_reasoning_effort = "fastest"\n'
        'home_selector = "/home"\n'
        'codex_home_selector = "/codex"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="model_reasoning_effort is invalid"):
        interview_eval._policy_selectors(policy, enrollment)


@pytest.mark.parametrize("turns", [0, 1])
def test_cell_routes_interview_exchanges_and_keeps_pane_for_compiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, turns: int
) -> None:
    root, cell, frozen = _cell_fixture(tmp_path)
    events: list[object] = []
    pane = _RecordingPane(events)
    presentation = _RecordingPresentation(pane)
    codex_call = 0

    def fake_run(
        argv: list[str],
        cwd: Path,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, prompt, env
        if any("authority_reconcile.py" in argument for argument in argv):
            output = Path(argv[argv.index("--output") + 1])
            output.write_text("{}\n", encoding="utf-8")
            events.append("run:authority-reconcile")
            return subprocess.CompletedProcess(argv, 0, "", "")
        events.append("run:authority-compiler")
        raise _StopAfterInterview

    def fake_codex(
        executable: str,
        model: str,
        reasoning_effort: str,
        home: str,
        codex_home: str,
        argv: list[str],
        cwd: Path,
        prompt: str,
        activity_line: object = None,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal codex_call
        assert reasoning_effort == "medium"
        del executable, model, home, codex_home, cwd, prompt
        codex_call += 1
        output = Path(argv[argv.index("--output-last-message") + 1])
        if "simulator-schema.json" in " ".join(argv):
            payload = {"answer": "multiline answer\nline two"}
            events.append("codex:simulator")
            stdout = ""
        else:
            complete = turns == 0 or codex_call > 1
            payload = {
                "complete": complete,
                "question": "multiline question\nline two" if not complete else "",
                "discovery_record": "{}" if complete else "",
            }
            events.append("codex:interviewer")
            stdout = (
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}) + "\n"
                if codex_call == 1
                else ""
            )
        output.write_text(json.dumps(payload), encoding="utf-8")
        if activity_line is not None and stdout:
            activity_line(stdout)  # type: ignore[operator]
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(interview_eval, "_run", fake_run)
    monkeypatch.setattr(interview_eval, "_codex", fake_codex)

    with pytest.raises(_StopAfterInterview):
        interview_eval._cell(
            root,
            cell,
            ("codex", "model", "medium", "/home", "/codex"),
            frozen,
            presentation,  # type: ignore[arg-type]
        )

    first_interviewer = events.index("codex:interviewer")
    assert events[:3] == [
        "pane:create",
        ("pane:stage", "Preparing"),
        "run:authority-reconcile",
    ]
    assert events[first_interviewer - 1] == ("pane:stage", "Interview")
    assert ("pane:stage", "Interview") in events
    assert events[-2:] == [("pane:stage", "Contract"), "run:authority-compiler"]
    exchanges = [
        event
        for event in events
        if isinstance(event, tuple) and event[0] == "pane:exchange"
    ]
    if turns == 0:
        assert exchanges == []
    else:
        assert exchanges == [
            (
                "pane:exchange",
                "multiline question\nline two",
                "multiline answer\nline two",
            )
        ]


def test_cell_retains_pane_summary_on_catchable_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, cell, frozen = _cell_fixture(tmp_path)
    events: list[object] = []
    pane = _RecordingPane(events)

    def fake_run(
        argv: list[str],
        cwd: Path,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, prompt, env
        output = Path(argv[argv.index("--output") + 1])
        output.write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def interrupted(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise KeyboardInterrupt

    monkeypatch.setattr(interview_eval, "_run", fake_run)
    monkeypatch.setattr(interview_eval, "_codex", interrupted)

    with pytest.raises(KeyboardInterrupt):
        interview_eval._cell(
            root,
            cell,
            ("codex", "model", "medium", "/home", "/codex"),
            frozen,
            _RecordingPresentation(pane),  # type: ignore[arg-type]
        )

    assert events == [
        "pane:create",
        ("pane:stage", "Preparing"),
        ("pane:stage", "Interview"),
    ]


def test_cell_treats_invalid_completed_discovery_as_interview_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, cell, frozen = _cell_fixture(tmp_path)
    events: list[object] = []
    pane = _RecordingPane(events)

    def fake_run(
        argv: list[str],
        cwd: Path,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, prompt, env
        output = Path(argv[argv.index("--output") + 1])
        output.write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def malformed(
        executable: str,
        model: str,
        reasoning_effort: str,
        home: str,
        codex_home: str,
        argv: list[str],
        cwd: Path,
        prompt: str,
        activity_line: object = None,
    ) -> subprocess.CompletedProcess[str]:
        assert reasoning_effort == "medium"
        del executable, model, home, codex_home, cwd, prompt
        del activity_line
        output = Path(argv[argv.index("--output-last-message") + 1])
        output.write_text(
            json.dumps(
                {"complete": True, "question": "", "discovery_record": "not-json"}
            ),
            encoding="utf-8",
        )
        stdout = json.dumps({"type": "thread.started", "thread_id": "thread-1"})
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(interview_eval, "_run", fake_run)
    monkeypatch.setattr(interview_eval, "_codex", malformed)

    with pytest.raises(RuntimeError, match="Discovery Record is not JSON"):
        interview_eval._cell(
            root,
            cell,
            ("codex", "model", "medium", "/home", "/codex"),
            frozen,
            _RecordingPresentation(pane),  # type: ignore[arg-type]
        )

    assert events == [
        "pane:create",
        ("pane:stage", "Preparing"),
        ("pane:stage", "Interview"),
    ]


def test_cell_reports_every_whole_cell_stage_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, cell, frozen = _cell_fixture(tmp_path)
    events: list[object] = []
    presentation = _RecordingPresentation(_RecordingPane(events))

    def fake_run(
        argv: list[str],
        cwd: Path,
        prompt: str | None = None,
        env: dict[str, str] | None = None,
        activity_line: object = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, prompt, env, activity_line
        if "--output" in argv:
            output = Path(argv[argv.index("--output") + 1])
            payload = (
                {"contract_digest": "contract"}
                if "compiler_session_check.py" in " ".join(argv)
                else {}
            )
            output.write_text(json.dumps(payload), encoding="utf-8")
        stdout = "diff" if argv[:2] == ["git", "diff"] else ""
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    def fake_codex(
        executable: str,
        model: str,
        reasoning_effort: str,
        home: str,
        codex_home: str,
        argv: list[str],
        cwd: Path,
        prompt: str,
        activity_line: object = None,
    ) -> subprocess.CompletedProcess[str]:
        assert reasoning_effort == "medium"
        del executable, model, home, codex_home, cwd, prompt
        output = Path(argv[argv.index("--output-last-message") + 1])
        if output.name == "interviewer.json":
            output.write_text(
                json.dumps(
                    {"complete": True, "question": "", "discovery_record": "{}"}
                ),
                encoding="utf-8",
            )
            stdout = '{"type":"thread.started","thread_id":"thread-1"}\n'
        elif output.name == "implementation-return.json":
            output.write_text(json.dumps({"status": "implemented"}), encoding="utf-8")
            stdout = '{"type":"item.completed","item":{"type":"file_change"}}\n'
        else:
            output.write_text("# Ultimateinterview Postmortem\n", encoding="utf-8")
            stdout = '{"type":"turn.completed"}\n'
        if activity_line is not None:
            activity_line(stdout)  # type: ignore[operator]
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(interview_eval, "_run", fake_run)
    monkeypatch.setattr(interview_eval, "_codex", fake_codex)

    result = interview_eval._cell(
        root,
        cell,
        ("codex", "gpt-5.6-sol", "medium", "/home", "/codex"),
        frozen,
        presentation,  # type: ignore[arg-type]
    )

    assert result["status"] == "completed"
    assert [event for event in events if event[0] == "pane:stage"] == [
        ("pane:stage", "Preparing"),
        ("pane:stage", "Interview"),
        ("pane:stage", "Contract"),
        ("pane:stage", "Implementation"),
        ("pane:stage", "Checking"),
        ("pane:stage", "Postmortem"),
    ]


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
    presentations: list[object] = []
    attempt_presentations: list[_RecordingPresentation] = []
    detections: list[dict[str, object]] = []

    monkeypatch.setattr(interview_eval, "_project", lambda _: project)
    monkeypatch.setattr(
        interview_eval,
        "_policy_selectors",
        lambda *_: ("codex", "gpt-5.6-sol", "medium", "/home", "/codex"),
    )
    monkeypatch.setattr(interview_eval, "_baseline", lambda _: baseline.parent)

    def fake_detect(**kwargs: object) -> object:
        detections.append(kwargs)
        presentation = _RecordingPresentation(_RecordingPane([]))
        attempt_presentations.append(presentation)
        return presentation

    monkeypatch.setattr(interview_eval.TmuxPresentation, "detect", fake_detect)

    def fake_cell(
        root: Path,
        cell: dict[str, object],
        selectors: tuple[str, str, str, str, str],
        frozen: Path,
        presentation: object | None = None,
    ) -> dict[str, object]:
        del selectors, frozen
        cell_id = str(cell["cell_id"])
        calls.append(cell_id)
        assert presentation is not None
        presentations.append(presentation)
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
    assert [row["scheduled_cells"] for row in detections] == [2, 2, 2]
    assert [row["max_parallel"] for row in detections] == [2, 2, 2]
    assert presentations[0] is presentations[1]
    assert presentations[2] is presentations[3]
    assert presentations[4] is presentations[5]
    assert len({id(value) for value in presentations}) == 3
    assert len({str(row["attempt_id"]) for row in detections}) == 3
    assert [presentation.pane.events for presentation in attempt_presentations] == [
        ["pane:succeeded", "pane:succeeded"],
        ["pane:succeeded", "pane:succeeded"],
        ["pane:succeeded", "pane:succeeded"],
    ]


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
