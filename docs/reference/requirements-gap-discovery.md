# Requirements Gap Discovery Workflow

이 문서는 Socratic interview 외에 소프트웨어 개발 요구사항의 빈 곳을 찾기 위한 재사용 가능한 워크플로우다. 핵심 관점은 "더 많은 질문"이 아니라 서로 다른 증거 형태를 충돌시켜 빈칸을 드러내는 것이다.

## When to Use

- 요구사항 인터뷰를 했지만 예외 케이스, 비기능 요구사항, 운영 조건이 흐릿할 때
- stakeholder 간 말이 서로 맞지 않거나 용어가 다를 때
- user story는 있지만 상태, 이벤트, 실패 처리, 권한, 데이터 소유자가 불명확할 때
- "빠르게", "안정적으로", "보안성 있게" 같은 품질 요구가 측정 가능하지 않을 때
- 출시 후 운영, 지원, 감사, 장애 대응 요구사항이 빠졌을 가능성이 있을 때

## Epistemic Model

| Method | Finds gaps in | Evidence shape |
| --- | --- | --- |
| Socratic interview | reasoning, assumptions, definitions | stakeholder answers and contradictions |
| Contextual observation | tacit work, workarounds, real timing, exceptions | observed workflow, logs, tickets, diary notes |
| Viewpoint matrix | conflicting goals, missing owners, unrepresented stakeholders | perspective-by-perspective requirement table |
| EventStorming / Domain Storytelling | missing events, ambiguous handoffs, state ownership | event flow, actor-action-object stories |
| Goal + obstacle analysis | hidden failure conditions and brittle assumptions | goal tree, obstacle list, mitigation requirements |
| Misuse / abuse cases | security, fraud, privacy, safety, operational misuse | hostile/careless actor scenarios |
| Quality attribute scenarios | vague non-functional requirements | stimulus-response-measure scenario |
| Controlled language review | ambiguity, unverifiable wording | EARS or Given/When/Then requirements |

## Recommended Flow

### 1. Map the Domain Flow

Use EventStorming or Domain Storytelling before writing detailed requirements.

Capture:

- Domain events: `OrderPlaced`, `PaymentAuthorized`, `InventoryReserved`
- Actors: customer, admin, external service, operator, scheduler
- Work objects: order, invoice, token, shipment, approval
- State transitions: pending -> approved -> fulfilled -> cancelled
- Handoffs: who acts next, and what they need to know

Gap prompts:

- What event must have happened before this event is valid?
- What happens if this event is duplicated, delayed, or arrives out of order?
- Who owns the state change?
- What compensating action exists if the next step fails?
- Which event has no visible trigger?
- Which actor needs information that no previous step creates?

### 2. Build a Viewpoint Matrix

Create one row per viewpoint. Use this to catch contradictions and missing stakeholders.

| Viewpoint | Goals | Constraints | Data owned | Failure fears | Acceptance evidence | Open questions |
| --- | --- | --- | --- | --- | --- | --- |
| End user |  |  |  |  |  |  |
| Admin/operator |  |  |  |  |  |  |
| Customer support |  |  |  |  |  |  |
| Security/privacy |  |  |  |  |  |  |
| Compliance/legal |  |  |  |  |  |  |
| Finance/billing |  |  |  |  |  |  |
| Engineering/maintainer |  |  |  |  |  |  |
| External system/API |  |  |  |  |  |  |

Gap prompts:

- Which viewpoint is affected but not represented?
- Which requirement has no owner?
- Which data object has no owner, retention rule, or deletion rule?
- Which acceptance criterion is meaningful to one viewpoint but invisible to another?
- Which stakeholder can block release?

### 3. Convert Goals into Obstacles

For each important goal, write the success condition and then search for obstacles.

Template:

```text
Goal:
  The system shall <desired outcome>.

Assumptions:
  - <condition that must hold>

Obstacles:
  - <what can prevent the goal?>

Derived requirements:
  - <what the system must do to prevent, detect, recover, or escalate>

Residual risk:
  - <risk accepted or deferred>
```

Gap prompts:

- What must be true outside the system for this goal to succeed?
- What happens if that assumption is false?
- Can a user, service, batch job, or operator prevent the goal accidentally?
- What must be logged or surfaced when the goal fails?
- Is recovery manual, automatic, or impossible?

### 4. Add Misuse and Abuse Cases

For each core flow, add hostile, careless, overloaded, and unauthorized actors.

Template:

```text
Misuse actor:
  <attacker, unauthorized user, careless admin, overloaded operator>

Misuse goal:
  <what they try to do>

Damage:
  <business, privacy, security, safety, financial, or operational impact>

Required controls:
  Prevent:
  Detect:
  Rate-limit/throttle:
  Log/audit:
  Reverse/recover:
  Escalate:
```

Gap prompts:

- What should not be possible?
- What should be possible only with extra verification?
- What is allowed but suspicious at high volume?
- What must be auditable later?
- What damage cannot be undone?

### 5. Turn Quality Claims into Scenarios

Avoid vague requirements like "fast", "stable", "secure", or "scalable". Convert them into quality attribute scenarios.

Template:

```text
Quality attribute:
  <performance, availability, security, modifiability, observability, recovery, interoperability>

Source:
  <user, admin, attacker, service, batch job, operator>

Stimulus:
  <event or condition>

Environment:
  <normal load, peak load, degraded dependency, incident, migration, mobile network>

Artifact:
  <API, screen, worker, database, queue, external integration>

Response:
  <what the system does>

Response measure:
  <p95 latency, error budget, RTO, RPO, throughput, max data loss, alert time>
```

Gap prompts:

- Under what load or failure condition must this still hold?
- What is the measurable threshold?
- Who is alerted, how quickly, and with what context?
- What data loss is acceptable?
- How is the requirement tested before release?

### 6. Normalize Requirements with Controlled Language

Rewrite candidate requirements so ambiguity becomes visible.

Use EARS-style patterns:

```text
Ubiquitous:
  The <system> shall <response>.

Event-driven:
  When <trigger>, the <system> shall <response>.

State-driven:
  While <state>, the <system> shall <response>.

Conditional:
  If <condition>, then the <system> shall <response>.

Optional feature:
  Where <feature is included>, the <system> shall <response>.
```

Or Given/When/Then:

```text
Given <precondition>
When <trigger/action>
Then <observable outcome>
And <measurable or persisted evidence>
```

Gap prompts:

- Is the trigger explicit?
- Is the actor explicit?
- Is the system response observable?
- Is the exception path defined?
- Can this be verified without asking the author what they meant?

## Evidence Ledger

Track every requirement as a row with its source and proof path.

| ID | Requirement | Source | Viewpoint | Domain event/story | Failure or misuse case | Quality scenario | Acceptance evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 |  |  |  |  |  |  |  | Draft |

Recommended statuses:

- `Draft`: stated but not validated
- `Triangulated`: supported by at least two evidence types
- `Contested`: sources disagree
- `Blocked`: needs a decision, policy, or external fact
- `Accepted`: has owner, acceptance evidence, and release impact
- `Deferred`: intentionally out of scope with recorded risk

## Review Checklist

Before treating requirements as complete, check:

- Every important workflow has a normal path, exception path, and recovery path.
- Every state transition has an owner and trigger.
- Every external dependency has timeout, retry, fallback, and failure visibility rules.
- Every data object has ownership, retention, deletion, privacy, and audit rules where relevant.
- Every vague quality word has a measurable scenario.
- Every security-sensitive flow has misuse/abuse cases.
- Every stakeholder viewpoint has reviewed its relevant requirements.
- Every requirement can be tested, observed, or audited.
- Every unresolved assumption is recorded with an owner and deadline.

## Source Notes

- ISO/IEC/IEEE 29148 frames requirements engineering as elicitation, analysis, specification, validation, communication, and management across the lifecycle.
- Viewpoint-oriented requirements engineering organizes requirements from different stakeholder and system perspectives to expose conflicts and omissions.
- Ethnographic requirements work shows that observing real work reveals tacit practices and exceptions that interviews often miss.
- EventStorming and Domain Storytelling make domain events, actors, handoffs, and work objects explicit.
- Goal-oriented requirements engineering and KAOS obstacle analysis turn desired outcomes into explicit success theories and counterconditions.
- SEI's ATAM and Quality Attribute Workshop use scenarios to expose architecture-significant quality requirements and tradeoffs.
- Misuse cases complement use cases by eliciting what the system must prevent, detect, audit, or recover from.
- EARS reduces ambiguity by constraining natural-language requirements into explicit trigger/condition/response patterns.
