# Blind Pairwise Question-Quality Evaluation Plan

## Goal

Measure interview-question quality separately from contract and implementation fidelity without adding a stateful owner simulator, an ambiguity ledger, or a multi-axis absolute rubric.

The diagnostic answers one bounded question:

> Which interview more efficiently resolves material contract-changing uncertainty without asking discoverable facts or inventing scope?

It does not claim to measure whether a real owner understood the questions or whether an adaptive follow-up elicited previously hidden knowledge.

## Evaluation Boundary

Run the comparison on validation transcripts only. Keep it outside candidate selection, mutation feedback, Pareto updates, and convergence until stability is demonstrated.

For each comparison, give the judge only:

- the user request;
- a compact, identical starter-repository snapshot;
- the complete questions, options, recommendations, and selected answers for anonymous Interview A and Interview B.

Do not expose candidate or generation identity, skill text, mutation intent, existing scores, contract drafts, compiled artifacts, implementation results, postmortems, or rankings. The selected answer supplies conversational context but is not itself a reason to prefer one candidate.

## Closed Judge Contract

Require exactly one preference and one transcript-grounded decisive example:

```json
{
  "preference": "A | B | tie",
  "decisive_example": "one concise example from the supplied transcripts"
}
```

Use this judge instruction:

> Which interview more efficiently resolves material contract-changing uncertainty without asking discoverable facts or inventing scope? Choose A, B, or tie and cite one decisive example. Judge the questions and decision structure, not the desirability of the deterministically selected answers.

Do not add separate clarity, relevance, depth, breadth, or style scores.

## Pairing And Position Control

With four candidates there are six unique pairs. Use the three perfect matchings:

1. `C0-C1`, `C2-C3`
2. `C0-C2`, `C1-C3`
3. `C0-C3`, `C1-C2`

Assign matchings deterministically across validation case/repetition strata. Evaluate every scheduled pair twice with A and B reversed. A comparison is position-consistent only when both orders identify the same candidate or both return `tie`; conflicting reversed results are recorded as unstable and scored as a tie.

A minimal twelve-call diagnostic covers all six unique candidate pairs once in both positions. Additional validation strata may repeat the schedule to measure repeat stability, but are not required for the first diagnostic.

## Aggregation

For each position-consistent pair:

- win: `1.0`;
- tie or unstable: `0.5` for each candidate;
- loss: `0.0`.

Report each candidate's points divided by comparisons participated in. Do not introduce Elo, Bradley-Terry, or confidence-weighted ranking for four candidates.

Also report only two stability diagnostics:

- position consistency: fraction of reversed comparisons that agree after candidate normalization;
- repeat consistency, if the schedule is repeated: fraction that preserve the same normalized outcome.

## Existing Zero-Cost Diagnostic

Separately report a per-cell miss-free bit from the already validated postmortem:

```text
pass = discovery-miss count == 0 and decision-miss count == 0
```

Aggregate its Wilson lower bound across cells and repetitions. Treat this as elicitation-outcome evidence, not direct question-quality evidence; it must not replace the blind pairwise comparison.

## Promotion Gate

Keep pairwise preference diagnostic-only for the first run. Consider adding it to Pareto selection or train feedback only if:

- A/B reversal is acceptably stable;
- repeated comparisons are acceptably stable;
- decisive examples are grounded in the supplied transcripts;
- the ranking is not merely a proxy for fewer questions, shorter prose, or existing fidelity; and
- invalid cells are not rewarded for appearing concise.

If these checks fail, revise or discard the judge contract rather than adding more rubric dimensions or simulator state.

## Minimal Implementation Surface

The first implementation should add only:

1. deterministic pair scheduling and A/B reversal;
2. one closed judge schema and prompt;
3. one generation-level pairwise-votes artifact containing inputs by digest, preferences, decisive examples, and normalized outcomes;
4. a compact report section for candidate win rate and the two stability diagnostics; and
5. tests for identity blinding, deterministic pairing, position balance, output validation, and diagnostic-only isolation.

Do not add a stateful owner simulator, gold ambiguity axes, a question ledger, multiple judge roles, absolute Likert scores, or fitness feedback in the initial implementation.
