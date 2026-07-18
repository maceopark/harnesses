# Native subagent evolution protocol

This protocol runs without Orca. Each role is a separate ephemeral `codex exec` process in an isolated temporary directory.

## Information boundaries

| Role | May see | Must not see |
|---|---|---|
| Failure-Lens Proposer | General seed category and fixed handoff goal | Candidate skill, other tools, prior scores, mutations, desired result |
| Lens Auditor / Deduplicator | Proposed lenses and closed acceptance rule | Candidate skill, cases, scores, mutations |
| Lens-Conditioned Case Designer | Frozen lenses, context mode, and audited evidence in repository mode | Candidate skill, Judge output, mutations, another partition's case |
| Repository Discovery | Public repository request and repository files | Candidate skill, private owner oracle, lens evaluation result |
| Evidence Auditor | Sealed discovery and repository files | Candidate skill, private owner oracle, desired result |
| Owner Oracle Designer | Public request, audited evidence, objective failure signals | Candidate skill, transcript, Judge output |
| Interviewer | Candidate skill, public request, transcript | Private oracle, judge output |
| Owner | Private oracle, current question, transcript | Candidate skill, judge output |
| Adversarial Reviewer | Public request, audited evidence, transcript, contract, frozen lenses | Private oracle, candidate lineage, desired finding |
| Judge | Private oracle, completed transcript and contract | Candidate lineage, desired winner |
| Adjudicator | Blind findings, exact cited artifacts, frozen lenses, private oracle | Candidate skill, mutation, preferred fix |
| Mutator | Candidate skill, transcript, judge failure summary, approved findings | Private oracle, raw blind findings, rejected findings, holdout cases |

The coordinator passes role inputs only through versioned JSON artifacts. A process is not given another role's private working-directory path.

This is logical context isolation, not an adversarial operating-system security boundary. `codex exec --sandbox read-only` prevents mutation but may permit broader host reads depending on the local Codex sandbox implementation. Evaluation integrity therefore relies on fresh temporary working directories, minimal prompts, omitted paths, artifact scans, and non-adversarial role instructions. Use containers or another OS-level read-deny boundary if protection against a deliberately probing role is required.

## One development run

1. Failure-Lens Proposer creates solution-neutral, externally observable failure lenses from a general seed.
2. Lens Auditor dispositions every proposal, rejects duplicates and tool-dependent or unobservable claims, and freezes at least one accepted lens. The coordinator writes `lens-set.json` and its digest before case generation.
3. Repository mode runs Discovery and Evidence Auditor against the supplied public request; greenfield mode has no repository evidence stage.
4. Lens-Conditioned Case Designer creates an objectively judgeable case without seeing the candidate. In repository mode it receives the audited evidence, must preserve the supplied public request byte-for-byte, and may not create the private oracle; Owner Oracle Designer then creates only the latent owner decisions. Greenfield mode receives its oracle from the case designer.
5. A fresh Interviewer process proposes one question or closes with a contract.
6. A fresh Owner process answers only that question from the oracle. Steps 5–6 repeat while material decisions remain open and progress continues.
7. A blind Adversarial Reviewer cites exact JSON pointers and values from the public handoff artifacts for every proposed blocker.
8. A fresh Judge scores the observed transcript and contract. A separate oracle-aware Adjudicator dispositions every blind finding.
9. In development only, a fresh Mutator receives the skill, transcript, Judge failure summary, and only adjudicator-approved findings—not the oracle or rejected/raw findings—and writes one candidate revision.

Every role above is a separate ephemeral `codex exec` process. LLM general knowledge is therefore routed through `possible failure -> observable test -> observed finding -> independent adjudication -> smallest mutation`; proposed good practice is never copied directly into the skill.

## Evidence

Every run directory preserves role prompts by digest, raw structured outputs, the frozen lens set, transcript, blind review, adjudication, evaluation, candidate skill, and manifest. All role outputs use closed JSON schemas. A run is invalid if a role times out, returns malformed JSON, violates a role boundary, leaves a proposed lens/finding/conflict undispositioned, cites a value that does not exactly match its artifact, or falsely claims readiness during forced closure. Stagnation and the safety ceiling produce explicit non-ready contracts rather than normal completion.

Development results may guide mutation. Holdout mode never invokes the Mutator. A shared study registry records seed, public-request, frozen-lens-set, lens-conditioned-case, and full-case digests; the harness fails closed if a holdout identity overlaps a development run in either direction. This intentionally requires a separate lens set and case for holdout. Identity is reserved under a POSIX file lock before interviewing and marked complete under the same lock, preventing parallel runs from passing the same stale registry snapshot. Failed runs retain a reservation and require explicit review. This is harness-enforced lineage sealing, not filesystem confidentiality: an operator can still bypass it by deleting the registry or manually copying artifacts.

## Repository ground truth

Repository mode adds two read-only roles before the interview:

1. Discovery cites exact repository-relative paths and line bounds for every claimed fact.
2. Evidence Auditor independently re-opens those files and rejects unsupported or overstated facts.

Only the audited evidence pack reaches the Interviewer. Product choices that cannot be discovered from the repository live in a separate private Owner oracle. The implementing contract must reconcile both sources without asking the Owner to repeat discoverable facts.

## Adaptive termination

The Interviewer reports its current open material decisions on every turn. Normal completion occurs only when it returns a contract; an implementation-ready contract must have no open material decisions. Repeating both the same open-decision set and the same question triggers stagnation closure; different questions may continue resolving different aspects of one decision. `--safety-max-turns` defaults to 30 and is only a runaway guard, not a target or normal stopping rule. Reaching stagnation or the safety ceiling forces a non-ready contract so confirmed evidence is preserved.

## Run

Development mode invokes all five roles and emits a candidate:

```bash
python3 requirements-interview-evolution/native-evolution/run_evolution.py \
  --mode development \
  --seed "a compact ambiguous software task" \
  --skill requirements-interview-evolution/clarify-requirements/SKILL.md \
  --run-dir requirements-interview-evolution/native-evolution/runs/dev-001
```

Holdout mode omits the Mutator by construction:

```bash
python3 requirements-interview-evolution/native-evolution/run_evolution.py \
  --mode holdout \
  --seed "a new task not used during mutation" \
  --skill requirements-interview-evolution/clarify-requirements/SKILL.md \
  --run-dir requirements-interview-evolution/native-evolution/runs/holdout-001
```

Repository mode:

```bash
python3 requirements-interview-evolution/native-evolution/run_evolution.py \
  --context repository \
  --repo /absolute/path/to/repository \
  --mode development \
  --seed "the requested brownfield change" \
  --skill requirements-interview-evolution/clarify-requirements/SKILL.md \
  --run-dir requirements-interview-evolution/native-evolution/runs/repo-dev-001
```

Each `codex exec` call is ephemeral, read-only, ignores user configuration, and runs in a new temporary directory. Only Discovery and Evidence Auditor are explicitly given the repository path and `--add-dir`; this is not a hard OS read-deny guarantee for other roles. Authentication still comes from the local Codex installation. Use `--model` to pin a model and `--timeout` to change the per-role limit.

Use one explicit registry for a study:

```bash
--study-registry requirements-interview-evolution/native-evolution/runs/study-registry.json
```

Repository citations are sealed by the coordinator with the exact quoted text, a quote digest, cited-file digests, and Git HEAD/status digests when the target is a Git repository. The auditor must accept or reject every discovered fact and may not silently discard a reported conflict.
