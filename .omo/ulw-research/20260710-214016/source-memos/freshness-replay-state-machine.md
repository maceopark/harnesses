# Freshness, replay, rollback, mix-and-match, and authority rotation

Scope: a read-only design derivation for `ultimateinterview`. This is a **design proposition**, not a description of current executable behavior. TUF is the source pattern, not a claim that an interview ledger has TUF's cryptographic security.

Primary source baseline: TUF specification 1.0.34 at commit [`da50e092`](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md). TUF explicitly separates detection/safety from availability: an attacker can always deny service, and protection does not mean an update will complete ([lines 147-154](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L147-L154)).

## 1. Current behavior versus proposition

### Current ultimateinterview behavior (observed on disk)

- `protocol.json` has one global monotonic-within-the-session `material_revision`, reviewed-contract digest/reviewer fields, open-world records, and probe state (`references/state-files.md:34-38`).
- A material ledger/evidence/probe mutation increments `material_revision` and resets checkpoint, dry-sweep, and reviewed-contract freshness; open-world history remains but its revision binding becomes stale (`state-files.md:38`).
- The Build Contract is bound to the raw Part 1 digest and a canonical self-digesting sidecar; later Part 1 changes invalidate the gate (`state-files.md:31`; `handoff-sequence.md:102-104`).
- Session writes are journaled/atomic as a file set and recover interrupted generations (`state-files.md:28`).
- Evidence freshness is an enum (`current|stale|unknown`) supplied on each record. Only `current` establishing evidence earns causal-group credit (`state-files.md:48`; `scripts/claim_evidence.py`). There is no age policy or trusted clock binding.

### Not currently enforced

- no per-artifact version/high-water mark for `ledger.json`, `protocol.json`, `questions.json`, `transcript.md`, `handoff.md`, and `build-contract.json`;
- no external/durable head that detects replay of the **entire** session directory to an earlier internally consistent generation;
- no expiry timestamp or trusted-time policy for a session head, review, checkpoint, evidence, authority grant, or deferral;
- no snapshot manifest that binds every consumed artifact into one exact generation;
- no same-version/different-content equivocation predicate;
- no modeled authority-policy version, rotation chain, revocation epoch, or dual old/new authorization;
- no recovery rule for fast-forwarded counters after authority compromise;
- schema-v0 remains deliberately weaker, so mixed-version sessions do not have uniform assurance.

Therefore current behavior catches many **in-place stale references and partial edits**, but a copied older directory can replay a fully coherent state unless something outside the directory remembers a later head.

## 2. TUF pattern and bounded transfer

TUF uses four roles: root delegates authority; timestamp points to the latest snapshot and limits replay time; snapshot names one coherent set of target metadata; targets binds content. The snapshot exists specifically to prevent mix-and-match, while timestamp is periodically refreshed to bound replay of still-valid signed state ([role definitions, lines 295-352](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L295-L352)).

Transfer to an interview session:

| TUF role | Proposed ultimateinterview analogue | Security meaning only if... |
| --- | --- | --- |
| root | `authority-policy.json`: who may establish owner/delegate decisions, review, gate, rotate policy; thresholds/scopes | authority identities and approvals are authenticated and the bootstrap policy is trusted out of band |
| timestamp | `session-head.json`: short-lived pointer to the current snapshot version+digest | head is protected by an independent authority and a durable client remembers its version |
| snapshot | `session-snapshot.json`: exact versions+digests+lengths of all state artifacts | published atomically/immutably; consumers reject artifacts outside the manifest |
| targets | ledger/protocol/questions/transcript/handoff/sidecar, plus evidence attachments | each artifact is canonicalized and digest-checked; semantic validation still runs |

Do **not** say “TUF-secure interview.” Without cryptographic authentication, protected keys, a trusted bootstrap, durable client state, and a trusted clock, the transfer is a deterministic coherence protocol, not TUF's attacker model.

## 3. Proposed state

All versions are positive integers except initial local `0` high-water marks. All digests are over canonical bytes and name their algorithm.

```text
TrustedState = {
  session_id,
  fixed_update_start,           # captured once per validation cycle
  clock_source,
  last_seen_time,               # optional anti-clock-rollback floor
  root: {
    version, digest, expires_at,
    roles: role -> {authority_ids, threshold, scopes},
    policy_schema_version
  },
  timestamp: null | {
    version, digest, expires_at,
    snapshot: {version, digest, length}
  },
  snapshot: null | {
    version, digest, expires_at,
    entries: artifact_id -> {
      version, digest, length, media_type,
      authority_epoch, tombstone
    }
  },
  artifact_high_water: artifact_id -> version,
  generation_id,
  consumed_transition_nonces: set<nonce>,
  external_checkpoint: null | {head_version, head_digest, observed_at}
}
```

Candidate objects additionally carry `schema_version`, their claimed `version`, `expires_at`, authorization proofs/approval records, and references to children. An approval record is `{authority_id, role, scope, policy_version, payload_digest, transition_nonce, approved_at}`; duplicate authority IDs never count twice. A mutation authorization is single-use: its nonce is consumed atomically with the generation commit. Retries with the same `(generation_id, transition_nonce, payload_digest)` are idempotent; reuse for another generation/payload is rejected. This is an agent-runtime replay control, not a TUF requirement.

Policy-chosen fields, not derivable from TUF:

- TTLs by object class (`session-head`, snapshot, review, checkpoint, runtime evidence, delegated approval);
- trusted clock and permitted skew;
- authority identity/authentication mechanism and threshold;
- maximum root steps and object sizes per cycle;
- immutable/external checkpoint store, if whole-directory replay is in scope;
- which semantic changes increment which artifact version;
- tombstone retention and explicit reset/break-glass procedure.

## 4. State machine

```text
BOOTSTRAP
  -> BEGIN_CYCLE(t0)
  -> ROTATE_ROOT*                 # exactly v+1, one intermediate at a time
  -> VALIDATE_ROOT_EXPIRY
  -> FETCH_TIMESTAMP
       -> NO_UPDATE               # same version, same digest
       -> REJECT                  # rollback/equivocation/expiry/auth failure
       -> ACCEPT_TIMESTAMP
  -> FETCH_SNAPSHOT
       -> REJECT                  # reference/auth/rollback/expiry failure
       -> ACCEPT_SNAPSHOT
  -> VALIDATE_ALL_ARTIFACTS
       -> REJECT                  # any missing/mixed/tampered/semantic failure
       -> COMMIT_GENERATION
  -> READY
```

Any rejection leaves the prior `TrustedState` usable and retryable. Candidate files are staged separately; nothing becomes trusted until the generation commit succeeds. This follows TUF's requirement that a failed cycle must not make future updates unrecoverable ([lines 1295-1300](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1295-L1300)).

### Transition predicates

#### `BOOTSTRAP -> BEGIN_CYCLE`

Accept only a configured out-of-band root policy and an empty high-water state, or load an already trusted durable state. Reject a root policy discovered solely inside the untrusted/replayed session directory. Set `t0 = clock.now()` once; require `t0 >= last_seen_time - allowed_skew`, then do every expiry comparison against this fixed `t0`. TUF fixes time at cycle start to avoid mid-cycle expiry races ([lines 1301-1308](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1301-L1308)); trusting the clock itself is an additional local assumption.

#### `ROTATE_ROOT(N -> N+1)`

Accept iff all hold:

1. candidate filename/version is exactly `N+1`, never a jump or reuse;
2. candidate payload satisfies the old root's threshold for the root role;
3. the same payload satisfies the candidate root's own new threshold;
4. each counted approval has a unique authority ID and exact payload/scope binding;
5. policy schema is supported and thresholds are positive/not greater than authority-set size;
6. the number/size of intermediate roots remains under configured limits.

Persist each accepted intermediate root before requesting the next. TUF requires sequential intermediates and both predecessor and successor thresholds ([lines 1314-1357](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1314-L1357), [lines 1582-1612](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1582-L1612)). Intermediate root expiry may be ignored during traversal; the final trusted root must have `expires_at > t0` ([lines 1358-1370](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1358-L1370)).

If timestamp or snapshot authorities/scopes/thresholds changed, clear trusted timestamp and snapshot high-water state before continuing. This is TUF's recovery action for fast-forwarded child versions after those keys rotate ([lines 1371-1381](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1371-L1381)). Do **not** clear artifact history on arbitrary edits; clearing is a privileged recovery effect of a validated authority rotation.

If the old threshold is unavailable or compromised beyond threshold, normal rotation cannot establish continuity: stop and require an explicitly documented out-of-band re-bootstrap. TUF warns threshold root compromise is nearly impossible to recover from safely ([lines 302-315](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L302-L315)).

Delegated owner rotation is authorized by its parent role, names exact decision scopes, increments the containing policy/artifact version, and cannot self-expand scope.

#### `FETCH_TIMESTAMP -> NO_UPDATE | ACCEPT_TIMESTAMP | REJECT`

First validate threshold authorization under the current root and expiry `expires_at > t0`. Then:

- `candidate.version < trusted.version` => reject `TIMESTAMP_ROLLBACK`;
- `candidate.version == trusted.version && digest == trusted.digest` => `NO_UPDATE` (no downstream consumption);
- `candidate.version == trusted.version && digest != trusted.digest` => reject `TIMESTAMP_EQUIVOCATION`;
- `candidate.version > trusted.version` but `candidate.snapshot.version < trusted.timestamp.snapshot.version` => reject `SNAPSHOT_POINTER_ROLLBACK`;
- otherwise accept and persist.

TUF itself requires a strictly newer timestamp, treats equality as a normal abort, requires the snapshot pointer not to decrease, and rejects expiry ([lines 1384-1427](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1384-L1427)). The explicit equal-version/different-digest reason is a useful stronger diagnostic, not a distinct TUF guarantee.

#### `ACCEPT_TIMESTAMP -> ACCEPT_SNAPSHOT | REJECT`

Accept candidate snapshot iff:

1. length/digest equal the exact reference in the accepted timestamp;
2. authorization meets current snapshot-role threshold;
3. candidate version exactly equals timestamp's referenced version;
4. candidate `expires_at > t0`;
5. for every previously trusted artifact ID, the new snapshot contains either (a) the ID at a version `>=` its high-water mark, or (b) an explicit, authorized tombstone at a higher version;
6. no artifact version is reused with different digest/content type/authority epoch;
7. every required state artifact appears exactly once.

TUF checks timestamp-to-snapshot digest and exact version, then prevents target-metadata version decrease/disappearance and checks expiry ([lines 1429-1483](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1429-L1483)). Explicit tombstones are the proposed adaptation needed for legitimate interview artifact deletion; TUF does not supply this interview-specific rule.

#### `ACCEPT_SNAPSHOT -> VALIDATE_ALL_ARTIFACTS -> COMMIT_GENERATION`

For every non-tombstoned manifest entry:

- fetch/read only the version-addressed object named by the manifest;
- require exact length, digest, media type, and internal version;
- require its authorizing policy epoch to be current for that artifact/scope;
- run its semantic validators (`ledger`, `protocol`, transcript, contract ABI, implementation gate);
- require all cross-references to resolve **within the candidate snapshot**, never from a previously trusted or working-directory file;
- require artifact-specific TTL/freshness rules, where configured.
- require each transition authorization nonce to be unused, or an exact idempotent retry of the already committed generation.

Then commit the snapshot, artifacts, all high-water marks, `generation_id`, consumed nonces, `last_seen_time`, and external checkpoint as one durable generation. A failure before commit discards candidate state. Version/hash addressing implements the same goal as TUF consistent snapshots: readers see one self-contained generation while publishers prepare another ([lines 1630-1681](https://github.com/theupdateframework/specification/blob/da50e092557f7d5b94e827c99e5d796f2820dd63/tuf-spec.md#L1630-L1681)).

`READY` is valid only for `(session_id, root.version, timestamp.version, snapshot.version, snapshot.digest, generation_id)`. A later consumer must name or reload this tuple; “latest files in the directory” is not an authority.

## 5. Attack-to-rejection mapping

| Attack/failure | Rejection predicate | Lost guarantee if omitted |
| --- | --- | --- |
| replay/freeze of old head | timestamp version not strictly newer; or expired at fixed `t0` | attacker can keep an old but internally valid contract indefinitely |
| rollback of one artifact | manifest artifact version below durable high-water mark | older evidence/decision can replace known-newer state |
| whole-directory rollback | external checkpoint head version/digest is newer than directory head | all internal checks pass on a coherent old copy |
| mix old ledger with new protocol | artifact digest/version not equal candidate snapshot entry | gate may evaluate a combination never committed together |
| mix old handoff with new sidecar | cross-reference/source digest not equal same snapshot's handoff | reviewed result no longer describes delivered contract |
| same version, changed bytes | equal version with different digest | version loses immutability/equivocation detection |
| authority substitution | approval not valid under current root role/scope/threshold | unauthorized actor can mint “fresh” state |
| skipped rotation version | root candidate version not exactly `N+1` | client cannot verify continuous transfer of authority |
| one-sided rotation | new root lacks old or new threshold | old authority is bypassed or unusable new policy is installed |
| compromised child authority fast-forward | validated child-authority rotation does not clear affected cached high-water marks | recovered legitimate versions are rejected forever as rollback |
| clock rollback | `t0 < last_seen_time - skew` | expired state may become apparently current again |
| partial commit/crash | candidate generation visible before all files+head durable | consumers can observe mixed generations |
| artifact disappearance | prior ID absent without higher-version authorized tombstone | rollback can masquerade as deletion |
| resumed node replays an approved effect | transition nonce already consumed for another generation/payload | approval can authorize the same logical side effect more than once |

## 6. Liveness and operating costs

1. **Expiry trades freeze detection for availability.** If refresh authority, clock, or storage is unavailable at expiry, safe behavior is to stop. TUF explicitly promises detection, not successful update under attack.
2. **Trusted time is a real dependency.** Wall-clock rollback, skew, suspended machines, and offline operation need a named policy. Fixed-cycle time prevents an update racing its own expiry but does not authenticate time.
3. **Durable high-water state is required.** Restore/reimage of both session and checkpoint defeats rollback detection. An external append-only checkpoint or separately backed-up client state adds infrastructure, privacy, retention, and availability cost.
4. **Sequential rotation is deliberately slow.** Every intermediate authority policy must remain available. Losing an intermediate or the old threshold stalls normal recovery.
5. **Dual authorization can deadlock.** A departed owner or lost credential can block rotation. Break-glass is an out-of-band re-bootstrap with an explicit loss-of-continuity record, not a silent threshold bypass.
6. **Monotonic versions reject legitimate historical restore.** Rollback must be republished as a new higher-version generation or performed under a privileged reset/rotation procedure.
7. **Snapshot publication adds write amplification.** Every material change requires artifact versioning, a new manifest, a new head, canonicalization, and atomic publication. Immutable generations consume storage until retention safely deletes unreachable history.
8. **Rotation forces revalidation.** Changing timestamp/snapshot authority clears affected caches; changing delegated ownership invalidates scoped approvals and can reopen requirements/checkpoints/reviews.
9. **Thresholds cost coordination.** They improve compromise tolerance only when authorities are causally/operationally independent; duplicate identities and correlated agents must not count twice.
10. **Fail-closed parsers cost forward compatibility.** Unsupported schema/policy versions stop consumption until the validator is upgraded.
11. **Bound resource use.** Max root steps, delegation depth, object bytes, artifact count, and total generation bytes are liveness/security requirements; TUF similarly bounds downloads and root traversal.

## 7. Test matrix

Each rejection test also asserts: prior trusted generation remains byte-for-byte usable; candidate state is not partially persisted; reason code is stable.

| ID | Setup/mutation | Expected |
| --- | --- | --- |
| FR-01 | first trusted bootstrap root from configured out-of-band digest | accept |
| FR-02 | bootstrap root found only inside session directory | reject `UNTRUSTED_BOOTSTRAP` |
| FR-03 | root `N+1` approved by old and new thresholds | accept/persist, continue rotation |
| FR-04 | root jumps `N -> N+2` | reject `ROOT_VERSION_GAP` |
| FR-05 | root `N+1` lacks old threshold | reject `ROOT_OLD_THRESHOLD` |
| FR-06 | root `N+1` lacks new threshold | reject `ROOT_NEW_THRESHOLD` |
| FR-07 | duplicate signer/approver ID counted twice | reject threshold |
| FR-08 | intermediate root expired, final root current | accept chain (bounded traversal) |
| FR-09 | final root expired at fixed `t0` | reject `ROOT_EXPIRED` |
| FR-10 | timestamp authority rotates through valid root | clear trusted timestamp+snapshot, retain audit history |
| FR-11 | timestamp version lower than high-water | reject `TIMESTAMP_ROLLBACK` |
| FR-12 | timestamp same version+same digest | `NO_UPDATE`, no artifact reads |
| FR-13 | timestamp same version+different digest | reject `TIMESTAMP_EQUIVOCATION` |
| FR-14 | timestamp newer but snapshot pointer decreases | reject `SNAPSHOT_POINTER_ROLLBACK` |
| FR-15 | timestamp expires one instant before/equal `t0` | reject; equality is not fresh |
| FR-16 | timestamp valid at `t0`, expires during long validation | finish using fixed `t0`; next cycle rejects if still expired |
| FR-17 | local clock goes backward beyond allowed skew | reject `CLOCK_ROLLBACK` |
| FR-18 | snapshot bytes do not match timestamp digest/length | reject `SNAPSHOT_REFERENCE_MISMATCH` |
| FR-19 | snapshot internal version differs from timestamp reference | reject `SNAPSHOT_VERSION_MISMATCH` |
| FR-20 | one artifact's version decreases | reject `ARTIFACT_ROLLBACK` |
| FR-21 | prior artifact disappears with no tombstone | reject `ARTIFACT_DISAPPEARED` |
| FR-22 | prior artifact replaced by authorized higher-version tombstone | accept deletion |
| FR-23 | same artifact version has different digest | reject `ARTIFACT_EQUIVOCATION` |
| FR-24 | old ledger + new protocol are individually valid | reject because ledger digest/version is outside candidate snapshot |
| FR-25 | new handoff + old valid sidecar | reject same-snapshot source-digest mismatch |
| FR-26 | all artifacts match manifest but one semantic validator fails | reject generation |
| FR-27 | crash after artifact staging but before head commit | recover prior generation; staged candidate unreachable |
| FR-28 | crash after durable generation commit but before response | retry yields same trusted head idempotently |
| FR-29 | replace entire directory with old coherent copy while external checkpoint is newer | reject `WHOLE_STATE_REPLAY` |
| FR-30 | same replacement with no external/durable checkpoint | **must demonstrate undetectable replay**; records lost guarantee |
| FR-31 | approval is valid identity but wrong role/scope/payload digest | reject `AUTHORITY_SCOPE_MISMATCH` |
| FR-32 | delegated owner self-expands scope during rotation | reject; parent must authorize scope change |
| FR-33 | compromised child authority fast-forwards versions; later valid root rotates that authority | clear affected high-water state, accept recovered chain |
| FR-34 | root threshold compromised, attacker publishes self-consistent chain | normal protocol cannot prove recovery; require out-of-band re-bootstrap |
| FR-35 | unsupported policy/schema version | reject fail-closed |
| FR-36 | root chain/object/artifact count exceeds configured bound | reject resource-limit reason without corrupting trusted state |
| FR-37 | schema-v0 session presented to v1 assurance gate | reject or explicitly downgrade claim; never label equivalent |
| FR-38 | expiry TTL changes without authority-policy version increment | reject policy/reference mismatch |
| FR-39 | retry same committed generation with same nonce+payload | idempotent success/no second effect |
| FR-40 | reuse consumed nonce for different generation or payload | reject `AUTHORIZATION_REPLAY` |

Property/model tests:

- Generate arbitrary interleavings of staged writes/crashes; invariant: a reader observes either old generation or new generation, never a mixture.
- Generate monotonically increasing valid chains, then mutate one version, digest, expiry, authority, or reference; exactly the mutated predicate rejects.
- Replay every strict prefix of an accepted history against its final durable checkpoint; every prefix rejects.
- Rotate every role independently; only the affected cache/high-water state is cleared.
- Determinism: same trusted state, candidate bytes, clock value, and policy yield identical result/reason.
- Recovery: after any rejected candidate, a later valid successor from the original trusted state can still commit.

## 8. Assumptions and lost guarantees

| Assumption | If false |
| --- | --- |
| root bootstrap is authentic and not replayed | all later validation can be perfectly consistent but attacker-authorized |
| authority IDs/approvals are authenticated | thresholds are labels, not authorization |
| counted authorities are operationally independent | threshold does not tolerate the claimed number of compromises |
| canonical digest algorithm/serialization is collision resistant and unambiguous | mix-and-match/tamper binding may fail |
| trusted high-water/checkpoint survives session rollback | whole-state replay is undetectable |
| clock is sufficiently trustworthy | expiry cannot bound freeze/replay |
| publishers version every material semantic change | same-version stale semantics can pass |
| semantic validators are adequate | coherent, fresh, authorized nonsense can pass |
| consumers use only the committed snapshot tuple | a later ad hoc file read can reintroduce mix-and-match |

The state machine establishes **provenance continuity, monotonicity, bounded staleness, and generation coherence under these assumptions**. It does not establish that requirements are true, complete, safe, or correctly interpreted.

## OBSERVATIONS

1. Current `material_revision` is an effective local invalidation token but not a replay-resistant version: replaying the whole directory replays the token and every bound record together.
2. The current atomic journal is close to consistent-snapshot publication, but consumers need a single manifest/head tuple to prevent direct reads from bypassing that generation boundary.
3. Build Contract self-digests bind content but do not authenticate the producer; digest correctness and authority are separate predicates.
4. TUF rotation's surprising but important recovery rule is to clear timestamp/snapshot trusted state when those authorities rotate; otherwise an attacker can fast-forward versions and make recovered honest state look like rollback.
5. An `expires_at` field alone is security theater unless the clock source, skew, refresh owner, offline behavior, and rejection path are specified and tested.

## CLAIMS

1. **Primary-source claim:** TUF prevents rollback with durable version high-water marks, freeze with expiry checked at fixed cycle time, mix-and-match with authenticated parent references, and root rotation with sequential old+new threshold authorization.
2. **Design proposition:** ultimateinterview can transfer these as a root-policy -> session-head -> snapshot-manifest -> artifact state machine, with exact rejection predicates above.
3. **Necessary boundary:** without an external/durable head, replay of an older fully coherent session directory is not detectable by internal digests or `material_revision`.
4. **Necessary boundary:** without authenticated independent authorities, “threshold,” “rotation,” and “signature” language must be replaced by “recorded approvals” and yields workflow coherence, not cryptographic compromise tolerance.
5. **Liveness claim:** every stronger freshness property introduces a corresponding stop condition—expired head, unavailable clock/checkpoint, missing rotation intermediate, unavailable old authority, or unsupported schema.

## EXPAND

1. Decide the actual threat model: accidental stale files, malicious local rewrite, malicious agent, compromised owner, or full storage rollback. The required mechanisms differ sharply.
2. Ask the policy-enforcement lane to map each predicate to the sole mutation/consumption chokepoint; direct artifact reads are a deterministic bypass.
3. Ask the evidence-authenticity/correlated-quorum lanes to define authenticated authority IDs and independence; otherwise threshold fields overclaim.
4. Prototype an external checkpoint with a privacy-minimal tuple `(session_id, head_version, head_digest)` and test restore/replay behavior.
5. Model-check the transition system for atomicity, monotonicity, rotation recovery, and retry liveness under crash and adversarial reorder.
6. Define object-class TTLs from real freshness needs, then test clock rollback/skew/offline scenarios before adding expiry gates.
7. Compare a schema-v0 and schema-v1 fixture under the proposed manifest gate and name the assurance downgrade explicitly.
