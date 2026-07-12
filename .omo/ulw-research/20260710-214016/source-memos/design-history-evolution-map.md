# Ultimateinterview design evolution and recurring failure modes

Snapshot: 2026-07-10 America/Los_Angeles. Read-only investigation. Historical anchors use `git show <SHA>:<path> | nl -ba`; working-tree anchors are explicitly labeled `WORKTREE@32c565c` because the current v1 contract is modified/uncommitted.

## Temporal validity

- `e4cf1ed99be79696ec8c795de30c0366afc3488e` (2026-07-05) is the repository's initial commit, but it imports a pre-existing multi-document design narrative. Its internal “same-day follow-up” chronology predates the Git granularity; do not interpret every idea in that commit as landing simultaneously in executable skill code.
- `77b0327fe2549baebbe6ca4d287d98bc1c56296e` (2026-07-07) is the first tracked local `.agents/skills/ultimateinterview/` runtime with scripts, references, fixtures, and postmortem integration.
- `3fc0d0e7a667d9a6f61680802fddcef5c6fae223` plus documentation commit `32c565c12a2064ad516379fea8effc7afab0ac62` (2026-07-10) are the last committed contract.
- The live working tree contains a schema-v1 rewrite over `32c565c`: typed ClaimEvidence, causal independence groups, open-world/probe freshness, canonical `build-contract.json`, execution-return/postmortem v2 integration. It is the current on-disk contract, but not a committed/release-complete one. `.omo/plans/ultimateinterview-contract-oracle-control-plane.md:149-154` still has F1-F4 independent final gates unchecked even though implementation todos 1-9 are checked.

## Evolution map

### 1. Risk-routed interviewing and a two-pass audit (historical design bundle, 2026-07-05)

- `e4cf1ed:docs/ultrainterview-improvement-proposal.md:181-188` introduces draft -> audit -> closure gate -> restated approval; lines 200-218 say the design goal is routing and gates, not accumulating methods.
- `e4cf1ed:docs/ultrainterview-research-synthesis.md:9-15` establishes a small always-on core, conditional lenses, and high-risk/seed-only readiness review. Lines 71-84 define fresh-context triggers and deliberately withhold the full conversation/intended conclusion from the reviewer to avoid inherited assumptions.
- `e4cf1ed:docs/ultrainterview-hardening-review.md:18-42` diagnoses the original design as enumeration-heavy and falsification-light: one-shot divergence, framing left unchallenged, exploitation-only question ranking, rich-answer compression, tunnel vision, unpressured convergence, and silent code/docs conflict resolution.
- The same hardening review diagnoses false readiness from percent dilution and self-scoring (`:44-48`), provenance collapse (`:50-57`), and conversation-only state loss across compaction (`:54-57`). It records blocker-based readiness, persisted session state, pressure, falsification checkpoints, re-divergence, breadth sweeps, provenance, and evidence collision at `:59-91`.
- Important superseded state: lines `93-103` say triangulation and always-on sweep/probe were initially prose/manual and postmortem was deferred; lines `105-115` explicitly supersede those points with `evidence_channels`, fail-closed channel validation, mechanical critical-entry triangulation, mandatory sweep/probe, and a separate postmortem skill.

### 2. Durable runtime and feedback-loop import (first tracked skill, 2026-07-07)

- `77b0327` adds the complete local skill tree. `77b0327:.agents/skills/ultimateinterview/SKILL.md:29-40` makes repo inspection, persisted ledger/protocol/questions/transcript, post-compaction reload, six evidence channels, typed status, budget, and no unsolicited synthesis runtime invariants.
- `77b0327:.agents/skills/ultimateinterview/SKILL.md:43-56` moves arithmetic/status into deterministic helpers, establishes blocker-based `handoff_ready`, and distinguishes convergence from implementation readiness.
- `77b0327:.agents/skills/ultimateinterview/SKILL.md:60-86` makes Due Now obligations, two dry sweeps, critical-path ordering, checkpoint/probe minimums, suggestion labeling, pressure, nuance decomposition, evidence collision, and weight-5 channel triangulation part of the loop.
- `77b0327:.agents/skills/ultimateinterview/references/interview-loop.md:49-61` is the earliest explicit anti-invention control: model-invented options are `suggestion`, never `recommended`; recommendations must cite evidence and remain defeasible through Other.
- The postmortem feedback loop is empirical rather than self-certified: `e4cf1ed:docs/ultrainterview-postmortem-design.md:9-21` says interview misses are observable only after diff/spec comparison, and lines `54-89` define failure attribution and fresh-context cross-skill checking.

### 3. Postmortem-driven failure discovery and synthesis protection (2026-07-07)

- Historical app-1 fixture: `f50d110:.agents/skills/ultimateinterview/scripts/regression_fixtures/todo-cli-app/postmortem.md:24-34,53-74` records one low-impact blank-title enumeration miss: 13/14 (~93%).
- App-2: `.ultimateinterview/todo-cli-app-2/postmortem.md:24-32,75-83` records one unknown-command enumeration miss: 8/9 (~89%).
- App-3: `.ultimateinterview/todo-cli-app-3/postmortem.md:25-37,58-63` records two domain/state misses (atomic-write durability and time-injection seam): 12/14 (86%).
- App-4 is the pivotal synthesis-loss incident. `f50d110:.agents/skills/ultimateinterview/scripts/regression_fixtures/todo-cli-app-4/postmortem.md:19-42` records eight escapes, including two cases already present in ledger g14 but compressed out of Part 1. Lines `85-105` separate raw 62.5% from interview-only 68.2%, identify the ledger -> Build Contract fidelity gap, and explain why a Part-1-only reviewer inherited the narrowed contract and could not catch it. Lines `109-110` call for a first-class `synthesis-loss` taxonomy and independent critic routing.
- `f0e1ad6`/`7c155eb` add and tighten `verification_lint`; `131b4fd` adds predicate lint/audit scan; `f50d110` adds regression fixtures and signal-firing so rule edits are checked against measured historical verdicts rather than prose confidence.
- App-5 then exposes deeper “category without predicate” misses. `.ultimateinterview/todo-cli-app-5/postmortem.md:39-49` shows `invalid next_id` lacked a deciding predicate and “Python 3” lacked a version floor, forcing implementer invention. Lines `59-73` show the shipped `python` commands were not resolvable on the host. Lines `85-87` show an executor-authored self-audit reported 17/17 but independent reconciliation found two escapes and corrected the auditor in both directions.

### 4. Hidden epistemic method and guardrail compilation (2026-07-07 to 2026-07-08)

- `cf67bbe:docs/ultimateinterview-epistemic-protocols-handoff.md:43-72` proposes hidden multi-hypothesis recognition, reverse-evidence, recognition checkpoints, and endgame guardrail compilation without a protocol-picker UI. Lines `125-151` keep existing gates, demand determinate predicates, and require a fresh-session rehearsal.
- `1aa49e4` implements that docs-only methodology. Its `references/lenses.md` diff adds typed artifact contracts and `reverse-evidence`; `references/orientation.md` adds hidden candidate readings without new user ceremony; `references/handoff-sequence.md` adds stop-time predicates vs accepted residuals vs substrate-owned fast risks. The example-session addition explicitly says static docs cannot prove discovery-rate improvement; only a later independent postmortem can.
- `33f64b01202bf8c4f4757d37fc0e62b4f41db22a` adds the boundary-depth matrix for multi-surface/multi-actor/multi-channel/async flows so an early failure is not mislabeled end-to-end success.

### 5. Composite deterministic readiness and freshness (committed baseline, 2026-07-10)

- `3fc0d0e:.agents/skills/ultimateinterview/references/handoff-sequence.md:28-40` defines context-isolated review, a Part-1-only fresh implementer test, explicit behavior-fidelity comparison to the ledger, and forbids self-audit for self-referential interviews. General work still has a documented self-audit fallback when no reviewer exists (`:38`), so independence is conditional outside self-reference.
- `3fc0d0e:.agents/skills/ultimateinterview/references/handoff-sequence.md:52-65` turns synthesis protection into FULL-subcase reproduction plus source-id traceability. `handoff_coverage.py` is explicitly only an ID-citation floor; semantic narrowing still requires a human/reviewer read.
- `3fc0d0e:.agents/skills/ultimateinterview/references/handoff-sequence.md:69-103` composes ambiguity, contested/deferral, checkpoint, protocol, coverage, predicate, host-command, review, and raw Part-1 digest gates; only `session_status.py --gate` may authorize delivery.
- `32c565c:docs/ultimateinterview-deterministic-readiness-hardening.md:5-12` formally separates `interview_converged` from `implementation_ready` and denies that either proves zero uncertainty. Lines `31-53` add atomic/journaled state, writer-managed invalidation, stale review rejection, host checks, and a single composite gate. Lines `77-84` explicitly bound the claim: 284 tests/fixture stability do not establish a higher real-world discovery rate; that needs a fresh interview -> implementation -> independent postmortem cycle.

### 6. Causal evidence, open-world freshness, and digest-bound ABIs (current uncommitted v1)

- `WORKTREE@32c565c:.agents/skills/ultimateinterview/SKILL.md:35,80` replaces distinct-channel counting with eligible causal `independence_group` counting; derived restatements retain their root group, model priors/assumptions are hypothesis-only, and single-source authority is an override rather than a synthetic second source.
- `WORKTREE@32c565c:.agents/skills/ultimateinterview/references/state-files.md:34-57` makes runtime timestamp/environment, warrant/counterevidence, provenance, freshness, epistemic authority, decision authority, derivation DAG, and current/firsthand eligibility explicit. Material evidence/probe changes advance a material revision and stale prior open-world, sweep, checkpoint, and review evidence.
- `WORKTREE@32c565c:.agents/skills/ultimateinterview/references/handoff-sequence.md:73-104` gates on causal groups, fresh orientation/breadth open-world records, authorized bounded L0-L3 probes, sidecar digest validity, semantic decision logging, and structured evidence. No-divergence/inconclusive probes earn zero settlement credit.
- `.omo/plans/ultimateinterview-contract-oracle-control-plane.md:162-169` states the intended success contract; however final independent F1-F4 remain unchecked at `:149-154`. Treat this as current design under verification, not historical proof of release readiness.

## Recurring failure modes

### Hallucination / invention

- No committed ultimateinterview history uses “hallucination” as a named failure class. The historically observed equivalent is unsupported invention at two boundaries: interview-generated options and implementer-filled predicates.
- The anti-invention progression is: suggestion-labeling for model-created options (`77b0327:interview-loop.md:49-61`) -> postmortem evidence that vague categories caused invented behavior (`app-5 postmortem:39-49`) -> predicates/version-floor gates (`3fc0d0e:handoff-sequence.md:52-60,89`) -> current v1 model-prior/hypothesis-only ClaimEvidence (`WORKTREE SKILL.md:35`, `state-files.md:50-57`).
- Remaining gap: the contract prevents model priors from *counting as evidence*, but does not prove the model will not propose bad hypotheses. Open-world candidates are bounded, falsifier/evidence-route tagged, and non-establishing; quality still depends on external probing.

### Synthesis loss

- Empirically confirmed at app-4: two behaviors were correctly captured in the ledger and lost only while drafting Part 1 (`f50d110:.agents/skills/ultimateinterview/scripts/regression_fixtures/todo-cli-app-4/postmortem.md:34-42`).
- The fresh-implementer test alone is insufficient because it reads the already-narrowed Part 1 (`:105`); this is a correlated-source problem.
- Current defense is two-layered: fail-closed ID traceability plus independent/manual FULL-subcase fidelity review (`WORKTREE handoff-sequence.md:35-36,52,65,88`). Semantic equivalence remains not machine-proven.

### Evidence independence

- Early provenance was only channel diversity; simulated viewpoints could be assigned evidence-like status, and a user confirmation prompted by an existing record could add a second channel without establishing causal independence (`e4cf1ed:docs/ultrainterview-hardening-review.md:50-52,84,109-110`).
- The committed 2026-07-10 baseline still counts distinct channels and can credit a checkpoint as a second `from-user` channel (`3fc0d0e SKILL.md:75-85`), which is structurally correlated evidence.
- Current v1 corrects this with causal groups, derivation inheritance, stable checkpoint user groups, runtime provenance/freshness, and explicit owner/delegated authority. Legacy schema v0 intentionally retains channel-only behavior, so mixed-version readiness has different epistemic strength.

### Freshness and circular review

- Fresh-context review began as a high-risk conditional gate that withholds conversation/intended conclusion (`e4cf1ed research-synthesis.md:71-84`).
- App-5 demonstrated executor self-audit blindness; its independent critic found misses and corrected an initial auditor error (`app-5 postmortem.md:3,85-87`).
- Committed hardening binds review to the exact raw current Part 1 and invalidates it on material edits (`32c565c readiness-hardening.md:37-51`). Current v1 extends freshness to material revisions, open-world sweeps, probes, and a canonical sidecar digest.
- Remaining boundary: non-self-referential tasks still permit `fresh-context gate: self-audited` when delegation is unavailable (`handoff-sequence.md:38`). Self-referential tasks fail closed to a subagent (`:40`). Same-agent “fresh-eyed” is context restriction, not true independence.

### Gate failures / false readiness

- Percent dilution rewarded adding settled facts and could invert readiness for the same residual risk (`e4cf1ed hardening-review.md:44-48`); replaced by blocker-based readiness.
- Malformed/empty/multi-section ledgers, invalid statuses, duplicate IDs, and unsupported single-source waivers motivated fail-closed schema rules (`e4cf1ed ultrainterview-refine-handoff.md:9-37,62-69`).
- Manual counters and conversation-state assumptions allowed protocol steps to be claimed without durable evidence; the current contract says an unrecorded protocol step did not happen and writer-manages all invalidation.
- Host-incompatible verification (`python` vs `python3`), undefined acceptance predicates, test-suite-only checks, and stale reviews all produced green-looking but non-executable contracts; they are now composite blockers (`32c565c readiness-hardening.md:43-53`).
- Gate success remains bounded: deterministic tests prove implementation stability and replay consistency, not discovery completeness or semantic truth (`32c565c:77-84`). The postmortem/evidence bundle is calibration evidence, not a proof that no gaming or negative-space miss occurred.

## OBSERVATIONS

1. The design repeatedly strengthens after a concrete escape: enumeration misses -> lessons, synthesis loss -> ledger/Part-1 fidelity, invented predicates -> predicate gates, host substitutions -> command resolution, self-audit blindness -> critic review, stale drafts -> digests, correlated channels -> causal groups.
2. The strongest recurring failure is not raw model fabrication; it is a *boundary transform* that silently upgrades a hypothesis, compresses a settled statement, or reuses correlated evidence as if independent.
3. The contract increasingly separates claims: discovery convergence, implementation readiness, execution provenance, and postmortem semantic assessment are distinct. This separation is more important than any individual lens.
4. Backward compatibility deliberately preserves weaker schema-v0 semantics. Any assurance statement must name the schema/version and material revision it evaluated.

## CLAIMS

1. **Historical claim:** by `3fc0d0e`/`32c565c`, ultimateinterview had a composite fail-closed readiness gate with exact-Part-1 freshness, but evidence independence was still channel-based and synthesis fidelity still partly human.
2. **Current-worktree claim:** the v1 rewrite directly addresses causal independence, model-prior non-evidence, open-world/probe freshness, and digest-bound contract/execution artifacts. It is current on disk but not independently release-gated or committed.
3. **Empirical claim:** app-4 proves trace coverage and fresh-implementer review are individually insufficient against synthesis narrowing; app-5 proves executor self-audit and category-only acceptance language are insufficient against hidden invention.
4. **Bounded claim:** deterministic gates can reject known malformed/stale/unexecutable states; they cannot prove the interview found every unknown unknown or that an LLM-generated hypothesis is correct.

## EXPAND

- Compare schema-v0 and schema-v1 readiness on the same fixture to quantify the assurance delta (channel diversity vs causal independence, digest-only vs sidecar, ordinary sweep vs revision-bound open-world/probe evidence).
- Add an adversarial fixture where two differently worded records share one root source, and another where one same-channel runtime observation has two genuinely independent producers.
- Test synthesis-loss beyond ID presence with structured subcase IDs or a semantic diff oracle; explicitly measure false positives from paraphrase and false negatives from subset compression.
- Require a true independent reviewer (not self-audit fallback) for any high-risk/seed-like gate, or make the fallback visibly downgrade `implementation_ready` to a weaker verdict.
- Run the pending F1-F4 release wave and a fresh interview -> implementation -> independent postmortem cycle before claiming v1 improves discovery rate.
