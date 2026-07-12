# Live `ultimateinterview` contract mapped to zero-trust-compatible controls

Scope: current working tree under `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview`. This is a read-only analysis. The v1 architecture is **live local working-tree state**, not the committed contract at `HEAD=32c565c`: core v1 files (`claim_evidence.py`, `open_world.py`, `probe_policy.py`, `build_contract*.py`, v1 integration tests) are untracked, and many older contract files are modified. The last committed helper implementation baseline is `3fc0d0e` (`ENG-00000: harden ultimateinterview deterministic readiness`); `32c565c` adds readiness-hardening documentation only.

Intent-node tags: I1 evidence integrity; I2 claim validity; I3 independence; I4 freshness/revocation; I5 policy enforcement; I6 executable handoff; I7 bounded human authority.

Enforcement labels:

- **SCRIPT**: represented and rejected/blocked by current helper code.
- **MIXED**: a mechanical floor exists, but semantic truth remains a human/fresh-review obligation.
- **PROSE**: normative documentation only; no matching executable check found.

## Provenance and evidence integrity (I1, I2)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Evidence-source routing and closed channels | MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:29`, `:35-36`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:32-38`, `:85-98` | Vocabulary is enforced; whether the claimed source really produced the observation is not. |
| Typed v1 ClaimEvidence record | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:48-50`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:129-183` | Records claim kind, actor, provenance mode, lineage, group, runtime time/environment, freshness, warrant, counterevidence, epistemic and decision authority. |
| Strict schema, unknown-field rejection | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:109-115`, `:186-237`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:3`, `:46-48` | Prevents malformed/extra fields and duplicate IDs; not maliciously authenticated. |
| Derived-evidence lineage | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:117-126`, `:191-237` | Parent existence, acyclicity, one root group, and hypothesis taint are enforced. |
| Evidence-channel projection | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:234-241`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_contracts.py:50-67` | Compatibility channels must exactly equal typed-record projection. |
| Assumptions/model priors cannot establish | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:150-183`, `:279-288`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/orientation.md:15-16` | Strong anti-self-certification floor. |
| Origin/surfacing attribution | SCRIPT for enum; PROSE for causal truth | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:52`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:36` | Origin is postmortem attribution, not source authenticity. |
| Part-1 source traceability | SCRIPT floor | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:52`, `:65`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:429-436`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:56-66` | Ensures source IDs exist in Part 1; does not prove full behavior survived synthesis. |
| Atomic multi-file state generation | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:7`, `:28`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/atomic_write.py:70-118`, `:134-177` | Crash consistency and root-path containment; no signature/MAC/append-only tamper evidence. |

Gaps:

1. ClaimEvidence has no required source locator (file:line, URL, command, artifact path), source-content digest, repository revision, capture ID, or verifier. `warrant` and `counterevidence` are nonblank/free-text (`claim_evidence.py:129-143`). A syntactically valid record is not reproducible evidence.
2. No channel↔source-actor compatibility rule was found. For example, a caller can declare `channel=from-code` with a semantically inconsistent actor; strict enums do not establish truthful coupling.
3. `counterevidence` is deduplicated (`claim_evidence.py:145-148`) but has no typed references and no automatic effect on status, freshness, authority, or readiness. The prose collision rule (`SKILL.md:79`) remains the operative semantic control.
4. State files and journals are locally editable JSON/Markdown. Atomicity protects against interrupted writes, not malicious or accidental post-write tampering. Only the compiled BuildContract has canonical digests.

## Causal independence and triangulation (I3)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Causal groups, not channel count | SCRIPT in v1 | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:35`, `:80`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:279-302` | Only current, firsthand, non-assumption, `establishes` records earn credit. |
| Derived records retain root group | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:205-227` | Prevents restatement from minting independence. |
| Weight-5 settlement threshold | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/ambiguity_ledger.py:328-373`, `:509-538`, `:627-650` | Two eligible groups, or one owner/delegated decision-authority override. |
| Pressure gate for risky user settlements | SCRIPT floor | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:76`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:32`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_update.py:488-515` | Token proves the step was declared, not the quality of pressure. |
| Stable checkpoint group | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:86`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_contracts.py:70-82` | Repeats do not mint new groups; however, the user is automatically labeled OWNER. |
| Probe producer shapes | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/probe_policy.py:178-225`, `:246-267` | L0-L3 require specific producer-kind sets and unique declared independence keys. |
| Fresh reviewer context isolation | PROSE/MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:28-40`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:40-41` | Gate records reviewer name/digest but cannot prove fresh context, cross-vendor model, or independence. |

Gaps:

1. `independence_group` and probe `independence_key` are caller-supplied strings. The code validates equality/uniqueness and lineage shape, not causal non-correlation, common-source dependence, model identity, shared prompt, shared training data, or shared runtime.
2. Fresh-context reviewer identity is a string and self-audit is generally accepted. The self-referential-subagent rule is prose-only; the gate cannot identify the subject or reject same-agent review.
3. `critic` model override is a routing convention, not attested model separation. No verifier records model/provider/version/context digest.

## Freshness, invalidation, and revocation (I4)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Evidence freshness enum and eligibility | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:67-70`, `:137-143`, `:279-288` | Only explicitly `current` evidence establishes. |
| Runtime observation metadata | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/claim_evidence.py:170-175` | Runtime actor requires timezone-aware time and environment. |
| Material-revision invalidation | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:36-38`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_update.py:933-947` | Ledger/probe material changes reset dry streak, checkpoint freshness, and contract review. |
| Open-world revision binding | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/open_world.py:88-124`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/protocol_state.py:367-386` | Orientation and breadth records must match current material revision. |
| Question queue invalidation | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:38`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_update.py:1094-1107` | Ledger mutation clears stale scored questions unless replaced. |
| Part-1 and sidecar digests | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:31`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:204-223`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:284-303` | Later Part-1 edit or sidecar mismatch blocks. |
| Probe target/digest binding | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/probe_policy.py:103-175`, `:246-267` | Decision/result/authorization bind to contract digest and targets. |

Gaps:

1. Evidence freshness is self-declared. There is no TTL/max age, source-specific freshness policy, automatic transition from current→stale, or revocation record.
2. External drift is invisible until someone writes a ledger material change. A repository commit, document update, runtime deployment, policy change, or stakeholder revocation does not automatically invalidate evidence.
3. `observed_at` is mandatory only for `source_actor=runtime`; code/docs/research observations have no observation time or source revision requirement.
4. BuildContract digests prove internal byte consistency, not signer identity, publication time, source authenticity, or revocation status.

## Fail-closed policy gates (I5)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| One typed canonical writer | SCRIPT/MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:5-7`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_update.py:820-889`, `:977-1014` | Writer validates and journals; hand editing is discouraged, not access-controlled. |
| Protocol blocker set | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/protocol_state.py:361-439` | Blocks missing intake/framing, stale/missing open-world passes, sweep/probe/checkpoint obligations, unresolved lenses/artifact enums, untested contract. |
| Ledger blocker set | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/ambiguity_ledger.py:500-563`, `:566-607`, `:627-650` | Blocks score 2/3, unevidenced v1 settlements, weight-5 independence failure, Blocked/Contested, ownerless deferral. |
| Composite implementation gate | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:69-104`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:170-235`, `:237-368`, `:370-446` | `implementation_ready` only if all collected failures are empty. |
| Lens artifact enum | SCRIPT floor | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/lenses.md:5-22`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/protocol_state.py:419-430` | Artifact type/presence enforced; internal fields reviewer-only. |
| Traceability/predicate/command composition | SCRIPT floor | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:50-53`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:429-445` | IDs, textual predicate findings, parsing and PATH heads block. |
| Budget and due-now routing | SCRIPT/MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/protocol_state.py:243-253`, `:330-358`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:37-38`, `:64` | Script emits obligation; it cannot force the agent to call/obey `--next`. |

Gaps:

1. This is policy-as-data in the same local trust domain, not a separate policy decision/enforcement plane. `session_update.py` is PEP-like only for writes routed through it; `session_status.py --next` is advisory, and `--gate` blocks only when invoked. The interviewer can edit state, author evidence, name reviewer, omit the gate, and hand off or run tools; no universal wrapper mediates delivery/implementation, and there is no principal separation, least-privilege file permission, or authenticated audit log.
2. Semantic critical-path triggers, artifact field completeness, synthesis fidelity, and reviewer quality are explicitly outside helper proof (`ambiguity_ledger.py:310-314`; `lenses.md:22`; `handoff-sequence.md:35-36`).
3. `transcript_check.py` is a separate required step, not composed into `session_status.py --gate`; some exit-check and multiple-awaiting conditions are warnings (`transcript_check.py:150-195`). `implementation_ready: yes` does not itself prove transcript clean.
4. The gate checks command heads and table shapes; it does not run verification commands or validate their claimed pass conditions.

## Falsification and adversarial challenge (I2, I5)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Multi-reading + reverse evidence at orientation | PROSE + typed open-world record | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/orientation.md:15-19`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/open_world.py:52-85` | Candidate must carry question/falsifier/evidence route; actual challenge quality is semantic. |
| Candidate falsification value | PROSE only | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/interview-loop.md:20`, `:40`, `:64-66` | `would_falsify` is deliberately unmodeled and embedded in free text; scorer does not rank it structurally. |
| Mandatory checkpoint | SCRIPT occurrence/freshness; PROSE content | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:67`, `:86-87`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/interview-loop.md:84-100`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/protocol_state.py:400-403` | Counter/freshness enforced; statement set and correction quality are not. |
| Open-world novelty before lens/dry sweep | SCRIPT record shape/order | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/interview-loop.md:102-104`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/open_world.py:88-153`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_update.py:865-888` | Blocks inventory-only recording mechanically, but model can still produce weak candidates. |
| Bounded contrarian probe | SCRIPT shape/effects | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:68`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/interview-loop.md:109-117`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/probe_policy.py:184-267`, `:270-301` | Neutral/inconclusive yields zero credit; material divergence requires reopen. Helper records metadata and never performs the probe (`probe_policy.py:184-185`). |
| Fresh implementer anti-gaming questions | MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:33-36`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:370-427` | Structured disposition and digest enforced; findings depend on reviewer. |

Gaps:

1. Candidate falsifiers and `reverse-evidence=` are conventions/free text, not structured links to claims, observations, or executable checks.
2. ClaimEvidence `counterevidence` does not automatically mark Contested, lower authority, or reopen a requirement.
3. Probe results require artifact refs but do not check artifact existence/content hash or execute/verifiably reproduce the probe.
4. Two dry sweeps are process saturation, not evidence of model completeness; the contract honestly labels outcome as implementation-ready under recorded evidence, not uncertainty zero (`SKILL.md:8`).
5. Readiness resists percentage dilution because the percentage is explicitly informational and the gate is blocker-based (`output-template.md:202-209`). It is still gameable through self-authored impact weights, splitting/merging entries, Accepted/Deferred status, owner labels, and independence groups. Structured owner/date and critical-source floors make gaming visible but do not independently validate those choices.

## Crash recovery and resumption (I1, I4, I5)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Resume unfinished session instead of overwrite | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:16`, `:34`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/session_init.py:45-75` | Existing unfinished slug blocks reinitialization; completed slug gets suffix. |
| State-first reload after summarization/gap | PROSE | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/SKILL.md:33-34` | Correct source-of-truth rule, but no automatic resume orchestrator. |
| Persist in-flight question/locality/pressure/queue | SCRIPT + convention | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:67-70`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/transcript-format.md:3-18` | Asked marker and track are persisted; transcript semantic completeness remains authored. |
| Lock, journal, rollback/recover generation | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/atomic_write.py:48-55`, `:70-125`, `:134-177`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:28` | Strong local crash consistency on POSIX. |
| Transcript↔protocol check | SCRIPT with warnings | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/transcript_check.py:15-19`, `:104-195` | Numbering/hard counter violations fail; some anomalies warn only. |
| Read-only/plan-mode inline fallback | PROSE | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/state-files.md:71` | No deterministic later merge/reconciliation protocol. |

Gaps:

1. Session state is repo-local and gitignored; no replication/export/restore identity, generation hash chain, remote checkpoint, or cross-machine recovery.
2. Journal stores original plaintext and validates path shape, not authenticity/integrity against tampering.
3. Phase reconstruction relies on flags and re-reading references; no single persisted phase enum/state-machine transition proof.
4. Deferred inline writes can diverge from disk before persistence; no conflict detection or merge semantics are documented.

## Executable handoff and assurance boundaries (I5, I6, I7)

| Mechanism | Enforcement | Absolute file:line evidence | Boundary |
| --- | --- | --- | --- |
| Two-part Build Contract/audit separation | PROSE + compiled schema | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:42-67`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/output-template.md:3-13` | Helps least-knowledge consumption; not confidentiality/access isolation. |
| Strict BuildContract v1 ABI | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:51-209`, `:229-281`, `:284-303` | Stable REQ/VER/source IDs, typed policies, closed coverage, source/self digests. |
| Test + real-surface floor | SCRIPT for declarations | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:60`, `:78-90`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:133-151`, `:277-281`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:335-357` | Requires executable command heads, not successful execution. |
| Guardrail Compile trust-boundary split | MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:59`, `:83`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/output-template.md:92-104`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:314-333` | Separates stop-time predicates, accepted residuals, and substrate-owned pre-action risks; predicate validation is lexical. |
| Human decision boundaries and decision log | SCRIPT floor | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:55`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:296-312`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:103-106`, `:197-200` | Requires logging instruction/path, not that the later implementer actually logs. |
| Deferral owner/date | SCRIPT | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:73-85`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/ambiguity_ledger.py:566-607`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:154-167` | Owner is nonblank text; authority/availability unverified. |
| Probe authorization boundary | SCRIPT shape | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/interview-loop.md:111`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/probe_policy.py:88-100`, `:103-175` | L2/L3 auth binds level/scope/targets/digest; approver/auth ID are unsigned strings. |
| Explicit approval before another agent builds | PROSE | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:24-26`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/output-template.md:345-355` | Restated approval is Part 2 and is not included in composite Part-1 gate evaluation. |
| Fresh review and implementer test | MIXED | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:28-40`, `:62-64`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/build_contract_schema.py:170-186`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/scripts/implementation_gate.py:370-427` | Concrete reviewer string, disposition, no unresolved items, and digest match enforced; actual independence and review quality unproven. |
| Human semantic floors stated honestly | PROSE | `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/lenses.md:22`; `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview/references/handoff-sequence.md:35-36` | Lens internal completeness and full enumerated-behavior preservation explicitly require review. |

Gaps and discrepancies:

1. **Authority overclaim:** every non-fatigue checkpoint confirmation is mechanically minted as `decision_authority=owner` (`session_contracts.py:70-82`). The system does not establish that the current user owns or was delegated the affected decision.
2. **Unauthenticated authorization:** `approved_by`, authorization ID, owners, reviewers, and decision actors are strings; no identity provider, signature, role/policy lookup, expiration, revocation, or separation-of-duty check exists.
3. **Restated approval is not a gate input:** explicit approval before seeding is normative prose/Part 2, while `implementation_gate.evaluate` extracts and gates Part 1 (`implementation_gate.py:225-235`).
4. **Staged L3 inconsistency:** docs allow L3 staged/production telemetry (`interview-loop.md:111`) and enum includes `l3:staged-telemetry` (`probe_policy.py:44-48`), but deterministic selection reaches L3 only for `production_only` (`:66-81`), L3 authorization permits production scope only (`:141-150`), and production-only attempts require production lineage (`:263-266`). Staged-only L3 appears unreachable.
5. **No property-proof/model-adequacy split:** BuildContract has trace, acceptance, and verification declarations but no formalism, model artifact/digest, assumptions/bounds, property, proof result/certificate/checker, model-adequacy evidence, or residual proof risk. A digest is integrity, not semantic proof.
6. **No runtime enforcement return:** the handoff instructs the implementer to log `decisions.jsonl`, name tests, and stop for postmortem, but the live gate only checks that these instructions are present; it does not bind an implementation result/attestation back to the contract.

## Git-history evidence

- `git log -S 'fresh-implementer' -- .agents/skills/ultimateinterview` identifies baseline introduction/evolution in `77b0327`, `f50d110`, `131b4fd`, and `3fc0d0e`.
- `git log -S 'crash' -- .agents/skills/ultimateinterview` identifies crash/resume evolution in `77b0327`, `f50d110`, `131b4fd`, `3fc0d0e`.
- `git log -S 'material_revision'` and `-S 'independence_group'` do not reach the live v1 code because those files/changes are presently uncommitted/untracked.
- `3fc0d0e` added the committed deterministic readiness implementation baseline (31 files, including `implementation_gate.py`, `atomic_write.py`, status/update hardening); `32c565c` added two readiness-hardening documents; `1aa49e4` added prose epistemic hardening; `33f64b0` added boundary-depth contract language.

## Verification

Current executable controls were cross-checked by running:

```text
uv run --python 3.14 --with pytest --with 'pydantic>=2.7' --with 'typer>=0.12' --with 'rich>=13.7' pytest -q \
  scripts/test_claim_evidence.py scripts/test_claim_evidence_lineage.py \
  scripts/test_open_world.py scripts/test_probe_policy.py \
  scripts/test_v1_ledger_integration.py scripts/test_v1_protocol_integration.py \
  scripts/test_v1_gate_integration.py scripts/test_v1_session_integration.py \
  scripts/test_v1_build_contract_integration.py scripts/test_build_contract.py \
  scripts/test_build_contract_strict.py scripts/test_atomic_write.py
```

Result: **169 passed in 0.95s**. This verifies helper behavior represented by those tests, not runtime truth of evidence, reviewer independence, command execution, or external authority.

## OBSERVATIONS

1. The live contract has a strong typed fail-closed *process-integrity* core: causal-lineage preservation, current-establishing evidence eligibility, blocker-based readiness, revision invalidation, atomic crash recovery, and digest-bound BuildContract compilation.
2. It already contains zero-trust-compatible architectural seams: explicit authority types, least-sufficient probe levels, scoped high-risk authorization, policy-like blocker evaluation, enforcement-like exit failure, decision boundaries, real-surface verification, and substrate-owned fast-risk classification.
3. The dominant trust gap is that claims about identity, source, independence, freshness, authorization, and review context are structured but self-asserted. The system validates the envelope, not the issuer or observation.
4. The documentation usually states semantic boundaries honestly (artifact enum vs contents; ID traceability vs behavior fidelity; readiness under recorded evidence vs zero uncertainty), but a few prose claims are stronger than executable enforcement, especially fresh reviewer independence, user ownership, explicit final approval, and staged L3 telemetry.
5. The v1 design is not yet a committed/published baseline, so any architectural recommendation must first stabilize the live contract and tests as one coherent version.

## CLAIMS

1. **I1:** Current helpers provide atomicity and internal digest consistency, not authenticated provenance or tamper evidence.
2. **I2:** Current helpers constrain which evidence may establish a claim, but cannot verify the warrant, source observation, counterevidence semantics, or model adequacy.
3. **I3:** Current helpers prevent obvious derived-evidence double counting, but declared group/key uniqueness is not proof of causal independence.
4. **I4:** Current helpers invalidate on interview-state revision and Part-1 byte changes, but lack source-driven expiry, external drift detection, and revocation.
5. **I5:** The composite gate is meaningfully fail-closed for represented state, but it is not a separate trusted enforcement plane and omits some delivery procedures such as transcript cleanliness and final approval.
6. **I6:** BuildContract v1 is machine-parseable and coverage-closed, but verification commands are checked for presence/resolvability rather than executed proof, and semantic completeness remains reviewer-bounded.
7. **I7:** Authority and approval scopes are modeled but identities/roles are not authenticated; checkpoint confirmation currently over-assigns OWNER authority.

## EXPAND

1. Add evidence artifact references: canonical locator, capture method, observed revision/time, content digest, verifier, and optional signed attestation; validate channel↔actor compatibility.
2. Replace raw `freshness=current` with source-class freshness policy: max age/revision binding, checked-at timestamp, invalidation reason, explicit revoke/supersede chain, and gate-time revalidation.
3. Add an independence certificate/assessment: producer identity/model/provider/context digest, shared-source disclosures, correlation rationale, and conservative same-group default unless separation is demonstrated.
4. Split epistemic authority from decision authority end to end. Require an authenticated owner/delegation record before OWNER/DELEGATED can override triangulation; checkpoint should default to `decision_authority=none` unless authority was established.
5. Make reviewer independence a policy predicate: distinct principal/context, subject-aware self-review prohibition, model/provider separation where requested, review input digest, and signed result. Keep self-audit as an explicitly weaker disposition.
6. Compose transcript consistency and final approval into delivery readiness, or emit separate named verdicts (`contract_ready`, `transcript_ready`, `approved_for_seed`) so `implementation_ready` cannot be mistaken for authorization to execute.
7. Make probes proof-carrying: artifact digests/existence, executable reproduction command, captured output, producer attestation, and fix the staged-L3 dead surface.
8. Add optional risk-triggered formal verification fields per REQ/VER: formalism, model artifact+digest, assumptions/bounds, property, result, certificate+checker, model-adequacy evidence, and residual risk. Do not conflate a proof of a model with proof that the model captures user intent.
9. Separate policy decision from enforcement operationally: immutable policy/version, read-only evaluator, append-only signed event log, least-privilege writer, and an execution harness that refuses a stale/unapproved contract digest.
10. Bind implementation return evidence to the BuildContract digest: decision log, test/REQ mapping, executed verification results, environment identity, and postmortem attestation, while preserving the fresh independent postmortem boundary.
