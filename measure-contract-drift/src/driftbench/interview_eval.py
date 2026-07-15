"""Small direct-Codex interview evaluation runtime."""

from __future__ import annotations

import concurrent.futures
import difflib
import fcntl
import hashlib
import json
import os
import queue
import secrets
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .corpus import starter_tree_digest
from .evolution import (
    EvaluationRubric,
    EvolutionRunner,
    GeneratorContext,
    InterviewTurn,
    load_decision_log,
    load_study,
    submit_recommendations,
)
from .tmux_panes import TmuxPresentation

_LOCK = threading.Lock()
_STATE_SCHEMA = "DriftBenchInterviewEvalState.v2"
_SNAPSHOT = "frozen-312f1b3"
_REQUIRED_SESSION_ARTIFACTS = {
    "build-contract.json",
    "implementation-return.json",
    "postmortem.md",
}
_INHERITED_LOCK_FD: int | None = None


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


def _verify_resume(
    root: Path,
    state_path: Path,
    policy_path: Path,
    snapshot: Path,
    cell_ids: set[str],
) -> dict[str, Any]:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema") != _STATE_SCHEMA:
        raise RuntimeError("resume state schema is incompatible")
    if set(state) != {
        "schema",
        "policy",
        "policy_sha256",
        "frozen_manifest_sha256",
        "cells",
    }:
        raise RuntimeError("resume state fields are invalid")
    if state.get("policy") != str(policy_path) or state.get("policy_sha256") != _sha(
        policy_path
    ):
        raise RuntimeError("resume policy binding is invalid")
    if state.get("frozen_manifest_sha256") != _sha(snapshot / "manifest.json"):
        raise RuntimeError("resume frozen snapshot binding is invalid")
    inputs = root / "inputs"
    input_manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    _verify_hashes(inputs, input_manifest.get("hashes"), ignored={"manifest.json"})
    cells = state.get("cells")
    if not isinstance(cells, dict) or set(cells) != cell_ids:
        raise RuntimeError("resume cell inventory is invalid")
    for cell_id, result in cells.items():
        if not isinstance(result, dict):
            raise RuntimeError(f"resume cell state is invalid: {cell_id}")
        status = result.get("status")
        if status == "pending":
            if result != {"status": "pending"}:
                raise RuntimeError(f"resume pending cell state is invalid: {cell_id}")
        elif status == "failed":
            if set(result) != {"status", "error"} or not isinstance(
                result.get("error"), str
            ) or not result["error"]:
                raise RuntimeError(f"resume failed cell state is invalid: {cell_id}")
        elif status == "completed":
            if set(result) != {"status", "session", "repo", "hashes"}:
                raise RuntimeError(f"resume completed cell state is invalid: {cell_id}")
            cell_root = root / "cells" / cell_id
            expected_repo = (cell_root / "repo").resolve()
            expected_session = (
                expected_repo / ".ultimateinterview" / cell_id
            ).resolve()
            if result.get("repo") != str(expected_repo) or result.get("session") != str(
                expected_session
            ):
                raise RuntimeError(f"resume completed cell paths are invalid: {cell_id}")
            hashes = result.get("hashes")
            if not isinstance(hashes, dict) or not hashes:
                raise RuntimeError(f"resume completed cell hashes are invalid: {cell_id}")
            required = {
                str((expected_session / name).relative_to(cell_root))
                for name in _REQUIRED_SESSION_ARTIFACTS
            }
            if not required <= set(hashes):
                raise RuntimeError(f"resume completed cell evidence is incomplete: {cell_id}")
            _verify_hashes(cell_root, hashes)
        else:
            raise RuntimeError(f"resume cell status is invalid: {cell_id}")
    return state


def _project(policy: Path) -> Path:
    for parent in (policy.parent, *policy.parents):
        if (parent / "protocol").is_dir() and (parent / "corpus").is_dir():
            return parent
    return policy.parent


def _frozen_snapshot(project: Path) -> Path:
    root = project / "protocol/ultimateinterview" / _SNAPSHOT
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise RuntimeError("frozen snapshot manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("snapshot") != _SNAPSHOT:
        raise RuntimeError("frozen snapshot identity is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("frozen snapshot manifest is invalid")
    actual = {
        str(path.relative_to(root / "frozen"))
        for path in _artifact_files(root / "frozen")
    }
    actual.add("public-authority.json")
    authority_path = root / "public-authority.json"
    if authority_path.is_symlink():
        raise RuntimeError("vendored public authority must not be a symlink")
    if actual != set(files):
        raise RuntimeError("frozen snapshot inventory is invalid")
    for relative, expected in files.items():
        path = (
            root / ("frozen" if relative != "public-authority.json" else "") / relative
        )
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"frozen snapshot path is invalid: {relative}")
        if not path.is_file() or _sha(path) != expected:
            raise RuntimeError(f"frozen snapshot mismatch: {relative}")
    return root


def _validate_policy(policy_path: Path) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or set(policy) != {"codex"}:
        raise RuntimeError("live policy allows exactly the codex top-level field")
    codex = policy["codex"]
    if not isinstance(codex, dict) or set(codex) != {"executable"} or not isinstance(
        codex.get("executable"), str
    ) or not codex["executable"]:
        raise RuntimeError("live policy codex field is invalid")
    return policy


def _lock_path(root: Path) -> Path:
    resolved = root.resolve()
    digest = hashlib.sha256(str(resolved).encode()).hexdigest()
    lock_dir = resolved.parent / ".interview-eval-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"{digest}.lock"


class _RunLock:
    def __init__(self, root: Path) -> None:
        self.path = _lock_path(root)
        self.fd: int | None = None

    def __enter__(self) -> int:
        global _INHERITED_LOCK_FD
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.set_inheritable(fd, True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise RuntimeError("run is already owned by another process") from None
        self.fd = fd
        _INHERITED_LOCK_FD = fd
        return fd

    def __exit__(self, *args: object) -> None:
        global _INHERITED_LOCK_FD
        assert self.fd is not None
        _INHERITED_LOCK_FD = None
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def _policy_selectors(
    policy_path: Path, enrollment_path: Path | None = None
) -> tuple[str, str, str, str, str]:
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
    reasoning_effort = str(enrolled.get("model_reasoning_effort", "medium"))
    if reasoning_effort not in {"low", "medium", "high"}:
        raise RuntimeError("live model_reasoning_effort is invalid")
    return (
        str(codex["executable"]),
        model,
        reasoning_effort,
        str(enrolled["home_selector"]),
        str(enrolled["codex_home_selector"]),
    )


def _run(
    argv: list[str],
    cwd: Path,
    prompt: str | None = None,
    env: dict[str, str] | None = None,
    activity_line: Callable[[str], None] | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ if env is None else env)
    environment.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    if activity_line is None:
        try:
            result = subprocess.run(
                argv, cwd=cwd, input=prompt, text=True, capture_output=True,
                env=environment, check=False, timeout=timeout_seconds,
                pass_fds=(() if _INHERITED_LOCK_FD is None else (_INHERITED_LOCK_FD,)),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"command timed out after {timeout_seconds:g} seconds: {' '.join(argv)}"
            ) from error
    else:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
            pass_fds=(() if _INHERITED_LOCK_FD is None else (_INHERITED_LOCK_FD,)),
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        stdout: list[str] = []
        stderr: list[str] = []
        activity_events: queue.Queue[str | None] = queue.Queue(maxsize=64)

        def present_activity() -> None:
            while (line := activity_events.get()) is not None:
                try:
                    activity_line(line)
                except BaseException:
                    pass

        def read_stdout() -> None:
            for line in process.stdout:
                stdout.append(line)
                try:
                    activity_events.put_nowait(line)
                except queue.Full:
                    pass

        def read_stderr() -> None:
            stderr.extend(process.stderr)

        readers = [
            threading.Thread(target=read_stdout),
            threading.Thread(target=read_stderr),
        ]
        presenter = threading.Thread(target=present_activity, daemon=True)
        presenter.start()
        for reader in readers:
            reader.start()
        try:
            if prompt is not None:
                try:
                    process.stdin.write(prompt)
                except BrokenPipeError:
                    pass
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise RuntimeError(
                f"command timed out after {timeout_seconds:g} seconds: {' '.join(argv)}"
            ) from error
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
        finally:
            for reader in readers:
                reader.join()
            last_pending: str | None = None
            while True:
                try:
                    pending = activity_events.get_nowait()
                except queue.Empty:
                    break
                if pending is not None:
                    last_pending = pending
            if last_pending is not None:
                activity_events.put(last_pending)
            activity_events.put(None)
            presenter.join()
            process.stdout.close()
            process.stderr.close()
        result = subprocess.CompletedProcess(
            argv, returncode, "".join(stdout), "".join(stderr)
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
    reasoning_effort: str,
    home: str,
    codex_home: str,
    argv: list[str],
    cwd: Path,
    prompt: str,
    activity_line: Callable[[str], None] | None = None,
    timeout_seconds: float | None = None,
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
        f'model_reasoning_effort="{reasoning_effort}"',
        "-",
    ]
    for attempt in range(3):
        try:
            if activity_line is None:
                if timeout_seconds is None:
                    return _run(command, cwd, prompt=prompt, env=environment)
                return _run(command, cwd, prompt=prompt, env=environment,
                            timeout_seconds=timeout_seconds)
            if timeout_seconds is None:
                return _run(command, cwd, prompt=prompt, env=environment,
                            activity_line=activity_line)
            return _run(command, cwd, prompt=prompt, env=environment,
                        activity_line=activity_line, timeout_seconds=timeout_seconds)
        except RuntimeError as error:
            if "at capacity" not in str(error).lower() or attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _cell(
    root: Path,
    cell: dict[str, Any],
    selectors: tuple[str, str, str, str, str],
    frozen: Path,
    presentation: TmuxPresentation | None = None,
) -> dict[str, Any]:
    executable, model, reasoning_effort, home, codex_home = selectors
    pane = presentation.pane_for(cell) if presentation is not None else None
    if pane is not None:
        pane.create()
        pane.stage("Preparing")
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
    if pane is not None:
        pane.stage("Interview")
    activity_line = pane.activity_line if pane is not None else None
    try:
        first = _codex(
            executable,
            model,
            reasoning_effort,
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
            activity_line,
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
                reasoning_effort,
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
                activity_line,
            )
            answer = _output(simulator, simulator_final)["answer"]
            if pane is not None:
                pane.exchange(interview["question"], answer)
            transcript.append({"question": interview["question"], "answer": answer})
            _pretty(session / "transcript.json", transcript)
            resumed = _codex(
                executable,
                model,
                reasoning_effort,
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
                activity_line,
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
    except BaseException:
        raise
    if pane is not None:
        pane.stage("Contract")
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
                reasoning_effort,
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
                activity_line,
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
    if pane is not None:
        pane.stage("Implementation")
    _codex(
        executable,
        model,
        reasoning_effort,
        home,
        codex_home,
        [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            str(implementation_return_path),
            "-C",
            str(starter_root),
        ],
        starter_root,
        implementation_prompt,
        activity_line,
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
    if pane is not None:
        pane.stage("Checking")
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
    if pane is not None:
        pane.stage("Postmortem")
    _codex(
        executable,
        model,
        reasoning_effort,
        home,
        codex_home,
        [
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(report_path),
            "-C",
            str(session),
        ],
        session,
        post_prompt,
        activity_line,
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
            attempts = session / "attempts"
            attempts.mkdir(exist_ok=True)
            shutil.copy2(
                report_path,
                attempts / f"postmortem-rejected-{report_attempt + 1}.md",
            )
            (attempts / f"postmortem-rejected-{report_attempt + 1}.txt").write_text(
                str(error) + "\n", encoding="utf-8"
            )
            if report_attempt == 4:
                raise
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
                reasoning_effort,
                home,
                codex_home,
                [
                    "exec",
                    "--ephemeral",
                    "--json",
                    "--sandbox",
                    "read-only",
                    "--output-last-message",
                    str(report_path),
                    "-C",
                    str(session),
                ],
                session,
                correction_prompt,
                activity_line,
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


def _run_locked(
    policy_path: Path,
    *,
    max_cells: int | None = None,
    max_parallel: int = 1,
    run_dir: Path | None = None,
) -> Path:
    policy_path = policy_path.resolve(strict=True)
    project = _project(policy_path)
    snapshot = _frozen_snapshot(project)
    frozen = snapshot / "frozen"
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
    _validate_policy(policy_path)
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
        input_hashes = {
            str(path.relative_to(inputs)): _sha(path)
            for path in sorted(_artifact_files(inputs))
        }
        _pretty(inputs / "manifest.json", {"hashes": input_hashes})
    selectors = _policy_selectors(policy_path, enrollment_input)
    frozen_skill = frozen / ".agents/skills/ultimateinterview/SKILL.md"
    if is_resume:
        preliminary_state = json.loads(state_path.read_text(encoding="utf-8"))
        if preliminary_state.get("schema") != _STATE_SCHEMA:
            raise RuntimeError("resume state schema is incompatible")
        input_manifest = json.loads(
            (inputs / "manifest.json").read_text(encoding="utf-8")
        )
        _verify_hashes(inputs, input_manifest.get("hashes"), ignored={"manifest.json"})
    corpus = json.loads(cases_input.read_text(encoding="utf-8"))["cases"]
    cells = [
        {
            "cell_id": row["case_id"],
            "case_id": row["case_id"],
            "skill": frozen_skill,
            "prompt": row["prompt"],
            "starter": starters_input / row["case_id"],
        }
        for row in corpus
    ]
    if len(cells) != 6 or len({row["cell_id"] for row in cells}) != 6:
        raise RuntimeError("live evaluation requires exactly six public cases")
    cell_ids = {row["cell_id"] for row in cells}
    state = (
        _verify_resume(root, state_path, policy_path, snapshot, cell_ids)
        if is_resume
        else {
            "schema": _STATE_SCHEMA,
            "policy": str(policy_path),
            "policy_sha256": _sha(policy_path),
            "frozen_manifest_sha256": _sha(snapshot / "manifest.json"),
            "cells": {row["cell_id"]: {"status": "pending"} for row in cells},
        }
    )
    _pretty(state_path, state)

    pending = [
        cell
        for cell in cells
        if state["cells"].get(cell["cell_id"], {}).get("status") != "completed"
    ]
    if max_cells is not None:
        pending = pending[:max_cells]
    presentation = TmuxPresentation.detect(
        scheduled_cells=len(pending),
        max_parallel=max_parallel,
        run_id=root.name,
        attempt_id=secrets.token_hex(8),
    )

    def work(cell: dict[str, Any]) -> None:
        try:
            cell_root = root / "cells" / cell["cell_id"]
            if cell_root.exists():
                shutil.rmtree(cell_root)
            result = _cell(root, cell, selectors, frozen, presentation)
        except BaseException as error:
            if presentation is not None:
                presentation.cell_failed(cell, error)
            if not isinstance(error, Exception):
                raise
            result = {"status": "failed", "error": str(error)}
            with _LOCK:
                state["cells"][cell["cell_id"]] = result
                _pretty(state_path, state)
            return
        try:
            with _LOCK:
                state["cells"][cell["cell_id"]] = result
                _pretty(state_path, state)
        except BaseException as error:
            if presentation is not None:
                presentation.cell_failed(cell, error)
            raise
        if presentation is not None:
            presentation.cell_succeeded(cell)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel)
    try:
        list(pool.map(work, pending))
    except BaseException as error:
        if presentation is not None:
            presentation.invocation_failed(error)
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown()
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


def _legacy_run(
    policy_path: Path,
    *,
    max_cells: int | None = None,
    max_parallel: int = 1,
    run_dir: Path | None = None,
) -> Path:
    if max_cells is not None and not 1 <= max_cells <= 6:
        raise RuntimeError("max_cells must be between one and six")
    if not 1 <= max_parallel <= 6:
        raise RuntimeError("max_parallel must be between one and six")
    policy_path = policy_path.resolve(strict=True)
    _validate_policy(policy_path)
    project = _project(policy_path)
    root = (run_dir or project / ".measurecontractdrift/interview-eval" / (
        "live-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-interview-eval"
    )).resolve()
    with _RunLock(root):
        return _run_locked(
            policy_path,
            max_cells=max_cells,
            max_parallel=max_parallel,
            run_dir=root,
        )


def _legacy_resume(
    run_dir: Path, *, max_cells: int | None = None, max_parallel: int = 1
) -> Path:
    run_dir = run_dir.resolve(strict=True)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    if state.get("schema") != _STATE_SCHEMA:
        raise RuntimeError("resume state schema is incompatible")
    return _legacy_run(
        Path(state["policy"]),
        max_cells=max_cells,
        max_parallel=max_parallel,
        run_dir=run_dir,
    )


class DirectCodexEvolutionBackend:
    """Role-separated direct Codex adapter for :class:`EvolutionRunner`."""

    def __init__(self, study_path: Path, workspace: Path) -> None:
        self.study, _ = load_study(study_path)
        self.project = _project(study_path)
        policy = self.project / "configs/interview-eval.json"
        self.selectors = _policy_selectors(policy)
        if self.selectors[1] != self.study.model or self.selectors[2] != self.study.reasoning_effort:
            raise RuntimeError("study model settings do not match live enrollment")
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.judge_workspace = self.workspace / "judge-empty"
        self.total_tokens = 0

    @staticmethod
    def _usage_tokens(stdout: str) -> int:
        total = 0
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = event.get("usage") if isinstance(event, dict) else None
            if isinstance(usage, dict):
                for name in ("input_tokens", "output_tokens"):
                    value = usage.get(name)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        total += value
        return total

    def _invoke(self, name: str, cwd: Path, prompt: str,
                schema: dict[str, Any], *, writable: bool = False) -> dict[str, Any]:
        role = self.workspace / "role-output" / name
        role.mkdir(parents=True, exist_ok=True)
        schema_path = role / "schema.json"
        output_path = role / "output.json"
        _pretty(schema_path, schema)
        executable, model, effort, home, codex_home = self.selectors
        argv = ["exec", "--ephemeral", "--json", "--sandbox",
                "workspace-write" if writable else "read-only", "--output-schema",
                str(schema_path), "--output-last-message", str(output_path), "-C", str(cwd)]
        result = _codex(executable, model, effort, home, codex_home,
                        argv, cwd, prompt, timeout_seconds=300)
        self.total_tokens += self._usage_tokens(result.stdout)
        return _output(result, output_path)

    def make_rubric(self, case: Any, starter: Path) -> dict[str, Any]:
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "requirements": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "decision_points": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"decision_id": {"type": "string"},
                                   "description": {"type": "string"},
                                   "requires_recommendation_or_question": {"type": "boolean"}},
                    "required": ["decision_id", "description", "requires_recommendation_or_question"]}},
            }, "required": ["requirements", "decision_points"],
        }
        return self._invoke(
            f"rubric-{case.case_id}", starter,
            "You are the fixed independent rubric judge. Inspect only the original request "
            "and starter repository below. Enumerate observable requirements. For ambiguity, "
            "do not invent an answer; record a decision point requiring a grounded recommendation "
            f"or question. Original request:\n{case.prompt}", schema,
        )

    def generate(self, context: GeneratorContext, count: int) -> list[dict[str, str]]:
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {"candidates": {"type": "array", "minItems": count,
                "maxItems": count, "items": {"type": "object", "additionalProperties": False,
                    "properties": {"SKILL.md": {"type": "string"}}, "required": ["SKILL.md"]}}},
            "required": ["candidates"],
        }
        empty = self.workspace / "generator-empty"
        if empty.exists():
            shutil.rmtree(empty)
        empty.mkdir()
        prompt = (
            "Generate exactly the requested number of improved interview skill variants. "
            "Each candidate may contain only SKILL.md. You cannot inspect corpus, validation, "
            "final-test, compiler, checker, simulator, judge, or runtime files. Use at most three "
            "suggestions supplied here.\n\nParent SKILL.md:\n"
            f"{context.parent_skill}\n\nTrain failure taxonomy:\n"
            f"{json.dumps(context.train_failure_taxonomy)}\n\nImprovement suggestions:\n"
            f"{json.dumps(context.improvement_suggestions)}"
        )
        return list(self._invoke(f"generator-{secrets.token_hex(8)}", empty,
                                prompt, schema)["candidates"])

    @staticmethod
    def _tree_snapshot(root: Path) -> dict[str, bytes]:
        return {str(path.relative_to(root)): path.read_bytes() for path in _artifact_files(root)
                if ".driftbench" not in path.relative_to(root).parts}

    @staticmethod
    def _diff(before: dict[str, bytes], after: dict[str, bytes]) -> str:
        lines: list[str] = []
        for name in sorted(set(before) | set(after)):
            old = before.get(name, b"").decode("utf-8", errors="replace").splitlines(True)
            new = after.get(name, b"").decode("utf-8", errors="replace").splitlines(True)
            lines.extend(difflib.unified_diff(old, new, f"a/{name}", f"b/{name}"))
        return "".join(lines)

    def evaluate(self, *, candidate_id: str, skill: str, case: Any, starter: Path,
                 rubric: EvaluationRubric, repetition: int) -> dict[str, Any]:
        del candidate_id  # candidate identity is never sent to the judge
        started = time.monotonic()
        tokens_before = self.total_tokens
        decision_schema = {
            "type": "object", "additionalProperties": False,
            "properties": {"schema": {"type": "string", "const": "StructuredInterviewTurn.v1"},
                "decisions": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "decision_id": {"type": "string"}, "question": {"type": "string"},
                        "options": {"type": "array", "minItems": 2, "items": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"option_id": {"type": "string"}, "label": {"type": "string"},
                                           "compatible": {"type": "boolean"}},
                            "required": ["option_id", "label", "compatible"]}},
                        "recommended_option_id": {"type": "string"},
                        "preselected_option_id": {"type": "string"},
                        "recommendation_rationale": {"type": "string"},
                        "impact_boundary": {"type": "string"}},
                    "required": ["decision_id", "question", "options", "recommended_option_id",
                                 "preselected_option_id", "recommendation_rationale", "impact_boundary"]}}},
            "required": ["schema", "decisions"],
        }
        turn_raw = self._invoke(f"interview-{case.case_id}-r{repetition}", starter,
            f"{skill}\n\nInterview the request below. Return structured material decisions with one "
            "grounded compatible recommendation and matching preselection for every question. "
            f"Request:\n{case.prompt}", decision_schema)
        turn = InterviewTurn.model_validate(turn_raw)
        submission = submit_recommendations(turn)
        spec_schema = {"type": "object", "additionalProperties": False,
                       "properties": {"sealed_spec_json": {"type": "string"},
                                      "contract_references": {"type": "array", "items": {"type": "string"}}},
                       "required": ["sealed_spec_json", "contract_references"]}
        compiled = self._invoke(f"contract-{case.case_id}-r{repetition}", starter,
            "Compile a complete sealed implementation spec from the original request, structured "
            "interview decisions, and simulator selections. Do not add unstated behavior. Return "
            "the complete spec as JSON text in sealed_spec_json.\n"
            f"Request: {case.prompt}\nDecisions: {turn.model_dump_json(by_alias=True)}\n"
            f"Selections: {submission.model_dump_json(by_alias=True)}", spec_schema)
        try:
            sealed_spec = json.loads(compiled["sealed_spec_json"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("sealed implementation spec is not valid JSON") from error
        if not isinstance(sealed_spec, dict) or not sealed_spec:
            raise RuntimeError("sealed implementation spec must be a non-empty object")
        before = self._tree_snapshot(starter)
        evidence_dir = starter / ".driftbench"
        evidence_dir.mkdir()
        implementation_path = evidence_dir / "implementation-return.json"
        executable, model, effort, home, codex_home = self.selectors
        implementation_prompt = (
            "You are a fresh implementer. You receive only the sealed spec below, not the interview "
            "transcript or evaluator feedback. Implement it in this starter repository and run "
            "verification. Write newline-delimited ImplementationDecision.v1 objects to "
            ".driftbench/decision.jsonl; create an empty file if no implementation decision was "
            "needed. Every non-empty row must contain exactly these fields: "
            "schema=ImplementationDecision.v1, decision_id (string), decision (string), trigger "
            "(string), impact_scope (string), observable (boolean), reversible (boolean), "
            "contract_reference (string or null), rationale (string), alternatives_considered "
            "(array of strings), and affected_files (array of safe relative paths). Do not use "
            "`id`, `requirements`, or any additional field. Your final JSON must contain status, "
            "requirement_verification, and commands.\n\n"
            f"Sealed spec:\n{json.dumps(sealed_spec, ensure_ascii=False)}"
        )
        _codex(executable, model, effort, home, codex_home,
               ["exec", "--ephemeral", "--json", "--sandbox", "workspace-write",
                "--output-last-message", str(implementation_path), "-C", str(starter)],
               starter, implementation_prompt, timeout_seconds=300)
        decision_path = evidence_dir / "decision.jsonl"
        decisions = load_decision_log(decision_path)
        implementation_return = json.loads(implementation_path.read_text(encoding="utf-8"))
        if not isinstance(implementation_return, dict):
            raise RuntimeError("implementation return must be an object")
        after = self._tree_snapshot(starter)
        diff = self._diff(before, after)
        executions = self._independent_execution(case.case_id, starter)
        traceability_value = implementation_return.get("requirement_verification")
        traceability = isinstance(traceability_value, (dict, list)) and bool(traceability_value)
        verification_valid = bool(executions) and all(
            row.get("valid_observation") is True
            and row.get("outcome_valid") is True
            for row in executions
        )
        checks = {
            "schema_valid": True, "digest_valid": True, "lineage_valid": True,
            "changed_path_scope_valid": all(not path.startswith("../") for path in after),
            "traceability_valid": traceability,
            "verification_executed": verification_valid, "decision_log_complete": True,
            "critical_governance_failure": False,
        }
        blinded = {
            "request": case.prompt,
            "rubric": rubric.model_dump(mode="json", by_alias=True),
            "structured_decisions": turn.model_dump(mode="json", by_alias=True),
            "sealed_spec": sealed_spec, "code_diff": diff,
            "independent_execution": executions,
            "decision_log": [row.model_dump(mode="json", by_alias=True) for row in decisions],
        }
        judge_schema = {"type": "object", "additionalProperties": False,
            "properties": {**{name: {"type": "number", "minimum": 0, "maximum": 1}
                                for name in ("contract_coverage", "recommendation_integrity",
                                             "implementation_conformance", "verification_credibility",
                                             "decision_governance")},
                "unlogged_material_decision_ids": {"type": "array", "items": {"type": "string"}},
                "safety_or_authority_expansion": {"type": "boolean"}},
            "required": ["contract_coverage", "recommendation_integrity",
                         "implementation_conformance", "verification_credibility",
                         "decision_governance", "unlogged_material_decision_ids",
                         "safety_or_authority_expansion"]}
        self.judge_workspace.mkdir(exist_ok=True)
        judge = self._invoke(f"judge-{case.case_id}-r{repetition}", self.judge_workspace,
            "Act as the fixed independent blinded judge. Score only the supplied evidence; candidate "
            "identity and any implementer self-score are absent. Identify unlogged material behavior.\n"
            f"{json.dumps(blinded, ensure_ascii=False)}", judge_schema)
        return {"checks": checks, "judge": judge,
                "material_decisions": len(turn.decisions),
                "tokens": self.total_tokens - tokens_before,
                "wall_clock_ms": int((time.monotonic() - started) * 1000),
                "evidence": {"implementation_return": implementation_return,
                    "diff": diff, "executions": executions,
                    "decisions": [row.model_dump(mode="json", by_alias=True) for row in decisions]}}

    @staticmethod
    def _independent_execution(case_id: str, starter: Path) -> list[dict[str, Any]]:
        commands = {
            "bookmarks": (["bookmark", "tag", "bm-1", "reading"],
                          ["bookmark", "tag", "missing", "reading"]),
            "config-merge": (["config", "merge", "team"],
                             ["config", "merge", "missing"]),
            "contacts-csv": (["contacts", "import", "incoming.csv"],
                             ["contacts", "import", "missing.csv"]),
            "expense": (["expense", "add", "9", "tea"],
                        ["expense", "add", "-1", "tea"]),
            "reminder": (["reminder", "add", "Call Ada", "Monday"],
                         ["reminder", "add", "Call Ada", ""]),
            "todo": (["todo", "complete", "todo-1"],
                     ["todo", "complete", "missing"]),
            "inventory-transfer": (["inventory", "transfer", "widget", "east", "west", "2"],
                                   ["inventory", "transfer", "widget", "east", "west", "999"]),
            "feature-flags": (["flag", "set", "dev", "dark_mode", "true"],
                              ["flag", "set", "missing", "dark_mode", "true"]),
            "order-cancel": (["order", "cancel", "ord-1", "duplicate"],
                             ["order", "cancel", "ord-2", "late"]),
            "playlist-reorder": (["playlist", "move", "track-3", "1"],
                                 ["playlist", "move", "missing", "1"]),
            "access-grant": (["access", "grant", "ada", "editor"],
                             ["access", "grant", "missing", "editor"]),
            "appointment-reschedule": (["appointment", "reschedule", "appt-1", "Tuesday"],
                                       ["appointment", "reschedule", "missing", "Tuesday"]),
        }
        if case_id not in commands:
            raise RuntimeError(f"independent execution is undefined: {case_id}")
        results = []
        for index, argv in enumerate(commands[case_id]):
            copy = starter.parent / f"independent-{index}"
            shutil.copytree(starter, copy, ignore=shutil.ignore_patterns(".driftbench"))
            state_files = [path for path in copy.glob("*.json")]
            before = {path.name: path.read_bytes() for path in state_files}
            completed = subprocess.run(
                [os.environ.get("PYTHON", "python"), "cli.py", *argv], cwd=copy,
                text=True, capture_output=True, check=False,
            )
            after = {path.name: path.read_bytes() for path in state_files}
            try:
                observation = json.loads(completed.stdout)
            except json.JSONDecodeError:
                observation = None
            valid_observation = (
                isinstance(observation, dict)
                and observation.get("schema") == "StarterObservation.v1"
                and observation.get("exit_code") == completed.returncode
                and isinstance(observation.get("state_sha256"), str)
                and any(
                    hashlib.sha256(payload).hexdigest() == observation["state_sha256"]
                    for payload in after.values()
                )
                and completed.stderr == ""
            )
            outcome_valid = (
                completed.returncode == 0
                and before != after
                and isinstance(observation, dict)
                and observation.get("status") == "completed"
                and observation.get("changed") is True
                if index == 0
                else completed.returncode != 0
                and before == after
                and isinstance(observation, dict)
                and observation.get("changed") is False
            )
            results.append({"argv": argv, "stdout": completed.stdout,
                            "returncode": completed.returncode,
                            "expected_success": index == 0,
                            "valid_observation": valid_observation,
                            "outcome_valid": outcome_valid,
                            "state_changed": before != after,
                            "state_byte_identical": before == after})
        return results


def run(study_path: Path, *, run_dir: Path | None = None,
        max_generations: int | None = None, max_candidates: int | None = None,
        smoke: bool = False, backend: Any | None = None, **legacy_limits: Any) -> Path:
    """Run a new evolution study; old codex-only policies remain explicitly incompatible."""

    study_path = study_path.resolve(strict=True)
    raw = json.loads(study_path.read_text(encoding="utf-8"))
    if set(raw) == {"codex"}:  # compatibility for callers of the removed v2 surface
        return _legacy_run(study_path, run_dir=run_dir, **legacy_limits)
    project = _project(study_path)
    root = (run_dir or project / ".measurecontractdrift/interview-eval" / (
        "live-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-evolution"
    )).resolve()
    with _RunLock(root):
        adapter = backend or DirectCodexEvolutionBackend(study_path, root)
        return EvolutionRunner(study_path, root, adapter).run(
            maximum_generations=max_generations, maximum_candidates=max_candidates,
            smoke=smoke)


def resume(run_dir: Path, *, backend: Any | None = None,
           max_generations: int | None = None,
           max_candidates: int | None = None, smoke: bool = False,
           **legacy_limits: Any) -> Path:
    run_dir = run_dir.resolve(strict=True)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    if state.get("schema") == _STATE_SCHEMA:
        return _legacy_resume(run_dir, **legacy_limits)
    if state.get("schema") != "DriftBenchEvolutionState.v1":
        raise RuntimeError("resume state schema is incompatible")
    study_path = Path(state["study_path"])
    smoke = smoke or state.get("mode") == "train-smoke"
    adapter = backend or DirectCodexEvolutionBackend(study_path, run_dir)
    with _RunLock(run_dir):
        return EvolutionRunner(study_path, run_dir, adapter).run(
            maximum_generations=max_generations, maximum_candidates=max_candidates,
            smoke=smoke)
