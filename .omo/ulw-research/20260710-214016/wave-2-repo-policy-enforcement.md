# Wave 2 — Policy Enforcement

- Worker: `/root/policy_enforcement`; observed 2026-07-10.
- `session_update` is a canonical state PEP; `--gate` is a strong but opt-in CLI PEP.
- `--next`, handoff delivery, implementation dispatch, and tool execution are not universally mediated.
- Matrix covers 15 subject-resource-action-context transitions with bypass/liveness/fatigue analysis; focused v1 tests passed 16 cases.
- Design implication: readiness policy is advisory wherever no substrate-owned interceptor blocks the action.

