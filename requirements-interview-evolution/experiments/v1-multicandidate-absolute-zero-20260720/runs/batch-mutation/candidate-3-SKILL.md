---
name: clarify-requirements
description: Clarify ambiguous requests and produce an executable, approved implementation contract.
---

# Clarify Requirements

Before implementation:

1. Identify each independent decision that could change observable behavior, compatibility, safety, cost, data, acceptance criteria, or reversibility.
2. Inspect the repository for existing behavior, tests, conventions, and compatibility constraints that can resolve those decisions.
3. For every unresolved material decision, do exactly one of the following:
   - ask the responsible owner a focused question;
   - propose a clearly labeled default and obtain explicit approval; or
   - record an explicit delegation boundary naming who may decide it during implementation and what constraints apply.
4. Do not turn implementation ideas, additional test scenarios, broader compatibility guarantees, or risk mitigations into contract requirements unless they follow from the request, repository evidence, an approved default, or an explicit owner decision.
5. When a chosen implementation may alter behavior outside the reported case, either define the required compatibility boundary and acceptance evidence or record the bounded residual risk without silently expanding the contract.
6. Summarize the executable contract inline, including scope, required behavior, acceptance criteria, resolved decisions, delegation boundaries, and acknowledged residual risks. Confirm owner approval before implementation. Do not require a separate decision log file.

Before sealing the contract, trace every proposed boundary against current observable behavior and compatibility tests. Any unsupported change in invocation count, parsing extent, precedence, emitted content, error text, platform coverage, or test scope must be repository-resolved, owner-approved as a labeled default, or explicitly delegated with constraints; silence never implies preservation, exclusion, or expansion.
