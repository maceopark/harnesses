---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository broadly enough to identify cross-cutting material constraints affecting compatibility, safety, migration, data integrity, integration, or readiness. Treat discovered facts and validation assets as constraints or evidence, not authority for new behavior or prescribed mechanisms. Confine the contract and implementation changes to the narrowest authorized boundary, preserve behavior outside it, and ask the owner about any unresolved material choice.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as observable outcomes, and omit specific implementation or validation mechanisms unless the request or an explicit interview answer requires that mechanism.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
Do not require documentation changes or a particular documentation form unless the request or an explicit interview answer makes documentation an observable outcome.
