---
name: ultimateinterview
description: Evidence-led requirements ambiguity management for brownfield software changes. Use when a developer wants to expose consequential unknowns and produce an implementation-ready contract before coding. Especially for "ultimateinterview", "requirements gap", "clarify before coding", "unknown unknowns", "make a spec", brownfield feature requests, bugfixes with unclear desired behavior, or mentions of Socratic interview, deep-interview, grill-me, PRD, acceptance criteria, non-goals, edge cases, misuse cases, DDD, domain model, falsification checkpoint, brain dump, or build contract.
---

# Ultimateinterview

Turn discoveries from conversation and repository observation into an authorized, verifiable Build Contract. Creativity belongs in discovery; strictness belongs at the handoff boundary.

A discovery record is unsealed and non-normative. Only a Build Contract emitted by the authority compiler may direct implementation. Never hand-author, edit, or represent an uncompiled document as a sealed Build Contract.

## Artifact Locality

Ultimateinterview is agent- and substrate-neutral. Store its Discovery Record, compiler-produced Build Contract, implementation return, postmortem, and related session artifacts under the repository-local `.ultimateinterview/<session>/` directory. Never place Ultimateinterview artifacts under agent/runtime-specific state directory. Run the compiler from this skill directory, but keep its input and output in `.ultimateinterview/<session>/`.

## JSON Contract Reference

Before constructing, compiling, validating, or handing off any compiler-only JSON artifact, read `references/json-contracts.md` and follow its canonical filenames, fields, digest rules, authority boundary, and session layout. The compiler remains the executable source of truth when code and prose disagree.

## Discovery

Start from the requested outcome and investigate whatever would materially change it. Follow useful branches in the conversation. Before asking the owner for a fact the repository can answer, inspect the relevant code, docs, tests, configuration, history, and existing artifacts. Research, scenarios, experiments, and small prototypes are also valid discovery tools. Outside the mandatory closure reviews, an additional fresh-context review is optional and returns findings, not decisions.

Throughout the entire interview—from initial repository inspection through owner questions, authority reconciliation, Discovery Record construction, and closure—make the best possible effort to uncover consequential blind spots. Continuously challenge the current framing for omitted actors, assumptions, scenarios, dependencies, constraints, and downstream effects; do not postpone blind-spot discovery until the final closure reviews.

Use observations to expose assumptions, conflicts, alternatives, missing behavior, and decision boundaries. Record a recommendation, conventional default, scenario, or assumption as a proposal until valid authority settles it. Do not silently reconcile a conflict between an owner statement and repository evidence; show the conflict and obtain the authority that governs it.

### Risk Proportionality

Keep discovery broad, but do not promote every conceivable exception into a question or normative requirement. When exception depth can materially change scope, establish one owner-approved risk posture early and apply it consistently instead of asking about each low-risk edge separately. Recommend a posture that covers normal use, credible single faults, realistic concurrency, and rare events with security, privacy, authorization, corruption, irreversible loss, or unrecoverable-state impact, while allowing reversible low-impact compound failures to use the ordinary authorized fail-closed behavior.

Triage each candidate blind spot using repository evidence or a concrete causal path. Record qualitative likelihood rather than inventing unsupported probabilities, the observable impact and reversibility, whether existing general behavior already contains it, the implementation and verification burden, and whether leaving it open would force materially different observable implementations.

Treat a finding as closure-blocking when at least one of these applies:

- repository evidence shows a reachable normal, single-fault, or realistic-concurrency path with material observable impact;
- the outcome can violate security, privacy, authorization, data integrity, irreversible-loss, or recoverability expectations even if rare;
- absent authority would force an implementer to invent materially different user-visible, lifecycle, failure, retry, recovery, retention, or compatibility behavior.

Treat a finding as non-blocking under the approved risk posture when it requires multiple independent unlikely failures, its impact is localized, reversible, and retryable, ordinary authorized fail-closed behavior safely contains it, and dedicated handling or verification would be disproportionate. A purely theoretical scenario without repository evidence or a credible causal path is also non-blocking. Do not silently discard a non-blocking finding: retain a concise rationale in discovery evidence or non-goals when it helps auditability, but do not turn it into a normative clause, acceptance test, owner question, or closure restart trigger. Escalate uncertainty in this classification only when the classification itself could materially change the contract.

### Owner Questions

Use the full extent of available reasoning, repository inspection, research, scenario analysis, counterexamples, boundary and failure analysis, misuse cases, experiments, and safe prototypes to uncover consequential blind spots the owner may not have considered. Apply the approved risk posture, then convert closure-blocking findings into precise owner questions when the answers can materially change the contract. Do not manufacture uncertainty, overwhelm the owner with speculative trivia, ask separately about risks already covered by the approved posture, or confuse supporting evidence with authority.

When discovery needs an owner decision, use the runtime's native structured question interface when available: GJC `ask` or Claude Code `AskUserQuestion`. Do not substitute an unstructured prose question when either interface is available.

For every question:

- ask only about a decision that can materially change the contract;
- provide the smallest useful set of distinct choices, normally two to five;
- include exactly one clearly marked recommended choice and briefly state why it is recommended;
- give each choice a concise label and enough consequence or trade-off detail for an informed decision;
- permit a custom answer through the runtime's automatic custom option, or an explicit custom option when the runtime does not provide one;
- use multi-select only when choices can validly be combined;
- group questions only when they are independent and can be answered together without hiding dependencies.

A recommendation is a proposal, not authority. Never record the recommended choice as an `owner-decision` until the owner explicitly selects or states it. If no structured question interface exists, preserve the same shape in plain text with a question, numbered choices, one marked recommendation, and a custom-answer path.

Keep a minimal unsealed Discovery Record in JSON for the compiler. It must contain:

- the schema identifier, goal, scope, and non-goals;
- an Authority Register and separately identified supporting evidence;
- normative requirements with their decision class, scope, constraints, authority references, and evidence references;
- acceptance predicates, verification procedures, and complete trace rows;
- unresolved owner decisions and authority conflicts.

Describe each acceptance predicate as:

```text
precondition/input -> action -> observable result -> applicable failure result
```

Discovery does not require a prescribed question order, a fixed category list, or a claim that all unknowns were found. Select the next observation or owner question only when it can materially affect the contract.

### Interview Closure

Treat an incomplete specification as a direct customer-impact risk: a missed ambiguity can produce a poor experience for paying customers. Before ending the interview or asserting that no consequential ambiguity remains, perform three distinct closure review passes. Run each pass in its own fresh-context reviewer session; the interviewing session may coordinate the reviews but must not perform or self-certify any pass. If the runtime cannot create three fresh-context sessions, keep the interview incomplete, state the blocker, and do not reconcile authority or compile a Build Contract.

Give each reviewer repository access plus the current Discovery Record, Authority Register material, supporting evidence, approved risk posture, and only its pass-specific brief. Do not give it the live interview transcript, another closure reviewer's output, the interviewing agent's conclusions, or an intended answer. Require each reviewer to return findings with repository evidence, not product decisions. For every candidate finding, require a concrete reachability basis, qualitative likelihood, impact and reversibility, existing containment, handling burden, and a closure-blocking or non-blocking classification under the approved posture. Preserve each result under `.ultimateinterview/<session>/closure-reviews/` with its round, pass, fresh-session identity, supplied inputs, and findings so closure is auditable.

In every pass, explicitly search for blind spots: relevant considerations that are absent from the discovery record, not merely ambiguities already visible inside it. Reconsider the whole discovered contract from the assigned fresh-context angle rather than mechanically repeating the same checklist:

1. Search for completeness blind spots across every relevant aspect you can identify, including omitted actors, journeys, states, data, interfaces, dependencies, scope boundaries, lifecycle, compatibility, and operations.
2. Search for scenario blind spots across edge, failure, recovery, concurrency, misuse, abuse, security, privacy, and irreversible outcomes, including hidden choices or conflicting expectations that no existing question exposed.
3. Search for implementation and verification blind spots: trace every substantive branch and observable outcome to authority, acceptance, and a context-complete verification path, and look again for assumptions or missing cases an implementer would otherwise have to invent.

After every pass, the interviewing session must independently verify the reviewer's cited repository evidence, investigate repository-answerable gaps, and apply the approved risk posture. Return every closure-blocking unresolved choice or blind spot to the owner. Non-blocking findings do not prevent closure and do not trigger a new round unless the owner changes the risk posture or their resolution would otherwise materially change the prospective contract. Restart all three passes in three new fresh-context sessions after an answer materially changes that contract. End the interview only when all three current-round fresh-context passes reveal no closure-blocking consequential blind spot, unresolved consequential ambiguity, authority conflict, or unverifiable normative behavior. State this bounded, risk-proportional conclusion and disclose any retained non-blocking findings; never claim that every possible unknown has been discovered.

## Authority Register

Every Authority Register entry needs a stable ID, one authority kind, its owner or canonical artifact, the decision or delegated scope, constraints and preserved observable behavior, source and version, status, and any conflict or supersession relationship.

The only authority kinds that may authorize a normative clause are:

- `owner-decision`: an explicit decision by the identified owner;
- `canonical-contract`: an owner-approved contract with identifiable applicability, version, and precedence;
- `bounded-delegation`: an explicit, non-transferable delegation with a bounded scope, decision classes, and constraints.

Evidence is not authority. Repository behavior, documentation, tests, configuration, history, research, prototypes, user statements that are not explicit decisions, model recommendations, assumptions, reviewer findings, and consensus can support or challenge a decision, but cannot authorize product policy. Do not infer, broaden, or re-delegate a delegation.

Return the following decisions to the owner unless a valid canonical contract explicitly governs them: user-visible behavior; scope and non-goals; actor, authorization, rights, or ownership; retention, deletion, or lifecycle; failure, retry, or recovery semantics; irreversible migration or data loss; compatibility floor; and numeric quality thresholds. This list is not exhaustive. Unclear authority is an unresolved owner decision.

A bounded delegation may allow an implementer to choose internal architecture, file or module structure, algorithms, or test organization inside the delegation's limits. It never authorizes a new observable product decision.

Represent a delegation boundary structurally, never with words such as “whole repo.” Use either normalized relative repository paths or stable named components, with explicit nonempty `includes` and `excludes`. Every delegated scope item must appear in `includes`; wildcard, absolute, traversal, transferable, or implicit boundaries are invalid.

## Compile the Contract

Construct the Discovery Record without filling gaps with model defaults. Then run the compiler from this skill directory, using the available Python interpreter:

```text
python3 scripts/authority_compiler.py <discovery-record.json> --authority-register <authority-register.json> --output <build-contract.json>
```

Use `scripts/authority_compiler.py` for every compile. Do not substitute manual review, passing tests, or consensus for compilation. On a compiler failure, do not create a partial or sealed result. Read the diagnostic, correct only authorized record data, or return the unresolved decision or conflict to the owner.

The compiler must write the sealed Build Contract as deterministic, human-readable UTF-8 JSON with two-space indentation, stable key order, and exactly one trailing newline. The contract digest remains bound to canonical JSON content. Never minify, beautify, or otherwise post-process the compiler output after sealing; formatting is the compiler's responsibility.

The compiler must fail closed unless all of the following hold:

- every normative clause has applicable authority references, while supporting evidence remains separate;
- authority scope, constraints, status, and precedence cover the whole clause;
- no authority conflict or required owner decision remains unresolved;
- acceptance and failure outcomes derive from authorized requirements rather than inventing behavior;
- every normative requirement is observable and has a verification path;
- each requirement has a complete `authority -> requirement -> acceptance -> verification` trace.

The compiler is a validator and normalizer, not a source of recommendations or product choices. Its successful output is the sealed Build Contract; retain its contract digest for downstream binding.

## Build Contract Handoff

Hand an implementing coding agent the compiler-produced Build Contract and repository access. The contract must state the goal, scope and non-goals, observable and failure behavior, clause authority references, explicit decision boundaries and bounded delegations, acceptance predicates, verification commands or scenarios, and requirement-to-acceptance-to-verification traceability.

Every verification command must be context-complete: state its working directory, exact target, and selection or isolation semantics. A project/environment selector alone does not establish execution scope.

The compiler-produced Build Contract must begin with an `implementation_decision_policy`. When contract insufficiency forces an arbitrary implementation choice that is permitted by the authority boundary, choose the simplest option that works within the contract and applicable bounded delegation, then record one digest-bound JSON object in repository-local `.ultimateinterview/<session>/decision.jsonl` before acting. Include the gap, decision, rationale, alternatives, affected paths, requirement references, and observable impact. The log is evidence, not authority and not an automatic stop gate.

The handoff is substrate-neutral: any coding agent can consume it without a particular harness, orchestrator, role name, or prior conversation. Every substantive implementation branch, refusal, fallback, preflight, hook, recovery behavior, or policy must cite an authorized requirement, acceptance predicate, or applicable bounded delegation. An unmapped substantive behavior returns to the owner for authority and a newly compiled contract. Non-substantive internal choices that do not add observable behavior or substantive branches may be logged and implemented without a new owner decision.

Request an implementation return bound to the Build Contract digest. It records, for each requirement and verification, the actual outcome; changed repository paths; commands or scenarios run and their results; existing evidence artifacts; non-contract implementation decisions and their rationale; and honest `not-run`, `blocked`, or `failed` states. This return is self-reported evidence, not authority and not final evaluation.

## Post-implementation Boundary

Independent divergence evaluation is outside this skill. After implementation produces a digest-bound return, hand the compiler-produced Build Contract, repository state or diff, verification evidence, and implementation return to the separate `ultimateinterview-postmortem` skill. Ultimateinterview must not duplicate, pre-empt, or perform that evaluator's audit.
