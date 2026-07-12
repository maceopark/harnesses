# Cryptographic protocol principles for trustworthy conclusions from untrusted participants

Research date: 2026-07-10. Scope: cryptographic proof-system principles and their bounded transfer to requirements elicitation. This is a design-analogy assessment, not a claim that a human/LLM interview is a cryptographic protocol.

## Executive result

Cryptographic protocols obtain trustworthy acceptance from an untrusted prover only because the claim is reduced to a precisely defined language or relation, the verifier runs a specified randomized acceptance predicate, and security is quantified against a specified adversary under explicit assumptions. The transferable lesson is therefore **protocol structure and obligation discipline**, not a transferable proof guarantee.

The strongest safe pattern for requirements elicitation is:

1. define a falsifiable claim and an admissible evidence relation;
2. freeze the claim/evidence manifest before disclosing discriminating checks;
3. issue challenges selected independently of the answerer and bound to the exact claim/context;
4. require checkable responses and record acceptance/rejection reasons;
5. repeat or diversify challenges while tracking their dependence;
6. treat privacy, truth, provenance, and “knowledge” as separate properties;
7. preserve an independent verifier whose checking work is cheaper and more deterministic than generating the handoff.

This can reduce opportunistic revision and expose inconsistencies. It does **not** yield cryptographic soundness, completeness, zero knowledge, or extractability unless the interview has actually been compiled into a formal relation and verified by a real proof system.

## Primary-source account

### 1. Completeness, soundness, and prover/verifier asymmetry

Goldwasser–Micali–Rackoff introduced probabilistic interactive proofs with a powerful prover and an efficient verifier. Their motivating requirements are: a true theorem can be proved, a false theorem cannot be proved except with small probability, and verification is efficient even if proving is expensive ([GMR 1985, pp. 1–2](https://evervault.com/papers/zkp-1986.pdf)). Goldreich–Krawczyk state the modern quantified form: for inputs in the language, an honest prover makes the verifier accept with overwhelming probability (completeness); for inputs outside it, no prover behavior makes the verifier accept except with negligible probability (soundness) ([GK 1996, pp. 5–6](https://www.wisdom.weizmann.ac.il/~oded/PSX/zk-comp.pdf)). Thaler distinguishes a **proof**, sound even against computationally unbounded provers, from an **argument**, sound only against polynomial-time provers ([Thaler 2022, §3.1–3.2](https://people.cs.georgetown.edu/jthaler/ProofsArgsAndZK.pdf)).

Implications:

- Acceptance is meaningful only relative to a formal statement space, verifier algorithm, error bound, and adversary class.
- Completeness and soundness protect different failures: rejecting honest/true cases versus accepting malicious/false cases. Improving one does not automatically improve the other.
- The asymmetry is deliberate: the prover may spend much more work constructing a response, while the verifier executes a cheaper check.
- Repetition can reduce soundness error when its probabilistic and composition assumptions hold; it is not a license to multiply informal confidence scores.

### 2. Commitments

A commitment has a commit phase and an opening phase. Its two core security properties are **hiding** (the receiver cannot learn the committed value before opening) and **binding** (the committer cannot successfully open the same commitment to another value). Naor constructs bit commitment from pseudorandom generators and explicitly describes the locked-box intuition and later verification ([Naor 1991, pp. 1–2](https://www.wisdom.weizmann.ac.il/~naor/PAPERS/bit.pdf)). The properties can be computational or information-theoretic and are assumptions, not ordinary-language effects.

A commitment authenticates/fixes a value relative to an opening rule; it says nothing about whether the committed proposition is true. A signed or hashed false statement remains false.

### 3. Challenge–response and special soundness

Canonical three-message public-coin or Σ-style protocols have: prover commitment, verifier random challenge, prover response. Cramer–Damgård–Schoenmakers define **special soundness**: from two accepting conversations with the same first message and different challenges, a witness can be computed in polynomial time; this implies the usual knowledge-extractor condition for their protocol class ([CDS 1994, pp. 2–3](https://ir.cwi.nl/pub/1456/1456D.pdf)). Fiat–Shamir’s original identification construction also quantifies a cheating probability tied to guessing verifier challenges and argues that answering alternative challenges exposes forbidden algebraic knowledge ([FS 1987, pp. 3–4](https://dl.icdst.org/pdfs/files4/1ed5c255525327916ef6e93774be5840.pdf)).

The unpredictability and independence of the challenge are essential: the prover commits before learning what will be checked. “Ask another question” is not equivalent if the question is predictable, chosen by the answerer, or adaptively softened after seeing the first response.

### 4. Proofs of knowledge and extractability

Soundness of a statement and knowledge of a witness are not identical. A proof of knowledge is defined for a fixed binary relation through an extractor that, given oracle-style access to a successful prover, outputs a witness; Bellare–Goldreich additionally tie expected extraction work inversely (up to a polynomial factor) to the prover's acceptance probability. They warn that commonly cited PoK formalizations were inadequate for some applications and proposed a corrected definition ([Bellare–Goldreich 1992, pp. 2–8](https://www.wisdom.weizmann.ac.il/~oded/PSX/pok.pdf)). In special-sound protocols, the extractor commonly rewinds the prover to the same commitment and supplies different challenges; two valid responses algebraically reveal the witness ([CDS 1994](https://ir.cwi.nl/pub/1456/1456D.pdf)).

Extractability is therefore a theorem about a machine model and relation, not a synonym for “the answers sounded knowledgeable.” Even within cryptography, extraction technique and adversary model matter: quantum adversaries required new rewinding definitions and techniques ([Unruh 2012/2015](https://eprint.iacr.org/2010/212.pdf)).

### 5. Zero knowledge

Zero knowledge is not “little information was disclosed.” It is simulation-based: for every allowed malicious verifier, there is an efficient simulator whose output distribution is identical, statistically close, or computationally indistinguishable from the verifier’s real view, using only the public statement (and permitted auxiliary input) ([GMR 1985](https://evervault.com/papers/zkp-1986.pdf); [GK 1996, §2](https://www.wisdom.weizmann.ac.il/~oded/PSX/zk-comp.pdf)).

Important separations:

- Zero knowledge is a privacy property, not truthfulness or knowledge soundness; those require separate completeness/soundness/extraction arguments.
- Honest-verifier zero knowledge (HVZK) protects only against a verifier that follows the challenge distribution. CDS explicitly notes that HVZK need not protect against a cheating verifier ([CDS 1994, pp. 1–3](https://ir.cwi.nl/pub/1456/1456D.pdf)).
- Composition is nontrivial. Goldreich–Krawczyk show the original definition is not generally closed under sequential composition and even strong black-box formulations are not generally closed under parallel execution; naive parallel repetition can sacrifice zero knowledge ([GK 1996](https://www.wisdom.weizmann.ac.il/~oded/PSX/zk-comp.pdf)).

### 6. Fiat–Shamir: power and assumptions

Fiat–Shamir replaces an interactive verifier’s public random challenge with a deterministic hash of the prior transcript and (for signatures/proofs) the message/statement, yielding a non-interactive object ([Fiat–Shamir 1987](https://dl.icdst.org/pdfs/files4/1ed5c255525327916ef6e93774be5840.pdf)). Security results commonly model that hash as a random oracle and use forking/reprogramming arguments.

The assumption boundary is material:

- Canetti–Goldreich–Halevi construct schemes secure in the random-oracle model but insecure under **every** concrete hash-function implementation, proving that ROM security does not generically instantiate ([CGH 1998/2002](https://eprint.iacr.org/1998/011.pdf)).
- Goldwasser–Kalai construct secure three-round public-coin identification schemes for which the Fiat–Shamir signature is insecure for any hash implementation, despite positive ROM results ([GK 2003](https://doi.org/10.1109/SFCS.2003.1238185)).
- Bernhard–Pereira–Warinschi identify weak versus strong Fiat–Shamir transformations and practical pitfalls in Helios ([BPW 2012](https://doi.org/10.1007/978-3-642-34961-4_38)).
- Recent work gives explicit false-statement attacks for some proof systems when a prover-controlled circuit can incorporate the challenge hash, underscoring adaptive-statement/context-binding hazards ([KRS 2025](https://eprint.iacr.org/2025/118.pdf)).
- A current IRTF draft therefore binds protocol ID, session ID, statement/instance label, codecs, and the evolving transcript into the Fiat–Shamir state. It is an Internet-Draft, not a final RFC, but it is strong operational evidence about the context-binding surface ([draft-irtf-cfrg-fiat-shamir-00](https://www.ietf.org/archive/id/draft-irtf-cfrg-fiat-shamir-00.html), accessed 2026-07-10).

Fiat–Shamir does not say “replace any independent reviewer with a deterministic question generator.” It applies to specified public-coin proof protocols under substantial encoding, binding, and oracle-model assumptions.

## Bounded transfer matrix

| Source primitive | Required assumptions in cryptography | Requirements-interview analogue | Preserved heuristic | Lost property / unsafe analogy | Falsifier for the analogue |
|---|---|---|---|---|---|
| Completeness | Formal language/relation; honest prover strategy; quantified randomness | Legitimate requirements and evidence have an admissible path to acceptance | Define what sufficient evidence looks like; track false rejection | “All true requirements will emerge.” Humans may omit, misunderstand, or lack evidence | Known valid requirement repeatedly cannot pass the rubric |
| Soundness | Formal verifier; adversary class; soundness bound | Unsupported or contradictory handoffs fail deterministic gates | Separate claim generation from acceptance; require falsifiable checks | “A passed interview is probably correct” or numeric soundness error | False seeded claims pass without violating a stated check |
| Proof vs argument | Unbounded vs computationally bounded cheating prover | Decide which manipulations/threat capabilities the process covers | State attacker/participant capability assumptions | Calling heuristic resistance “proof” | Stronger but plausible adversary bypasses the gate |
| Commitment | Hiding and binding scheme; opening verification; identity/context binding | Freeze claim, assumptions, evidence manifest before challenge/review | Prevent silent post-hoc rewriting; make revisions explicit | Commitment proves truth, provenance, authority, or freshness | Two incompatible openings accepted, or fixed false claim accepted as true |
| Challenge–response | Challenge sampled after commitment, unpredictable to prover, correct distribution | Ask discriminating questions only after baseline claim is frozen | Reduces tailoring to known checklist; probes alternative hypotheses | Any follow-up question creates cryptographic soundness | Answerer can predict/control challenges or reviewer changes them to fit answers |
| Special soundness | Same first message/state; distinct challenges; extraction algorithm | Branch tests from one frozen claim; compare implications under counterfactuals | Inconsistency between branches is diagnostically useful | Two answers extract the underlying requirement/witness | No deterministic witness can be computed, or participant state changed between branches |
| Repetition/amplification | Independent (or proven-composable) challenges and known base error | Multiple diverse probes, reviewers, or evidence channels | More independent failure opportunities can increase confidence | Multiply confidence as if errors were independent; parallelization is always safe | Challenges share source/model/data or copy one another’s conclusions |
| Zero knowledge | Efficient simulator for every allowed verifier; indistinguishable views; composition theorem | Data minimization: prove only claim-relevant facts, segregate sensitive evidence | Minimize disclosure and public transcript contents | Redaction, NDA, “need to know,” or concise answers are zero knowledge | Transcript permits inference unavailable from the public claim alone |
| Extractability / PoK | Formal relation; black-box/non-black-box extractor; rewind/access model; knowledge error | Demand concrete artifacts that operationalize asserted knowledge | Prefer executable examples and traceable evidence over fluency | Interviewer “extracts knowledge” from coherent prose | No witness/artifact can be recovered or independently checked from accepted responses |
| Verifier/prover asymmetry | Powerful prover, efficient probabilistic verifier, exact predicate | Author/agent does expensive synthesis; independent reviewer runs cheap decisive gates | Push complexity into evidence construction; keep acceptance small and auditable | Human judgment can cheaply verify any semantic claim | Reviewer must redo the full investigation or relies on the same opaque model |
| Fiat–Shamir | Public-coin protocol; random-oracle/transform theorem; full transcript/statement/context binding; canonical encoding | Deterministically derive reproducible audit prompts from a frozen, canonical handoff | Reproducible prompt selection and tamper-evident context binding | Self-generated hash challenge replaces an independent verifier or inherits soundness | Answerer can grind/reframe inputs, omit context, or choose semantically equivalent encodings to get favorable prompts |

## Concrete design recommendations for requirements elicitation

1. **Use cryptographic vocabulary only for implemented properties.** Name informal mechanisms “commit-before-challenge,” “independent challenge,” “evidence gate,” or “privacy-minimizing disclosure,” not “sound,” “zero knowledge,” or “proof of knowledge.”
2. **Define the statement before collecting proof.** Every challenge must refer to a stable claim ID, scope, assumptions, and acceptance predicate. Ambiguous claims make soundness undefined.
3. **Freeze, then challenge.** Record the original answer and evidence inventory before disclosing red-team questions. Permit changes, but preserve a visible delta and invalidate stale approvals.
4. **Keep challenge selection independent.** Use reviewer randomness, precommitted challenge pools, or separately owned threat lenses. If deterministic derivation is wanted for reproducibility, bind the full canonical claim, scope, session, protocol version, and prior transcript; do not claim Fiat–Shamir security.
5. **Design branch challenges around falsifiers.** Ask what evidence would distinguish competing requirements, what observation would refute the current answer, and what downstream behavior changes under each branch.
6. **Do not score correlated repetitions as independent.** Multiple agents sharing the same model, context, retrieval corpus, or earlier summary are one observation group unless independence is demonstrated.
7. **Separate four ledgers:** semantic truth/evidence, provenance/authenticity, revision history/commitment, and confidentiality/disclosure. No one ledger substitutes for another.
8. **Require witness-like artifacts where possible.** Examples: executable acceptance test, schema instance, API trace, decision table, source line, signed stakeholder approval. Call these independently checkable evidence, not extracted knowledge.
9. **Make verifier work decisively cheaper.** If approval requires redoing the whole interview, the handoff is not proof-carrying. Put compact machine-checkable predicates beside narrative rationale.
10. **Track completeness and soundness failures separately.** Seed known-valid cases to measure over-rejection and known-false/contradictory cases to measure under-rejection. Do not collapse them into one quality score.
11. **Treat privacy composition as a first-class risk.** Individually harmless answers can jointly reveal sensitive strategy or identity. Define transcript retention, linkage, and audience before elicitation.

## Counter-search and limits

The counter-search looked specifically for failures of random-oracle instantiation, Fiat–Shamir, zero-knowledge composition, extraction/rewinding, and unconditional commitments.

- ROM proof does not generically imply security for any concrete hash: CGH is a formal counterexample.
- Secure interactive identification does not generically survive Fiat–Shamir: Goldwasser–Kalai is a formal counterexample.
- Weak transcript/statement binding has practical protocol consequences: BPW and the IRTF draft document this surface.
- Zero knowledge is not automatically preserved by sequential/parallel composition: Goldreich–Krawczyk provides lower bounds and counterexamples.
- Extractors are model-specific; even moving from classical to quantum adversaries requires different techniques: Unruh and later quantum-rewinding work show the assumption sensitivity.
- A plain transcript hash is not a commitment to truth and may not establish identity, authority, timestamp freshness, or canonical semantic equivalence.
- Human/LLM participants are stateful, non-resettable, semantically adaptive, and often correlated. The “same prover state under two challenges” condition needed by special-soundness extraction is unavailable.
- Natural-language requirements generally lack a decidable relation and complete witness set. Therefore “soundness,” “completeness,” and “knowledge error” have no numerical meaning until a bounded formal subclaim is defined.

## Search trace

Twenty-five varied English searches were run across primary paper repositories, author pages, publisher records, standards/drafts, and counterexample literature. Representative queries:

1. `Goldwasser Micali Rackoff 1985 knowledge complexity interactive proof systems PDF completeness soundness`
2. `Goldreich Foundations Cryptography proof systems completeness soundness knowledge soundness PDF`
3. `Blum 1981 coin flipping over telephone commitment scheme PDF`
4. `Naor 1991 bit commitment statistically binding computationally hiding PDF`
5. `Schnorr 1991 efficient signature generation smart cards challenge response proof of knowledge PDF`
6. `Cramer Damgard Schoenmakers 1994 proofs partial knowledge sigma protocols special soundness PDF`
7. `Fiat Shamir 1986 how to prove yourself practical solutions identification signature PDF`
8. `Pointcheval Stern 1996 security proofs signature schemes random oracle Fiat Shamir forking lemma PDF`
9. `Goldreich Oren 1994 definitions properties zero knowledge proof systems noninteractive impossibility PDF`
10. `Feige Fiat Shamir 1988 zero knowledge proofs of identity proof of knowledge extraction PDF`
11. `Bellare Goldreich 1992 defining proofs of knowledge extractor PDF`
12. `Goldreich Krawczyk 1996 composition zero knowledge proof systems constant round black box simulation PDF`
13. `Canetti Goldreich Halevi 1998 random oracle methodology revisited PDF uninstantiable schemes`
14. `Goldwasser Kalai 2003 Fiat Shamir transformation signature insecure PDF`
15. `Bernhard Pereira Warinschi 2012 how not to prove yourself Fiat Shamir weaknesses PDF`
16. `commitment scheme unconditional hiding binding impossibility Mayers Lo Chau bit commitment classical explanation primary paper`
17. `site:datatracker.ietf.org Fiat Shamir transform draft CFRG transcript domain separation challenge`
18. `site:nist.gov zero knowledge proof standards Fiat Shamir challenge response`
19. `IETF sigma protocols Fiat Shamir transcript hash context binding specification`
20. `Justin Thaler Proofs Arguments and Zero Knowledge verifier prover asymmetry soundness completeness PDF`
21. `proof of knowledge extraction rewinding limitations concurrent protocols black box extractor primary paper PDF`
22. `knowledge extraction impossibility meta reduction Fiat Shamir primary paper`
23. `Unruh quantum proofs of knowledge rewinding extractor impossibility PDF`
24. `How to Prove False Statements Fiat-Shamir eprint 2024`
25. `practical attacks on Fiat-Shamir adaptive soundness full statement hash 2024 paper`

No second expansion pass produced a principle that changes the safe-transfer boundary: all new leads refined assumption sensitivity (adaptive statement binding, quantum rewinding, concrete transcript encoding) rather than supporting cryptographic guarantees for natural-language interviews.

## Ranked source set

1. Goldwasser, Micali, Rackoff, “The Knowledge Complexity of Interactive Proof-Systems” (STOC 1985 / SIAM J. Comput. 1989), primary: https://evervault.com/papers/zkp-1986.pdf
2. Bellare, Goldreich, “On Defining Proofs of Knowledge” (CRYPTO 1992), primary author copy: https://www.wisdom.weizmann.ac.il/~oded/PSX/pok.pdf
3. Cramer, Damgård, Schoenmakers, “Proofs of Partial Knowledge…” (CRYPTO 1994), primary: https://ir.cwi.nl/pub/1456/1456D.pdf
4. Fiat, Shamir, “How to Prove Yourself” (CRYPTO 1986/1987), primary: https://dl.icdst.org/pdfs/files4/1ed5c255525327916ef6e93774be5840.pdf
5. Naor, “Bit Commitment Using Pseudorandomness” (J. Cryptology 1991), primary author copy: https://www.wisdom.weizmann.ac.il/~naor/PAPERS/bit.pdf
6. Canetti, Goldreich, Halevi, “The Random Oracle Methodology, Revisited” (STOC 1998 / JACM 2004), primary: https://eprint.iacr.org/1998/011.pdf
7. Goldwasser, Kalai, “On the (In)security of the Fiat-Shamir Paradigm” (FOCS 2003), primary DOI: https://doi.org/10.1109/SFCS.2003.1238185
8. Goldreich, Krawczyk, “On the Composition of Zero-Knowledge Proof Systems” (SIAM J. Comput. 1996), primary author copy: https://www.wisdom.weizmann.ac.il/~oded/PSX/zk-comp.pdf
9. Bernhard, Pereira, Warinschi, “How Not to Prove Yourself” (ASIACRYPT 2012), primary DOI/repository: https://doi.org/10.1007/978-3-642-34961-4_38
10. Khovratovich, Rothblum, Soukhanov, “How to Prove False Statements” (CRYPTO 2025), primary: https://eprint.iacr.org/2025/118.pdf
11. Unruh, “Quantum Proofs of Knowledge” (EUROCRYPT 2012), primary: https://eprint.iacr.org/2010/212.pdf
12. IRTF CFRG, “Fiat-Shamir Transformation,” Internet-Draft -00, current draft/specification evidence (not final standard), accessed 2026-07-10: https://www.ietf.org/archive/id/draft-irtf-cfrg-fiat-shamir-00.html
13. ZKProof Σ-protocol Working Group, “A Spec for Σ-Protocols” v0.2, current technical specification evidence, accessed 2026-07-10: https://sigma.zkproof.org/tex-spec.pdf
14. Thaler, “Proofs, Arguments, and Zero-Knowledge” (2022), strong independent secondary synthesis: https://people.cs.georgetown.edu/jthaler/ProofsArgsAndZK.pdf

## OBSERVATIONS

- O1: GMR formalizes probabilistic acceptance with an efficient verifier and much more powerful prover; the efficient verifier is not optional.
- O2: Completeness quantifies honest/true acceptance; soundness quantifies malicious/false acceptance. They are logically separate.
- O3: Commitments supply hiding and binding, not truth, provenance, authority, or freshness by themselves.
- O4: Σ special soundness relies on identical first message plus distinct challenges and an explicit polynomial-time extraction algorithm.
- O5: PoK is extractor-defined; successful verification alone does not establish knowledge.
- O6: Zero knowledge is simulator/indistinguishability-defined, is separate from soundness, and is composition-sensitive.
- O7: Fiat–Shamir security is theorem- and model-dependent; full statement, protocol, session, encoding, and transcript binding are part of the security surface.
- O8: There are primary formal counterexamples to generic ROM instantiation and generic Fiat–Shamir preservation.
- O9: Current specifications emphasize domain separation, session IDs, instance labels, canonical codecs, and complete transcript absorption, but remain drafts/specification work rather than universal security proofs.
- O10: Natural-language interviews lack the formal relation, resettable prover, extraction algorithm, and quantified challenge distribution needed to inherit cryptographic guarantees.

## CLAIMS

- CLAIM: Interactive proof acceptance is trustworthy only relative to a formal language/relation, quantified completeness/soundness bounds, an efficient verifier, and a stated adversary model. — RISK: high — SOURCES: evervault.com/GMR; wisdom.weizmann.ac.il/GK; people.cs.georgetown.edu/Thaler — COUNTER: searched for definitions omitting these elements; only informal explanations did so — PRIMARY: GMR 1985; GK 1996
- CLAIM: A cryptographic commitment fixes/hides a value under opening rules but does not prove the value’s semantic truth. — RISK: high — SOURCES: wisdom.weizmann.ac.il/Naor; sigma.zkproof.org specification — COUNTER: searched commitment impossibility and unconditional commitment variants; none turn binding into truth — PRIMARY: Naor 1991
- CLAIM: Special-soundness extraction requires accepting transcripts sharing the same first message under different challenges and a relation-specific extractor. — RISK: high — SOURCES: ir.cwi.nl/CDS; wisdom.weizmann.ac.il/Bellare-Goldreich — COUNTER: searched extractor/rewinding limits; results reinforced model dependence — PRIMARY: CDS 1994; Bellare–Goldreich 1992
- CLAIM: Zero knowledge is a simulator-based privacy property, distinct from truth/soundness/knowledge, and is not generically preserved by naive composition. — RISK: high — SOURCES: evervault.com/GMR; wisdom.weizmann.ac.il/GK composition — COUNTER: searched parallel/sequential composition; GK gives formal negative results — PRIMARY: GMR 1985; GK 1996
- CLAIM: Fiat–Shamir does not generically preserve security when a random oracle is replaced by an arbitrary concrete hash; context/statement/transcript binding is necessary but not a universal sufficiency theorem. — RISK: high — SOURCES: eprint.iacr.org/CGH; doi.org/Goldwasser-Kalai; ietf.org IRTF draft; uclouvain.be/BPW — COUNTER: searched positive Pointcheval–Stern/modern ROM results; these are conditional and do not refute the standard-model counterexamples — PRIMARY: CGH 1998; Goldwasser–Kalai 2003; BPW 2012
- CLAIM: Commit-before-challenge, independent discriminating challenges, explicit acceptance predicates, and cheap independent verification are defensible design heuristics for requirements elicitation, but no cryptographic error bound transfers. — RISK: normal — SOURCES: GMR; CDS; Naor; Thaler — COUNTER: searched for a formal reduction from natural-language interviewing to proof systems; none found — PRIMARY: analogy is an explicit inference from the cited primitives, not a source claim
- CLAIM: Calling interview transcripts “zero knowledge,” accepted prose “proof of knowledge,” or deterministic self-questioning “Fiat–Shamir” is unsafe without an implemented simulator/extractor/formal relation and transform theorem. — RISK: high — SOURCES: Bellare–Goldreich; GK composition; CGH; Goldwasser–Kalai — COUNTER: searched standards and tutorials for relaxed definitions; rigorous sources retain the formal requirements — PRIMARY: Bellare–Goldreich 1992; CGH 1998; Goldwasser–Kalai 2003

## EXPAND

- LEAD: Compile a small subset of requirements claims into a decidable relation with executable witnesses, then test whether an actual proof-carrying handoff is feasible. — WHY: this is the only path from analogy to a real soundness claim. — ANGLE: acceptance-test DSL, schema constraints, trace attestations, proof-carrying data.
- LEAD: Measure challenge dependence empirically across reviewers/models/corpora. — WHY: repetition only helps when errors/challenges are sufficiently independent. — ANGLE: seeded false/true requirements, blinded reviewers, correlation matrix, conditional error rates.
- LEAD: Threat-model transcript grinding and semantic re-encoding. — WHY: deterministic prompt derivation can be gamed by rephrasing or selectively omitting context. — ANGLE: canonicalization, full-context binding, precommitted challenge pools, adversarial search.
- LEAD: Define privacy composition for interview transcripts. — WHY: “minimal disclosure” per answer can still leak sensitive facts jointly. — ANGLE: linkage, retention, auxiliary information, role-scoped views, simulator-style red-team test.
- DEAD END: No rigorous source supports inheriting cryptographic soundness, zero knowledge, or extractability for ordinary requirements interviews solely by adopting analogous vocabulary or conversational stages.
