# Ultrainterview Comparison

Use this when the user asks why `ultimateinterview` is better than Ouroboros interview, oh-my-codex deep-interview, or grill-me.

## Evidence Read

- `ouroboros/skills/interview/SKILL.md`: Socratic interview using an MCP question generator, ambiguity ledger, code/research routing, lateral advisory fanout, seed-ready guard, and restate gate.
- `ouroboros/src/ouroboros/agents/socratic-interviewer.md`: question-generator role boundaries, one focused Socratic question, brownfield context prefixes, breadth control, and stop conditions.
- `oh-my-codex/skills/deep-interview/SKILL.md`: intent-first Socratic clarification, weighted ambiguity thresholds, brownfield preflight, challenge modes, context snapshots, `.omx/specs/` output, and execution handoff.
- `skills/skills/productivity/grill-me/SKILL.md` and `skills/skills/productivity/grilling/SKILL.md`: relentless one-question-at-a-time decision-tree grilling with recommended answers; stateless by design.
- `docs/requirements-gap-discovery.md`: Contextual observation, Viewpoint matrix, EventStorming, Domain Storytelling, obstacle analysis, misuse/abuse cases, quality attribute scenarios, EARS, and evidence ledger.

## What Existing Tools Cover

| Tool | Strength | Gap for brownfield spec clarity |
| --- | --- | --- |
| Ouroboros interview | Strong Socratic ambiguity reduction, MCP persistence, lateral advisory, breadth checks, seed handoff | Centers on question generation and seed readiness; requirements methods like Contextual observation, Viewpoint matrix, EventStorming, misuse cases, quality attribute scenarios, and EARS are not a mandatory sweep |
| Design-thinking diverge-converge | Good macro-shape: broaden possibilities, then choose | Too generic unless tied to concrete evidence channels and implementation gates |
| oh-my-codex deep-interview | Stronger brownfield preflight, ambiguity scoring, pressure passes, challenge modes, durable spec output | Still mainly dimension-scored Socratic clarification; it does not require every requirement to pass through domain flow, viewpoint, obstacle, misuse, quality attribute, and controlled-language checks |
| grill-me | Excellent plan hardening; one question at a time, recommended answers, codebase exploration instead of asking factual questions | Stateless and conversational; no required evidence ledger, no mandatory output spec, no systematic quality/misuse/domain-flow coverage |

## Why Ultrainterview Is Better For This User's Goal

The user's goal is not just "ask better questions"; it is to discover as many missing requirements as possible and turn them into a clear spec before coding in an existing codebase. `ultimateinterview` is better for that goal because it combines the best parts of the existing tools with repo evidence, a durable ambiguity ledger, adaptive question selection, risk-triggered requirements lenses, and a conditional seed-readiness audit before high-risk or seed-like handoff.

Better coverage:

- Keeps Socratic questioning for intent and assumptions.
- Challenges the framing itself before the first question: symptom vs root cause, the do-nothing option, and simpler alternatives.
- Pairs gap enumeration with falsification checkpoints: the current world model is periodically presented as numbered falsifiable statements the user corrects, which is the collision move that grill-me, Ouroboros inverted interview, and deep-interview evidence-backed confirmation all converge on.
- Opens with a brain-dump intake instead of structured questions, so the user's narrative - priorities, fears, "by the way" constraints - lands before any LLM-shaped choice can steer it (BMAD's core criticism of MCQ-tree elicitation); structured choices prefer evidenced options, while unevidenced candidates are labeled suggestions and are never recommended.
- Treats risky answers as claims: a gap cannot settle below score 2 until the answer survives one pressure follow-up or is triangulated by a second evidence channel, when the answer settles a weight-3/5 gap, collapses a score-3 gap, contradicts repo evidence, narrows scope, or is hedged. Low-risk confirmations settle directly - pressure is spent where implementation risk lives, not on every sentence.
- Batches low-risk confirmations into smart-default rounds (evidence-backed default per item, accept-all path), reserving one-at-a-time adaptivity for critical-path decisions - so the round-trip cost of the interview scales with risk, not with gap count.
- Runs a breadth sweep every few answers - and at least once per interview at every depth, with a slim contrarian review at each sweep - and tracks divergence saturation, so tunnel vision, silent track-dropping, and unchallenged framing are interrupted structurally, not by luck.
- Uses design-thinking diverge-converge, but makes the diverge phase concrete: Contextual observation, Viewpoint matrix, EventStorming, Domain Storytelling, domain/state modeling, obstacle analysis, misuse cases, quality attribute scenarios, EARS, and evidence ledger.
- Uses LLM strengths directly: fast repo inspection, pattern comparison, scenario generation, adversarial case generation, controlled-language rewriting, and synthesis into a spec.
- Forces brownfield facts to come from code/docs before bothering the user.
- Converts each open question into an implementation-impact decision rather than an abstract philosophical question.
- Selects the next question by expected usefulness: implementation impact, branch splitting, ambiguity reduction, coverage, user cost, and redundancy.
- Uses DDD/state/world-model ideas only when they clarify entities, lifecycle, invariants, transitions, consistency boundaries, or vocabulary drift.
- Treats the first structured spec as a draft, then audits it before high-risk or seed-like handoff.
- Requires an output spec and acceptance evidence, not just shared understanding.

Better safety:

- A requirement is not treated as settled unless it has source/evidence, and critical (weight-5) requirements need two distinct evidence channels or explicit single-source acceptance - enforced deterministically by the ledger script from each entry's recorded `evidence_channels`, not from a self-declared status label.
- Protocol execution itself is script-enforced, not just promised: `protocol.json` records lens decisions, sweep/probe/checkpoint counters, brain-dump and framing status, and budget usage, and `scripts/protocol_state.py` derives due-now obligations and handoff blockers from it. A protocol step that is not recorded did not happen - the same fail-closed trust model the ledger applies to evidence, applied to the interview's own prose rules.
- Evidence conflicts are surfaced, not resolved silently: when the user's claim contradicts code or docs, both sources are shown and the entry stays Contested until the user picks the governing one.
- The ledger is persisted to `.ultimateinterview/<slug>/ledger.json` each round, so long interviews survive context summarization without silent state loss.
- Handoff readiness is blocker-based (no active score 2/3 gap, no untriangulated weight-5 settlement), not percentage-based, so it cannot be diluted by accumulating settled entries.
- An intent guard prevents recommended options from silently narrowing a previously settled scope or artifact class.
- A question budget per depth stops silent over-interviewing; past budget the user explicitly defers or extends.
- Vague words like "fast", "safe", "stable", "simple", and "compatible" must become measurable quality attribute scenarios.
- Abuse, privacy, rollback, audit, and recovery requirements are first-class instead of optional edge-case questions.
- Unresolved ambiguity is allowed only when explicitly deferred with owner/risk.
- Heavy lenses are triggered by risk, so low-risk changes are not forced through irrelevant ceremony.
- For full, high-ambiguity, or seed-like handoffs, a fresh-context reviewer can challenge the draft without inheriting the interviewer's assumptions.

Better handoff:

- The spec leads with a Build Contract - goal, target surface, behavior contract with acceptance criteria, decision boundaries, non-goals, constraints, verification commands, deferred risks - that must pass a fresh-implementer test (could someone with no access to the interview build the same change from Part 1 alone?) before handoff. The audit trail (`Problem`, `Framing challenge outcome`, `Existing evidence`, `Requirements ledger`, `Triggered lenses`, `Seed-readiness audit`, `Q&A record`, `Contested log`, domain sections, `Viewpoint matrix`, misuse and quality scenarios) follows as Part 2, so evidence is available on dispute without burying the build decisions.
- The Q&A record and contested log make the handoff auditable: a downstream agent can distinguish "settled by evidence" from "settled by one unchallenged sentence".
- When the repo keeps a glossary, the handoff proposes glossary updates so the next interview inherits this one's vocabulary decisions.
- This makes the output closer to an execution-ready spec than a transcript, seed, or sharpened conversation.

## Honest Tradeoffs

`ultimateinterview` is not always better. Use the lighter tools when:

- the user wants a quick Socratic conversation: Ouroboros interview or deep-interview
- the plan already exists and only needs pressure-testing: grill-me
- the team already has a complete PRD and only needs issue slicing or implementation
- the change is tiny, reversible, and low-risk

Use `ultimateinterview` when the cost of missed requirements is higher than the cost of a more systematic pre-build interview.

The current design is intentionally not a mandatory full-method sweep. The core path is always on, while viewpoint, domain/state, misuse, quality, and formalization lenses are activated only when their risk signals appear.
