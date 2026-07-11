# ExecutionEvidenceBundle and decisions.jsonl

`scripts/pack_evidence.py` is the adapter boundary for execution evidence. It
projects the interview specification, decisions, executor state, manual
artifacts, and verification-command captures into one schema-versioned JSON;
the postmortem consumes the bundle rather than executor-internal formats.
Schema version **5** additively projects validated `build-contract.json` and
`execution-return.json`; schema v4 added owned `CAPTURED-OUTPUT` artifacts.

## decisions.jsonl

Written during implementation to `.ultimateinterview/<slug>/decisions.jsonl`,
one JSON object per line. Unknown fields are rejected fail-closed.

| Field | Required | Meaning |
| --- | --- | --- |
| `decision` | yes | concrete implementation decision |
| `reason` | yes | why that choice was made |
| `spec_citation` | no | handoff REQ or ledger id, if any |
| `alternatives` | no | considered and rejected options |
| `impact` | no | affected data, errors, UX, or behavior |
| `self_class` | no | implementer's evidence-only classification |
| `ts` | no | timestamp string |

## Verification command capture

Capture exactly one executable row from Part 1's `Verification Commands` table:

```bash
uv run <this-skill>/scripts/capture_verification.py <session-dir> --row <N> [--check <text>] [--slug <slug>] [--timeout 60]
```

The command reads Part 1 with `handoff_coverage.extract_part1`, parses stable
`VER-ID`, pass-condition, and run-policy coordinates with the shared
`verification_contract.parse_verification_rows`, and refuses a prose/action
row or any policy other than `safe-auto` (exit 2). A `safe-auto` command must
pass the BuildContract `verification_policy` allowlist; shell controls,
credential assignments, destructive/manual/expensive rows, and unbounded
commands are refused before process creation. Validated commands launch as
`shlex` argv with `shell=False` and the repository root as working directory.
A nonzero exit, timeout, or spawn failure is captured as a fact artifact; none
is a producer-side pass/fail verdict. The default output location is
`<repo-root>/.omo/evidence/<slug>/captured-output-row-<NNNN>.json`, where
`slug` defaults to the session directory name.

On POSIX, each command runs in an isolated process group. A timeout sends
SIGTERM to the group, allows a bounded grace interval, escalates surviving
members with SIGKILL, then reaps the leader and drains both streams before the
fact artifact is written. Output carried by `TimeoutExpired` is merged with
the final drain exactly once before byte counts and hashes are computed.
After drain/reap, capture polls the process group against a monotonic bounded
deadline, reissues SIGKILL when membership reappears, and requires a continuous
absence window before returning. ESRCH/EPERM signal races remain inside this
bounded proof loop; capture writes no success artifact unless disappearance is
observable, and an unprovable cleanup exits with a typed error instead.
Non-POSIX runtimes use a bounded direct-process
terminate/kill/drain fallback and never call POSIX-only process-group APIs.

Each capture is a strict, extra-field-forbidden `CAPTURED-OUTPUT` envelope:

| Field | Meaning |
| --- | --- |
| `marker` | literal `CAPTURED-OUTPUT` owner marker |
| `spec_row_number` | one-based displayed Verification Commands row number |
| `check` | displayed check text |
| `kind` | row kind from the specification |
| `exact_command` | exact command-cell string executed |
| `command_digest` | `canonical_command_digest(exact_command)` |
| `effective_heads` | canonical unique command heads from the exact command |
| `cwd` | repository-root execution directory |
| `started_at` | capture start timestamp |
| `ended_at` | capture end timestamp |
| `spawned` | whether the subprocess was spawned |
| `timed_out` | whether its timeout elapsed |
| `timeout_seconds` | configured positive timeout in seconds |
| `exit_code` | process exit code, or `null` when unavailable |
| `stdout` | bounded inline stdout text |
| `stderr` | bounded inline stderr text |
| `stdout_full_bytes` | byte length of untruncated stdout |
| `stderr_full_bytes` | byte length of untruncated stderr |
| `stdout_sha256` | SHA-256 of untruncated stdout bytes |
| `stderr_sha256` | SHA-256 of untruncated stderr bytes |

Capture and final bundle writes are atomic: a same-directory temporary file is
flushed and fsynced, then replaced into place. Inline stdout and stderr are
individually bounded at 128,000 raw bytes. Their untruncated byte counts and
SHA-256 values always remain in the envelope, so truncation never claims the
stored text was complete.

The consumer joins a capture to a specification row only through
`verification_contract.captured_output_matches(row, rec)`: row number and
check must match `row_identity`, the digest must equal the canonical digest of
the row's raw command, effective-head sets must be equal, and the record must
have `spawned == true` and `timed_out == false`. This is provenance matching,
not a semantic pass judgment.

## Building the bundle

```bash
uv run <this-skill>/scripts/pack_evidence.py <repo>/.ultimateinterview/<slug> \
  [--diff-range main..HEAD | --diff-file impl.diff] \
  [--evidence-dir <dir>] [--ulw-dir <dir> | --no-ulw] \
  [--repo-root <repo>] [--out <path>]
```

The required order is **initial pack → capture verification commands → final
repack**. The initial pack is an audit-start snapshot; capture artifacts are
then written; the final repack is the bundle a postmortem must consume.

All runtime/manual files remain in `artifacts.files` with stable artifact ids,
repo-relative paths, byte size, file SHA-256, inferred kind, references, and
bounded text. Schema-v5 IDs combine a readable path slug with a SHA-256 prefix
of the exact canonical relative POSIX path, so case and punctuation variants
remain distinct; duplicate final IDs fail packing. Evidence directories and
every discovered component must be real non-symlink paths contained by the
resolved repository root before any file is read. For each valid owned capture,
packing additionally projects the
strictly validated record into `artifacts.captured_outputs`. The projection
keeps every envelope field (including untruncated stream byte counts and
SHA-256 values), `artifact_id` (the stable manifest id), and `file_sha256`
(recomputed from the artifact file during this pack). Its effective heads are
recomputed from `exact_command` and must exactly equal the record. A parseable
file claiming `marker: "CAPTURED-OUTPUT"` but failing validation or canonical
heads aborts packing (exit 1, no bundle written); unknown foreign artifacts
retain the ordinary bounded manifest behavior.

Absent ulw-loop state, artifacts, or diff are visible in `missing_evidence`;
malformed foreign ulw ledger data becomes `warnings`. Owned interview ledger,
decision-log, BuildContract, ExecutionReturn, and captured-output invalidity
fails closed. An absent ExecutionReturn is an auditable missing-evidence/process
finding, not a packing failure. Foreign executor state remains under
`execution`; the validated return is separate under `contract` and never
overwrites that provenance.

## Size discipline

- ulw event strings over 2,000 characters are truncated; nested values over
  8,192 bytes become digest stubs. `brief_md` identical to the handoff is
  deduplicated.
- Ordinary artifact text is limited to 128,000 bytes per file and 262,144
  bytes total, while its manifest remains available.
- Capture stdout/stderr inline text is limited to 128,000 bytes per stream;
  each capture preserves full-byte counts and SHA-256 values as described
  above.
- A bundle over 786,432 bytes receives a visible warning.

## Bundle shape (schema_version 5)

```json
{
  "schema_version": 5,
  "sources": {"session_dir": "...", "ulw_dir": null, "evidence_dir": "...", "repo_root": "..."},
  "spec": {"handoff_md": "...", "interview_ledger": []},
  "decisions": [],
  "execution": {"present": false, "ledger_events": [], "criterion_events": [], "revisions": [], "user_decision_blockers": [], "event_kind_counts": {}},
  "contract": {
    "compatibility_mode": "stable-v5",
    "build_contract_path": ".../build-contract.json",
    "build_contract": {"schema_version": 1, "contract_digest": "..."},
    "execution_return_path": ".../execution-return.json",
    "execution_return": {"marker": "EXECUTION-RETURN", "schema_version": 1, "contract_digest": "..."}
  },
  "artifacts": {
    "present": true,
    "root": ".../.omo/evidence/<slug>",
    "files": [{"id": "artifact-...", "path": ".omo/evidence/...", "sha256": "..."}],
    "captured_outputs": [{"artifact_id": "artifact-...", "file_sha256": "...", "marker": "CAPTURED-OUTPUT", "spec_row_number": 1, "...": "all capture-envelope fields"}]
  },
  "lessons": {"stores": []},
  "diff": null,
  "warnings": [],
  "missing_evidence": []
}
```

When sidecars are absent, v5 records `compatibility_mode: "legacy-v4"`, null
projections, and explicit missing-evidence notes. Consumers continue to read
historical schema-v3/v4 bundles without rewriting them. Stable-v5 verification
joins use `VER-ID` plus the validated contract digest; positional joins are
reserved for legacy compatibility. Consumers accept only exact schema versions
3, 4, and 5. Before a stable-v5 join, the consumer freshly compiles current
Part 1 and requires exact equality with both the current BuildContract sidecar
and its embedded projection. It likewise requires the current ExecutionReturn
sidecar to equal the embedded return, revalidates the current decision log, and
checks artifact IDs and hashes against current non-symlink files on disk.

`criterion_events` projects `evidence_captured`, `criterion_failed`, and
`criterion_blocked`; `revisions` projects `criteria_revised`; and
`user_decision_blockers` projects `goal_needs_user_decision`. Lessons stores
are an audit-start snapshot of active rows.

A green `postmortem_lint` proves execution-provenance + human-entered
self-consistency ONLY, not non-gaming or semantic pass.
