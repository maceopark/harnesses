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
import selectors
import shutil
import subprocess
import threading
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .discovery import (
    OwnerCard, OwnerExchange, StructuredInterviewTurnV2,
    discovery_result, selection_from_owner_exchange,
    validate_turn_sequence,
)


_ACTIVE_MODEL_GROUPS: set[int] = set()
_ACTIVE_MODEL_GROUPS_LOCK = threading.Lock()
_MODEL_SHUTTING_DOWN = threading.Event()


def terminate_active_model_processes() -> None:
    """Stop every isolated model process group owned by this coordinator."""
    _MODEL_SHUTTING_DOWN.set()
    with _ACTIVE_MODEL_GROUPS_LOCK:
        groups = tuple(_ACTIVE_MODEL_GROUPS)
    for process_group in groups:
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass


RUNTIME_CONTRACT = """The runtime accepts StructuredInterviewTurn.v2. An ask turn contains
one or more independent decisions (six total maximum). Each decision has a stable decision_id,
question, 2-4 options with option_id, label, normative_statement and compatibility, exactly one
compatible recommendation, a rationale, and an impact boundary. At least two options are
compatible. A complete turn contains only a non-empty contract_draft. The controller asks an
independent owner responder whether a decision uniquely reaches sealed owner authority. Encode contract_draft as a JSON object
string on complete turns and use null on ask turns. The final draft must project every
selected authority and its normative statement exactly. Zero-question completion is valid."""

MUTATION_BOUNDARY = """The candidate SKILL.md is only a mutable discovery overlay. It may govern
repository grounding, identification of material decisions, question ordering, grouping,
recommendations, and interview termination. It must not define or alter authority kinds, contract
schemas, decision-to-requirement projection, reconciliation, compilation, implementation planning,
or postmortem rules. Those surfaces are fixed runtime infrastructure and are not mutation targets."""


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

OWNER_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"exchanges": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "decision_id": {"type": "string"},
            "verdict": {"type": "string", "enum": ["matched", "irrelevant", "ambiguous", "not-specified"]},
            "item_id": {"type": ["string", "null"]},
            "option_id": {"type": ["string", "null"]},
            "answer": {"type": "string"}},
        "required": ["decision_id", "verdict", "item_id", "option_id", "answer"]}}},
    "required": ["exchanges"],
}


def unique_cell_decision_ids(
    raw: Mapping[str, Any], *, used_ids: set[str], turn_number: int,
) -> dict[str, Any]:
    """Deterministically repair model-local IDs that collide with an earlier turn."""
    normalized = dict(raw)
    decisions = []
    allocated = set(used_ids)
    for index, value in enumerate(raw.get("decisions", ())):
        decision = dict(value)
        identity = str(decision.get("decision_id", ""))
        if identity in allocated:
            identity = f"DEC-T{turn_number:02d}-{index + 1:02d}"
            suffix = 1
            while identity in allocated:
                suffix += 1
                identity = f"DEC-T{turn_number:02d}-{index + 1:02d}-{suffix}"
            decision["decision_id"] = identity
        allocated.add(identity)
        decisions.append(decision)
    normalized["decisions"] = decisions
    return normalized


def parse_contract_draft(value: Any) -> dict[str, Any]:
    """Parse one JSON object, tolerating only duplicated trailing closing braces."""
    if not isinstance(value, str):
        raise RuntimeError("interviewer contract draft is not a JSON string")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        try:
            parsed, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError:
            raise RuntimeError("interviewer contract draft is malformed JSON") from error
        trailing = value[end:].strip()
        if not trailing or set(trailing) != {"}"}:
            raise RuntimeError("interviewer contract draft is malformed JSON") from error
    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError("interviewer contract draft must be a non-empty JSON object")
    return parsed


def suppress_duplicate_owner_authority(
    exchanges: Sequence[OwnerExchange], resolved_item_ids: set[str],
) -> list[OwnerExchange]:
    """Grant each sealed Owner Card item at most once across and within turns."""
    seen = set(resolved_item_ids)
    normalized: list[OwnerExchange] = []
    for exchange in exchanges:
        duplicate = exchange.verdict == "matched" and exchange.item_id in seen
        if duplicate:
            exchange = exchange.model_copy(update={
                "verdict": "irrelevant",
                "item_id": None,
                "option_id": None,
                "answer": "This owner authority was already resolved by another decision.",
            })
        elif exchange.verdict == "matched" and exchange.item_id is not None:
            seen.add(exchange.item_id)
        normalized.append(exchange)
    return normalized


def _run_isolated(argv: Sequence[str], *, cwd: Path, input_text: str,
                  timeout: int, on_stdout_line: Callable[[str], None] | None = None
                  ) -> subprocess.CompletedProcess[str]:
    if _MODEL_SHUTTING_DOWN.is_set():
        raise RuntimeError("model invocation refused during coordinator shutdown")
    process = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    with _ACTIVE_MODEL_GROUPS_LOCK:
        _ACTIVE_MODEL_GROUPS.add(process.pid)
    if on_stdout_line is None:
        try:
            stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
            raise
        finally:
            with _ACTIVE_MODEL_GROUPS_LOCK:
                _ACTIVE_MODEL_GROUPS.discard(process.pid)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    process.stdin.write(input_text)
    process.stdin.close()
    streams = selectors.DefaultSelector()
    streams.register(process.stdout, selectors.EVENT_READ, "stdout")
    streams.register(process.stderr, selectors.EVENT_READ, "stderr")
    captured: dict[str, list[str]] = {"stdout": [], "stderr": []}
    deadline = time.monotonic() + timeout
    try:
        while streams.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            for key, _ in streams.select(min(remaining, 1.0)):
                line = key.fileobj.readline()
                if line:
                    captured[key.data].append(line)
                    if key.data == "stdout" and on_stdout_line is not None:
                        on_stdout_line(line)
                else:
                    streams.unregister(key.fileobj)
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    finally:
        streams.close()
        with _ACTIVE_MODEL_GROUPS_LOCK:
            _ACTIVE_MODEL_GROUPS.discard(process.pid)
    return subprocess.CompletedProcess(
        argv, process.returncode, "".join(captured["stdout"]), "".join(captured["stderr"])
    )


def _tool_summary(line: str) -> str | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or event.get("type") not in {"item.started", "item.completed"}:
        return None
    item = event.get("item")
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if event["type"] == "item.started":
        if kind == "command_execution":
            command = str(item.get("command", "")).splitlines()
            return "command: " + (command[0][:240] if command else "[empty]")
        if kind == "mcp_tool_call":
            return f"MCP {item.get('server', '?')}.{item.get('tool', '?')}"
        if kind == "web_search":
            query = str(item.get("query", "")).splitlines()
            return "web search: " + (query[0][:240] if query else "[empty]")
        if kind == "collab_tool_call":
            return "collab: " + str(item.get("tool", "unknown"))
    if event["type"] == "item.completed" and kind == "file_change":
        changes = item.get("changes", [])
        return f"file change: {len(changes) if isinstance(changes, list) else '?'} path(s)"
    return None


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
    return ("Create one free interview-strategy variation. You receive only the seed and runtime "
            "contract below. Do not assume a corpus, rubric, evaluator, ranking, or existing skill. "
            "Vary only the mutable discovery overlay. Do not add or alter contract compilation, "
            "projection, authority, planning, or postmortem instructions. "
            "Return only one non-empty discovery overlay of at most 8192 UTF-8 bytes. Do not repeat "
            "or edit the seed; the controller composes the seed with this one overlay.\n\nSEED:\n"
            + seed_skill
            + "\n\nMUTATION BOUNDARY:\n" + MUTATION_BOUNDARY
            + "\n\nRUNTIME CONTRACT:\n" + runtime_contract)


def build_evolution_prompt(seed_skill: str, parent_overlay: str,
                           train_feedback: Mapping[str, Any],
                           mutation_intent: Mapping[str, Any],
                           runtime_contract: str = RUNTIME_CONTRACT) -> str:
    """Build the complete mutation input without exposing validation details."""
    feedback = {
        "schema": train_feedback.get("schema"),
        "generation": train_feedback.get("generation"),
        "root_causes": train_feedback.get("root_causes"),
        "evidence": train_feedback.get("evidence"),
    }
    return (
        "Edit the parent discovery overlay into one complete evolved overlay. Preserve useful "
        "behavior, but freely add, remove, replace, reorder, or simplify overlay instructions when "
        "the train-only feedback supports it. The returned overlay replaces the parent overlay; it "
        "is not a delta to append. The call is independent: do not assume candidate "
        "identity, rankings, validation findings, a corpus, evaluator internals, or other mutations. "
        "The bound mutation operator is normative: return a changed complete overlay; "
        "train feedback is evidence, not permission to alter the runtime contract. "
        "Apply the mutation only to the mutable discovery overlay. Ignore feedback that would "
        "require changing contract compilation, projection, authority, planning, or postmortem "
        "behavior because those surfaces are fixed runtime infrastructure. "
        "Do not repeat or edit the immutable seed. Keep the result compact: return only one non-empty "
        "complete discovery overlay of at most 6144 UTF-8 bytes (the runtime hard limit is 8192 bytes)."
        "\n\nIMMUTABLE SEED:\n" + seed_skill
        + "\n\nEDITABLE PARENT OVERLAY:\n" + (parent_overlay or "[empty overlay]")
        + "\n\nTRAIN-ONLY FEEDBACK:\n"
        + json.dumps(feedback, ensure_ascii=False, sort_keys=True)
        + "\n\nBOUND MUTATION INTENT:\n"
        + json.dumps(dict(mutation_intent), ensure_ascii=False, sort_keys=True)
        + "\n\nMUTATION BOUNDARY:\n" + MUTATION_BOUNDARY
        + "\n\nRUNTIME CONTRACT:\n" + runtime_contract
    )


def _fixed_contract_surface(skill_text: str, contracts_text: str) -> str:
    start = skill_text.find("## 5. Small Execution Contract")
    end = skill_text.find("## 7. Implementation Planning")
    if start < 0 or end <= start:
        raise RuntimeError("pinned Ultimateinterview contract surface is malformed")
    return skill_text[start:end].strip() + "\n\n" + contracts_text.strip()


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


def interview_blockers(contract_draft: Mapping[str, Any],
                       owner_result: Mapping[str, Any]) -> tuple[str, ...]:
    """Return material reasons why implementation has no complete owner authority."""
    blockers: list[str] = []
    status = contract_draft.get("status")
    if status == "incomplete":
        blockers.append("contract-draft-status:incomplete")
    elif status not in (None, "complete"):
        blockers.append(f"contract-draft-status:{status}")
    unresolved = contract_draft.get("unresolved_material_decisions", [])
    if not isinstance(unresolved, list):
        blockers.append("unresolved-material-decisions:malformed")
    else:
        blockers.extend(f"unresolved-material-decision:{item}" for item in unresolved
                        if isinstance(item, str) and item.strip())
    applicable = set(map(str, owner_result.get("applicable_item_ids", ())))
    resolved = set(map(str, owner_result.get("resolved_item_ids", ())))
    blockers.extend(f"unresolved-owner-item:{item}" for item in sorted(applicable - resolved))
    blockers.extend(f"ambiguous-owner-decision:{item}" for item in
                    map(str, owner_result.get("ambiguous_decision_ids", ())))
    return tuple(dict.fromkeys(blockers))


def build_implementation_prompt(build_contract: Mapping[str, Any],
                                decision_log_path: str) -> str:
    return (
        "You are a fresh implementer. You receive only the sealed Build Contract and repository. "
        "Before editing, determine whether every required observable behavior is authorized. If any "
        "user-visible, policy, scope, lifecycle, failure, compatibility, data-loss, ownership, or "
        "out-of-delegation decision is still required, do not modify the repository: return status "
        "blocked-contract-gap and list each gap in contract_gaps. A decision log cannot authorize "
        "such a gap. Otherwise implement every requirement and run direct verification. Only a truly "
        "internal arbitrary choice covered by an active bounded implementation delegation may be "
        f"written before acting to the exact path {decision_log_path}. Return status completed with "
        "an empty contract_gaps array. Do not self-score; return factual verification only."
        "\n\nBUILD CONTRACT:\n" + json.dumps(dict(build_contract), ensure_ascii=False)
    )


def validate_implementation_outcome(*, implementation: Mapping[str, Any],
                                    implementation_diff: str,
                                    decisions: Sequence[Mapping[str, Any]],
                                    build_contract: Mapping[str, Any]) -> bool:
    """Validate the implementer's authority claim; return True when safely blocked."""
    status = implementation.get("status")
    gaps = implementation.get("contract_gaps")
    if not isinstance(gaps, list) or any(not isinstance(gap, str) or not gap.strip()
                                         for gap in gaps):
        raise RuntimeError("implementer contract_gaps must be a string array")
    if status == "blocked-contract-gap":
        if not gaps:
            raise RuntimeError("blocked implementation must identify at least one contract gap")
        if implementation_diff.strip():
            raise RuntimeError("blocked implementation modified the repository")
    elif status == "completed":
        if gaps:
            raise RuntimeError("completed implementation reported unresolved contract gaps")
    else:
        raise RuntimeError("implementer returned an invalid status")
    delegations = build_contract.get("bounded_implementation_delegations")
    if decisions and (not isinstance(delegations, list) or not delegations):
        raise RuntimeError("decision log requires an active bounded implementation delegation")
    for decision in decisions:
        if decision.get("observable_impact") not in {"none", "none beyond the Build Contract"}:
            raise RuntimeError("decision log contains observable behavior outside the Build Contract")
    return status == "blocked-contract-gap"


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
                              f"owner-card:{case_id}/{row['authority_id']}", ["observable-behavior"])
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

    def __init__(self, project: Path, workspace: Path, *,
                 codex: str = "codex", model: str | None = None, reasoning_effort: str | None = None,
                 event_sink: Callable[[str], None] | None = None,
                 runtime_digest: str | None = None) -> None:
        self.project, self.workspace = project.resolve(), workspace.resolve()
        self.codex, self.model, self.reasoning_effort = codex, model, reasoning_effort
        self.event_sink = event_sink or (lambda _message: None)
        self.protocol = self.project / "protocol/ultimateinterview/schema3-discovery"
        protocol_digest = self._verify_protocol()
        if runtime_digest is not None and runtime_digest != protocol_digest:
            raise RuntimeError("discovery runtime digest does not bind the pinned protocol")
        skill_root = self.protocol / ".agents/skills/ultimateinterview"
        self.contract_surface = _fixed_contract_surface(
            (skill_root / "SKILL.md").read_text(encoding="utf-8"),
            (skill_root / "references/json-contracts.md").read_text(encoding="utf-8"),
        )

    def _verify_protocol(self) -> str:
        manifest = json.loads((self.protocol / "manifest.json").read_text(encoding="utf-8"))
        for relative, digest in manifest["files"].items():
            path = self.protocol / relative
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"protocol snapshot drift: {relative}")
        return hashlib.sha256((self.protocol / "manifest.json").read_bytes()).hexdigest()

    def _invoke(self, role: str, cwd: Path, prompt: str, schema: Mapping[str, Any],
                *, writable: bool = False, pane: Any | None = None,
                role_label: str | None = None) -> InvocationResult:
        role_dir = self.workspace / "role-output" / role
        role_dir.mkdir(parents=True, exist_ok=True)
        schema_path, output_path = role_dir / "schema.json", role_dir / "output.json"
        _json(schema_path, schema)
        argv = [self.codex, "exec", "--ephemeral", "--json", "--sandbox",
                "workspace-write" if writable else "read-only", "--output-schema", str(schema_path),
                "--output-last-message", str(output_path), "-C", str(cwd)]
        if self.model: argv[2:2] = ["--model", self.model]
        if self.reasoning_effort: argv[2:2] = ["-c", f'model_reasoning_effort="{self.reasoning_effort}"']
        if pane is not None and role_label is not None:
            pane.role(role_label)
        def monitor(line: str) -> None:
            summary = _tool_summary(line)
            if summary is not None and pane is not None:
                pane.tool_call(summary)
        completed: subprocess.CompletedProcess[str] | None = None
        for capacity_attempt in range(1, 4):
            output_path.unlink(missing_ok=True)
            completed = _run_isolated(
                argv, cwd=cwd, input_text=prompt, timeout=900,
                on_stdout_line=monitor if pane is not None else None,
            )
            detail = completed.stderr + "\n" + completed.stdout
            at_capacity = "selected model is at capacity" in detail.lower()
            if not completed.returncode or not at_capacity or capacity_attempt == 3:
                break
            delay = 4 * capacity_attempt + int(hashlib.sha256(role.encode()).hexdigest()[:2], 16) % 4
            if pane is not None:
                pane.tool_call(
                    f"model capacity; retry {capacity_attempt + 1}/3 after {delay}s"
                )
            time.sleep(delay)
        assert completed is not None
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
                  "properties": {"overlay.md": {"type": "string", "minLength": 1, "maxLength": 8192}},
                  "required": ["overlay.md"]}
        empty = self.workspace / "generator-empty"
        empty.mkdir(parents=True, exist_ok=True)
        prompt = build_generator_prompt(seed_skill, RUNTIME_CONTRACT +
                                        f"\nPinned runtime digest: {runtime_digest}")
        role = "generator-" + hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        value = self._invoke(role, empty, prompt, schema).value["overlay.md"]
        if not value.strip() or len(value.encode()) > 8192:
            raise RuntimeError("invalid generated skill")
        return value

    def evolve(self, *, seed_skill: str, parent_overlay: str,
               train_feedback: Mapping[str, Any],
               mutation_intent: Mapping[str, Any], runtime_digest: str) -> str:
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"overlay.md": {"type": "string", "minLength": 1,
                                                "maxLength": 6144}},
                  "required": ["overlay.md"]}
        empty = self.workspace / "generator-empty"
        empty.mkdir(parents=True, exist_ok=True)
        prompt = build_evolution_prompt(
            seed_skill, parent_overlay, train_feedback, mutation_intent,
            RUNTIME_CONTRACT + f"\nPinned runtime digest: {runtime_digest}",
        )
        role = "evolver-" + hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        value = self._invoke(role, empty, prompt, schema).value["overlay.md"]
        if not value.strip() or len(value.encode()) > 8192:
            raise RuntimeError("invalid evolved skill")
        return value

    def summarize_skill_change(self, *, parent_skill: str, candidate_skill: str,
                               mutation_intent: Mapping[str, Any]) -> Mapping[str, str]:
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {
                      "parent_summary": {"type": "string", "minLength": 1, "maxLength": 400},
                      "candidate_summary": {"type": "string", "minLength": 1, "maxLength": 400},
                      "change_summary": {"type": "string", "minLength": 1, "maxLength": 500}},
                  "required": ["parent_summary", "candidate_summary", "change_summary"]}
        empty = self.workspace / "report-empty"
        empty.mkdir(parents=True, exist_ok=True)
        prompt = (
            "Summarize this interview-skill evolution for a human comparison report. "
            "Use plain, concrete language. Explain the operating strategy, not formatting trivia. "
            "The change summary must say what the candidate added, removed, reordered, compressed, "
            "or made stricter relative to the parent. Do not score either skill and do not infer "
            "behavior absent from the text. Return only the requested JSON.\n\n"
            "MUTATION INTENT:\n" + json.dumps(dict(mutation_intent), ensure_ascii=False,
                                                sort_keys=True)
            + "\n\nPARENT SKILL:\n" + parent_skill
            + "\n\nCANDIDATE SKILL:\n" + candidate_skill)
        role = "skill-summary-" + hashlib.sha256(os.urandom(32)).hexdigest()[:16]
        value = self._invoke(role, empty, prompt, schema).value
        return {key: str(value[key]) for key in (
            "parent_summary", "candidate_summary", "change_summary")}

    def _resolve_owner(self, *, card: OwnerCard, decisions: Sequence[Any],
                       resolved_item_ids: set[str], cell_id: str, turn_number: int,
                       pane: Any | None = None) -> tuple[list[OwnerExchange], int]:
        """Controller-only semantic authority resolver; it never sees a candidate ID or skill."""
        prompt = (
            "You are an independent owner responder. Map each supplied decision to at most one "
            "sealed owner-card item only when exactly one offered compatible option expresses that "
            "item's owner statement. Answer every question consistently from the complete Markdown "
            "world model, including its facts, vocabulary, priorities, and explicit unknowns. "
            "Do not infer authority from a merely related question. "
            "Items listed under ALREADY RESOLVED ITEMS must never be matched again; return "
            "irrelevant with null item_id and option_id for a decision that only repeats one of "
            "those items. "
            "Use irrelevant when it does not address a card item; not-specified when the card cannot "
            "answer it; ambiguous when more than one mapping is plausible. Never disclose unrelated "
            "card items. Matched answers must use the card statement concisely.\n\nSEALED OWNER CARD:\n"
            + card.source_markdown + "\n\nMACHINE-READABLE AUTHORITY ITEMS:\n"
            + json.dumps([item.model_dump(mode="json") for item in card.items], ensure_ascii=False)
            + "\n\nALREADY RESOLVED ITEMS:\n"
            + json.dumps(sorted(resolved_item_ids)) + "\n\nDECISIONS:\n"
            + json.dumps([decision.model_dump(mode="json") for decision in decisions], ensure_ascii=False)
        )
        empty = self.workspace / "owner-responder-empty"
        empty.mkdir(parents=True, exist_ok=True)
        invocation = self._invoke(f"owner-{cell_id}-t{turn_number}", empty, prompt,
                                  OWNER_RESPONSE_SCHEMA, pane=pane, role_label="Owner")
        exchanges = [OwnerExchange.model_validate(row) for row in invocation.value["exchanges"]]
        expected = {decision.decision_id for decision in decisions}
        if {row.decision_id for row in exchanges} != expected:
            raise RuntimeError("owner responder must return exactly one exchange per decision")
        exchanges = suppress_duplicate_owner_authority(exchanges, resolved_item_ids)
        return exchanges, invocation.tokens

    def interview(self, *, candidate_id: str, skill: str, case_id: str, request: str,
                  repetition: int, repository: Path, owner_card: OwnerCard,
                  pane: Any | None = None
                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], int]:
        turns: list[StructuredInterviewTurnV2] = []
        selections: list[Any] = []
        exchanges: list[OwnerExchange] = []
        tokens = 0
        while not turns or turns[-1].action != "complete":
            remaining = 6 - sum(len(turn.decisions) for turn in turns)
            history = [{"turn": t.model_dump(mode="json", by_alias=True)} for t in turns]
            history.extend({"owner_exchange": s.model_dump(mode="json")} for s in exchanges)
            prompt = ("DISCOVERY POLICY (seed plus controller-owned overlay):\n" + skill + "\n\n" + MUTATION_BOUNDARY
                      + "\n\nFIXED ULTIMATEINTERVIEW CONTRACT SURFACE (governs on conflict):\n"
                      + self.contract_surface + "\n\n" + RUNTIME_CONTRACT
                      + f"\n\nREQUEST:\n{request}\n\n"
                      f"HISTORY:\n{json.dumps(history, ensure_ascii=False)}\n"
                      f"Previously used decision IDs: "
                      f"{json.dumps([decision.decision_id for turn in turns for decision in turn.decisions])}. "
                      "Never reuse any previous decision_id; allocate a new ID for every new decision. "
                      "On completion, contract_draft must contain exactly one valid JSON object string "
                      "with no characters or extra closing braces after that object. "
                      f"Remaining decision budget: {remaining}. Inspect the repository and return the next turn.")
            invocation = self._invoke(
                                      f"interview-{candidate_id}-{case_id}-r{repetition}-t{len(turns)+1}", repository,
                                      prompt, TURN_SCHEMA, pane=pane, role_label="Q&A")
            raw = unique_cell_decision_ids(
                invocation.value,
                used_ids={decision.decision_id for prior in turns for decision in prior.decisions},
                turn_number=len(turns) + 1,
            )
            if raw.get("action") == "complete":
                raw["contract_draft"] = parse_contract_draft(raw["contract_draft"])
            turn = StructuredInterviewTurnV2.model_validate(raw)
            if len(turn.decisions) > remaining: raise RuntimeError("interview decision budget exceeded")
            turns.append(turn); tokens += invocation.tokens
            if pane is not None:
                for decision in turn.decisions:
                    pane.question(
                        decision_id=decision.decision_id,
                        question=decision.question,
                        options=[f"{option.option_id}: {option.label}" for option in decision.options],
                        recommended=decision.recommended_option_id,
                    )
            if turn.decisions:
                turn_exchanges, owner_tokens = self._resolve_owner(
                    card=owner_card, decisions=turn.decisions,
                    resolved_item_ids={row.item_id for row in exchanges if row.item_id is not None},
                    cell_id=f"{candidate_id}-{case_id}-r{repetition}", turn_number=len(turns), pane=pane)
                tokens += owner_tokens
            else:
                turn_exchanges = []
            for decision, exchange in zip(turn.decisions, turn_exchanges):
                exchanges.append(exchange)
                selection = selection_from_owner_exchange(owner_card, decision, exchange)
                if selection is not None:
                    selections.append(selection)
                self.event_sink(f"Question {decision.decision_id}: {decision.question}")
                self.event_sink("Options " + "; ".join(f"{o.option_id}={o.label}" for o in decision.options))
                self.event_sink(f"Recommended {decision.recommended_option_id}")
                self.event_sink(f"Owner {exchange.verdict}: {exchange.answer}")
                if pane is not None:
                    pane.answer(
                        decision_id=decision.decision_id,
                        selected=f"{exchange.verdict}: {exchange.answer}",
                    )
            if len(turns) > 7: raise RuntimeError("interview did not complete")
        validate_turn_sequence(turns)
        return ([t.model_dump(mode="json", by_alias=True) for t in turns],
                [s.model_dump(mode="json") for s in selections],
                [s.model_dump(mode="json") for s in exchanges],
                turns[-1].contract_draft or {}, tokens)

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

    @staticmethod
    def _blocked_result(*, attempt_dir: Path, session: Path, marker_name: str,
                        reasons: Sequence[str], owner_result: Mapping[str, Any],
                        transcript: Sequence[Mapping[str, Any]],
                        selections: Sequence[Mapping[str, Any]], tokens: int,
                        started: float, contract_requirements: int = 0,
                        details: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        marker = {
            "schema": "DiscoveryImplementationBlock.v1",
            "stage": marker_name.removesuffix("-blocked.json"),
            "reasons": list(reasons),
            "details": dict(details or {}),
        }
        _json(attempt_dir / marker_name, marker)
        _json(session / marker_name, marker)
        return {
            "fulfilled": 0,
            "contract_requirements": contract_requirements,
            "escaped_requirements": 0,
            "material_decisions": len(selections),
            "tokens": tokens,
            "question_turns": len(transcript),
            "discovery_success": False,
            "hard_veto": True,
            "critical_misses": list(owner_result.get("critical_miss_ids", ())),
            "authority_expansion": False,
            "lineage_valid": True,
            "failure_taxonomy": [marker_name.removesuffix("-blocked.json") + "-blocked"],
            "failure_evidence": list(reasons),
            "wall_clock_ms": int((time.monotonic() - started) * 1000),
        }

    def evaluate(self, *, cell: Any, prompt: str, skill: str, repo: Path,
                 attempt_dir: Path, owner_card: OwnerCard, pane: Any | None = None
                 ) -> Mapping[str, Any]:
        """Execute one closed interview→compiler→implementer→postmortem cell."""
        started = time.monotonic()
        _initialize_git_worktree(repo)
        tokens = 0
        transcript, selections, exchanges, draft, interview_tokens = self.interview(
            candidate_id=cell.candidate_id, skill=skill, case_id=cell.case_id,
            request=prompt, repetition=cell.repetition, repository=repo,
            owner_card=owner_card, pane=pane)
        tokens += interview_tokens
        _json(attempt_dir / "transcript.json", {"schema": "DiscoveryTranscript.v1",
              "cell": cell.model_dump(mode="json"), "turns": transcript})
        _json(attempt_dir / "selections.json", {"schema": "DiscoverySelections.v1",
              "selections": selections})
        _json(attempt_dir / "owner-exchanges.json", {"schema": "DiscoveryOwnerExchanges.v1",
              "card_digest": hashlib.sha256(owner_card.model_dump_json(by_alias=True).encode()).hexdigest(),
              "exchanges": exchanges})
        session = attempt_dir / ".ultimateinterview" / cell.cell_id
        session.mkdir(parents=True)
        owner_result = discovery_result(
            owner_card, [OwnerExchange.model_validate(row) for row in exchanges]
        )
        owner_result_value = owner_result.model_dump(mode="json", by_alias=True)
        _json(attempt_dir / "discovery-result.json", owner_result_value)
        blockers = interview_blockers(draft, owner_result_value)
        if blockers:
            return self._blocked_result(
                attempt_dir=attempt_dir, session=session,
                marker_name="interview-blocked.json", reasons=blockers,
                owner_result=owner_result_value, transcript=transcript,
                selections=selections, tokens=tokens, started=started,
                details={"contract_draft": draft},
            )
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
            "properties": {"status": {"type": "string",
                                        "enum": ["completed", "blocked-contract-gap"]},
                "contract_gaps": {"type": "array", "items": {"type": "string"}},
                "requirement_verification": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "status": {"type": "string"},
                        "evidence": {"type": "string"}},
                    "required": ["requirement_id", "status", "evidence"]}},
                "commands": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "array", "items": {"type": "string"}}},
            "required": ["status", "contract_gaps", "requirement_verification", "commands", "notes"]}
        repo_session = repo / ".ultimateinterview" / cell.cell_id
        repo_session.mkdir(parents=True, exist_ok=False)
        decision_log_relative = f".ultimateinterview/{cell.cell_id}/decision.jsonl"
        implementation = self._invoke(f"implement-{cell.cell_id}", repo,
            build_implementation_prompt(build_contract, decision_log_relative),
            impl_schema, writable=True,
            pane=pane, role_label="Coding")
        tokens += implementation.tokens
        _json(session / "implementation-return.json", implementation.value)
        decision_source = repo_session / "decision.jsonl"
        unexpected_session_files = [path for path in repo_session.rglob("*")
                                    if path.is_file() and path != decision_source]
        if unexpected_session_files:
            raise RuntimeError("implementer wrote unexpected session artifacts")
        if decision_source.is_file():
            shutil.copy2(decision_source, session / "decision.jsonl")
        shutil.rmtree(repo_session)
        try:
            repo_session.parent.rmdir()
        except OSError:
            pass
        after = _tree(repo)
        diff = _diff(before, after)
        (attempt_dir / "implementation.diff").write_text(diff, encoding="utf-8")
        bundle = session / "compiler-evidence-bundle.json"
        post_root = self.protocol / ".agents/skills/ultimateinterview-postmortem"
        self._run(python, str(post_root / "scripts/compiler_session_check.py"), str(session),
                  "--diff-file", str(attempt_dir / "implementation.diff"), "--repo-root", str(repo),
                  "--output", str(bundle))
        compiler_bundle = json.loads(bundle.read_text())
        safely_blocked = validate_implementation_outcome(
            implementation=implementation.value, implementation_diff=diff,
            decisions=compiler_bundle.get("decisions", ()), build_contract=build_contract,
        )
        if safely_blocked:
            return self._blocked_result(
                attempt_dir=attempt_dir, session=session,
                marker_name="implementation-blocked.json",
                reasons=implementation.value["contract_gaps"],
                owner_result=owner_result_value, transcript=transcript,
                selections=selections, tokens=tokens, started=started,
                contract_requirements=len(build_contract.get("requirements", ())),
                details={"contract_digest": build_contract.get("contract_digest")},
            )
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
                             judge_prompt, judge_schema, pane=pane, role_label="Postmortem")
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
        probe_failures: list[str] = []
        for probe in owner_card.probes:
            completed = subprocess.run(list(probe.command), cwd=repo, text=True,
                                       capture_output=True, timeout=30)
            if completed.returncode != probe.expected_exit or (
                    probe.stdout_contains is not None and probe.stdout_contains not in completed.stdout):
                probe_failures.append(probe.probe_id)
        owner_result = discovery_result(owner_card,
            [OwnerExchange.model_validate(row) for row in exchanges], probe_failures=probe_failures)
        owner_result_value = owner_result.model_dump(mode="json", by_alias=True)
        _json(attempt_dir / "discovery-result.json", owner_result_value)
        semantic_veto = counts["escaped"] > 0 or counts["scope_drift"] > 0
        failure_taxonomy = {row["root_cause"] for row in failure_rows}
        failure_evidence = [row["evidence"] for row in failure_rows]
        if counts["escaped"] > 0:
            failure_taxonomy.add("unreported-contract-gap")
            failure_evidence.append(
                f"implementer reported no contract gaps but postmortem found {counts['escaped']} escaped requirement(s)"
            )
        result = {**parsed, "fulfilled": counts["fulfilled"],
                  "contract_requirements": counts["contract_requirements"],
                  "escaped_requirements": counts["escaped"],
                  "material_decisions": len(selections), "tokens": tokens,
                  "question_turns": len(transcript),
                  "discovery_success": (not owner_result.hard_veto and not semantic_veto
                                        and len(owner_result.resolved_item_ids)
                                        == len(owner_result.applicable_item_ids)),
                  "hard_veto": owner_result.hard_veto or semantic_veto,
                  "critical_misses": list(owner_result.critical_miss_ids),
                  "authority_expansion": any(row["class"] == "scope-drift" for row in failure_rows),
                  "lineage_valid": True,
                  "failure_taxonomy": sorted(failure_taxonomy),
                  "failure_evidence": failure_evidence,
                  "wall_clock_ms": int((time.monotonic() - started) * 1000)}
        _json(attempt_dir / "postmortem-result.json", result)
        return result


__all__ = ["CellBackendResult", "DirectCodexDiscoveryBackend", "RUNTIME_CONTRACT",
           "TURN_SCHEMA", "build_compiler_inputs", "build_evaluator_prompt", "build_generator_prompt",
           "build_evolution_prompt", "build_implementation_prompt", "interview_blockers",
           "normalize_compiler_inputs", "parse_postmortem_markdown",
           "validate_implementation_outcome", "verify_compiled_selection_lineage"]
