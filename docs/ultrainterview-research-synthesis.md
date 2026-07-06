# Ultrainterview Research Synthesis

작성일: 2026-07-05

이 문서는 `ultrainterview` 스킬에 DDD, 상태 모델링, 뉴로-심볼릭/월드모델, 수학적 질문 선택, fresh-context gating을 어떻게 반영할지 정리한 재사용 가능한 판단 근거다.

## 결론

`ultrainterview`는 더 많은 방법론을 항상 실행하는 스킬이 되면 안 된다. 좋은 구조는 다음 세 가지다.

1. 항상 켜지는 작은 core.
2. 위험 신호가 있을 때만 켜지는 conditional lenses.
3. 고위험 또는 seed-like handoff 직전에만 켜지는 readiness / fresh-context gate.

즉, DDD와 상태 모델링은 모든 SW 요구사항의 기본 체크리스트가 아니라 `domain/state` 렌즈다. 질문 선택도 엄밀한 POMDP나 Bayesian optimizer를 구현하는 것이 아니라, ambiguity ledger를 belief state처럼 쓰고 다음 질문을 실용적으로 점수화하는 방식이 맞다.

## Core Always On

항상 필요한 것은 방법론 이름이 아니라 구현 전 의사결정을 안전하게 만드는 최소 구조다.

- repo/docs를 먼저 조사한다.
- 문제, desired outcome, in/out scope, non-goals, decision boundaries를 잡는다.
- code fact와 human decision을 분리한다.
- requirement마다 evidence source를 남긴다.
- acceptance evidence와 verification surface를 만든다.
- 한 번에 가장 영향이 큰 human-decision question 하나만 묻는다.

## Conditional Lenses

| Lens | Trigger | Skip when |
| --- | --- | --- |
| `domain/state` | identity, lifecycle, state transition, invariant, ownership, consistency, concurrency, overloaded term | CRUD, reporting, simple validation, stable vocabulary, reversible local edit |
| `viewpoint` | support/admin/security/finance/compliance/operator/API 관점이 갈릴 수 있음 | single-owner local change |
| `goal/obstacle` | outcome이 불명확하거나 실패 조건이 구현을 바꿈 | 이미 구체적이고 테스트 가능한 이슈 |
| `misuse` | auth, privacy, money, destructive action, public input, fraud, irreversible write | read-only/cosmetic work |
| `quality` | fast, reliable, scalable, safe, compatible, observable 같은 말이 구현을 바꿈 | 품질 기준이 이미 측정 가능함 |
| `controlled-language` | trigger/condition/response/measurement가 불명확함 | acceptance criteria가 이미 testable함 |

## Domain / State Modeling

DDD에서 가져올 핵심은 tactical pattern 전체가 아니다. 인터뷰에 유용한 것은 다음 질문들이다.

- 이 용어가 screen, table, service, team마다 같은 뜻인가?
- 두 객체의 속성이 같으면 같은 객체인가, 같은 값일 뿐인가?
- 어떤 rule이 invariant이고, 어떤 것은 validation 또는 preference인가?
- 어떤 상태와 전이가 legal/illegal인가?
- 실패, retry, partial completion, recovery 상태는 무엇인가?
- 어떤 변경은 aggregate/root 같은 consistency boundary 안에서 함께 저장되어야 하는가?

이 접근은 Fowler의 DDD/Bounded Context 설명, Microsoft의 tactical DDD guidance, W3C SCXML, TLA+, Alloy 쪽 근거와 잘 맞는다. 다만 Microsoft DDD guidance도 단순 CRUD에는 더 단순한 접근이 적합하다고 말하므로, 이 렌즈는 조건부여야 한다.

## Question Selection

질문 생성과 모호성 수렴은 다음처럼 다룬다.

1. ledger를 belief state처럼 본다.
2. plausible requirement hypotheses와 implementation branches를 유지한다.
3. candidate questions를 만든다.
4. repo가 답할 수 있는 질문, 중복 질문, 구현에 영향 없는 질문을 버린다.
5. 남은 질문을 점수화한다.

```text
score(q) = impact(q) * branch_split(q) * uncertainty_reduction(q) * coverage(q)
           / (1 + user_cost(q) + redundancy(q))
```

이 식은 active learning, expected information gain, value of information, POMDP dialogue management에서 온 아이디어를 실용화한 것이다. 실제 스킬에서는 확률 모델을 엄밀하게 계산하지 않고 추정값으로 충분하다.

가장 좋은 질문은 "더 궁금한 질문"이 아니라 "답을 들으면 구현 분기가 가장 많이 사라지는 질문"이다.

## Readiness / Fresh-Context Gate

`docs/ultrainterview-improvement-proposal.md`의 좋은 아이디어는 draft spec을 바로 seed로 보지 않고, seed-readiness audit을 거치게 하는 것이다. 다만 이것도 항상 켜면 다시 과잉 절차가 된다.

Fresh-context gate는 다음 경우에만 켠다.

- depth가 `full`
- ambiguity score `3`이 handoff 근처까지 남아 있음
- score `2` gap이 behavior, data, security, rollout, recovery, verification을 바꿈
- spec이 다른 agent/team의 implementation seed가 됨
- security/privacy, data/schema, irreversible writes, external integration, performance/reliability, multi-stakeholder workflow가 있음
- 사용자가 independent gating 또는 fresh-context review를 요청함

fresh-context reviewer에게는 전체 대화가 아니라 draft spec, evidence ledger, relevant paths, audit checklist만 준다. 목적은 기존 인터뷰어의 암묵적 가정을 물려받지 않는 것이다.

## Why This Is Better Than Existing Local Skills

- Ouroboros interview는 Socratic question generation과 seed readiness에 강하지만, requirement-gap lenses를 risk-routed spec artifact로 묶지는 않는다.
- oh-my-codex deep-interview는 intent structuring과 ambiguity thresholds에 강하지만, DDD/state/misuse/quality/formalization 렌즈를 통합하지는 않는다.
- grill-me는 one-question-at-a-time pressure testing에 강하지만 stateless이고 durable evidence ledger나 final spec contract가 없다.
- `ultrainterview`는 이 셋을 모두 대체하려는 것이 아니라, brownfield 개발자가 coding 전에 spec을 만들기 위한 orchestration layer가 된다.

## Sources

- Martin Fowler, [Domain Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- Martin Fowler, [Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
- Microsoft, [Tactical Domain-Driven Design](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/tactical-domain-driven-design)
- Microsoft, [Design a DDD-oriented microservice](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/ddd-oriented-microservice)
- W3C, [SCXML](https://www.w3.org/TR/scxml/)
- Alloy, [Alloy Tools](https://alloytools.org/)
- Leslie Lamport, [Specifying and Verifying Systems With TLA+](https://lamport.azurewebsites.net/pubs/spec-and-verifying.pdf)
- Burr Settles, [Active Learning Literature Survey](https://burrsettles.com/pub/settles.activelearning.pdf)
- Young et al., [POMDP-Based Statistical Spoken Dialog Systems](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/young2013procieee.pdf)
- Alistair Mavin, [EARS](https://alistairmavin.com/ears/)
- NASA, [How to Write a Good Requirement](https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/)
- ISO, [ISO/IEC/IEEE 29148:2011](https://www.iso.org/standard/45171.html)
- Agile Alliance, [INVEST](https://agilealliance.org/glossary/invest/)
