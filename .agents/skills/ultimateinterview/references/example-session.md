# Worked Example: One Complete Session

A synthetic but fully executed `focused` interview, kept small on purpose. Every dashboard below is real output from the helper scripts run against the files shown - nothing is mocked. Pattern-match against this when unsure what a step's artifacts should look like. (This session exercises the current mechanics: stakes calibration, `pending` lens state, origin instrumentation, obligation precedence (`due_now_corrections`), checkpoint lens re-flip, the combined `session_status.py` final dashboards, and the exit check.)

> Vintage note: this rehearsal predates typed-event bookkeeping, so its deltas set protocol counters manually. In a live session that pattern is now forbidden - pass `event` (and `transcript`/`checkpoint_confirm`) in the delta and let the script compute the counters (`references/state-files.md` §Typed events). The dashboards and file shapes shown remain accurate.

## Epistemic hardening rehearsal

This compact rehearsal shows the hidden methodology layer without adding visible protocol ceremony:

- ORIENT records two candidate readings in ordinary reasons: `deficit=boundary-undefined` for "which sessions die?" and `deficit=execution-blind` for "what proves the handoff is safe to execute?", each with `reverse-evidence=<specific repo fact or user correction that would make the reading unnecessary>`.
- The `domain/state` lens fires with `reverse-evidence=repo already has one deactivation lifecycle covering sessions/tokens`; once settled, its typed artifact is `StateModel`.
- The `misuse` lens records `MisuseCaseSet` for compromised-account and accidental-lockout cases, while `controlled-language` records `ControlledAcceptanceCriteria` for the command/test predicates.
- The checkpoint stays recognition-style: "Current model - correct only what is wrong" includes one hidden-reading line ("Execution risk is stop-time-checkable except permission prompts; wrong if destructive commands are needed before verification"). The user corrects lines rather than selecting a protocol.
- The Build Contract includes a `Guardrail Compile` table: a stop-time predicate (`uv run scripts/test_deterministic_helpers.py` exits 0), an accepted residual (discovery-rate improvement needs a later postmortem), and a fast/pre-action risk (destructive command blocking belongs to the harness permission substrate).

The visible user path is still brain dump, dashboard, highest-leverage question, checkpoint, handoff. No prompt asks for `/probe`, `/attend`, protocol names, or methodology labels.

Fresh-implementer proof for this hardening change:

| Part 1 only review question | Result | Re-bound evidence |
| --- | --- | --- |
| What would a fresh implementer still need to ask before applying this method? | Nothing blocking for the no-schema path: storage location is existing `ledger.reason`, `ledger.origin`, and `lenses.<name>.reason`; structured `questions.json` fields remain out of scope unless scripts/tests change. | `references/state-files.md` hidden-tag conventions plus helper tests. |
| Which criterion could be gamed without the behavior? | A grep-only check could find `deficit=` and `Guardrail Compile` without proving the flow stays low-friction. | This rehearsal binds the terms to the actual user path, and helper tests/protocol-state smoke prove schema compatibility. |
| Does `SKILL.md` need method detail? | No; it needs only routing-level protection that the method is hidden. | `SKILL.md` Core Rule points to the reference files and forbids user protocol choice. |

Guardrail Compile inventory for the rehearsal:

| Risk | Class | Predicate / residual / substrate owner | Evidence |
| --- | --- | --- | --- |
| Hidden tags accidentally loosen helper schemas. | Stop-time predicate | `uv run scripts/test_deterministic_helpers.py` and `uv run scripts/protocol_state.py --format markdown scripts/regression_fixtures/todo-cli-app-5/protocol.json` both exit 0. | Helper/schema compatibility remains executable. |
| Discovery-rate improvement cannot be proven by static docs alone. | Accepted residual | owner: requester; decision date: after first real postmortem; mitigation: run `ultimateinterview-postmortem` on the next implementation seeded by this hardened method. | This is outcome measurement, not an implementer precondition. |
| Destructive command blocking, permission prompts, and agent/tool prompt-injection interception. | Fast/pre-action | substrate: harness permission system and tool-level approvals; do not simulate as stop-time predicates. Product-level prompt injection remains a misuse/security requirement when the product consumes untrusted text. | Guardrail compile surfaces harness-owned pre-action risk without hiding product security controls. |

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
  decision date: 2026-10-01, origin: sweep). This is `new-gaps`, so the dry streak resets.
- [sweep: from-ledger] first follow-up sweep: no new gap (`dry`, streak 1).
- [sweep: from-ledger] second follow-up sweep: no new gap (`dry`, streak 2).
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
  dump 3, pressure 1, batch 3, checkpoint 1, sweep 1 | sweeps: 3 total, 2 dry in a row
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
     "status": "Deferred", "ambiguity_score": 2, "impact_weight": 3,
     "deferred": {"owner": "jpark", "decision_date": "2026-10-01"},
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
  "sweeps_run": 3,
  "dry_sweeps_in_row": 2,
  "contrarian_probes_run": 1,
  "falsification_checkpoints_run": 1,
  "checkpoint_since_last_material_change": true,
  "framing_challenged": true,
  "brain_dump_done": true,
  "build_contract_tested": true,
  "build_contract_digest": "fef6d0a5a59d4c23c6dba47d3f5bb98bade873ab6115d4ef7048af759bcdf52b",
  "build_contract_reviewer": "self-audit:rehearsal",
  "lenses": {
    "viewpoint": {"state": "done", "artifact": "ViewpointMatrix", "reason": "admin/user/support/security viewpoints covered; reverse-evidence cleared by checkpoint"},
    "domain/state": {"state": "done", "artifact": "StateModel", "reason": "active/inactive lifecycle, revocation events, and illegal transitions settled"},
    "goal/obstacle": {"state": "done", "artifact": "GoalObstacleMap", "reason": "reversible no-delete deactivation goal and revocation obstacles settled"},
    "misuse": {"state": "done", "artifact": "MisuseCaseSet", "reason": "unauthorized/reactivated access and accidental bulk-action paths enumerated"},
    "quality": {"state": "skipped", "reason": "UI toggle; no architecture-significant quality attribute survived the controlled-language pass"},
    "controlled-language": {"state": "done", "artifact": "ControlledAcceptanceCriteria", "reason": "revocation, login rejection, reactivation, and audit predicates written"}
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

- interview_converged: yes (stop condition met: handoff_ready, and protocol blockers empty or only the build contract; run the Handoff sequence this turn)
```

The combined runner reported convergence. After the contract was drafted, reviewed, and digest-bound, `session_status.py --gate` returned `implementation_ready: yes` in the same turn.

# Part 1 — Build Contract

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

## Goal

An admin can deactivate and reactivate one user reversibly; deactivation revokes all access without deleting data. (source: R1, R2, R3, N1)

## Target Surface

| File / module | Expected change |
| --- | --- |
| user migration and model | add `users.is_active`, default true |
| auth and token services | reject inactive login and revoke session/API/refresh credentials atomically |
| admin route and UI | add single-user toggle, grey inactive rows, show Deactivated chip |
| audit log | record deactivate/reactivate rows |

## Behavior Contract

| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source |
| --- | --- | --- | --- |
| REQ-001 | Deactivation revokes every credential atomically. | When deactivation commits, the current browser session, API token, and refresh token all fail on their first subsequent request. | R1, R2 |
| REQ-002 | Inactive users cannot log in, but reactivation restores login without reset or expiry. | While inactive login returns the existing generic failure; after reactivation the same password works, with no password reset and no auto-expiry. | R1, R3 |
| REQ-003 | Support can find inactive users. | When an inactive user appears in the admin list, the row remains present, is greyed, and carries the Deactivated status chip. | R7 |
| REQ-004 | Every flip is auditable and single-user only. | Each deactivate/reactivate action writes one `audit_log` row and no bulk operation is exposed. | R4, D1 |
| REQ-005 | Existing UI vocabulary is reused. | The toggle remains in the user-detail danger zone and uses the existing status-chip vocabulary. | R5, R6 |

## Change Impact & Preservation

| Source | Current evidence / behavior | Preserved invariant | Target difference | Code surface | Acceptance check | Runtime signal |
| --- | --- | --- | --- | --- | --- | --- |
| F1, F2, R1, R2, R3 | current auth loads a user before issuing credentials and `revoke_all` already exists | generic login failure and password remain unchanged | inactive state gates issuance and revokes existing credentials | auth/token services | REQ-001, REQ-002 | all three live credential probes fail after commit |
| R4, R5, R6, R7 | admin detail/list and audit patterns already exist | list discoverability and UI vocabulary remain | add toggle, status presentation, and two audit actions | admin API/UI/audit log | REQ-003, REQ-004, REQ-005 | list row and audit rows are observable |
| N1 | user data is retained today | user record and related data remain | only `is_active` changes | migration/model | negative deletion assertion | row counts and user data remain unchanged |

## Quality Bars

| Attribute | Bar (a number an implementer can verify) | Weight | Verification |
| --- | --- | --- | --- |
| Revocation freshness | 0 successful grace requests after the deactivation transaction commits | 5 | live credential surface row below |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| exact migration helper, route shape, and CSS implementation | yes | must preserve every observable in REQ-001 through REQ-005 |
| meaning of inactive, retained data, revocation set, or auto-expiry | no | use the settled requirements; log any forced deviation |

## Out Of Scope / Non-Goals

- No deletion or purge (source: N1) — negative: user row and related records remain after both flips.
- No bulk deactivate (source: D1) — negative: no bulk endpoint, command, or UI control exists.
- No auto-expiry (source: R3) — negative: elapsed time alone never reactivates a user.

## Implementation Constraints

- Interfaces: preserve the current generic login failure and admin status vocabulary.
- Compatibility: existing users migrate as active; existing clients keep their current fields.
- Migration: backfill occurs through the default-true column migration.
- Decision core: `(current_state, requested_flip, credential_set) -> next_state + revocation set + audit action`.
- Effects boundary: one transaction changes the user state, revokes session/API/refresh credentials, and writes the audit row; rollback leaves all unchanged.

## Rollout & Recovery

| Activation | Compatibility / backfill | Rollback trigger | Rollback action | Observation metric + window | Owner |
| --- | --- | --- | --- | --- | --- |
| deploy migration, API, then UI in one release | existing users default active; old clients ignore presentation | any credential remains usable after commit or active login regresses | disable UI/route and roll back application; retain compatible column | credential-probe failures and login error rate for 24 hours | service owner |

## Guardrail Compile

| Risk | Class | Predicate / residual / substrate owner | Evidence |
| --- | --- | --- | --- |
| stale credential survives | Stop-time predicate | live session, API token, and refresh token all fail on first request after commit | REQ-001 surface command |
| future notification-policy change | Accepted residual | owner: service owner; decision date: next notification change; mitigation: open a new interview | R2/R4 scope |
| destructive execution or harness prompt injection | Fast/pre-action | substrate: permission system and tool guard | no product-level control is claimed |

## Verification Commands

| Check | Kind | Command / action | Pass condition |
| --- | --- | --- | --- |
| REQ-001 through REQ-005 unit/integration | test | `uv run pytest tests/test_admin_user_deactivation.py -q` | all named REQ tests pass |
| REQ-001 live credential traversal | real-surface | `uv run pytest tests/test_admin_user_deactivation.py -q -m live_surface` | installed service flow revokes all three credentials and preserves the user row |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| D1 bulk deactivate for compromise waves | jpark | 2026-10-01 | no bulk surface is built; reopen after the first real incident |

## Fresh-Implementer Test

| Reviewer (fresh-context agent / self-audit) | "Would have to ask" items found | Gameable criteria found | Folded back / re-bound? | Unresolved after disposition |
| --- | --- | --- | --- | --- |
| self-audit:rehearsal | password-reset email and double-click idempotency | credential checks could target doubles | settled from R2/R4; verification rebound to installed service and live credentials | none |

# Part 2 — Audit Trail

Fresh-implementer evidence is bound to the Part-1 digest in `protocol.json`; the exit-check line closed the transcript.
