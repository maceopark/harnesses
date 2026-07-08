# Orientation, Framing, and Right-Sizing

Read once at skill start (ORIENT phase). Governs everything before the first scored question: classification, repo inspection, session-state creation, the brain-dump intake, the framing challenge, and depth choice.

## Orientation

1. Classify the work as `brownfield-change`, `bugfix`, `integration`, `data/schema`, `UX/UI`, `security/privacy`, `performance`, or `research-spike`.
2. Inspect local context before the first question:
   - applicable `AGENTS.md`, `README`, `docs/`, ADRs, PRDs, issue text, tests, and snapshots
   - repo glossary or domain-model files (`CONTEXT.md`, `CONTEXT-MAP.md`, `docs/glossary*`): reuse canonical terms, and record conflicts between the user's vocabulary and the glossary as gaps
   - interview lessons (`docs/ultimateinterview-lessons.md` and the global `lessons.md` beside this skill, from `ultimateinterview-postmortem`): when a lesson row's signal appears in the request or touched code, treat its lens as triggered and note `lesson-triggered` in the ledger; skip `## Retired` rows
   - likely modules, public interfaces, domain terms, existing tests, and user-facing surfaces
   - current behavior when cheaply observable (tests, CLI, HTTP, logs, code search)
3. Run a hidden deficit-recognition pass before choosing lens states. This is internal machinery, not a user-facing protocol menu: never ask the user to choose a protocol, slash command, Greek term, or method label. Tag likely deficit classes in ordinary ledger/lens reason text, such as `deficit=context-insufficient`, `deficit=boundary-undefined`, `deficit=framework-absent`, `deficit=execution-blind`, `deficit=application-mismatch`, `deficit=context-tethered`, `deficit=recall-or-comprehension`, or `deficit=method-underdetermined`. When two plausible readings survive the repo scan, record at least two candidate readings with supporting evidence and `reverse-evidence=<observation that would shrink or falsify this reading>`; collapse to one frame only when the evidence is unambiguous. Use the tags to trigger, skip, or complete lenses, then phrase the visible turn as recognition of the current model ("correct the wrong lines"), not as a choice of method.
4. Create the session with `scripts/session_init.py <repo-root> <slug> --depth <depth> --entries '<json array>'` - it writes all four state files already valid, applies the fresh-suffix rule, and ensures `.gitignore` coverage (report its one-line gitignore note). Compose the initial entries first; the six-way coverage below is a checklist for them, not JSON keys: known facts, human decisions needed, assumptions, open gaps, potential non-goals, and evidence to verify. Store hidden deficit conclusions in existing fields: `ledger.origin` (`orientation` or `lens:<name>`), `ledger.reason`, and `lenses.<name>.reason`; do not add protocol schema fields unless replay or testing is impossible without them.
5. Open with a brain dump, not a question - invite the user to narrate: what they want and why, constraints they already know, what they are afraid of breaking, edge cases they have seen, and any "by the way". Bundle the stakes calibration into the same message: state the chosen depth, its budget, and the one-line reason ("treating this as `focused`, 12 interactions, because <reason> - correct me if the stakes are higher or lower"). Mine the dump into ledger entries (`from-user`), extract the real implementation branches, and only then start scored questions. Set `brain_dump_done` in `protocol.json`. Dump statements are claims: they go through Answer Handling like any answer - a critical-path dump claim still needs pressure or a second channel before dropping below score `2`. Skip the invitation only when the request itself already is the dump (a rich issue text, spec draft, or long prior discussion) or the user declines; record `brain_dump_waiver` with the reason.
6. If the user arrives with substantial pre-work (prior discussion, draft specs, failed attempts), do not re-elicit it. Enter context-first: synthesize the pre-work into the initial ledger, then run a falsification checkpoint (pattern in `references/interview-loop.md`) as the first user interaction. This satisfies the brain-dump intake; record the waiver.

## Challenge The Framing

After the brain-dump intake and before the first scored question, spend one pass challenging the request itself:

- Is the stated request a symptom? What root cause would make it unnecessary?
- What happens if we do nothing?
- Is there a materially simpler alternative that still reaches the desired outcome?
- Is the requested artifact class actually what the outcome needs?

Record the outcome in `protocol.json` (`framing_challenged`) and the transcript; only a challenge that changes the problem statement creates or updates ledger entries. If the challenge changes the problem statement, restate it and confirm with the user before continuing. Re-run the challenge only when new evidence contradicts the problem statement or stagnation escalation triggers it.

## Right-Size The Interview

Run the core path every time, then activate only the lenses triggered by the change.

Core path: inspect repo/docs first; clarify problem, outcome, scope, non-goals, decision boundaries; identify acceptance evidence and verification surface; keep ledger and protocol state persisted; critical-path questions one at a time, low-risk confirmations batched with smart defaults.

Hidden deficit tags are an input to right-sizing, not a new depth. A hidden `deficit=execution-blind` can trigger endgame guardrail compilation; `deficit=boundary-undefined` can trigger controlled-language or domain/state; `deficit=context-insufficient` can keep a repo-prober lane open. The user should still experience the same brain dump, dashboard, highest-leverage question, and checkpoint flow.

Depth and question budget (interaction costing and the budget-exhaustion rule are SKILL.md invariants):

- `minimal`: tiny, reversible, low-risk change with obvious behavior and existing tests. Core path, one pressure question, one pre-handoff breadth sweep and contrarian probe, controlled acceptance criteria. Budget: 3 human-decision interactions - dump + one scored thread + checkpoint by design; the framing restatement folds into the checkpoint, and needing a second scored question means the change is not `minimal`: escalate the depth.
- `focused`: default. Core path plus the triggered lenses below. Budget: 12 human-decision interactions.
- `full`: one of these is the change's primary risk, not merely a touched area: security/privacy, data/schema, external integration, performance/reliability, irreversible writes, multi-stakeholder workflow, unclear domain language, or high cost of a wrong assumption. A touched-but-secondary concern stays `focused` with that lens triggered; the readiness gate (`references/handoff-sequence.md`) still fires on touch. Every relevant lens, with non-applicability recorded for skipped ones. Budget: 20 human-decision interactions.

Lens triggers:

- `viewpoint`: multiple stakeholders, operations/support impact, compliance, billing, external systems, or ownership conflict
- `domain/state`: long-lived domain concepts, identity, lifecycle states, legal/illegal transitions, guards, invariants, overloaded vocabulary, consistency, concurrency, cross-context boundaries, or a temporal word in the goal or request (today, daily, morning, weekly, due, per-day - the boundary-crossing walk in `references/lenses.md` §4 is then mandatory)
- `goal/obstacle`: unclear outcome, brittle assumptions, missing exception paths, or contested priorities
- `misuse`: security, privacy, fraud, destructive actions, unauthorized access, irreversible data changes, abuse potential, or any command/API surface accepting free-text or user-supplied values (degenerate-input enumeration in `references/lenses.md` §6 is then mandatory)
- `quality`: vague words such as fast, reliable, scalable, compatible, simple, usable, safe, robust, or architecture-significant quality attributes
- `controlled-language`: fuzzy acceptance criteria, missing trigger/condition/response, prose that admits multiple interpretations, a validity/reject category (invalid, malformed, corrupt) named without its deciding predicate, or a persisted/loaded field named only by type (integer, boolean, count, version) whose coercion boundary is unstated (does a JSON boolean count as the integer? a numeric string? a float? — claudeplan wrote `true` into an `isinstance(int)` field)

For each untriggered heavy lens, record a short skip reason in the ledger or final spec when the omission could surprise the implementation agent.
