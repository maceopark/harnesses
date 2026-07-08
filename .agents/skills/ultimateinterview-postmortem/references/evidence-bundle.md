# ExecutionEvidenceBundle and decisions.jsonl

The adapter boundary from the closed-loop design (see
`docs/ultimateinterview-postmortem-closed-loop-handoff.md` §14): the postmortem never reads
executor-internal file formats. One script - this skill's
`scripts/pack_evidence.py` - projects every execution
evidence source into a single schema-versioned JSON, and the postmortem
consumes only that. The postmortem runs the script itself at the start of
every audit; the user never packs evidence by hand. Swapping the executor
(ulw-loop, ultragoal, manual coding)
means writing a different adapter, not touching the postmortem.

## decisions.jsonl (implementer decision log)

Written during implementation to `.ultimateinterview/<slug>/decisions.jsonl` -
one JSON object per line, appended whenever the implementer makes a decision
the spec did not force: a filled spec gap, a deviation, an assumption. This is
the raw material that lets the postmortem separate `spec_gap` from
`implementation_deviation` instead of guessing from the diff.

Fields (snake_case; unknown fields are rejected fail-closed):

| Field | Required | Meaning |
| --- | --- | --- |
| `decision` | yes | what was decided, concretely |
| `reason` | yes | why - what forced the choice |
| `spec_citation` | no | the handoff REQ / ledger id this touches, or absent when nothing in the spec covers it (that absence is itself spec-gap evidence) |
| `alternatives` | no | list of options considered and rejected |
| `impact` | no | what the decision changes (data shape, error semantics, UX...) |
| `self_class` | no | implementer's own guess: `spec_gap` \| `implementation_deviation` \| `evaluation_uncertainty` \| `execution_process_gap` \| `legitimate_spec_evolution` - evidence for the postmortem, never a verdict |
| `ts` | no | ISO timestamp string |

Example line:

```json
{"decision": "used ISO dates in store", "reason": "spec named no serialization format", "spec_citation": "REQ-3", "alternatives": ["epoch seconds"], "impact": "store file format", "self_class": "spec_gap"}
```

## Building the bundle

```bash
uv run <this-skill>/scripts/pack_evidence.py <repo>/.ultimateinterview/<slug> \
  [--diff-range main..HEAD | --diff-file impl.diff] \
  [--evidence-dir <dir>] \
  [--ulw-dir <dir> | --no-ulw] \
  [--repo-root <repo>] [--out <path>]
```

Writes `<session-dir>/evidence_bundle.json` and prints a one-line summary plus
every warning/missing-evidence note. Exit 1 (nothing written) when a file the
skill owns is invalid: absent `handoff.md`/`ledger.json`, an invalid interview
ledger, or any malformed `decisions.jsonl` line. Executor-owned inputs degrade
instead: absent ulw-loop dir or diff lands in `missing_evidence`, malformed
ulw ledger lines in `warnings` - both visible in the bundle, never dropped.

ulw-loop state is auto-discovered when `--ulw-dir` is omitted: the script
checks `<repo-root>/.omo/ulw-loop` and one subdir level below it (ulw-loop
scopes state to `<session-id>/` subdirectories when a Codex session id is
set). Among multiple candidates, a `brief.md` mentioning the interview slug
wins; otherwise the newest ledger/goals mtime does, with a warning naming the
losers so a wrong pick is visible. `--ulw-dir` pins the choice; `--no-ulw`
packs without execution evidence and says so in `missing_evidence`.

Runtime/manual artifacts are also packed. When `--evidence-dir` is omitted,
the script checks `<repo-root>/.omo/evidence/<slug>` and records every file as
an artifact manifest entry with a stable id, inferred kind, repo-relative
path, byte size, sha256, criterion-event references, and UTF-8 text content
when the file is small enough for direct review. This mirrors the useful part
of lazycodex quality-gate `artifactRefs` without requiring humans to duplicate
manual QA metadata by hand. Pass `--evidence-dir` when a runner stored
artifacts in another evidence subdirectory. Missing artifact directories are
recorded in `missing_evidence` instead of blocking the bundle.

Run packing after implementation, QA, and sign-off evidence are complete.
Earlier runs are only diagnostic snapshots; the postmortem should use the
final regenerated bundle.

## Lessons snapshot (schema_version 3)

Pack runs first in the audit, so the bundle also snapshots each lessons store's
ACTIVE rows at that moment - the audit-start truth. `postmortem_lint` validates
the report's `### Lessons Fire-Tracking` table against this snapshot, never
against the live store: a bulk-absorption run empties the active table before
the lint sees it, so a live count would let the fire-tracking check pass
vacuously (the blind spot the app-5 run exposed). `--lessons <path>` overrides
the snapshot targets; the default is `<repo-root>/docs/ultimateinterview-lessons.md`
plus the global store beside the interview skill. A store named explicitly but
absent lands in `missing_evidence`; an unparseable one lands in `warnings`.

## Size discipline (schema_version 2)

The bundle's consumer is a model context, so the adapter bounds everything it
inlines - the first real executor run packed 5.1 MB because 21 steering
events each embedded full goals-state snapshots, and the bundle became
unreadable by the very thing it exists to feed. Bounds (constants in
`pack_evidence.py`):

- Event fields (every `ledger_events` entry, hence also the projections, and
  each entry of `goals.goals`): a string field over 2,000 chars is truncated
  inline with `…[truncated: N chars total, sha256 …]`; a nested dict/list
  serializing over 8,192 bytes becomes a digest stub
  `{"omitted": "oversized-value", "bytes", "sha256", "shape", "keys"?, "preview"}`.
  Narrative fields (`message`, `evidence`, ids, timestamps) always survive
  verbatim; raw snapshots stay on disk at `sources.ulw_dir`.
- `brief_md` identical to the handoff (the common ulw-loop case) is replaced
  by the marker `[identical to spec.handoff_md - sha256 …]`.
- Artifact text: 128,000 bytes per file plus a 262,144-byte total budget;
  past either, the entry keeps its manifest (path, size, sha256, references)
  with `text_omitted` saying why.
- A bundle still over 786,432 bytes appends its own `warnings` entry - an
  executor input is dwarfing the digest bounds and the adapter needs a new
  bound, not the postmortem a bigger context.

## Bundle shape (schema_version 3)

```json
{
  "schema_version": 3,
  "sources": {
    "session_dir": "...",
    "ulw_dir": "... | null",
    "evidence_dir": "... | null",
    "repo_root": "..."
  },
  "spec": {"handoff_md": "<text>", "interview_ledger": [ {"id": "g1", ...} ]},
  "decisions": [ {"decision": "...", "reason": "...", ...} ],
  "execution": {
    "present": true,
    "brief_md": "<text> | null",
    "goals": {},
    "ledger_events": [ {"kind": "...", ...} ],
    "criterion_events": [],
    "revisions": [],
    "user_decision_blockers": [],
    "event_kind_counts": {"evidence_captured": 3}
  },
  "artifacts": {
    "present": true,
    "root": ".../.omo/evidence/<slug>",
    "files": [
      {
        "id": "artifact-omo-evidence-slug-green-pytest-txt",
        "kind": "log",
        "path": ".omo/evidence/<slug>/green-pytest.txt",
        "size_bytes": 123,
        "sha256": "...",
        "referenced_by": [
          {
            "source": "execution.criterion_events",
            "index": 0,
            "kind": "evidence_captured",
            "goal_id": "G001",
            "criterion_id": "C001"
          }
        ],
        "text": "..."
      }
    ]
  },
  "lessons": {
    "stores": [
      {
        "path": ".../ultimateinterview/lessons.md",
        "name": "lessons.md",
        "active_count": 3,
        "active": [ {"signal": "<=120 chars", "lens": "domain/state", "fired": 1, "caught": 1} ]
      }
    ]
  },
  "diff": {"source": "git diff main..HEAD", "text": "..."},
  "warnings": [],
  "missing_evidence": []
}
```

Projections (verified against lazycodex v4.16.0 `constants.ts`; the kind
constants in `pack_evidence.py` are the version pin - ulw-loop's ledger itself
carries no schema version):

- `criterion_events`: kinds `evidence_captured`, `criterion_failed`, `criterion_blocked`
- `revisions`: kind `criteria_revised` - note upstream records no original-spec citation, so revision provenance still needs the interview ledger side
- `user_decision_blockers`: kind `goal_needs_user_decision` - fires only for auth/credential-style blockers upstream, so its absence proves nothing about other external decisions
- `ledger_events` keeps every event with size-bounded fields (see Size discipline above); `event_kind_counts` shows what the projections did not consume
- `lessons.stores[]` is the audit-start snapshot of each lessons store's active rows (schema v3+); `postmortem_lint` anchors fire-tracking to `active_count` here, not to the live store

## How the postmortem uses it

- `decisions[]` entries are first-class `spec_gap` candidates: check each against the handoff - if the spec really is silent there, the interview missed it; if the spec covers it and the decision contradicts it, it is `divergent-implementation`.
- `execution.revisions` and `user_decision_blockers` feed the "should the interview have asked this up front?" analysis.
- `missing_evidence` entries map to `execution_process_gap` in the failure classification: what happened cannot be reconstructed.
- The interview-side classes (`synthesis-loss`, lens attribution) stay as-is; the bundle adds execution-side resolution, it does not replace them.
