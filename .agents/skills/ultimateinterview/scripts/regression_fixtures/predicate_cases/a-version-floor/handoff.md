# Spec: claudeplan store version (cross-arm case A — one-sided version rule)

> Crafted regression fixture for predicate_lint. Mirrors claudeplan's store
> version handling: an upper rule with no floor.

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-003 | A store written by a newer schema is refused | Given the store version is greater than 1, the command exits 1 and leaves the file unchanged | g3 |
