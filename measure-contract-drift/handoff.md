# Measure Contract Drift Handoff

## Current status

The generation-evolution experiment tooling and the requested g02 run are complete.

- g02 completed all 72 cells: 48 train and 24 validation.
- Results: 66 completed and 6 invalid, with no required artifacts missing.
- Four structural mutation intents are bound through the manifest, lineage, and digests.
- Early convergence was detected at generation 2 with `frontier-stagnation`.
- The final-test cases have not been run.
- LLM-generated parent, candidate, and change summaries are persisted and shown in the generation comparison report.
- A second resume made no model calls and reproduced identical summary, report, and receipt SHA-256 values.
- The full test suite passed: 60 tests.
- Commit `6875da2` was pushed and matched `origin/master` at completion time.

Primary artifacts are under:

`.measurecontractdrift/discovery/g02-20260716T134943793896Z/`

- `generation-comparison.html`
- `skill-change-summaries.json`
- `convergence.json`
- `receipt.json`

## Recommended next work

### 1. Run the sealed final test

Evaluate the final selected skill once against the held-out cases:

- `todo`
- `access-grant`
- `appointment-reschedule`

Do not feed final-test results back into mutation, candidate selection, or Pareto updates. This is the most natural next step because it measures generalization after the experiment converged.

### 2. Add a multi-generation orchestration CLI

Automate candidate generation, train, validation, Pareto updates, and convergence checks across generations. Stop when convergence is detected or the configured generation limit is reached. This is an extension for future experiments; the current experiment already converged at g02.

### 3. Strengthen repetition-consistency metrics

Compare r1 and r2 for each candidate/case across question decisions, fidelity, and root causes. Use the result to identify candidates whose mean score is strong but whose behavior is unstable, optionally exposing consistency as a Pareto-supporting metric.

### 4. Build a long-term evolution dashboard

Combine generation reports into one view showing lineage, mutation intent, score changes, Pareto movement, and convergence over time. The first useful view should cover g00 through g02 and clearly display the early-stop reason.

## Suggested execution order

1. Run and seal the three final-test cases.
2. Preserve the resulting artifacts without using them as evolution input.
3. For future experiments, add the multi-generation CLI.
4. Add repetition-consistency analysis and the cross-generation dashboard.

## State archive

The `.measurecontractdrift` directory contains the experiment's execution state and generated artifacts. Use the ZIP created alongside this handoff for transfer or backup, then extract it at the project root so the hidden directory is restored with its original name.
