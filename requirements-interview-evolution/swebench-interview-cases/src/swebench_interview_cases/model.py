"""Ephemeral structured Codex transport fixed to the Build Contract model."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from jsonschema import validate

from . import MODEL_ID, MODEL_REASONING_EFFORT


class ModelError(RuntimeError):
    pass


IMPLEMENTATION_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "tests", "completed"],
    "properties": {
        "summary": {"type": "string"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "result"],
                "properties": {
                    "command": {"type": "string"},
                    "result": {"type": "string"},
                },
            },
        },
        "completed": {"type": "boolean"},
    },
}


class CodexJsonModel:
    def __init__(self, record_root: Path, timeout_seconds: int = 900) -> None:
        self.record_root = record_root
        self.timeout_seconds = timeout_seconds
        self.sequence = 0

    def generate(
        self, *, role: str, instructions: str, payload: Mapping[str, Any], schema: dict[str, Any],
        readable_directories: tuple[Path, ...] = (),
    ) -> dict[str, Any]:
        self.sequence += 1
        self.record_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"swebench-{role}-") as temporary:
            root = Path(temporary)
            schema_path = root / "schema.json"
            output_path = root / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            prompt = (
                f"{instructions}\nReturn only the JSON required by the supplied schema.\n"
                f"INPUT:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            )
            command = [
                "codex", "exec", "--model", MODEL_ID,
                "-c", f'model_reasoning_effort="{MODEL_REASONING_EFFORT}"',
                "--ephemeral", "--sandbox", "read-only",
                "--skip-git-repo-check", "--ignore-user-config", "--color", "never",
                "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                "-C", str(root), "-",
            ]
            for directory in readable_directories:
                command[-1:-1] = ["--add-dir", str(directory.resolve())]
            completed = subprocess.run(
                command, input=prompt, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.timeout_seconds, check=False,
            )
            record = {
                "role": role, "model": MODEL_ID,
                "model_reasoning_effort": MODEL_REASONING_EFFORT,
                "command": command[:-1] + ["<stdin>"],
                "prompt": prompt, "input": payload, "exit_code": completed.returncode,
                "stdout": completed.stdout, "stderr": completed.stderr,
            }
            record_path = self.record_root / f"{self.sequence:03d}-{role}.json"
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            if completed.returncode != 0:
                raise ModelError(f"{role} failed: {completed.stderr[-2000:]}")
            if not output_path.is_file():
                raise ModelError(f"{role} produced no structured output")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            validate(result, schema)
            return result


class CodexWorkspaceImplementer:
    """Run a fresh implementation agent in one isolated writable checkout."""

    def __init__(self, record_path: Path, timeout_seconds: int = 1800) -> None:
        self.record_path = record_path
        self.timeout_seconds = timeout_seconds

    def implement(
        self, *, repository: Path, public_request: str,
        audited_evidence: Mapping[str, Any], contract: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="swebench-implementer-schema-") as temporary:
            root = Path(temporary)
            schema_path = root / "schema.json"
            output_path = root / "output.json"
            schema_path.write_text(
                json.dumps(IMPLEMENTATION_RESULT_SCHEMA), encoding="utf-8",
            )
            prompt = (
                "You are the fresh implementation agent. Implement the supplied public request in the "
                "current repository, treating the supplied contract as authoritative and the audited "
                "repository evidence as known context. Inspect the repository as needed. Do not access "
                "or infer any gold patch, hidden tests, owner oracle, or files outside this checkout.\n\n"
                "Before making ANY autonomous implementation decision, append exactly "
                "one JSON object as one line to decision.jsonl in the repository root. This includes technical "
                "choices even when every reasonable option remains within the contract and has no user-visible "
                "effect. Each object must contain non-empty strings "
                "for timestamp, gap, reason, observable_impact, and reversibility; a non-empty string array "
                "options_considered with at least two entries; and a non-empty string choice. Log before "
                "acting. Logging is mandatory evidence, not an admission that the contract is defective. Do "
                "not use the log to override the contract. If no autonomous choice is made, do not create the file.\n\n"
                "Make the smallest complete implementation, run focused tests, and return only the JSON "
                "required by the supplied output schema.\n\n"
                f"PUBLIC REQUEST:\n{public_request}\n\n"
                f"AUDITED EVIDENCE:\n{json.dumps(audited_evidence, ensure_ascii=False, sort_keys=True)}\n\n"
                f"CONTRACT:\n{json.dumps(contract, ensure_ascii=False, sort_keys=True)}"
            )
            command = [
                "codex", "exec", "--model", MODEL_ID,
                "-c", f'model_reasoning_effort="{MODEL_REASONING_EFFORT}"', "--ephemeral",
                "--sandbox", "workspace-write", "--skip-git-repo-check",
                "--ignore-user-config", "--color", "never",
                "--output-schema", str(schema_path),
                "--output-last-message", str(output_path),
                "-C", str(repository.resolve()), "-",
            ]
            completed = subprocess.run(
                command, input=prompt, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.timeout_seconds, check=False,
            )
            record = {
                "role": "fresh-implementer", "model": MODEL_ID,
                "model_reasoning_effort": MODEL_REASONING_EFFORT,
                "command": command[:-1] + ["<stdin>"], "prompt": prompt,
                "exit_code": completed.returncode, "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
            self.record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            if completed.returncode != 0:
                raise ModelError(f"fresh-implementer failed: {completed.stderr[-2000:]}")
            if not output_path.is_file():
                raise ModelError("fresh-implementer produced no structured output")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            validate(result, IMPLEMENTATION_RESULT_SCHEMA)
            return result
