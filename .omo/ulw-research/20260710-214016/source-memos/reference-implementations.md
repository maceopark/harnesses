# Reference implementations: provenance, freshness, delegation, and proof-carrying workflows

Research date: 2026-07-10. All repository links below are commit-pinned. Workspace product files were not modified.

## Pinned corpus

| System | Pin | Role in the comparison |
|---|---|---|
| python-tuf | [`3197848bccf84199138f844584a7349cc8f4f43c`](https://github.com/theupdateframework/python-tuf/tree/3197848bccf84199138f844584a7349cc8f4f43c) | Threshold/delegation, rollback and freeze defense, trust-root rotation |
| TUF specification | [`da50e092557f7d5b94e827c99e5d796f2820dd63`](https://github.com/theupdateframework/specification/tree/da50e092557f7d5b94e827c99e5d796f2820dd63) (spec 1.0.34) | Normative trust-transition and client-workflow semantics |
| in-toto Python | [`a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b`](https://github.com/in-toto/in-toto/tree/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b) | Signed step evidence, distinct-functionary thresholds, artifact rules, inspections |
| in-toto specification | [`117bb8e34aee9a7a6a5f6242b3e97c7c1391663a`](https://github.com/in-toto/specification/tree/117bb8e34aee9a7a6a5f6242b3e97c7c1391663a) | Normative layout/link semantics and explicit command-alignment limitation |
| Rekor | [`0a635eca86fab2b79dfe39b6fd857a3774c4ab84`](https://github.com/sigstore/rekor/tree/0a635eca86fab2b79dfe39b6fd857a3774c4ab84) | Canonical log leaves, inclusion/consistency proofs, checkpoints, SETs |
| Sigstore docs | [`c91481065c626ca6a5770fca578ef476f1159198`](https://github.com/sigstore/docs/tree/c91481065c626ca6a5770fca578ef476f1159198) | Official monitoring and security-model caveats |
| SLSA verifier | [`aaf98fd77ddc1963c0f34f34c46bd84d7a08c260`](https://github.com/slsa-framework/slsa-verifier/tree/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260) | Binding a signed statement to artifact, builder, source, and caller expectations |
| SLSA specification | [`aeefc2798b837ca03820d80d189961d2bb7bec2c`](https://github.com/slsa-framework/slsa/tree/aeefc2798b837ca03820d80d189961d2bb7bec2c) | Verification model and expectation formation |
| Witness CLI | [`713151bb3fb1bba66fdf739b296c1911fb209569`](https://github.com/in-toto/witness/tree/713151bb3fb1bba66fdf739b296c1911fb209569) | User-facing proof-carrying command workflow |
| go-witness dependency used by CLI | [`afcde8ce90904c70054bedf999fe95b962c338a5`](https://github.com/in-toto/go-witness/tree/afcde8ce90904c70054bedf999fe95b962c338a5) (`v0.12.0`) | Policy evaluation, signature/freshness checks, artifact graph continuity |

## 1. TUF: stateful trust, not merely signed files

### Call and data flow

1. `Updater.refresh()` fixes the order `root -> timestamp -> snapshot -> targets`; delegated targets load on demand. This order is part of the security protocol, not an optimization ([`updater.py:150-177`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/updater.py#L150-L177)).
2. Root rotation downloads only `N+1`; `_load_data(..., self.root)` verifies the new root under the currently trusted root, then the new root verifies itself before becoming trusted ([`trusted_metadata_set.py:166-202`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/_internal/trusted_metadata_set.py#L166-L202)). The normative spec requires unique key IDs and both old and new thresholds ([`tuf-spec.md:1335-1347`](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1335-L1347)).
3. Threshold verification iterates only role-authorized key IDs, cryptographically verifies each, and fails if the number of distinct valid authorized keys is below the role threshold ([`_payload.py:429-504`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/api/_payload.py#L429-L504)).
4. Timestamp update checks final-root expiry, timestamp version rollback, and snapshot-version rollback; an expired intermediate timestamp remains loaded solely so it still constrains rollback, but cannot authorize snapshot loading ([`trusted_metadata_set.py:204-274`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/_internal/trusted_metadata_set.py#L204-L274)).
5. Snapshot bytes are hash/length-bound by timestamp; every previously known metadata entry must remain present and nondecreasing in version; final snapshot must be unexpired and exactly the version named by timestamp ([`trusted_metadata_set.py:320-367`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/_internal/trusted_metadata_set.py#L320-L367)).
6. Targets/delegated metadata are hash/length-bound to the snapshot, version-equal, unexpired, and signature-verified by their immediate delegator ([`trusted_metadata_set.py:405-435,457-481`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/_internal/trusted_metadata_set.py#L405-L435)). Delegation traversal is ordered, cycle-bounded, and honors terminating roles ([`updater.py:520-568`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tuf/ngclient/updater.py#L520-L568)).
7. Revocation is prospective: a delegator signs fresh metadata omitting the delegation ([TUF spec `tuf-spec.md:322-336`](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L322-L336)). Old trusted state and expiry/version checks are therefore essential to prevent replay.

### Direct lessons for ultimateinterview

- Treat the active interview contract as a versioned trust state. A later handoff must not silently reduce or replace prior obligations.
- A policy/schema change should be accepted under both the previous policy and the proposed policy, analogous to TUF root rotation. This prevents a new policy from authorizing its own weakening.
- Separate roles: author, evidence producer, freshness authority, snapshot/index authority, and verifier. Multiple labels backed by one actor are not fault independence.
- Pin every accepted evidence item by digest/length/version in a signed or otherwise tamper-evident snapshot. A collection of individually plausible files does not prove they coexisted.
- Retain expired prior state for rollback comparison, while refusing to use it to approve a final handoff.

### Non-lessons

- TUF protects distribution of opaque target bytes, not the semantic truth of those bytes. A cryptographically valid handoff can still encode bad requirements.
- TUF freshness assumes a usable verifier clock and detects but cannot prevent denial of service. Interview freshness needs an explicit time/event authority and a human recovery path.
- A threshold of keys is not automatically independent judgment: correlated keys or agents can share the same failure source.

### Executed verification

`uv run --with pytest --with freezegun --with cryptography pytest -q tests/test_updater_key_rotations.py` at the pin: **2 tests and 25 subtests passed**. The case table includes old-threshold and new-threshold failures during root changes ([`test_updater_key_rotations.py:128-151`](https://github.com/theupdateframework/python-tuf/blob/3197848bccf84199138f844584a7349cc8f4f43c/tests/test_updater_key_rotations.py#L128-L151)).

## 2. in-toto: evidence graph plus independent agreement

### Call and data flow

1. `in_toto_verify` exposes the entire verifier order: owner signatures, layout expiry, substitution, link loading, link signature thresholds, recursive sublayouts, command warning, threshold artifact agreement, step rules, live inspections, inspection rules ([`verifylib.py:1484-1634`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L1484-L1634)).
2. Link filenames provide only an early availability threshold. The code explicitly says a later signature-based threshold is indispensable ([`verifylib.py:100-175`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L100-L175)).
3. Link verification rejects unauthorized or invalid/expired signers, counts multiple subkeys of one main key only once, and requires enough distinct authorized functionaries ([`verifylib.py:402-558`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L402-L558)).
4. Threshold is stronger than “N signatures”: all accepted links for a thresholded step must report equal materials and products ([`verifylib.py:1190-1277`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L1190-L1277)); the spec states multiple functionaries perform the operation and report the same result ([`in-toto-spec.md:730-760`](https://github.com/in-toto/specification/blob/117bb8e34aee9a7a6a5f6242b3e97c7c1391663a/in-toto-spec.md#L730-L760)).
5. A signed sublayout is recursively verified and collapsed to a summary link, enabling scoped delegation without exposing every internal step to the super-layout ([`verifylib.py:1326-1395`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L1326-L1395)).
6. Expiration is checked, but the verifier does not consult external creation-time, revocation, or key-usage services. Revocation requires a newly signed layout ([`verifylib.py:1513-1521`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L1513-L1521)).

### Direct lessons for ultimateinterview

- Model the handoff as a graph: each obligation names its allowed producers, evidence predicate, materials/inputs, products/outputs, and upstream edges.
- Count independent evidence only after identity verification, and deduplicate correlated identities. The useful threshold is “distinct authorized producers agreeing on normalized claim content.”
- Require agreement on the semantic payload, not merely separately signed prose. Canonicalized decision/constraint IDs and values are the analogue of equal artifact digests.
- Permit delegated sub-interviews, but require a signed/scoped summary with explicit inputs and outputs that the parent can verify.
- Run deterministic inspections after static evidence binding and before final acceptance; preserve all failed reasons for diagnosis.

### Non-lessons

- `expected_command` is deliberately warning-only because a compromised host can forge it and legitimate invocation flags vary ([spec `in-toto-spec.md:770-780`](https://github.com/in-toto/specification/blob/117bb8e34aee9a7a6a5f6242b3e97c7c1391663a/in-toto-spec.md#L770-L780); implementation [`verifylib.py:1504-1507`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/in_toto/verifylib.py#L1504-L1507)). Do not treat a recorded agent command/prompt as security evidence.
- Artifact rules are permissive unless closed with explicit disallow rules. A requirements gate must specify whether unknown fields/claims fail closed.
- in-toto attests that authorized actors reported a process/result; it does not establish that the requirement itself is correct or complete.

### Executed verification

`uv run --with pytest pytest -q tests/test_verifylib.py -k 'thresholds or threshold_constraints'` at the pin: **14 passed, 42 deselected**. Tests cover unauthorized links, invalid signatures, insufficient distinct links, disagreement, subkey non-independence, and expired keys ([`test_verifylib.py:1168-1539`](https://github.com/in-toto/in-toto/blob/a8ce9ee2125ae5a4b041a4e37cc1cf10eed0da6b/tests/test_verifylib.py#L1168-L1539)).

## 3. Sigstore/Rekor: discoverable evidence with verifiable history

### Call and data flow

1. Upload parses a typed proposed entry, checks algorithm policy, canonicalizes the entry, and only then queues the leaf in Trillian ([`pkg/api/entries.go:289-339`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/api/entries.go#L289-L339)). Duplicate leaf insertion returns conflict and the existing content-derived ID ([`entries.go:345-365`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/api/entries.go#L345-L365)).
2. `AddLeaf` waits for integration, fetches the proof, verifies the Merkle inclusion proof locally, and only then returns the integrated leaf ([`trillian_client.go:89-187,299-348`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/trillianclient/trillian_client.go#L89-L187)).
3. The server binds body, integrated time, virtual log index, and log ID into a Signed Entry Timestamp; it also returns the Merkle path and a signed checkpoint ([`entries.go:381-459`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/api/entries.go#L381-L459)).
4. Client `VerifyLogEntry` independently verifies body-to-leaf inclusion, checkpoint signature/root binding, and SET canonical payload ([`pkg/verify/verify.go:113-240`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/verify/verify.go#L113-L240)).
5. Append-only is a different proof: `ProveConsistency` compares a trusted old checkpoint to a newer checkpoint via a Merkle consistency proof; `VerifyCurrentCheckpoint` authenticates both tree heads and invokes that check ([`verify.go:38-110`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/verify/verify.go#L38-L110)).
6. Official docs say append-only consistency requires auditors/monitors ([`logging/overview.md:26-36`](https://github.com/sigstore/docs/blob/c91481065c626ca6a5770fca578ef476f1159198/content/en/logging/overview.md#L26-L36)) and explicitly warn that long-term trust requires monitoring and an operator can forge short-window timestamps more easily ([`about/security.md:32-38`](https://github.com/sigstore/docs/blob/c91481065c626ca6a5770fca578ef476f1159198/content/en/about/security.md#L32-L38)).

### Direct lessons for ultimateinterview

- Give every normalized evidence statement a content digest and append-only sequence position; return a receipt immediately after accepted integration.
- A receipt should bind content digest, actor/producer identity, integration time, sequence index, and log identity.
- Distinguish three UI states: `recorded` (signed receipt), `included` (Merkle/inventory membership), and `history-consistent` (linked to a previously trusted checkpoint). Never collapse them into one green badge.
- Persist checkpoints outside the current run and compare them on resume; otherwise a rewritten or forked ledger cannot be detected by the same party serving the ledger.
- Add independent monitors for missing expected evidence and equivocation, not merely successful entry lookup.

### Non-lessons

- An inclusion proof says an entry is in one tree; it does not prove the tree is the unique globally observed history.
- An append-only log does not retract false claims. Correction/revocation must be a new linked statement, and consumers need a resolution rule for superseded claims.
- SET integrated time is an operator assertion. It becomes stronger through checkpoint consistency, witness observation, and monitoring, not by the timestamp field alone.
- Transparency provides accountability/detectability, not confidentiality; an interview ledger may contain secrets and cannot simply be made public.

### Executed verification

`go test ./pkg/verify` at the Rekor pin: **passed** (`ok github.com/sigstore/rekor/pkg/verify 1.165s`). The exercised package contains negative cases for consistency, inclusion, checkpoint signatures, and SET verification ([`pkg/verify/verify_test.go`](https://github.com/sigstore/rekor/blob/0a635eca86fab2b79dfe39b6fd857a3774c4ab84/pkg/verify/verify_test.go)).

## 4. SLSA: provenance must be checked against expectations

### Call and data flow

1. GHA artifact verification obtains trusted Sigstore roots and verifies either an offline bundle or an online Rekor-backed signature before interpreting provenance ([`verifier.go:213-242`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/verifier.go#L213-L242)).
2. Offline bundle verification requires tlog material, verifies the tlog entry, extracts the DSSE envelope, ensures the logged signature matches the envelope, and verifies the signed attestation ([`bundle.go:222-280`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/bundle.go#L222-L280)).
3. Certificate identity checks validate the OIDC issuer first, then the reusable workflow identity and a versioned trusted ref ([`builder.go:62-97`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/builder.go#L62-L97)); the caller source repository is separately matched to the certificate extension ([`builder.go:47-60`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/builder.go#L47-L60)).
4. DSSE parsing enforces the in-toto payload type and recognized SLSA predicate types ([`slsaprovenance.go:28-58`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/slsaprovenance/slsaprovenance.go#L28-L58)). The v1 parser disallows unknown statement fields and accepts only supported builder-to-buildType mappings ([`v1.0/provenance.go:61-94`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/slsaprovenance/v1.0/provenance.go#L61-L94)).
5. After authenticity, verifier policy separately matches builder ID, canonical source URI, subject digest (minimum 256-bit), and optional branch/tag/versioned-tag/workflow inputs ([`provenance.go:183-209,355-439`](https://github.com/slsa-framework/slsa-verifier/blob/aaf98fd77ddc1963c0f34f34c46bd84d7a08c260/verifiers/internal/gha/provenance.go#L183-L209)).
6. The SLSA spec is explicit: provenance “doesn't do anything unless somebody inspects it”; verification needs builder root, signature, artifact subject, buildType, and external-parameter expectations ([`verifying-artifacts.md:24-27,39-103`](https://github.com/slsa-framework/slsa/blob/aeefc2798b837ca03820d80d189961d2bb7bec2c/spec/verifying-artifacts.md#L24-L27)). Expected builder, canonical source, buildType, and external parameters are distinct policy coordinates, with unknown parameters failing closed ([`verifying-artifacts.md:138-173`](https://github.com/slsa-framework/slsa/blob/aeefc2798b837ca03820d80d189961d2bb7bec2c/spec/verifying-artifacts.md#L138-L173)).

### Direct lessons for ultimateinterview

- Split `authentic evidence` from `evidence satisfies this handoff's expectations`. Signature success is only the first half.
- Bind a handoff to its exact subject: repository/worktree, requested change or decision set, current policy version, and evidence digest.
- Maintain an explicit expectation map: allowed producer/verifier identities, claim schema/type, source scope, external inputs, and permitted ranges.
- Reject unknown decision-critical fields by default. If a field is ignored, record the allowlisted reason.
- Prefer stable high-level contract types whose parameters are reviewable over raw “commands/prompts executed,” mirroring SLSA's abstraction guidance.

### Non-lessons

- SLSA level is a property of a build path under a stated root of trust, not a universal truth score. The spec says L3 still assumes trust in the build platform ([`verifying-artifacts.md:106-115`](https://github.com/slsa-framework/slsa/blob/aeefc2798b837ca03820d80d189961d2bb7bec2c/spec/verifying-artifacts.md#L106-L115)).
- Provenance completeness is scoped; recursive dependency verification is optional and resolved-dependency completeness is not guaranteed ([`verifying-artifacts.md:177-190`](https://github.com/slsa-framework/slsa/blob/aeefc2798b837ca03820d80d189961d2bb7bec2c/spec/verifying-artifacts.md#L177-L190)).
- A verifier's built-in trusted workflow allowlist is policy, not objective fact. ultimateinterview must expose who owns and can change its expectation map.

## 5. Witness: proof-carrying workflow, with important quorum limits

### Call and data flow

1. CLI `run` requires exactly one signer, always captures materials/products, optionally captures the command and other attestors, signs DSSE envelopes, and can store them by content identity in Archivista ([`cmd/run.go:65-199`](https://github.com/in-toto/witness/blob/713151bb3fb1bba66fdf739b296c1911fb209569/cmd/run.go#L65-L199)).
2. CLI `verify` requires policy trust input, attestation source, and at least one artifact/subject digest, then passes all of them to `witness.Verify` ([`cmd/verify.go:71-216`](https://github.com/in-toto/witness/blob/713151bb3fb1bba66fdf739b296c1911fb209569/cmd/verify.go#L71-L216)).
3. Core `Verify` authenticates the policy envelope, runs policy verification as an attestor, emits a SLSA verification summary, and fails unless its result is `PASSED` ([`verify.go:138-195`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/verify.go#L138-L195)).
4. Policy verification requires a verified source and subject digests, checks policy expiry, searches evidence by step/subject/attestation over bounded depth, traverses back-references, deduplicates repeated collections by statement plus verified signer identities, verifies artifact edges, and rejects an empty policy as vacuous ([`policy/policy.go:190-352`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/policy/policy.go#L190-L352)).
5. A step requires exact collection-name scoping, all named attestation types, every same-type attestor to pass Rego, and a nonempty attestation list ([`policy/step.go:140-213`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/policy/step.go#L140-L213)).
6. Artifact edges require at least one genuinely overlapping path and matching digest; no overlap is rejected rather than passing vacuously ([`policy/policy.go:442-544`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/policy/policy.go#L442-L544)).
7. DSSE supports configurable threshold and certificate-time/timestamp verification ([`dsse/verify.go:29-67,75-189`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/dsse/verify.go#L29-L67)). But the high-level policy path authenticates policy signatures with the default threshold of one, and a step passes if any verifier matches any allowed functionary ([`policy/policy.go:404-439`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/policy/policy.go#L404-L439)).

### Direct lessons for ultimateinterview

- Make each verification run itself produce a signed, subject-bound verification summary that names the policy and evidence it evaluated.
- A gate should reject vacuity: zero steps, a step with zero required claims, or an evidence edge with no semantic overlap must fail.
- Evidence lookup may recurse through back-references, but must be depth-bounded and content-deduplicated so replay cannot inflate coverage.
- Evaluate every evidence object of a required predicate type; do not let a later benign duplicate hide a failing earlier object.
- Preserve passed and rejected evidence with exact reasons. Fail-closed need not mean fail-opaque.

### Non-lessons

- Witness `Step.Functionaries` is allowlist/OR semantics, not N-of-M step consensus. ultimateinterview needs its own distinct-producer threshold if it claims quorum.
- DSSE threshold code increments per successful signature-verifier match and does not itself document a distinct-key deduplication rule in this path. Do not import it as a Byzantine quorum primitive without a uniqueness test and identity-independence model.
- Rego evaluation is only as sound as the predicate schema and policy author. It proves policy evaluation, not the truth of unconstrained prose.

### Executed verification

At the exact dependency commit, `go test ./dsse` passed (`ok github.com/in-toto/go-witness/dsse (cached)`). The threshold test creates five independent signer/verifier pairs and checks success at 5 and failure at 10 ([`dsse/dsse_test.go:197-243`](https://github.com/in-toto/go-witness/blob/afcde8ce90904c70054bedf999fe95b962c338a5/dsse/dsse_test.go#L197-L243)). This test does **not** establish duplicate-signer resistance.

## Cross-system control matrix

| Control | TUF | in-toto | Rekor | SLSA verifier | Witness | ultimateinterview implication |
|---|---|---|---|---|---|---|
| Subject/content binding | target hash/length | material/product digests | canonical leaf hash | statement subject = artifact digest | subject digest + artifact edges | Digest normalized decision set, evidence, and handoff |
| Producer authorization | role keys | step pubkeys | entry signature/schema | cert/OIDC builder + source | functionary keys/cert constraints | Explicit allowed producer identities per claim |
| Threshold | unique role keys | distinct functionaries + equal artifacts | none at entry level | none by default | DSSE primitive; step OR | Separate quorum control with identity deduplication |
| Delegation | scoped paths, terminating roles | recursive sublayouts | not a workflow delegation system | reusable/delegator builders | policy steps/backrefs | Scoped sub-interviews with summary proof |
| Freshness | expiry + timestamp version | layout expiry | integrated time/checkpoint | cert time + policy expectations | policy expiry + cert/timestamp | Expiry/event epoch and resume-time revalidation |
| Revocation | new signed delegator/root metadata | new signed layout | append correction; cannot delete | trust-root/expectation update | new signed policy | Prospective supersession statements; never erase history |
| Append-only/history | version/rollback state, not global log | no | inclusion + checkpoint consistency + monitor | consumes Rekor | content-addressed store, not automatically a global log | Persist checkpoints and monitor equivocation |
| Semantic verification | opaque target | artifact rules/inspections | none | caller expectations | Rego + artifact edges | Typed obligations and executable checks, human review for meaning |

## Recommended minimal mechanism for ultimateinterview

1. **Signed/versioned policy envelope**: policy ID, version, expiry/event epoch, allowed producer/verifier identities, claim schemas, quorum rules, and previous-policy digest.
2. **Canonical evidence statement**: claim ID/type, subject digest, producer identity, inputs/materials, outputs, source location, capture time, verification method, and supersedes/revokes links.
3. **Snapshot manifest**: sorted evidence digests plus expected claim inventory, signed by an evidence-index role. This prevents mix-and-match and silent omission.
4. **Verifier pipeline**: authenticate old/new policy transition; check freshness/rollback; verify producer signatures; bind every claim to subject; enforce distinct-producer thresholds and normalized agreement; execute deterministic inspections; reject unknown critical fields; emit signed summary.
5. **Transparency receipt and checkpoint**: append accepted policy/evidence/summary digests; return inclusion proof; compare the current checkpoint with a previously persisted one; make equivocation/missing-evidence monitoring a separate process.
6. **Human boundary**: show cryptographic/process status separately from semantic-review status. Never label a signed, included, or policy-passing claim “true.”

## OBSERVATIONS

- The strongest reusable pattern is not “add signatures”; it is **typed state transition + subject binding + independent expectation check + freshness/history check**.
- TUF and in-toto both preserve an order of operations. Rearranging checks can turn stale or untrusted state into an authority for later checks.
- Threshold systems explicitly deduplicate authority identities. Counting agent runs, model calls, signatures, or files without a shared-failure identity model creates false quorum.
- Append-only and revocation coexist only through supersession: retain the original claim, append its correction/revocation, and define the resolver consumers must apply.
- Every reference system has a declared non-goal. A trustworthy ultimateinterview design should expose its own proof boundary just as explicitly.

## CLAIMS

1. **A signature is necessary but insufficient.** It authenticates a producer, not relevance, freshness, completeness, semantic correctness, or agreement with caller expectations.
2. **Policy changes are security-sensitive inputs.** TUF's dual-authorized root transition is the best direct model for preventing a new interview policy from authorizing its own downgrade.
3. **Quorum requires distinct authorized identities agreeing on canonical content.** in-toto's threshold artifact equality is a stronger reference than raw multisignature count.
4. **Inclusion is not append-only proof.** A Rekor-style evidence ledger needs persisted checkpoints, consistency proofs, and independent monitoring before claiming tamper-evident history.
5. **Freshness is stateful.** Expiration alone is weaker than expiration plus monotone version/event checks against previously trusted state.
6. **Proof-carrying workflows must reject vacuity.** Empty policies, empty obligations, unconstrained fields, and edges with no semantic overlap cannot be green.
7. **ultimateinterview can prove process conformance, not requirements truth.** Semantic validity still depends on evidence quality, coverage, and accountable human judgment.

## EXPAND

- Inspect Sigstore's newer `rekor-tiles` implementation and witness/cosigning ecosystem to compare log sharding, checkpoint witness thresholds, and offline bundles with legacy Trillian Rekor.
- Build an executable adversarial fixture for duplicate DSSE signatures/verifiers in go-witness; confirm whether one identity can inflate `verified` under `VerifyWithThreshold` and upstream a regression if so.
- Compare Witness v0.12.0 policy OR semantics with any newer unreleased quorum/coverage work; do not assume the current CLI exposes the core DSSE threshold.
- Model an ultimateinterview policy transition with TUF-like old/new authorization and test downgrade, rollback, expired-intermediate, and recovery cases.
- Specify a canonical claim normalization format, then test semantic-equivalent/different claims for deterministic agreement and collision-resistant identity.
- Add a split-view experiment: serve two valid inclusion proofs from divergent evidence checkpoints and verify that only cross-run checkpoint consistency/independent witnessing detects it.
- Define correlation domains for agent reviewers (same model, prompt, context, retrieval source, toolchain, and operator) before setting any N-of-M threshold.
