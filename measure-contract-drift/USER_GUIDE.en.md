# How the Ultimateinterview Contract-Drift Benchmark Works

## Audience

This guide is for software engineers with roughly three years of experience who are comfortable with CLIs, JSON, tests, Docker, and basic hashes, but do not have an ML background.

You do not need to understand model training, embeddings, or statistics to understand this benchmark. The central question is a software-engineering question:

> When requirements pass through an interview and a handoff, how much of the intended behavior survives in a fresh implementation context?

## 1. The problem being measured

A typical agent workflow has several lossy boundaries:

1. A user describes a feature.
2. An interviewer asks clarifying questions.
3. The interview is compiled into `handoff` and Build Contract artifacts.
4. A fresh implementer receives those artifacts but not the interview conversation.
5. The implementation is tested against observable behavior.

Information can drift at every boundary. A requirement may be omitted, weakened, contradicted, or implemented with the wrong edge-case behavior.

This benchmark treats that workflow like a distributed system. Each role has a narrow input contract, produces immutable artifacts, and cannot silently read another role's private context.

## 2. The high-level pipeline

```text
fixed case + starter repository
          |
          v
planner/interviewer ----> handoff + Build Contract
                                  |
                                  v
                         fresh implementer
                                  |
                                  v
                     independent observation role
                                  |
                                  v
                     typed contract comparator
                                  |
                                  v
                         fresh postmortem
                                  |
                                  v
                       scorecard + receipts
```

The roles are intentionally separated:

- **Planner/interviewer:** turns the case into an explicit handoff and Build Contract.
- **Implementer:** receives only the allowed transfer artifacts and a clean starter tree.
- **Observation role:** independently materializes and executes the implementation.
- **Comparator:** compares expected and observed typed behavior exactly.
- **Postmortem:** analyzes the completed evidence without sharing the implementer's working context.

This separation prevents a common evaluation mistake: letting the same agent write the requirements, implementation, and self-evaluation while retaining all hidden context.

## 3. Cases and prompts

The public development corpus is stored in:

```text
corpus/public/cases.json
```

It contains six fixed development cases:

- bookmark tagging
- configuration merging
- CSV contact import
- expense recording
- reminder creation
- todo completion

Each case binds:

- a stable case ID and opaque token,
- a natural-language prompt,
- a clean starter repository,
- the starter tree digest,
- the expected command and persistence boundary.

The complete study design is **6 public development cases + 4 opaque holdout cases**. The four holdout prompts and starters are deliberately not stored in this repository. Only their external provisioning contract and public-safe commitments appear in:

```text
corpus/external-holdout/service-manifest.template.json
```

This is comparable to keeping production secrets out of a test runner: the controller can request a trusted evaluation but cannot inspect or optimize against the private data.

## 4. Automated interviewing

The benchmark has two distinct concepts that should not be confused.

### Deterministic fake-development mode

The checked-in one-line run uses deterministic role adapters. It does not call a model. This mode proves that:

- role boundaries work,
- interview artifacts can be generated and transferred,
- implementations can be independently executed,
- scoring is reproducible,
- tampering and invalid resume attempts fail closed.

It is development infrastructure evidence, not evidence that one LLM is better than another.

### Live interview mode

The service interfaces allow an externally provisioned model and trusted user simulator to conduct a variable-length interview. The number of questions is not fixed in advance. The simulator answers validated requests under an interaction budget and explicit routing rules.

Live provider credentials, simulator, evaluator, reporter, and private holdout data must be supplied outside this standalone repository. Missing services cause a blocked result instead of silently falling back to fake answers.

## 5. Why Docker/OCI workers are used

Planner, implementer, observation, and postmortem work run in separate OCI workers.

The worker policy enforces:

- a digest-addressed Linux arm64 image,
- no network,
- a read-only root filesystem,
- a non-root UID/GID,
- dropped Linux capabilities,
- `no-new-privileges`,
- a pinned seccomp policy,
- CPU, memory, process, and disk limits,
- only `/tmp` and one role-specific named volume.

Role input is canonical JSON written to a named volume. The input digest is checked before work begins. The worker writes one canonical output bound to that input digest. The controller then validates and imports only declared artifacts.

This is not intended as protection from a malicious machine owner. The local Docker daemon and operator are trusted. The isolation prevents accidental context sharing and undeclared file/network access between benchmark roles.

## 6. Canonical JSON and hashes

Many artifacts are canonicalized before hashing:

- UTF-8 encoding,
- normalized strings,
- sorted object keys,
- compact JSON representation,
- trailing newline where required,
- SHA-256 digest.

Why is this necessary? Normal JSON permits many byte representations of the same value. Without canonicalization, harmless formatting differences would change hashes and make replay unreliable.

The digest chain binds:

```text
run configuration
  -> corpus and arm definitions
  -> cell input
  -> role context and transferred artifacts
  -> worker input/output
  -> implementation and observation
  -> lifecycle manifest
  -> attempt receipt
  -> terminal receipt
  -> scorecard
```

If an artifact changes, downstream replay validation rejects the stale chain.

## 7. The three scored arms

The development benchmark compares three workflow shapes:

### `direct-v1`

A fresh implementer receives the public case/starter without a planner-generated contract. This is the baseline.

### `plan-v1`

A planner produces a handoff and Build Contract. A fresh implementer receives only those artifacts and the clean starter.

### `ultimateinterview-current-v1-structural`

The planner path additionally executes the frozen native Ultimateinterview v1 structural/readiness lifecycle before transfer.

A fourth fixture, `ultimateinterview-full-v2-expected-fail`, exists only for conformance testing. It is excluded from scoring because the pinned snapshot cannot provide the creditable execution receipts required by that protocol version.

## 8. Fresh-context transfer

The implementer does not receive the original interview transcript or the planner's hidden state.

For planning arms, it receives only:

- the clean starter tree,
- handoff data,
- Build Contract data,
- explicitly allowed metadata and digests.

The implementation output is transferred as a deterministic, content-addressed implementation recipe. The observation worker recreates it independently and verifies the resulting tree digest before executing it.

This makes the benchmark measure the handoff rather than shared conversational memory.

## 9. Observation and semantic comparison

A successful process exit is not enough. The observation role checks case-specific behavior:

- the expected command was executed,
- the correct case and state file were used,
- the command reported success,
- state actually changed when required,
- the reported state digest matches the file on disk,
- the pre-state and post-state satisfy the case-specific transition.

Expected and observed behavior are represented as typed atoms with five dimensions:

- **guard:** when the obligation applies,
- **effect:** what must happen,
- **polarity:** must or must-not,
- **boundary:** where the behavior is scoped,
- **temporal:** when the obligation must hold.

Primary credit is exact: the complete expected and observed atom sets must match. Broad, partial, or contradictory behavior does not receive exact credit.

## 10. Receipts and score replay

The controller stores receipts for each lifecycle phase:

- stage input,
- launch role,
- read output,
- clean workspace volume,
- complete attempt,
- terminal cell result.

Scoring does not trust copied score fields. It reconstructs:

- the allowed arm,
- the worker image and OCI profile,
- launch commands and controls,
- role input/output digests,
- native fixture evidence,
- observation predicates,
- typed comparison result.

A forged scorecard, changed worker image, substituted receipt, undeclared file, or altered observation causes scoring or resume to fail closed.

## 11. Development scores and their limits

The fake-development scorecard reports exact contract coverage for deterministic implementations. It is useful for validating benchmark mechanics and regression tests.

It does **not** establish:

- model quality,
- interview effectiveness in production,
- superiority of one arm,
- holdout performance,
- creditable v2 protocol performance.

A real comparison requires externally provisioned live models, multiple cases and seeds, preregistered settings, and the private holdout evaluator/reporter path.

## 12. Running the benchmark

From the workspace root:

```sh
benchmark/ultimateinterview-contract-drift/scripts/run-fake.sh
```

The script:

1. builds the pinned worker image,
2. resolves its immutable Docker image ID,
3. starts or resumes the deterministic development run,
4. executes all six cases across all three scored arms,
5. validates artifacts and writes the scorecard.

Validate the corpus:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  driftbench validate-corpus \
  --public-root benchmark/ultimateinterview-contract-drift/corpus/public \
  --partition dev
```

Run the test suite:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  --extra test pytest -q \
  benchmark/ultimateinterview-contract-drift/tests
```

Run worker preflight:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  python -m driftbench.worker_launcher \
  --project-root benchmark/ultimateinterview-contract-drift \
  preflight
```

## 13. Reading a run directory

A run directory contains:

- `run-manifest.json`: immutable run identity and input bindings,
- `state.json`: current run and cell states,
- `evaluation-status.json`: public-safe orchestration status,
- `scorecard.json`: development-only metrics,
- `cells/<cell-id>/`: inputs, contexts, role executions, implementation, observation, postmortem, and receipts.

Start with `scorecard.json`, then inspect a cell's `terminal-receipt.json` and `lifecycle-manifest.json`. Follow referenced digests rather than treating any single JSON file as authoritative by itself.

## 14. Common misunderstandings

### “A score of 1.0 means the interview method is proven.”

No. In fake mode it means the deterministic fixture implementation satisfied the checked development predicates.

### “The observer can just trust what the implementer says it changed.”

No. The observer recreates the implementation, checks digests, executes it, and verifies state transitions.

### “Why not keep the full transcript so implementation is easier?”

Because the benchmark is measuring handoff quality. Shared transcript memory would hide handoff loss.

### “Why are the four holdout prompts missing?”

If agents or optimizers can read holdout cases, repeated development can overfit to them. Holdout secrecy is an access-control property, not just a naming convention.

### “Is Docker a perfect security sandbox?”

No. The benchmark trusts the local operator and Docker daemon. OCI isolation is used for reproducible role separation and least privilege.

## 15. Useful source locations

```text
README.md                              quick-start commands
corpus/public/cases.json               six public prompts
corpus/public/starters/                clean CLI starter trees
corpus/external-holdout/               private-service boundary template
configs/fake-dev.toml                  deterministic run configuration
arms/arms.json                         scored/non-scored arm policy
oci/profile.json                       worker isolation policy
src/driftbench/cli.py                  controller and command flow
src/driftbench/role_worker.py          role execution and observations
src/driftbench/worker_launcher.py      Docker launch and receipt replay
src/driftbench/semantic.py             exact typed comparator
src/driftbench/metrics.py              score reconstruction
```
