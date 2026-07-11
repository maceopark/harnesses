# Consumer verification

Read during ENDGAME when a downstream consumer receives a contract, grant, or receipt.

Consumer execution, authentication, and policy enforcement remain downstream. This skill compiles and validates the handoff state; it does not execute consumer commands, authenticate an external actor, or operate a persistent policy service. The consumer must apply its own current authorization, target, expiry, and halt boundaries before it acts.

For schema-v2 handoffs, the `Consumer Verification` table compiles only abstract requirements. It must contain one `implementation-readiness` row for every `VER-*` verification and at least one `probe` row for a `PROBE-*` decision. Each row declares the receipt kind, exact ID, target, environment/scope, allowed outcome, expected exit code, run policy, and whether execution is eligible for automatic handling. Only `safe-auto` rows may set `Auto execute` to `yes`; consumer code must still enforce its own current authorization.

A downstream grant or receipt must bind the current session ID, manifest digest, Part-1 digest, contract digest, policy version, exact verification/probe ID, action or observation-spec digest, target, environment/scope, issuer and subject identity, issued/expiry times, nonce, outcome/exit, and artifact/stdout/stderr digests. A probe consumer supplies the persisted Task 4 observation-spec digest when it validates a `ProbeGrant`; equality with an arbitrary digest is not sufficient. The compiled contract is an allowlist and shape boundary only. It does not issue a grant, sign a grant, select a consumer, dispatch a command, or change adequacy or stakeholder verdicts.
