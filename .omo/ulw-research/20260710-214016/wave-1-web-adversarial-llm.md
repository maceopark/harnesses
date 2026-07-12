# Wave 1 — Adversarial LLM Reliability

- Worker: `/root/adversarial_llm`; observed 2026-07-10.
- Result: external checkable feedback is the most consistent differentiator; reflection, votes, debate, learned verifiers, and confidence remain bounded advisory signals.
- Intrinsic correction can degrade; same-model debate can converge falsely; more calls can reinforce hard-case errors; retrieval creates common-mode distractors and provenance/freshness risk.
- Sound scoped checkers materially outperform same-LLM verification on formal tasks, but only for encoded predicates.
- Controls: claim-bound evidence, external verifier routing, process+outcome gates, abstention/escalation, slice-specific calibration, verifier stress tests.
- EXPAND: reduced-space test on ultimateinterview; correlation audit; adversarial gate bundles; per-gate abstention calibration.

