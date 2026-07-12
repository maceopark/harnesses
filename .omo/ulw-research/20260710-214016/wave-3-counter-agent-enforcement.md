# Wave 3 — Agent Controls vs Local Enforcement

- Adopt consequential-transition mediation, not per-token authorization.
- Dispatch grant binds subject/resource/action/session/generation/payload digest/policy version/expiry/nonce; PEP consumes it immediately and emits a durable receipt.
- Atomic recovery, idempotency, replay resistance, and audit receipt are separate; current local system materially provides only the first.
- Same idempotency key + same binding returns prior receipt; conflicting binding rejects. External effects use intent/outbox plus observed-effect reconciliation; never claim exactly-once.
- Framework guardrail presence is not universal coverage; inventory and bypass-test every equivalent effect path.

