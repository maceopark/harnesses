# Provenance and freshness local audit

Scope: read-only reconciliation of supply-chain specifications/reference patterns with the live local `ultimateinterview` v1 working tree and the executed deterministic-gate bypass evidence. No product/source file was changed. The proposed controls below are not current behavior.

## Bottom line

The live helpers enforce a useful **intra-session structural floor**: strict evidence-record shape, derivation graph hygiene, a self-declared `current` eligibility bit, material-revision invalidation, atomic multi-file writes, raw Part-1 and canonical BuildContract digests, exact sidecar recompilation, and digest-bound probe records. They do **not** enforce the properties that make supply-chain terminology security-bearing: authenticated producer identity, content-addressed source observations, one manifest for every consumed artifact, durable high-water state, expiry against trusted time, authority-policy rotation/revocation, transparency checkpoints, or execution receipts.

The executed bypasses are decisive:

- the same actor/warrant can declare groups `a` and `b`; observations from year 2000 declared `current` settle a weight-5 item;
- `channel=from-code` with `source_actor=user` is accepted and eligible;
- coherent ledger mutation without revision change can preserve readiness;
- a command naming a nonexistent test passes the command/head gate because it is not executed;
- a fixture without `questions.json`, `transcript.md`, or a decisions log passed the composite gate.

These results refute blanket claims of authenticated provenance, actual causal independence, trusted freshness, executed verification, full-generation coherence, or universal fail-closed delivery. They do not refute the narrower structural guarantees named above.

## Current/proposed matrix

| Surface | Current-enforced | Current-declarative | Absent | Proposed acceptance rule | Cost / overclaim boundary |
|---|---|---|---|---|---|
| Evidence record schema | Closed enums, nonblank core fields, unknown-field rejection, unique IDs (`claim_evidence.py:109-143,186-200`). | `channel`, `source_actor`, `freshness`, `warrant`, `independence_group`, and authorities are claimant assertions. | Source locator/digest, capture receipt, verifier identity, signature/trust policy. | Accept only a verifier-produced projection from fetched bytes/receipt and pinned policy; producer classifications never earn readiness credit directly. | Low for local descriptors; medium for authenticated attestations. Schema validity is not evidence authenticity. |
| Provenance lineage | Parent existence, acyclicity, root-group retention, and hypothesis taint are enforced (`claim_evidence.py:191-237`). | Parent edges and `method` originate with the claimant. | Signed edges, hidden-input detection, multi-root correlation policy. | Every parent statement digest resolves/authenticates; graph is acyclic; signed edges bind the same ledger/contract target; eligible roots are verifier-computed; missing/unsigned parent gives zero credit. | Collector enforcement needed to make graph completeness credible. A valid graph can omit a common cause. |
| Channel/source binding | Closed channel and actor vocabularies separately. | Prose says a channel names the actual source. | Any channel-to-actor compatibility table. | Derive channel from verified predicate/collector class; reject impossible pairs, including direct `from-code + user` reports. | Low. Prevents a demonstrated zero-cost bypass; does not prove source truth. |
| Causal independence | Only `current + firsthand + establishes` records count; derived evidence does not mint a new root (`claim_evidence.py:279-302`). | `independence_group`, producer ID/key, reviewer identity are strings. | Authenticated failure-domain coordinates or common-cause collapse. | Ignore asserted groups; derive domains from verified identity/receipt/policy, build correlation components, and count at most one component per policy-defined failure domain over the same subject digest. | Medium/high; false separation creates threshold theater. Distinct keys/models/channels are not automatically independent. |
| Material revision | Canonical mutations increment the session-global revision and clear dry streak, checkpoint freshness, and reviewed-contract state (`session_update.py:933-947`). Open-world records must bind the current revision (`protocol_state.py:367-386`). | Correct use of canonical writer is normative; direct file edits remain possible. | Per-artifact versions/high-water marks, same-version equivocation detection, external rollback memory. | Every material semantic change increments the affected artifact version; candidate versions cannot fall below durable high-water; same version with different digest rejects. | Low/medium. Current token catches routed mutations, not coherent directory replay or direct edits. |
| BuildContract digest | Raw Part 1 SHA-256 is compared to protocol and sidecar; sidecar is recompiled and must exactly equal the candidate (`implementation_gate.py:204-223`). Canonical self-excluding body SHA-256 is validated (`build_contract_schema.py:284-303`). | `source_ids` are textual IDs, not content digests (`build_contract_schema.py:56-66`). Reviewer is a string. | Signer, issuance time, evidence/repo digests, revocation state. | Require canonical algorithm-tagged digests for exact source bytes, Part 1, contract body, policy, and snapshot; verify subject before semantic checks. | Low. Digest proves byte identity/integrity under collision assumptions, not origin, authority, adequacy, or truth. |
| Session manifest | Atomic journaled replacement protects routed file-set crash consistency (`atomic_write.py:70-177`). | Four working files are described as the source of truth. | A manifest binding ledger, protocol, questions, transcript, handoff, sidecar, evidence attachments, and repo revision; composite gate presently omits some of these. | Gate consumes exactly one immutable manifest; every required entry appears once and matches version, length, digest, media type, internal version, authority epoch; all references resolve inside that snapshot only. | Medium write/storage amplification. Atomic writes are not a content-addressed snapshot, and missing files currently bypass the composite gate. |
| Freshness | Eligibility requires the literal enum `current`; runtime actor requires timezone-aware `observed_at` plus environment (`claim_evidence.py:137-174,279-288`). Material change invalidates selected session flags. | Freshness and runtime time are supplied by the claimant; fresh reviewer identity/context is asserted. | TTL/max age, expiry, fixed verification start, trusted clock/skew, source revision, automatic staleness, external drift/revocation. | Compute freshness from authenticated observation time/revision and source-class policy at one fixed `verification_started_at`; reject expiry equality, clock rollback beyond skew, changed material revision, stale authority epoch, or revoked/superseded source. | Medium availability/clock cost. Expiry bounds staleness; it cannot make a false claim true or detect a still-unexpired replay alone. |
| Whole-state replay | None beyond internal consistency. | Session directory is treated as current state. | Durable external head/checkpoint. | Reject when external `(session_id, head_version, head_digest)` is newer/different; commit new head and artifact high-water marks atomically. Without this state, test and document coherent replay as undetectable. | Medium infrastructure/privacy/restore cost. Internal hashes and `material_revision` replay with the directory. |
| Authority and scoped approvals | Probe authorization objects bind declared level/scope/targets/contract digest; owner/delegated records can authorize single-source acceptance. | Approver, owner, reviewer, authorization ID, and decision authority are unsigned strings; checkpoint mechanically assigns OWNER (`session_contracts.py:70-82`). | Identity provider/trust root, delegation proof, expiry, revocation, separation of duty. | Verify identity under pinned policy; exact role/scope/payload/policy-version binding; one principal/independence domain counts once; unauthorized claims contribute zero authority. | Medium/high. Authentication is not expertise or truth; automatic OWNER is an authority overclaim. |
| Policy/root rotation | None. | No live rotation contract. | Root/policy versions, sequential transition, dual authorization, authority epochs, revocation chain, break-glass record. | Candidate root is exactly `N+1`; same payload meets old-root and new-root thresholds with unique authenticated IDs; final root unexpired; persist every intermediate; changed child authority clears only affected cached child state; above-threshold old-root compromise requires named out-of-band re-bootstrap. | High coordination/liveness cost. With string approvals, call this recorded approval workflow, not cryptographic rotation. |
| Transition replay/idempotency | Atomic writer recovers crashes. | None for approvals/effects. | Single-use authorization nonce/generation binding. | `(authority, nonce)` unused, or exact retry of already committed `(generation_id, nonce, payload_digest)`; reuse for different payload/generation rejects. | Low/medium. File atomicity does not stop replaying an approved logical effect. |
| Verification execution | Gate parses command tables and checks command heads on PATH (`implementation_gate.py:438-445`). | Pass conditions and claimed review results are text. | Command execution, captured stdout/stderr/exit, environment/tool identity, receipt digest. | Execute policy-permitted checks; receipt binds command, environment, subject/contract digest, exit/output digest, time, verifier; inspection over another digest or failed check blocks. | Medium runtime/credential risk. Current gate proves command plausibility, not execution or result. |
| Reproducible compilation | Same-process recompilation must equal the sidecar. | Fresh-context reviewer and fold-back disposition are recorded as strings. | Two independent/cross-environment builds, toolchain identity, stored outputs. | From one snapshot, two bounded variation runs produce byte-identical canonical contract and identical gate verdict; unexplained difference blocks; store run receipts. | Medium/high. Agreement detects drift/nondeterminism, not semantic correctness or independent reasoning. |
| Transparency | None. | Local histories/journal exist for process/recovery. | Append-only external event log, inclusion/consistency proof, checkpoint gossip/monitoring. | For high-risk handoff, require inclusion plus consistency from a previously retained checkpoint and compare independently stored checkpoints; bind snapshot and parent digest, event, actor, time. | High privacy/operations cost. Inclusion proves occurrence, not truth; one log can equivocate without escaping checkpoints. |
| Rotation/recovery derivatives | Material local mutation reopens selected gates. | Recovery procedure exists only in research design. | Compromise window, quarantine, causal invalidation, revoked snapshot marker. | Freeze consumption; preserve old record; identify affected roots and descendants; mark derivative settlements/contracts blocked; rotate/re-bootstrap; reobserve, rebuild, regate; publish new revision that references revoked state. | High human/operational cost. Credential rotation alone does not repair derived decisions. |

## Exact acceptance predicates

The following is the minimum coherent predicate set. The first block is deployable with ordinary hashes and a protected local policy; authentication-bearing clauses require a real trust root/identity mechanism and must otherwise be labeled `recorded`, not `verified`.

### 1. Manifest and generation coherence

Accept candidate generation `G` iff:

```text
supported_schema(G.head, G.snapshot, every artifact)
and G.head.session_id == expected_session_id
and G.head.snapshot.{version,digest,length} == measure(G.snapshot)
and required_artifact_ids == keys(non_tombstoned(G.snapshot.entries))
and every required artifact appears exactly once
and for each entry e:
      bytes = read_version_addressed(e.artifact_id, e.version)
      len(bytes) == e.length
      and digest(e.algorithm, bytes) == e.digest
      and media_type(bytes) == e.media_type
      and internal_version(bytes) == e.version
      and e.version >= durable_high_water[e.artifact_id]
      and not reused_version_with_different_digest_or_type_or_epoch(e)
and every cross_reference resolves within G.snapshot
and no consumer reads an unmanifested working-directory artifact
and every artifact semantic validator passes
and external_checkpoint <= (G.head.version, G.head.digest)
```

Deletion requires an authenticated higher-version tombstone; absence is not deletion. Commit snapshot, all artifact bytes/high-water marks, generation ID, consumed nonces, and external checkpoint atomically. A failed candidate leaves the prior generation usable.

### 2. Digest/content binding

For every evidence subject, derivation parent, handoff, contract, policy, and manifest:

```text
algorithm in policy.allowed_digest_algorithms
and canonicalization is versioned and unambiguous
and locator is immutable or bytes are in a content-addressed store
and recompute(fetch_exact(locator)) == declared_digest
and declared_digest == signed_statement.subject.digest        # authenticated profile
and contract.source_part1_sha256 == sha256(extracted_raw_part1)
and contract.contract_digest == sha256(canonical(contract minus contract_digest))
```

URI equality, source ID presence, or same filename never substitutes for byte-digest equality. A passing digest claim is limited to identity/coherence.

### 3. Freshness, rollback, and replay

At cycle start capture one `t0` and use it for every expiry decision:

```text
t0 >= durable_last_seen_time - allowed_skew
and final_root.expires_at > t0
and head.expires_at > t0
and snapshot.expires_at > t0
and evidence/review/approval age_or_revision satisfies source_class_policy at t0
and candidate_head.version > trusted_head.version
and candidate_snapshot.version >= trusted_snapshot.version
and each artifact.version >= durable_high_water[artifact_id]
and candidate authority_epoch is current for artifact/scope
and source/material revision == the revision reviewed/observed
and not revoked_or_superseded(subject, producer, policy)
```

Special cases: equal head version + equal digest is `NO_UPDATE`; equal version + different digest rejects equivocation; lower version rejects rollback; a higher head pointing to a lower snapshot rejects pointer rollback. Whole-directory rollback rejects only if a durable/external checkpoint survived it. Expiry without monotonic durable state still permits replay within the validity window.

### 4. Policy/authority rotation

Accept root/policy transition `N -> N+1` iff:

```text
candidate.version == N + 1
and verify_threshold(candidate.payload, old_root.root_role)
and verify_threshold(candidate.payload, candidate_root.root_role)
and every counted approval has a unique authenticated principal/key
and every approval binds exact role, scope, policy_version, payload_digest, nonce
and thresholds are positive and <= authorized-set size
and schema/resource bounds are supported
and final candidate.expires_at > t0
```

Persist each intermediate transition. If timestamp/snapshot authority changes, clear only affected cached child state/high-water state so attacker-fast-forwarded ceilings do not brick recovery; retain audit history. If the old threshold is unavailable or compromised at/above threshold, stop normal rotation and require a named, auditable out-of-band trust bootstrap. Never silently waive the old threshold.

### 5. Provenance/authenticity and independence

Accept raw attestation `R` for current target `C` under pinned policy `P` iff:

```text
supported_envelope(R)
and verify_signature(R.envelope, P.trust_roots)
and exact_issuer_subject_pair(R) in P.allowed_identity_pairs
and signer_identity(R) in P.allowed_signers_for(R.predicate_type)
and verify_signed_time_or_log_proof(R, P.time_policy)
and statement/predicate type is explicitly allowed
and R.{ledger_id, contract_digest, policy_digest, run_nonce} == C.expected_tuple
and every subject/parent passes digest/content binding
and every signed derivation parent resolves/authenticates
and derivation graph is acyclic and target-compatible
and no unverified/hypothesis root earns establishing credit
and channel, freshness, authority, producer_id, and domains are verifier-derived
and nonce is unused or an exact idempotent retry
```

For a threshold claim, build the verifier's correlation graph over required separation dimensions (principal/key custody, organization/admin boundary, control plane, collector/runtime, run/session/model context, tool-result inputs, upstream evidence). Collapse each connected component to one vote. Accept only when the policy threshold is met by current firsthand authentic observations over the exact same claim/contract digest and required producer kinds/cuts are satisfied. A signature alone authenticates bytes/identity; it does not establish independence or truth.

## Specification and implementation reconciliation

- TUF's transferable compound is authenticated parent binding + persistent monotonic versions + fixed-start expiry + sequential old/new root authorization. Current `material_revision` and digests cover only a subset; no durable client memory, expiry, trust root, or rotation exists.
- in-toto's useful pattern is authorized step attestations plus artifact continuity and matching step results. Current source IDs and review rows do not bind observed bytes or execution results. Its warning-only expected command also cautions against treating command text as executed proof.
- SLSA requires signature, subject digest, predicate type, recognized builder, then consumer expectation checks. Current helpers have structural expectations but no authenticated producer or subject provenance.
- Sigstore/Rekor inclusion must be paired with retained checkpoint consistency/monitoring. No local transparency surface exists, and even a future inclusion proof would not establish semantic truth.
- Reproducible builds motivate a second varied compile, while current equality is a same-process deterministic recompilation. Matching bad inputs/policy can reproduce a wrong contract.
- Reference tools can expose weaker semantics than the abstract spec: an implementation's list of authorized functionaries may be alternatives (OR), not a quorum; exact implementation behavior must be tested rather than inferred from a threshold-looking configuration.

## Costs and overclaims

1. **Availability:** expiry, unavailable clocks/checkpoints, lost intermediate roots, departed owners, unsupported schemas, and required independent producers all create legitimate `Blocked` outcomes.
2. **Write/storage:** per-artifact versions, immutable generations, manifests, heads, receipts, and retained checkpoints add write amplification and retention pressure.
3. **Privacy:** evidence locators, signer identities, transcripts, runtime outputs, and transparent logs can expose secrets/PII; prefer digest-only public checkpoints and protected content stores.
4. **Operations:** trust-root custody, policy ownership, rotation, revocation, monitors, clock/skew handling, and break-glass bootstrap become ongoing responsibilities.
5. **Latency:** gate-produced observations, execution receipts, independent reviews, and multi-domain thresholds slow handoff and may require credentials or production windows.
6. **Model error:** the policy, canonicalizer, semantic validator, collector, and correlation graph become trusted code/data. A perfectly verified weak policy can bless nonsense.
7. **Safe language:** say `digest-bound`, `schema-valid`, `revision-current under local state`, `recorded approval`, or `authenticated under policy P` as applicable. Do not say `TUF-secure`, `independent`, `fresh`, `tamper-proof`, `verified execution`, `proven`, or `truthful` without the corresponding acceptance predicate and trust assumptions.

## OBSERVATIONS

1. Live v1 is strongest at local shape and causal-lineage hygiene, not external provenance. It validates the envelope but has no trustworthy issuer/observation plane.
2. BuildContract digests are real executable integrity checks, but their coverage is narrow: Part 1 and canonical sidecar, not the entire session generation or evidence corpus.
3. `material_revision` is a useful invalidation token only for mutations routed through the canonical writer. It is replayed together with a copied directory and can be bypassed by coherent direct edits.
4. The freshness enum is a claimant label, not a freshness calculation. The year-2000 bypass proves that `current` has no temporal meaning today.
5. Atomic journaling supplies crash consistency, not authenticity, immutability, snapshot selection, or rollback resistance.
6. Rotation, revocation, external checkpoints, transparency, and execution attestations are wholly proposed surfaces. None should be described as latent guarantees of the current helpers.

## CLAIMS

1. Current helpers provide digest and revision **coherence for selected locally represented state**, not supply-chain-grade provenance or freshness.
2. The minimal proportionate upgrade is source descriptors/digests + a complete session manifest + per-artifact versions/durable head + verifier-derived channel/freshness/group projections. Public PKI/transparency is not the first step.
3. Authenticated attestations are the best normal assurance/cost target only after classifications move from claimant input to verifier output; signatures over current self-declarations merely authenticate the bypass.
4. Freshness is a compound predicate: trusted observation/revision binding, expiry at fixed time, monotonic durable state, authenticated current-state pointer, and revocation. Any single field is insufficient.
5. Policy rotation requires continuity under both old and new policy; above-threshold compromise cannot be repaired by an in-band self-authorization story.
6. No integrity mechanism establishes semantic truth, specification adequacy, reviewer expertise, or user intent. Those remain independent acceptance obligations.

## EXPAND

1. Decide the local threat model before implementation: accidental stale files, malicious local edits, malicious agent, compromised authority, or full storage rollback require different profiles.
2. Prototype a privacy-minimal external checkpoint `(session_id, head_version, head_digest)` and demonstrate both detected and intentionally undetectable whole-directory replay.
3. Define the exact manifest required set and canonical bytes for transcript/evidence attachments; decide whether transcript tail or full transcript is integrity-bearing.
4. Define source-class TTL/revision policies, clock/skew/offline rules, and revocation ownership before adding an `expires_at` field.
5. Define a pinned identity/failure-domain policy and claim-specific separation dimensions; test deliberate group/key/model/control-plane correlation bypasses.
6. Make verification receipts bind executed command, outputs, environment, tool version, contract/snapshot digest, and run nonce; keep unsafe/credentialed commands policy-gated.
7. Add recovery tests for compromised child fast-forward, sequential rotation, missing old authority, causal derivative invalidation, and exact idempotent retry.
8. Preserve assurance labels by schema/profile. A legacy v0 or unsigned local profile must never inherit authenticated/rollback-resistant claims from a stronger optional profile.
