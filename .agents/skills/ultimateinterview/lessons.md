# Ultimateinterview Lessons

Signal-to-lens routing rules learned from spec postmortems. The `ultimateinterview` skill reads this file during Orientation: when a signal below appears in a new request or the touched code, treat the named lens as triggered. Keep signals observable at interview time, never hindsight. `Fired/Caught` is fire-tracking: postmortems increment Fired when the signal appeared, Caught when the triggered lens actually produced a ledger entry; Fired ≥ 3 with Caught 0 retires the row.

| Signal | Lens to trigger | Failure class | Evidence | Date | Fired/Caught |
| --- | --- | --- | --- | --- | --- |

## Retired

Rows moved here after 3 dry fires (signal appeared, lens caught nothing) or after absorption into the skill body (the rule became unconditional method; keeping the row would double-fire it). Kept for the record; Orientation skips them.

| Signal | Lens to trigger | Retired date | Reason |
| --- | --- | --- | --- |
| Closed operation set — enumerate the illegal/unknown-operation branch as its own matrix row | misuse | 2026-07-07 | Absorbed as an unconditional rule: op × data-state matrix requires the unknown/illegal-operation row (handoff-sequence.md Verification commands + audit-checklists operation-surface gate). Was 2/2 |
| File-based store — enumerate write-path durability (crash/interrupt mid-write) | domain/state | 2026-07-07 | Absorbed into the data/schema audit checklist row (audit-checklists.md: ownership/retention/deletion/durability). Was 1/1 |
| Time-dependent behavior + real-surface-only verification — spec must name the time-injection seam | domain/state | 2026-07-07 | Absorbed as a gate line: environment-manipulating verification rows must name their sanctioned injection seam (handoff-sequence.md Gates). Was 0/0 |
| New or changed command (CLI/API) accepts free-text user input — enumerate degenerate inputs as explicit ledger entries | misuse | 2026-07-07 | Absorbed as unconditional rules: orientation.md misuse trigger (free-text/user-supplied input) + lenses.md §6 degenerate-input enumeration + audit-checklists misuse input-surface gate. Was 4/4 |
| Temporal word in goal (today, daily, morning, weekly, due) — falsify time-boundary semantics with one concrete boundary crossing | domain/state | 2026-07-07 | Absorbed: orientation.md domain/state trigger (temporal words) + lenses.md §4 boundary-crossing walk. Was 3/3 |
| Input-validation pinned for a tool-owned store — decide load-time revalidation vs trust of stored values | domain/state | 2026-07-07 | Absorbed into audit-checklists store-trust gate (revalidation decision) + lenses.md §6 input-and-load rule. Was 1/1 |
| File-store path or override seam — enumerate the store-ACCESS error surface (missing parent dir, permission, undecodable bytes, seam edge values) | domain/state | 2026-07-07 | Absorbed into audit-checklists store-trust gate (access-error surface). Was 1/1 |
| Closed on-disk schema + migration non-goal — decide the unknown/extra-field policy (reject vs ignore-and-preserve) | domain/state | 2026-07-07 | Absorbed into audit-checklists store-trust gate (unknown/extra-field policy). Was 1/1 |
