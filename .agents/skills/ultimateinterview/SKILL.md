---
name: ultimateinterview
description: Agent-agnostic material-decision interview and implementation planning for brownfield software changes. Use when a developer wants a fast, evidence-grounded Build Contract plus a fresh-context-ready implementation plan before coding; especially for unclear feature or bugfix behavior, requirements gaps, acceptance criteria, non-goals, edge cases, misuse cases, PRDs, specs, or implementation handoffs.
---

# Ultimateinterview

Produce a small, authorized, verifiable execution contract and a derived implementation plan. Ground briefly, ask only decisions that can materially change implementation, compile the contract, plan the implementation within bounded delegation, run one fresh handoff check, then finalize, print a copy-ready implementation prompt, and stop.

Evidence describes current state; it does not authorize new behavior. Only an explicit `owner-decision`, an applicable `canonical-contract`, or a `bounded-delegation` may authorize a normative decision. A delegated default is a choice made under bounded delegation, never an authority kind.

Keep all session artifacts under `.ultimateinterview/<session>/`. Use `execution-contract.md` as the single human-facing contract and `evidence-map.md` as its compact observed-evidence input. Both remain unsealed. Only compiler-produced `build-contract.json` is normative. Compiler-produced `implementation-plan.json` is digest-bound derived guidance, never authority.

## 1. Minimum Grounding

Skip repository grounding for a genuinely greenfield request when the user supplied the governing behavior and success criteria. For brownfield work, inspect the nearest two or three governing surfaces first: applicable instructions, the affected entrypoint, and the closest contract or test.

Follow another direct dependency only when it could change a current material decision, contract boundary, or verification path. Do not broaden the search for vague completeness. Before asking the owner for a repository fact, inspect it.

Write a compact evidence map containing only:

- a stable evidence ID;
- the exact source or repository path;
- the observed fact;
- why that fact can affect the contract.

The map records what was observed, not a claim of discovery completeness or product authority.

## 2. Fast-Path Decision

After minimum grounding, proceed without owner questions when the request and observed evidence admit no materially different interpretation of:

- observable behavior;
- scope and boundaries;
- applicable failure results; or
- success and verification.

The user's explicit request may authorize what it actually states. Do not expand it into unstated behavior.

## 3. Material Decision Loop

Investigate repository facts yourself. Ask the owner only when different answers can change at least one of:

- observable behavior;
- authorization, data safety, or an irreversible result;
- ownership or an interface boundary; or
- acceptance or verification.

Use the runtime's structured question interface for every owner question when available. Present concrete choices as a multi-select that allows one or more selections, and mark exactly one supported choice as recommended and preselected. Keep selectable combinations compatible; ask dependent decisions one at a time and group only independent decisions. Offer that recommendation only when repository evidence, an applicable canonical contract, or a strong reversible convention supports it. The preselection remains a proposal and is not an owner decision until the owner submits it. If the runtime lacks multi-select or preselection, use the closest available structured control, put the recommended choice first and label it clearly, state the capability limitation, and do not silently fall back to an unstructured prose question.

Use three material owner decisions as a soft reassessment point, not a question-message limit, hard cap, or quota. Clarifications of the same decision do not count again. After the third decision is resolved, continue only for a remaining material blocker under the criteria above.

Apply the safest reversible default only to internal choices covered by an explicit bounded delegation. Never invent observable behavior, authorization, retry or recovery, retention, compatibility, migration, or API/protocol semantics as a default.

Use this termination test throughout:

> Within stated delegations and tolerances, could two plausibly compliant implementations differ on a material observable outcome or on whether success is achieved?

If yes, resolve only the authority or decision causing that difference. If no, stop interviewing. If required authority is unavailable, finish as `incomplete` rather than guessing.

## 4. Small Execution Contract

Write `execution-contract.md` with exactly four substantive sections:

1. `Outcome & Boundaries` — outcome, in-scope boundaries, and non-goals.
2. `Decisions & Defaults` — one closed `ultimateinterview-material-decisions` JSON block containing each normative decision, applicable boundary, authority, compiler lineage references, and `choice: explicit | delegated-default`.
3. `Acceptance` — each predicate as `precondition/input -> action -> observable success -> applicable failure result`.
4. `Verification` — context-complete commands or scenarios with working directory, target, and the acceptance predicate verified.

Do not create a separate interview ledger, ambiguity score, transcript snapshot, approval brief, or duplicated human-authored Authority Register. Treat the small contract as the human source of truth. When the current compiler requires normalized Discovery and Authority Register JSON, project the inline authority and contract data into those machine artifacts without asking the owner to restate it or adding decisions.

Assign stable `DEC-NNN` IDs and do not renumber them within a session. Use `ultimateinterview.material-decisions.v2` for every new contract. Treat each decision as one independently adjudicable postmortem verdict unit: if two clauses could be fulfilled or diverge independently, split them before compilation. Map each `DEC-NNN` to exactly one dedicated `REQ-NNN`, exactly one applicable authority, and that requirement's complete acceptance and verification rows; never map two decisions to the same requirement. The requirement's combined `constraints` and `preserved_behaviors` must contain exactly the byte-identical decision `statement`, with either array allowed to be empty. Across the requirement set, retain every obligation from each referenced authority. The projection gate enforces these atomicity and coverage rules; v1 manifests are legacy validation inputs only.

## 5. Compile the Candidate Contract

Before creating compiler JSON, read `references/json-contracts.md`. Generate the compiler inputs from the accepted small contract, then run from this skill directory:

```text
python3 scripts/authority_reconcile.py <authority-reconciliation.json> --output <authority-register.json>
python3 scripts/authority_compiler.py <discovery-record.json> --authority-register <authority-register.json> --output <build-contract.json>
python3 scripts/projection_check.py <execution-contract.md> --discovery <discovery-record.json> --authority-register <authority-register.json> --build-contract <build-contract.json>
```

Do not hand-author, edit, or post-process the sealed output. Compiler or projection-gate failure means the contract is not ready: correct only the projection, resolve missing authority, or finish incomplete. The gate must prove complete `material decision -> authority -> requirement -> acceptance -> verification` traceability and structural equality with a fresh compile before implementation planning.

## 6. Implementation Planning

Treat the Build Contract as immutable product intent. Inspect the affected implementation surfaces and produce `implementation-plan-draft.json` using the closed format in `references/json-contracts.md`. Do not repeat the behavioral interview or ask the owner for repository facts. Ask the owner only when planning exposes a new observable, policy, scope, lifecycle, failure, compatibility, data-loss, ownership, or out-of-delegation decision; return that gap to the Material Decision Loop and compile a new contract before continuing.

Record each material internal choice as `IMP-NNN`. Every choice must cite one active bounded delegation, the contract requirements, acceptances, and verifications it realizes, the affected repository paths or stable named components, its rationale and alternatives, and `observable_impact: none beyond the Build Contract`. A plan may not use consensus, evidence, convention, or model preference as delegation.

Write dependency-ordered `STEP-NNN` rows covering every contract requirement, acceptance, verification, and implementation decision. Include exact affected surfaces and a context-complete test realization for every verification. Stop planning only when a fresh implementer can execute the approach, boundaries, sequence, and verification without making another material internal decision. Small local choices already contained by a recorded `IMP-NNN` and its delegation remain free.

Compile the derived plan:

```text
python3 scripts/implementation_plan.py <implementation-plan-draft.json> --build-contract <build-contract.json> --output <implementation-plan.json>
```

The compiler validates references, delegation, coverage, dependency order, context-complete test realization, contract binding, and the fixed return-to-owner boundary. It adds `plan_digest`. It does not authorize the plan or change the Build Contract.

## 7. One Fresh Handoff Check

Run exactly one fresh-context reviewer after compiling the candidate contract and implementation plan. Give it `execution-contract.md`, `evidence-map.md`, `build-contract.json`, `implementation-plan.json`, and repository access; do not provide the interview transcript, interviewer conclusions, or intended answer. The check measures lineage loss and whether the derived plan is executable in the repository. It does not prove discovery completeness or authorize product behavior.

Allow at most three blockers, limited to:

- `material-divergence` — two plausibly compliant implementations can produce materially different outcomes not explicitly delegated or allowed by tolerance;
- `evidence-contract-mismatch` — a material observed fact is neither preserved, explicitly superseded by valid authority, nor intentionally excluded; or
- `unverifiable-acceptance` — success or an applicable failure result cannot be objectively determined;
- `infeasible-implementation` — the proposed approach cannot be implemented on the inspected repository surfaces without changing the contract; or
- `implementation-decision-gap` — a fresh implementer must still make a material internal choice not contained by an `IMP-NNN` row and its bounded delegation.

The reviewer may inspect only repository surfaces needed to test feasibility. It must not invent product requirements, choose a replacement architecture, critique general architecture, report immaterial delegated variation, or treat evidence as authority.

Resolve admissible blockers as needed, but never rerun the reviewer for the same contract digest. Correct delegated plan defects and recompile the plan; return authority gaps to the owner and compile a new contract. If the contract digest changes materially, the prior review is stale and exactly one new fresh check is required for that new digest. If a material owner decision remains unresolved, finish as `incomplete`.

## Finalize and Hand Off

After resolving the fresh check, rerun the deterministic gates against the final artifacts:

```text
python3 scripts/authority_compiler.py <discovery-record.json> --authority-register <authority-register.json> --output <build-contract.json>
python3 scripts/projection_check.py <execution-contract.md> --discovery <discovery-record.json> --authority-register <authority-register.json> --build-contract <build-contract.json>
python3 scripts/implementation_plan.py <implementation-plan-draft.json> --build-contract <build-contract.json> --output <implementation-plan.json>
python3 scripts/implementation_plan.py <implementation-plan.json> --build-contract <build-contract.json> --check
```

Hand any implementing coding agent the sealed Build Contract, compiled implementation plan, and repository access. The Build Contract governs; the plan explains how to realize it. Internal choices may proceed only as recorded within bounded delegation. Contract-plan conflict, substantive unmapped behavior, or an infeasible plan returns for authority or replanning rather than silent invention.

Only after every final gate passes and no material owner decision remains unresolved, end the user-facing response with exactly one copy-ready `Implementation prompt` code block. Substitute the actual repository-relative session paths for `<session>`; do not leave placeholders, duplicate the artifact contents, include the interview transcript, or write the prompt into a new artifact unless the owner asks. Do not print this prompt when the session finishes as `incomplete`.

Use this prompt, preserving its authority order while adapting only repository-specific path wording:

```text
Implement the completed Ultimateinterview handoff in this repository.

Build Contract:
.ultimateinterview/<session>/build-contract.json

Implementation Plan:
.ultimateinterview/<session>/implementation-plan.json

First read every applicable AGENTS.md from the repository root through the target paths. Verify that the compiled implementation plan is bound to the supplied Build Contract before editing.

Implementation rules:
- The Build Contract is the governing authority for product behavior, scope, acceptance, and verification.
- The Implementation Plan is derived execution guidance. Follow its IMP-NNN decisions and dependency-ordered STEP-NNN steps unless repository reality makes a step infeasible.
- Never let the plan override the contract or invent observable behavior, fallback, retry, compatibility, migration, lifecycle, or failure semantics.
- If the plan is infeasible but the contract can remain unchanged, explain the reason, replan within the recorded bounded delegations, and continue.
- If implementation requires changing the contract or making a new material product decision, stop and report the exact decision gap instead of guessing.
- Keep unrelated changes untouched and run every contract verification.

Complete the implementation and report:
1. requirements implemented and files changed;
2. any plan deviation and its reason;
3. verification commands and results; and
4. any remaining blocker or contract divergence.
```
