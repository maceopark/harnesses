# Skeptical mapping: security and formal-method analogies for requirements interviewing

Scope: read-only red-team of proposed mappings into `ultimateinterview`, grounded in the live contract and critical/primary sources. The standard is not whether an analogy is evocative; it is whether the source discipline's guarantee survives transfer.

## Bottom line

Use these fields as **engineering control patterns**, never as inherited assurance claims. A requirements interview has no cryptographic witness relation, no extractor, no bounded Byzantine fault model, no independent replica population, no complete formal model, and no oracle for stakeholder intent. Its strongest honest claim remains the one already at `.agents/skills/ultimateinterview/SKILL.md:8`: implementation-ready under recorded evidence, not proof that uncertainty is zero.

The live contract already contains several sound nonclaims: model priors are hypothesis-only (`SKILL.md:35`); self-audit is circular (`:40`); no-divergence gets zero evidence/completeness credit (`:68`); single-source owner acceptance is governance, not a second epistemic source (`:80`); and handoff coverage cannot detect semantic narrowing without a human (`:52`). Preserve these boundaries.

## Red-team matrix

### 1. "Proof of knowledge" -> an answer demonstrates that the stakeholder knows the requirement

- Category error: cryptographic proof of knowledge is defined through an efficiently checkable relation and an extractor with oracle/rewinding access to the prover. A plausible answer or accepted transcript supplies neither. Bellare and Goldreich warn that earlier PoK formalizations misled applications.
- Security-theater risk: vocabulary such as `soundness`, `witness`, `extract`, or `proof` causes confidence to jump without adding an observable.
- Counterexample: a stakeholder can consistently repeat a policy inherited from docs yet lack knowledge of runtime behavior; a coached respondent can pass challenge questions.
- Falsifier/boundary: the mapping becomes literal only if each claim has a machine-checkable witness relation and an extraction algorithm satisfying a stated knowledge-error bound. Human questioning does not.
- Safe replacement: **claim substantiation** — record answer, authority, evidence route, counterevidence, and an operational check. Say “the answer survived these probes,” never “knowledge was proved.”
- Sources: Bellare & Goldreich, [On Defining Proofs of Knowledge](https://www.wisdom.weizmann.ac.il/~oded/pok.html); modern definition example, [Zero-Knowledge Proofs of Training](https://eprint.iacr.org/2024/162.pdf).

### 2. Challenge-response / sigma protocol -> pressure follow-up makes a claim sound

- Category error: sigma-protocol soundness depends on a commitment causally preceding an unpredictable challenge, a formal relation, and special-soundness/extraction properties. An interviewer writes both questions and scoring rules; the respondent sees the conversational frame and can adapt a narrative.
- Counterexample: repeated “what would falsify this?” questions can select for rhetorically robust stories, not true ones; later answers may simply conform to earlier transcript commitments.
- Correlated failure: question author, evaluator, and ledger updater are often the same model and share one context.
- Falsifier/boundary: gains count only when a predeclared challenge has a discriminatory expected outcome and the answer is checked against an external observation not generated from the answer.
- Safe replacement: **precommitted adversarial probe** — persist the claim and expected discriminating observation before running the probe; treat narrative consistency as zero independent evidence.

### 3. Fiat-Shamir -> hash the transcript/digest the contract to remove interaction or make review objective

- Category error: Fiat-Shamir security is protocol- and model-dependent, typically relying on a random-oracle argument. Hashing natural-language interview state produces integrity binding, not unpredictable challenges, soundness, or truth.
- Counterexample: Canetti–Goldreich–Halevi construct schemes secure in the random-oracle model but insecure under every concrete hash; Goldwasser–Kalai give secure interactive identification schemes whose Fiat-Shamir transform is insecure for any hash.
- Falsifier/boundary: only use the name if there is a proven transform for the exact protocol and instantiated assumptions. There is none for requirements interviews.
- Safe replacement: **content-addressed snapshot** — a digest detects accidental/unauthorized changes relative to an externally anchored value; it says nothing about content adequacy.
- Sources: Canetti, Goldreich & Halevi, [The Random Oracle Methodology, Revisited](https://arxiv.org/abs/cs/0010019); Goldwasser & Kalai, [On the (In)security of the Fiat-Shamir Paradigm](https://doi.org/10.1109/SFCS.2003.1238185).

### 4. Zero knowledge -> reveal only what the implementer needs

- Category error: zero knowledge is a simulator-based indistinguishability property about leakage while proving a formal statement. Selective disclosure, summarization, or Part-1-only reading is not zero knowledge.
- Counterexample: a summary can omit a constraint and still look minimal; cryptographic ZK can produce simulated transcripts, so transcript realism itself does not establish a witness.
- Falsifier/boundary: literal only with a formal simulator, adversarial view, and leakage definition.
- Safe replacement: **least-necessary disclosure with traceable redaction** — enumerate omitted fields, owner, and re-access route; do not claim privacy beyond the storage/access controls actually used.

### 5. Commitment / immutable ledger -> the intent cannot be repudiated or rewritten

- Category error: local append-only JSON or a digest is mutable by anyone controlling the workspace unless the commitment is externally anchored and verification keys/log consistency are protected.
- Replay/freshness risk: an old valid snapshot can be replayed; a fresh digest can faithfully bind stale or false content.
- Falsifier/boundary: tamper evidence is credible only when an independently held anchor, authenticated signer, freshness rule, and verification procedure exist.
- Safe replacement: **versioned, content-addressed audit record** — state the mutation authority and freshness invalidation; avoid `immutable`, `nonrepudiable`, or `commitment` unless implemented.
- Source boundary: NIST explicitly distinguishes algorithm/module validation from correct product use and notes embedded validation gives no assurance of correct utilization: [CMVP FAQ](https://csrc.nist.gov/Projects/cryptographic-module-validation-program/FAQs).

### 6. Zero trust -> trust no claim; continuously verify every requirement

- Category error: NIST zero trust removes *implicit* trust based on network location; it does not eliminate trust. It relocates trust into identities, policy, telemetry, PDP/PEP, and enforcement. An interview has semantic claims, not resource-access requests.
- Security-theater risk: “never trust, always verify” hides the central interviewer/model as policy author, evidence classifier, decision point, and enforcement point.
- Counterexample: poisoned repo evidence or a misclassified `independence_group` is repeatedly re-evaluated by the same policy and remains accepted; continuous repetition does not add independence.
- Falsifier/boundary: the analogy is useful only when the protected resource, policy subject, decision authority, enforcement action, telemetry, revocation event, and trust anchors are explicitly named.
- Safe replacement: **no implicit epistemic credit + event-triggered revalidation** — evidence receives only typed, scoped credit; material revision/age/counterevidence triggers review. Do not promise continuous semantic verification.
- Sources: [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final); Google’s own [BeyondCorp long-tail account](https://www.usenix.org/publications/loginonline/beyondcorp-and-long-tail-zero-trust) documents exceptions, incompatible workflows, coarse controls, and trust shifted to overlay/inventory systems; [Building a Healthy Fleet](https://www.usenix.org/publications/login/fall2018/king) says any security capability is only as secure as the systems it trusts.

### 7. PDP/PEP separation -> deterministic gate makes the requirements policy true

- Category error: enforcement can prove only that declared policy was applied. It cannot prove policy correctness or the truth/completeness of evidence inputs.
- Counterexample: a strict schema admits a confidently wrong requirement; a gate blocks a correct but unmodeled exception.
- Executed local counterexample: the current policy/head checks accepted `python3 -m pytest tests/definitely-missing.py` even though the target does not exist. This demonstrates parse/head resolvability, not executability or result truth. Freshness, group identity, and reviewer identity are also self-attested rather than authenticated.
- Falsifier/boundary: semantic assurance rises only when policy authorship, reviewer authority, enforcement, and appeal/change paths are separately exercised and the policy is tested against real outcomes.
- Safe replacement: **mechanical conformance gate** — label every gate as shape, traceability, freshness, authorization, or executed-behavior enforcement. Maintain a separate human/runtime validation claim.

### 8. Byzantine quorum / consensus -> two independent evidence groups establish truth

- Category error: BFT consensus establishes agreement/safety under a specified communication model and an explicit bound on faulty replicas; agreement is not external truth. Interview evidence sources are not deterministic replicas, and no `f` bound exists.
- Correlated failure: code, docs, tests, and LLM reviewers may all descend from the same mistaken requirement; “two groups” can be one causal lineage with two labels.
- Counterexample: Knight and Leveson’s 27 independently developed program versions failed together substantially more often than the independence model predicted; shared specifications induce common-mode faults. Their result is bounded to that experiment, not a universal rate.
- Falsifier/boundary: quorum language is justified only if the fault model, threshold, membership, independence evidence, and validity rule are explicit. Merely different channels/models/vendors is insufficient.
- Safe replacement: **causal-lineage triangulation** — require an independence rationale and test it through provenance; if lineages share prompt, source corpus, spec, operator, or evaluator, count once. Treat agreement as confidence evidence, never truth.
- Sources: Lamport et al., [The Byzantine Generals Problem / bounds](https://www.microsoft.com/en-us/research/?p=338426); Knight & Leveson, [An Experimental Evaluation of the Assumption of Independence](https://libraopen.library.virginia.edu/entities/publication/4ac33eeb-79b4-46e4-aef9-f6ec56a62286); NASA follow-up on [correlated failures](https://ntrs.nasa.gov/citations/19900041359).

### 9. Threshold trust -> two reviewers or two L1 producers are enough

- Category error: threshold cryptography assumes distinct protected key shares and an adversary unable to corrupt the threshold. Two LLM calls do not hold independently protected epistemic shares.
- Counterexample: two “fresh” reviewers using the same base model, training corpus, repo, prompt, and acceptance rubric reproduce the same omission.
- Falsifier/boundary: count separate producers only after identifying non-shared causal dependencies and a failure mode that one can catch independently.
- Safe replacement: **heterogeneous evidence portfolio** — combine differently generated observations (e.g., static code path, runtime trace, accountable owner decision), then test contradictions. Do not set a magic reviewer count.

### 10. Formal specification / refinement -> controlled-language requirements are formally verified

- Category error: making a sentence decidable or machine-parseable is not proving it matches stakeholder intent. Formal verification establishes a theorem relative to a model, semantics, axioms, and trusted toolchain.
- Counterexample: Lamport describes TLC as finding errors in a specification and notes a syntactically correct spec may not capture author intent; TLC explores a finite instance. seL4 explicitly lists hardware, boot, assembly, DMA, and configuration assumptions and says a verified kernel does not automatically make a secure system.
- Falsifier/boundary: a formal claim must name the property, model, checked state space/proof, assumptions, TCB, and excluded environment. An executable acceptance criterion is merely testable until that exists.
- Safe replacement: **decidable contract + explicit model boundary** — say what the checker proves and what remains a validation question. Use formal methods for internal consistency/refinement, not discovery completeness.
- Sources: Lamport, [TLA+ Models vs TLC Models](https://lamport.azurewebsites.net/tla/model-popup.html) and [TLC description](https://lamport.azurewebsites.net/tla/xmxx99-07-16.pdf); [seL4 proof assumptions FAQ](https://sel4.systems/About/FAQ.html); NASA’s explicit split between verification and validation, [Systems Engineering Handbook](https://www.nasa.gov/reference/5-0-product-realization/).

### 11. Proof obligations / proof-carrying handoff -> every REQ/VER pair proves the build contract

- Category error: coverage is conditional on the obligation generator. If requirements omit a hazard, 100% REQ->VER coverage certifies the omission. A proof-carrying object also depends on checker, logic, semantics, and trusted base.
- Counterexample: a test named for every REQ passes while all REQs encode the wrong behavior; the live contract itself admits `handoff_coverage.py` proves citation, while a human must detect behavior narrowing (`SKILL.md:52`).
- Executed local counterexample: ID-only coverage accepted an unrelated footnote mentioning `REQ-777` while the required A/B/C behavior was absent. A direct low-weight ledger addition also left the composite gate ready because it did not advance `material_revision`. These are concrete boundaries on trace/freshness claims, not allegations that the shape gates failed their documented job.
- Falsifier/boundary: coverage supports adequacy only if an independently justified completeness argument exists for the requirement set and verification environment.
- Safe replacement: **machine-checkable traceability obligations** — use strict IDs, digests, and total result coverage to prevent silent loss, while separately recording semantic validation and unknown-unknown residuals.
- Supporting boundary: CompCert proves generated code matches source semantics; it does not prove the source program fulfills user intent: [CompCert](https://compcert.org/).

### 12. Model checking -> a dry open-world sweep proves no gaps remain

- Category error: finite-state exploration establishes absence of counterexamples only within the encoded model/bounds. A generative “sweep” has neither a closed state space nor exhaustive transition relation.
- Goodhart effect: requiring two dry sweeps and capping surviving hypotheses at three optimizes the production and disposition of candidate records, not discovery recall. Unknown unknowns have no measurable denominator.
- Counterexample: two identical prompts over the same repository miss the same absent stakeholder or runtime environment.
- Falsifier/boundary: “dry” means only “this named method, corpus, model/version, prompt, and budget produced no new candidate.” Any broader completeness claim is false unless the search space is closed and enumerated.
- Safe replacement: **bounded negative search record** — persist scope, method, budget, mutation/revision binding, and blind spots; retain the current rule that dry/no-divergence adds zero completeness credit.

### 13. Assurance case -> structured evidence and defeaters establish readiness

- Category error: an assurance case is a defeasible argument, not a proof machine. Its strength is bounded by evidence quality, identified defeaters, reviewer independence, and organizational incentives.
- Security-theater/Goodhart risk: tables, trace links, strict schemas, and “fresh review” can become a paperwork/tick-box exercise; optimization favors a complete-looking case and hides unmodeled hazards.
- Counterexample: the Nimrod safety case existed before a fatal crash, yet missed/buried the key hazard; Haddon-Cave described paperwork/tick-box behavior, lack of operator input, and the need for organizationally distinct review. This is a counterexample to “case present -> safe,” not to all assurance-case use.
- Falsifier/boundary: the case earns confidence only insofar as operators/runtime evidence participate, rebutting/undermining/undercutting defeaters are actively sought, residual doubt remains visible, and the reviewer can reject the case independently.
- Safe replacement: **living, defeasible requirements argument** — organize claims/evidence/defeaters, but call the result reviewed readiness under stated evidence. Keep uneliminated defeaters and missing evidence first-class.
- Sources: UK [Nimrod Review](https://www.gov.uk/government/publications/the-nimrod-review); Haddon-Cave’s [post-Nimrod safety-case shortcomings](https://www.judiciary.uk/wp-content/uploads/2017/06/mj-haddon-cave-nuclear-industry-association-speech-zen-and-safety-cases-20170620.pdf); Leveson, [Use of Safety Cases in Certification and Regulation](https://onlinepubs.trb.org/onlinepubs/PBRLit/Leveson.pdf); SEI, [Toward a Theory of Assurance Case Confidence](https://insights.sei.cmu.edu/library/toward-a-theory-of-assurance-case-confidence/); NASA, [Formal Assurance Arguments: A Solution in Search of a Problem?](https://ntrs.nasa.gov/api/citations/20160006364/downloads/20160006364.pdf).

### 13a. Requirements extraction -> interviewing recovers a pre-existing complete intent

- Category error: requirements interviews are generative transformations, not witness extraction. The analyst's framing, examples, domain research, and synthesis co-create normative requirements.
- Counterexample: Ferrari, Spoletini, and Debnath found only 30–38% of post-interview requirements fully traceable to the fictional customer's initial ideas in a 30-analyst controlled study; the result is bounded to that study. Spoletini et al. found 68% of detected ambiguities during later recording review in a 42-student study, showing that a completed live interview is not a completeness boundary.
- Falsifier/boundary: extraction language is acceptable only for verbatim source recovery. For the final contract, preserve separate links for source statement, analyst inference, and normative requirement, and label analyst-added content.
- Safe replacement: **traceable co-creation** — test stakeholder/source coverage and review recordings, but state the uncovered population and method limits. Purposive interview agreement is not statistical generalization.
- Sources: Ferrari et al., [Requirements elicitation interviews as co-creation](https://link.springer.com/article/10.1007/s00766-022-00383-7); Spoletini et al., [recording review and later ambiguity detection](https://par.nsf.gov/servlets/purl/10061985); OMB, [Cognitive Interviewing Methodology](https://obamawhitehouse.archives.gov/sites/default/files/omb/inforeg/directive2/final_addendum_to_stat_policy_dir_2.pdf).

### 14. LLM debate / critic quorum -> independent agents reliably eliminate hallucination

- Category error: an LLM judge is another fallible measurement instrument, not a truth oracle. Model diversity can be superficial; prompts, training data, style preferences, and evaluation rubrics remain shared.
- Bias/correlated failure: MT-Bench reports position, verbosity, self-enhancement, and reasoning limits. More votes can amplify shared error; same-family/self-review can prefer its own style or conclusions.
- Goodhart effect: once “fresh-review pass,” residual score, or critic agreement becomes a release metric, outputs learn to satisfy judge-visible form (length, citations, schema completeness) rather than semantic adequacy.
- Falsifier/boundary: reviewer consensus counts only if blinded/order-randomized evaluation predicts held-out executable/gold outcomes and inter-reviewer errors are measured, not assumed independent.
- Safe replacement: **advisory adversarial review** — blind origins where possible, randomize order, require explicit counterexamples, and route high-risk disputed claims to executable/runtime evidence or accountable humans. One LLM’s review never supplies epistemic independence from another solely by process isolation.
- Sources: Zheng et al., [Judging LLM-as-a-Judge with MT-Bench](https://arxiv.org/abs/2306.05685); Chen et al., [Are More LLM Calls All You Need?](https://arxiv.org/abs/2403.02419) (vote/filter-vote performance can decrease as calls increase, especially on hard queries); Kenton et al., [On scalable oversight with weak LLMs judging strong LLMs](https://arxiv.org/abs/2407.04622) (debate gains are task-dependent and mixed outside extractive information asymmetry); Chen et al., [Beyond the Surface: Measuring Self-Preference](https://aclanthology.org/2025.emnlp-main.86/).

### 15. Provenance / transparency log / reproducible build -> signed evidence is trustworthy

- Category error: provenance authenticates a claimed origin/process; signature/log inclusion does not establish authorization, semantic correctness, freshness, or artifact quality.
- Counterexamples/assumptions: in-toto can validate an insecure layout and older unexpired layouts can be replayed; SLSA L3 assumes the build platform; Sigstore identity-at-time is not permission or quality; transparency logs need monitoring/gossip to detect equivocation/forks.
- Falsifier/boundary: the claim is limited to exactly what was authenticated: signer identity, digest, process/materials, log inclusion, and time. Any “therefore correct” inference requires separate evidence.
- Safe replacement: **authenticated provenance + independent content validation + freshness/authorization policy**.

### 16. Residual/readiness metrics -> lower ambiguity score means less real uncertainty

- Proxy failure: `residual = sum(weight * score)` is a workflow prioritization proxy, not calibrated uncertainty. The live docs already admit percentage dilution as settled entries accumulate (`output-template.md:200-208`).
- Goodhart paths: split one hard gap into low-weight entries; defer it (removed from residual); mark owner acceptance; underweight a missing stakeholder; add settled entries to improve percentage; craft questions that lower scores without new observations.
- Falsifier/boundary: the metric is useful if independent postmortems show monotonic prediction of implementation-changing escapes after controlling for scope/complexity. Until calibrated, it is only queue state.
- Safe replacement: **operational workflow indicator** — gate only on explicit blockers and provenance rules; report deferred/accepted risks beside residual; periodically audit score transitions against postmortem escapes. Never call it confidence or completeness.
- Sources: Manheim & Garrabrant, [Categorizing Variants of Goodhart's Law](https://arxiv.org/abs/1803.04585); Amodei et al., [Concrete Problems in AI Safety](https://arxiv.org/abs/1606.06565); DeepMind, [Specification gaming](https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/).

## Cross-cutting correlated failure modes

1. **Single semantic root:** code, tests, docs, generated spec, and reviewers all derive from one wrong stakeholder statement.
2. **Single model lineage:** “fresh” agents share weights/training/style priors; vendor diversity does not prove causal diversity.
3. **Single prompt/rubric:** all reviewers are anchored by the same Part 1, question framing, acceptance predicates, and examples.
4. **Single operator/incentive:** interviewer authors evidence, scores ambiguity, decides independence, compiles the contract, and selects reviewers.
5. **Single observability boundary:** all evidence is static while failure exists only in production, a missing stakeholder, a long time horizon, or an unmodeled interaction.
6. **Single compromised substrate:** workspace/controller can rewrite ledger, digest, decisions, tool outputs, and review prompts before external anchoring.
7. **Temporal common mode:** evidence was independent when captured but all became stale after the same material/environment change.

Safe default: count causal lineages, not artifacts, channels, calls, models, vendors, or signatures. For critical claims, deliberately seek evidence that would fail for a different reason.

## Unverifiable assumptions to keep explicit

- `independence_group` labels reflect actual causal independence rather than user/model assertion.
- repository state and tool outputs are authentic, complete, and current.
- question framing does not suppress an option or prime the respondent.
- accountable owners understand downstream runtime consequences.
- no omitted stakeholder has veto/operational knowledge.
- the real operating environment is represented by tests/probes.
- a “fresh-context” reviewer is independent enough to catch the author model's errors.
- the material-revision detector captures every change that invalidates evidence.
- the obligation generator includes every material requirement/hazard.
- score/weight/status transitions correlate with real implementation risk.

None should silently become an establishing evidence record. Where not testable, retain as residual risk with owner and revisit trigger.

## Recommended vocabulary firewall

Avoid inherited guarantee terms in user-facing/runtime claims: `proof of knowledge`, `zero knowledge`, `sound`, `complete`, `Byzantine fault tolerant`, `consensus`, `quorum proves`, `zero trust verifies`, `immutable`, `nonrepudiable`, `formally verified requirements`, `continuous verification`.

Prefer bounded terms: `substantiated claim`, `precommitted probe`, `content-addressed snapshot`, `causal-lineage triangulation`, `mechanical conformance gate`, `decidable criterion`, `bounded negative search`, `defeasible readiness argument`, `advisory independent review`, `authenticated provenance`, `event-triggered revalidation`.

## OBSERVATIONS

- The current contract has unusually good boundary language, but its strict schemas and gates make overclaiming especially tempting.
- The hardest gap is not another gate; it is verifying the semantic independence and authority of evidence lineages.
- The highest-value controls are boring and bounded: external observations, explicit authority, provenance, freshness invalidation, executable predicates, and visible residual doubt.
- The strongest empirical counterexamples are common-mode failure (Knight–Leveson), paper assurance (Nimrod), and biased model judging (MT-Bench and debate/voting studies).
- Human elicitation evidence also blocks extraction/completeness rhetoric: requirements are co-created and later reviews can surface ambiguities missed during initial elicitation. A structured interview improves observability but does not enumerate a closed requirement population.

## CLAIMS

- CLAIM: Cryptographic guarantees do not transfer to human interview transcripts without the original formal relation, extractor/challenge assumptions, adversary model, and security proof. — RISK: high — SOURCES: wisdom.weizmann.ac.il, arxiv.org, IEEE — COUNTER: searched for literal PoK/Fiat-Shamir instantiation for requirements interviews; none found — PRIMARY: Bellare–Goldreich; Canetti–Goldreich–Halevi; Goldwasser–Kalai.
- CLAIM: Reviewer/source multiplicity does not establish independence; shared specification and model lineage can create common-mode error. — RISK: high — SOURCES: virginia.edu, nasa.gov, arxiv.org — COUNTER: Knight–Leveson is one bounded experiment, so no universal failure rate asserted — PRIMARY: Knight–Leveson and follow-up fault analysis; MT-Bench/debate experiments.
- CLAIM: Formal/mechanical checks prove only properties of the encoded model/contract and cannot alone validate stakeholder intent or completeness. — RISK: high — SOURCES: lamport.azurewebsites.net, nasa.gov, sel4.systems — COUNTER: formal verification can give strong conditional guarantees, so the claim is explicitly conditional rather than anti-formal — PRIMARY: Lamport/TLC, NASA V&V, seL4 assumptions.
- CLAIM: Assurance artifacts can become compliance theater when evidence, operators, defeaters, and independent review are weak. — RISK: high — SOURCES: gov.uk, judiciary.uk, mit.edu, cmu.edu — COUNTER: Nimrod refutes artifact-presence sufficiency, not all assurance cases; safe reformulation is a living defeasible argument — PRIMARY: Haddon-Cave/Nimrod; Leveson; SEI.
- CLAIM: Ambiguity/readiness scores are gameable proxies unless calibrated against postmortem implementation escapes. — RISK: normal — SOURCES: arxiv.org, deepmind.google, live contract — COUNTER: useful as workflow prioritization even without probabilistic calibration — PRIMARY: Manheim–Garrabrant; Amodei et al.; local metric definition.

## EXPAND

- LEAD: empirically calibrate `residual`, reviewer agreement, and independence-group counts against postmortem escape rate across completed ultimateinterview sessions — WHY: converts Goodhart concern from structural warning to measured validity — ANGLE: pre-register metrics and hold out sessions.
- LEAD: threat-model the workspace/controller as a shared trust root for ledger, digest, tool output, and reviewer prompts — WHY: all provenance claims currently collapse if the substrate is compromised — ANGLE: external anchoring and mutation-authority audit.
- LEAD: define and test a causal-lineage rubric for `independence_group` — WHY: current field is typed but semantic independence remains unverifiable — ANGLE: shared source/prompt/model/operator/spec dependency graph plus adversarial relabeling tests.
- LEAD: blind and order-randomize fresh-review experiments, then compare with executable/runtime findings — WHY: directly measures LLM reviewer bias and correlated misses in this task domain — ANGLE: same-family vs cross-family vs human/runtime gold.
- DEAD END: literal cryptographic PoK/ZK/Fiat-Shamir security for natural-language requirements transcripts; required objects and proofs are absent, so only analogy-level reformulations are supportable.
