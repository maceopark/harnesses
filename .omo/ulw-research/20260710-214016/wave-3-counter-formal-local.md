# Wave 3 — Formal Methods vs Local BuildContract

- Five non-collapsing verdicts: ABI, trace, property, adequacy, stakeholder.
- Live v1 implements ABI and structural trace only; property execution/result schema is absent; adequacy is human-mediated; stakeholder identity/authority is unauthenticated.
- Stabilize dirty/untracked v1 before extension. Use versioned v2 or digest-bound `assurance-results.json`, not in-place extra fields or one `verified` boolean.
- Property must bind model/property/scope/assumptions/tool/version/contract and keep unknown non-pass. Adequacy uses risk-specific must-kill mutation/vacuity/counterexamples with zero unexplained survivors.
- Formal proof never replaces real-surface evidence or stakeholder validation.

