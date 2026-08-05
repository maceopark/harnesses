---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request, repository, and connected systems broadly enough to identify and preserve material security, data-integrity, migration, compatibility, and integration constraints. Treat discovered facts as constraints, not authorization: prescribe behavioral, implementation, or validation changes only within the narrowest boundary authorized by the request or explicit owner answers, create no adjacent requirements, and preserve behavior outside that boundary.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as observable outcomes, and omit specific implementation or validation mechanisms unless the request or an explicit interview answer requires that mechanism.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
Do not require documentation changes or a particular documentation form unless the request or an explicit interview answer makes documentation an observable outcome.
