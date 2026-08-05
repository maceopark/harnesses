"""Imported SWE-bench case execution using the v5 interview loop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from .adapter import BLIND_FAILURE_TAXONOMY, project_role_payload
from .cache import ContentAddressedCache
from .model import CodexJsonModel
from .leakage import audit_public_payload, patch_only_sentinels
from .schemas import artifact_digest, validate_case_pair


DEFAULT_EVALUATOR_RUBRIC = (
    "Treat the public request, issue-time owner decisions, and audited repository facts as the "
    "contract boundary. Count behavior not supported by those sources as invented, including "
    "gold-patch implementation choices, exact messages, test placement, documentation work, "
    "or broadened input domains. Count removal or alteration of compatible repository behavior "
    "as a compatibility regression. Hindsight-only evidence may diagnose a mismatch but must not "
    "retroactively create a requirement that was unknowable at interview time."
)


QUESTION = {
    "type": ["object", "null"], "additionalProperties": False,
    "required": ["header", "prompt", "options"],
    "properties": {
        "header": {"type": "string"}, "prompt": {"type": "string"},
        "options": {"type": "array", "minItems": 2, "maxItems": 3, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["label", "description", "recommended"],
            "properties": {"label": {"type": "string"}, "description": {"type": "string"}, "recommended": {"type": "boolean"}},
        }},
    },
}

CONTRACT = {
    "type": ["object", "null"], "additionalProperties": False,
    "required": ["summary", "implementation_ready", "confirmed_decisions", "open_material_decisions", "acceptance_checks"],
    "properties": {
        "summary": {"type": "string"}, "implementation_ready": {"type": "boolean"},
        "confirmed_decisions": {"type": "array", "items": {"type": "string"}},
        "open_material_decisions": {"type": "array", "items": {"type": "string"}},
        "acceptance_checks": {"type": "array", "items": {"type": "string"}},
    },
}

INTERVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["action", "reason", "open_material_decisions", "question", "contract"],
    "properties": {
        "action": {"enum": ["question", "complete"]}, "reason": {"type": "string"},
        "open_material_decisions": {"type": "array", "items": {"type": "string"}},
        "question": QUESTION, "contract": CONTRACT,
    },
}

DISCOVERY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["scope_summary", "facts", "unknowns"],
    "properties": {
        "scope_summary": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["id", "statement", "path", "line_start", "line_end"],
            "properties": {"id": {"type": "string"}, "statement": {"type": "string"}, "path": {"type": "string"}, "line_start": {"type": "integer", "minimum": 1}, "line_end": {"type": "integer", "minimum": 1}}}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
    },
}

AUDIT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["accepted_fact_ids", "rejected", "summary"],
    "properties": {
        "accepted_fact_ids": {"type": "array", "items": {"type": "string"}},
        "rejected": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "reason"], "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}}},
        "summary": {"type": "string"},
    },
}

OWNER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {"answer": {"type": "string"}}}

FINDING = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "failure_class", "general_cause", "observable_signal", "description", "material", "citations"],
    "properties": {
        "id": {"type": "string"}, "failure_class": {"enum": list(BLIND_FAILURE_TAXONOMY)},
        "general_cause": {"type": "string"}, "observable_signal": {"type": "string"},
        "description": {"type": "string"}, "material": {"type": "boolean"},
        "citations": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["artifact", "pointer", "quoted_value"],
            "properties": {
                "artifact": {"enum": ["contract", "transcript", "evidence"]},
                "pointer": {"type": "string", "pattern": "^/"},
                # Structured outputs require arrays and objects to have closed
                # child schemas. A citation can always point to the exact
                # scalar leaf instead of quoting a composite container.
                "quoted_value": {"type": ["boolean", "null", "number", "string"]},
            },
        }},
    },
}

REVIEW_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["findings", "summary"], "properties": {"findings": {"type": "array", "items": FINDING}, "summary": {"type": "string"}}}

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["implementation_ready", "repository_fidelity", "owner_recall", "invented_requirements", "compatibility_regressions", "redundant_questions", "material_blockers", "summary"],
    "properties": {
        "implementation_ready": {"type": "boolean"}, "repository_fidelity": {"type": "number", "minimum": 0, "maximum": 1},
        "owner_recall": {"type": "number", "minimum": 0, "maximum": 1},
        "invented_requirements": {"type": "array", "items": {"type": "string"}},
        "compatibility_regressions": {"type": "array", "items": {"type": "string"}},
        "redundant_questions": {"type": "array", "items": {"type": "string"}},
        "material_blockers": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}

ADJUDICATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdicts", "summary"],
    "properties": {
        "verdicts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "required": ["finding_id", "approved", "evidence_supported", "material", "repository_independent", "implementation_independent", "oracle_conflict", "reason"],
            "properties": {"finding_id": {"type": "string"}, "approved": {"type": "boolean"}, "evidence_supported": {"type": "boolean"}, "material": {"type": "boolean"}, "repository_independent": {"type": "boolean"}, "implementation_independent": {"type": "boolean"}, "oracle_conflict": {"type": "boolean"}, "reason": {"type": "string"}}}},
        "summary": {"type": "string"},
    },
}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _validate_discovery(repo_root: Path, discovery: Mapping[str, Any]) -> None:
    root = repo_root.resolve()
    ids: set[str] = set()
    for fact in discovery["facts"]:
        if fact["id"] in ids:
            raise ValueError("duplicate repository fact ID")
        ids.add(fact["id"])
        relative = Path(fact["path"])
        target = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(root) or not target.is_file():
            raise ValueError("repository fact cites an unsafe or missing file")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if fact["line_start"] > fact["line_end"] or fact["line_end"] > len(lines):
            raise ValueError("repository fact cites invalid line bounds")


def _audited_evidence(discovery: Mapping[str, Any], audit: Mapping[str, Any]) -> dict[str, Any]:
    facts = {item["id"]: item for item in discovery["facts"]}
    accepted = audit["accepted_fact_ids"]
    rejected = {item["id"] for item in audit["rejected"]}
    if len(accepted) != len(set(accepted)) or set(accepted) & rejected or set(accepted) | rejected != set(facts):
        raise ValueError("evidence auditor must disposition every fact exactly once")
    return {"scope_summary": discovery["scope_summary"], "facts": [facts[item] for item in accepted], "unknowns": discovery["unknowns"], "audit_summary": audit["summary"]}


def _validate_interview(item: Mapping[str, Any]) -> None:
    if item["action"] == "question":
        if item["question"] is None or item["contract"] is not None or not item["open_material_decisions"]:
            raise ValueError("invalid question action")
    else:
        contract = item["contract"]
        if item["question"] is not None or contract is None:
            raise ValueError("invalid complete action")
        if contract["implementation_ready"] and contract["open_material_decisions"]:
            raise ValueError("implementation-ready contract retains blockers")


def _resolve_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"invalid citation pointer: {pointer}") from exc
        elif isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            raise ValueError(f"invalid citation pointer: {pointer}")
    return current


def _validate_review_citations(
    review: Mapping[str, Any], *, contract: Mapping[str, Any],
    transcript: list[dict[str, Any]], evidence: Mapping[str, Any],
) -> None:
    artifacts = {"contract": contract, "transcript": transcript, "evidence": evidence}
    ids: set[str] = set()
    for finding in review["findings"]:
        if finding["id"] in ids:
            raise ValueError("blind review has duplicate finding IDs")
        ids.add(finding["id"])
        for citation in finding["citations"]:
            observed = _resolve_pointer(artifacts[citation["artifact"]], citation["pointer"])
            if observed != citation["quoted_value"]:
                raise ValueError("blind review citation does not exactly match artifact value")


def _validate_adjudication(
    adjudication: Mapping[str, Any], *, findings: list[Mapping[str, Any]],
) -> None:
    findings_by_id = {item["id"]: item for item in findings}
    finding_ids = list(findings_by_id)
    if len(finding_ids) != len(findings):
        raise ValueError("blind review has duplicate finding IDs")
    verdict_ids = [item["finding_id"] for item in adjudication["verdicts"]]
    if len(verdict_ids) != len(set(verdict_ids)) or set(verdict_ids) != set(finding_ids):
        raise ValueError("adjudicator must disposition every blind finding exactly once")
    for verdict in adjudication["verdicts"]:
        finding = findings_by_id[verdict["finding_id"]]
        required = (
            verdict["evidence_supported"] and verdict["material"] and finding["material"]
            and verdict["repository_independent"] and verdict["implementation_independent"]
            and not verdict["oracle_conflict"]
        )
        if verdict["approved"] != required:
            raise ValueError(
                "adjudication approval contradicts required evidence/material/independence gates"
            )


def _runtime_leakage_audit(
    *, run_dir: Path, repo_root: Path, issue: str, gold_patch: str
) -> list[dict[str, str]]:
    sentinels = patch_only_sentinels(gold_patch, public_issue_text=issue)
    filtered: dict[str, set[str]] = {kind: set() for kind in sentinels}
    for kind, values in sentinels.items():
        for value in values:
            found = subprocess.run(
                ["git", "grep", "-I", "-F", "-q", "--", value], cwd=repo_root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            ).returncode == 0
            if not found:
                filtered[kind].add(value)
    public_roles = {"repository-discovery", "evidence-auditor", "interviewer", "adversarial-reviewer"}
    findings = []
    for record_path in sorted((run_dir / "calls").glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record["role"] not in public_roles:
            continue
        for finding in audit_public_payload(record["prompt"], filtered, location=record_path.name):
            findings.append({"kind": finding.kind, "sentinel": finding.sentinel, "location": finding.location})
    return findings


def run_imported_case(
    *, public_case: Mapping[str, Any], sealed_source: Mapping[str, Any], cache: ContentAddressedCache,
    repo_root: Path, skill_md: str, run_dir: Path, stagnation_patience: int = 3,
    evaluator_rubric: str = DEFAULT_EVALUATOR_RUBRIC,
) -> dict[str, Any]:
    validate_case_pair(public_case, sealed_source)
    if sealed_source["review_state"]["status"] != "approved":
        raise ValueError("only independently approved imported cases may run")
    if stagnation_patience < 2:
        raise ValueError("stagnation_patience must be at least 2")
    run_dir.mkdir(parents=True, exist_ok=False)
    issue_descriptor = public_case["public_request"]
    issue = cache.get_text(issue_descriptor["cache_key"], issue_descriptor["digest"])
    model = CodexJsonModel(run_dir / "calls")
    discovery_payload = project_role_payload("repository-discovery", public_case=public_case, public_request_text=issue, runtime={"repository_root": str(repo_root.resolve())})
    discovery = model.generate(role="repository-discovery", instructions="Inspect only the supplied base-commit repository. Report issue-material existing facts with exact repository-relative line citations. Do not invent future requirements or owner choices.", payload=discovery_payload, schema=DISCOVERY_SCHEMA, readable_directories=(repo_root,))
    _validate_discovery(repo_root, discovery)
    _write(run_dir / "discovery.json", discovery)
    audit_payload = project_role_payload("evidence-auditor", public_case=public_case, public_request_text=issue, runtime={"discovery": discovery})
    fact_ids = [item["id"] for item in discovery["facts"]]
    audit = model.generate(
        role="evidence-auditor",
        instructions=(
            "Independently re-open every cited file and disposition every fact. Accept only direct "
            "support; never create product requirements. The complete fact-ID set is "
            f"{json.dumps(fact_ids)}. Return each of these IDs exactly once across accepted_fact_ids "
            "and rejected, and never return an ID outside this set."
        ),
        payload=audit_payload, schema=AUDIT_SCHEMA, readable_directories=(repo_root,),
    )
    evidence = _audited_evidence(discovery, audit)
    _write(run_dir / "evidence.json", evidence)
    transcript: list[dict[str, Any]] = []
    open_set_history: list[tuple[str, ...]] = []
    contract = None
    termination = "completed"
    turn = 1
    while True:
        payload = project_role_payload("interviewer", public_case=public_case, public_request_text=issue, runtime={"candidate_skill": skill_md, "audited_repository_evidence": evidence, "transcript": transcript})
        interview = model.generate(role="interviewer", instructions="Follow candidate_skill exactly. Continue until no material blocker remains; there is no arbitrary question budget. Ask exactly one structured question at a time. Repository evidence is already known and must not be delegated back to the owner. Complete only with an implementable contract.", payload=payload, schema=INTERVIEW_SCHEMA)
        _validate_interview(interview)
        if interview["action"] == "complete":
            contract = interview["contract"]
            transcript.append({"turn": turn, "interviewer": interview})
            break
        open_set = tuple(sorted(set(interview["open_material_decisions"])))
        open_set_history.append(open_set)
        owner_payload = project_role_payload("owner", public_case=public_case, public_request_text=issue, sealed_source=sealed_source, runtime={"question": interview["question"]})
        owner = model.generate(role="owner", instructions="Answer only the current question from the issue-time owner oracle. Do not volunteer unasked decisions or mention the oracle.", payload=owner_payload, schema=OWNER_SCHEMA)
        transcript.append({"turn": turn, "open_material_decisions": list(open_set), "question": interview["question"], "answer": owner["answer"]})
        if (
            len(open_set_history) >= stagnation_patience
            and len(set(open_set_history[-stagnation_patience:])) == 1
        ):
            termination = "stagnation"
            break
        turn += 1
    if contract is None:
        payload = project_role_payload("interviewer", public_case=public_case, public_request_text=issue, runtime={"candidate_skill": skill_md, "audited_repository_evidence": evidence, "transcript": transcript})
        forced = model.generate(role="interviewer", instructions="The interview stagnated. Return a non-ready contract that preserves every unresolved material blocker. Do not claim implementation readiness.", payload=payload, schema=INTERVIEW_SCHEMA)
        _validate_interview(forced)
        if forced["action"] != "complete" or forced["contract"]["implementation_ready"]:
            raise ValueError("stagnation close must produce a non-ready contract")
        contract = forced["contract"]
        transcript.append({"termination": termination, "interviewer": forced})
    _write(run_dir / "transcript.json", transcript)
    _write(run_dir / "contract.json", contract)
    review_payload = project_role_payload("adversarial-reviewer", public_case=public_case, public_request_text=issue, runtime={"transcript": transcript, "contract": contract, "audited_repository_evidence": evidence})
    citation_error = ""
    for attempt in range(3):
        retry = (
            f" Your prior citation was invalid: {citation_error}. Regenerate the complete review."
            if citation_error else ""
        )
        review = model.generate(
            role="adversarial-reviewer",
            instructions=(
                "Blindly review only public request, audited repository evidence, transcript, and contract. "
                "Use only the fixed failure taxonomy. Report material readiness failures with exact JSON-pointer "
                "citations to scalar leaves; do not quote arrays or objects and do not infer gold behavior. "
                "Citation artifact roots are exact: contract uses /summary, /implementation_ready, "
                "/confirmed_decisions/N, /open_material_decisions/N, or /acceptance_checks/N; transcript uses "
                "/N/...; evidence uses /scope_summary, /facts/N/..., /unknowns/N, or /audit_summary. Never cite "
                "/repository_facts or another public-case path as an evidence artifact."
                + retry
            ),
            payload=review_payload,
            schema=REVIEW_SCHEMA,
        )
        try:
            _validate_review_citations(
                review, contract=contract, transcript=transcript, evidence=evidence,
            )
            break
        except ValueError as exc:
            citation_error = str(exc)
            if attempt == 2:
                raise
    _write(run_dir / "blind-review.json", review)
    judge_payload = project_role_payload("judge", public_case=public_case, public_request_text=issue, sealed_source=sealed_source, runtime={"transcript": transcript, "contract": contract})
    judge = model.generate(
        role="judge",
        instructions=(
            "Compare observed interview and contract against audited public facts and the sealed "
            "issue-time decisions. Keep hindsight-only observations diagnostic. Score only the "
            "closed schema fields. Apply this frozen evaluator rubric exactly:\n"
            f"{evaluator_rubric}"
        ),
        payload={**judge_payload, "audited_repository_evidence": evidence}, schema=JUDGE_SCHEMA,
    )
    _write(run_dir / "judge.json", judge)
    adjudicator_payload = project_role_payload("adjudicator", public_case=public_case, public_request_text=issue, sealed_source=sealed_source, runtime={"transcript": transcript, "contract": contract, "findings": review["findings"]})
    adjudication_error = ""
    for attempt in range(3):
        retry = (
            f" Your prior adjudication was structurally invalid: {adjudication_error}. "
            "Regenerate the complete adjudication."
            if adjudication_error else ""
        )
        adjudication = model.generate(
            role="adjudicator",
            instructions=(
                "Disposition every blind finding independently. Approve only citation-supported material "
                "readiness failures, and state whether each is repository- and implementation-independent. "
                "Do not create replacement requirements. For every verdict, approved must equal exactly: "
                "evidence_supported AND verdict.material AND finding.material AND repository_independent AND "
                "implementation_independent AND NOT oracle_conflict. Disposition every finding exactly once."
                + retry
            ),
            payload={**adjudicator_payload, "audited_repository_evidence": evidence},
            schema=ADJUDICATION_SCHEMA,
        )
        try:
            _validate_adjudication(adjudication, findings=review["findings"])
            break
        except ValueError as exc:
            adjudication_error = str(exc)
            if attempt == 2:
                raise
    _write(run_dir / "adjudication.json", adjudication)
    gold_descriptor = sealed_source["inputs"]["gold_patch"]
    gold_patch = cache.get_text(gold_descriptor["cache_key"], gold_descriptor["digest"])
    runtime_leakage = _runtime_leakage_audit(
        run_dir=run_dir, repo_root=repo_root, issue=issue, gold_patch=gold_patch
    )
    runtime_audit = {
        "schema": "ImportedRuntimeIsolationAudit.v1", "contamination": 0,
        "leakage": len(runtime_leakage), "findings": runtime_leakage,
    }
    _write(run_dir / "runtime-audit.json", runtime_audit)
    if runtime_leakage:
        raise ValueError("public-role recorded input contains patch-only lexical leakage")
    manifest = {
        "schema": "NativeEvolutionImportedRun.v1", "alias": public_case["alias"],
        "partition": public_case["metadata"]["partition"], "model": "gpt-5.6-sol",
        "skill_sha256": hashlib.sha256(skill_md.encode()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(evaluator_rubric.encode()).hexdigest(),
        "case_sha256": artifact_digest(public_case), "sealed_source_sha256": artifact_digest(sealed_source),
        "roles": ["repository-discovery", "evidence-auditor", "interviewer", "owner", "adversarial-reviewer", "judge", "adjudicator"],
        "per_case_mutator_invoked": False, "termination_reason": termination,
        "artifact_sha256": {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest() for name in ("discovery.json", "evidence.json", "transcript.json", "contract.json", "blind-review.json", "judge.json", "adjudication.json", "runtime-audit.json")},
    }
    _write(run_dir / "run-manifest.json", manifest)
    return {"manifest": manifest, "judge": judge, "review": review, "adjudication": adjudication}


def replay_imported_judge(
    *, source_run: Path, public_case: Mapping[str, Any], sealed_source: Mapping[str, Any],
    cache: ContentAddressedCache, evaluator_rubric: str, evaluator_sha256: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Rejudge immutable interview artifacts without regenerating the interview.

    The evaluator rubric affects only ``judge.json`` in the imported-case
    pipeline.  This replay verifies the source evidence by digest, reconstructs
    the original judge payload, and writes a separate derived artifact tree.
    """

    validate_case_pair(public_case, sealed_source)
    expected_identity = hashlib.sha256(evaluator_rubric.encode()).hexdigest()
    if evaluator_sha256 != expected_identity:
        raise ValueError("replay evaluator identity does not match rubric bytes")
    manifest_path = source_run / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("alias") != public_case["alias"]:
        raise ValueError("replay source alias does not match public case")
    if manifest.get("case_sha256") != artifact_digest(public_case):
        raise ValueError("replay source public-case digest drifted")
    if manifest.get("sealed_source_sha256") != artifact_digest(sealed_source):
        raise ValueError("replay source sealed-source digest drifted")
    immutable_names = ("discovery.json", "evidence.json", "transcript.json", "contract.json")
    immutable_digests: dict[str, str] = {}
    for name in immutable_names:
        path = source_run / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get("artifact_sha256", {}).get(name) != digest:
            raise ValueError(f"replay source artifact digest drifted: {name}")
        immutable_digests[name] = digest
    output_dir.mkdir(parents=True, exist_ok=False)
    issue_descriptor = public_case["public_request"]
    issue = cache.get_text(issue_descriptor["cache_key"], issue_descriptor["digest"])
    transcript = json.loads((source_run / "transcript.json").read_text(encoding="utf-8"))
    contract = json.loads((source_run / "contract.json").read_text(encoding="utf-8"))
    evidence = json.loads((source_run / "evidence.json").read_text(encoding="utf-8"))
    judge_payload = project_role_payload(
        "judge", public_case=public_case, public_request_text=issue,
        sealed_source=sealed_source, runtime={"transcript": transcript, "contract": contract},
    )
    model = CodexJsonModel(output_dir / "calls")
    judge = model.generate(
        role="judge",
        instructions=(
            "Compare observed interview and contract against audited public facts and the sealed "
            "issue-time decisions. Keep hindsight-only observations diagnostic. Score only the "
            "closed schema fields. Apply this frozen evaluator rubric exactly:\n"
            f"{evaluator_rubric}"
        ),
        payload={**judge_payload, "audited_repository_evidence": evidence}, schema=JUDGE_SCHEMA,
    )
    _write(output_dir / "judge.json", judge)
    replay_manifest = {
        "schema": "ImportedEvaluatorReplay.v1",
        "alias": manifest["alias"],
        "partition": manifest["partition"],
        "model": manifest["model"],
        "source_run_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_skill_sha256": manifest["skill_sha256"],
        "source_evaluator_sha256": manifest["evaluator_sha256"],
        "replay_evaluator_sha256": evaluator_sha256,
        "raw_artifact_sha256": immutable_digests,
        "judge_sha256": hashlib.sha256((output_dir / "judge.json").read_bytes()).hexdigest(),
    }
    _write(output_dir / "replay-manifest.json", replay_manifest)
    return {"manifest": replay_manifest, "judge": judge}


def replay_recorded_judge(
    *, source_run: Path, evaluator_rubric: str, evaluator_sha256: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay the exact recorded judge payload when the corpus has since rotated."""

    expected_identity = hashlib.sha256(evaluator_rubric.encode()).hexdigest()
    if evaluator_sha256 != expected_identity:
        raise ValueError("replay evaluator identity does not match rubric bytes")
    manifest_path = source_run / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    immutable_names = ("discovery.json", "evidence.json", "transcript.json", "contract.json")
    immutable_digests: dict[str, str] = {}
    raw_values: dict[str, Any] = {}
    for name in immutable_names:
        path = source_run / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get("artifact_sha256", {}).get(name) != digest:
            raise ValueError(f"replay source artifact digest drifted: {name}")
        immutable_digests[name] = digest
        raw_values[name] = json.loads(path.read_text(encoding="utf-8"))
    judge_records = []
    for path in sorted((source_run / "calls").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("role") == "judge":
            judge_records.append((path, record))
    if len(judge_records) != 1:
        raise ValueError("source run must contain exactly one recorded judge call")
    record_path, record = judge_records[0]
    payload = record.get("input")
    if not isinstance(payload, dict):
        raise ValueError("recorded judge payload is invalid")
    for field, name in (
        ("transcript", "transcript.json"), ("contract", "contract.json"),
        ("audited_repository_evidence", "evidence.json"),
    ):
        if payload.get(field) != raw_values[name]:
            raise ValueError(f"recorded judge payload drifted from {name}")
    upstream = payload.get("upstream")
    if not isinstance(upstream, dict):
        raise ValueError("recorded judge payload has invalid upstream identity")
    reconstructed_public = {
        "schema": "InterviewerSafeCase.v1",
        "alias": payload.get("alias"),
        "upstream": upstream,
        "public_request": {
            "cache_key": upstream.get("issue_cache_key"),
            "digest": upstream.get("issue_digest"),
        },
        "repository_facts": payload.get("repository_facts"),
        "metadata": payload.get("metadata"),
        "sealed_source_digest": manifest.get("sealed_source_sha256"),
    }
    reconstructed_sealed = {
        "schema": "SealedSWEbenchSource.v1",
        "alias": payload.get("alias"),
        "inputs": payload.get("sealed_inputs"),
        "evidence": payload.get("sealed_evidence"),
        "material_decisions": payload.get("material_decisions"),
        "hindsight_observations": payload.get("hindsight_observations"),
        "implementation_incidentals": payload.get("implementation_incidentals"),
        "review_state": payload.get("review_state"),
    }
    if artifact_digest(reconstructed_public) != manifest.get("case_sha256"):
        raise ValueError("recorded judge payload public case identity drifted")
    if artifact_digest(reconstructed_sealed) != manifest.get("sealed_source_sha256"):
        raise ValueError("recorded judge payload sealed source identity drifted")
    output_dir.mkdir(parents=True, exist_ok=False)
    model = CodexJsonModel(output_dir / "calls")
    judge = model.generate(
        role="judge",
        instructions=(
            "Compare observed interview and contract against audited public facts and the sealed "
            "issue-time decisions. Keep hindsight-only observations diagnostic. Score only the "
            "closed schema fields. Apply this frozen evaluator rubric exactly:\n"
            f"{evaluator_rubric}"
        ),
        payload=payload, schema=JUDGE_SCHEMA,
    )
    _write(output_dir / "judge.json", judge)
    replay_manifest = {
        "schema": "ImportedEvaluatorReplay.v1",
        "alias": manifest["alias"], "partition": manifest["partition"],
        "model": manifest["model"],
        "source_run_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_judge_call_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
        "source_skill_sha256": manifest["skill_sha256"],
        "source_evaluator_sha256": manifest["evaluator_sha256"],
        "replay_evaluator_sha256": evaluator_sha256,
        "raw_artifact_sha256": immutable_digests,
        "judge_sha256": hashlib.sha256((output_dir / "judge.json").read_bytes()).hexdigest(),
    }
    _write(output_dir / "replay-manifest.json", replay_manifest)
    return {"manifest": replay_manifest, "judge": judge}


def authenticate_recorded_judge_payload(source_run: Path) -> tuple[Path, dict[str, Any]]:
    """Authenticate every public and sealed field in a recorded judge call."""

    manifest = json.loads((source_run / "run-manifest.json").read_text(encoding="utf-8"))
    records = []
    for path in sorted((source_run / "calls").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("role") == "judge":
            records.append((path, record))
    if len(records) != 1 or not isinstance(records[0][1].get("input"), dict):
        raise ValueError("source run must contain exactly one valid recorded judge call")
    path, record = records[0]
    payload = record["input"]
    for field, name in (
        ("transcript", "transcript.json"), ("contract", "contract.json"),
        ("audited_repository_evidence", "evidence.json"),
    ):
        if payload.get(field) != json.loads((source_run / name).read_text(encoding="utf-8")):
            raise ValueError(f"recorded judge payload drifted from {name}")
    upstream = payload.get("upstream")
    if not isinstance(upstream, dict):
        raise ValueError("recorded judge payload has invalid upstream identity")
    public = {
        "schema": "InterviewerSafeCase.v1", "alias": payload.get("alias"),
        "upstream": upstream,
        "public_request": {"cache_key": upstream.get("issue_cache_key"), "digest": upstream.get("issue_digest")},
        "repository_facts": payload.get("repository_facts"), "metadata": payload.get("metadata"),
        "sealed_source_digest": manifest.get("sealed_source_sha256"),
    }
    sealed = {
        "schema": "SealedSWEbenchSource.v1", "alias": payload.get("alias"),
        "inputs": payload.get("sealed_inputs"), "evidence": payload.get("sealed_evidence"),
        "material_decisions": payload.get("material_decisions"),
        "hindsight_observations": payload.get("hindsight_observations"),
        "implementation_incidentals": payload.get("implementation_incidentals"),
        "review_state": payload.get("review_state"),
    }
    if artifact_digest(public) != manifest.get("case_sha256"):
        raise ValueError("recorded judge payload public case identity drifted")
    if artifact_digest(sealed) != manifest.get("sealed_source_sha256"):
        raise ValueError("recorded judge payload sealed source identity drifted")
    return path, payload
