# Transcript Format

`transcript.md` is append-only. One `##` heading per budget-costing interaction, typed and numbered so the reload rule, the postmortem skill, and counter cross-checks can parse it:

```markdown
## interaction 3 [batch] — smart defaults: encoding, filename, cap
```

Typed markers (exactly one per heading): `[brain-dump]`, `[scored-question]`, `[bundle]`, `[batch]`, `[checkpoint]`, `[sweep]`, `[framing]`, `[contrarian-probe]` (a probe that asks the user - budgeted). `[bundle]` is a structured multi-question round-trip of up to three independent critical-path gaps (SKILL.md Per-Round Loop) - one heading, one sub-bullet per question with its own verbatim answer and ledger deltas; it is not a `[batch]` (smart defaults for low-risk gaps) and not a `[scored-question]` (one question). Non-budgeted events append under the parent interaction as sub-bullets tagged `[pressure-followup]` (max two per parent; a still-vague thread returns to the queue as a new `[scored-question]`), `[sweep: from-ledger]`, `[contrarian: self-run]`, `[repo-work]`, `[note]` (0-cost event-less notes - invitations, process feedback, lane fold-backs - written via the `transcript` delta without an event, never hand-appended).

Each interaction records, in order: the question/prompt as asked, the verbatim answer, ledger deltas (`R2: 3->0, +from-user`), and the residual line (`Residual: 15 -> 8`). Add a timestamp to each heading when the clock is available (`## interaction 3 [batch] — title (2026-07-05 14:02)`). At handoff, append one exit-check line: interactions used, `due_now_corrections`, and the entry-origin histogram.

Rules:

- Write the question at ask time, marked `[awaiting-answer]` (`transcript` delta with `awaiting: true`); the marker resolves to `[answered]` mechanically - any answer-bearing delta (costed event, `pressure-followup`, `checkpoint_confirm`) rewrites it (crash/summarization between ask and answer then loses nothing).
- The interaction number must equal `interactions_used` in `protocol.json` after the write - if they disagree, the counter is wrong, not the transcript.
- Checkpoint corrections get one sub-bullet each: `correction: <statement #> - <what changed>`.
- Script-invisible events also get sub-bullets so the postmortem can audit them: `[decomposition]` when a rich answer is split into multiple entries, `[scope-reduction]` when an option was labeled scope reduction, `[scope-addition]` when one was labeled scope addition, `[single-channel]` when a weight-3 entry settles on one evidence channel.
