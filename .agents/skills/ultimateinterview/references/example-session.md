# Worked Example: One Complete Session

A synthetic but fully executed `focused` interview, kept small on purpose. Every dashboard below is real output from the helper scripts run against the files shown - nothing is mocked. Pattern-match against this when unsure what a step's artifacts should look like. (This session exercises the current mechanics: stakes calibration, `pending` lens state, origin instrumentation, obligation precedence (`due_now_corrections`), checkpoint lens re-flip, the combined `session_status.py` final dashboards, and the exit check.)

> Vintage note: this rehearsal predates typed-event bookkeeping, so its deltas set protocol counters manually. In a live session that pattern is now forbidden - pass `event` (and `transcript`/`checkpoint_confirm`) in the delta and let the script compute the counters (`references/state-files.md` §Typed events). The dashboards and file shapes shown remain accurate.

**Request:** "Add a deactivate-account toggle for admins."

## Orientation (repo-only, cost 0)

Classified `brownfield-change`, depth `focused` (budget 12): the primary risk is auth behavior (misuse); data/schema is merely touched (one boolean column), so per the depth rule it stays `focused` with `domain/state` triggered - the readiness gate still fires on touch. Inspection found: no `is_active` flag on `users`; auth loads the user row at login (`api/auth/login.py:44`); `auth/sessions.py` has `revoke_all(user_id)` already used by password-reset; admin actions write `audit_log` rows. Lenses at init: `domain/state` (active↔deactivated lifecycle), `misuse` (lockout abuse), `goal/obstacle`, `controlled-language` triggered; `viewpoint` and `quality` **`pending`** - genuinely undecided until the dump says who is affected. Session folder `.ultimateinterview/deactivate-toggle/` created; `.gitignore` already covers it.

## transcript.md (verbatim, per references/transcript-format.md)

```markdown
# Transcript: deactivate-toggle

## interaction 1 [brain-dump] — invitation + stakes calibration (2026-07-05 17:02)
Q: What do you want, why, what are you afraid of breaking, edge cases, "by the way"?
   Stakes: treating this as focused (12 interactions) because deactivation is
   reversible and UI+flag scoped - correct me if the stakes are higher or lower.
A (verbatim): "Support keeps asking us to disable compromised accounts fast.
Just a toggle in admin. By the way, sessions should die the moment we flip it -
that's the whole point. Don't delete anything, ever."
- stakes: user did not correct focused/12 - calibration accepted
- ledger deltas: F1,F2 (orientation, pre-seeded), R1 s2, R2 s3w5 (scope of
  "sessions" undefined: cookies? api tokens? refresh?), R3 s2, N1 non-goal
- viewpoint lens: pending -> triggered (support named as a stakeholder)
- [repo-work] framing challenged (after dump, before scored questions): root
  cause = incident response speed; do-nothing leaves support paging engineers;
  no simpler alternative reaches "support self-serve". Request survived -
  recorded here and in protocol.json, NOT as a ledger entry.
- Residual: - -> 29 | gap count 6

## interaction 2 [scored-question] — session revocation scope (Q-sessions, 187.50) (17:05)
Q: When the toggle flips, what exactly dies: browser sessions only, or also
   api_tokens and the mobile refresh token?
A (verbatim): "Everything, I guess. If they're compromised they're compromised."
- [pressure-followup] (1 of 2 free) hedged ("I guess") + settles w5: scenario -
  "the mobile app holds a refresh token; deactivate at 09:00, the app silently
  re-auths at 09:05. Acceptable?" A: "No - refresh tokens too, same transaction.
  And when we flip it back the person just logs in again, no password dance."
- ledger deltas: R2 3->0 (+from-code: revoke_all precedent; the scenario answer
  itself stays from-user - one channel, never a triangulation pair), R1 2->0
  (+from-code: login.py:44 rejection point), R3 2->0 (pressure surfaced the
  reactivation decision; Accepted single-source, origin: pressure)
- Residual: 29 -> 2 | gap count 6

## interaction 3 [batch] — smart defaults (3 items, one message) (17:08)
Based on repo precedent: (a) audit_log row per flip (action=user.deactivate/
reactivate); (b) toggle in the user-detail danger zone like the role editor;
(c) status label "Deactivated" reusing the status-chip vocabulary.
Reply per-item or "accept all".
A (verbatim): "accept all"
- ledger deltas: R4 s1, R5 s1, R6 s1 (origin: batch, +from-user confirmation)
- Residual: 2 -> 6 | gap count 9 (residual rose because enumeration added
  entries - gap count rose with it, so this is divergence, not stagnation)

## pre-handoff: flush, sweep + probe (cost 0) (17:10)
- [due-now] protocol_state.py: "no breadth sweep has run", "no contrarian probe
  has run" - preempted the plan to jump straight to the mandatory checkpoint
  (nothing left to flush: interaction 3 was the batch); due_now_corrections -> 1
- [sweep: from-ledger] unvisited track: bulk deactivation for compromise waves -
  dump already said "not now" territory; D1 recorded Deferred (owner: jpark,
  origin: sweep). Nothing else new.
- [contrarian: self-run] "what if the real need is temporary suspension with
  auto-expiry, not a manual toggle?" - R3's explicit no-auto-expiry decision
  holds (user chose it under pressure); model survived
- quality lens: pending -> skipped (no architecture-significant quality
  attribute survived the controlled-language pass)

## interaction 4 [checkpoint] — mandatory pre-handoff falsification (17:11)
Current model - correct only what is wrong:
1. Deactivate = admin toggle; login rejected while inactive [from-user/from-code] (R1)
2. Flip revokes sessions + api tokens + refresh tokens, same transaction [from-user/from-code] (R2)
3. Deactivated users are hidden from admin user lists [assumption] (unledgered; the correction below mints R7)
4. Reactivation restores access as-was; no auto-expiry [from-user] (R3)
5. Non-goal: no deletion, no purge [from-user] (N1)
6. Deferred, not built now: bulk deactivate for compromise waves [from-user] (D1)
A (verbatim): "3 is wrong - support has to FIND deactivated accounts. Grey them
out with the status chip. Rest correct."
- correction: statement 3 - R7 created s3->0 same turn (+from-code: the user
  list query has no active-filter today, so visible is the no-change default)
- viewpoint lens: done -> triggered (correction touches the support viewpoint) ->
  re-run inline -> done. Folding this correction does NOT re-arm the checkpoint
  blocker - the user authored it.
- Residual: 6 -> 6 (R7 settled same turn; batch defaults hold at 1) | gap count 10

## pre-handoff: gates + handoff (cost 0) (17:13)
- checkpoint ran after the sweep's D1 and the quality-lens decision, so
  checkpoint_since_last_material_change holds true into the gates
- exit-check: interactions 4 | due_now_corrections 1 | origins: orientation 2,
  dump 3, pressure 1, batch 3, checkpoint 1, sweep 1
```

## Mid-interview dashboard (after interaction 1) - real output

The stop condition is nowhere near satisfiable, and the script says exactly why:

```text
## Ambiguity Dashboard

- Handoff ready: no (blocker-based: no active score 2 or 3 gaps, weight-5 settlements triangulated or accepted)
- Residual ambiguity: 29 (sum of impact_weight x ambiguity_score over active gaps)
- Ambiguity %: 57% (informational; remaining share, lower is better; never gate handoff on this)
- Active gaps: 6
- Deferred gaps: 0
- Residual / denominator: 29 / 51

### Blockers
- active score 3 gaps remain: R2
- active score 2 gaps remain: R1, R3

### Top Drivers

| ID | Ambiguity | Weight | Contribution | Reason |
| --- | --- | --- | --- | --- |
| R2 | 3 | 5 | 15 | scope of 'sessions' undefined |
| R1 | 2 | 3 | 6 | rejection point unverified |
| R3 | 2 | 3 | 6 | reactivation semantics open |
```

## Obligation precedence + honest lens states (after interaction 3) - real output

Right after interaction 3 the ledger side of the stop condition is already met (no active score 2 or 3 gaps), but `protocol_state.py` names exactly what the protocol is still owed - the sweep/probe/checkpoint minimums, the still-`pending` quality lens, and the untested build contract. This is the output that preempted the plan to jump straight to the checkpoint (`due_now_corrections` -> 1) and forced the canonical pre-handoff order: sweep and probe first, checkpoint after. Note: at interaction 4 the residual was flat (6 -> 6) but the gap count grew (9 -> 10), so no stagnation obligation ever fires - productive divergence is exempt.

```text
## Protocol Dashboard

- Protocol ready: no
- Depth: focused
- Question budget: 3 / 12 interactions used

### Handoff Blockers
- no breadth sweep has run
- no contrarian probe has run
- no falsification checkpoint has run
- undecided lens(es): quality; decide triggered or skipped-with-reason before handoff
- build contract has not passed a fresh-implementer test (agent or self-audited)
```

## What a false-ready attempt looks like - real output

An invented evidence channel is rejected with the actual problem named, not union noise:

```text
$ ambiguity_ledger.py ledger.json   # entry with "channels": ["gut-feeling"]
Invalid value: invalid ledger JSON at LedgerDocument.entries.0.evidence_channels:
Value error, unknown evidence channel 'gut-feeling'; use one of: assumption,
from-code, from-docs, from-research, from-scenario, from-user (+1 more)   [exit 2]
```

## questions.json (interaction 2 round) + real ranking

```json
{"questions": [
  {"id": "Q-sessions", "question": "When the toggle flips, what exactly dies: browser sessions only, or also api_tokens and the mobile refresh token?",
   "impact": 5, "branch_split": 3, "uncertainty_reduction": 5, "coverage": 5, "user_cost": 1, "redundancy": 0},
  {"id": "Q-restore", "question": "Reactivation: does access come back as-was, or force a password reset first?",
   "impact": 3, "branch_split": 3, "uncertainty_reduction": 5, "coverage": 3, "user_cost": 3, "redundancy": 0},
  {"id": "Q-visibility", "question": "Are deactivated users hidden from admin user lists or shown with a status?",
   "impact": 3, "branch_split": 3, "uncertainty_reduction": 3, "coverage": 3, "user_cost": 1, "redundancy": 0}
]}
```

```text
1  Q-sessions  187.50   2  Q-visibility  40.50   3  Q-restore  33.75
```

(Q-restore lost the ranking but was absorbed into interaction 2's pressure thread - a follow-up costs 0. Q-visibility never needed asking: the checkpoint's falsifiable statement 3 flushed it out as a correction instead.)

## ledger.json (final)

```json
{
  "entries": [
    {"id": "F1", "requirement": "auth loads the user row at login (api/auth/login.py:44); users has no is_active/status flag",
     "status": "Triangulated", "ambiguity_score": 0, "impact_weight": 2,
     "evidence_channels": ["from-code"], "origin": "orientation", "reason": "read during Orientation"},
    {"id": "F2", "requirement": "auth/sessions.py revoke_all(user_id) exists; password-reset already uses it",
     "status": "Triangulated", "ambiguity_score": 0, "impact_weight": 2,
     "evidence_channels": ["from-code"], "origin": "orientation", "reason": "read during Orientation"},
    {"id": "R1", "requirement": "deactivation = admin toggle on user detail page; login rejected with the generic failure message while deactivated",
     "status": "Triangulated", "ambiguity_score": 0, "impact_weight": 3,
     "evidence_channels": ["from-user", "from-code"], "origin": "dump",
     "reason": "dump claim; rejection point verified against api/auth/login.py:44 (interaction 2 thread)"},
    {"id": "R2", "requirement": "deactivate revokes browser sessions AND api_tokens AND the mobile refresh token in the same transaction, via revoke_all + token revocation",
     "status": "Triangulated", "ambiguity_score": 0, "impact_weight": 5,
     "evidence_channels": ["from-user", "from-code"], "origin": "dump",
     "reason": "settled at interaction 2; survived pressure (mobile refresh-token case forced the boundary - a scenario answer stays from-user); second channel from-code: revoke_all precedent"},
    {"id": "R3", "requirement": "reactivation restores access as-was, no forced password reset; deactivation never auto-expires",
     "status": "Accepted", "ambiguity_score": 0, "impact_weight": 3,
     "evidence_channels": ["from-user"], "origin": "pressure",
     "reason": "surfaced by the interaction-2 pressure follow-up; user's explicit single-source decision"},
    {"id": "R4", "requirement": "every toggle flip writes an audit_log row (action=user.deactivate/reactivate, actor, target)",
     "status": "Triangulated", "ambiguity_score": 1, "impact_weight": 2,
     "evidence_channels": ["from-code", "from-user"], "origin": "batch",
     "reason": "batch default accepted at interaction 3 (repo precedent: admin actions audit)"},
    {"id": "R5", "requirement": "toggle lives in the user detail page danger zone, mirroring the role editor placement",
     "status": "Triangulated", "ambiguity_score": 1, "impact_weight": 1,
     "evidence_channels": ["from-code", "from-user"], "origin": "batch",
     "reason": "batch default accepted at interaction 3"},
    {"id": "R6", "requirement": "status label is 'Deactivated', reusing the existing status-chip component vocabulary",
     "status": "Triangulated", "ambiguity_score": 1, "impact_weight": 1,
     "evidence_channels": ["from-code", "from-user"], "origin": "batch",
     "reason": "batch default accepted at interaction 3"},
    {"id": "R7", "requirement": "deactivated users stay VISIBLE in admin lists, greyed with the status chip (checkpoint correction: hidden-by-default assumption was wrong - support must find them)",
     "status": "Triangulated", "ambiguity_score": 0, "impact_weight": 3,
     "evidence_channels": ["from-user", "from-code"], "origin": "checkpoint",
     "reason": "correction to checkpoint statement 3; user list query has no active-filter today (from-code), so visibility is the no-change default"},
    {"id": "N1", "requirement": "non-goal: no deletion, no data purge - deactivate only",
     "status": "Accepted", "ambiguity_score": 1, "impact_weight": 2,
     "evidence_channels": ["from-user"], "origin": "dump", "reason": "stated twice in the dump, confirmed at checkpoint"},
    {"id": "D1", "requirement": "Deferred: bulk deactivate for compromise waves",
     "status": "Deferred", "ambiguity_score": 2, "impact_weight": 3, "deferred": true,
     "evidence_channels": ["from-user"], "origin": "sweep",
     "reason": "owner: jpark, revisit after first real incident; implementer must not build this"}
  ]
}
```

## protocol.json (final)

```json
{
  "depth": "focused",
  "question_budget": 12,
  "interactions_used": 4,
  "answers_since_sweep": 0,
  "sweeps_run": 1,
  "contrarian_probes_run": 1,
  "falsification_checkpoints_run": 1,
  "checkpoint_since_last_material_change": true,
  "framing_challenged": true,
  "brain_dump_done": true,
  "build_contract_tested": true,
  "lenses": {
    "viewpoint": {"state": "done"},
    "domain/state": {"state": "done"},
    "goal/obstacle": {"state": "done"},
    "misuse": {"state": "done"},
    "quality": {"state": "skipped", "reason": "UI toggle; no architecture-significant quality attribute survived the controlled-language pass"},
    "controlled-language": {"state": "done"}
  },
  "residual_history": [29, 2, 6, 6],
  "gap_count_history": [6, 6, 9, 10],
  "stagnation_escalated_at": 0,
  "due_now_corrections": 1
}
```

## Final dashboards - real output

One combined invocation, per the Handoff rule: `uv run scripts/session_status.py --format markdown .ultimateinterview/deactivate-toggle`

```text
## Ambiguity Dashboard

- Handoff ready: yes (blocker-based: no active score 2 or 3 gaps, weight-5 settlements triangulated or accepted)
- Residual ambiguity: 6 (sum of impact_weight x ambiguity_score over active gaps)
- Ambiguity %: 8% (informational; remaining share, lower is better; never gate handoff on this)
- Active gaps: 10
- Deferred gaps: 1
- Residual / denominator: 6 / 72

### Top Drivers

| ID | Ambiguity | Weight | Contribution | Reason |
| --- | --- | --- | --- | --- |
| N1 | 1 | 2 | 2 | stated twice in the dump, confirmed at checkpoint |
| R4 | 1 | 2 | 2 | batch default accepted at interaction 3 (repo precedent: admin actions audit) |
| R5 | 1 | 1 | 1 | batch default accepted at interaction 3 |

## Protocol Dashboard

- Protocol ready: yes (all pre-handoff protocol obligations met)
- Depth: focused
- Question budget: 4 / 12 interactions used

## Combined

- ready: yes (stop condition met: handoff_ready, and protocol blockers empty or only the build contract; run the Handoff sequence this turn)
```

The combined runner reported ready, gates pass -> the Handoff sequence ran in the same turn.

## handoff.md - Build Contract (Part 1, after the fresh-implementer test)

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

- **Goal**: an admin can deactivate/reactivate a user; deactivation instantly revokes all access, reversibly, with nothing deleted.
- **Target surface**: migration `users.is_active` (bool, default true); `api/auth/login.py` (reject inactive at the row-load point, generic message); `api/routes/admin_users.py` (PATCH deactivate/reactivate); `auth/sessions.py` `revoke_all` + api/refresh token revocation in the same transaction; admin user-detail UI (danger-zone toggle, greyed list rows + "Deactivated" chip); `audit_log` writes.
- **Behavior contract** (excerpt): `When an admin deactivates a user, the system shall revoke all browser sessions, api_tokens, and refresh tokens in the same transaction.` / `While a user is deactivated, the login endpoint shall reject authentication with the generic failure message.` / `When a user is reactivated, the system shall restore login access without requiring a password reset.`
- **Quality bars**: (weight 5) already-issued session, api, and refresh credentials are dead on the first request after the deactivation transaction commits (zero grace requests) - verified by the revocation test below.
- **Decision boundaries**: exact migration mechanics, endpoint shape, and chip styling are the implementer's; anything touching what "deactivated" means is not.
- **Out of scope / non-goals**: no deletion or purge (N1); no bulk deactivate (D1, deferred to jpark); no auto-expiry (explicit user decision R3).
- **Verification commands**: auth test - login rejected while inactive; revocation test - live session + api token + refresh token all dead after flip; reactivation test - login works, no reset; audit rows present for both flips.
- **Deferred risks**: D1 bulk deactivate (owner jpark - do not build).

Fresh-implementer test: self-audited (no subagent in the rehearsal harness); two "would have to ask" items found (does deactivation block password-reset emails? is the toggle idempotent under double-click?) - both folded back and settled from R2/R4 evidence; anti-gaming pass found no gameable criterion (the revocation and login checks run against live sessions and the real endpoint, not test doubles) - then `build_contract_tested` was set. The exit-check line closed the transcript.
