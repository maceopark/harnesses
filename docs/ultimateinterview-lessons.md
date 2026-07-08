# Ultimateinterview Lessons

Signal-to-lens routing rules learned from spec postmortems. The `ultimateinterview` skill reads this file during Orientation: when a signal below appears in a new request or the touched code, treat the named lens as triggered. Keep signals observable at interview time, never hindsight. `Fired/Caught` is fire-tracking: postmortems increment Fired when the signal appeared, Caught when the triggered lens actually produced a ledger entry; Fired ≥ 3 with Caught 0 retires the row.

Repo-specific signals only — repo-agnostic lessons live in the global store (`~/.agents/skills/ultimateinterview/lessons.md`); dedupe against both before appending.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |

## Retired

Rows moved here after 3 dry fires (signal appeared, lens caught nothing). Kept for the record; Orientation skips them.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
