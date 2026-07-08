# Spec: claudeplan store (cross-arm case A — coercion pinned)

> Same shape as a-bool-int, but the type-coercion boundary is pinned, so
> predicate_lint's numeric-coercion check must NOT fire.

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | Store schema is `{version: int, next_id: int, todos: []}`; next_id is a positive integer counter. A JSON boolean is not a valid integer for these fields and a numeric string is rejected too — load fails with exit 3. | Given a store whose next_id is `true`, exit 3 and the file is unchanged | g1 |
| REQ-002 | Ids are assigned from next_id in add order | Given two adds, ids are 1 then 2 | g2 |
