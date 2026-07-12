# Wave 1 — Cryptographic Protocols

Worker: `/root/crypto_protocols` · Observed: 2026-07-10

## Digest

- Formal acceptance requires a relation/language, verifier predicate, adversary model, and quantified error; these guarantees do not transfer to natural-language interviews.
- Safe heuristics: freeze-before-challenge, independent discriminating challenge, explicit predicate, branch falsifier, and cheaper independent verifier.
- Commitment gives binding/hiding, not truth. PoK requires an extractor. ZK is simulator-based privacy. Fiat-Shamir remains assumption- and context-binding-dependent.
- Use ordinary-language names for transferred heuristics and explicitly record the lost guarantee.

## Sources

- https://www.wisdom.weizmann.ac.il/~oded/PSX/pok.pdf
- https://ir.cwi.nl/pub/1456/1456D.pdf
- https://www.wisdom.weizmann.ac.il/~naor/PAPERS/bit.pdf
- https://eprint.iacr.org/1998/011.pdf
- https://doi.org/10.1109/SFCS.2003.1238185

## EXPAND

- Compile bounded requirements predicates into executable witness relations.
- Measure challenge/reviewer dependence empirically.
- Threat-model deterministic challenge grinding and semantic re-encoding.
- Define transcript privacy composition.

