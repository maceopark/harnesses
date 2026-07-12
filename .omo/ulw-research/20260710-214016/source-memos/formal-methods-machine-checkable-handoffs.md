# Formal methods for machine-checkable requirements handoffs

Scope: research synthesis for `ultimateinterview` BuildContract. Read-only. The recommendations are risk-triggered extensions, not a proposal to formalize every requirement.

## Executive boundary

There are two different claims and they must never share one green status:

1. **Model-relative verification:** given formal model `M`, assumptions `A`, and property `P`, a checker established `A \land M \models P` within a declared scope or proof calculus.
2. **Model adequacy / requirements validation:** `M`, `A`, and `P` faithfully and sufficiently represent stakeholder intent and the real environment.

Formal methods can strongly support (1). They cannot mechanically establish (2) from the same artifact. IronSpec states that verified systems are only as strong as their trusted specs, that specs cannot themselves be proven correct, and reports ten specification bugs across all six real-world verified systems evaluated. It therefore adds sanity checks, spec-testing proofs, and mutation testing rather than treating proof success as intent validation [IronSpec, USENIX OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/goldweber).

The BuildContract already has useful integrity and traceability primitives: typed REQ/VER ids, source ids, explicit acceptance text, REQ-to-VER closure, real-surface/test floors, a Part-1 SHA-256, and a self-excluding contract digest (`build_contract_schema.py:56-66,133-151,189-210,229-304`). Those establish structural validity and freshness, not semantic correctness. The formal-methods extension should preserve that distinction.

## Technique-to-gate map

| Technique | Formal source / property | Assumptions and decidable envelope | BuildContract mapping | Executable gate | Residual risk / human boundary |
| --- | --- | --- | --- | --- | --- |
| Typed controlled specification | Existing EARS/GWT REQ rows, finite enums, state-transition tables | Syntax, ids, types, total enum coverage are decidable; natural-language truth is not | Keep `Requirement`; add typed predicates or referenced finite domain model | Schema validation; duplicate/dangling/totality lint; reject undefined enum/state branches | A well-typed wrong requirement remains wrong |
| Alloy bounded relational analysis | Object relations, authorization matrices, cardinality and uniqueness constraints, scope exclusions | Exhaustive only in user-declared finite scopes; Analyzer compiles bounded problem to SAT [official FAQ](https://alloytools.org/faq/how_does_the_alloy_analyzer_work.html) | Link REQs to `.als`, command, exact per-signature scope, expected assertion, source/model digest | FAIL on counterexample, parser error, timeout, missing scope, or stale digest; PASS says `no counterexample within scope`, never `proved globally` | Small-scope hypothesis is empirical; bugs beyond scope and model omissions remain |
| TLA+/TLC model checking | State machine from Behavior Contract + Change Impact invariants; safety, deadlock, temporal/liveness properties | TLC checks a finite-state model / accepted TLA+ subset; real systems may be unbounded. Original paper calls it debugging and choosing a finite model [Yu, Manolios, Lamport](https://lamport.azurewebsites.net/pubs/yuanyu-model-checking.pdf) | Link REQ/guardrails to `.tla` + `.cfg`; record constants, state bounds, invariants, temporal properties, fairness assumptions, model/source digests | Require tool success, no counterexample, nonzero explored state count, explicit bound report, no ignored property; preserve trace on failure | Finite-instance result; state explosion; fairness/environment assumptions; property may be vacuous |
| Event-B refinement | Abstract requirement machine refined toward design; invariant establishment/preservation, well-definedness, feasibility, guard strengthening, simulation, equality, variant termination | Individual proof obligations are logic-relative; automation may leave POs interactive. Rodin PO catalog explicitly lists these classes [Rodin manual](https://wiki.event-b.org/index.php/Proof_Obligation_Names_%28Rodin_User_Manual%29) | `preserved_invariant`, `target_difference`, `decision_core`, and REQ rows map to named abstract/concrete machines and PO ids | Require zero undischarged POs and replay success; report interactive/axiomatic proofs separately. Add an explicit deadlock obligation because Rodin manual says generation is missing by default | Refinement preserves the chosen abstraction, not stakeholder intent; gluing invariant/model can be wrong; prover/plugin TCB |
| Deductive program verification (Dafny-like) | Pure decision core with preconditions, postconditions, invariants, frame conditions, termination measure | Often SMT-backed; proof is relative to contracts and axioms. Dafny says false `assume` can yield invalid conclusions and `{:axiom}` transfers responsibility to the author [official reference](https://dafny.org/dafny/DafnyRef/DafnyRef) | Use `implementation_constraints.decision_core`; map each function contract to REQ/VER and real-surface observation | Require verifier success plus lint rejecting `assume`, `{:axiom}`, `{:extern}`, `{:verify false}`, `assert {:only}`, or bodyless lemmas unless each is enumerated as an owned assumption; retain real-surface VER | Compiler/runtime/FFI/hardware outside proof; spec weakness; solver/tool bugs; total correctness requires termination obligations |
| SMT decision procedures | Finite predicate consistency, contradictions, implication, coverage, threshold arithmetic | Use the most specific decidable fragment. cvc5: QF_NIA is undecidable; quantified UF is undecidable; some decidable fragments are still expensive; solver may return `unknown` [official tutorial](https://cvc5.github.io/tutorials/beginners/theories.html) | Add `logic`, formula/model digest, result, timeout/resources, solver version, proof format | PASS only on expected SAT witness or independently checked UNSAT certificate. UNKNOWN/TIMEOUT/UNSUPPORTED is not PASS; route to residual/human or stronger method | Encoding errors; unsupported combinations; heuristics; a satisfying assignment is not real-world evidence |
| Proof-producing SMT / certificate checking | Solver produces LFSC/Alethe/Lean proof; independent checker validates result | Checker + logic/signatures are TCB. cvc5 warns unsupported LFSC rules become `trust` steps that prove arbitrary formulas [official LFSC docs](https://cvc5.github.io/docs/cvc5-1.3.2/proofs/output_lfsc.html) | Store certificate path/digest, checker/version, property digest, zero-trust-step count | Re-run checker; reject any trust step/warning, digest mismatch, stale/missing certificate, or unsupported proof rule | Small checker reduces but does not eliminate TCB; semantics/axioms remain trusted |
| Proof-carrying code / certifying computation | Producer ships artifact plus machine-checkable proof of compliance with consumer policy | Consumer must predefine a formal safety policy; checker is trusted. PCC is about adherence to that policy, not discovering it [Necula bibliography/abstract](https://people.eecs.berkeley.edu/~necula/papers.html) | Treat `build-contract.json` + implementation manifest + per-property certificate as a bound bundle; policy is stable REQ/guardrail ids | Consumer-side gate verifies contract digest, artifact digest, policy version, certificate, checker, and freshness before accepting handoff/output | Proof policy can omit the dangerous property; proof size/check cost; compiler/platform semantics; checker TCB |
| Proof-carrying data | Each derived message/output carries proof that local data and history satisfy a prescribed compliance predicate | Cryptographic construction is computationally sound under assumptions and specialized infrastructure; original PCD uses proofs on every message and a signature-card model [Chiesa & Tromer](https://projects.csail.mit.edu/pcd/) | Conceptual fit for chained handoff transformations: every derived artifact cites parent digest and compliance predicate; full cryptographic PCD is disproportionate for local Markdown/JSON | Practical version: deterministic derivation manifest + digest chain + independently checkable certificate; crypto PCD only under an actual mutually-untrusted distributed threat model | Proves prescribed history predicate, not truth of source evidence; crypto/setup/key assumptions; major complexity |
| Translation validation | Validate one concrete transformation rather than prove the transformer correct for all inputs | Per-run equivalence/refinement relation must itself be formal and checkable [Pnueli et al. pattern](https://weizmann.esploro.exlibrisgroup.com/esploro/outputs/journalArticle/Translation-validation-From-SIGNAL-to-C/993262325003596) | Ideal for `handoff.md Part 1 -> build-contract.json`: validate semantic field preservation per compilation, not merely SHA freshness | Compile, compare normalized source AST to JSON, produce equivalence witness/diff, reject dropped/narrowed enum cases | Validator and source parser can share bugs; prose-to-AST interpretation is still a human/LLM boundary |
| Assurance case (ISO 15026 / SACM) | Structured top claim → subclaims → evidence + explicit assumptions/counterevidence | Graph well-formedness, trace closure, freshness, ownership are decidable; argumentative sufficiency is not. ISO says assurance-case structure does not impose quality requirements on contents [ISO 15026-2](https://www.iso.org/standard/52926.html) | Part 2 can compile to claim/evidence/assumption nodes keyed by REQ/VER/source ids; include challenge links and residuals | Require every top claim to terminate in current evidence or explicit assumption/residual; reject cycles, dangling refs, stale evidence, unresolved counterevidence, unowned assumptions | A complete-looking graph can be weak or circular in substance; independent review remains mandatory |

## Recommended BuildContract extension

Do not add a boolean `formally_verified`. Add zero or more **FormalObligation** records; absence is valid when the risk trigger says formalization is disproportionate.

```json
{
  "id": "FO-001",
  "requirement_ids": ["REQ-003"],
  "claim_kind": "bounded-model-check|refinement|deductive-proof|certificate|assurance-structure",
  "property": "No admitted request can reach effect without authorization",
  "formalism": "TLA+",
  "model_path": "spec/Auth.tla",
  "model_sha256": "...",
  "source_contract_sha256": "...",
  "assumptions": ["finite Users=3", "fairness WF_vars(Authorize)"],
  "scope": {"bounded": true, "description": "Users=3, Requests=4, queue<=2"},
  "tool": {"name": "TLC", "version": "...", "command": "..."},
  "expected": "no-counterexample",
  "result": "pass|fail|unknown",
  "certificate": {"path": null, "sha256": null, "checker": null, "trust_steps": 0},
  "model_adequacy": {
    "evidence_ids": ["g15", "scenario-auth-bypass"],
    "independent_reviewer": "reviewer-id",
    "mutation_or_vacuity_check": "passed",
    "known_omissions": ["cross-region outage"],
    "disposition": "accepted|rework|deferred"
  },
  "residual_owner": "..."
}
```

Required semantics:

- `result=pass` means only the formal claim under recorded assumptions/scope.
- `result=unknown` is a first-class non-pass, not coerced to success.
- `scope.bounded=true` requires human-readable bound disclosure in Part 1 and an owned residual.
- Any unchecked axiom, oracle, extern, trust step, abstraction, or environment assumption must be explicit and owned.
- `model_sha256`, contract SHA, tool version, command, and certificate digest bind proof to the exact handoff.
- Model adequacy evidence must come from channels independent of the proof derivation where feasible: scenario examples/counterexamples, repo/runtime observations, independent review, mutation/vacuity checks.

## Gate topology

1. **G0 — Structural compile:** current BuildContract v1 schema, REQ/VER closure, source and self-digests. This proves parseability/trace integrity only.
2. **G1 — Formalizability classification:** for each high-impact REQ, mark `finite-decidable`, `bounded-checkable`, `interactive-proof`, `runtime-observable-only`, or `human-judgment`. Reject missing classification, not human judgment itself.
3. **G2 — Consistency/non-vacuity:** check model satisfiable/reachable; ensure preconditions/triggers are realizable; mutate salient predicates or run vacuity checks. A universally true property caused by an impossible antecedent must fail review. Vacuity research explicitly notes that valid formulas can hide model problems [Beer, Ben-David, Eisner, Rodeh](https://weizmann.esploro.exlibrisgroup.com/esploro/outputs/abstract/Efficient-detection-of-vacuity-in-temporal/993267415703596).
4. **G3 — Property/refinement:** run chosen checker; accept only the method-specific success condition. Preserve counterexamples and undischarged POs as evidence.
5. **G4 — Certificate/TCB:** independently check proof if available; reject trust steps, stale digests, unapproved axioms/oracles, checker mismatch.
6. **G5 — Model adequacy:** independent reviewer sees the formalized model plus source REQ/scenarios and asks: omitted actor/state/boundary? unrealistic assumption? property weaker than prose? counterexample outside scope? This gate is human-evidence-backed, not labeled proof.
7. **G6 — Real surface:** retain current `test` plus `real-surface` verification floor. Deductive/model proof never substitutes for runtime/compiled/endpoint observation across unmodeled layers.
8. **G7 — Assurance closure:** every formal PASS, assumption, omission, counterevidence item, and residual is connected to REQ/VER and an owner. Reject stale/unowned/unresolved nodes.

Suggested fail-closed result enum: `pass`, `fail`, `unknown`, `stale`, `unchecked-assumption`, `unsupported`, `not-applicable`. Only `pass` or justified `not-applicable` clears a mandatory obligation.

## Decidability boundary

Use an explicit ladder rather than promising universal mechanical checking:

| Class | Examples | Mechanical status |
| --- | --- | --- |
| Finite structural | ids, enums, graphs, transition matrices, trace closure, bounded cardinalities | Decidable; require deterministic gate |
| Finite/bounded semantic | Alloy scopes, TLC finite constants, bounded traces, SAT/bit-vectors | Exhaustive only within declared bound; result must say bounded |
| Decidable theories | propositional SAT, many quantifier-free bit-vector/linear arithmetic fragments | Decidable in principle; may still hit resource limits; record timeout as non-pass |
| Semi-/heuristically decidable | many quantified SMT problems, nonlinear integer arithmetic, unbounded transition systems | May return unknown/not terminate; require bounded reduction, interactive proof, or residual |
| Human validation | intent completeness, domain ontology adequacy, risk appetite, evidence relevance, socio-technical behavior | Not derivable from the formal model itself; require named human/independent evidence and ownership |

The useful design move is **not** to force undecidable questions into fake booleans. It is to make the boundary machine-readable and fail closed when an obligation claimed as mechanical yields `unknown` or silently relies on an unchecked assumption.

## Proof obligations aligned to current Part 1

| Current BuildContract surface | Candidate mechanically checked obligation | Adequacy check that remains separate |
| --- | --- | --- |
| Goal / Target Surface | Every changed target is covered by a REQ and impact trace | Are the real change surfaces and stakeholders complete? |
| Behavior Contract | Predicate well-definedness; state/operation totality; consistency; invariant/safety/temporal properties | Does the formal predicate encode the intended behavior and all material cases? |
| Change Impact & Preservation | Refinement/simulation from current model to target; preserved invariant POs | Is the abstraction relation faithful to real current behavior? |
| Quality Bars | Arithmetic threshold consistency; bounded resource property where modelable | Is the metric the right proxy, and is the threshold acceptable? |
| Decision Boundaries | Every free variable/choice classified as agent-owned or fixed; no unowned assumption | Were decision rights assigned to legitimate owners? |
| Out of Scope | Negative capability properties / absence checks | Is exclusion safe and acceptable? |
| Decision Core / Effects Boundary | Functional contract proof for pure core; state-machine model for effects ordering/idempotency | Does model include actual I/O failures, concurrency, and platform semantics? |
| Rollout & Recovery | Reachability of rollback; no forbidden state; variant/termination where appropriate | Are activation signals and operational recovery assumptions realistic? |
| Guardrails | Each stop-time predicate decidable; counterexample for bypass attempt | Are fast risks truly enforced by substrate on every path? |
| Verification Commands | REQ coverage closure, result parsing, proof/certificate checking | Does the command exercise the real surface without gaming/stubbing? |
| Deferred Risks | Owner/date/type closure | Is accepting the residual prudent? Human decision only. |
| Fresh-Implementer Test | No unresolved structural findings | Review cannot prove completeness; use independence, mutation, counter-scenarios |

## What not to claim

- Not “mathematically proven requirements.” Say “property `P` holds for model `M` under assumptions `A` and scope `S`.”
- Not “Alloy/TLC found no bugs.” Say “no counterexample within the recorded finite instance.”
- Not “the proof certificate removes trust.” It relocates trust into policy, semantics, checker, axioms, compiler/platform, and binding digests.
- Not “assurance-case complete means assured.” ISO explicitly standardizes structure while disclaiming content quality.
- Not “formal proof replaces tests.” Tests/observations validate model-to-reality links and unmodeled layers; proof supplies different evidence.
- Not “unknown is likely safe.” Unknown is no proof.

## Source set and counter-search record

Primary/official sources consulted across more than ten distinct searches:

- TLA+/TLC original model-checking paper: https://lamport.azurewebsites.net/pubs/yuanyu-model-checking.pdf
- Alloy Analyzer official bounded-scope explanation: https://alloytools.org/faq/how_does_the_alloy_analyzer_work.html
- Event-B/Rodin official proof-obligation catalog: https://wiki.event-b.org/index.php/Proof_Obligation_Names_%28Rodin_User_Manual%29
- Dafny official reference, unchecked assumptions/axioms: https://dafny.org/dafny/DafnyRef/DafnyRef
- cvc5 official decidability/unknown guidance: https://cvc5.github.io/tutorials/beginners/theories.html
- cvc5 official LFSC proof/trust-step documentation: https://cvc5.github.io/docs/cvc5-1.3.2/proofs/output_lfsc.html
- Necula PCC bibliography and original abstract: https://people.eecs.berkeley.edu/~necula/papers.html
- Chiesa/Tromer PCD project/paper: https://projects.csail.mit.edu/pcd/
- ISO assurance-case standard abstract/limitations: https://www.iso.org/standard/52926.html
- OMG SACM normative and machine-readable artifacts: https://www.omg.org/spec/SACM/2.0/
- Translation-validation primary pattern: https://weizmann.esploro.exlibrisgroup.com/esploro/outputs/journalArticle/Translation-validation-From-SIGNAL-to-C/993262325003596
- IronSpec specification-bug counterevidence: https://www.usenix.org/conference/osdi24/presentation/goldweber
- Temporal-property vacuity counterevidence: https://weizmann.esploro.exlibrisgroup.com/esploro/outputs/abstract/Efficient-detection-of-vacuity-in-temporal/993267415703596
- NIST cost/fit caution: https://www.nist.gov/publications/cost-effective-uses-formal-methods-verification-and-validation

## OBSERVATIONS

- Current BuildContract v1 already carries the right identifiers and digests to become proof-carrying, but its current `Verification` record has command/pass/run-policy fields only; it does not encode formalism, model, assumptions, scope, solver result, certificate, checker, trust steps, or model adequacy.
- The highest-value near-term additions are bounded relational/state-model checks and per-run translation validation of Part 1 → JSON. Full cryptographic PCD is not proportionate unless artifacts cross mutually untrusted distributed components.
- Proof obligation catalogs are reusable requirement prompts: well-definedness, feasibility, invariant establishment/preservation, refinement simulation, guard strengthening, termination, and deadlock. They expose exact missing questions rather than a generic “verify this.”
- Vacuity/mutation checks are crucial because a property can pass for the wrong reason, even before asking whether the model matches reality.
- Assurance cases are best used as a typed argument/evidence index with explicit assumptions and counterevidence, not a numeric assurance score.

## CLAIMS

1. A machine-checkable handoff should be a bound tuple `(contract, model, assumptions, property, scope, result, certificate/checker, adequacy evidence, residual owner)`, not a contract plus a `verified=true` flag.
2. A proof-producing/verifier-independent gate materially improves trust only when trust steps and unchecked axioms are rejected and exact artifact/property digests are bound.
3. Formal verification and model validation must be separately represented and separately gated; neither subsumes the other.
4. The system should fail closed on `unknown`, stale proofs, missing bounds, unsupported rules, and unowned assumptions, while allowing explicitly justified `not-applicable` for low-risk/non-formalizable requirements.
5. Formalization should be triggered by risk and structural fit: authorization/state/concurrency/invariants/refinement are good candidates; stakeholder value, organizational policy, and evidence relevance remain human judgment boundaries.

## EXPAND

- Define a backward-compatible `FormalObligation` Pydantic schema and fixture matrix; coordinate with deterministic-gates before implementation.
- Prototype Part-1 Markdown → normalized AST → BuildContract JSON translation validation, including full enumerated subcase preservation rather than id citation alone.
- Run a reduced-space comparison on one existing todo-cli handoff: Alloy or TLA+ finite model + mutation/vacuity checks + current real-surface VERs; measure new defects, authoring cost, and false confidence.
- Design an assumption ledger with categories `domain`, `environment`, `abstraction`, `tool`, `axiom`, `bound`, and mandatory owner/disposition.
- Evaluate a proof format/checker only after selecting the solver/logics; cvc5 LFSC cannot be called independent proof today if output contains trust steps.
- Compile Part 2 to a small SACM-like claim/evidence graph and test only structural properties first: trace closure, freshness, cycles, counterevidence resolution, and assumption ownership.
