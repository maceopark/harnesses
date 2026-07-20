---
name: emergent-orchestration
description: >-
  Run bounded-autonomy multi-agent work on top of Orca orchestration by fixing
  the information flow while letting workers self-select useful contributions,
  abstain when they add no value, and adapt coordination within explicit safety
  and decision boundaries. Use when a task benefits from dynamic roles,
  self-organizing agents, sequential peer context, role-free collaboration, or
  testing centralized versus autonomous coordination. Use $orchestration for
  the underlying Orca task, dispatch, messaging, DAG, and wait mechanics.
---

# Emergent Orchestration

Use this skill to turn a multi-agent task into a bounded-autonomy organization.
It is an application pattern on top of `$orchestration`; it does not replace
Orca's lifecycle, provenance, or worker-completion rules.

## Choose this pattern

Use it when the work has at least two of these properties:

- multiple valid expert perspectives;
- sequential dependencies or accumulated context;
- uncertain decomposition or changing subtask needs;
- a meaningful cost to assigning the wrong fixed role;
- a need to compare coordination quality, cost, latency, or resilience.

Do not use it for a trivial one-agent task, a strictly deterministic pipeline,
or work where a required specialist must be assigned by policy.

## Preserve the three boundaries

Before dispatching workers, write down:

1. **Immutable mission** — the outcome, non-negotiable values, forbidden
   actions, data boundaries, and the conditions for stopping.
2. **Human/system standards** — acceptance criteria, risk limits, evidence
   requirements, budget, time limit, and when a decision gate is required.
3. **Autonomous protocol** — worker ordering, context handoff format, batching,
   abstention rules, and how the next worker is selected.

Keep the first two boundaries fixed during execution. Permit workers to adapt
only the protocol-level details, and record any material protocol change.

## Default protocol: sequential self-selection

Prefer a small ordered wave over a central coordinator or an unconstrained
broadcast. For each worker in order:

1. Give the worker the mission, constraints, current evidence, and all prior
   worker outputs relevant to the task.
2. Ask it to identify the highest-value unresolved contribution rather than
   assigning it a job title.
3. Permit `ABSTAIN` when the expected contribution is low, duplicative, or
   outside the worker's competence. Require a short reason and the remaining
   gap; abstention never means silently skipping required safety work.
4. Require an artifact, evidence references, open questions, and a concise
   handoff note for the next worker.
5. Dispatch the next worker only after the current worker has sent a valid
   Orca `worker_done` message for its active task and dispatch.

Use a final synthesis/verification worker when the mission produces a decision,
code change, or external-facing artifact. That worker may consolidate and
challenge prior work, but must not erase conflicts or unsupported claims.

## Orca execution contract

Use the `$orchestration` commands and preserve provenance:

```bash
orca status --json
orca orchestration task-create --spec "<mission and acceptance criteria>" --json
orca orchestration dispatch --task <task_id> --to <worker_handle> --inject --json
orca orchestration check --wait \
  --types worker_done,escalation,decision_gate \
  --timeout-ms 900000 --json
orca orchestration dispatch-show --task <task_id> --json
```

Create one tracked task per independently owned work item. Dispatch to a
concrete live worker handle, never to a broad group. Do not claim that work was
orchestrated until `task-list` and `dispatch-show` confirm the task and
dispatch. A worker must send exactly one lifecycle `worker_done` message from
its own terminal. Treat timeouts as checkpoints and continue with rolling waits
while the worker is alive.

## Enforce lifecycle integrity

Treat orchestration state as an append-only evidence ledger. For each
`(taskId, dispatchId)` pair, accept only the first valid `worker_done` sent from
the dispatched worker while that dispatch is active. Require all of the
following before using it as completion authority:

- a non-empty subject and non-empty body;
- the exact active `taskId` and `dispatchId`;
- a completed artifact or explicit failure summary;
- evidence, unresolved work, and a usable handoff in the body, or a valid
  `reportPath` whose artifact exists and can be read;
- `task-list` and `dispatch-show` confirming the completed state.

Classify later messages for the same pair as `duplicate` and ignore them for
lifecycle and synthesis. Classify messages received after the task or dispatch
was marked `failed`, superseded, or retried as `late`; retain them as
non-authoritative diagnostic evidence only. Never let a late message complete
or overwrite the active retry.

Reject empty `handoff` or `worker_done` bodies. If the dispatch is still active,
ask the worker to correct the delivery and send its one valid `worker_done`. If
Orca already terminalized the dispatch from an invalid empty completion, record
`invalid-completion` in the authoritative ledger and create a fresh recovery
task/dispatch for the missing result; do not ask the terminalized dispatch to
send a second lifecycle completion. If a valid `worker_done` already completed
the dispatch, use a normal non-lifecycle message for any clarification.

For long results, require a concise non-empty `worker_done` body plus a durable
artifact path and digest. Read and verify the artifact before passing it to the
next worker. Do not rely on shell-local variables or a separate message that
may arrive empty.

Maintain an authoritative ledger entry for every dispatch:

```text
task_id | dispatch_id | worker | status | authoritative_message_id |
artifact_path/digest | duplicates | late_messages | recovery_reason
```

Use only authoritative ledger entries as `Current evidence` for downstream
workers. Preserve disagreements from valid results, but exclude duplicate,
late, empty, or provenance-mismatched messages from consensus counts.

## Recover stale workers safely

Do not treat a single timeout as failure. Use rolling waits and inspect
`task-list`, `dispatch-show`, terminal presence, and recent output. Recover only
when the worker terminal has disappeared, become unreachable/stale, exited, or
repeatedly fails liveness checks without activity.

When recovery is necessary:

1. Record the original task/dispatch and concrete recovery reason as failed,
   superseded, or `invalid-completion`. Use Orca's recovery surface when it can
   represent the correction; otherwise preserve Orca's terminal record and put
   the coordinator classification in the authoritative ledger.
2. Create a fresh task and fresh terminal for the retry; do not reuse the old
   `(taskId, dispatchId)` as if it were still active.
3. Include the prior failure as diagnostic context, not as a completed result.
4. Verify the retry's new task and dispatch before waiting.
5. If the old worker later reports completion, mark it `late` and ignore it as
   lifecycle authority.

Never impersonate a worker to manufacture `worker_done`. Never retroactively
promote an untracked result into an orchestrated completion.

For independent work, use parallel tasks only when their outputs do not depend
on one another. For dependent work, use the sequential protocol or a shallow
DAG. Keep the dependency depth small and make the next worker's context
explicit; do not rely on hidden terminal history.

## Worker prompt contract

Inject a prompt with this shape:

```text
Mission: <immutable outcome>
Standards: <acceptance criteria, risk limits, budget, evidence rules>
Current evidence: <task-local facts and prior worker outputs>

Choose the contribution that has the highest expected value for the mission.
Do not assume a fixed role. You may ABSTAIN only if your contribution would be
low-value, duplicative, or outside competence; state the reason and the gap.

Return:
1. contribution_type: <what you chose to do>
2. artifact: <analysis, patch, test result, or decision input>
3. evidence: <files, commands, tests, or citations>
4. unresolved: <conflicts, risks, and questions>
5. handoff: <what the next worker should inspect>

Completion delivery:
- Send worker_done exactly once from this terminal.
- Put a non-empty executive summary in the body.
- For a long result, include reportPath and artifact digest; verify the file
  exists before sending.
- After worker_done succeeds, stop and send no further lifecycle messages.
```

Do not expose a worker's private reasoning. Pass only the task result,
evidence, unresolved items, and handoff needed by the next worker.

## Decision gates and safety

Create a decision gate before crossing any materially branching boundary:

- irreversible or destructive action;
- external production effect or credential use;
- conflict between mission and a proposed optimization;
- a worker requests authority outside the stated standards;
- evidence is insufficient for a high-stakes conclusion.

Resolve the gate with a recorded decision, then continue the task DAG. Never
let self-selection bypass authorization, review, privacy, security, or testing
requirements.

## Evaluate the organization

For a first deployment, compare the self-selecting protocol with the existing
fixed-role or centralized baseline on the same task set. Record at least:

- outcome quality and requirement coverage;
- factual/error and policy-violation rate;
- token cost and wall-clock latency;
- number and quality of abstentions;
- rework or human correction time;
- recovery after a worker failure or substitution.

Start with 4–8 capable workers. Increase the count only when measurements show
that the additional context and cost improve the mission outcome. Prefer a
stronger model or better context handoff over simply adding workers.

## Failure modes

- **Weak-model autonomy:** switch to explicit roles and tighter sequencing when
  workers mis-select contributions or abstain excessively.
- **Context flooding:** summarize prior outputs into a verified task ledger;
  retain links to raw evidence.
- **Latency growth:** batch only workers whose inputs are independent, and
  preserve sequential handoffs at dependency boundaries.
- **Role drift:** reassert the mission and standards at every dispatch.
- **False consensus:** require each worker to expose disagreement, uncertainty,
  and evidence rather than merely editing the previous answer.
- **Empty completion:** do not accept an empty body or a summary that only
  points to an empty/missing handoff; recover the content while the dispatch is
  active.
- **Duplicate completion:** accept the first valid `worker_done` only and mark
  later messages for that dispatch diagnostic-only.
- **Late completion:** never let a failed or superseded dispatch overwrite its
  active retry, even when the late content is useful.
- **Stale terminal:** verify liveness across task, dispatch, and terminal state;
  record the failed provenance before creating a fresh task and terminal.

## Completion checklist

Before reporting completion:

- verify the mission and acceptance criteria;
- verify every dispatched worker reached `worker_done` or was explicitly
  escalated/failed;
- verify exactly one authoritative, non-empty `worker_done` exists for each
  completed dispatch and classify duplicates/late messages;
- inspect `dispatch-show` and the final artifact;
- verify every referenced `reportPath` and digest;
- run the smallest relevant tests or checks;
- report abstentions, unresolved risks, cost/latency observations, and any
  validation gap;
- report lifecycle anomalies and recovery attempts separately from substantive
  debate or work results.
