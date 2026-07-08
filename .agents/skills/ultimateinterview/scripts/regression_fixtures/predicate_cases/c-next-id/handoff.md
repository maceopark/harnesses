# Spec: app-5 store (cross-arm case C — invalid next_id, escape E1)

> Crafted regression fixture for predicate_lint. Mirrors the real app-5 escape
> E1: an integer-typed persisted store with an "invalid next_id" reject case
> that names the category but no predicate. Should fire BOTH numeric-coercion
> (int fields, no coercion boundary) and reject-category (bare "invalid").

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-011 | Store schema is `{next_id: int, tasks: [{id: int, done: bool}]}` and ids are monotonic | Given a store is loaded, next_id exceeds every task id | g17 |
| REQ-013 | Invalid readable store data is a storage error and the file is preserved | Given the store has invalid next_id or a corrupt shape, the command exits 3 | g17 |
