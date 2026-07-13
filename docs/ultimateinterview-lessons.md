# Ultimateinterview Lessons

Repository-specific routing lessons learned from compiler-only postmortems. Signals must be observable in the request or repository at discovery time, never hindsight. `Fired/Caught` records whether a signal appeared and whether the Discovery Record explicitly preserved a `lesson-triggered` marker whose requirement or evidence reference covered it.

Repo-specific signals only. Dedupe before adding or strengthening a row; a decision log or postmortem finding is evidence, not product authority.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |
| A Build Contract pins `uv run --project <fixture> pytest` from a workspace root that already has unrelated tests - establish whether project selection changes cwd or collection, and authorize a fixture-scoped collector when it does not | core-path | trigger-too-narrow | todo-cli-benchmark-new ESC-001 and todo-cli-app-6 ESC-001: `uv --project` selected the environment but retained the harness cwd; app-6 required an uncontracted pytest11 routing hook recorded in digest-bound `decision.jsonl` | 2026-07-13 | 1/0 |

## Retired

Rows moved here after repeated dry fires. They remain provenance only and do not participate in current discovery.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
