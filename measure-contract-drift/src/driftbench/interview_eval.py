"""Small direct-Codex interview evaluation runtime."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .corpus import starter_tree_digest

_LOCK = threading.Lock()


def _pretty(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise RuntimeError(f"artifact symlink is not allowed: {relative}")
        if path.is_file():
            if path.stat().st_size > 16 * 1024 * 1024:
                raise RuntimeError(f"artifact exceeds 16 MiB: {relative}")
            files.append(path)
    return files


def _remove_python_caches(root: Path) -> None:
    for cache in root.rglob("__pycache__"):
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
    for bytecode in root.rglob("*.py[co]"):
        if bytecode.is_file() and not bytecode.is_symlink():
            bytecode.unlink()


def _verify_hashes(
    root: Path, hashes: object, *, ignored: set[str] | None = None
) -> None:
    if not isinstance(hashes, dict):
        raise RuntimeError("artifact hashes are invalid")
    ignored = ignored or set()
    actual = {
        str(path.relative_to(root))
        for path in _artifact_files(root)
        if str(path.relative_to(root)) not in ignored
    }
    if actual != set(hashes):
        raise RuntimeError("artifact inventory is invalid")
    for relative, expected in hashes.items():
        path = root / relative
        if not isinstance(expected, str) or _sha(path) != expected:
            raise RuntimeError(f"artifact mismatch: {relative}")


def _verify_resume(root: Path, state_path: Path, policy_path: Path) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("policy") != str(policy_path) or state.get("policy_sha256") != _sha(
        policy_path
    ):
        raise RuntimeError("resume policy binding is invalid")
    inputs = root / "inputs"
    input_manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    _verify_hashes(inputs, input_manifest.get("hashes"), ignored={"manifest.json"})
    cells = state.get("cells")
    if not isinstance(cells, dict):
        raise RuntimeError("resume cell state is invalid")
    for cell_id, result in cells.items():
        if not isinstance(result, dict):
            raise RuntimeError(f"resume cell state is invalid: {cell_id}")
        if result.get("status") == "completed":
            _verify_hashes(root / "cells" / cell_id, result.get("hashes"))
    return state


def _project(policy: Path) -> Path:
    for parent in (policy.parent, *policy.parents):
        if (parent / "protocol").is_dir() and (parent / "corpus").is_dir():
            return parent
    return policy.parent


def _baseline(project: Path) -> Path:
    root = project / "protocol/ultimateinterview/baseline-89db971"
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise RuntimeError("vendored skill baseline manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("baseline") != "ultimateinterview-89db971":
        raise RuntimeError("vendored skill baseline identity is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("vendored skill baseline manifest is invalid")
    actual = {
        str(path.relative_to(root / "frozen"))
        for path in _artifact_files(root / "frozen")
    }
    actual.add("public-authority.json")
    authority_path = root / "public-authority.json"
    if authority_path.is_symlink():
        raise RuntimeError("vendored public authority must not be a symlink")
    if actual != set(files):
        raise RuntimeError("vendored skill baseline inventory is invalid")
    for relative, expected in files.items():
        path = (
            root / ("frozen" if relative != "public-authority.json" else "") / relative
        )
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"vendored skill baseline path is invalid: {relative}")
        if not path.is_file() or _sha(path) != expected:
            raise RuntimeError(f"vendored skill baseline mismatch: {relative}")
    return root


def _policy_selectors(
    policy_path: Path, enrollment_path: Path | None = None
) -> tuple[str, str, str, str]:
    """Read only executable/model and enrollment selectors; never inspect a version."""
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    codex = policy.get("codex", {})
    enrollment_path = enrollment_path or (
        _project(policy_path) / ".measurecontractdrift/live.toml"
    )
    import tomllib

    enrolled = tomllib.loads(enrollment_path.read_text(encoding="utf-8"))
    model = str(enrolled["model"])
    if model != "gpt-5.6-sol":
        raise RuntimeError("interview evaluation requires gpt-5.6-sol")
    return (
        str(codex["executable"]),
        model,
        str(enrolled["home_selector"]),
        str(enrolled["codex_home_selector"]),
    )


def _run(
    argv: list[str],
    cwd: Path,
    prompt: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ if env is None else env)
    environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    result = subprocess.run(
        argv,
        cwd=cwd,
        input=prompt,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr}"
        )
    return result


def _schema(path: Path, properties: dict[str, Any], required: list[str]) -> Path:
    _pretty(
        path,
        {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    )
    return path


def _output(result: subprocess.CompletedProcess[str], path: Path) -> dict[str, Any]:
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("Codex output must be a JSON object")
    return value


def _thread_id(stdout: str) -> str:
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started" and isinstance(
            event.get("thread_id"), str
        ):
            return event["thread_id"]
    raise RuntimeError("interviewer did not report a persistent thread id")


def _codex(
    executable: str,
    model: str,
    home: str,
    codex_home: str,
    argv: list[str],
    cwd: Path,
    prompt: str,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, HOME=home, CODEX_HOME=codex_home)
    command = [
        executable,
        *argv,
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--config",
        f'model="{model}"',
        "--config",
        'model_reasoning_effort="low"',
        "-",
    ]
    for attempt in range(3):
        try:
            return _run(command, cwd, prompt=prompt, env=environment)
        except RuntimeError as error:
            if "at capacity" not in str(error).lower() or attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _cell(
    root: Path, cell: dict[str, Any], selectors: tuple[str, str, str, str], frozen: Path
) -> dict[str, Any]:
    executable, model, home, codex_home = selectors
    cell_root = root / "cells" / cell["cell_id"]
    repo = cell_root / "repo"
    starter_root = repo / "starters" / cell["case_id"]
    if not starter_root.exists():
        starter_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cell["starter"], starter_root)
    session = repo / ".ultimateinterview" / cell["cell_id"]
    session.mkdir(parents=True, exist_ok=True)
    interview_skill = Path(cell["skill"]).read_text(encoding="utf-8")
    postmortem_skill = (
        frozen / ".agents/skills/ultimateinterview-postmortem/SKILL.md"
    ).read_text(encoding="utf-8")
    postmortem_template = (
        frozen
        / ".agents/skills/ultimateinterview-postmortem/references/postmortem-template.md"
    ).read_text(encoding="utf-8")
    scripts = frozen / ".agents/skills/ultimateinterview/scripts"
    json_contracts = (
        frozen / ".agents/skills/ultimateinterview/references/json-contracts.md"
    ).read_text(encoding="utf-8")
    authority_source = json.loads(
        (frozen.parent / "public-authority.json").read_text(encoding="utf-8")
    )
    authority_case = next(
        row for row in authority_source["cases"] if row["case_id"] == cell["case_id"]
    )
    owner_authority = next(
        row
        for row in authority_case["reconciliation"]["authorities"]
        if row["kind"] == "owner-decision"
    )
    if owner_authority["constraints"] != [cell["prompt"]]:
        raise RuntimeError("authority prompt binding is invalid")
    if starter_tree_digest(cell["starter"]) != authority_case["starter_digest"]:
        raise RuntimeError("authority starter binding is invalid")
    reconciliation_input = session / "authority-reconciliation.json"
    _pretty(reconciliation_input, authority_case["reconciliation"])
    authority = session / "authority-register.json"
    _run(
        [
            os.environ.get("PYTHON", "python"),
            str(scripts / "authority_reconcile.py"),
            str(reconciliation_input),
            "--output",
            str(authority),
        ],
        session,
    )
    authority_binding = {
        "path": str(authority.relative_to(repo)),
        "sha256": _sha(authority),
    }
    interview_schema = _schema(
        session / "interviewer-schema.json",
        {
            "complete": {"type": "boolean"},
            "question": {"type": "string"},
            "discovery_record": {"type": "string"},
        },
        ["complete", "question", "discovery_record"],
    )
    answer_schema = _schema(
        session / "simulator-schema.json",
        {"answer": {"type": "string"}},
        ["answer"],
    )
    final = session / "interviewer.json"
    prompt = (
        f"{interview_skill}\n\nTask:\n{cell['prompt']}\n"
        f"Authority reconciliation binding:\n{json.dumps(authority_binding)}\n"
        "Interview efficiently. Ask up to three independent material questions in one "
        "question string when possible. On completion return the exact native Discovery "
        "Record as JSON text in discovery_record.\n\n"
        f"Vendored JSON contracts:\n{json_contracts}"
    )
    first = _codex(
        executable,
        model,
        home,
        codex_home,
        [
            "exec",
            "--json",
            "--output-schema",
            str(interview_schema),
            "--output-last-message",
            str(final),
            "-C",
            str(session),
        ],
        session,
        prompt,
    )
    interview = _output(first, final)
    thread = _thread_id(first.stdout)
    turns = 0
    transcript: list[dict[str, str]] = []
    while not interview["complete"]:
        turns += 1
        if turns > 20:
            raise RuntimeError("interview did not complete")
        simulator_final = session / "simulator.json"
        simulator_prompt = (
            "Act as the user who requested the task below. Answer only from the task and "
            "the explicit interview history; make a concrete choice when the question asks "
            "for one. Do not inspect files or the interview skill.\n\n"
            f"Task:\n{cell['prompt']}\n\n"
            f"Prior interview:\n{json.dumps(transcript, ensure_ascii=False)}\n\n"
            f"Question:\n{interview['question']}"
        )
        simulator = _codex(
            executable,
            model,
            home,
            codex_home,
            [
                "exec",
                "--ephemeral",
                "--json",
                "--output-schema",
                str(answer_schema),
                "--output-last-message",
                str(simulator_final),
                "-C",
                str(session),
            ],
            session,
            simulator_prompt,
        )
        answer = _output(simulator, simulator_final)["answer"]
        transcript.append({"question": interview["question"], "answer": answer})
        _pretty(session / "transcript.json", transcript)
        resumed = _codex(
            executable,
            model,
            home,
            codex_home,
            [
                "exec",
                "resume",
                thread,
                "--json",
                "--output-schema",
                str(interview_schema),
                "--output-last-message",
                str(final),
            ],
            session,
            f"Simulator answer: {answer}\nContinue the interview and return the required JSON.",
        )
        interview = _output(resumed, final)
    discovery_text = interview["discovery_record"]
    if not isinstance(discovery_text, str):
        raise RuntimeError("completed interviewer output lacks a Discovery Record")
    try:
        discovery = json.loads(discovery_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("completed Discovery Record is not JSON") from error
    if not isinstance(discovery, dict):
        raise RuntimeError("completed Discovery Record is not an object")
    discovery_path = session / "discovery-record.json"
    contract = session / "build-contract.json"
    compiler_argv = [
        os.environ.get("PYTHON", "python"),
        str(scripts / "authority_compiler.py"),
        str(discovery_path),
        "--authority-register",
        str(authority),
        "--output",
        str(contract),
    ]
    for compiler_attempt in range(3):
        _pretty(discovery_path, discovery)
        try:
            _run(compiler_argv, session)
            break
        except RuntimeError as error:
            attempts = session / "attempts"
            attempts.mkdir(exist_ok=True)
            shutil.copy2(
                discovery_path,
                attempts / f"discovery-rejected-{compiler_attempt + 1}.json",
            )
            (attempts / f"discovery-rejected-{compiler_attempt + 1}.txt").write_text(
                str(error) + "\n", encoding="utf-8"
            )
            if compiler_attempt == 2:
                raise
            correction = _codex(
                executable,
                model,
                home,
                codex_home,
                [
                    "exec",
                    "resume",
                    thread,
                    "--json",
                    "--output-schema",
                    str(interview_schema),
                    "--output-last-message",
                    str(final),
                ],
                session,
                "The vendored authority compiler rejected the Discovery Record. "
                "Correct the record using the vendored JSON contract and return complete=true "
                f"with the full corrected JSON text.\n\nCompiler result:\n{error}",
            )
            corrected = _output(correction, final)
            if not corrected["complete"]:
                raise RuntimeError("interviewer did not complete compiler correction")
            try:
                discovery = json.loads(corrected["discovery_record"])
            except json.JSONDecodeError as parse_error:
                raise RuntimeError(
                    "corrected Discovery Record is not JSON"
                ) from parse_error
            if not isinstance(discovery, dict):
                raise RuntimeError("corrected Discovery Record is not an object")
    if not (repo / ".git").is_dir():
        _run(["git", "init", "--initial-branch=main", "."], repo)
        _run(["git", "config", "user.name", "DriftBench"], repo)
        _run(["git", "config", "user.email", "driftbench@invalid"], repo)
        _run(["git", "add", "--", "starters"], repo)
        _run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "--quiet",
                "-m",
                "baseline",
            ],
            repo,
        )
    else:
        _run(["git", "checkout", "--", "starters"], repo)
    implementation_return_path = session / "implementation-return.json"
    implementation_prompt = (
        f"The sealed Build Contract is {contract}. It was already produced by the vendored "
        "compiler and must not be recompiled or modified. "
        f"Implement it now by editing only {starter_root}. "
        "Run its verification commands. Your final response must be only the exact native "
        "Implementation Return JSON object from the vendored contract below, without Markdown "
        "fences or commentary. If an implementation decision needs authority not present in "
        "the contract, return blocked rather than changing controller-owned evidence. "
        "Do not inspect the parent project or any .agents directory.\n\n"
        f"Vendored JSON contracts:\n{json_contracts}"
    )
    _codex(
        executable,
        model,
        home,
        codex_home,
        [
            "exec",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            str(implementation_return_path),
            "-C",
            str(starter_root),
        ],
        starter_root,
        implementation_prompt,
    )
    try:
        implementation_return_document = json.loads(
            implementation_return_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise RuntimeError("implementation return is not JSON") from error
    _pretty(implementation_return_path, implementation_return_document)
    _remove_python_caches(starter_root)
    _run(
        [
            "git",
            "add",
            "--intent-to-add",
            "--",
            ".",
            ":(exclude).ultimateinterview",
        ],
        repo,
    )
    diff = _run(
        [
            "git",
            "diff",
            "--binary",
            "HEAD",
            "--",
            ".",
            ":(exclude).ultimateinterview",
        ],
        repo,
    ).stdout
    diff_file = session / "implementation.diff"
    diff_file.write_text(diff, encoding="utf-8")
    validator = "import importlib.util,json,sys; p=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(p);sys.modules['c']=m;p.loader.exec_module(m);m.validate_implementation_return(json.loads(open(sys.argv[2]).read()),json.loads(open(sys.argv[3]).read()))"
    _run(
        [
            os.environ.get("PYTHON", "python"),
            "-c",
            validator,
            str(scripts / "authority_compiler.py"),
            str(session / "implementation-return.json"),
            str(contract),
        ],
        repo,
    )
    implementation_return = json.loads(
        (session / "implementation-return.json").read_text(encoding="utf-8")
    )
    if implementation_return.get("status") != "implemented":
        raise RuntimeError(
            "implementation did not complete: "
            + "; ".join(implementation_return.get("blocked", []))
        )
    post_script = frozen / ".agents/skills/ultimateinterview-postmortem/scripts"
    pre_report_bundle = session / "compiler-evidence-bundle.pre-report.json"
    _run(
        [
            os.environ.get("PYTHON", "python"),
            str(post_script / "compiler_session_check.py"),
            str(session),
            "--repo-root",
            str(repo),
            "--diff-file",
            str(diff_file),
            "--output",
            str(pre_report_bundle),
        ],
        session,
    )
    pre_report_document = json.loads(pre_report_bundle.read_text(encoding="utf-8"))
    report_contract_digest = pre_report_document["contract_digest"]
    post_prompt = (
        f"{postmortem_skill}\n\nActive interview skill:\n{interview_skill}\n\n"
        f"Vendored JSON contracts:\n{json_contracts}\n\n"
        f"Required report template:\n{postmortem_template}\n\n"
        f"Session: {session}\nRepository: {repo}\n"
        f"Compiler evidence: {pre_report_bundle}\n"
        "The compiler evidence bundle was produced immediately before this turn by the "
        "vendored checker and is the authoritative prerequisite result. Do not rerun or "
        "compare a compiler or checker; the controller revalidates the session after the report. "
        "All required skill and contract text is included in this prompt. Do not inspect "
        "the parent repository, root .agents directory, or any non-cell skill installation. "
        "Return the complete report as your final response and begin it exactly with "
        "'# Ultimateinterview Postmortem'. The controller writes that response to postmortem.md. "
        f"The metadata line must be exactly 'contract_digest: {report_contract_digest}' "
        "with no backticks or trailing spaces. Derive each headline count mechanically "
        "from the Divergence Table so every row contributes to exactly one class. "
    )
    report_path = session / "postmortem.md"
    _codex(
        executable,
        model,
        home,
        codex_home,
        [
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(report_path),
            "-C",
            str(session),
        ],
        session,
        post_prompt,
    )
    _run(
        [
            os.environ.get("PYTHON", "python"),
            str(post_script / "compiler_session_check.py"),
            str(session),
            "--repo-root",
            str(repo),
            "--diff-file",
            str(diff_file),
            "--output",
            str(session / "compiler-evidence-bundle.json"),
        ],
        session,
    )
    report_argv = [
        os.environ.get("PYTHON", "python"),
        str(post_script / "postmortem_report_check.py"),
        str(report_path),
        "--bundle",
        str(session / "compiler-evidence-bundle.json"),
        "--lesson-store",
        "repo",
        "-",
        "-",
        "--lesson-store",
        "global",
        "-",
        "-",
    ]
    for report_attempt in range(5):
        try:
            _run(report_argv, session)
            break
        except RuntimeError as error:
            if report_attempt == 4:
                raise
            attempts = session / "attempts"
            attempts.mkdir(exist_ok=True)
            shutil.copy2(
                report_path,
                attempts / f"postmortem-rejected-{report_attempt + 1}.md",
            )
            (attempts / f"postmortem-rejected-{report_attempt + 1}.txt").write_text(
                str(error) + "\n", encoding="utf-8"
            )
            correction_prompt = (
                "The vendored postmortem report validator rejected the prior report. "
                "Read only compiler-evidence-bundle.json in this cell session and return a "
                "complete corrected report as your final response without changing any file. "
                "Do not inspect parent repositories or any skill installation. "
                f"\n\nValidator result:\n{error}"
                f"\n\nRequired template:\n{postmortem_template}\n"
                f"The metadata line must be exactly 'contract_digest: {report_contract_digest}' "
                "with no backticks or trailing spaces. Recalculate the Conclusion counts "
                "from the Divergence Table before returning the complete report. "
                "Retain exactly one table with the template's required header in every "
                "required section, including Finding Details when it has no data rows."
            )
            _codex(
                executable,
                model,
                home,
                codex_home,
                [
                    "exec",
                    "--ephemeral",
                    "--sandbox",
                    "read-only",
                    "--output-last-message",
                    str(report_path),
                    "-C",
                    str(session),
                ],
                session,
                correction_prompt,
            )
    files = _artifact_files(cell_root)
    return {
        "status": "completed",
        "session": str(session),
        "repo": str(repo),
        "hashes": {
            str(path.relative_to(cell_root)): _sha(path) for path in sorted(files)
        },
    }


def run(
    policy_path: Path,
    *,
    max_cells: int | None = None,
    max_parallel: int = 1,
    run_dir: Path | None = None,
) -> Path:
    policy_path = policy_path.resolve(strict=True)
    project = _project(policy_path)
    baseline = _baseline(project)
    frozen = baseline / "frozen"
    root = run_dir or project / ".measurecontractdrift/interview-eval" / (
        "live-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-interview-eval"
    )
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "state.json"
    is_resume = state_path.exists()
    inputs = root / "inputs"
    enrollment_input = inputs / "enrollment.toml"
    cases_input = inputs / "cases.json"
    starters_input = inputs / "starters"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    candidate_setting = policy.get("candidate_skill")
    if not isinstance(candidate_setting, str) or not candidate_setting.strip():
        raise RuntimeError("candidate_skill must be a nonempty relative path")
    candidate_relative = Path(candidate_setting)
    candidate_source = (policy_path.parent / candidate_relative).resolve()
    if candidate_relative.is_absolute() or not candidate_source.is_relative_to(
        project.parent
    ):
        raise RuntimeError("candidate_skill must stay inside the workspace")
    candidate_input = inputs / "candidate-SKILL.md"
    if not is_resume:
        if _artifact_files(root):
            raise RuntimeError("new run directory is not empty")
        inputs.mkdir(parents=True)
        enrollment_input.write_bytes(
            (project / ".measurecontractdrift/live.toml").read_bytes()
        )
        cases_input.write_bytes((project / "corpus/public/cases.json").read_bytes())
        corpus_source = json.loads(cases_input.read_text(encoding="utf-8"))["cases"]
        for row in corpus_source:
            shutil.copytree(
                project / "corpus/public" / row["starter_tree"],
                starters_input / row["case_id"],
            )
        candidate_source = candidate_source.resolve(strict=True)
        candidate_input.write_bytes(candidate_source.read_bytes())
        input_hashes = {
            str(path.relative_to(inputs)): _sha(path)
            for path in sorted(_artifact_files(inputs))
        }
        _pretty(inputs / "manifest.json", {"hashes": input_hashes})
    selectors = _policy_selectors(policy_path, enrollment_input)
    baseline_skill = frozen / ".agents/skills/ultimateinterview/SKILL.md"
    treatments = [("baseline", baseline_skill)]
    if not candidate_input.is_file():
        raise RuntimeError("candidate skill input is missing")
    treatments.append(("candidate", candidate_input))
    corpus = json.loads(cases_input.read_text(encoding="utf-8"))["cases"]
    cells = [
        {
            "cell_id": f"{row['case_id']}-{treatment}",
            "case_id": row["case_id"],
            "treatment": treatment,
            "skill": skill,
            "prompt": row["prompt"],
            "starter": starters_input / row["case_id"],
        }
        for row in corpus
        for treatment, skill in treatments
    ]
    state = (
        _verify_resume(root, state_path, policy_path)
        if is_resume
        else {
            "policy": str(policy_path),
            "policy_sha256": _sha(policy_path),
            "baseline_manifest_sha256": _sha(baseline / "manifest.json"),
            "cells": {row["cell_id"]: {"status": "pending"} for row in cells},
        }
    )
    if state.get("baseline_manifest_sha256") != _sha(baseline / "manifest.json"):
        raise RuntimeError("resume baseline binding is invalid")
    if not isinstance(state.get("cells"), dict) or set(state["cells"]) != {
        row["cell_id"] for row in cells
    }:
        raise RuntimeError("resume cell inventory is invalid")
    _pretty(state_path, state)

    def work(cell: dict[str, Any]) -> None:
        try:
            cell_root = root / "cells" / cell["cell_id"]
            if cell_root.exists():
                shutil.rmtree(cell_root)
            result = _cell(root, cell, selectors, frozen)
        except Exception as error:
            result = {"status": "failed", "error": str(error)}
        with _LOCK:
            state["cells"][cell["cell_id"]] = result
            _pretty(state_path, state)

    pending = [
        cell
        for cell in cells
        if state["cells"].get(cell["cell_id"], {}).get("status") != "completed"
    ]
    if max_cells is not None:
        pending = pending[:max_cells]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        list(pool.map(work, pending))
    _pretty(root / "state.json", state)
    statuses = [item["status"] for item in state["cells"].values()]
    receipt_status = (
        "failed"
        if "failed" in statuses
        else "completed"
        if all(status == "completed" for status in statuses)
        else "partial"
    )
    hashes = {
        str(path.relative_to(root)): _sha(path)
        for path in sorted(_artifact_files(root))
        if path.name not in {"manifest.json", "receipt.json"}
    }
    manifest_path = root / "manifest.json"
    _pretty(
        manifest_path,
        {"policy": str(policy_path), "cells": list(state["cells"]), "hashes": hashes},
    )
    _pretty(
        root / "receipt.json",
        {
            "status": receipt_status,
            "completed_cells": statuses.count("completed"),
            "total_cells": len(statuses),
            "manifest_sha256": _sha(manifest_path),
        },
    )
    return root


def resume(
    run_dir: Path, *, max_cells: int | None = None, max_parallel: int = 1
) -> Path:
    run_dir = run_dir.resolve(strict=True)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    return run(
        Path(state["policy"]),
        max_cells=max_cells,
        max_parallel=max_parallel,
        run_dir=run_dir,
    )
