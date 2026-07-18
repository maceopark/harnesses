# Clean-room evolution record

## Boundary

This folder was designed and evaluated without using other interview skills, repository benchmarks, corpora, experiment results, or prior evaluation conclusions. The only external input used was the generic Codex skill packaging contract. All scenarios, decision labels, scoring rules, candidate versions, and stopping criteria in this folder were created from first principles.

## Goal and measures

The target is a small skill that surfaces consequential ambiguity without inventing requirements or exhausting the user with low-value questions.

The executable proxy awards:

- 60 points for material-decision recall;
- 10 each for one-decision-per-turn interaction, closure reflection, scenario challenge, and an implementation-authorization boundary;
- penalties for invented decisions and questions beyond the case budget.

This proxy checks whether each version's rules cover a scenario. The run files are explicit manual rule-to-scenario walkthroughs, not claims of independent LLM execution. They make the reasoning reproducible but cannot prove model-level behavioral reliability.

## Evolution

| Version | Bytes | Mean | Questions | Change | Why |
|---|---:|---:|---:|---|---|
| v0 | 237 | 22.67 | 6 | Ask for desired result and success | Smallest viable seed; establishes the failure baseline. |
| v1 | 442 | 67.00 | 41 | Add a broad ambiguity checklist and approval | Fixed severe decision omissions, but batched and over-questioned low-risk work. |
| v2 | 992 | 90.00 | 30 | Add materiality, decision state, prioritization, one-at-a-time flow, and stop rule | Preserved recall while reducing burden and preventing silent consequential defaults. |
| v3 | 3250 | 100.00 | 30 | Add misuse/failure challenge, evidence labels, bounded recommendations, and explicit authorization | Closed the remaining proxy gap: a coherent contract could still fail on failure or misuse paths, or be mistaken for implementation approval. |
| v4 | 5522 | runtime finding | 16 in one Todo interview | Prefer structured runtime questions, bundle low-risk defaults, autonomously judge readiness, emit a JSON Build Contract, require gap decisions in `decision.jsonl`, and print a start prompt | The first real interview reached an implementable contract but asked many low-risk questions individually and did not initially produce an implementation-ready machine-readable handoff. |

The post-freeze holdout contains notification-preference and concurrent-edit requests. The frozen v3 rule walkthrough scored 100.00 with no invented decisions.

## First real-interview correction

The v3 proxy ceiling did not predict interaction efficiency. In the first real clean-room Todo CLI interview, v3 asked 16 sequential questions. The resulting contract was implementable, but choices such as language, ID style, sort order, output style, storage location, packaging surface, and concurrency posture could have been proposed as a reversible default bundle. The runtime also offered a structured question surface that the skill did not explicitly require, and the close procedure lacked a machine-readable handoff.

This observation reopened evolution and produced v4. It is evidence that the earlier stopping claim applied only to the static proxy, not real interview behavior. v4 must now be judged through subsequent real interviews; no new universal convergence claim is made here.

## Native subagent evidence

The non-Orca runner under `native-evolution/` now separates Case Designer, Interviewer, Owner, Judge, and Mutator into independent ephemeral Codex processes. Its first real development run is `native-evolution/runs/greeting-v4-smoke-2/`.

The run completed 13 role calls. The Judge observed five questions, 0.8333 material-decision recall, no invented requirements, and no unnecessary questions. It rejected implementation readiness because the five-turn limit prevented contract synthesis and character-repertoire behavior remained open. The Mutator proposed a candidate addressing turn-budget reservation and explicit Unicode policy. That candidate is preserved as evidence but is not adopted from a single development case.

The prior `greeting-v4-smoke/` attempt stopped on an invalid strict output schema. It remains a failed harness run and did not contribute skill-quality evidence.

The first repository-grounded run is `native-evolution/runs/greeting-repo-v4/`. Discovery cited eight facts across code, tests, and documentation; an independent Evidence Auditor re-opened and accepted all eight. The adaptive interview closed normally after three Owner questions rather than at a fixed turn count. The Judge rejected the resulting contract with repository fidelity 0.86 and Owner-decision recall 0.83 because it invented unknown-option rejection and an internal placement constraint. This demonstrates that repository evidence and latent Owner decisions independently affected the verdict. The generated candidate remains unadopted pending replication and holdout evaluation.

The current harness was then hardened after independent review: exact citation text and digests are coordinator-sealed, every fact and conflict requires an explicit auditor disposition, forced closure cannot claim readiness, and a shared study registry rejects development/holdout identity overlap. Registry identities are reserved and completed under a POSIX file lock so parallel runs cannot both pass a stale snapshot. Logical prompt/work-directory isolation is explicitly distinguished from OS-level read-deny isolation.

The first hardened repository holdout is `native-evolution/runs/greeting-repo-v4-holdout-2/`. It closed normally after six questions with repository fidelity 1.00 and Owner-decision recall 0.86. The Judge rejected implementation readiness because strict base-10 parsing, rejection of `--count=N`, and prohibited alternate input surfaces were not fully sealed; it also identified invented documentation/test mandates. Holdout mode emitted no candidate and invoked no Mutator. These results are final-evaluation evidence only and are not mutation input.

The preceding `greeting-repo-v4-holdout/` attempt failed closed because the first conflict-disposition contract could not represent an auditor-resolved conflict. The schema now requires every conflict to be explicitly resolved with a reason or retained as unresolved; the failed attempt is harness evidence only.

## Failure-lens evolution evidence

The v3 native runner now discovers evaluation axes before designing a case. A fresh Failure-Lens Proposer emits three to five solution-neutral observable failures; a separate Lens Auditor dispositions every proposal and freezes the accepted set before case generation. A blind Adversarial Reviewer may cite only exact public-artifact values, and an oracle-aware Adjudicator must disposition every proposed finding before any finding can reach the Mutator. Development and holdout registry identities now include the frozen lens-set and lens-conditioned-case digests. Holdout cannot reuse either partition identity and never invokes the Mutator.

The completed development cell is `native-evolution/runs/greeting-capitalization-lens-v3-dev/`. It generated five distinct discovery, interaction, synthesis, handoff, and verification lenses; the interview closed after one question with repository fidelity 1.00 and owner-decision recall 0.96. Blind review found no material blocker, adjudication had no finding to approve, and the emitted candidate was byte-identical to deployed v4. This is evidence that the discovered lenses were testable, not evidence that an unobserved good idea should be added to the skill.

The completed, separately sealed holdout is `native-evolution/runs/greeting-farewell-lens-v3-holdout/`. It generated four different discovery, interaction, synthesis, and verification lenses, invoked no Mutator, and completed with repository fidelity 1.00 and owner-decision recall 0.90. The final contract was implementation-ready, but the Judge identified one unnecessary question that reopened an already answered decision and briefly introduced a conflicting recommended variant. Because this was holdout evidence, the finding was not mutation input and no candidate was emitted.

Failed development and holdout cells are preserved rather than rewritten or reported as wins. They exposed harness-contract defects in accepted-lens projection, reviewer pointer roots, exact string citation handling, forced-close readiness, and role-call timeouts. The coordinator now freezes proposer text by accepted ID, documents artifact-root pointer aliases, permits only exact non-empty substrings for string citations while retaining canonical equality for structured values, and continues to reject readiness during forced closure. The final unit suite covers these fail-closed boundaries. No candidate is promoted to v5 from this evidence.

## Prior stopping decision, superseded by runtime evidence

A hypothetical v4 adding a mandatory domain-by-domain questionnaire was rejected. It introduced no new failure class in the six development cases or two post-freeze cases, could not improve the bounded score above 100, and would increase prompt size and interview burden. The stopping condition is therefore satisfied on this clean-room surface: full proxy coverage, zero invented decisions, no excess questions, post-freeze holdout parity, and no identified change with positive measured benefit.

The Todo interview supplied exactly such a real-world failure, so evolution resumed. Future failures should continue to be captured before changing the skill.

## Reproduce

```bash
python3 -m unittest discover -s requirements-interview-evolution/tests -v
python3 requirements-interview-evolution/eval/score.py requirements-interview-evolution/eval/cases.json requirements-interview-evolution/eval/runs/v3.json
python3 requirements-interview-evolution/eval/score.py requirements-interview-evolution/eval/holdout-cases.json requirements-interview-evolution/eval/runs/v3-holdout.json
uv run --with pyyaml python /Users/jpark/.codex/skills/.system/skill-creator/scripts/quick_validate.py requirements-interview-evolution/clarify-requirements
```
