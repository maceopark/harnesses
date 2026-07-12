# Evidence authenticity and causal independence

## Current bypass, demonstrated

`ClaimEvidence` accepts an evidence record whose authenticity-bearing fields are all declarations: `channel`, `source_actor`, `provenance_mode`, `independence_group`, `freshness`, `epistemic_authority`, and `decision_authority` (`claim_evidence.py:129-143`). Collection validation checks ID uniqueness and the internal shape of declared derivation edges (`:191-237`). Eligibility then counts distinct declared `independence_group` strings on current, firsthand, establishing records (`:279-288`). There is no source locator, source digest, signed envelope, trust root, verified producer identity, or policy-derived failure domain.

Executable read-only repro:

```text
Given two records with channel=from-code, source_actor=user,
the same warrant, and self-chosen groups claimed-a / claimed-b:

accepted= True
eligible_groups= ['claimed-a', 'claimed-b']
count= 2
```

This is not merely missing cryptography. A signature over `independence_group="claimed-a"` would authenticate the declaration without proving that the producer, observation path, or causal inputs differ from `claimed-b`.

`ProbeResult` has the same structural issue: it rejects duplicate `independence_key` strings (`probe_policy.py:201-205`) and enforces producer-kind shapes, but `producer_id`, `independence_key`, and `kind` are unauthenticated declarations (`:178-182`).

## Primary-source design constraints

- An in-toto Statement binds a predicate type to subjects whose artifacts are matched by digest. This gives a suitable typed, content-bound assertion container, not truth by itself: [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md).
- SLSA verification explicitly requires envelope signature verification, subject-to-artifact digest matching, predicate type checking, and lookup of the recognized signing identity plus `builder.id` in a preconfigured root of trust. It also warns that even Build L3 assumes the build platform is trusted and does not cover compromise of that platform: [SLSA verifying artifacts v1.2](https://slsa.dev/spec/v1.2/verifying-artifacts).
- Sigstore verification binds an artifact signature to an expected certificate identity and OIDC issuer; bundles can carry certificate, transparency-log proof, and signed-time material: [Sigstore verification](https://docs.sigstore.dev/cosign/verifying/verify/), [Sigstore bundle format](https://docs.sigstore.dev/about/bundle/).
- DSSE authenticates payload bytes and payload type, while explicitly leaving key management/PKI outside its scope. Therefore an envelope requires an external identity/trust policy: [DSSE specification](https://github.com/secure-systems-lab/dsse).
- TUF threshold verification counts authorized distinct key IDs against a role threshold. TUF also permits a one-key deployment and calls it insecure. Thus threshold keys improve compromise resistance only to the extent that their custody/failure domains are actually separated: [TUF specification](https://theupdateframework.github.io/specification/).
- in-toto layouts require threshold link metadata from authorized functionaries reporting the same step results, and recommend separating metadata generation from step execution. Its spec also warns some reported environment fields can be forged and must not be used for security checks: [in-toto specification](https://github.com/in-toto/docs/blob/master/in-toto-spec.md).
- W3C PROV supplies useful entity/activity/agent and derivation/attribution relations, but is a representation model, not an authentication protocol. Use its graph vocabulary only after authenticating nodes/edges: [PROV-O Recommendation](https://www.w3.org/TR/prov-o/).
- A content-addressed identifier standardizes an algorithm plus digest, but dereference/location remains separate and the hash input must be defined by the application: [RFC 6920](https://datatracker.ietf.org/doc/html/rfc6920).

## Assurance/cost-ranked options

Rank is ascending assurance and cost. The recommended deployable target is Option 3, with Option 4 only for critical/runtime-bound evidence.

| Option | Mechanism | Assurance gained | Cost | What remains unproven |
|---|---|---|---|---|
| 1. Verified source descriptors | Require an allowlisted immutable locator, media/schema type, digest algorithm/value, observation command/query, and captured result digest. The gate fetches/reads the source itself and recomputes the digest. Compute `source_id` from normalized locator plus digest; reject caller-supplied group credit. | Stops missing-source claims, mutable-path substitution, and two labels over identical bytes. Strong for repo/docs evidence the gate can read. | Low | The captured source may itself be false; two different documents may copy the same upstream mistake; local gate compromise. |
| 2. Gate-produced observations | Do not accept an evidence record directly. Accept a recipe with bounded capability, execute it in a clean/sandboxed collector, and have the collector emit the record plus input/output digests, run ID, tool version, environment identity, and transcript digest. | Removes the model/interviewer as the authority on what code/query output said; makes observation reproducible and derivation explicit. | Low-medium for repo/docs, medium-high for runtime | Collector/control-plane compromise; semantically bad recipes; shared underlying data still correlates results. |
| 3. Authenticated attestations plus policy-derived domains (recommended) | Wrap collector output in DSSE/in-toto or a Sigstore bundle. Verify signature/cert chain, exact issuer+subject, signed time/log proof where required, statement/predicate type, subject digest, contract/ledger binding, and policy version. Ignore asserted `independence_group`; derive producer and failure-domain coordinates from a signed local trust policy keyed by verified identity. | Detects post-production tampering and identity spoofing; binds evidence to exact bytes, claim, contract revision, producer, and policy. Enables auditable domain collapse. | Medium | A trusted producer can lie or be compromised; policy can misclassify correlated producers; signature is not truth. |
| 4. Domain-separated threshold evidence | For critical claims require `k` verified attestations whose policy-derived producer paths satisfy a claim-specific separation rule. Record signed derivation inputs and a correlation graph over identity, organization/admin boundary, credential/key custody, control plane, collector/runtime, run/session/model context, tool-result inputs, and upstream evidence. Collapse attestations sharing a disallowed ancestor to one vote. | Resists one compromised key, one producer, one session/model, or one control plane when the selected domains are genuinely separate. | High | Common-mode specification/data errors, hidden shared dependencies, collusion, and bad domain policy. Threshold signatures alone do not supply this property. |
| 5. Remote/hardware-attested collectors plus append-only transparency | Bind collector measurement/workload identity and nonce to the attestation, use isolated workloads/HSM or workload identity, publish attestations/checkpoints to an append-only log, and monitor identities. | Strongest practical origin, non-equivocation, replay, and audit story for high-risk runtime evidence. | Very high; infrastructure and operations | Platform/attestation-root compromise, semantic falsehood, privacy leakage, monitor failure, correlated platform administrators. |

## Minimal authenticated evidence projection

The ledger should store a verifier projection, not accept these security decisions from the producer:

```text
EvidenceProjection {
  evidence_id
  ledger_id
  contract_digest
  statement_digest
  predicate_type
  subject: { media_type, digest_algorithm, digest_value, immutable_locator? }
  observation: { recipe_digest, result_digest, observed_at, run_nonce }
  signer: { trust_root_id, issuer, subject, key_or_cert_id }
  producer_id                 # policy lookup result
  domains: {                 # policy lookup/verified collector results
    authority, organization, credential_custody, control_plane,
    collector, runtime, session_or_run, model_context, upstream_root
  }
  parents: [statement_digest]
  policy_digest
  verification_receipt_digest
}
```

Producer-supplied equivalents may remain as diagnostic claims, but must never drive acceptance. The verifier recomputes the projection from the envelope, fetched subjects, collector receipt, and local policy.

## Local fail-closed acceptance predicates

Let `R` be a raw attestation, `P` a locally trusted policy identified by a pinned digest, `C` the current ledger/contract target, and `V(R,P)` the verifier projection.

### A. Authenticity and target binding

Accept a record only if all are true:

```text
supported_envelope(R)
and verify_signature(R.envelope, P.trust_roots)
and signer_identity(R) in P.allowed_signers_for(R.predicate_type)
and exact_issuer_subject_pair(R) in P.allowed_identity_pairs
and verify_signed_time_or_log_proof(R, P.time_policy)
and R.statement.type == "https://in-toto.io/Statement/v1"
and R.statement.predicateType in P.allowed_predicate_types
and R.predicate.ledger_id == C.ledger_id
and R.predicate.contract_digest == C.contract_digest
and R.predicate.policy_digest == sha256(canonical(P))
and R.predicate.run_nonce == C.issued_nonce
and (signer_identity(R), R.predicate.run_nonce) not in accepted_nonce_index
and sha256(canonical_statement(R.statement)) == R.statement_digest
```

Fail on an unknown signer, unknown field that affects predicate semantics, unsupported algorithm/type, absent target binding, or unverifiable signed time. Do not silently downgrade to unsigned v1 records for readiness credit.

### B. Source locator/digest binding

For every subject and every immediate derivation parent:

```text
algorithm in P.allowed_digest_algorithms
and locator_scheme in P.allowed_locator_schemes
and immutable(locator)                       # e.g. full commit/digest, not branch/latest
and media_type in P.allowed_media_types
and digest(fetch_exact(locator)) == declared_digest
and declared_digest == statement.subject.digest
```

If evidence is captured bytes rather than dereferenceable content, require the bytes in a content-addressed evidence store and recompute the digest there. URI equality never substitutes for digest equality. Human-friendly URIs are navigation aids, not policy identity.

### C. Channel/source consistency

Derive `channel` from a predicate/collector policy table. At minimum reject impossible pairs such as `from-code + source_actor=user` unless the signed predicate says the user is reporting a code observation and the evidence channel is consequently `from-user`, not `from-code`. Derive `freshness` from authenticated observation time plus policy TTL; derive `epistemic_authority` from claim kind and verifier class. Ignore producer declarations for all three.

### D. Derivation integrity

```text
all parent statement digests resolve and authenticate
and graph is acyclic
and every edge is inside the signed predicate
and every parent target/contract binding is compatible
and root_set(record) == union(root_set(parent))  # computed, never declared
and no hypothesis/unverified root can yield establishing credit
```

Unlike the current one-root-only rule, a synthesis may have multiple roots. It still earns zero new independence credit: its eligible roots are exactly the verified roots it cites. Missing parent, unsigned edge, digest mismatch, or hidden input means no readiness credit.

### E. Causal-independence and correlation

`independence_group` becomes a verifier output. First collapse records by shared disallowed dependencies:

```text
correlated(a,b,P,claim) :=
  exists dimension in P.separation_dimensions(claim)
    where V(a).domains[dimension] == V(b).domains[dimension]
  or shares_unreported_or_unverified_parent(a,b)
  or same collector result / run / session / model context where policy forbids it
```

Then compute connected components over the correlation relation. Each component is one eligible group. A critical claim passes only if:

```text
eligible_components >= P.threshold(claim)
and each component contains >= 1 authentic current firsthand observation
and every required producer kind is represented
and pairwise component separation satisfies P.required_cut(claim)
```

The separation dimensions must be claim/threat-model specific. Requiring different organizations for a user preference is nonsensical; requiring different collection runs may be sufficient for nondeterminism; a security-critical runtime fact may require different credential custody and control planes. The policy must name which common causes are allowed (normally the target artifact/claim itself) and which collapse votes.

### F. Adversarial tests that must reject

1. Same signed attestation copied twice with new record IDs/groups.
2. Same signer/key emits two different group labels.
3. Two certificates map to one OIDC identity or credential-custody domain.
4. Two agents use the same model session/tool result but claim independent runs.
5. A doc is a generated copy of code but omits the code parent.
6. A mutable branch/URL still resolves but its bytes changed.
7. Valid signature, wrong ledger ID or stale contract digest.
8. Valid signature and target, untrusted issuer/subject pair.
9. Valid signatures from threshold keys stored in the same custody/control plane when policy requires custody separation.
10. Derived synthesis with one missing/unverified parent, a cycle, or a hypothesis ancestor.
11. Producer asserts `owner`, `current`, `firsthand`, or `establishes` contrary to verifier policy.
12. Transparency inclusion proof is valid but the signed predicate/subject digest is wrong (log inclusion must not override content checks).
13. A previously accepted transcript/attestation is replayed into a new interview, ledger entry, contract revision, or challenge nonce.

## Recommended staged adoption

1. Immediately stop counting caller-provided group strings. Add source descriptor/digest fields, channel-source compatibility, exact contract binding, and verifier-derived groups. This closes the demonstrated zero-cost bypass.
2. Make local repo/docs evidence gate-produced. Store content/result digests and signed derivation parents.
3. Add DSSE/in-toto verification with a pinned local identity/failure-domain policy. A Sigstore bundle is a practical identity/time/log carrier where public or enterprise Sigstore roots are acceptable.
4. Enable domain-separated thresholds only for claims whose impact warrants them. A two-source default without a named separation policy is assurance theater.
5. Reserve remote/hardware attestation and transparency monitoring for critical runtime/production claims.

## Residual risks and explicit non-claims

- Authenticity is not correctness: a trusted signer can honestly attest a wrong observation or maliciously lie.
- Content identity is not semantic independence: different bytes can repeat the same upstream error; identical bytes can be independently fetched but do not become two epistemic sources.
- Identity is not failure-domain independence: different keys/certificates may share administrators, storage, CI, model context, or data.
- A derivation graph is only as complete as collector enforcement. User/model-authored graphs can omit common ancestors.
- Policy is a root of trust and a source of model error. Its digest/version must be bound to receipts; changes require review and re-evaluation.
- Thresholds improve resistance to modeled compromises, not unknown common modes or collusion.
- Transparency provides public detectability/non-equivocation support, not statement truth, and requires monitoring.
- Reproducibility can expose divergence but two runs sharing the same specification bug can agree.
- Availability/liveness degrades as authentic-source and separation requirements rise; the gate needs explicit `Blocked`, not a soft fallback.

## OBSERVATIONS

- The current schema has good internal graph hygiene (unique IDs, acyclic derivation, taint retention) but no externally grounded evidence origin.
- Both evidence and probe independence are set-cardinality checks over caller strings.
- Source locator/digest, signer identity, producer trust policy, collection receipts, and failure-domain coordinates are absent.
- Existing contract digests protect some internal freshness/binding surfaces but are not signatures and can be recomputed after malicious edits.

## CLAIMS

- The first required change is not “add signatures”; it is “move all acceptance-relevant classifications from the claimant to a verifier projection.”
- Source authenticity requires both content binding and producer authentication; causal independence additionally requires policy-modeled common-cause separation.
- Distinct keys, identities, channels, files, agents, or model samples are insufficient proxies for independence unless a policy maps and collapses their shared dependencies.
- Option 3 is the best assurance/cost target for normal handoff evidence; Option 4 should be risk-triggered rather than universal.

## EXPAND

- Define claim-specific `separation_dimensions` and `required_cut` policies with the correlated-quorum owner.
- Define trust-policy ownership, rotation, revocation, and historical re-evaluation with freshness/replay and policy-enforcement owners.
- Select an attestation predicate: reuse in-toto Link/SLSA ResourceDescriptor fields where possible; specify only interview-specific claim/contract/derivation fields.
- Prototype verifier receipts and a content-addressed evidence store; measure developer latency and blocked-rate effects.
- Threat-model hidden-parent omission and compromised collectors; decide which source classes require enforced network/tool isolation to claim graph completeness.
