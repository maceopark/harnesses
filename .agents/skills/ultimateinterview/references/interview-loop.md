# Interview Loop Methods

Read once when the LOOP phase begins - before the first scored question. SKILL.md owns the Per-Round Loop and the Answer Handling rules; this file owns the methods the loop calls. Treat the persisted ledger as the current belief state: known facts, requirement hypotheses, unsettled slots, live implementation branches, deferred risks.

## Diverge: technique routing

Generate candidate gaps through the core path and triggered lenses. When a technique below is active, read `references/lenses.md` for its full method before running it - these one-liners are routing, not the method:

1. `Contextual Observation` (core path): tacit requirements and exceptions from observed behavior, tests, logs, tickets, current workflows.
2. `Viewpoint Matrix` (`viewpoint`): goal, constraint, data owned, failure fear, acceptance evidence per stakeholder; rows are `simulated` or `confirmed` - simulated rows enter the ledger as `assumption` and cannot triangulate.
3. `EventStorming` (core path): domain flow as events; missing, duplicate, out-of-order, and compensating events; vocabulary mismatch.
4. `Domain / State Modeling` (`domain/state`): ubiquitous language, concept types, lifecycle, invariants; skip for plain CRUD; escalate to a formalism only when it would change implementation risk.
5. `Goal + Obstacle Analysis` (`goal/obstacle`): goals, assumptions, obstacles, derived requirements, residual risks.
6. `Misuse / Abuse Cases` (`misuse`): hostile, careless, overloaded, unauthorized actors; prevent, detect, log, recover, escalate.
7. `Quality Attribute Scenarios` (`quality`): each vague quality word becomes a measurable stimulus/response scenario.
8. `Controlled Language` (`controlled-language`): rewrite requirements in EARS or Given/When/Then; what cannot be written is still ambiguous.

## Question generation, pruning, and scoring

Generate candidate questions from open gaps, goals, obstacles, state/domain models, controlled-language failures, and branch points. Prune questions that the repo can answer, duplicate prior questions, do not affect implementation, or would ask the user to validate low-confidence speculation.

Score the shortlist with `scripts/question_score.py` when the candidates can be represented as JSON. The script is authoritative for ranking; the formula is:

```text
score(q) = impact(q) * branch_split(q) * uncertainty_reduction(q) * coverage(q)
           / (1 + user_cost(q) + redundancy(q))
```

Anchor the estimates (0-5) instead of inventing them fresh each round:

- `impact`: 5 = changes data shape, security, or module boundaries; 3 = changes behavior or tests; 1 = wording only
- `branch_split`: 5 = eliminates three or more plausible implementation paths; 3 = eliminates one; 1 = none
- `uncertainty_reduction`: 5 = collapses a score-3 gap; 3 = collapses a score-2 gap; 1 = confirms a score-1 assumption
- `coverage`: 5 = first question in a triggered-but-unvisited lens; 3 = new aspect of a visited lens; 1 = revisits covered ground
- `user_cost`: 5 = needs an organizational decision or research; 3 = careful thought; 1 = quick pick
- `redundancy`: 5 = near-duplicate of a prior question; 0 = new

Use `0.5`, not `0`, for negligible-but-nonzero numerator dimensions: the product zeroes out on any true `0`; keep the estimates honest and anchored.

## Smart-default batches

- Batch 3-5 low-risk gaps into one message. Each item states the proposed default and its evidence (`Based on <code/doc evidence>, default: <X>`), and the user can reply per-item or accept all remaining defaults in one line.
- Accepted defaults settle at score `1` with their evidence channels recorded (the deriving channel plus `from-user` for the confirmation); a corrected item is a normal answer and goes through Answer Handling.
- Defaults are scope-neutral: a default may settle HOW something already in scope behaves, never silently add a capability. A candidate default that would add one is a `scope addition` and needs its own explicit opt-in question, outside the batch.
- Multi-question round-trip (distinct from a smart-default batch, which carries low-risk gaps only): up to three critical-path gaps MAY share ONE structured multi-question round-trip (costs 1 interaction) when ALL hold - mutually independent (answers cannot constrain each other), each option space evidenced, each with a recommended default; never bundle gaps whose answers could interact.
- Routing (critical-path definition, never-batch-a-critical-path-gap, the flush rule) is in SKILL.md Per-Round Loop.

## Question shaping

Shape the answer as a low-friction choice: deliver scored questions through the structured-question UI even when the option space is unevidenced - the built-in freeform Other always stays open, so options never trap the user. Evidenced options (from code, docs, or the user's own brain dump) may carry a recommendation; options invented from your model of the problem are labeled `suggestion`, never recommended, and the scenario framing moves into the question text:

- Use `single choice` for mutually exclusive implementation decisions.
- Use `multi choice` when several independent conditions, actors, edge cases, or constraints may apply.
- Offer 2-5 options by default; use 6 only when the option set is naturally larger and still scannable.
- Include `None of these / Other` with freeform text whenever the options might not cover the user's intent.
- Mark one option as `recommended` only when evidence supports it, and give a short reason. Never mark a `scope reduction` or `scope addition` option as recommended. Offer a recommended answer when evidence supports it, labeled as a recommendation, not a fact.
- Anchor options to the stated need: never compose a `basic`/default tier that bundles capabilities the user never asked for - tier menus inflate scope by anchoring (a cross-tool comparison shipped priority/deadline fields into a "very simple" tool this way). Each beyond-need capability is its own explicit choice labeled `scope addition`.
- The structured UI with suggestion-labeled options plus its built-in Other replaces pure freeform for scored questions and, by default, for the falsification checkpoint (Other carries corrections); reserve UI-less narrative elicitation for the brain-dump invitation and story-eliciting pressure/checkpoint follow-ups.
- When the gap is deferrable (it does not block the current artifact), include an explicit `Defer - decide later` option; choosing it settles the entry as `Deferred` with owner and decision date recorded in the same bookkeeping pass, and the gap moves to Deferred Risks instead of returning to the queue.
- When the harness has a native structured-question tool (e.g. AskUserQuestion), prefer it for every interaction whose answer space is enumerable - scored choice questions, smart-default batches, and the falsification checkpoint: respect its option ceiling (trim to the 3-4 highest-value options plus its built-in Other), put the recommendation and reason in the option description. Render a falsification checkpoint as a structured question: list the tagged statements in the question body, offer an explicit `all correct` option (recommended only when evidence supports it) and, where the statement set fits the ceiling, the highest-risk statement(s) as discrete flag-if-wrong options; the built-in Other carries the specific correction, so the user still articulates why a statement is wrong and nothing is truncated. If the statement set exceeds the option ceiling and per-statement flagging matters, keep the statements in the body with an `all correct` / `some wrong -> Other` pick, or split into more than one structured round. Keep it UI-less only where the step is inherently open narration: the brain-dump invitation, and a pressure or checkpoint follow-up that needs a story (concrete example, walkthrough, evidence). Pressure follow-ups route by answer shape: an enumerable boundary/branch pick goes through the UI (suggestion-labeled options unless evidenced); only a follow-up that needs a story stays UI-less.

Prefer a scenario question over an abstract one: `I found <evidence>. In scenario <stress case>, should the system <A> or <B>? I recommend <A/B> because <evidence>.` A real shaped prompt is in `references/example-session.md`.

## Pressure follow-ups

Triggers, the free-follow-up cap, and the script `pressure` token live in SKILL.md Answer Handling §Pressure where it pays. The follow-up itself uses one of these techniques: ask for a concrete example or evidence; probe the assumption that makes the answer true; force a boundary ("what would you explicitly NOT do?"); or stress it with one scenario. Corroboration by a second evidence channel counts instead of a follow-up. UI routing for the follow-up (enumerable pick through the structured UI, story-eliciting follow-up UI-less) is in §Question shaping.

## Advisory lanes (background, while the user answers)

Overlap divergence with human latency: a scored question, bundle, batch, or checkpoint round-trip leaves the model idle while the user thinks - use it. Immediately after sending the question, when the harness supports background subagents, dispatch up to three read-only advisory lanes so their findings are waiting when the answer lands. Lane ROLES are fixed here; each lane's PROMPT is composed fresh at dispatch from live session state: the question just asked, the top open gaps (id + one-line requirement), relevant file paths, and the lane's role contract - never the full conversation.
Dispatch every lane through the task tool with the agent name `critic` (a read-only review role); the lane's functional role stays in its freshly composed prompt, not the agent name (see SKILL.md Invariants → Subagent naming). The fixed `critic` agent name lets a `task.agentModelOverrides["critic"]` binding route lanes to a cross-vendor model.

- `repo-prober`: investigate open ledger gaps the repo might answer; return per-gap `{claim, channel, evidence path/command, minimal evidence row}` - conclusions, not file dumps.
- `contrarian`: given the current falsifiable statements, name the one most likely wrong and the unasked question that would expose it (same contract as the slim review - a sweep due next may reuse the freshest lane output instead of spawning again).
- `question-scout`: draft scored-question candidates for the remaining gaps in `question_score.py` input shape, so step 7's regeneration starts from a ranked draft.
- `implementer-scout` (once per interview): armed the first round where no score-`3` gap remains but the stop condition is not yet met (`session_status.py --next` emits the arming advisory while `implementer_scout_run` is false; set the flag true in the dispatch round's delta). Give it a one-line-per-entry extract of the settled requirements plus repo read access - no ledger, no conversation - and ask what it would have to ask before implementing. It takes a lane slot with priority that round. Findings fold back as gaps (origin `fold-back`, validated against the repo first, same as the endgame test); this early run never sets `build_contract_tested` - the endgame fresh-implementer test on the real Part 1 still runs.

Rules: lanes are read-only and budget-free (repo-only work); instruct each lane at dispatch to push its findings back to the main session unprompted the moment it finishes (never wait to be polled - idle lanes cost retrieval round-trips); their returns are advisory evidence, folded into the NEXT bookkeeping pass under the channel of their evidence source - a lane's opinion is never `from-user` and never auto-answers anything or gets echoed to the user. A lane that has not returned by the time the answer is processed folds into the following round instead - never block on a lane. Skip lanes at `minimal` depth and whenever no user round-trip is in flight.

## Falsification checkpoints

At a checkpoint, present the current world model as numbered falsifiable statements - locked facts, inferred assumptions, artifact class, scope boundaries, non-goals - and ask the user to correct only the wrong or incomplete lines. Triggers are in SKILL.md Per-Round Loop step 5; the corroboration-crediting rule is in SKILL.md Checkpoint Invariants - book the confirmation with the `checkpoint_confirm` delta (`{ids, fatigue}`) so counters and crediting apply mechanically.

Pattern:

```text
Current model - correct only what is wrong:
1. <locked fact> [from-code] (k2, g15)
2. <inferred assumption> [assumption] (g7)
3. Artifact class: <what will be built>
4. Non-goal: <what will not be built>
Reply with line numbers and corrections, or "all correct".
```

Fatigue signal: when answers shorten or hedge across consecutive rounds, or a second consecutive checkpoint returns a reflexive "all correct", convert the next checkpoint into one targeted question on the statement you are least sure of, offer to batch or defer remaining low-weight gaps, and log `[fatigue]`.

## Breadth sweep

Every 4 human-decision interactions (`answers_since_sweep`; a batch counts once - the `Due Now` obligation fires this), run a breadth sweep before the next scored question: list unvisited tracks from the original request, check whether any lens trigger has appeared since orientation, and ask the user "which unresolved tracks besides the one we just discussed matter to you?" only if the ledger cannot answer it. Log the sweep outcome (new gaps, or `nothing new`) in the transcript. The sweep is always-on at every depth: if the cadence never fires before the interview ends, run one breadth sweep immediately before the pre-handoff falsification checkpoint. Book it as event `sweep-asked` (asked the user, costs 1) or `sweep-free` (repo-only, costs 0) - both reset the cadence.

## Contrarian probe

Ask: what if the opposite of our strongest assumption is true? Are we solving the right problem? On stagnation escalation, run this (or a checkpoint) instead of a scored question, then set `stagnation_escalated_at` to the current length of `residual_history`. Log the outcome in the transcript even when it changes nothing (`contrarian probe: model survived`).

## Slim contrarian review

Run at breadth sweeps: as a subagent at every sweep at `full` depth, at most one subagent review per interview at `minimal`/`focused` (later sweeps self-run it inline). Give it only the current falsifiable statements, the ledger, and relevant file paths, and ask one thing: which statement is most likely wrong, and what unasked question would expose it? Fold findings into the ledger. When subagent tools are unavailable, answer the same question yourself inline and log `contrarian review: self-run` in the transcript. A slim review never increments `contrarian_probes_run`; only a contrarian probe does.
Spawn this review through the task tool with the agent name `critic` (see SKILL.md Invariants → Subagent naming).
