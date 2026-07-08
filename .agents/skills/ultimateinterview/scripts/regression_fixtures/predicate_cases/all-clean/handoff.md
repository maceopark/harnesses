# Spec: well-specified contract (predicate control fixture)

> Control fixture: a reject category WITH a decidable predicate, no integer-typed
> persisted field, no one-sided version rule. predicate_lint must report
> predicate_ok: yes — proof the checks suppress correctly, not just that they fire.

# Part 1 — Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion | Source |
| --- | --- | --- | --- |
| REQ-001 | A title is invalid iff it is empty, whitespace-only, or exceeds 256 characters; reject with exit 2 | Given `""` or `"   "`, the command exits 2 and adds no task | g1 |
| REQ-002 | The default view lists not-done tasks in insertion order | Given three tasks and one completed, the other two show in add order | g2 |
