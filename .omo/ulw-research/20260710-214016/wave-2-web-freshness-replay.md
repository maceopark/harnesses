# Wave 2 — Freshness, Replay, and Rotation

- Worker: `/root/freshness_replay`; observed 2026-07-10.
- Whole-session replay remains internally coherent without an external durable head.
- Proposed layers: authority policy/root → short-lived signed session head/timestamp → exact snapshot manifest → versioned artifacts.
- Reject rollback, equal-version/different-digest equivocation, mix-and-match, expiry, stale authority epoch, reused transition nonce, and improper old/new rotation.
- Rotation/reset rules and 40 scenario/model tests are design propositions, not current enforcement.
- Liveness/clock/privacy/recovery costs are explicit.
