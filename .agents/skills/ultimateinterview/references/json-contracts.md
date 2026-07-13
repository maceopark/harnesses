# Ultimateinterview JSON Contracts

This is the canonical cross-skill format reference for compiler-only Ultimateinterview sessions. Producers and consumers must fail closed on unknown schema identifiers, missing required fields, duplicate IDs, invalid references, digest mismatches, or malformed JSON/JSONL. Repository evidence and implementation self-reports are never authority.

All JSON files are UTF-8. Compiler-produced JSON is deterministic, two-space-indented, and ends with exactly one newline. JSONL uses one compact JSON object per nonblank line and ends with one newline.

## Session layout

```text
.ultimateinterview/<session>/
  discovery-record.json       # unsealed compiler input
  build-contract.json         # sealed normative output
  decision.jsonl              # digest-bound implementation gap evidence, optional
  implementation-return.json  # digest-bound implementer self-report, optional
  compiler-evidence-bundle.json # postmortem-owned validated projection
  postmortem.md               # independent evaluator report, optional
```

## Canonical digest algorithm

Canonical JSON is `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"`, encoded as UTF-8 and hashed with SHA-256.

- `source_discovery_digest`: canonical digest of the complete Discovery Record.
- `contract_digest`: canonical digest of the complete Build Contract after removing only its top-level `contract_digest` field.
- Acceptance binding digest: owned by `authority_compiler.py`; consumers must verify by recompiling rather than reproducing a partial algorithm.

Formatting does not affect these canonical content digests.

## Discovery Record

Schema identifier: `ultimateinterview.discovery-record.v1`.

Top-level required fields:

```json
{
  "schema": "ultimateinterview.discovery-record.v1",
  "goal": "Clause without id",
  "scope": ["Clause with id and decision_class=scope"],
  "non_goals": ["Clause with id and decision_class=non-goals"],
  "authorities": ["Authority"],
  "evidence": ["Evidence"],
  "requirements": ["Requirement Clause"],
  "acceptance_predicates": ["AcceptancePredicate"],
  "verifications": ["Verification"],
  "trace": ["TraceRow"],
  "unresolved_decisions": ["UnresolvedDecision"],
  "conflicts": ["Conflict"]
}
```

A Clause contains `id` when used in arrays, plus `text`, `decision_class`, nonempty `scope`, nonempty `constraints`, nonempty `preserved_behaviors`, `authority_refs`, and `evidence_refs`. A requirement additionally contains `acceptance_bindings`, each with `acceptance_ref` and a 64-lowercase-hex `digest`.

An Authority contains:

```json
{
  "id": "AUTH-ID",
  "kind": "owner-decision | canonical-contract | bounded-delegation",
  "status": "active | inactive | revoked | superseded",
  "source": {"uri": "stable source", "version": "version"},
  "scope": ["normalized scope item"],
  "constraints": ["mandatory constraint"],
  "preserved_behaviors": ["mandatory behavior"],
  "decision_classes": ["covered decision class"],
  "statement": "authorized statement",
  "supersedes": [],
  "conflicts_with": []
}
```

Kind-specific required fields are `owner` for `owner-decision`; `canonical_artifact`, `applicability`, and nonnegative `precedence` for `canonical-contract`; and `delegate` plus `delegation_boundary` for `bounded-delegation`. A delegation boundary contains `kind` (`repository-paths` or `named-component`), nonempty `includes`, and nonempty `excludes`.

Evidence contains `id`, `kind`, `source {uri, version}`, and `summary`. Evidence IDs may appear only in `evidence_refs`, never `authority_refs`.

Acceptance predicates contain exactly:

```json
{
  "id": "ACC-ID",
  "requirement_ref": "REQ-ID",
  "precondition": "state before action",
  "input": "input or trigger",
  "action": "operation",
  "observable_result": "authorized success/observable result",
  "failure_result": "authorized applicable failure result"
}
```

Verifications contain `id`, `requirement_ref`, nonempty `acceptance_refs`, `method` (`command`, `scenario`, or `inspection`), `procedure`, and `expected_result`. The expected result must equal an authorized acceptance `observable_result` or `failure_result`.

Each TraceRow contains `authority_ref`, `requirement_ref`, `acceptance_ref`, and `verification_ref`. The trace must contain every compiler-required cross-product and no unrelated row.

Compilation is prohibited while `unresolved_decisions` contains any row or any conflict remains unresolved.

## Build Contract

Schema identifier: `ultimateinterview.build-contract.v1`. Only `authority_compiler.py` may produce this file. Its first serialized key is always `implementation_decision_policy`.

```json
{
  "implementation_decision_policy": {
    "log_path": ".ultimateinterview/<session>/decision.jsonl",
    "instruction": "log a forced contract-gap decision before acting",
    "required_fields": [
      "contract_digest",
      "requirement_refs",
      "gap",
      "decision",
      "rationale",
      "alternatives",
      "affected_paths",
      "observable_impact"
    ],
    "authority_boundary": "the log is evidence, not authority; owner-only or out-of-delegation decisions stop implementation"
  },
  "schema": "ultimateinterview.build-contract.v1",
  "source_discovery_digest": "64 lowercase hex",
  "goal": "normalized Clause",
  "scope": ["normalized Clause"],
  "non_goals": ["normalized Clause"],
  "authorities": ["normalized Authority"],
  "requirements": ["normalized Requirement Clause"],
  "bounded_implementation_delegations": ["active normalized delegation"],
  "acceptance_predicates": ["normalized AcceptancePredicate"],
  "verifications": ["normalized Verification"],
  "trace": ["normalized TraceRow"],
  "unresolved_decisions": [],
  "contract_digest": "64 lowercase hex"
}
```

The Build Contract is the sole normative implementation input. A consumer must verify `contract_digest`; when `discovery-record.json` is available, it must also recompile and require structural equality.

## Implementation decision log

File: `decision.jsonl`. Each line contains exactly:

```json
{"contract_digest":"64 lowercase hex","requirement_refs":["REQ-ID"],"gap":"what the contract did not decide","decision":"internal decision taken","rationale":"why it was necessary","alternatives":["considered alternative"],"affected_paths":["normalized/repository/path"],"observable_impact":"none, or the exact impact"}
```

`contract_digest` must match the current sealed contract and every requirement reference must exist. The log is evidence only. A user-visible, policy, scope, lifecycle, failure, compatibility, data-loss, or out-of-delegation gap must stop implementation and return to the owner; recording it does not authorize proceeding.

## Implementation Return

Schema identifier: `ultimateinterview.implementation-return.v1`.

Required fields:

```json
{
  "schema": "ultimateinterview.implementation-return.v1",
  "contract_digest": "64 lowercase hex",
  "status": "implemented | blocked | failed",
  "changed_repository_paths": ["normalized/repository/path"],
  "requirement_outcomes": {"REQ-ID": "passed | failed | blocked | not-run with evidence"},
  "verification_outcomes": {"VER-ID": "passed | failed | blocked | not-run with evidence"},
  "commands": [{"command": "exact command", "result": "observed result"}],
  "existing_evidence_artifacts": ["repository-relative path"],
  "non_contract_implementation_decisions": ["decision.jsonl reference or structured summary"],
  "not_run": ["honest missing lane"],
  "blocked": ["blocked item"],
  "failed": ["failed item"]
}
```

The return is implementer-authored evidence, not authority or final evaluation. Postmortem consumers must reject a digest mismatch and must not upgrade self-reported `passed` to observed success without direct verification evidence.

## Compiler Postmortem Evidence Bundle

Schema identifier: `ultimateinterview.compiler-postmortem-evidence.v1`. It is produced by `ultimateinterview-postmortem/scripts/compiler_session_check.py` and contains:

```json
{
  "schema": "ultimateinterview.compiler-postmortem-evidence.v1",
  "session_dir": "absolute session path",
  "contract_digest": "verified digest",
  "contract_sha256": "on-disk artifact hash",
  "discovery_sha256": "on-disk hash or null",
  "ids": {
    "requirements": ["REQ-ID"],
    "acceptances": ["ACC-ID"],
    "verifications": ["VER-ID"],
    "authorities": ["AUTH-ID"]
  },
  "scope_paths": ["normalized repository path"],
  "build_contract": "verified complete Build Contract object",
  "implementation_return": "digest-bound object or null",
  "decisions": ["validated decision records"],
  "repository_evidence": {
    "source": "diff source",
    "diff": "scoped diff text",
    "status": "scoped git status",
    "files": [{"path": "path", "sha256": "hash", "size": 0, "text": "bounded UTF-8 text or null"}]
  },
  "missing_evidence": ["explicit missing evidence statement"]
}
```

The bundle is evaluator-owned evidence. It never changes the Build Contract and never authorizes implementation behavior.
