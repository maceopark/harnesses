---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
State contract clauses as externally observable outcomes and independently verifiable material security, data-integrity, migration, compatibility, and readiness obligations; include a specific implementation or validation mechanism only when it is material or explicitly authorized, and leave every reversible non-material choice to the implementer for recording in a decision log outside the contract.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
Do not require documentation changes or a particular documentation form unless the request or an explicit interview answer makes documentation an observable outcome.
