# Supply-chain trust patterns for evidence-led requirements

Scope: bounded transfer from TUF, in-toto, SLSA, Sigstore/Rekor, and reproducible-build systems into `ultimateinterview`. Source/product files were not changed. Sources accessed 2026-07-10.

## Executive result

The strongest transferable pattern is not “sign the requirements.” It is a layered verifier:

1. **Provenance:** bind every material claim to its exact evidence object, observer, method, and contract revision.
2. **State consistency:** bind the ledger, protocol, reviewed build contract, and handoff into one digest-addressed snapshot so evidence from different revisions cannot be mixed.
3. **Freshness:** persist monotonic revisions and explicit expiry/review deadlines; compare all deadlines against one verification-start time.
4. **Authorization:** delegate narrowly by claim class or target surface; require independent approvals only for high-impact policy transitions.
5. **Transparency:** retain append-only, externally checkable revision history plus independent monitors; inclusion is not truth.
6. **Reproduction:** a fresh agent deterministically compiles the same Build Contract and reaches the same gate verdict from the same inputs; agreement is correspondence, not correctness.
7. **Recovery:** revoke compromised authority, identify a compromise window, invalidate affected attestations and derived contracts, rotate trust through both old and new authorization thresholds when possible, and rerun freshness/sweep/checkpoint/review gates.

This is an integrity and accountability overlay. It cannot establish that user statements are true, that reviewers are independent, that a requirement is desirable, or that the chosen evidence policy is sound.

## Exact source mechanisms

### TUF: versioned, expiring role metadata

- A TUF client records one fixed update-start time, then compares all expiry checks against it. This prevents a metadata item from becoming invalid merely because a long verification crosses its expiry boundary ([current TUF spec, §5.1 and §§5.3-5.6](https://theupdateframework.github.io/specification/latest/)).
- Metadata versions are persisted; a client must not replace trusted metadata with a lower version. Timestamp must advance, snapshot binds the versions/hashes of all targets metadata, and targets are checked against that snapshot. Together these address rollback, freeze, and mix-and-match attacks ([current TUF spec, §§4.2, 5.4-5.6](https://theupdateframework.github.io/specification/latest/)).
- Threshold means distinct authorized keys: one key contributes at most one signature. Root rotation from N to N+1 requires a threshold under the old root **and** a threshold under the new root, and the version must be exactly N+1. Out-of-date clients update through every intermediate root ([current TUF spec, §5.3 and §6.1](https://theupdateframework.github.io/specification/latest/)).
- Delegation is scoped to target paths and can be revoked by newly signed delegating-role metadata. It limits blast radius but does not make the delegate correct ([current TUF spec, §2.1.2](https://theupdateframework.github.io/specification/latest/)).
- Recovery includes deleting cached timestamp/snapshot metadata after those keys rotate, specifically to recover from attacker-inflated versions (fast-forward attacks) ([current TUF spec, §5.3.11](https://theupdateframework.github.io/specification/latest/)).
- The original CCS analysis shows the boundary: compromise below a role threshold is recoverable by replacement; compromise at/above the root threshold can authorize an attacker-controlled trust graph. Freeze duration is bounded by unexpired metadata from uncompromised roles ([Samuel et al., CCS 2010, pp. 7-9](https://ssl.engineering.nyu.edu/papers/samuel_tuf_ccs_2010.pdf)).

### in-toto: authorized step attestations and artifact continuity

- A signed layout names steps, authorized functionary keys, expected materials/products, and inspections. Link metadata records commands, materials, products, byproducts, and environment; hashes connect outputs of one step to inputs of another ([in-toto specification, §§3-5](https://github.com/in-toto/specification/blob/master/in-toto-spec.md)).
- Step threshold is the number of link metadata items required from functionaries that “perform the operation and report the same results”; artifact rules then compare named hashes across steps ([in-toto specification, §4.3.1](https://github.com/in-toto/specification/blob/master/in-toto-spec.md)). This is closer to independent reproduction than to multiple people merely clicking Approve.
- Layout expiration is checked, but in-toto explicitly does **not** prevent replay of an older, still-unexpired layout; it recommends TUF for secure bootstrapping ([in-toto specification, §§1.5.2, 5.2](https://github.com/in-toto/specification/blob/master/in-toto-spec.md)).
- The framework can faithfully verify an insecure layout. It does not require code review or a trusted execution host, `expected_command` is warning-only, and byproducts are opaque unless a separate inspection checks them ([in-toto specification, §§1.5.2, 4.3.1, 4.4](https://github.com/in-toto/specification/blob/master/in-toto-spec.md)).

### SLSA: provenance plus consumer expectations

- SLSA v1.2 defines provenance as verifiable information about where, when, and how an artifact was produced. A verifier checks the envelope signature, artifact subject digest, predicate type, recognized builder identity/level, then compares canonical source, build type, and external parameters against expectations ([SLSA v1.2, Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts)).
- Provenance alone is inert: SLSA says it “doesn’t do anything unless somebody inspects it.” Producer-defined expectation changes should use authenticated communication and protection against unilateral modification, such as two-party control ([SLSA v1.2, Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts)).
- Build L1 provenance may be incomplete/unsigned and is trivial to forge; L2 protects against post-build tampering; L3 hardens the build process but still assumes the build platform is trusted and does not cover a malicious platform insider ([SLSA v1.2, Build track basics](https://slsa.dev/spec/v1.2/build-track-basics), [verification limits](https://slsa.dev/spec/v1.2/verifying-artifacts)).
- SLSA currently does not require complete/verified resolved dependencies, and consumer-side verification is needed to cover registry/transit compromise. A monitor helps only if a human or automated system acts on failures ([SLSA v1.2, Verifying artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts)).

### Sigstore/Rekor: witnessed identity events, not semantic truth

- Rekor provides inclusion and append-only consistency proofs over a Merkle log. Sigstore’s own security model says a keyless signature proves successful authentication as an identity at a time; it does not prove the signer should have authenticated, should have signed, or that the artifact is good ([Sigstore threat model](https://docs.sigstore.dev/about/threat-model/)).
- Long-term trust requires monitoring. A compromised log can fork views, deny entries, or falsify time; collusion with monitors can leave replay/fork attacks undetected. Sigstore assumes multiple monitors that gossip, and uses TUF for trust-root distribution, rotation, and revocation ([Sigstore threat model](https://docs.sigstore.dev/about/threat-model/), [Sigstore security model](https://docs.sigstore.dev/about/security/)).
- Independent analyses reach the same boundary: a transparency log without gossip/cross-logging can show a targeted victim a split view; gossip or cross-logging makes equivocation detectable rather than impossible ([Chuat et al., 2015](https://arxiv.org/abs/1511.01514), [Hof and Carle, 2017](https://arxiv.org/abs/1711.07278)).

### Reproducible and collectively verified builds

- A reproducible build lets another party recreate bit-for-bit output from the same source, build instructions, and sufficiently defined environment. One same-machine repeat is insufficient; deliberate environmental variation is needed to test the claim ([Reproducible Builds project: plans](https://reproducible-builds.org/docs/plans/), [adding variance](https://reproducible-builds.org/docs/adding-build-variance/)).
- Reproducibility binds declared source to output but shared malicious inputs/toolchains can reproduce the same bad result. Diverse double-compilation addresses the specific “trusting trust” compiler case by using a second trusted compiler and comparing the resulting binary ([Wheeler, 2010](https://arxiv.org/abs/1004.5548)).
- CHAINIAC combines independent witnesses, reproducible-build verifiers, collective release-policy signatures, and a tamper-evident log. The combination matters: no one mechanism supplies all properties ([Nikitin et al., USENIX Security 2017](https://www.usenix.org/conference/usenixsecurity17/technical-sessions/presentation/nikitin)).

## Bounded adaptation matrix

| Supply-chain pattern | `ultimateinterview` adaptation | Fail-closed verifier rule | What it establishes | Boundary / counterexample |
|---|---|---|---|---|
| Content-addressed provenance (in-toto/SLSA) | Each `evidence_record` carries canonical source locator, source digest/revision, observation method, observer/agent identity, `observed_at`, and the exact ledger entry/revision it supports. Derivations retain parent observation IDs. | Reject missing or unresolvable subjects; reject a record if its digest no longer matches. Unknown provenance fields fail unless explicitly allowed by schema/policy. | Which exact evidence object and process produced a claim. | A signed false user statement remains false; a digest proves identity of bytes, not semantics or authority. |
| Snapshot consistency (TUF snapshot + in-toto artifact rules) | Generate a `session-snapshot.json` manifest binding hashes/versions of `ledger.json`, `protocol.json`, `questions.json`, transcript tail, `build-contract.json`, `handoff.md`, and material repo revision. | Handoff/gate consumes exactly one manifest; any missing, altered, or cross-revision component fails. | Prevents mix-and-match and synthesis from stale components. | Does not prove the snapshot’s contents are adequate. Snapshot creation must be separated from final verification for higher assurance. |
| Monotonic version + expiry (TUF) | Add `revision`, `supersedes`, `issued_at`, `review_by`, and `material_revision` to policy/snapshot metadata. Record one `verification_started_at`. | New revision must be exactly prior+1; reject rollback, expired review, or material changes after `reviewed_at`. Same revision with different digest is an error. | Detects rollback, freeze, and stale approval. | Wall-clock integrity is assumed. Expiry only bounds staleness; it does not discover a false claim before expiry. |
| Narrow delegation (TUF targets / in-toto sublayout) | Authority map scopes decision owners/reviewers to ledger category, domain, repo path, risk tier, and permitted action (`observe`, `settle`, `defer`, `approve-policy`). Delegation chains are explicit. | An attestation outside the signer’s scope contributes zero authority. Revocation by delegator invalidates affected descendants prospectively and triggers impact analysis. | Least-authority decisions and bounded compromise radius. | Identity is not expertise. Circular delegation and one person holding multiple roles destroy independence; depth/role-count limits are needed. |
| Distinct threshold (TUF/in-toto) | For weight-5, score-3 settlement, material scope reduction, single-source override, and Build Contract policy changes, require `k-of-n` eligible **independence groups**, not signatures or channel labels. Require matching claim/contract digest. | Count at most one approval per independence group and per human principal; approvals over different digests do not combine. Disagreement keeps the item Contested/Blocked. | Resistance to one compromised or mistaken causal lineage. | Thresholds amplify correlated error if all reviewers inherit the same transcript/model/source. Majority is not truth; owner decisions may legitimately be single-source and must be labeled as authority, not corroboration. |
| Old+new threshold policy rotation (TUF root) | Changes to evidence vocabulary, authority map, threshold policy, or gate semantics are versioned policy-root transitions signed/approved under both the previously trusted policy and the proposed policy. | Require revision N+1 and old-policy + new-policy thresholds. If the old threshold is unavailable due to compromise, enter explicit emergency recovery with out-of-band owner authorization and a new trust bootstrap; never silently self-authorize. | Continuity of trust across policy/role rotation. | If the old root threshold is compromised, in-band recovery cannot be trusted. Human workflows need a named emergency authority and audit record, not a cryptographic fiction. |
| Transparency log + monitors (Rekor) | Append canonical snapshot digest, parent digest, event type, actor, and timestamp to an append-only session log; independent monitor/reviewer stores signed checkpoints and watches for forks, missing revisions, identity misuse, and unauthorized policy changes. | Inclusion proof and append-only consistency are required for high-risk handoff; compare checkpoints from at least two independent observation groups or a cross-log. | Tamper evidence, discoverability, and after-the-fact accountability. | Logging secrets may violate privacy; store digests/redacted metadata. One operator can equivocate unless checkpoints escape its control. Inclusion means “this statement existed,” not “it was true.” |
| Reproducible compilation (reproducible builds) | Given the snapshot and reviewed Part 1, a fresh-context agent runs the canonical compiler twice and must produce byte-identical canonical `build-contract.json` plus the same deterministic gate verdict. Variation pass uses a different context/model/provider where feasible. | Canonicalize only specified nondeterminism; any unexplained diff blocks. Store both outputs and tool/version identities. | Detects hidden transcript dependence, nondeterministic synthesis, and compiler/gate drift. | Same prompt/model/tooling can share defects. Matching output can be consistently wrong; fresh implementer behavior/acceptance review remains necessary. |
| Consumer expectations (SLSA) | The gate owns an explicit expectation policy: allowed evidence channels, authority scopes, required contract fields, target repo/revision, accepted verification commands, and freshness limits. | Verify provenance first, then compare every material field to policy; reject unknown high-impact fields and unapproved expectation changes. | Converts provenance into a decision rather than an archive. | Producer-supplied expectations can bless themselves. Expectations need separate governance and consumer-side enforcement. |
| Independent inspections (in-toto) | Run deterministic schema/coverage/gate checks plus fresh-context behavioral review after compilation; record inspection commands, versions, return values, and subject digest as attestations. | Inspection failure or inspection over a different digest blocks. Opaque logs/byproducts are not evidence unless a named inspection interprets them. | Evidence that specified checks ran against the delivered contract. | A passing weak test only proves the weak test passed. The layout/policy must itself be reviewed. |

## Minimal deployable profile

Avoid importing a full PKI into a local requirements skill. The proportionate first profile is:

1. Canonical SHA-256 digests and monotonic revisions for all session artifacts.
2. One snapshot manifest binding ledger, protocol, contract, handoff, and repo/material revision.
3. Explicit `issued_at`, `reviewed_at`, `review_by`, `verification_started_at`, and `supersedes` fields.
4. Independence-group-aware thresholds only at existing high-risk readiness triggers; all other items keep current evidence/owner semantics.
5. Append-only snapshot/checkpoint log retained outside mutable session state.
6. Fresh-context reproducibility check for `build-contract.json` and gate verdict.
7. A documented recovery state machine: `trusted -> suspected -> quarantined -> revoked -> re-evaluating -> reissued`, with no path that erases the old record.

## Compromise recovery procedure

1. **Freeze consumption:** mark the current snapshot quarantined; downstream implementation must stop accepting it.
2. **Bound the window:** record `last_known_good`, first suspicious event, affected principals/agents/sources, and all derived ledger/contract nodes.
3. **Preserve evidence:** append a compromise marker; do not delete or rewrite the old log. Export checkpoints to an independent store.
4. **Rotate/revoke:** remove compromised delegation; rotate credentials/agent identity/policy root. Use old+new threshold transition if the old root remains below compromise threshold; otherwise perform a named out-of-band trust bootstrap.
5. **Invalidate derivatives:** all settlements, checkpoint credits, contracts, and handoffs causally dependent on affected observations become Contested/Blocked, even when their files are unchanged.
6. **Clear attacker-controlled freshness state:** discard cached current-snapshot pointers and any version ceilings derived from compromised roles; restore from the last independently checkpointed revision.
7. **Reobserve and reproduce:** reacquire evidence through independent groups, rerun open-world sweep and falsification checkpoint after material change, rebuild the canonical contract, and rerun deterministic plus fresh-context gates.
8. **Reissue, never overwrite:** publish a new revision referencing the revoked snapshot and recovery rationale. Consumers verify the full transition chain.

## Counter-search results

- **“A transparency log prevents tampering.”** Refuted as stated. Merkle inclusion/consistency makes tampering or equivocation detectable only when clients/monitors retain and compare checkpoints; split views remain possible without gossip/cross-logging.
- **“A signature proves the claim is trustworthy.”** Refuted. Sigstore explicitly distinguishes authentication-at-a-time from authorization, intent, and artifact goodness.
- **“Provenance is enough.”** Refuted. SLSA requires consumer expectations and an enforcement point; its strongest build level still assumes the platform itself is trusted.
- **“Threshold approval is independent corroboration.”** Refuted unless approvals come from distinct causal/administrative groups and cover the same digest. TUF counts distinct keys, while the requirements adaptation must additionally model correlated people/models/sources.
- **“Expiry prevents replay.”** Partially refuted. Expiry bounds replay duration; in-toto explicitly remains vulnerable to older, still-unexpired layouts. Monotonic persisted versions and authenticated current-state metadata are also required.
- **“Reproducible output proves correct requirements.”** Refuted. It proves correspondence/determinism under declared inputs and environment. Shared bad source, policy, prompt, compiler, or model can reproduce bad output.
- **“Revocation repairs history.”** Refuted. It changes future trust decisions. Recovery must identify a compromise interval and re-evaluate all derived artifacts; historical transparency records should remain visible.

## Source and search coverage

Primary observation group: current TUF v1.0.x spec, in-toto specification, SLSA v1.2 approved specification, Sigstore security/threat model, Reproducible Builds project documentation. Independent observation groups: CCS 2010 TUF analysis; USENIX Security 2017 CHAINIAC; Chuat et al. transparency-gossip analysis; Hof/Carle software-distribution transparency; Wheeler diverse double-compilation. Search sweep used 20+ distinct queries across official-domain restriction, exact phrases, threat/limitation counter-search, academic-paper search, current-version search, implementation/recovery terms, and reproducibility variance/independence terms.

## OBSERVATIONS

- O1: TUF’s freshness property is a compound of fixed-start-time expiry, persisted monotonic versions, and authenticated current-state binding; expiry alone is insufficient.
- O2: Root rotation is a two-policy transition: N+1 is authorized by thresholds under both N and N+1.
- O3: in-toto thresholds require multiple authorized reports and matching artifact results, but the layout itself can encode weak policy.
- O4: SLSA separates provenance authenticity from expectations and consumer-side verification.
- O5: Sigstore separates identity-at-signing-time from authorization and semantic quality; monitoring is a required part of long-term trust.
- O6: Transparency logs provide tamper evidence only when checkpoints are independently observed and compared.
- O7: Reproducibility tests source/output correspondence and process determinism, not source or requirement correctness.
- O8: Compromise recovery is causal: revoke authority, bound the compromise window, invalidate derivatives, rotate trust, and reobserve.

## CLAIMS

- C1 (supported, primary + independent): A digest-bound, monotonic, expiring snapshot is the closest safe transfer of TUF into `ultimateinterview`; a signature-only ledger is not.
- C2 (supported, primary + independent): Threshold review should count independence groups over the same canonical claim/contract digest, not raw approvals or evidence-channel labels.
- C3 (supported, primary + independent): Append-only logging is useful for accountability only when at least one checkpoint/monitor is outside the mutable session and equivocation is checked.
- C4 (supported, primary + independent): A reproducible Build Contract is a valuable hidden-context detector but must remain subordinate to behavioral review and falsification.
- C5 (supported, primary): Policy/authority rotation should require both old and new authorization thresholds; above-threshold root compromise requires an explicit out-of-band bootstrap.
- C6 (supported, primary + independent): Recovery must invalidate derived settlements/contracts according to causal provenance, not merely rotate credentials.
- C7 (bounded adaptation): The minimal deployable profile should use ordinary hashes, manifests, revisions, and reviewers; public PKI/transparency infrastructure is disproportionate unless artifacts cross organizational trust boundaries.

## EXPAND

- LEAD: Compare this matrix with the current deterministic-gates worker’s executable findings — WHY: distinguish already-enforced digest/freshness behavior from new recommendations — ANGLE: map each matrix verifier rule to existing scripts and exact missing assertions.
- LEAD: Have skeptical-mapping test independence-group thresholds against shared-model/shared-transcript correlated failure — WHY: threshold theater is the largest adaptation risk — ANGLE: construct counterexamples where 3-of-5 approvals share one poisoned source.
- LEAD: Define the emergency trust-bootstrap owner and compromise-window semantics — WHY: old+new threshold rotation cannot recover when the old root itself is above-threshold compromised — ANGLE: organizational authority and audit requirements, not cryptographic analogy.
- LEAD: Privacy review for append-only evidence logs — WHY: transcripts and evidence locators can contain secrets/PII that public transparency designs assume may be disclosed — ANGLE: digest-only entries, encrypted evidence, retention and erasure tension.
- DEAD END: Treating signatures, inclusion proofs, reproducibility, or majority approval as direct evidence of semantic truth; every primary spec explicitly or structurally stops short of that claim.
