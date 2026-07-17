# Ultimateinterview JSON Contracts

This is the canonical cross-skill format reference for compiler-only Ultimateinterview sessions. Producers and consumers must fail closed on unknown schema identifiers, missing required fields, duplicate IDs, invalid references, digest mismatches, or malformed JSON/JSONL. Repository evidence is never authority.

All JSON files are UTF-8. Compiler-produced JSON is deterministic, two-space-indented, and ends with exactly one newline. JSONL uses one compact JSON object per nonblank line and ends with one newline.

## Session layout

```text
.ultimateinterview/<session>/
  execution-contract.md          # unsealed four-section contract with mandatory DEC manifest in v3; absent only in legacy sessions
  evidence-map.md                # compact observed evidence for the one-time handoff check, optional for legacy sessions
  authority-reconciliation.json # owner-approved reconciliation input
  authority-register.json       # sealed native Authority Register
  discovery-record.json         # unsealed compiler input bound to the register
  build-contract.json           # sealed normative output
  implementation-plan-draft.json # unsealed derived planning input
  implementation-plan.json     # compiled non-normative plan bound to the contract
  decision.jsonl                # digest-bound implementation gap evidence, optional
  compiler-evidence-bundle.json # postmortem-owned validated projection
  postmortem.md                 # independent evaluator report, optional
```

## Workflow routing record

Every new `evidence-map.md` starts with a `Workflow Path` record naming exactly one of `lightweight`, `standard`, or `high-risk`, followed by concise evidence-backed reasons. This record is process evidence, not product authority, and is not copied into the Authority Register or Build Contract.

`lightweight` is fail-closed: every eligibility condition in `SKILL.md` must be established, it must be rechecked against the compiled Build Contract and Implementation Plan, and any unknown or violated condition upgrades the session to `standard` or `high-risk`. Lightweight sessions skip only the fresh-context reviewer. They still produce and validate all compiler inputs, the sealed Build Contract, the projection result, and the digest-bound Implementation Plan. Standard and high-risk sessions require the path-defined fresh review. Every path preserves the same session lineage consumed by `ultimateinterview-postmortem`; no path may replace these portable artifacts with vendor-, model-, UI-, or orchestrator-specific state.

## Canonical digest algorithm

Canonical JSON is `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"`, encoded as UTF-8 and hashed with SHA-256.

- `source_discovery_digest`: canonical digest of the complete Discovery Record.
- `contract_digest`: canonical digest of the complete Build Contract after removing only its top-level `contract_digest` field.
- `authority_register_digest`: canonical digest of the complete Authority Register after removing only its top-level `authority_register_digest` field.
- Acceptance binding digest: owned by `authority_compiler.py`; consumers must verify by recompiling rather than reproducing a partial algorithm.

Formatting does not affect these canonical content digests.

## Material decision projection manifest

The `Decisions & Defaults` section of every new `execution-contract.md` contains exactly one fenced JSON block whose info string is `ultimateinterview-material-decisions`. It is the deterministic source for projection checking, not a separate artifact:

````text
```ultimateinterview-material-decisions
{
  "schema": "ultimateinterview.material-decisions.v2",
  "decisions": [
    {
      "id": "DEC-001",
      "statement": "Exact atomic normative obligation.",
      "choice": "explicit",
      "authority_ref": "AUTH-001",
      "requirement_ref": "REQ-001",
      "applicable_boundary": ["normalized/scope"],
      "acceptance_refs": ["ACC-001"],
      "verification_refs": ["VER-001"]
    }
  ]
}
```
````

The manifest is closed and nonempty, and it is the only content allowed in `Decisions & Defaults`; prose decisions outside it fail the gate. IDs match `DEC-NNN`, remain stable within the session, and are unique. `choice` is `explicit` only with active owner-decision or canonical-contract authority and `delegated-default` only with active bounded-delegation authority. `ultimateinterview.material-decisions.v1` remains accepted only to validate already sealed legacy sessions.

The `statement` is an atomic projection anchor and one postmortem verdict unit. In v2, each decision maps to a dedicated requirement that no other decision may reference. That requirement names exactly the decision's one authority, and the union of its `constraints` and `preserved_behaviors` is exactly `{statement}`; either array may be empty. `applicable_boundary` exactly equals the requirement scope. The acceptance and verification references cover every and only those attached to the requirement, and the compiler trace contains every applicable authority-requirement-acceptance-verification row. Missing, invented, shared, or compound requirement projections fail closed.

After reconciliation and compilation, run:

```text
python3 scripts/projection_check.py <execution-contract.md> --discovery <discovery-record.json> --authority-register <authority-register.json> --build-contract <build-contract.json>
```

The gate strictly parses the manifest, revalidates the Authority Register, freshly recompiles Discovery, requires structural equality with the sealed Build Contract, and validates the complete decision lineage. Its result includes `decision_requirements` and `legacy_shared_requirements` so postmortems can disclose coarse v1 verdict units. It writes nothing. Legacy sessions without `execution-contract.md` remain compiler-auditable, but no new v3 session may hand off implementation until this gate passes.

## Authority reconciliation

Before creating Discovery, write `authority-reconciliation.json` with schema
`ultimateinterview.authority-reconciliation-input.v1`, then run:

```text
python3 scripts/authority_reconcile.py <authority-reconciliation.json> --output <authority-register.json>
```

The input contains exactly `schema`, `owner_approval`, `authorities`, `conflicts`, and
`unresolved_decisions`. `owner_approval` contains exactly `id`, `owner`, `source`,
`statement`, `approval_authority_ref`, `approved_authority_refs`, and
`approved_conflict_refs`. Its approval authority must be an active `owner-decision`
owned by `owner`, and its approved authority and conflict references must cover the
complete register exactly. Reconciliation fails while any unresolved decision or
authority conflict remains. Evidence, model, and corpus identifiers (`E-`, `EVID-`,
`EVIDENCE-`, `M-`, `MODEL-`, `C-`, or `CORPUS-`) cannot be authority IDs or clause
authority references.

`authority_reconcile.py` is the sole native reconciliation CLI. It writes
`ultimateinterview.authority-register.v1` with exactly `schema`, `owner_approval`,
`authorities`, `conflicts`, and `authority_register_digest`, using two-space UTF-8 JSON
and one LF. It never replaces its output on failure. Discovery copies the reconciled
authorities and conflicts unchanged and binds `authority_register_digest`; the compiler
requires `--authority-register <authority-register.json>` and rejects any mismatch.

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
  "authority_register_digest": "64 lowercase hex",
  "evidence": ["Evidence"],
  "requirements": ["Requirement Clause"],
  "acceptance_predicates": ["AcceptancePredicate"],
  "verifications": ["Verification"],
  "trace": ["TraceRow"],
  "unresolved_decisions": ["UnresolvedDecision"],
  "conflicts": ["Conflict"]
}
```

A Clause contains `id` when used in arrays, plus `text`, `decision_class`, nonempty `scope`, `constraints`, `preserved_behaviors`, `authority_refs`, and `evidence_refs`. Goal, scope, and non-goal clauses keep both obligation arrays nonempty and exactly retain their referenced authorities. A requirement may leave either obligation array empty, but their union must be nonempty and contain only authorized obligations. Across all requirements, every obligation from every referenced authority must remain covered. A requirement additionally contains `acceptance_bindings`, each with `acceptance_ref` and a 64-lowercase-hex `digest`.

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
Compile only with the reconciled register:

```text
python3 scripts/authority_compiler.py <discovery-record.json> --authority-register <authority-register.json> --output <build-contract.json>
```

```json
{
  "implementation_decision_policy": {
    "log_path": ".ultimateinterview/<session>/decision.jsonl",
    "instruction": "for a permitted arbitrary contract-gap decision, choose the simplest option that works within the contract and applicable bounded delegation, then log it before acting",
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

## Implementation Plan

`implementation-plan-draft.json` uses schema `ultimateinterview.implementation-plan-draft.v1` and contains exactly:

```json
{
  "schema": "ultimateinterview.implementation-plan-draft.v1",
  "contract_digest": "64 lowercase hex",
  "approach": {
    "summary": "recommended implementation approach",
    "rationale": "why this approach fits the contract and repository"
  },
  "decisions": [
    {
      "id": "IMP-001",
      "statement": "one material internal implementation choice",
      "delegation_ref": "AUTH-DELEGATION",
      "requirement_refs": ["REQ-001"],
      "acceptance_refs": ["ACC-001"],
      "verification_refs": ["VER-001"],
      "affected_surfaces": ["src/component.py"],
      "rationale": "why this delegated choice is recommended",
      "alternatives": ["material alternative considered"],
      "observable_impact": "none beyond the Build Contract"
    }
  ],
  "steps": [
    {
      "id": "STEP-001",
      "summary": "implement one dependency-ordered unit",
      "depends_on": [],
      "decision_refs": ["IMP-001"],
      "requirement_refs": ["REQ-001"],
      "acceptance_refs": ["ACC-001"],
      "verification_refs": ["VER-001"],
      "affected_surfaces": ["src/component.py", "tests/test_component.py"]
    }
  ],
  "test_realization": [
    {
      "verification_ref": "VER-001",
      "working_directory": "repository root",
      "target": "tests/test_component.py",
      "procedure": "exact command or scenario including isolation and selection semantics",
      "expected_result": "byte-identical Build Contract verification result"
    }
  ],
  "return_to_owner_conditions": [
    "observable behavior not authorized by the Build Contract",
    "required work outside an applicable bounded delegation",
    "a verification cannot objectively determine its acceptance predicate",
    "the recommended approach is infeasible without changing the Build Contract"
  ]
}
```

The draft is closed and nonempty: at least one `IMP-NNN`, one `STEP-NNN`, and one test-realization row are required. Every implementation decision uses an active entry in `bounded_implementation_delegations`; repository evidence and model preference cannot replace delegation. `affected_surfaces` are normalized repository-relative paths or stable named components without absolute paths, traversal, dot segments, backslashes, or wildcards. `observable_impact` is the exact literal `none beyond the Build Contract`; anything else returns to the owner.

Decision, step, acceptance, and verification references must exist and remain requirement-consistent. Every decision is consumed by a step. Across all steps, every and only Build Contract requirement, acceptance, and verification is covered. `depends_on` names earlier or later steps as a directed acyclic graph; unknown, self, duplicate, or cyclic dependencies fail closed. `test_realization` contains every and only contract verification once, and its `expected_result` is byte-identical to that verification's expected result. Working directory, target, and procedure are all required and nonempty. The return-to-owner list is fixed and exact.

Compile from the skill directory:

```text
python3 scripts/implementation_plan.py <implementation-plan-draft.json> --build-contract <build-contract.json> --output <implementation-plan.json>
```

The compiler validates the complete Build Contract digest, normalizes the closed draft, replaces `schema` with `ultimateinterview.implementation-plan.v1`, adds `plan_digest`, and writes deterministic two-space UTF-8 JSON with one LF. `plan_digest` is the canonical SHA-256 of the complete compiled plan after removing only `plan_digest`. The compiled plan is derived guidance, not authority, and may be replaced without recompiling the Build Contract only while the same contract digest remains valid. Consumers validate an on-disk plan and its complete structural equality with a fresh compile by running `python3 scripts/implementation_plan.py <implementation-plan.json> --build-contract <build-contract.json> --check`.

## Compiler Postmortem Evidence Bundle

Schema identifier: `ultimateinterview.compiler-postmortem-evidence.v1`. It is produced by `ultimateinterview-postmortem/scripts/compiler_session_check.py` and contains:

```json
{
  "schema": "ultimateinterview.compiler-postmortem-evidence.v1",
  "session_dir": "absolute session path",
  "contract_digest": "verified digest",
  "contract_sha256": "on-disk artifact hash",
  "discovery_sha256": "on-disk hash or null",
  "authority_register_sha256": "on-disk artifact hash",
  "projection_gate": "validated material-decision summary or null for a legacy session",
  "ids": {
    "requirements": ["REQ-ID"],
    "acceptances": ["ACC-ID"],
    "verifications": ["VER-ID"],
    "authorities": ["AUTH-ID"]
  },
  "scope_paths": ["normalized repository path"],
  "build_contract": "verified complete Build Contract object",
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
