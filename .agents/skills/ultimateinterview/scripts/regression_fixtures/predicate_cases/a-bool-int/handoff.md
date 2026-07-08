# Spec: claudeplan store (cross-arm case A — bool-as-int)

> Crafted regression fixture for predicate_lint. Mirrors claudeplan's store
> shape: an integer-typed persisted field with no coercion boundary pinned.

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | Store schema is `{version: int, next_id: int, todos: []}`; next_id is a positive integer counter | Given a fresh store, next_id starts at 1 and increments on add | g1 |
| REQ-002 | Ids are assigned from next_id in add order | Given two adds, ids are 1 then 2 | g2 |
