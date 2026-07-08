# Spec: codexplan id handling (cross-arm case B — predicate pinned)

> Same requirement as b-invalid-id, but the reject predicate is decidable, so
> reject-category must NOT fire.

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-004 | An id argument is invalid unless it matches `^[1-9][0-9]*$` (a positive base-10 integer, no sign, no leading zero, no whitespace); reject exits 2 | Given `abc`, `01`, `+1`, or ` 1`, the command exits 2 and writes stderr | g4 |
