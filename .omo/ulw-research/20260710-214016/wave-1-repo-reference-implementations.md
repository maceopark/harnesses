# Wave 1 — Reference Implementations

- Worker: `/root/reference_implementations`; observed 2026-07-10.
- Pinned implementations inspected: python-tuf, in-toto, Rekor, SLSA verifier, Witness.
- Executed evidence: TUF key rotation 2 tests/25 subtests passed; in-toto thresholds 14 tests passed; Rekor verify and go-witness DSSE packages passed.
- TUF dual-authorizes root rotation; in-toto checks authorized matching artifact reports; Rekor inclusion needs persisted consistency/checkpoint monitoring; SLSA separates signed provenance from consumer expectations; Witness functionaries are OR by default, not quorum.
- EXPAND closed as implementation corroboration; split-view/duplicate-threshold empirical extensions remain future benchmark work.

