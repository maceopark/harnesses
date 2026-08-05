---
name: clarify-requirements
description: Clarify an ambiguous request before implementation.
---

# Interview

Inspect the request and repository.
Ask only questions whose answers can materially change the resulting contract.
Produce the runtime-required contract without inventing unauthorized behavior.
Admit a contract clause only when it states requested or explicitly authorized externally observable behavior, or an independently required and verifiable material security, data-integrity, migration, or compatibility constraint. A choice is material when reasonable alternatives change observable behavior, compatibility, safety, cost, data, acceptance, or reversibility; resolve each unresolved material choice through an owner answer, an explicit approved default, or an explicit delegation boundary. Keep reversible non-material implementation choices outside the contract, while recording every implementer choice in the runtime-provided decision log without requiring a new log artifact. Prescribe an implementation or validation mechanism only when explicitly authorized as a contract obligation.
Do not promote inferred edge cases or exhaustive examples into separate requirements unless explicitly requested or answered.
