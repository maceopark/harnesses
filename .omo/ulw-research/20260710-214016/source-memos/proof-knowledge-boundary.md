# Proof-of-knowledge / requirements-interview boundary

## Verdict

**Overall: bounded metaphor, not a proof-of-knowledge transfer.** A requirements interview can borrow the engineering shape of explicit claims, predeclared acceptance predicates, independently chosen challenges, counterexamples, and repeated checks. It cannot safely claim proof of knowledge, extractability, cryptographic soundness, or a calibrated knowledge error unless it supplies the missing formal objects and algorithms.

The exact transferable core is smaller: a machine-checkable requirement may be represented by a public instance `x`, a concrete evidence artifact `w`, and a decidable checker `R(x,w)`. That is ordinary witness verification. It becomes a proof of knowledge only if a universal efficient extractor can obtain such a `w` from every sufficiently successful prover under the stated access model.

## Primary-source boundary

Bellare and Goldreich define demonstrated “knowledge” computationally: an efficient extractor, given the public input and oracle access to the prover, must output a witness. Their Definition 3.1 fixes a binary relation `R`, an acceptance probability `p(x)`, a knowledge error `κ(x)`, and expected extraction time bounded by `|x|^c/(p(x)-κ(x))` ([author-hosted CRYPTO '92 paper, pp. 8–10](https://cseweb.ucsd.edu/~mihir/papers/pok.pdf)). They also stress:

- the extractor is universal across provers, not selected after seeing a convenient prover;
- the public transcript alone is insufficient in zero-knowledge cases; extractors seek related accepting transcripts via oracle access;
- proof-of-knowledge validity does not, in their definition, automatically supply soundness for statements outside the language;
- knowledge error is a quantitative property of a specified protocol and probability space, not a qualitative confidence label.

Goldwasser, Micali, and Rackoff define zero knowledge by efficient generation of transcript distributions without the prover; their original paper explicitly says such texts can be generated without the prover in the zero-knowledge case ([STOC '85 extended abstract, pp. 6–9](https://evervault.com/papers/zkp-1986.pdf)). Therefore an accepting-looking transcript is not itself evidence that its visible author possessed a witness.

The local interview contract is appropriately narrower already: it says the result is “implementation-ready under the recorded evidence, not proof that uncertainty is zero,” assigns typed evidence/provenance, requires pressure testing and independent causal groups for high-impact entries, and admits that deterministic handoff coverage cannot prove synthesis fidelity (`.agents/skills/ultimateinterview/SKILL.md`, especially lines 8, 29–36, 76–80, 93–100).

## Normalized transfers

| Primitive | Assumptions required in cryptography | Local interview analogue | Preserved property | Lost guarantee | Falsifier / counterexample | I-node | Verdict |
|---|---|---|---|---|---|---|---|
| Witness relation `R(x,w)` | Stable public instance `x`; bounded witness `w`; decidable relation; relation adequately captures the intended statement | Requirement/claim `x`, artifact or observation `w`, executable acceptance predicate | A named artifact can be checked against a named predicate | The predicate may encode the wrong requirement; normative intent and open-world adequacy are not decidable from the artifact | Test passes because it checks a mocked API while production semantics differ | **I-PK-01 relation adequacy:** require each critical predicate to name scope, environment, authority, and known complement | **Bounded**; exact only for the encoded predicate |
| Verifier acceptance | Fixed verifier; explicit accepting state; controlled randomness | Readiness gate / ledger status / executable lint | Reproducible accept/reject for syntactic and decidable conditions | Acceptance is not truth, stakeholder knowledge, completeness, or extractability | A perfectly schema-valid but substantively false evidence record passes | **I-PK-02 acceptance semantics:** rename acceptance as `gate_passed_under_evidence(E,A,t)` | **Exact** as a gate, **non-transferable** as knowledge |
| Universal knowledge extractor `K` | For every prover, oracle access; efficient witness output whenever `p>κ`; quantifier order fixed in advance | Hypothetical procedure that could recover the implementation-relevant fact/decision from any interviewee who repeatedly passes | If constructed, would justify a computational possession claim | Current process records answers and evidence but does not extract a witness from arbitrary successful interviewees | A user pastes a correct design and passes scripted questions, but cannot explain or regenerate its rationale; conversely, an owner knows the desired policy but cannot produce a technical artifact | **I-PK-03 extractor obligation:** prohibit “proves knowledge” unless an explicit extractor, access model, witness type, and success bound are supplied | **Non-transferable** in the general interview |
| Oracle access / rewinding | Extractor can reset or query the same prover state, often obtaining related transcripts while controlling challenges | Re-ask from a fresh angle, fresh-context reviewer, or scenario replay | Multiple probes may expose inconsistency | Humans cannot be reset; LLM state, learning, fatigue, clues, and conversation history change the prover; answers are not counterfactual responses from the same committed state | First question teaches the answer to the second, so two consistent responses are not independent | **I-PK-04 reset/access model:** call follow-ups “additional observations,” never rewinds or extraction trials | **Metaphor** for probing; **non-transferable** for extraction |
| Commitment before challenge | Binding commitment; challenge sampled after commitment and not chosen by prover; response tied to both | Freeze a claim/design digest before red-team scenario selection | Reduces post-hoc answer editing when the digest and challenge provenance are enforced | Natural-language claims are underspecified; interviewer may leak likely challenges; edits can be legitimate requirement formation | Stakeholder changes a requirement after seeing a valid scenario because the scenario reveals their actual preference | **I-PK-05 formation-vs-test:** label each round either elicitation/co-creation or test of a frozen claim; do not score the former as soundness evidence | **Bounded** when artifacts are frozen; otherwise **metaphor** |
| Random verifier challenge | Defined challenge distribution, private/unpredictable coins, coverage tied to formal relation | Independently generated misuse case, property test, mutation, or fresh reviewer question | Limits tailoring to a known checklist and can reveal selected counterexamples | No defensible distribution over “all requirement failures”; question-selection bias and correlated models remain | Ten random edge cases miss the single authorization boundary that matters | **I-PK-06 challenge provenance:** record generator, seed/input corpus, independence lineage, scope, and uncovered complement | **Bounded** for a declared test space; **non-transferable** globally |
| Special-soundness style extraction from related transcripts | Same first commitment; distinct challenges; accepting responses; efficient algebraic extractor | Compare answers to two scenarios against one frozen requirement | Cross-scenario consistency can reveal a concrete invariant | Consistency does not yield a unique or true requirement, and there is generally no extraction function | Two mutually consistent answers support a false shared premise; or two different implementations both satisfy the intent | **I-PK-07 cross-scenario warrant:** require an explicit derivation from responses to invariant plus a counterexample; call it inference, not extraction | **Metaphor**, except for a deliberately formalized micro-protocol |
| Knowledge error `κ` and repetition | Known probability space; independence/composition theorem; fixed adversary model; extractor runtime related to `p-κ` | Residual ambiguity score, repeated pressure questions, multiple reviewers | More independent checks can reduce observed unresolved risk | Interview scores are ordinal heuristics, not probabilities; repeated correlated checks do not exponentiate confidence | Same model paraphrases the same repository claim five times and is counted as five confirmations | **I-PK-08 no pseudo-probability:** forbid cryptographic error-rate or exponential-confidence language without empirical calibration and independence proof | **Non-transferable** |
| PoK validity vs soundness | These are separately defined properties in Bellare–Goldreich; validity concerns extraction on `x∈L_R`, soundness bounds acceptance on `x∉L_R` | Evidence that a source can produce a supporting artifact vs evidence that the requirement/claim is not false | Forces separate questions: “is there support?” and “what would refute this?” | A process may elicit an artifact without ruling out false statements or inadequate relations | A witness exists for the encoded relation, but the relation omits tenant isolation | **I-PK-09 separate gates:** distinguish witness/evidence validity, claim falsification, and specification adequacy | **Exact conceptual distinction**; cryptographic guarantees do not transfer |
| Transcript as evidence | In ZK, transcript distributions may be simulated without the witness; PoK relies on extractor access, not appearance | Interview transcript, polished handoff, checkpoint confirmation | Audit trail of what was said and accepted | Possession, authorship, truth, causal independence, or competence | Copied answer, coached interviewee, simulator/LLM-generated narrative, or fatigue “yes” produces a plausible transcript | **I-PK-10 transcript non-possession:** treat transcript as provenance-bearing claim record only; require external evidence for factual establishment | **Non-transferable** as proof; **exact** as an audit record |
| Fiat–Shamir removal of interaction | Public-coin protocol plus modeled hash/random-oracle assumptions and a proof for the transformed scheme | Hash a frozen spec to generate deterministic challenge prompts; replace interview with static checklist | Reproducible prompt selection | No random-oracle model for semantics; adaptivity is essential to requirements discovery; deterministic prompt generation does not imply knowledge soundness | Static generated prompts never branch on a newly discovered stakeholder or lifecycle state | **I-PK-11 no Fiat–Shamir analogy:** describe deterministic challenge derivation only as reproducibility, not compilation to non-interactive proof | **Non-transferable** |
| Pre-existing witness possession | The witness exists before the proof and satisfies the fixed relation | Stakeholder supposedly “has” the complete requirement that questions recover | Fits factual recall tasks with a stable source of truth | Many requirements are negotiated or created during the interview; authority can make a decision without possessing a prior hidden witness | A failure scenario causes the product owner to choose a new policy that did not exist before the question | **I-PK-12 co-creation boundary:** distinguish discovery of facts, elicitation of preferences, and constitution of decisions | **Non-transferable** for normative requirements; **bounded** for factual recall |

## Counterexample suite

These are rejection tests for any future “proof-of-knowledge interview” wording:

1. **Simulated transcript:** Can an LLM or template generate an accepting-looking transcript without access to the alleged witness? If yes, transcript acceptance is not possession.
2. **Copied witness:** Can an interviewee replay a correct artifact supplied by someone else? If yes, the artifact may still be useful, but it does not establish the interviewee's knowledge or authority.
3. **Authoritative non-extractor:** Can a legitimate owner decide the requirement but fail to produce a technical witness? If yes, extractor failure would incorrectly reject valid normative authority.
4. **Co-created requirement:** Does the answer become defined only after the challenge? If yes, the round elicited or constituted intent; it did not test pre-existing possession.
5. **Correlated repetition:** Do all “independent” challenges derive from the same model, document, or interviewer framing? If yes, repetition has no cryptographic amplification interpretation.
6. **Wrong relation:** Can a witness satisfy the checker while violating the real stakeholder goal? If yes, witness verification is exact only for an inadequate relation.
7. **State drift:** Would a retry occur after learning, fatigue, policy change, or environmental change? If yes, there is no resettable-prover experiment.
8. **Multiple valid witnesses:** Can incompatible implementations or policies all pass? If yes, extraction of one artifact cannot establish intendedness or uniqueness.

## Safe replacement language

### Preferred short form

> This is an evidence-backed requirements acceptance protocol, not a proof of stakeholder knowledge. It records claims and provenance, challenges selected high-risk assumptions, checks explicit predicates, and blocks handoff on known unresolved gaps. A passing gate means implementation-ready under the recorded evidence, assumptions, scope, environment, and time—not that the claims are globally true, complete, independent, or extractable.

### When the crypto analogy is useful

> Inspired by challenge-response protocols, the interview freezes selected claims before independently sourced counterexamples and records whether each claim survives. The analogy is procedural only: there is no cryptographic extractor, knowledge-error bound, resettable prover, or completeness guarantee.

### When a literal witness exists

> For requirement `x`, artifact `w` is accepted when checker `R(x,w)` returns true in environment `e` at time `t`. This establishes only that `w` satisfies the encoded predicate. It does not establish stakeholder possession, authorship, specification adequacy, or freedom from omitted requirements.

### Terms to avoid

- “proof that the stakeholder knows the requirements”
- “knowledge extraction” for ordinary follow-up questioning
- “soundness amplification” for repeated reviewers/questions
- “negligible error” or numeric confidence without a calibrated probability model
- “Fiat–Shamir for interviews”
- “zero knowledge” merely because private details were omitted

Use instead: **claim elicitation**, **evidence acquisition**, **counterexample challenge**, **cross-scenario consistency check**, **typed provenance**, **readiness predicate**, **bounded test-space coverage**, **uncovered complement**, and **decision-authority record**.

## OBSERVATIONS

- The local skill already states the correct high-level boundary: implementation readiness under recorded evidence is not zero uncertainty.
- Its typed provenance, causal-group accounting, hypothesis-only assumptions, contested-state handling, and fatigue-safe checkpoint rules are compatible with the safe, non-cryptographic formulation.
- The biggest wording hazard is equating a passed interview/checkpoint or polished transcript with demonstrated possession. Genuine PoK definitions do not infer knowledge from transcript appearance.
- Requirements interviewing mixes three different acts—discovering facts, eliciting preferences, and constituting decisions. Only the first even plausibly resembles recovery of a pre-existing witness.

## CLAIMS

- **C-PK-1:** Without an explicit witness relation and universal efficient extractor, “proof of knowledge” is false as a technical claim.
- **C-PK-2:** A transcript can be a useful audit record while carrying no possession guarantee.
- **C-PK-3:** Executable acceptance predicates provide exact local verification of their encoding, not adequacy of the encoding.
- **C-PK-4:** Repeated questions reduce risk only under recorded independence and scope; they do not inherit cryptographic error reduction.
- **C-PK-5:** The safest transferable design is claim freeze → independently sourced challenge → observable check → counterevidence/defeater → bounded gate, with explicit uncovered complement.

## EXPAND

- **To crypto-protocols:** decide whether any narrowly scoped current gate actually defines `(x,w,R,K,κ)`; if not, retain only the procedural analogy.
- **To method-topology:** add an extractor-obligation checkpoint before crypto terminology can enter the final method; route `I-PK-01`, `I-PK-06`, and `I-PK-09` to spec-adequacy/coverage/assurance work.
- **To evidence-authenticity:** operationalize `I-PK-10` with authorship, causal-lineage, and anti-replay predicates; transcript validity is not source authenticity.
- **To correlated-quorum:** use `I-PK-08` as the hard boundary against treating repeated same-model checks as confidence amplification.
- **To assurance-warrants:** attach every critical `R(x,w)` to a warrant and defeater showing why the encoded predicate supports the higher-level claim.
