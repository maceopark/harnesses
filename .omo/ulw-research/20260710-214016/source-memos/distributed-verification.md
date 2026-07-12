# Distributed Verification: BFT, Quorums, Threshold Trust, and Correlated Failure

Research date: 2026-07-10  
Scope: read-only research for multi-evidence requirements verification  
Method: 27 varied web searches; full-text reading of 14 primary papers/standards; counter-search; checks against CometBFT and etcd documentation.

## Executive result

Quorum numbers are the last step of a distributed-systems guarantee, not the first. A mathematical BFT quorum guarantee presupposes a fixed or otherwise rigorously governed set of authenticated voters, an explicit fault model and bound, protocol rules that correct voters obey, and network/timing assumptions. It proves agreement or consistency relative to a validity predicate. It does not prove that the agreed proposition is true.

Multi-evidence requirements verification normally lacks those premises. Multiple samples from one LLM are repeated draws from a shared conditional distribution, not independently engineered failure domains. Different models also exhibit correlated errors. Accordingly, `2 of 3` or `3 of 4` evidence agreement can be a useful workflow threshold, but it is not BFT and must not be assigned a mathematically derived error probability without empirical dependence estimates.

The safest transfer is structural:

- separate safety (never accept contradictory or insufficiently grounded requirements) from liveness (eventually reach a handoff or escalate);
- identify voters/evidence groups and their causal failure domains, not merely channels or sample count;
- require quorum intersection across decision phases;
- use primary or machine-verifiable anchors where possible;
- treat contradictions and missing independence as escalation conditions;
- use timeouts/human fallback for liveness, never weaken safety silently.

## 1. Formal results and assumptions

### 1.1 Quorum intersection arithmetic

For a universe of `n` members and two quorums of size `q`:

`|Q1 ∩ Q2| >= 2q - n`.

For crash faults, intersection need only contain a member that remembers its state. Safety requires `2q > n`; liveness requires `q <= n-f`. At the tight bound, `n = 2f+1` and `q = f+1`.

For Byzantine faults, an intersection must contain more than the maximum `f` Byzantine members, so `2q-n > f`; liveness still requires `q <= n-f`. Combining them yields `n > 3f`. At the tight integer bound, `n=3f+1`, `q=2f+1`, and two quorums intersect in at least `f+1`, hence at least one correct member. This conclusion depends on the definition of a correct member, including single-vote/locking rules.

Lamport, Shostak, and Pease prove that with oral messages no solution tolerates `f` traitors unless `n >= 3f+1`; their signed-message model changes the result because authentication changes what equivocation can accomplish. Source: [The Byzantine Generals Problem](https://lamport.azurewebsites.net/pubs/byz.pdf).

PBFT instantiates the tight Byzantine bound and explicitly assumes independent node failures. It recommends different service/OS implementations, passwords, and administrators to make that assumption more plausible. PBFT does not rely on synchrony for safety, but it does for liveness. Source: [Practical Byzantine Fault Tolerance](https://pdos.csail.mit.edu/6.824/papers/castro-practicalbft.pdf).

HotStuff fixes `n=3f+1`, uses authenticated point-to-point communication, partial synchrony, and quorum certificates of `n-f=2f+1` votes. Its same-view safety lemma also needs a correct replica not to vote twice; its liveness theorem applies after GST when a correct leader and sufficient timely communication occur. Threshold signatures compress the proof of `2f+1` votes; they do not turn one signer into `2f+1` independent epistemic judgments. Source: [HotStuff](https://arxiv.org/pdf/1803.05069).

Flexible Paxos shows that majority quorums are not inherently required in every phase. The safety requirement is cross-phase intersection: every phase-1 quorum intersects every phase-2 quorum. Intra-phase quorums may be disjoint. This is directly useful for multi-stage verification: evidence collection and final authorization need a carried witness or shared anchor; raw majorities at each stage do not suffice. Source: [Flexible Paxos](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.OPODIS.2016.25).

### 1.2 Safety and liveness are different obligations

FLP proves that every deterministic consensus protocol in its fully asynchronous model has a possible nonterminating execution even with one faulty process. It is a nontermination result, not a claim that safety is impossible. Source: [Impossibility of Distributed Consensus with One Faulty Process](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf).

Dwork, Lynch, and Stockmeyer formalize partial synchrony and the now-standard split: safety can hold regardless of message delay, while termination is required only after timing bounds eventually hold. For partially synchronous Byzantine consensus with authentication, their tight resilience is `n >= 3f+1`. Source: [Consensus in the Presence of Partial Synchrony](https://groups.csail.mit.edu/tds/papers/Lynch/jacm88.pdf).

Operational confirmation appears in CometBFT: more than two-thirds precommits and lock-change proofs protect safety under less than one-third Byzantine voting power; increasing round timeouts support eventual liveness. etcd's Raft implementation confirms the availability trade-off in the crash model: a five-member cluster tolerates two failures, while larger/even clusters do not automatically add fault tolerance and impose replication cost. Sources: [CometBFT consensus specification](https://docs.cometbft.com/v0.38/spec/consensus/consensus), [etcd FAQ](https://etcd.io/docs/v3.2/faq/).

Requirements transfer:

- **Safety:** do not finalize mutually inconsistent requirement statements, unsupported risk acceptances, or a handoff whose mandatory evidence predicate is false.
- **Liveness:** eventually finalize, explicitly abstain, or escalate to an authorized human.
- A deadline may trigger escalation or a narrower provisional scope. It must not silently lower the evidence predicate.

### 1.3 Agreement is not truth

BFT state-machine replication guarantees that correct replicas agree on an ordered execution satisfying the protocol's validity predicate. If all replicas receive the same flawed specification, use the same weak predicate, or faithfully compute the wrong domain rule, consensus can be perfectly safe and still epistemically wrong.

This is the largest category error in mapping BFT to requirements. Reviewer consensus can guarantee a consistent recorded decision only if the workflow enforces protocol rules. It cannot guarantee that the requirement matches stakeholder intent or reality. External truth needs primary observation, executable checks, formal proof, authoritative decision, or calibrated empirical validation.

## 2. Byzantine quorum-system lessons for evidence types

Malkhi and Reiter distinguish opaque data from self-verifying data. In their threshold examples:

- masking arbitrary server answers requires stronger intersections; their threshold construction requires `n > 4f` and quorum intersections of at least `2f+1`;
- dissemination of self-verifying data requires that quorum intersections not be wholly faulty; in the threshold case it exists iff `n > 3f`.

Source: [Byzantine Quorum Systems](https://malkhi.com/files/byzquorums-STOC1997.pdf).

Safe transfer: a reproducible test result, signed authoritative artifact, schema-validated output, or proof object is more like self-verifying data than an LLM summary is. Such an anchor can reduce how much judgmental replication is useful. This is an analogy, not a theorem about requirements: signatures prove provenance/integrity, tests prove only their encoded predicate, and formal proofs prove only the model/specification supplied.

## 3. Identity, Sybil resistance, and failure domains

Douceur shows that redundancy can be defeated when one entity presents multiple identities. Without a logically centralized identity authority, convincing distinct identities is generally impossible except under strong resource and coordination assumptions. Source: [The Sybil Attack](https://users.ece.cmu.edu/~adrian/731-sp04/readings/Douceur-sybil.pdf).

For an evidence workflow, `agent-1`, `agent-2`, and `agent-3` are not three voters when they are the same model, prompt, retrieved context, tool results, and orchestration policy. Even different model names may share training data, base architectures, providers, benchmark exposure, or the same upstream source. Count causal failure domains, not process IDs, samples, personas, or output channels.

Minimum independence metadata should record:

- generator/model/provider and version;
- prompt and context lineage;
- retrieval source provenance and whether sources copy one another;
- tool/runtime and data snapshot;
- evaluator identity/model and whether it saw other answers;
- shared specification or assumption roots;
- contamination paths, including one answer being passed into another reviewer.

## 4. Why multiple LLM samples are not independent evidence

There are two distinct notions of independence:

1. **Sampling independence conditional on a fixed model/prompt.** Random seeds may produce conditionally independent draws from the model's output distribution.
2. **Error independence relative to truth.** The events that two outputs are wrong need not be independent because both are driven by the same latent difficulty, model, training data, prompt framing, context, and retrieval errors.

The first does not imply the second.

Chen et al. study Vote and Filter-Vote with GPT-3.5-turbo-0125 on four objective/multiple-choice tasks. Performance can increase and then decrease as calls increase: more samples amplify the correct mode on easy queries and the wrong mode on hard queries. On an AVERITEC example, the correct answer had probability 34% and an incorrect answer 56%, so increasing votes converges toward the wrong answer. Their scope is explicitly limited to two compound designs and relatively objective tasks; subjective and open-ended transfer is unresolved. Source: [Are More LLM Calls All You Need?](https://arxiv.org/abs/2403.02419).

Kim et al. evaluate 349 models on 14,402 HuggingFace leaderboard questions, 71 models on 12,032 HELM questions, and 20 models on 1,800 resume-job pairs. Conditional on both models being wrong, mean agreement was 0.423 on HuggingFace versus a 0.127 random-answer baseline, and 0.60 on HELM versus 1/3. Shared provider and architecture increased correlation, but larger/more accurate models also remained correlated across surface differences. The multiple-choice ground truths are stronger than the subjective resume labels, which the authors explicitly qualify. Source: [Correlated Errors in Large Language Models](https://proceedings.mlr.press/v267/kim25e.html).

The older N-version software evidence is structurally consistent. Knight and Leveson tested 27 independently developed implementations on one million cases and rejected the independence model at 99% confidence for that application. They explicitly say the result may or may not generalize and does not show N-version programming never works. Source: [An Experimental Evaluation of the Assumption of Independence in Multiversion Programming](https://people.cs.rutgers.edu/~uli/cs673/papers/EvaluationMultiVersionProgramming86.pdf).

Counter-search matters: Cai, Lyu, and Vouk later observed related/correlated faults while still estimating substantial N-version reliability improvements in two avionics datasets. Therefore the correct conclusion is not "diversity never helps." It is "correlation invalidates naive independence-based confidence and must be measured." Source: [An Experimental Evaluation on Reliability Features of N-Version Programming](https://www.cse.cuhk.edu.hk/~lyu/paper_pdf/issre05_xcai.pdf).

## 5. Candidate assurance thresholds

No evidence count below is a probability guarantee. These are candidate workflow policies, to be calibrated against a labeled corpus of past decisions.

### A0 — machine-verifiable / authoritative single-source exception

Accept one direct primary observation only when the claim is fully decided by a reproducible predicate or an authorized source: e.g., a test against the exact build, a schema/type check, a signed decision by the requirement owner, or a direct runtime query with provenance and freshness. Record scope and temporal validity. A summary of the artifact does not inherit this exception.

### A1 — ordinary, reversible decision

Require:

- two corroborating observation groups;
- at least one primary/direct observation;
- distinct provenance or method, not merely different prose;
- one explicit counter-check;
- no unresolved material contradiction.

This is heuristic triangulation, not `2-of-2 BFT`.

### A2 — material handoff or costly decision

Require:

- three observation groups;
- at least two materially distinct causal failure domains;
- at least one deterministic, executable, formal, or owner-authoritative anchor;
- blind/isolated initial reviews before reconciliation;
- an explicit adversarial counter-search;
- contradiction resolution tied to evidence, not majority override.

A practical availability-oriented policy is `3-of-4 plus mandatory anchor`. It resembles the quorum size for tolerating one Byzantine member (`n=4`, `q=3`), but it earns no BFT guarantee unless all formal premises hold.

### A3 — safety-critical, irreversible, legal/security, or high-blast-radius decision

An LLM/evidence quorum is advisory only. Require the domain's authoritative gate: human accountable owner, formal proof/model check, controlled experiment, security review, legal sign-off, or live runtime validation as applicable. Fail closed or narrow scope when the gate is unavailable. Record abstention and escalation as a successful outcome.

### Why `2-of-3` is especially weak under a Byzantine analogy

Two quorums of size two in a set of three may intersect in only one member. If one member is Byzantine or a common-mode source, it can sit in both quorums and support conflicting outcomes. Thus `2-of-3` is a crash-fault majority pattern, not one-fault BFT. In epistemic workflows it is weaker still because "correct reviewer" behavior and fault independence are not enforceable in the protocol sense.

## 6. Transfer limits and anti-patterns

- **Channel diversity is not causal independence.** Web, code, and an LLM may all repeat the same upstream assertion.
- **Prompt/persona diversity is not identity diversity.** It may improve coverage but cannot be counted as independent voters without calibration.
- **Threshold signatures prove authorization, not proposition truth.** NIST describes threshold schemes as distributing compromise risk across components; the security goal remains the cryptographic operation. Source: [NISTIR 8214A](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8214A.pdf).
- **Quorum intersection alone is insufficient.** Correct-voter state/locking, authenticated identity, membership/reconfiguration, freshness, and a bounded adversary are also required.
- **A supermajority can amplify a wrong mode.** More LLM calls are harmful when the most probable answer is wrong.
- **More reviewers reduce liveness.** Require escalation and timeouts rather than all-of-N unanimity for every decision.
- **Voting cannot resolve semantic ambiguity.** If candidate reviewers answer different interpretations, first refine the proposition and validity predicate.
- **Formal consensus does not discover stakeholder intent.** It records consistent agreement on supplied inputs.
- **Correlated failures do not prove diversity is worthless.** They preclude naive multiplication of error probabilities; empirical calibration may still show benefit.

## 7. Recommended control language

Use "evidence convergence" or "triangulation threshold" for heuristic workflows. Reserve "quorum guarantee" for a defined protocol with:

1. voter membership and authenticated identity;
2. stated failure semantics and maximum fault weight;
3. quorum sets and proof of required intersection;
4. correct-voter state transition/locking rules;
5. validity predicate;
6. synchrony/fairness assumptions for liveness;
7. reconfiguration and freshness rules;
8. evidence that implementations satisfy the model.

For LLM-assisted verification, require the record to state: "Agreement count is not a probability of correctness; common-mode dependence is unmeasured unless calibration evidence is linked."

## Primary sources read in full

1. Lamport, Shostak, Pease, [The Byzantine Generals Problem](https://lamport.azurewebsites.net/pubs/byz.pdf).
2. Castro, Liskov, [Practical Byzantine Fault Tolerance](https://pdos.csail.mit.edu/6.824/papers/castro-practicalbft.pdf).
3. Fischer, Lynch, Paterson, [Impossibility of Distributed Consensus with One Faulty Process](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf).
4. Dwork, Lynch, Stockmeyer, [Consensus in the Presence of Partial Synchrony](https://groups.csail.mit.edu/tds/papers/Lynch/jacm88.pdf).
5. Yin et al., [HotStuff](https://arxiv.org/pdf/1803.05069).
6. Howard, Malkhi, Spiegelman, [Flexible Paxos](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.OPODIS.2016.25).
7. Malkhi, Reiter, [Byzantine Quorum Systems](https://malkhi.com/files/byzquorums-STOC1997.pdf).
8. Mazières, [The Stellar Consensus Protocol](https://www.stellar.org/papers/stellar-consensus-protocol.pdf).
9. Douceur, [The Sybil Attack](https://users.ece.cmu.edu/~adrian/731-sp04/readings/Douceur-sybil.pdf).
10. Knight, Leveson, [Independence in Multiversion Programming](https://people.cs.rutgers.edu/~uli/cs673/papers/EvaluationMultiVersionProgramming86.pdf).
11. NIST, [NISTIR 8214A](https://nvlpubs.nist.gov/nistpubs/ir/2020/NIST.IR.8214A.pdf).
12. Chen et al., [Are More LLM Calls All You Need?](https://arxiv.org/abs/2403.02419).
13. Kim et al., [Correlated Errors in Large Language Models](https://proceedings.mlr.press/v267/kim25e.html).
14. Cai, Lyu, Vouk, [Reliability Features of N-Version Programming](https://www.cse.cuhk.edu.hk/~lyu/paper_pdf/issre05_xcai.pdf).

## OBSERVATIONS

- The same numbers (`2/3`, `3f+1`, `2f+1`) recur only after the system model fixes membership, authentication, fault semantics, correct behavior, and timing.
- PBFT itself calls out independent-node-failure as an assumption rather than an automatic property of replication.
- HotStuff's threshold signature is a compact quorum certificate, not evidence that signer judgments are causally independent.
- Flexible Paxos makes phase relationships more important than raw majority at each phase.
- FLP/DLS justify fail-closed safety plus explicit liveness escalation, not endless waiting or silent threshold reduction.
- LLM wrong answers correlate both within repeated calls on hard queries and across nominally different models.
- Empirical software-diversity counterevidence shows that correlated failure can coexist with real reliability gains; the gain is empirical, not a consequence of an independence formula.

## CLAIMS

- **Supported:** A mathematical BFT quorum threshold cannot be transferred to multi-evidence verification without explicit identity, failure-bound, protocol-behavior, and timing assumptions.
- **Supported:** `n=3f+1, q=2f+1` ensures Byzantine quorum intersection contains a correct member only under the stated Byzantine model and correct-member protocol rules.
- **Supported:** Multiple LLM samples are not independent evidence of truth; conditional sampling independence does not imply independent error events.
- **Supported with scoped empirical evidence:** Increasing LLM vote count can reduce accuracy on objective tasks when an incorrect answer is the model's modal response.
- **Supported with scoped empirical evidence:** Different LLMs have substantial correlated wrong-answer agreement; provider/architecture diversity reduces some but not all dependence.
- **Supported:** Agreement/consensus establishes consistency relative to a predicate, not external truth or stakeholder intent.
- **Candidate policy, not theorem:** `3-of-4 plus a mandatory primary/deterministic anchor` is a reasonable A2 workflow threshold if labeled explicitly as heuristic triangulation and calibrated later.

## EXPAND

- Calibrate A1/A2 thresholds on historical ultimateinterview decisions with independently adjudicated ground truth; estimate error correlation by failure-domain tags.
- Test blind-first review versus shared-context review to quantify contamination from answer exposure.
- Define a machine-readable failure-domain/provenance schema and reject duplicate causal roots before counting evidence groups.
- Model the proposed workflow in TLA+ to check contradiction, locking, timeout, and escalation invariants; this can verify workflow safety, not semantic truth.
- Create a reconfiguration rule for model/version/source changes so stale evidence cannot silently count toward a new decision epoch.
- Investigate weighted/adversarial quorum systems only if the workflow can justify stable trust weights; otherwise weighting risks laundering subjective authority into pseudo-mathematics.
