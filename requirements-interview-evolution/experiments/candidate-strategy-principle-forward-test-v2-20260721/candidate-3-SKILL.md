---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as externally observable outcomes and independently verifiable material security, data-integrity, migration, compatibility, and readiness obligations. Leave reversible non-material implementation and validation mechanisms to the implementer unless explicitly required, and record such choices in the contract without prescribing them. Repository evidence may identify constraints but does not authorize a particular mechanism; an existing test suite is not an acceptance requirement merely because it exists.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
Do not require documentation changes or a particular documentation form unless the request or an explicit interview answer makes documentation an observable outcome.
