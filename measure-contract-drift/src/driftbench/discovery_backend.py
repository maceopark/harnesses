"""Direct Codex backend for the generation-zero discovery experiment.

This module intentionally has no dependency on the retired evolution runtime.  The
coordinator owns scheduling and state; this backend owns one isolated model role at
a time and returns immutable artifacts/results to the coordinator.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import signal
import subprocess
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .discovery import (
    StructuredInterviewTurnV2,
    select_option,
    validate_turn_sequence,
)


RUNTIME_CONTRACT = """The runtime accepts StructuredInterviewTurn.v2. An ask turn contains
one or more independent decisions (six total maximum). Each decision has a stable decision_id,
question, 2-4 options with option_id, label, normative_statement and compatibility, exactly one
compatible recommendation, a rationale, and an impact boundary. At least two options are
compatible. A complete turn contains only a non-empty contract_draft. The runtime selects a
compatible answer and returns an owner-decision authority. Encode contract_draft as a JSON object
string on complete turns and use null on ask turns. The final draft must project every
selected authority and its normative statement exactly. Zero-question completion is valid."""


TURN_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "schema": {"type": "string", "const": "StructuredInterviewTurn.v2"},
        "action": {"type": "string", "enum": ["ask", "complete"]},
        "decisions": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "decision_id": {"type": "string"}, "question": {"type": "string"},
                "options": {"type": "array", "minItems": 2, "maxItems": 4, "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"option_id": {"type": "string"}, "label": {"type": "string"},
                        "normative_statement": {"type": "string"}, "compatible": {"type": "boolean"}},
                    "required": ["option_id", "label", "normative_statement", "compatible"]}},
                "recommended_option_id": {"type": "string"},
                "recommendation_rationale": {"type": "string"}, "impact_boundary": {"type": "string"}},
            "required": ["decision_id", "question", "options", "recommended_option_id",
                         "recommendation_rationale", "impact_boundary"]}},
        "contract_draft": {"type": ["string", "null"]},
    },
    "required": ["schema", "action", "decisions", "contract_draft"],
}


def _run_isolated(argv: Sequence[str], *, cwd: Path, input_text: str,
                  timeout: int) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


@dataclass(frozen=True)
class InvocationResult:
    value: dict[str, Any]
    tokens: int


@dataclass(frozen=True)
class CellBackendResult:
    material_decisions: int
    tokens: int
    wall_clock_ms: int
    postmortem_result: dict[str, Any]
    artifact_paths: tuple[str, ...]


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts
            and ".ultimateinterview" not in p.relative_to(root).parts}


def _diff(before: Mapping[str, bytes], after: Mapping[str, bytes]) -> str:
    result: list[str] = []
    for name in sorted(set(before) | set(after)):
        result.extend(difflib.unified_diff(
            before.get(name, b"").decode(errors="replace").splitlines(True),
            after.get(name, b"").decode(errors="replace").splitlines(True),
            f"a/{name}", f"b/{name}"))
    return "".join(result)


def _initialize_git_worktree(repo: Path) -> None:
    if (repo / ".git").is_dir():
        return
    commands = (
        ("git", "init", "--initial-branch=main", "."),
        ("git", "config", "user.name", "DriftBench"),
        ("git", "config", "user.email", "driftbench@invalid"),
        ("git", "add", "--", "."),
        ("git", "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "baseline"),
    )
    for command in commands:
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(f"cannot initialize cell worktree: {completed.stderr}")


def build_generator_prompt(seed_skill: str, runtime_contract: str = RUNTIME_CONTRACT) -> str:
    """Return the complete, deliberately narrow input for one independent generator."""
    return ("Create one free interview-skill variation. You receive only the seed and runtime "
            "contract below. Do not assume a corpus, rubric, evaluator, ranking, or existing skill. "
            "Return one non-empty SKILL.md of at most 8192 UTF-8 bytes.\n\nSEED:\n" + seed_skill
            + "\n\nRUNTIME CONTRACT:\n" + runtime_contract)


def build_evolution_prompt(parent_skill: str, train_feedback: Mapping[str, Any],
                           runtime_contract: str = RUNTIME_CONTRACT) -> str:
    """Build the complete mutation input without exposing validation details."""
    feedback = {
        "schema": train_feedback.get("schema"),
        "generation": train_feedback.get("generation"),
        "root_causes": train_feedback.get("root_causes"),
        "evidence": train_feedback.get("evidence"),
    }
    return (
        "Create one evolved interview skill. Improve the parent against the train-only feedback "
        "while preserving any useful behavior. The call is independent: do not assume candidate "
        "identity, rankings, validation findings, a corpus, evaluator internals, or other mutations. "
        "Keep the result compact: return one non-empty SKILL.md of at most 6144 UTF-8 bytes "
        "(the runtime hard limit is 8192 bytes).\n\nPARENT SKILL:\n"
        + parent_skill + "\n\nTRAIN-ONLY FEEDBACK:\n"
        + json.dumps(feedback, ensure_ascii=False, sort_keys=True)
        + "\n\nRUNTIME CONTRACT:\n" + runtime_contract
    )


def build_evaluator_prompt(*, request: str, transcript: Sequence[Mapping[str, Any]],
                           compiler_bundle: Mapping[str, Any], implementation_return: Mapping[str, Any],
                           implementation_diff: str, execution_evidence: Sequence[Mapping[str, Any]]) -> str:
    """Construct the blinded evaluator input from an explicit allowlist."""
    evidence = {"request": request, "transcript": list(transcript),
                "compiler_evidence_bundle": dict(compiler_bundle),
                "implementation_return": dict(implementation_return),
                "implementation_diff": implementation_diff,
                "direct_execution_evidence": list(execution_evidence)}
    return ("You are a fresh independent Ultimateinterview postmortem evaluator. Use schema 3 and "
            "the pinned template. Candidate identity, candidate skill, ranking, scoring formula, and "
            "implementer self-score are intentionally unavailable. Judge only direct evidence. "
            "Return the complete postmortem Markdown in `postmortem`.\n\nEVIDENCE:\n" +
            json.dumps(evidence, ensure_ascii=False, sort_keys=True))


def parse_postmortem_markdown(markdown: str) -> dict[str, Any]:
    """Deterministically extract schema-3 counts and finding classifications."""
    import re
    meta = dict(re.findall(r"^([a-z_]+):\s*(.+)$", markdown, re.MULTILINE))
    match = re.search(r"\*\*Counts:\*\*\s*(\d+) contract requirements\s*[—-]\s*"
        r"(\d+) fulfilled,\s*(\d+) escaped,\s*(\d+) scope-drift,\s*(\d+) divergent,\s*"
        r"(\d+) deferred,\s*(\d+) unverifiable\.", markdown)
    if meta.get("postmortem_schema") != "3" or not match:
        raise ValueError("postmortem is not a parseable schema 3 report")
    names = ("contract_requirements", "fulfilled", "escaped", "scope_drift", "divergent",
             "deferred", "unverifiable")
    counts = dict(zip(names, map(int, match.groups()), strict=True))
    if counts["contract_requirements"] != (counts["fulfilled"] + counts["scope_drift"] +
            counts["divergent"] + counts["deferred"] + counts["unverifiable"]):
        raise ValueError("postmortem requirement counts are inconsistent")
    findings = []
    for line in markdown.splitlines():
        if line.startswith("| REQ-") or line.startswith("| ESC-"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 6:
                findings.append({"id": cells[0], "class": cells[1], "root_cause": cells[4],
                                 "evidence": cells[3]})
    return {"schema": "DiscoveryPostmortemResult.v1", "contract_digest": meta.get("contract_digest"),
            "counts": counts, "findings": findings}


def verify_compiled_selection_lineage(
    selections: Sequence[Mapping[str, Any]], authority_register_value: Mapping[str, Any],
    build_contract: Mapping[str, Any],
) -> None:
    """Require every controller choice to survive register and contract compilation verbatim."""
    authorities = authority_register_value.get("authorities")
    requirements = build_contract.get("requirements")
    if not isinstance(authorities, list) or not isinstance(requirements, list):
        raise RuntimeError("compiled authority lineage is absent")
    for selection in selections:
        identity = selection.get("authority_id")
        statement = selection.get("normative_statement")
        register_matches = [row for row in authorities if isinstance(row, dict)
                            and row.get("id") == identity and row.get("statement") == statement]
        projected = [row for row in requirements if isinstance(row, dict)
                     and identity in row.get("authority_refs", []) and row.get("text") == statement]
        if len(register_matches) != 1 or len(projected) != 1:
            raise RuntimeError(f"dynamic authority lineage is invalid: {identity}")


_STABLE_SCOPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*\Z")


def normalize_compiler_inputs(
    reconciliation: Mapping[str, Any], discovery_record: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize representation-only compiler fields without adding new behavior."""
    left = json.loads(json.dumps(reconciliation))
    right = json.loads(json.dumps(discovery_record))

    def stable(value: str) -> str:
        if _STABLE_SCOPE.fullmatch(value):
            return value
        return "scope:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("source"), str):
                value["source"] = {"uri": value["source"], "version": "v1"}
            identity = value.get("id")
            classes = value.get("decision_classes")
            if isinstance(classes, list):
                value["decision_classes"] = [
                    item if item in {
                        "goal", "observable-behavior", "scope", "non-goals",
                        "actor-authorization-ownership", "retention-deletion-lifecycle",
                        "failure-retry-recovery", "irreversible-migration-data-loss",
                        "compatibility-floor", "numeric-quality-threshold",
                        "internal-architecture", "file-module-structure", "algorithm",
                        "test-organization",
                    } else (
                        "actor-authorization-ownership"
                        if isinstance(identity, str) and "APPROVAL" in identity.upper()
                        else "observable-behavior"
                    )
                    for item in classes
                ]
            decision_class = value.get("decision_class")
            if isinstance(decision_class, str) and decision_class not in {
                "goal", "observable-behavior", "scope", "non-goals",
                "actor-authorization-ownership", "retention-deletion-lifecycle",
                "failure-retry-recovery", "irreversible-migration-data-loss",
                "compatibility-floor", "numeric-quality-threshold",
                "internal-architecture", "file-module-structure", "algorithm",
                "test-organization",
            }:
                value["decision_class"] = "observable-behavior"
            scope = value.get("scope")
            if isinstance(scope, list) and all(isinstance(item, str) for item in scope):
                value["scope"] = [stable(item) for item in scope]
            if "statement" in value and isinstance(value.get("statement"), str):
                for field in ("constraints", "preserved_behaviors"):
                    if value.get(field) == []:
                        value[field] = [value["statement"]]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(left)
    walk(right)
    return left, right


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def build_compiler_inputs(*, request: str, case_id: str,
                          selections: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Project the request and controller choices into closed schema-3 inputs."""
    scope, request_id, approval_id = f"cli:{case_id}", f"REQUEST-{case_id}", f"OWNER-approval-{case_id}"

    def authority(identity: str, statement: str, source: str, classes: list[str]) -> dict[str, Any]:
        return {"id": identity, "kind": "owner-decision", "status": "active",
                "source": {"uri": source, "version": "1"}, "scope": [scope],
                "constraints": [statement], "preserved_behaviors": [statement],
                "decision_classes": classes, "statement": statement, "supersedes": [],
                "conflicts_with": [], "owner": "canonical-owner"}

    authorities = [authority(request_id, request, f"request:{case_id}",
                             ["goal", "scope", "observable-behavior"])]
    authorities += [authority(row["authority_id"], row["normative_statement"],
                              f"request:selection/{row['decision_id']}", ["observable-behavior"])
                    for row in selections]
    approval_statement = f"The canonical owner approves every authority for the {case_id} request."
    approval = authority(approval_id, approval_statement, "request:owner-approval",
                         ["actor-authorization-ownership"])
    approval["scope"] = ["contract:authority-register"]
    authorities.append(approval)
    reconciliation = {"schema": "ultimateinterview.authority-reconciliation-input.v1",
        "owner_approval": {"id": f"APPROVAL-{case_id}-v1", "owner": "canonical-owner",
            "source": {"uri": "request:owner-approval", "version": "1"},
            "statement": approval_statement, "approval_authority_ref": approval_id,
            "approved_authority_refs": [row["id"] for row in authorities],
            "approved_conflict_refs": []}, "authorities": authorities, "conflicts": [],
        "unresolved_decisions": []}

    clauses = [(request_id, request)] + [(row["authority_id"], row["normative_statement"])
                                         for row in selections]
    requirements, acceptances, verifications, trace, decisions = [], [], [], [], []
    for index, (authority_id, statement) in enumerate(clauses, 1):
        suffix = f"{index:03d}"
        req, acc, ver = f"REQ-{suffix}", f"ACC-{suffix}", f"VER-{suffix}"
        requirement = {"id": req, "text": statement, "decision_class": "observable-behavior",
            "scope": [scope], "constraints": [statement], "preserved_behaviors": [statement],
            "authority_refs": [authority_id], "evidence_refs": []}
        acceptance = {"id": acc, "requirement_ref": req,
            "precondition": f"The {case_id} command is invoked in the stated condition.",
            "input": "The command arguments and current repository state.",
            "action": "Run the requested CLI command.", "observable_result": statement,
            "failure_result": statement}
        requirement["acceptance_bindings"] = [{"acceptance_ref": acc,
            "digest": _canonical_digest({"domain": "ultimateinterview.acceptance-binding.v1",
                                           "requirement": dict(requirement), "acceptance": acceptance})}]
        requirements.append(requirement); acceptances.append(acceptance)
        verifications.append({"id": ver, "requirement_ref": req, "acceptance_refs": [acc],
            "method": "scenario", "procedure": f"Exercise {req} and inspect state, output, and exit code.",
            "expected_result": statement})
        trace.append({"authority_ref": authority_id, "requirement_ref": req,
                      "acceptance_ref": acc, "verification_ref": ver})
        decisions.append({"id": f"DEC-{suffix}", "statement": statement, "choice": "explicit",
            "authority_ref": authority_id, "requirement_ref": req, "applicable_boundary": [scope],
            "acceptance_refs": [acc], "verification_refs": [ver]})
    record = {"schema": "ultimateinterview.discovery-record.v1",
        "goal": {"text": request, "decision_class": "goal", "scope": [scope],
            "constraints": [request], "preserved_behaviors": [request],
            "authority_refs": [request_id], "evidence_refs": []},
        "scope": [{"id": "SCOPE-001", "text": request, "decision_class": "scope",
            "scope": [scope], "constraints": [request], "preserved_behaviors": [request],
            "authority_refs": [request_id], "evidence_refs": []}], "non_goals": [],
        "authorities": authorities, "authority_register_digest": "0" * 64, "evidence": [],
        "requirements": requirements, "acceptance_predicates": acceptances,
        "verifications": verifications, "trace": trace, "unresolved_decisions": [], "conflicts": []}
    manifest = json.dumps({"schema": "ultimateinterview.material-decisions.v2",
                           "decisions": decisions}, ensure_ascii=False, indent=2)
    execution = (f"# Execution Contract\n\n## Outcome\n\n{request}\n\n## Scope\n\n"
                 f"The authorized boundary is `{scope}`.\n\n## Decisions & Defaults\n"
                 f"```ultimateinterview-material-decisions\n{manifest}\n```\n\n## Acceptance\n\n"
                 "The sealed acceptance predicates and verifications are authoritative.\n")
    return reconciliation, record, execution


class DirectCodexDiscoveryBackend:
    """Standalone direct-Codex implementation of discovery backend operations."""

    def __init__(self, project: Path, workspace: Path, *, answer_seed: str,
                 codex: str = "codex", model: str | None = None, reasoning_effort: str | None = None,
                 event_sink: Callable[[str], None] | None = None) -> None:
        self.project, self.workspace, self.answer_seed = project.resolve(), workspace.resolve(), answer_seed
        self.codex, self.model, self.reasoning_effort = codex, model, reasoning_effort
        self.event_sink = event_sink or (lambda _message: None)
        self.protocol = self.project / "protocol/ultimateinterview/schema3-discovery"
        self._verify_protocol()

    def _verify_protocol(self) -> None:
        manifest = json.loads((self.protocol / "manifest.json").read_text(encoding="utf-8"))
        for relative, digest in manifest["files"].items():
            path = self.protocol / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"protocol snapshot drift: {relative}")

    def _invoke(self, role: str, cwd: Path, prompt: str, schema: Mapping[str, Any],
                *, writable: bool = False) -> InvocationResult:
        role_dir = self.workspace / "role-output" / role
        role_dir.mkdir(parents=True, exist_ok=True)
        schema_path, output_path = role_dir / "schema.json", role_dir / "output.json"
        _json(schema_path, schema)
        argv = [self.codex, "exec", "--ephemeral", "--json", "--sandbox",
                "workspace-write" if writable else "read-only", "--output-schema", str(schema_path),
                "--output-last-message", str(output_path), "-C", str(cwd)]
        if self.model: argv[2:2] = ["--model", self.model]
        if self.reasoning_effort: argv[2:2] = ["-c", f'model_reasoning_effort="{self.reasoning_effort}"']
        completed = _run_isolated(argv, cwd=cwd, input_text=prompt, timeout=900)
        if completed.returncode or not output_path.is_file():
            detail = (completed.stderr + "\n" + completed.stdout)[-6000:]
            raise RuntimeError(f"Codex {role} failed: {detail}")
        tokens = 0
        for line in completed.stdout.splitlines():
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            usage = event.get("usage", {}) if isinstance(event, dict) else {}
            tokens += sum(v for k, v in usage.items() if k in {"input_tokens", "output_tokens"}
                          and isinstance(v, int) and not isinstance(v, bool))
        value = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict): raise RuntimeError(f"Codex {role} output is not an object")
        return InvocationResult(value, tokens)

    def generate(self, *, seed_skill: str, runtime_digest: str) -> str:
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"SKILL.md": {"type": "string", "minLength": 1, "maxLength": 8192}},
                  "required": ["SKILL.md"]}
        empty = self.workspace / "generator-empty"
        empty.mkdir(parents=True, exist_ok=True)
        prompt = build_generator_prompt(seed_skill, RUNTIME_CONTRACT +
                                        f"\nPinned runtime digest: {runtime_digest}")
        role = "generator-" + hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        value = self._invoke(role, empty, prompt, schema).value["SKILL.md"]
        if not value.strip() or len(value.encode()) > 8192:
            raise RuntimeError("invalid generated skill")
        return value

    def evolve(self, *, parent_skill: str, train_feedback: Mapping[str, Any],
               runtime_digest: str) -> str:
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"SKILL.md": {"type": "string", "minLength": 1,
                                                "maxLength": 6144}},
                  "required": ["SKILL.md"]}
        empty = self.workspace / "generator-empty"
        empty.mkdir(parents=True, exist_ok=True)
        prompt = build_evolution_prompt(
            parent_skill, train_feedback,
            RUNTIME_CONTRACT + f"\nPinned runtime digest: {runtime_digest}",
        )
        role = "evolver-" + hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        value = self._invoke(role, empty, prompt, schema).value["SKILL.md"]
        if not value.strip() or len(value.encode()) > 8192:
            raise RuntimeError("invalid evolved skill")
        return value

    def interview(self, *, candidate_id: str, skill: str, case_id: str, request: str,
                  repetition: int, repository: Path, answer_seed: str,
                  pane: Any | None = None
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], int]:
        turns: list[StructuredInterviewTurnV2] = []
        selections: list[Any] = []
        tokens = 0
        while not turns or turns[-1].action != "complete":
            remaining = 6 - sum(len(turn.decisions) for turn in turns)
            history = [{"turn": t.model_dump(mode="json", by_alias=True)} for t in turns]
            history.extend({"selection": s.model_dump(mode="json")} for s in selections)
            prompt = (skill + "\n\n" + RUNTIME_CONTRACT + f"\n\nREQUEST:\n{request}\n\n"
                      f"HISTORY:\n{json.dumps(history, ensure_ascii=False)}\n"
                      f"Remaining decision budget: {remaining}. Inspect the repository and return the next turn.")
            invocation = self._invoke(
                                      f"interview-{candidate_id}-{case_id}-r{repetition}-t{len(turns)+1}", repository,
                                      prompt, TURN_SCHEMA)
            raw = dict(invocation.value)
            if raw.get("action") == "complete":
                try:
                    raw["contract_draft"] = json.loads(raw["contract_draft"])
                except (TypeError, json.JSONDecodeError) as error:
                    raise RuntimeError("interviewer contract draft is malformed JSON") from error
            turn = StructuredInterviewTurnV2.model_validate(raw)
            if len(turn.decisions) > remaining: raise RuntimeError("interview decision budget exceeded")
            turns.append(turn); tokens += invocation.tokens
            for decision in turn.decisions:
                selection = select_option(answer_seed, candidate_id, case_id, repetition, decision)
                selections.append(selection)
                self.event_sink(f"Question {decision.decision_id}: {decision.question}")
                self.event_sink("Options " + "; ".join(f"{o.option_id}={o.label}" for o in decision.options))
                self.event_sink(f"Recommended {decision.recommended_option_id}")
                self.event_sink(f"Selected answer {selection.option_id}: {selection.normative_statement}")
                if pane is not None:
                    pane.decision(
                        decision_id=decision.decision_id,
                        question=decision.question,
                        options=[f"{option.option_id}: {option.label}" for option in decision.options],
                        recommended=decision.recommended_option_id,
                        selected=f"{selection.option_id}: {selection.normative_statement}",
                    )
            if len(turns) > 7: raise RuntimeError("interview did not complete")
        validate_turn_sequence(turns)
        return ([t.model_dump(mode="json", by_alias=True) for t in turns],
                [s.model_dump(mode="json") for s in selections], turns[-1].contract_draft or {}, tokens)

    @staticmethod
    def evaluator_prompt(**kwargs: Any) -> str:
        return build_evaluator_prompt(**kwargs)

    @staticmethod
    def parse_postmortem(markdown: str) -> dict[str, Any]:
        return parse_postmortem_markdown(markdown)

    def _run(self, *argv: str, cwd: Path | None = None) -> None:
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError(f"validator failed ({Path(argv[1]).name}): {result.stderr[-2000:]}")

    def evaluate(self, *, cell: Any, prompt: str, skill: str, repo: Path,
                 attempt_dir: Path, answer_seed: str, pane: Any | None = None
                 ) -> Mapping[str, Any]:
        """Execute one closed interview→compiler→implementer→postmortem cell."""
        started = time.monotonic()
        _initialize_git_worktree(repo)
        tokens = 0
        transcript, selections, draft, interview_tokens = self.interview(
            candidate_id=cell.candidate_id, skill=skill, case_id=cell.case_id,
            request=prompt, repetition=cell.repetition, repository=repo,
            answer_seed=answer_seed, pane=pane)
        tokens += interview_tokens
        _json(attempt_dir / "transcript.json", {"schema": "DiscoveryTranscript.v1",
              "cell": cell.model_dump(mode="json"), "turns": transcript})
        _json(attempt_dir / "selections.json", {"schema": "DiscoverySelections.v1",
              "selections": selections})
        session = attempt_dir / ".ultimateinterview" / cell.cell_id
        session.mkdir(parents=True)
        skill_root = self.protocol / ".agents/skills/ultimateinterview"
        reconciliation, discovery_record, execution_contract = build_compiler_inputs(
            request=prompt, case_id=cell.case_id, selections=selections)
        _json(session / "authority-reconciliation.json", reconciliation)
        _json(session / "discovery-record.json", discovery_record)
        (session / "execution-contract.md").write_text(execution_contract, encoding="utf-8")
        python = os.environ.get("PYTHON", "python3")
        self._run(python, str(skill_root / "scripts/authority_reconcile.py"),
                  str(session / "authority-reconciliation.json"), "--output",
                  str(session / "authority-register.json"))
        reconciled_register = json.loads(
            (session / "authority-register.json").read_text(encoding="utf-8"))
        discovery_record["authority_register_digest"] = reconciled_register[
            "authority_register_digest"]
        _json(session / "discovery-record.json", discovery_record)
        self._run(python, str(skill_root / "scripts/authority_compiler.py"),
                  str(session / "discovery-record.json"), "--authority-register",
                  str(session / "authority-register.json"), "--output", str(session / "build-contract.json"))
        self._run(python, str(skill_root / "scripts/projection_check.py"),
                  str(session / "execution-contract.md"), "--discovery",
                  str(session / "discovery-record.json"), "--authority-register",
                  str(session / "authority-register.json"), "--build-contract",
                  str(session / "build-contract.json"))
        before = _tree(repo)
        build_contract = json.loads((session / "build-contract.json").read_text())
        authority_register_value = json.loads((session / "authority-register.json").read_text())
        verify_compiled_selection_lineage(selections, authority_register_value, build_contract)
        impl_schema = {"type": "object", "additionalProperties": False,
            "properties": {"status": {"type": "string"},
                "requirement_verification": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "status": {"type": "string"},
                        "evidence": {"type": "string"}},
                    "required": ["requirement_id", "status", "evidence"]}},
                "commands": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}}},
            "required": ["status", "requirement_verification", "commands", "notes"]}
        implementation = self._invoke(f"implement-{cell.cell_id}", repo,
            "You are a fresh implementer. You receive only the sealed Build Contract and repository. "
            "Implement every requirement, run direct verification, and do not expand authority. Write "
            "any permitted gap decisions to the contract-specified decision.jsonl before acting. Do not "
            "self-score. Return factual verification only.\n\nBUILD CONTRACT:\n" +
            json.dumps(build_contract, ensure_ascii=False), impl_schema, writable=True)
        tokens += implementation.tokens
        _json(session / "implementation-return.json", implementation.value)
        after = _tree(repo)
        diff = _diff(before, after)
        (attempt_dir / "implementation.diff").write_text(diff, encoding="utf-8")
        bundle = session / "compiler-evidence-bundle.json"
        post_root = self.protocol / ".agents/skills/ultimateinterview-postmortem"
        self._run(python, str(post_root / "scripts/compiler_session_check.py"), str(session),
                  "--diff-file", str(attempt_dir / "implementation.diff"), "--repo-root", str(repo),
                  "--output", str(bundle))
        compiler_bundle = json.loads(bundle.read_text())
        judge_schema = {"type": "object", "additionalProperties": False,
                        "properties": {"postmortem": {"type": "string", "minLength": 1}},
                        "required": ["postmortem"]}
        judge_prompt = build_evaluator_prompt(request=prompt, transcript=transcript,
            compiler_bundle=compiler_bundle, implementation_return=implementation.value,
            implementation_diff=diff, execution_evidence=implementation.value.get("requirement_verification", []))
        judge_prompt += (
            "\n\nDo not inspect files, invoke tools, or run any command. The controller already supplied "
            "the complete evidence and will run both pinned validators after your response. Return only "
            "the finished report in the required output field.\n" +
            "\n\nPINNED POSTMORTEM SKILL:\n" +
            (post_root / "SKILL.md").read_text(encoding="utf-8") +
            "\n\nPINNED REPORT TEMPLATE:\n" +
            (post_root / "references/postmortem-template.md").read_text(encoding="utf-8")
        )
        judge_workspace = self.workspace / "judge-empty"
        judge_workspace.mkdir(parents=True, exist_ok=True)
        judge = self._invoke(f"postmortem-{cell.cell_id}", judge_workspace,
                             judge_prompt, judge_schema)
        tokens += judge.tokens
        markdown = judge.value["postmortem"]
        (attempt_dir / "postmortem.md").write_text(markdown, encoding="utf-8")
        (session / "postmortem.md").write_text(markdown, encoding="utf-8")
        self._run(python, str(post_root / "scripts/postmortem_report_check.py"),
                  str(attempt_dir / "postmortem.md"), "--bundle", str(bundle))
        # Re-run compiler audit after the evaluator has written its report.
        self._run(python, str(post_root / "scripts/compiler_session_check.py"), str(session),
                  "--diff-file", str(attempt_dir / "implementation.diff"), "--repo-root", str(repo))
        parsed = parse_postmortem_markdown(markdown)
        counts = parsed["counts"]
        failure_rows = [row for row in parsed["findings"] if row["class"] != "fulfilled"]
        result = {**parsed, "fulfilled": counts["fulfilled"],
                  "contract_requirements": counts["contract_requirements"],
                  "escaped_requirements": counts["escaped"],
                  "material_decisions": len(selections), "tokens": tokens,
                  "authority_expansion": any(row["class"] == "scope-drift" for row in failure_rows),
                  "lineage_valid": True,
                  "failure_taxonomy": sorted({row["root_cause"] for row in failure_rows}),
                  "failure_evidence": [row["evidence"] for row in failure_rows],
                  "wall_clock_ms": int((time.monotonic() - started) * 1000)}
        _json(attempt_dir / "postmortem-result.json", result)
        return result


__all__ = ["CellBackendResult", "DirectCodexDiscoveryBackend", "RUNTIME_CONTRACT",
           "TURN_SCHEMA", "build_compiler_inputs", "build_evaluator_prompt", "build_generator_prompt",
           "build_evolution_prompt",
           "normalize_compiler_inputs", "parse_postmortem_markdown",
           "verify_compiled_selection_lineage"]
