---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository broadly enough to identify and respect cross-cutting compatibility, security, migration, data-integrity, and integration constraints. Treat repository facts as discovery evidence, not authority: prescribe contract behavior and implementation changes only within the narrowest boundary authorized by the request or an explicit decision. Maintain behavior outside that boundary as an implementation compatibility constraint without promoting it into independent contract clauses, and ask about every unresolved material choice within or crossing the boundary.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as observable outcomes, and omit specific implementation or validation mechanisms unless the request or an explicit interview answer requires that mechanism.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
