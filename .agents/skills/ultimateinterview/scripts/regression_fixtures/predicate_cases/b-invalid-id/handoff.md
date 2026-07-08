# Spec: codexplan id handling (cross-arm case B — bare reject category)

> Crafted regression fixture for predicate_lint. Mirrors codexplan's "invalid
> id value" requirement: a reject category named with no deciding predicate
> (which let the exit-code split — non-integer -> exit 2, out-of-range -> exit 1
> — go unpinned).

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-004 | An invalid id value is a domain error | Given the id argument is invalid, the command exits 1 and writes stderr | g4 |
