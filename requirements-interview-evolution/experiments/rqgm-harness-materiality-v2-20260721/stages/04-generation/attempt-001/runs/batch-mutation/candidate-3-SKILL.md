---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as observable outcomes, and omit specific implementation or validation mechanisms unless the request or an explicit interview answer requires that mechanism.
Treat documentation updates, internal change location or representation, and unrequested exact messages or data types as incidental choices unless repository evidence shows they affect compatibility or must be resolved for the contract to be implementable.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
