---
name: ultimateinterview-postmortem
description: Independent spec-versus-implementation retrospective for Ultimateinterview sessions. Use after implementation of a sealed Build Contract to measure material requirement misses, invented behavior, implementation divergence, handoff synthesis loss, and verification gaps, and to propose only small evidence-backed improvements.
---

# Ultimateinterview Postmortem

Compare the sealed Build Contract with the implementation and attribute each material difference to the earliest mechanism that could have prevented it. Evaluate the v3 lineage `observed evidence -> material decision -> execution contract -> acceptance/verification -> implementation`; do not turn the retrospective into another discovery protocol.

## Preconditions and Evidence Boundary

Read `../ultimateinterview/references/json-contracts.md`. Require a repository-local `.ultimateinterview/<session>/` containing a valid `build-contract.json`, `discovery-record.json`, and `authority-register.json`. New v3 sessions also require `execution-contract.md` with its deterministic DEC manifest; legacy compiler-only sessions remain auditable when it is absent. Treat `evidence-map.md` as preferred v3 lineage evidence when present. Never fabricate missing `decision.jsonl`.

The sealed Build Contract is the sole normative source. The evidence map, Discovery Record, repository state, tests, decision log, prior conversation, and reviewer output are evidence only. Evidence may reveal an unexplained mismatch but cannot authorize product behavior.

Require substantially complete implementation evidence: a merged PR, commit range, branch diff, or unambiguous working tree. Run from this skill directory:

```text
python3 scripts/compiler_session_check.py <session-dir> [--diff-range <range> | --diff-file <path>]
```

This must verify the sealed digest, recompile the Discovery Record against the Authority Register, run the deterministic projection gate whenever `execution-contract.md` is present, validate the decision log when present, scope the repository evidence, and regenerate `compiler-evidence-bundle.json`. Stop on failure. A legacy session with no execution contract records a null projection result; an execution contract that is present but lacks or fails the manifest is invalid, never silently downgraded to legacy.

The evaluator should be independent of the interview and implementation. If it participated in either and a fresh evaluator cannot be used, disclose the limitation and do not claim an independent result. Do not add a panel or iterative reviewer loop.

## Bounded Audit

Walk the evidence in both directions:

- each Build Contract requirement -> implementation location and directly observed verification evidence;
- each substantive implementation behavior -> an authorized requirement, acceptance predicate, or bounded delegation;
- each evidence-map fact -> preserved, explicitly superseded by authority, intentionally excluded, or lost before sealing;
- each material owner decision -> corresponding contract behavior and acceptance;
- each verification -> exact execution context and honest `passed`, `failed`, `blocked`, or `not-run` result.

Internal choices that remain within bounded delegation are authorized variation, not findings. Formatting, renames, comments, and other non-substantive differences are out of scope.

Classify contract and implementation outcomes using the existing report classes:

- `fulfilled` — contracted and implemented;
- `escaped-requirement` — material implemented behavior absent from the contract and not delegated;
- `scope-drift` — contracted behavior missing without an authorized deferral;
- `divergent-implementation` — implementation contradicts the contract or crosses an authority boundary;
- `deferred-outcome` — explicitly deferred by the contract; or
- `unverifiable` — the result cannot be established from direct evidence.

For every non-fulfilled item, assign one earliest root cause:

- `discovery-miss` — a material behavior was absent from both the compact observed evidence and the contract;
- `decision-miss` — observed evidence exposed a material fork, but the required authority was not obtained or observable behavior was defaulted without delegation;
- `handoff-loss` — observed evidence or an authorized decision was captured but omitted, narrowed, contradicted, or made unverifiable in the execution or sealed contract;
- `contract-defect` — the sealed contract is internally contradictory, materially underdetermined outside delegation, or has unverifiable acceptance;
- `implementation-drift` — the contract was adequate but implementation departed from it;
- `verification-gap` — contract or implementation evidence is insufficient to establish the result.

Do not blame the one-time Fresh Handoff Check for `discovery-miss`; its inputs cannot reveal facts the interviewer never observed. Use `handoff-loss` only for lineage already present in the evidence map, owner decisions, or compiler inputs. A current repository behavior intentionally superseded by valid authority is not an evidence-contract mismatch.

## Improvement Proposals

Draft at most one proposal per distinct root cause and no more than three total. A proposal must be:

- **simple** — one short rule or bounded deterministic check, with no new role, score, artifact family, or mandatory ceremony;
- **effective** — names the finding it would have prevented and the exact stage where it acts;
- **general** — applies across repositories rather than encoding the audited product; and
- **compatible** — strengthens the current Material Interview without duplicating or expanding it.

Zero proposals is valid. Do not recommend a skill change when the rule already exists and the failure was noncompliance. Proposals are evaluator evidence, not authority, and this skill never edits either skill automatically.

## Output and Validation

Use `references/postmortem-template.md` and write `.ultimateinterview/<session>/postmortem.md`. Keep the report conclusion-first and evidence-minimal:

1. mechanical counts and verdict;
2. implementation evidence;
3. one divergence row per requirement plus each unmatched substantive behavior;
4. details only for non-fulfilled items, including the v3 root cause;
5. one row per verification; and
6. process gaps, missing evidence, and any owner action.

The template retains a `Lessons` table for schema compatibility. Leave it empty unless the user separately requested a durable lesson-store update; do not create routing lenses or mutate lesson stores by default.

Validate the report and then recheck the compiler session:

```text
python3 scripts/postmortem_report_check.py <session-dir>/postmortem.md --bundle <session-dir>/compiler-evidence-bundle.json
python3 scripts/compiler_session_check.py <session-dir> [same diff arguments]
```

Verify that Conclusion counts equal the Divergence Table. If implementation reversed an owner decision, flag it for re-confirmation. Do not modify the sealed contract, Discovery Record, implementation, or either skill from inside a postmortem.
