# Wave 1 — Supply-chain Trust

Worker: `/root/transparency_supply_chain` · Observed: 2026-07-10

## Digest

- TUF freshness is expiry + persisted monotonic versions + authenticated snapshot binding; expiry alone does not stop replay.
- Provenance/signatures/log inclusion establish origin or occurrence, not semantic truth.
- Threshold review must cover the same digest and independent failure groups.
- A session snapshot should bind ledger, protocol, questions, transcript tail, BuildContract, handoff, and material repo revision.
- Compromise recovery must preserve history, bound the compromise window, revoke authority, invalidate causal derivatives, and reobserve.

## Sources

- https://theupdateframework.github.io/specification/latest/
- https://github.com/in-toto/specification/blob/master/in-toto-spec.md
- https://slsa.dev/spec/v1.2/verifying-artifacts
- https://docs.sigstore.dev/about/threat-model/
- https://reproducible-builds.org/docs/plans/

## EXPAND

- Compare adaptation matrix to executable local gates.
- Red-team shared-model/source thresholds.
- Define emergency bootstrap ownership and compromise semantics.
- Review privacy/retention tension in append-only logs.
