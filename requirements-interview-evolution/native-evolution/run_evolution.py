#!/usr/bin/env python3
"""Run one role-isolated interview-skill evolution cell without Orca."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class RoleBackend(Protocol):
    def invoke(self, role: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$" ) -> None:
    """Validate the closed JSON-schema subset used by this harness.

    Codex receives the same schema, but coordinator-side validation is required so a
    custom backend, transport regression, or malformed cached response fails closed.
    """
    if "anyOf" in schema:
        errors: list[str] = []
        for option in schema["anyOf"]:
            try:
                validate_schema(value, option, path)
                return
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"schema validation failed at {path}: no anyOf branch matched")

    expected = schema.get("type")
    allowed = expected if isinstance(expected, list) else [expected] if expected else []
    type_matches = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if allowed and not any(type_matches[kind](value) for kind in allowed):
        raise ValueError(f"schema validation failed at {path}: expected {allowed}")
    if value is None:
        return
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"schema validation failed at {path}: value is not in enum")

    if isinstance(value, dict):
        required = set(schema.get("required", []))
        missing = required - set(value)
        if missing:
            raise ValueError(f"schema validation failed at {path}: missing {sorted(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ValueError(f"schema validation failed at {path}: extra {sorted(extras)}")
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f"{path}/{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError(f"schema validation failed at {path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"schema validation failed at {path}: too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_schema(item, schema["items"], f"{path}/{index}")
    elif isinstance(value, str) and "pattern" in schema:
        if re.search(schema["pattern"], value) is None:
            raise ValueError(f"schema validation failed at {path}: pattern mismatch")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"schema validation failed at {path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"schema validation failed at {path}: above maximum")


DECISION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "answer", "why_material"],
    "properties": {
        "id": {"type": "string"},
        "answer": {"type": "string"},
        "why_material": {"type": "string"},
    },
}

ORACLE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["material_decisions", "owner_rules"],
    "properties": {
        "material_decisions": {"type": "array", "items": DECISION},
        "owner_rules": {"type": "array", "items": {"type": "string"}},
    },
}

CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["public_request", "oracle"],
    "properties": {"public_request": {"type": "string"}, "oracle": ORACLE},
}

OWNER_ORACLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["oracle"],
    "properties": {"oracle": ORACLE},
}

EVIDENCE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "line_start", "line_end"],
    "properties": {
        "path": {"type": "string"},
        "line_start": {"type": "integer", "minimum": 1},
        "line_end": {"type": "integer", "minimum": 1},
    },
}

FACT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "claim", "authority", "evidence"],
    "properties": {
        "id": {"type": "string"},
        "claim": {"type": "string"},
        "authority": {
            "type": "string",
            "enum": ["code", "test", "documentation", "configuration", "runtime-artifact"],
        },
        "evidence": {"type": "array", "minItems": 1, "items": EVIDENCE},
    },
}

DISCOVERY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scope_summary", "facts", "conflicts", "unknowns"],
    "properties": {
        "scope_summary": {"type": "string"},
        "facts": {"type": "array", "items": FACT},
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "description"],
                "properties": {"id": {"type": "string"}, "description": {"type": "string"}},
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
}

AUDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "accepted_fact_ids", "rejected_facts", "resolved_conflicts",
        "unresolved_conflict_ids", "audit_summary"
    ],
    "properties": {
        "accepted_fact_ids": {"type": "array", "items": {"type": "string"}},
        "rejected_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "reason"],
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
            },
        },
        "resolved_conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "resolution"],
                "properties": {"id": {"type": "string"}, "resolution": {"type": "string"}},
            },
        },
        "unresolved_conflict_ids": {"type": "array", "items": {"type": "string"}},
        "audit_summary": {"type": "string"},
    },
}

QUESTION = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["header", "prompt", "options"],
    "properties": {
        "header": {"type": "string"},
        "prompt": {"type": "string"},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "description", "recommended"],
                "properties": {
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "recommended": {"type": "boolean"},
                },
            },
        },
    },
}

CONTRACT = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": [
        "summary", "implementation_ready", "confirmed_decisions",
        "open_material_decisions", "acceptance_checks"
    ],
    "properties": {
        "summary": {"type": "string"},
        "implementation_ready": {"type": "boolean"},
        "confirmed_decisions": {"type": "array", "items": {"type": "string"}},
        "open_material_decisions": {"type": "array", "items": {"type": "string"}},
        "acceptance_checks": {"type": "array", "items": {"type": "string"}},
    },
}

INTERVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "reason", "open_material_decisions", "question", "contract"],
    "properties": {
        "action": {"type": "string", "enum": ["question", "complete"]},
        "reason": {"type": "string"},
        "open_material_decisions": {"type": "array", "items": {"type": "string"}},
        "question": QUESTION,
        "contract": CONTRACT,
    },
}

OWNER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
    "properties": {"answer": {"type": "string"}},
}

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "implementation_ready", "repository_fidelity", "owner_decision_recall",
        "invented_requirements", "question_count", "unnecessary_questions",
        "failures", "summary"
    ],
    "properties": {
        "implementation_ready": {"type": "boolean"},
        "repository_fidelity": {"type": "number", "minimum": 0, "maximum": 1},
        "owner_decision_recall": {"type": "number", "minimum": 0, "maximum": 1},
        "invented_requirements": {"type": "array", "items": {"type": "string"}},
        "question_count": {"type": "integer", "minimum": 0},
        "unnecessary_questions": {"type": "array", "items": {"type": "string"}},
        "failures": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}

MUTATOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["skill_md", "change_summary", "addressed_failures"],
    "properties": {
        "skill_md": {"type": "string"},
        "change_summary": {"type": "string"},
        "addressed_failures": {"type": "array", "items": {"type": "string"}},
    },
}

LENS_STAGES = [
    "discovery", "interaction", "synthesis", "handoff",
    "implementation", "verification", "learning",
]

FAILURE_LENS = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id", "stage", "failure_description", "observable_signal",
        "why_material", "minimal_test_shape",
    ],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "stage": {"type": "string", "enum": LENS_STAGES},
        "failure_description": {"type": "string"},
        "observable_signal": {"type": "string"},
        "why_material": {"type": "string"},
        "minimal_test_shape": {"type": "string"},
    },
}

LENS_PROPOSAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lenses"],
    "properties": {
        "lenses": {"type": "array", "minItems": 3, "maxItems": 5, "items": FAILURE_LENS}
    },
}

LENS_AUDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["accepted_lens_ids", "rejected_lenses", "assessments", "audit_summary"],
    "properties": {
        "accepted_lens_ids": {
            "type": "array", "minItems": 1, "items": {"type": "string"}
        },
        "rejected_lenses": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "reason"],
                "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
            },
        },
        "assessments": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "id", "observable", "material", "solution_neutral", "duplicate_of"
                ],
                "properties": {
                    "id": {"type": "string"},
                    "observable": {"type": "boolean"},
                    "material": {"type": "boolean"},
                    "solution_neutral": {"type": "boolean"},
                    "duplicate_of": {"type": ["string", "null"]},
                },
            },
        },
        "audit_summary": {"type": "string"},
    },
}

LENS_CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["public_request", "target_lens_ids", "objective_failure_signals", "oracle"],
    "properties": {
        "public_request": {"type": "string"},
        "target_lens_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "objective_failure_signals": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "oracle": {"anyOf": [ORACLE, {"type": "null"}]},
    },
}

FINDING_CITATION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["artifact", "pointer", "quoted_text"],
    "properties": {
        "artifact": {"type": "string", "enum": ["contract", "transcript", "evidence"]},
        "pointer": {"type": "string", "pattern": "^/"},
        "quoted_text": {"type": "string"},
    },
}

ADVERSARIAL_REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "review_summary"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "lens_id", "blocker_type", "description", "why_material", "citations"],
                "properties": {
                    "id": {"type": "string"},
                    "lens_id": {"type": "string"},
                    "blocker_type": {
                        "type": "string",
                        "enum": [
                            "repository-evidence-violation", "invented-requirement",
                            "synthesis-loss", "unverifiable-acceptance",
                            "handoff-decision-gap", "contract-contradiction",
                            "preservation-violation",
                        ],
                    },
                    "description": {"type": "string"},
                    "why_material": {"type": "string"},
                    "citations": {"type": "array", "minItems": 1, "items": FINDING_CITATION},
                },
            },
        },
        "review_summary": {"type": "string"},
    },
}

ADJUDICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts", "adjudication_summary"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": [
                    "finding_id", "approved", "evidence_supported", "lens_match",
                    "material", "oracle_conflict", "reason",
                ],
                "properties": {
                    "finding_id": {"type": "string"},
                    "approved": {"type": "boolean"},
                    "evidence_supported": {"type": "boolean"},
                    "lens_match": {"type": "boolean"},
                    "material": {"type": "boolean"},
                    "oracle_conflict": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
            },
        },
        "adjudication_summary": {"type": "string"},
    },
}


class CodexBackend:
    REPOSITORY_ROLES = {"discovery", "evidence-auditor"}

    def __init__(self, timeout: int, model: str | None = None,
                 repo_root: Path | None = None) -> None:
        self.timeout = timeout
        self.model = model
        self.repo_root = repo_root.resolve() if repo_root else None

    def invoke(self, role: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix=f"clarify-{role}-") as raw:
            root = Path(raw)
            schema_path = root / "schema.json"
            output_path = root / "output.json"
            write_json(schema_path, schema)
            command = [
                "codex", "exec", "--ephemeral", "--sandbox", "read-only",
                "--skip-git-repo-check", "--ignore-user-config", "--color", "never",
                "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                "-C", str(root),
            ]
            if role in self.REPOSITORY_ROLES:
                if self.repo_root is None:
                    raise RuntimeError(f"{role} requires a repository root")
                command.extend(["--add-dir", str(self.repo_root)])
            command.append("-")
            if self.model:
                command[2:2] = ["--model", self.model]
            completed = subprocess.run(
                command, input=prompt, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.timeout, env=os.environ.copy(), check=False
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"{role} failed with exit {completed.returncode}: {completed.stderr[-2000:]}"
                )
            if not output_path.is_file():
                raise RuntimeError(f"{role} did not produce a final structured response")
            return json.loads(output_path.read_text(encoding="utf-8"))


def role_prompt(role: str, payload: dict[str, Any]) -> str:
    common = "Return only the JSON object required by the supplied output schema."
    instructions = {
        "failure-lens-proposer": "You are the Failure-Lens Proposer. From only the general task seed and the fixed goal of producing an implementable requirements handoff, propose 3-5 distinct externally observable ways discovery, interaction, synthesis, handoff, implementation, verification, or learning can fail. Do not propose solutions or skill wording and do not name or compare products, agents, skills, or frameworks.",
        "lens-auditor": "You are the independent Lens Auditor and Deduplicator. Assess every proposal for observability, materiality, solution neutrality, and duplication. Accept only lenses for which all three booleans are true and duplicate_of is null. Reject duplicates, vague quality claims, style preferences, and anything dependent on a named product, skill, or implementation phrase. For a duplicate, set duplicate_of to the retained proposal ID. Preserve accepted lens IDs and disposition every proposed lens.",
        "lens-case-designer": "You are the Lens-Conditioned Case Designer. Create an objectively judgeable case shaped by the frozen failure lenses. Do not try to make a candidate skill fail and do not mention candidate wording, scores, mutations, or another partition. In repository context preserve the supplied public request byte-for-byte and return null oracle; in greenfield context create the private owner oracle.",
        "owner-oracle-designer": "You are the Owner Oracle Designer for a repository-grounded case. Use the public request and audited repository evidence. Define only latent product decisions that repository evidence cannot answer. Never contradict or restate accepted repository facts.",
        "discovery": "You are the read-only Repository Discovery Agent. Inspect the repository for facts material to the public request. Every fact must cite repository-relative file paths and exact inclusive line bounds. Put only actual contradictions in conflicts; use an empty array when sources agree. Report unknowns separately. Do not invent desired future behavior or owner choices.",
        "evidence-auditor": "You are an independent read-only Evidence Auditor. Re-open cited repository files, accept only directly supported facts, reject overclaims, and disposition every reported conflict as resolved with a reason or unresolved. Do not create product requirements.",
        "interviewer": "You are the Interviewer. Follow the supplied skill. Treat audited repository evidence as discoverable ground truth and never ask the Owner to repeat it. Ask one material structured question or complete when no open material decision remains. Report the current open material decisions explicitly.",
        "owner": "You are the Owner. Answer only the current question from the private owner oracle. Do not volunteer unasked decisions, evaluate the interviewer, mention the oracle, or reinterpret repository evidence.",
        "adversarial-reviewer": "You are a blind Adversarial Reviewer. Inspect only the public request, audited evidence, transcript, final contract, and frozen failure lenses. Report only material blockers in the allowed categories. Every finding must cite exact JSON pointers and exact quoted values from those artifacts. Pointer roots are the artifact values themselves: contract uses /implementation_ready rather than /final_contract/implementation_ready, transcript uses /0/... rather than /transcript/0/..., and evidence uses /facts/... rather than /audited_repository_evidence/facts/.... You do not have the private owner oracle and must not invent product requirements or preferred architecture.",
        "judge": "You are the independent Judge. Compare transcript and contract against both audited repository evidence and the private owner oracle. Score observed behavior only. Separate repository fidelity from owner-decision recall. Do not suggest exact replacement wording.",
        "adjudicator": "You are the oracle-aware Adjudicator. Decide every blind review finding independently. Approve it only when its exact citations support it, it matches the frozen lens, it is material rather than stylistic, and it does not conflict with repository evidence or the private owner oracle. Do not create replacement requirements or skill wording.",
        "mutator": "You are the Mutator. Revise the skill from the observed transcript, public audited evidence, and Judge failure summary. You never receive the private owner oracle or holdout data. Make the smallest generalizable change and return the full SKILL.md.",
    }
    if role not in instructions:
        raise ValueError(f"unknown role: {role}")
    return f"{instructions[role]}\n{common}\nINPUT:\n{canonical(payload)}"


def invoke_recorded(backend: RoleBackend, run_dir: Path, sequence: int, role: str,
                    payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    prompt = role_prompt(role, payload)
    result = backend.invoke(role, prompt, schema)
    validate_schema(result, schema)
    write_json(run_dir / "calls" / f"{sequence:03d}-{role}.json", {
        "role": role, "prompt": prompt, "prompt_sha256": digest_text(prompt),
        "input": payload, "output": result
    })
    return result


def validate_discovery(repo_root: Path, discovery: dict[str, Any]) -> None:
    root = repo_root.resolve()
    ids: set[str] = set()
    for fact in discovery["facts"]:
        if fact["id"] in ids:
            raise ValueError(f"duplicate discovery fact id: {fact['id']}")
        ids.add(fact["id"])
        for evidence in fact["evidence"]:
            relative = Path(evidence["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe evidence path: {relative}")
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                raise ValueError(f"evidence path is not a repository file: {relative}")
            line_count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
            if evidence["line_start"] > evidence["line_end"] or evidence["line_end"] > line_count:
                raise ValueError(f"invalid evidence line bounds: {relative}")


def seal_discovery(repo_root: Path, discovery: dict[str, Any]) -> dict[str, Any]:
    validate_discovery(repo_root, discovery)
    sealed = json.loads(json.dumps(discovery))
    root = repo_root.resolve()
    cited_files: dict[str, str] = {}
    for fact in sealed["facts"]:
        for evidence in fact["evidence"]:
            relative = evidence["path"]
            target = root / relative
            raw = target.read_bytes()
            lines = raw.decode("utf-8", errors="replace").splitlines()
            quoted = "\n".join(lines[evidence["line_start"] - 1:evidence["line_end"]])
            evidence["quoted_text"] = quoted
            evidence["quoted_text_sha256"] = digest_text(quoted)
            cited_files[relative] = hashlib.sha256(raw).hexdigest()
    git_head = None
    git_status_sha256 = None
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True
        )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True
        )
        git_head = head.stdout.strip()
        git_status_sha256 = digest_text(status.stdout)
    except (OSError, subprocess.CalledProcessError):
        pass
    sealed["repository_snapshot"] = {
        "git_head": git_head,
        "git_status_sha256": git_status_sha256,
        "cited_file_sha256": cited_files,
    }
    return sealed


def audited_evidence(discovery: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    by_id = {fact["id"]: fact for fact in discovery["facts"]}
    accepted = audit["accepted_fact_ids"]
    if len(accepted) != len(set(accepted)) or any(fact_id not in by_id for fact_id in accepted):
        raise ValueError("evidence auditor returned an invalid accepted fact inventory")
    rejected = {item["id"] for item in audit["rejected_facts"]}
    if any(fact_id not in by_id for fact_id in rejected) or set(accepted) & rejected:
        raise ValueError("evidence auditor returned contradictory fact dispositions")
    if set(accepted) | rejected != set(by_id):
        raise ValueError("evidence auditor must disposition every discovery fact")
    conflict_by_id = {item["id"]: item for item in discovery["conflicts"]}
    if len(conflict_by_id) != len(discovery["conflicts"]):
        raise ValueError("duplicate discovery conflict id")
    resolved = {item["id"] for item in audit["resolved_conflicts"]}
    unresolved = set(audit["unresolved_conflict_ids"])
    if resolved & unresolved or resolved | unresolved != set(conflict_by_id):
        raise ValueError("evidence auditor must disposition every discovery conflict")
    return {
        "scope_summary": discovery["scope_summary"],
        "facts": [by_id[fact_id] for fact_id in accepted],
        "unknowns": discovery["unknowns"],
        "unresolved_conflicts": [conflict_by_id[item] for item in audit["unresolved_conflict_ids"]],
        "resolved_conflicts": audit["resolved_conflicts"],
        "audit_summary": audit["audit_summary"],
        "repository_snapshot": discovery["repository_snapshot"],
    }


def validate_interview_output(interview: dict[str, Any]) -> None:
    if interview["action"] == "question":
        if not isinstance(interview["question"], dict) or interview["contract"] is not None:
            raise ValueError("question action requires question and forbids contract")
        if not interview["open_material_decisions"]:
            raise ValueError("question action requires at least one open material decision")
    else:
        contract = interview["contract"]
        if interview["question"] is not None or not isinstance(contract, dict):
            raise ValueError("complete action requires contract and forbids question")
        if contract["implementation_ready"] and contract["open_material_decisions"]:
            raise ValueError("implementation-ready contract cannot contain open material decisions")
        if sorted(set(interview["open_material_decisions"])) != sorted(
                set(contract["open_material_decisions"])):
            raise ValueError("interviewer and contract open decisions must match")


def validate_lens_set(proposal: dict[str, Any], audit: dict[str, Any]) -> list[dict[str, Any]]:
    proposed = proposal["lenses"]
    proposed_by_id = {lens["id"]: lens for lens in proposed}
    if len(proposed_by_id) != len(proposed):
        raise ValueError("failure-lens proposer returned duplicate lens ids")
    accepted_ids = audit["accepted_lens_ids"]
    rejected_ids = [item["id"] for item in audit["rejected_lenses"]]
    if len(accepted_ids) != len(set(accepted_ids)) or len(rejected_ids) != len(set(rejected_ids)):
        raise ValueError("lens auditor returned duplicate dispositions")
    if set(accepted_ids) & set(rejected_ids):
        raise ValueError("lens auditor returned contradictory dispositions")
    if set(accepted_ids) | set(rejected_ids) != set(proposed_by_id):
        raise ValueError("lens auditor must disposition every proposed lens")
    assessments = audit["assessments"]
    assessment_ids = [item["id"] for item in assessments]
    if len(assessment_ids) != len(set(assessment_ids)) or set(assessment_ids) != set(proposed_by_id):
        raise ValueError("lens auditor must assess every proposed lens exactly once")
    assessment_by_id = {item["id"]: item for item in assessments}
    for lens_id in accepted_ids:
        assessment = assessment_by_id[lens_id]
        if not (assessment["observable"] and assessment["material"]
                and assessment["solution_neutral"] and assessment["duplicate_of"] is None):
            raise ValueError("lens auditor accepted an unobservable, immaterial, dependent, or duplicate lens")
    for lens_id in rejected_ids:
        assessment = assessment_by_id[lens_id]
        if (assessment["observable"] and assessment["material"]
                and assessment["solution_neutral"] and assessment["duplicate_of"] is None):
            raise ValueError("lens auditor rejected a lens without a recorded rejection basis")
        duplicate_of = assessment["duplicate_of"]
        if duplicate_of is not None and duplicate_of not in proposed_by_id:
            raise ValueError("lens auditor duplicate target is unknown")
    accepted = [proposed_by_id[lens_id] for lens_id in accepted_ids]
    for lens in accepted:
        searchable = canonical(lens).lower()
        forbidden = ("ultimateinterview", "deep interview", "codex plan", "clarify-requirements")
        if any(term in searchable for term in forbidden):
            raise ValueError("accepted lens depends on a named tool or skill")
        fields = ("failure_description", "observable_signal", "why_material", "minimal_test_shape")
        if any(not lens[field].strip() for field in fields):
            raise ValueError("accepted lens contains an empty observable field")
    normalized_signatures = [
        digest_text(canonical({key: lens[key] for key in lens if key != "id"}).lower())
        for lens in accepted
    ]
    if len(normalized_signatures) != len(set(normalized_signatures)):
        raise ValueError("lens auditor accepted duplicate lenses")
    return accepted


def validate_lens_case(case: dict[str, Any], frozen_lenses: list[dict[str, Any]],
                       context_mode: str, seed: str) -> None:
    known = {lens["id"] for lens in frozen_lenses}
    selected = case["target_lens_ids"]
    if len(selected) != len(set(selected)) or not set(selected).issubset(known):
        raise ValueError("case designer selected an invalid failure lens")
    if context_mode == "repository":
        if case["public_request"] != seed:
            raise ValueError("repository case designer must preserve the public request")
        if case["oracle"] is not None:
            raise ValueError("repository case designer must not create a private oracle")
    elif not isinstance(case["oracle"], dict):
        raise ValueError("greenfield case designer must create a private oracle")


def resolve_pointer(value: Any, pointer: str) -> Any:
    current = value
    if pointer == "":
        return current
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with /")
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"invalid review citation pointer: {pointer}") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"invalid review citation pointer: {pointer}")
    return current


def validate_adversarial_review(review: dict[str, Any], frozen_lenses: list[dict[str, Any]],
                                contract: dict[str, Any], transcript: list[dict[str, Any]],
                                evidence: dict[str, Any]) -> None:
    lens_ids = {lens["id"] for lens in frozen_lenses}
    finding_ids: set[str] = set()
    artifacts = {"contract": contract, "transcript": transcript, "evidence": evidence}
    for finding in review["findings"]:
        if finding["id"] in finding_ids:
            raise ValueError("adversarial reviewer returned duplicate finding ids")
        finding_ids.add(finding["id"])
        if finding["lens_id"] not in lens_ids:
            raise ValueError("adversarial finding references an unknown lens")
        for citation in finding["citations"]:
            pointer = citation["pointer"]
            envelope_prefix = {
                "contract": "/final_contract",
                "transcript": "/transcript",
                "evidence": "/audited_repository_evidence",
            }[citation["artifact"]]
            if pointer == envelope_prefix:
                pointer = ""
            elif pointer.startswith(envelope_prefix + "/"):
                pointer = pointer[len(envelope_prefix):]
            observed = resolve_pointer(artifacts[citation["artifact"]], pointer)
            quoted = citation["quoted_text"]
            matches = quoted == observed if isinstance(observed, str) else quoted == canonical(observed)
            if not matches:
                raise ValueError("adversarial finding citation does not match the artifact")


def approved_findings(review: dict[str, Any], adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    findings = {item["id"]: item for item in review["findings"]}
    verdicts = adjudication["verdicts"]
    verdict_ids = [item["finding_id"] for item in verdicts]
    if len(verdict_ids) != len(set(verdict_ids)) or set(verdict_ids) != set(findings):
        raise ValueError("adjudicator must disposition every adversarial finding exactly once")
    approved: list[dict[str, Any]] = []
    for verdict in verdicts:
        valid = (
            verdict["evidence_supported"] and verdict["lens_match"]
            and verdict["material"] and not verdict["oracle_conflict"]
        )
        if verdict["approved"] != valid:
            raise ValueError("adjudicator approval is inconsistent with its verdict fields")
        if valid:
            approved.append(findings[verdict["finding_id"]])
    return approved


def case_identity(seed: str, public_request: str, evidence_pack: dict[str, Any],
                  oracle: dict[str, Any], lens_set_sha256: str,
                  lens_case: dict[str, Any]) -> dict[str, str]:
    return {
        "seed_sha256": digest_text(seed),
        "public_request_sha256": digest_text(public_request),
        "lens_set_sha256": lens_set_sha256,
        "lens_case_sha256": digest_text(canonical(lens_case)),
        "case_sha256": digest_text(canonical({
            "public_request": public_request,
            "evidence_pack": evidence_pack,
            "owner_oracle": oracle,
        })),
    }


def _locked_registry(path: Path, operation: Any) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            registry = ({"schema": "NativeEvolutionStudyRegistry.v1", "entries": []}
                        if not path.is_file() else json.loads(path.read_text(encoding="utf-8")))
            if registry.get("schema") != "NativeEvolutionStudyRegistry.v1":
                raise ValueError("study registry schema is invalid")
            result = operation(registry)
            replace_json(path, registry)
            return result
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def reserve_study_run(path: Path, mode: str, identity: dict[str, str],
                      run_dir: Path) -> None:
    resolved_run = str(run_dir.resolve())

    def reserve(registry: dict[str, Any]) -> None:
        for entry in registry.get("entries", []):
            overlap = sorted(
                key for key, value in identity.items() if entry["identity"].get(key) == value
            )
            if overlap and (mode == "holdout" or entry["mode"] == "holdout"):
                raise ValueError(
                    f"study partition contamination with {entry['mode']} run on {','.join(overlap)}"
                )
        registry["entries"].append({
            "mode": mode, "identity": identity, "run_dir": resolved_run,
            "status": "reserved", "recorded_at": datetime.now(UTC).isoformat(),
        })

    _locked_registry(path, reserve)


def complete_study_run(path: Path, run_dir: Path) -> None:
    resolved_run = str(run_dir.resolve())

    def complete(registry: dict[str, Any]) -> None:
        matches = [entry for entry in registry["entries"] if entry["run_dir"] == resolved_run]
        if len(matches) != 1 or matches[0]["status"] != "reserved":
            raise ValueError("study run reservation is missing or invalid")
        matches[0]["status"] = "completed"
        matches[0]["completed_at"] = datetime.now(UTC).isoformat()

    _locked_registry(path, complete)


def verify_run_artifacts(run_dir: Path, manifest: dict[str, Any]) -> None:
    """Fail closed before a registry entry can be marked completed."""
    lens_set_path = run_dir / "lens-set.json"
    lens_set = json.loads(lens_set_path.read_text(encoding="utf-8"))
    recorded_lens_digest = lens_set.pop("sha256", None)
    if recorded_lens_digest != digest_text(canonical(lens_set)):
        raise ValueError("run artifact integrity failure: lens-set.json self digest")
    checks = {
        "lens_set_sha256": ("lens-set.json", lambda item: item["sha256"]),
        "lens_case_sha256": ("lens-case.json", lambda item: digest_text(canonical(item))),
        "public_case_sha256": ("public-case.json", lambda item: digest_text(canonical(item))),
        "evidence_pack_sha256": ("evidence-pack.json", lambda item: digest_text(canonical(item))),
        "owner_oracle_sha256": (
            "private-owner-oracle.json", lambda item: digest_text(canonical(item))
        ),
        "transcript_sha256": ("transcript.json", lambda item: digest_text(canonical(item))),
        "evaluation_sha256": ("evaluation.json", lambda item: digest_text(canonical(item))),
        "adversarial_review_sha256": (
            "adversarial-review.json", lambda item: digest_text(canonical(item))
        ),
        "adjudication_sha256": ("adjudication.json", lambda item: digest_text(canonical(item))),
    }
    for field, (name, calculate) in checks.items():
        path = run_dir / name
        if not path.is_file() or manifest[field] != calculate(json.loads(path.read_text(encoding="utf-8"))):
            raise ValueError(f"run artifact integrity failure: {name}")
    if manifest["lens_set_sha256"] != manifest["case_identity"]["lens_set_sha256"]:
        raise ValueError("run artifact integrity failure: lens-set identity mismatch")
    calls = sorted((run_dir / "calls").glob("*.json"))
    if len(calls) != manifest["call_count"]:
        raise ValueError("run artifact integrity failure: call count mismatch")
    for call in calls:
        item = json.loads(call.read_text(encoding="utf-8"))
        if digest_text(item["prompt"]) != item["prompt_sha256"]:
            raise ValueError(f"run artifact integrity failure: {call.name} prompt digest")
    candidate = run_dir / "candidate-SKILL.md"
    if manifest["mode"] == "holdout":
        if candidate.exists() or manifest["candidate_sha256"] is not None:
            raise ValueError("holdout run contains a mutation candidate")
    elif not candidate.is_file() or manifest["candidate_sha256"] != digest_text(
            candidate.read_text(encoding="utf-8")):
        raise ValueError("run artifact integrity failure: candidate-SKILL.md")


def run(seed: str, skill: str, run_dir: Path, backend: RoleBackend,
        safety_max_turns: int | None, mode: str = "development", context_mode: str = "greenfield",
        repo_root: Path | None = None, stagnation_patience: int = 3,
        study_registry: Path | None = None) -> dict[str, Any]:
    if mode not in {"development", "holdout"}:
        raise ValueError("mode must be development or holdout")
    if context_mode not in {"greenfield", "repository"}:
        raise ValueError("context_mode must be greenfield or repository")
    if (safety_max_turns is not None and safety_max_turns < 2) or stagnation_patience < 2:
        raise ValueError("an explicit safety_max_turns and stagnation_patience must be at least 2")
    if context_mode == "repository" and repo_root is None:
        raise ValueError("repository context requires repo_root")

    run_dir.mkdir(parents=True, exist_ok=False)
    sequence = 1
    lens_proposal = invoke_recorded(backend, run_dir, sequence, "failure-lens-proposer", {
        "seed_category": seed,
        "fixed_goal": "surface material ambiguity and produce an implementable requirements handoff",
    }, LENS_PROPOSAL_SCHEMA)
    sequence += 1
    write_json(run_dir / "lens-proposal.json", lens_proposal)
    lens_audit = invoke_recorded(backend, run_dir, sequence, "lens-auditor", {
        "proposed_lenses": lens_proposal["lenses"],
        "acceptance_rule": (
            "distinct, externally observable, materially outcome-changing, solution-neutral"
        ),
    }, LENS_AUDIT_SCHEMA)
    sequence += 1
    write_json(run_dir / "lens-audit.json", lens_audit)
    frozen_lenses = validate_lens_set(lens_proposal, lens_audit)
    lens_set = {
        "schema": "NativeEvolutionFailureLensSet.v1",
        "lenses": frozen_lenses,
    }
    lens_set_digest = digest_text(canonical(lens_set))
    lens_set["sha256"] = lens_set_digest
    write_json(run_dir / "lens-set.json", lens_set)

    evidence_pack: dict[str, Any] = {
        "scope_summary": "greenfield; no repository evidence",
        "facts": [], "unknowns": [], "unresolved_conflicts": [], "audit_summary": "not applicable"
    }
    if context_mode == "repository":
        assert repo_root is not None
        public_request = seed
        discovery_raw = invoke_recorded(backend, run_dir, sequence, "discovery", {
            "public_request": public_request, "repository_root": str(repo_root.resolve())
        }, DISCOVERY_SCHEMA)
        sequence += 1
        discovery = seal_discovery(repo_root, discovery_raw)
        write_json(run_dir / "discovery.json", discovery)
        audit = invoke_recorded(backend, run_dir, sequence, "evidence-auditor", {
            "public_request": public_request,
            "repository_root": str(repo_root.resolve()),
            "discovery": discovery,
        }, AUDIT_SCHEMA)
        sequence += 1
        write_json(run_dir / "evidence-audit.json", audit)
        evidence_pack = audited_evidence(discovery, audit)
        lens_case = invoke_recorded(backend, run_dir, sequence, "lens-case-designer", {
            "seed": seed, "context_mode": context_mode,
            "frozen_failure_lenses": frozen_lenses,
            "audited_repository_evidence": evidence_pack,
        }, LENS_CASE_SCHEMA)
        sequence += 1
        validate_lens_case(lens_case, frozen_lenses, context_mode, seed)
        designed = invoke_recorded(backend, run_dir, sequence, "owner-oracle-designer", {
            "public_request": public_request, "audited_repository_evidence": evidence_pack,
            "objective_failure_signals": lens_case["objective_failure_signals"],
        }, OWNER_ORACLE_SCHEMA)
        sequence += 1
        oracle = designed["oracle"]
    else:
        lens_case = invoke_recorded(backend, run_dir, sequence, "lens-case-designer", {
            "seed": seed, "context_mode": context_mode,
            "frozen_failure_lenses": frozen_lenses,
            "audited_repository_evidence": None,
        }, LENS_CASE_SCHEMA)
        sequence += 1
        validate_lens_case(lens_case, frozen_lenses, context_mode, seed)
        public_request = lens_case["public_request"]
        oracle = lens_case["oracle"]

    write_json(run_dir / "public-case.json", {"public_request": public_request})
    write_json(run_dir / "lens-case.json", lens_case)
    write_json(run_dir / "evidence-pack.json", evidence_pack)
    write_json(run_dir / "private-owner-oracle.json", oracle)
    identity = case_identity(seed, public_request, evidence_pack, oracle, lens_set_digest, lens_case)
    registry_path = (study_registry or (run_dir.parent / "study-registry.json")).resolve()
    reserve_study_run(registry_path, mode, identity, run_dir)

    transcript: list[dict[str, Any]] = []
    final_contract: dict[str, Any] | None = None
    stagnation_history: list[tuple[tuple[str, ...], str]] = []
    termination_reason = "completed"

    turn = 1
    while True:
        interview = invoke_recorded(backend, run_dir, sequence, "interviewer", {
            "skill_md": skill, "public_request": public_request,
            "audited_repository_evidence": evidence_pack, "transcript": transcript,
            "turn": turn, "force_close": False,
        }, INTERVIEW_SCHEMA)
        sequence += 1
        validate_interview_output(interview)
        open_now = tuple(sorted(set(interview["open_material_decisions"])))
        if interview["action"] == "complete":
            final_contract = interview["contract"]
            transcript.append({"turn": turn, "interviewer": interview})
            break
        question = interview["question"]
        question_signature = digest_text(canonical({
            "header": question["header"], "prompt": question["prompt"]
        }))
        stagnation_history.append((open_now, question_signature))
        owner = invoke_recorded(backend, run_dir, sequence, "owner", {
            "oracle": oracle, "owner_rules": oracle["owner_rules"],
            "transcript": transcript, "question": question,
        }, OWNER_SCHEMA)
        sequence += 1
        transcript.append({
            "turn": turn, "open_material_decisions": list(open_now),
            "question": question, "answer": owner["answer"]
        })
        if (len(stagnation_history) >= stagnation_patience
                and len(set(stagnation_history[-stagnation_patience:])) == 1):
            termination_reason = "stagnation"
            break
        if safety_max_turns is not None and turn >= safety_max_turns:
            termination_reason = "safety_ceiling"
            break
        turn += 1

    if final_contract is None:
        forced = invoke_recorded(backend, run_dir, sequence, "interviewer", {
            "skill_md": skill, "public_request": public_request,
            "audited_repository_evidence": evidence_pack, "transcript": transcript,
            "turn": len(transcript) + 1, "force_close": True,
            "force_close_reason": termination_reason,
        }, INTERVIEW_SCHEMA)
        sequence += 1
        validate_interview_output(forced)
        if forced["action"] != "complete":
            raise ValueError("forced close must return a contract")
        if forced["contract"]["implementation_ready"]:
            raise ValueError("forced close cannot claim implementation readiness")
        final_contract = forced["contract"]
        transcript.append({"termination": termination_reason, "interviewer": forced})

    write_json(run_dir / "transcript.json", transcript)
    adversarial_review = invoke_recorded(backend, run_dir, sequence, "adversarial-reviewer", {
        "public_request": public_request,
        "audited_repository_evidence": evidence_pack,
        "transcript": transcript,
        "final_contract": final_contract,
        "frozen_failure_lenses": frozen_lenses,
    }, ADVERSARIAL_REVIEW_SCHEMA)
    sequence += 1
    validate_adversarial_review(
        adversarial_review, frozen_lenses, final_contract, transcript, evidence_pack
    )
    write_json(run_dir / "adversarial-review.json", adversarial_review)
    judge = invoke_recorded(backend, run_dir, sequence, "judge", {
        "owner_oracle": oracle, "audited_repository_evidence": evidence_pack,
        "public_request": public_request, "transcript": transcript,
        "final_contract": final_contract, "termination_reason": termination_reason,
        "frozen_failure_lenses": frozen_lenses,
    }, JUDGE_SCHEMA)
    sequence += 1
    write_json(run_dir / "evaluation.json", judge)
    adjudication = invoke_recorded(backend, run_dir, sequence, "adjudicator", {
        "public_request": public_request,
        "owner_oracle": oracle,
        "audited_repository_evidence": evidence_pack,
        "transcript": transcript,
        "final_contract": final_contract,
        "frozen_failure_lenses": frozen_lenses,
        "blind_review": adversarial_review,
    }, ADJUDICATION_SCHEMA)
    sequence += 1
    approved = approved_findings(adversarial_review, adjudication)
    write_json(run_dir / "adjudication.json", adjudication)

    mutation = None
    if mode == "development":
        mutation = invoke_recorded(backend, run_dir, sequence, "mutator", {
            "candidate_skill_md": skill, "public_request": public_request,
            "audited_repository_evidence": evidence_pack, "transcript": transcript,
            "judge_failure_summary": {
                "failures": judge["failures"],
                "unnecessary_questions": judge["unnecessary_questions"],
                "summary": judge["summary"],
            },
            "approved_adversarial_findings": approved,
        }, MUTATOR_SCHEMA)
        write_json(run_dir / "mutation.json", mutation)
        (run_dir / "candidate-SKILL.md").write_text(mutation["skill_md"], encoding="utf-8")

    manifest = {
        "schema": "NativeEvolutionRun.v3", "created_at": datetime.now(UTC).isoformat(),
        "seed": seed, "skill_sha256": digest_text(skill),
        "input_sha256": digest_text(canonical({
            "seed": seed, "mode": mode, "context_mode": context_mode,
        })),
        "model": getattr(backend, "model", None),
        "lens_set_sha256": lens_set_digest,
        "lens_case_sha256": digest_text(canonical(lens_case)),
        "public_case_sha256": digest_text(canonical({"public_request": public_request})),
        "evidence_pack_sha256": digest_text(canonical(evidence_pack)),
        "owner_oracle_sha256": digest_text(canonical(oracle)),
        "transcript_sha256": digest_text(canonical(transcript)),
        "evaluation_sha256": digest_text(canonical(judge)),
        "adversarial_review_sha256": digest_text(canonical(adversarial_review)),
        "adjudication_sha256": digest_text(canonical(adjudication)),
        "candidate_sha256": digest_text(mutation["skill_md"]) if mutation else None,
        "safety_max_turns": safety_max_turns, "stagnation_patience": stagnation_patience,
        "termination_reason": termination_reason, "mode": mode, "context_mode": context_mode,
        "case_identity": identity, "study_registry": str(registry_path),
        "roles": (["failure-lens-proposer", "lens-auditor", "lens-case-designer",
                   "interviewer", "owner", "adversarial-reviewer", "judge", "adjudicator", "mutator"]
                  if context_mode == "greenfield" and mode == "development" else
                  ["failure-lens-proposer", "lens-auditor", "lens-case-designer",
                   "interviewer", "owner", "adversarial-reviewer", "judge", "adjudicator"]
                  if context_mode == "greenfield" else
                  ["failure-lens-proposer", "lens-auditor", "discovery", "evidence-auditor",
                   "lens-case-designer", "owner-oracle-designer", "interviewer", "owner",
                   "adversarial-reviewer", "judge", "adjudicator"]
                  + (["mutator"] if mode == "development" else [])),
        "transport": "codex exec --ephemeral", "orca": False,
        "isolation": "logical-prompt-and-working-directory; not OS read-deny",
        "call_count": len(list((run_dir / "calls").glob("*.json"))),
    }
    write_json(run_dir / "manifest.json", manifest)
    verify_run_artifacts(run_dir, manifest)
    complete_study_run(registry_path, run_dir)
    return {"manifest": manifest, "evaluation": judge, "run_dir": str(run_dir)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed")
    parser.add_argument("--skill", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--context", choices=("greenfield", "repository"), default="greenfield")
    parser.add_argument("--repo", type=Path)
    parser.add_argument(
        "--safety-max-turns", type=int,
        help="optional emergency runaway guard; omitted means no turn ceiling",
    )
    parser.add_argument("--stagnation-patience", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--model")
    parser.add_argument("--study-registry", type=Path)
    parser.add_argument("--mode", choices=("development", "holdout"), default="development")
    parser.add_argument("--imported-case", type=Path)
    parser.add_argument("--sealed-source", type=Path)
    parser.add_argument("--cache-root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.imported_case is not None:
        missing = [name for name in ("sealed_source", "cache_root", "repo") if getattr(args, name) is None]
        if missing:
            raise SystemExit("--imported-case requires --sealed-source, --cache-root, and --repo")
        if args.model not in {None, "gpt-5.6-sol"}:
            raise SystemExit("imported cases require --model gpt-5.6-sol with no fallback")
        if args.safety_max_turns is not None:
            raise SystemExit("imported cases forbid an arbitrary interview turn ceiling")
        package_src = Path(__file__).resolve().parents[1] / "swebench-interview-cases" / "src"
        sys.path.insert(0, str(package_src))
        from swebench_interview_cases.cache import ContentAddressedCache
        from swebench_interview_cases.imported_native import run_imported_case

        skill = args.skill.read_text(encoding="utf-8")
        try:
            result = run_imported_case(
                public_case=json.loads(args.imported_case.read_text(encoding="utf-8")),
                sealed_source=json.loads(args.sealed_source.read_text(encoding="utf-8")),
                cache=ContentAddressedCache(args.cache_root), repo_root=args.repo,
                skill_md=skill, run_dir=args.run_dir,
                stagnation_patience=args.stagnation_patience,
            )
        except Exception as exc:
            args.run_dir.mkdir(parents=True, exist_ok=True)
            write_json(args.run_dir / "failure.json", {
                "schema": "NativeEvolutionImportedFailure.v1",
                "created_at": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__, "error": str(exc),
            })
            raise
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.seed is None:
        raise SystemExit("--seed is required unless --imported-case is used")
    if args.context == "repository" and args.repo is None:
        raise SystemExit("--context repository requires --repo")
    skill = args.skill.read_text(encoding="utf-8")
    backend = CodexBackend(args.timeout, args.model, args.repo)
    try:
        result = run(
            args.seed, skill, args.run_dir, backend, args.safety_max_turns,
            args.mode, args.context, args.repo, args.stagnation_patience,
            args.study_registry
        )
    except Exception as exc:
        args.run_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.run_dir / "failure.json", {
            "schema": "NativeEvolutionFailure.v1", "created_at": datetime.now(UTC).isoformat(),
            "error_type": type(exc).__name__, "error": str(exc), "mode": args.mode,
            "context_mode": args.context,
        })
        raise
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
