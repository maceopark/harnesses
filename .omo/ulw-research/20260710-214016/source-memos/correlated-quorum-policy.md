# Correlated-quorum policy for interview evidence

## Executive rule

Count **independently governed failure domains**, not responses, agent names, model calls, signatures, or self-declared group labels. Agreement is evidence of consistency under the recorded conditions; it is not proof that the agreed claim is true.

This is a policy for evidence acceptance, not a claim that an interview workflow implements Byzantine consensus. BFT thresholds are conditional on a closed or Sybil-resistant participant set, a declared fault bound, authenticated messages, correct protocol behavior, and quorum intersection. An LLM review ensemble normally lacks several of those conditions and is judging claims about the world rather than replicating a deterministic state machine.

## What the distributed-systems analogy safely transfers

- Membership matters before voting. NIST's BFT survey says the relevant protocols require fixed replicas with unique, Sybil-resistant identities and a known maximum failure threshold; Douceur shows that an unknown party can manufacture multiple identities absent trusted certification or strong resource assumptions.
- Authentication is necessary but insufficient. Signatures bind a message to a key and help prevent spoofing/replay. They do not prove that two keys have different owners, administrators, upstream data, software, or incentives.
- A threshold is meaningful only relative to a failure model. PBFT's guarantee assumes no more than one third of replicas are simultaneously faulty **and** explicitly assumes independent node failures. Castro and Liskov recommend different service/OS implementations, root passwords, and administrators to make that assumption more credible.
- Intersection must include an honest domain. NIST's discussion of federated quorum systems notes that mere quorum intersection is insufficient when the intersecting replica is Byzantine.
- Safety and liveness are separate. Fail-closed handling can preserve acceptance safety while reducing progress; timeouts, missing reviewers, or unresolved dependency metadata must not be silently converted into approval.

Sources: [Lamport, Shostak, and Pease, *The Byzantine Generals Problem*](https://lamport.azurewebsites.net/pubs/the-byz-generals.pdf); [Castro and Liskov, *Practical Byzantine Fault Tolerance*](https://pdos.csail.mit.edu/6.824/papers/castro-practicalbft.pdf); [NIST IR 8460, *State Machine Replication and Consensus with Byzantine Adversaries*](https://nvlpubs.nist.gov/nistpubs/ir/2023/NIST.IR.8460.ipd.pdf); [Douceur, *The Sybil Attack*](https://www.microsoft.com/en-us/research/wp-content/uploads/2002/01/IPTPS2002.pdf).

## Empirical reasons not to equate LLM votes with independent witnesses

- Across more than 350 models, Kim et al. found substantial wrong-answer correlation: on one leaderboard, two models selected the same wrong answer about 60% of the time conditional on both being wrong. Shared provider and architecture increased correlation, but correlation remained for accurate models with different providers and architectures. Vendor/model diversity is therefore a useful risk reducer, not proof of independence. [Kim et al., ICML 2025](https://proceedings.mlr.press/v267/kim25e.html)
- Repeated inference can amplify a stable error on hard items. Vote and Filter-Vote can have inverse-U accuracy as calls increase; more calls help easy queries while making hard queries worse. [Chen et al., NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/51173cf34c5faac9796a47dc2fdd3a71-Paper-Conference.pdf)
- Shared retrieval is a common-mode input. Amiraz et al. found that hard irrelevant passages distract multiple model families and that the distracting effect is robust across models. Different generators fed the same poisoned/misleading retrieval result are not independent evidence paths. [Amiraz et al., ACL 2025](https://aclanthology.org/2025.acl-long.892/)
- Independently built implementations can still share specification-induced failures. Knight and Leveson's 27-version experiment found coincident failures substantially above an independence model; the result is specific to that experiment but defeats a blanket independence presumption. [Knight and Leveson, 1985/1986 experiment](https://www.sciencedirect.com/science/article/pii/S1474667017601009)

Counter-evidence prevents an overbroad rule. Same-model self-consistency produced large average gains on several arithmetic and commonsense benchmarks, multi-agent debate has reported gains, and tool-interactive critique has improved outputs. Therefore, correlated calls are not worthless; they are valuable for candidate generation, robustness testing, and discovering disagreement. They simply must not be represented as independent corroboration. Sources: [Wang et al., ICLR 2023](https://iclr.cc/virtual/2023/poster/11718), [Du et al., multi-agent debate](https://arxiv.org/abs/2305.14325), [Gou et al., CRITIC, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/fef126561bbf9d4467dbb8d27334b8fe-Abstract-Conference.html). Intrinsic self-correction without external feedback is not a dependable substitute: [Huang et al., ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/8b4add8b0aa8749d80a34ca5d941c355-Abstract-Conference.html).

## Correlation taxonomy

| Code | Failure domain | Examples | Default treatment |
|---|---|---|---|
| C0 | Duplicate/derivative | retries, cached output, copied rationale, paraphrase of another vote | hard-collapse to one record |
| C1 | Identity/control | same human, organization, administrator, API credential, signing authority, budget owner | hard-collapse unless separately governed authority is demonstrated |
| C2 | Orchestration/session | same agent process, shared memory, shared conversation, same scheduler/controller, later reviewer sees earlier answer | hard-collapse for independence; retain as sequential critique evidence |
| C3 | Model lineage | same checkpoint; fine-tunes of same base; same architecture/provider; likely overlapping training/alignment data | exact checkpoint hard-collapse; shared lineage/provider creates a correlation edge and cannot alone satisfy diversity |
| C4 | Instruction/anchoring | same system/developer prompt, few-shot examples, rubric, role framing, debate transcript | same prompt/context is a correlation edge; exposure to a proposed answer removes blind-review independence |
| C5 | Evidence/retrieval | same source document, citation chain, corpus/index, retriever, query, ranked passages, poisoned or stale upstream data | shared evidence path is one corroboration path, regardless of number of readers |
| C6 | Tool/verifier/runtime | same search API, parser, test harness, compiler, judge model, cloud account/control plane, cache | shared decisive tool is one verification domain; add a different mechanism for critical claims |
| C7 | Specification/oracle | same ambiguous requirement, incorrect acceptance test, benchmark label, schema, or human premise | never cured by implementation/model diversity alone; challenge the premise/oracle |
| C8 | Temporal/release | same run, snapshot, model alias, mutable endpoint, transient incident, unrecorded version | count as one temporal observation; require freshness/version evidence |
| C9 | Incentive/adjudication | same manager, success metric, reward model, approval pressure, aggregator that prefers consensus | treat as governance dependence even if technical stacks differ |

An `independence_group` string is an auditable assertion, not evidence. The gate should derive clusters from verified provenance and a dependency graph. Threshold signatures authenticate distinct keys, not distinct failure domains.

## Safe non-mathematical language

Recommended:

- “Two independently governed evidence paths agree, with the recorded dependencies below.”
- “Three responses were produced, but because they share a model, prompt, and retrieval result they count as one corroboration domain.”
- “The threshold is a workflow acceptance rule. It does not establish truth or provide a Byzantine-fault-tolerance guarantee.”
- “No unresolved common dependency is known from the disclosed provenance; independence is not proven.”
- “Disagreement prevents automatic acceptance and triggers adjudication; it does not make the minority answer correct.”
- “This claim is accepted conditionally on the listed sources, model/tool versions, and freshness window.”

Avoid:

- “Three agents independently proved/verified this” when they share a model, prompt, source, or controller.
- “2-of-3 is Byzantine safe” without an authenticated membership system, explicit fault bound, protocol invariant, and failure-domain justification.
- “Different vendors are independent.”
- “Unanimous” when abstentions, tool failures, or filtered dissent are omitted.
- “Soundness amplification” for repeated LLM checks without a defined challenge distribution and composition argument.

## Gate predicates

The policy owner must set `required_domains` prospectively by claim risk. Do not obtain a desired answer first and then choose a threshold. There is no universal safe value such as “two” or “three.”

For every evidence record `e`:

1. **AUTHENTICATED**: a registered, accountable producer identity controls the signing credential; the signature binds the exact claim, disposition, evidence/source digests, dependency manifest, run identifier, and freshness data.
2. **SYBIL_RESISTANT**: enrollment maps voting identity to a governed principal; multiple keys, agents, aliases, or processes under one principal do not multiply weight.
3. **PROVENANCE_COMPLETE**: record immutable versions/digests for model/checkpoint or provider alias, prompts/rubric, context and prior outputs, retrieval corpus/index/query/results, decisive tools, verifier, controller, time, and source artifacts. Unknown material fields are `UNKNOWN`, never “independent.”
4. **CLAIM_SCOPED**: the vote addresses the same atomic claim and acceptance criterion; broad approvals cannot be counted for narrower claims they did not test.
5. **EVIDENCE_VALID**: cited evidence is accessible, relevant, fresh enough, and actually supports the disposition. Multiple summaries of one source remain one source path.
6. **NO_DUPLICATE_OR_DERIVATION**: retries, copied outputs, and answers produced after seeing the candidate are excluded from blind corroboration.
7. **DEPENDENCY_GRAPH_BUILT**: construct edges for C0–C9. Connected records linked by a hard-collapse relation contribute at most one approval domain. Softer shared dependencies remain visible and cannot collectively fill every required domain.
8. **DOMAIN_DIVERSITY_MET**: eligible agreeing clusters meet `required_domains`, including any prospectively required diversity dimensions (for example, accountable owner, model/tool mechanism, and evidence source). Model diversity cannot substitute for source or governance diversity.
9. **EXTERNAL_ANCHOR_MET**: for claims decidable by primary records, execution, tests, or authoritative data, at least one decisive path uses that external anchor rather than LLM opinion alone. The generator and final verifier must not share the only decisive mechanism for a high-impact claim.
10. **DISSENT_RESOLVED**: every eligible contradiction is preserved and resolved at claim level by new discriminating evidence, a more authoritative mechanism, or an accountable human decision. Majority count alone is not resolution.
11. **FAULT_ASSUMPTIONS_DECLARED**: any use of “quorum,” “fault tolerant,” or a BFT-derived numeric threshold states membership, fault bound, intersection rule, authentication, and synchrony/liveness assumptions. Otherwise use “acceptance threshold.”
12. **OUTCOME_FAILS_CLOSED**: authentication/provenance failure => reject the record; unknown independence or unresolved contradiction => abstain/escalate; timeout/nonresponse => unavailable, never assent.

Compact acceptance predicate:

```text
AUTO_ACCEPT(claim) :=
  all counted records pass 1-6
  AND dependency graph is complete enough to cluster records
  AND eligible agreeing clusters >= prospectively set required_domains
  AND required governance/source/mechanism diversity is present
  AND external anchor requirement is met
  AND no eligible unresolved contradiction exists
  AND evidence is within its freshness window
```

## Disagreement handling

1. Freeze and retain the original responses, abstentions, failures, and provenance. Do not let an aggregator erase minority reports.
2. Decompose disagreement into atomic propositions: fact, interpretation, requirement, risk tolerance, or recommendation.
3. Identify whether disagreement is real or caused by differing inputs, versions, scopes, or definitions.
4. Commission a discriminating check from a fresh domain: primary-source lookup, executable test, deterministic/static verifier, independently governed reviewer, or accountable domain expert.
5. Keep the adjudicator blind to vote counts when feasible; show claims and evidence, not social popularity.
6. Record the resolution, authority, new evidence, defeated alternatives, and residual dissent. If no discriminating evidence exists, abstain or obtain an explicit risk-owner decision.

Repeated debate is allowed as exploration, but convergence after agents see one another's answers is not new independent support.

## Residual risks

- Undisclosed model ancestry, training-data overlap, provider routing, or mutable model aliases can hide correlation.
- Independent organizations can still consume the same contaminated source, benchmark, vulnerability feed, or market consensus.
- Dependency manifests can be false or incomplete; signatures preserve provenance claims but do not make them true.
- A correlation graph is conservative and imperfect: hard collapsing may reduce liveness, while missed edges inflate confidence.
- A correct external tool can be invoked incorrectly; an executable result still needs input, environment, version, and oracle validation.
- Human/domain-expert reviewers share cultural assumptions, incentives, and source ecosystems; “human in the loop” is not automatically independent.
- Majority agreement can be wrong; minority dissent can also be wrong. The workflow can improve auditability and reduce some common modes, not guarantee epistemic correctness.
- Even authentic, independent evidence may all be stale or irrelevant to the deployed context.

## OBSERVATIONS

- O1: Classical BFT results attach guarantees to explicit membership, authentication, fault-bound, voting, and timing assumptions; response count alone carries no such guarantee.
- O2: Authentication and Sybil resistance answer “who/which governed principal spoke,” while correlation analysis answers “which failures could still be shared.” Neither substitutes for the other.
- O3: Empirical LLM work demonstrates both sides: repeated/multi-agent inference can improve average accuracy, yet stable hard-item errors, provider/architecture correlation, and shared RAG distraction create common-mode failures.
- O4: Shared specification and oracle defects can correlate even genuinely separate implementers, so model/vendor diversity is only one axis.
- O5: Disagreement has more epistemic value when it routes to a discriminating external check than when it is iterated until conversational convergence.

## CLAIMS

- C1: Same-model or same-context calls may count as repeated trials for robustness/search, but not as separate independent corroboration domains.
- C2: Distinct signatures, accounts, or agent names must not increase quorum weight until they map to distinct governed principals and pass dependency clustering.
- C3: Different providers/architectures reduce some common causes but do not establish independence; critical acceptance must also diversify evidence and verification mechanisms.
- C4: A safe workflow uses “acceptance threshold” unless it can state and enforce the full quorum/fault model.
- C5: Any eligible unresolved contradiction, unknown material dependency, or missing provenance blocks automatic acceptance; it routes to adjudication or abstention.
- C6: For externally decidable claims, external primary evidence or execution should outrank additional intrinsic LLM votes.

## EXPAND

- E1: Define a machine-readable dependency-manifest schema and hard/soft edge rules for C0–C9, then test it against known same-model, shared-RAG, copied-output, and hidden-principal fixtures.
- E2: Empirically estimate within-workflow error correlation by claim type rather than assuming cross-benchmark numbers transfer; pre-register evaluation and include hard/adversarial items.
- E3: Design Sybil-resistant enrollment and credential rotation for human, service, and agent producers; test one-principal-many-keys attacks.
- E4: Specify risk tiers and prospective `required_domains`/diversity requirements with the accountable risk owner; measure safety-liveness tradeoffs and escalation load.
- E5: Add a dissent-preservation and blind-adjudication protocol with deterministic outcome states: accept, reject, abstain, escalate.
- E6: Counter-test the policy for excessive collapsing: identify cases where correlated calls add useful evidence without being falsely promoted to independent witnesses.
