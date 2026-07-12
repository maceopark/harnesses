# Zero-trust architecture controls for an LLM requirements interview

Research date: 2026-07-10. Read-only research. Source sweep used 12 varied searches, followed by full-page/PDF reads of NIST SP 800-207, Google BeyondCorp papers, NCSC guidance, CISA maturity guidance, and an independent peer-reviewed counter-source.

## Source basis

Primary sources:

- [NIST SP 800-207, Zero Trust Architecture](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf), especially sections 2, 2.1, 3, and 5.
- [NIST publication landing page](https://csrc.nist.gov/pubs/sp/800/207/final).
- [Google BeyondCorp: Design to Deployment at Google](https://www.usenix.org/system/files/login/articles/login_spring16_06_osborn.pdf).
- [Google BeyondCorp: The Access Proxy](https://research.google/pubs/beyondcorp-the-access-proxy/).
- [Google BeyondCorp: Maintaining Productivity While Improving Security](https://storage.googleapis.com/gweb-research2023-media/pubtools/3901.pdf).
- [Google Cloud BeyondCorp principles](https://cloud.google.com/beyondcorp?hl=en).
- [CISA Zero Trust Maturity Model v2](https://www.cisa.gov/sites/default/files/2023-04/CISA_Zero_Trust_Maturity_Model_Version_2_508c.pdf).

Independent corroboration/counter-sources:

- UK NCSC, [Zero trust architecture design principles](https://www.ncsc.gov.uk/pdfs/blog-post/zero-trust-architecture-design-principles.pdf) and [Demystifying Zero Trust](https://www.ncsc.gov.uk/collection/zero-trust/demystifying-zero-trust).
- UK NCSC, [Zero trust: building a mixed estate](https://www.ncsc.gov.uk/collection/zero-trust/implementing-zt/zero-trust-building-a-mixed-estate).
- Christian D. Jensen, peer-reviewed, [Why Zero Trust Architectures Are Not Replacing Trust](https://orbit.dtu.dk/en/publications/why-zero-trust-architectures-are-not-replacing-trust/), IFIPTM 2023 proceedings, published 2024.

## Architectural semantics

NIST's operative definition is unusually precise: zero trust minimizes uncertainty in accurate, least-privilege **per-request access decisions** while treating the network as compromised. Its formal tenets phrase access as **per-session** and require that authorization to one resource not automatically authorize another. These are compatible but not identical: do not translate them into a claim that every token or conversational sentence must trigger a full evaluation. The evaluation boundary should be each consequential resource/action request or session transition.

NIST's model is:

- Subject: the user, service/application, and requesting device.
- Resource: data, application, service, workflow, account, compute, or actuator.
- Request context: subject identity, resource identity/sensitivity, requested action, device/application state, time, location, behavior, threat intelligence, and policy.
- Policy engine (PE): decides grant, deny, or revoke and logs the decision.
- Policy administrator (PA): establishes or shuts down the communication path.
- Policy enforcement point (PEP): enables, monitors, and terminates the subject-resource connection.
- Continuous diagnostics and mitigation: supplies current posture information; logs and telemetry feed later policy refinement and immediate reevaluation.

Google BeyondCorp provides a concrete implementation rather than a new invariant set. It replaces network-derived privilege with device inventory and state, associated user, requested resource, real-time credentials, programmatic policy, a centralized access-control engine, and gateways that enforce decisions. Its Trust Inferer continually updates device tiers on state change or missing updates. Google used multiple inventory sources, explicitly reconciled conflicting data rather than blindly trusting one source, and required that policy exceptions have a programmatically enforced owner and expiration.

## Translation to an LLM requirements interview

| ZT invariant | Implementable interview control | Concrete artifact / enforcement | Intent nodes |
|---|---|---|---|
| No implicit trust from location, ownership, or prior login | Do not accept a claim because it came from the repo, the user, an earlier accepted phase, a confident model, or a prestigious source. Each consequential claim carries explicit grounds and scope. | Claim record: `subject`, `claim`, `resource/scope`, `source`, `observed_at`, `method`, `confidence`, `contradiction_state`. Missing required fields prevents acceptance. | I1, I2, I7 |
| Protect resources, not network segments | Define protected interview resources: requirements, decisions, scope boundaries, irreversible actions, handoff assertions, and approval authority. Avoid treating the whole conversation as one undifferentiated trusted zone. | Resource registry with sensitivity/impact and permitted actions. | I2, I5, I6 |
| Least-privilege, granular access | Give each actor only the authority required for the action: models may propose and inspect; a model does not approve its own evidence or execute consequential changes unless explicitly delegated. Human authority is bounded to named decisions rather than a blanket approval. | Actor-action matrix; default-deny transition/tool policy; approval records name exact action and scope. | I5, I7 |
| Per-request/per-session evaluation | Re-evaluate each consequential claim acceptance, scope change, checkpoint transition, handoff finalization, and tool mutation. Approval of one claim/resource does not authorize another. | Transition request containing subject/resource/action/context; deterministic gate returns allow/deny/revise. | I2, I5, I6 |
| Dynamic policy using context | Decisions depend on evidence provenance, age, live-vs-static status, contradiction state, requirement criticality, affected surface, test results, and explicit user authority. | Versioned policy rules and decision log showing inputs and rule version. | I1, I2, I4, I5 |
| PDP separated from PEP | Separate deciding whether a transition is allowed from the mechanism that makes bypass impossible. A rubric/checklist is only a PE-like aid; it is not enforcement. | PDP: gate evaluator. PEP: orchestrator/script/tool wrapper that refuses state transition, artifact finalization, or mutation on deny. Log grant/deny/revoke. | I5, I6 |
| Continuous diagnostics and revocation | Re-evaluate accepted claims when their inputs change: file diff, source update, new contradiction, failed test, elapsed freshness window, or user scope change. Revoke or mark stale downstream conclusions. | Dependency graph from evidence to claims/decisions; event triggers; freshness TTL; invalidation/reopen state; no silent continuation. | I1, I4, I6 |
| Telemetry informs policy | Record denials, overrides, stale evidence, contradictions, test failures, and bypass attempts; use them to refine policy. Telemetry is itself protected and privacy-bounded. | Append-only decision/event log; periodic rule review; retention/redaction rules. | I1, I4, I6, I7 |
| All paths pass enforcement | No alternate route may finalize the handoff, mark a checkpoint complete, or invoke an authorized tool while bypassing the gate. | Enumerate transition and tool entry points; negative tests prove bypass attempts fail. | I5, I6 |
| Explicit exceptions | Exceptions are scoped, justified, owned, expiring, observable, and accompanied by remediation. | Exception record with owner, reason, affected resource/action, expiry, compensating control, and closure check. | I4, I5, I7 |

### Minimal request schema

```yaml
subject: model | user | reviewer | tool
resource: claim_id | decision_id | handoff | tool_action
action: propose | accept | revise | finalize | execute
context:
  evidence_ids: []
  evidence_freshness: current | stale | unknown
  contradiction_state: clear | open
  verification: static | executable | live
  policy_version: string
  delegated_authority: string | null
decision: allow | deny | revise | revoke
reason_codes: []
```

The schema is only useful if a PEP consumes it. A prose instruction to fill it in is not equivalent to enforcement.

## Applicability limits and category errors

1. **Access control is not epistemic proof.** ZTA decides whether a subject may act on a resource under policy. It does not prove that a source is true, that a requirement is complete, or that two reviewers are independent. Evidence validation and falsification (I2) and reviewer independence/anti-collusion (I3) need separate mechanisms.
2. **Zero trust does not eliminate trust.** NCSC explicitly says trust is built from signals; Jensen shows that implementations often shift implicit trust to identity providers, CAs, telemetry, policy engines, and administrators. The interview must enumerate these trust anchors and residual risk rather than claim to be trustless.
3. **Continuous does not mean constant interrogation.** NIST balances security with availability, usability, and cost. Use event-triggered and time-bounded revalidation at consequential boundaries, not an unending interview loop.
4. **A centralized gate is a high-value failure point.** NIST identifies policy-engine/administrator compromise, misconfiguration, and denial of service. The interview gate needs versioned/audited rules, recovery behavior, and fail-closed versus fail-operational decisions. The same LLM writing policy, evidence, and verdict is not independent assurance.
5. **Telemetry can be wrong, stale, or dangerous.** BeyondCorp reports difficult correlation, sparse identifiers, input errors, pipeline latency, and lockouts. NIST notes monitoring stores become attack targets and may create privacy risks. Evidence timestamps, conflict handling, source quality, redaction, and retention are mandatory.
6. **No single product or checklist implements ZT.** NCSC calls it an architectural approach requiring multiple controls and long migration. A prompt that says “never trust, always verify” adds no enforceable control.
7. **Legacy and external surfaces limit enforcement.** NIST excludes anonymous public/consumer processes from full enterprise policy control. NCSC documents legacy services that cannot integrate with modern authentication or policy engines. The interview must record uncovered/bypass paths and compensating controls rather than claim universal mediation.
8. **BeyondCorp is contextual evidence, not a universal blueprint.** Google had browser-heavy applications, substantial inventory/telemetry infrastructure, centralized gateways, and years for migration. The transferable invariants are explicit resource policy, current context, mediation, enforcement, revocation, and expiring exceptions—not Google's exact trust tiers or fleet machinery.
9. **Least privilege constrains authority, not useful cognition.** Artificially withholding relevant context from an interviewer may reduce requirement quality. Apply least privilege to mutation, approval, disclosure, and transition authority; use information minimization only where confidentiality or bias control justifies it.
10. **More verification can create availability and usability failures.** Incorrect denials, stale signals, and overly broad revocation can block legitimate work. Require reason codes, remediation paths, bounded human override, and audited expiry.

## Recommended interview invariants

- ZT-I1: No claim or transition inherits validity or authority solely from actor identity, prior phase success, source prestige, or workspace location.
- ZT-I2: Every consequential transition names subject, resource, action, and current context and is evaluated under a versioned policy.
- ZT-I3: Every allow/deny/revoke decision is enforced at every reachable transition/tool path; bypass tests are required.
- ZT-I4: Evidence-dependent decisions are revocable; freshness and contradiction events invalidate downstream state deterministically.
- ZT-I5: Authority is least-privilege and resource-specific; proposal, approval, enforcement, and exception ownership are distinguishable roles.
- ZT-I6: Exceptions are explicit, scoped, owned, expiring, logged, and paired with remediation.
- ZT-I7: Trust anchors, signal limitations, privacy/availability costs, uncovered surfaces, and residual risk are disclosed to the human decision owner.

## OBSERVATIONS

- NIST's core is not the slogan “never trust, always verify”; it is accurate, least-privilege, granular access under uncertainty, mediated by a decision point and an enforcement point.
- NIST says “per-request” in its operative definition and “per-session” in its tenets. The safe interview translation is re-evaluation at each consequential resource/action request or transition, with event-triggered reevaluation during longer sessions.
- BeyondCorp's strongest transferable lessons are complete mediation through gateways, current multi-source inventory, conflict reconciliation, sub-second-to-minutes freshness awareness, explainable denial/remediation, and expiring owned exceptions.
- Continuous diagnostics is a feedback loop: observe, decide, enforce, monitor, revoke, and refine. Merely collecting logs is not continuous enforcement.
- Zero-trust controls chiefly strengthen I4-I6. They support I1/I2 by demanding explicit current signals, but do not establish truth, completeness, or independent corroboration. They provide almost no native solution to I3.

## CLAIMS

- **High confidence:** An LLM requirements interview can faithfully adopt ZT's invariant-level control structure by treating claims, decisions, handoffs, and tool actions as resources and by enforcing subject-resource-action-context decisions at state transitions.
- **High confidence:** A requirements checklist, confidence score, or second model is not a PEP. Unless denial prevents finalization or action on every path, policy is advisory.
- **High confidence:** “Trust no model” is an unsafe simplification. The implementable requirement is “grant no implicit authority; make trust anchors and policy inputs explicit, scoped, current, auditable, and revocable.”
- **High confidence:** ZT cannot by itself guarantee epistemic validity, source independence, completeness, or freedom from correlated model error. Those are separate verification obligations.
- **Medium-high confidence:** Event-triggered revalidation with explicit freshness windows is the closest operational analogue to continuous diagnostics without making the interview unusably recursive.
- **Medium confidence:** A deterministic transition gate plus a bounded human override is the best PDP/PEP analogue, provided override scope, expiry, and residual risk are recorded and no bypass path exists.

## EXPAND

- Inspect the current ultimateinterview contract and enumerate every actual transition/finalization/tool path; test whether a deny result can be bypassed.
- Define the concrete freshness model: which evidence classes expire by time, which by repository/source change, and which only by explicit contradiction.
- Specify the trust-anchor registry: source systems, parsers, test runners, models, human approvers, and policy maintainers, including compromise and unavailability behavior.
- Add negative tests for stale evidence, contradictory sources, unowned/expired exceptions, policy-engine unavailability, and attempted self-approval.
- Coordinate with formal-methods on policy decidability and traceability; with distributed-verification on I3 independence; with adversarial-LLM on correlated error; and with requirements-human on bounded override and cognitive load.
