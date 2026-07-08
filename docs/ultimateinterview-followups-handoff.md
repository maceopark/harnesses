# Ultimateinterview — Deferred Follow-ups Handoff

Two follow-ups were deliberately deferred from the 2026-07-07 agent-council round (commits `6effa51`, `7c155eb` on `master`). This doc is self-contained so a fresh session — possibly a different model, definitely without this conversation — can pick either up cold.

## Orientation (read first, both tasks)

- **Canonical tree, edit here only:** `/.agents/skills/{ultimateinterview,ultimateinterview-postmortem}/`. Every other path (`~/.claude/skills/…`, `~/.agents/skills/…`, repo `.claude/skills/…`) is a **symlink into this tree**. Editing any of them edits the same inodes.
- **Symlink hazard:** `diff -rq` between two of these paths is a tautology (same files) — check inodes (`ls -di`) before treating copies as duplicates. An `rm -rf` through the `.claude/skills` path once deleted the only real tree (recovered via `git restore .agents/skills`). Do not "clean up duplicates."
- **Run tests from the skill dir** (each test file has a `__main__` pytest entry + a `sys.path` fix; `uv run pytest <file>` fails on old default interpreters because uv ignores inline script metadata when `pytest` is the command):
  ```bash
  cd .agents/skills/ultimateinterview        && uv run scripts/test_deterministic_helpers.py   # 145
  cd .agents/skills/ultimateinterview        && uv run scripts/test_verification_lint.py       # 9
  cd .agents/skills/ultimateinterview-postmortem && uv run scripts/test_pack_evidence.py       # 27
  cd .agents/skills/ultimateinterview-postmortem && uv run scripts/test_postmortem_lint.py     # 17
  ```
  Baseline at handoff time: **198 tests green**.
- **The closed loop, one line:** `ultimateinterview` (interview → spec/handoff) → executor builds → `ultimateinterview-postmortem` (spec-vs-code audit → discovery rate → lessons feed back into the next interview). Full guide: `docs/ultimateinterview-closed-loop-guide.md`.
- **Working-state caveat:** interview sessions live in `.ultimateinterview/<slug>/` which is **gitignored**. Prior postmortems, ledgers, and `evidence_bundle.json` exist locally but are NOT in a fresh checkout. The durable record is: this doc, the committed lessons stores (`docs/ultimateinterview-lessons.md` + `.agents/skills/ultimateinterview/lessons.md`), and the memory note `ultimateinterview-skill-design.md` (rounds 15–16).

---

## Task 1 — Trim interview `SKILL.md` below ~17k

### Why
`SKILL.md` is the hot-path runtime state machine; the standing discipline (from the round-7 hot-path split) is **≤ ~17k bytes**, with new prose offset by trims. It has drifted over:

- current: **`.agents/skills/ultimateinterview/SKILL.md` = 18,591 bytes** (`wc -c`)
- target: **≤ ~17,000 bytes** (need to cut ~1,600)
- the 2026-07-07 session already took the safe compressions (subagent-naming clause, `verification_lint` helper line, budget-costing list → pointer to `state-files.md`), bringing it 19,097 → 18,591. The remaining ~1,600 is the hard part.

### The constraint that makes this non-trivial
Every rule in this file was added deliberately and **survived a round-7 adversarial rule-diff** (3 parallel agents: rule-diff over ~190 rules, cold-start 8-scenario executability, cross-file consistency incl. postmortem coupling + frontmatter parity). Cutting 1,600 bytes by hand risks silently dropping a load-bearing rule. Do **not** hit the number by gutting content.

Specifically off-limits without a replacement:
- The ENDGAME enter-condition inlines the full readiness-gate trigger list on purpose — round-7 moved it INTO the cell for cold-start executability. Do not re-pointer it away.
- The `frontmatter` `description` is byte-tuned for skill triggering — keep it byte-identical.

### Recommended method (mirror round-7)
1. Back up the current file (scratchpad, not committed).
2. Draft the trim: prefer moving *per-moment method detail* into the phase `references/` (that's where it belongs) and leaving only *routing + invariants* in `SKILL.md`. Look for prose that restates a reference rather than routing to it.
3. **Verify with the round-7 adversarial trio** (fresh-context subagents, `agent: critic`):
   - rule-diff: enumerate every rule in the OLD file, confirm each survives in NEW-file-plus-references (nothing silently dropped);
   - cold-start executability: can an agent run each phase from NEW SKILL.md + the reference it points to?
   - cross-file consistency: SKILL.md ↔ references ↔ `ultimateinterview-postmortem` coupling still coherent.
4. Regenerate `references/example-session.md` dashboards only if any semantics changed (it is regression-checked REAL `session_status.py` output — keep it byte-consistent).
5. Tests stay green (the 4 suites above). SKILL.md changes are prose, so tests won't catch a dropped rule — the adversarial trio is the real gate.

### Acceptance
- `wc -c .agents/skills/ultimateinterview/SKILL.md` ≤ ~17,000.
- Adversarial rule-diff finds zero dropped rules.
- 198 tests still green; `protocol_state.py` / `session_status.py` still parse example-session.
- Frontmatter `description` unchanged.

---

## Task 2 — Discovery-rate regression harness for interview-rule changes

### The problem
The closed-loop guide has one hard rule before editing the interview skill (`docs/ultimateinterview-closed-loop-guide.md`, §"One rule before editing the skill itself"):

> Rerun the previously measured cases, compare discovery rates before/after, and patch only what measurably improved.

The 2026-07-07 round changed **interview rules** (new lens triggers + gates) but could **not** honor this rule, so those changes shipped labeled **"experimental / unproven"**. They must either be validated or stay flagged. The unproven changes:

- `controlled-language` **predicate gate** — "invalid/malformed/corrupt X" must name its deciding predicate (orientation trigger + behavior-contract rule + audit-checklist gate).
- `misuse` trigger on **free-text/user-supplied input** (orientation + lenses §6 + input-surface gate).
- `domain/state` trigger on **temporal words** (orientation + lenses §4 boundary walk).
- **store-trust** conditional gate (audit-checklists), and the three `1/1` store lessons in staging (`.agents/skills/ultimateinterview/lessons.md`).
- **version-floor** constraint rule (handoff-sequence).
- `verification_lint.py` as a pre-handoff gate.

### Why it's hard (be honest about this)
"Discovery rate" is a property of the **postmortem** (spec-vs-code), computed as `fulfilled / (fulfilled + escaped + divergent)` over the divergence table. It depends on the SPEC, and the interview-rule changes change what the spec *contains* (they make lenses fire earlier). So a true before/after needs: re-run the interview with the new rules → new spec → re-implement → re-postmortem → compare. That is a full human-in-the-loop cycle per case. There is no replay harness today.

### Split the work — the two halves have very different cost
1. **Tooling regression (cheap, mostly scripted already).** Run every script against every prior session and assert no crash + expected pass/fail. The 2026-07-07 session did this by hand and found a real defect (`verification_lint` false-positives on prose cells, since fixed). Automate it:
   - prior sessions with artifacts: `.ultimateinterview/{todo-cli-app, todo-cli-app-2, todo-cli-app-3, todo-cli-app-4, todo-cli-app-5}/` (handoff + ledger; app-5 also has diff + postmortem). NOTE these are gitignored — a fresh checkout won't have them; they live on the 2026-07-07 machine. Either run there, or capture a fixture set into the test tree.
   - assert: `handoff_coverage`, `verification_lint` (advisory), `postmortem_lint` run without crashing; document expected verdicts (e.g. old reports predate the `postmortem_lint` contract and legitimately fail its section checks — that's expected, not a regression).
2. **Interview-rule regression (the open design problem).** Options, cheapest first:
   - **(a) Signal-firing check (recommended starting point).** For each prior session's original request text + repo state, deterministically check whether the new orientation triggers fire the intended lens. This is static (no re-interview, no re-build) and directly tests "would the new rule have activated on this input?" It won't prove the escape gets caught, but a trigger that *doesn't* fire on a request whose escape it targets is a measurable regression. Could be a small script over the lessons/trigger signals + the request text.
   - **(b) Transcript replay.** `.ultimateinterview/<slug>/transcript.md` records the Q&A. Replay a prior transcript against the updated skill and diff which lenses/questions fire earlier. Needs the skill to be drivable programmatically against a recorded transcript — larger effort.
   - **(c) Blind-rebuild experiment.** The full manual protocol the user already runs (re-elicit "the same" app blind, compare specs + code). Highest fidelity, highest cost; this is the only path that produces a real before/after discovery rate. Reserve for high-stakes rule changes.

### Acceptance (scope to what's affordable)
- At minimum: a scripted **tooling-regression** check (half 1) that a future skill edit can run in one command, plus a documented fixture set so it survives a fresh checkout.
- Stretch: a **signal-firing check** (half 2a) that, given a request + the current triggers, reports which lenses would fire — enough to catch a trigger that stopped firing.
- Until (c) is run for a given rule change, keep that change labeled experimental in the memory note and do not claim a discovery-rate improvement.

---

## Pointers
- Memory note (the full round-by-round history incl. the council review that produced these follow-ups): `ultimateinterview-skill-design.md` rounds 15–16.
- Closed-loop user guide: `docs/ultimateinterview-closed-loop-guide.md`.
- Report/lint templates: `.agents/skills/ultimateinterview-postmortem/references/{postmortem-template.md, evidence-bundle.md}`.
- Scripts owning the deterministic contracts: `.agents/skills/ultimateinterview/scripts/{session_status,protocol_state,handoff_coverage,verification_lint,lessons}.py`, `.agents/skills/ultimateinterview-postmortem/scripts/{pack_evidence,postmortem_lint}.py`.
