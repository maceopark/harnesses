---
name: clarify-requirements
description: Clarify ambiguous requests and produce an executable, approved implementation contract.
---

# Clarify Requirements

Before implementation:

1. Identify every independent decision that could change observable behavior, compatibility, safety, cost, data, acceptance, or reversibility. Include technical choices when reasonable alternatives differ in any of those effects; do not dismiss them as implementation details.
2. Inspect the repository for the reported path, current behavior, tests, supported environments, adjacent paths, conventions, and compatibility constraints. Distinguish repository evidence from assumptions and hindsight.
3. Trace every proposed requirement and acceptance check to exactly one authority: the request, repository evidence, an explicitly approved default, or an owner decision. Remove requirements that lack such authority, including prescribed helpers, algorithms, fixtures, scopes, versions, generated output, extra regression guarantees, and implementation-derived tests.
4. For every unresolved material decision, do exactly one of the following:
   - ask the responsible owner a focused question that presents behaviorally distinct options;
   - propose a clearly labeled default, state its observable consequences and compatibility boundary, and obtain explicit approval; or
   - record an explicit delegation boundary naming who may decide it during implementation, the permitted alternatives, constraints, required evidence, and conditions that require returning to the owner.
5. Define the narrowest evidence-supported scope. Do not generalize from one failing path, object category, environment, or version to adjacent paths, categories, environments, or versions without repository evidence or explicit approval. Treat consistency across distinct existing paths as a material decision, not an automatic requirement.
6. Specify outcomes and acceptance oracles without prescribing an internal mechanism unless that mechanism is itself authorized. Verify that each oracle accepts known-valid behavior, rejects the reported failure, and does not freeze an unsupported representation, unchanged result, message, fixture, or intermediate helper behavior.
7. Treat tests as evidence for authorized behavior, not as new product requirements. Require only the minimum fixtures and coverage needed to prove the approved scope and compatibility boundary; additional scenarios remain implementation discretion unless separately justified.
8. When a choice may affect behavior outside the reported case, either define the approved compatibility boundary and evidence for it or record a bounded residual risk with explicit owner acceptance. Merely documenting a broader regression risk does not authorize it.
9. Summarize one inline executable contract containing scope, exclusions, required observable behavior, acceptance criteria, supported compatibility boundary, resolved material decisions, constrained delegation boundaries, and accepted residual risks. Confirm owner approval of the complete contract before implementation. Do not create or require `decision.jsonl` or another separate decision log.