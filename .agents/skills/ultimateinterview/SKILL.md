---
name: ultimateinterview
description: Material-decision interview for brownfield software changes. Use when a developer wants a fast, evidence-grounded, implementation-ready contract before coding; especially for unclear feature or bugfix behavior, requirements gaps, acceptance criteria, non-goals, edge cases, misuse cases, PRDs, specs, or Build Contracts.
---

# Ultimateinterview

Produce a small, authorized, verifiable execution contract. Ground briefly, ask only decisions that can materially change implementation, run one fresh handoff check, then compile and stop.

Evidence describes current state; it does not authorize new behavior. Only an explicit `owner-decision`, an applicable `canonical-contract`, or a `bounded-delegation` may authorize a normative decision. A delegated default is a choice made under bounded delegation, never an authority kind.

Keep all session artifacts under `.ultimateinterview/<session>/`. Use `execution-contract.md` as the single human-facing contract and `evidence-map.md` as its compact observed-evidence input. Both remain unsealed. Only compiler-produced `build-contract.json` is normative.

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

Assign stable `DEC-NNN` IDs and do not renumber them within a session. Each decision block row must use the closed format in `references/json-contracts.md`. Keep its `statement` atomic and byte-identical in the selected authority's and requirement's `constraints` or `preserved_behaviors`; this is the deterministic projection anchor. Every requirement-authority pair must have a decision row. Acceptance and verification references must cover every and only the rows belonging to that requirement.

## 5. One Fresh Handoff Check

Run exactly one fresh-context reviewer after drafting the small contract. Give it only `execution-contract.md` and `evidence-map.md`; do not provide the interview transcript, interviewer conclusions, or repository access. The check measures lineage loss from observed evidence through decisions into contract, acceptance, and verification. It does not prove discovery completeness.

Allow at most three blockers, limited to:

- `material-divergence` — two plausibly compliant implementations can produce materially different outcomes not explicitly delegated or allowed by tolerance;
- `evidence-contract-mismatch` — a material observed fact is neither preserved, explicitly superseded by valid authority, nor intentionally excluded; or
- `unverifiable-acceptance` — success or an applicable failure result cannot be objectively determined.

The reviewer must not browse, invent product requirements, critique general architecture, report delegated internal variation, or treat evidence as authority.

Resolve admissible blockers as needed, but never rerun the reviewer or restart the interview. Repeat only deterministic reconciliation, compilation, and validation. If a material owner decision remains unresolved, finish as `incomplete`.

## Compile and Hand Off

Before creating compiler JSON, read `references/json-contracts.md`. Generate the compiler inputs from the accepted small contract, then run from this skill directory:

```text
python3 scripts/authority_reconcile.py <authority-reconciliation.json> --output <authority-register.json>
python3 scripts/authority_compiler.py <discovery-record.json> --authority-register <authority-register.json> --output <build-contract.json>
python3 scripts/projection_check.py <execution-contract.md> --discovery <discovery-record.json> --authority-register <authority-register.json> --build-contract <build-contract.json>
```

Do not hand-author, edit, or post-process the sealed output. Compiler or projection-gate failure means the contract is not ready: correct only the projection, resolve missing authority, or finish incomplete. Do not rerun the fresh reviewer. The gate must prove complete `material decision -> authority -> requirement -> acceptance -> verification` traceability and structural equality with a fresh compile before handoff.

Hand the implementing agent the sealed Build Contract and repository access. Internal choices may proceed only within bounded delegation; substantive unmapped behavior returns for authority and recompilation. Request a digest-bound implementation return using the formats in `references/json-contracts.md`.
