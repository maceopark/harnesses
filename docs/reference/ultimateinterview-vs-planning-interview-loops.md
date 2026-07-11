# `ultimateinterview`와 Planning Interview Loop 비교

**작성일:** 2026-07-11

**범위:** Codex Plan Mode, oh-my-openagent Prometheus, Superpowers Brainstorming, 현재 개발 중인 `ultimateinterview`

**질문:** `ultimateinterview`의 높은 복잡성이 실제 우위를 보장하는가? 구조적으로 더 나은 이유가 있는가?

## 결론

`ultimateinterview`가 다른 도구보다 요구사항을 더 잘 발견한다는 보장은 아직 없다. 현재 증거가 지지하는 더 좁고 정확한 결론은 다음과 같다.

> `ultimateinterview`는 더 좋은 질문을 한다고 입증된 도구가 아니라, 불완전한 인터뷰를 완전하다고 선언하기 어렵게 만들고 누락을 관측·학습하도록 설계된 requirements-assurance system이다.

구조적 우위는 있다. 그러나 그 우위는 일반적인 대화 품질보다 증거 provenance, 거짓 완료 방지, handoff fidelity, 사후 escape 관측에 집중된다. 작은 변경이나 초기 아이디어 탐색에서는 이 구조가 이점보다 ceremony가 될 수 있다.

## 비교 대상은 완전히 같은 종류의 도구가 아니다

| 도구 | 주된 산출물 | 핵심 목적 |
| --- | --- | --- |
| Codex Plan Mode | 대화 안의 `<proposed_plan>` | 구현 결정을 남기지 않는 간결한 계획 |
| oh-my-openagent Prometheus | `.omo/plans/*.md` | 조사와 기본값으로 질문을 줄인 decision-complete 계획 |
| Superpowers | design spec + implementation plan | 소크라테스식 디자인 합의와 단계적 승인 |
| `ultimateinterview` | evidence ledger + Build Contract + handoff + postmortem lineage | brownfield 요구사항 assurance와 누락 학습 |

앞의 세 도구는 주로 “계획을 어떻게 완성하는가”를 다룬다. `ultimateinterview`는 인터뷰뿐 아니라 상태 보존, 증거 독립성, 계약 compilation, readiness gate, postmortem까지 소유한다. 따라서 복잡성의 일부는 인터뷰 루프 자체가 아니라 더 넓은 제품 경계에서 나온다.

## 각 도구의 인터뷰 루프

### Codex Plan Mode

```text
저장소 탐색
  ↓
Intent chat
  ├─ goal과 success criteria
  ├─ audience
  ├─ scope IN/OUT
  ├─ constraints와 current state
  └─ preferences와 trade-offs
  ↓ 안정되지 않음 → 계속 질문
  ↓ 안정됨
Implementation chat
  ├─ approach와 interfaces
  ├─ data flow와 failure modes
  ├─ tests와 acceptance
  └─ rollout, migration, compatibility
  ↓ 결정이 남음 → 계속 질문
  ↓ decision-complete
<proposed_plan>
```

Codex는 첫 질문 전에 적어도 한 번 non-mutating 탐색을 수행한다. 질문은 계획을 실제로 바꾸거나 중요한 가정을 확정하며, 저장소에서 답할 수 없는 것만 남긴다. `request_user_input` UI는 보통 한 개, 최대 세 개 질문과 각 질문의 2–3개 선택지를 지원한다. 최종 plan 전 별도의 approval brief는 없으며, 모델이 decision-complete라고 판단하면 plan을 출력한다.

중요한 한계는 Intent/Implementation phase가 별도의 deterministic state machine이 아니라 모델에 주입되는 대화 규칙이라는 점이다. 구조적으로 강제되는 것은 collaboration mode와 질문 UI schema다.

소스:

- [Plan Mode prompt](https://github.com/openai/codex/blob/5c19155cbd93bfa099016e7487259f61669823ff/codex-rs/collaboration-mode-templates/templates/plan.md)
- [`request_user_input` schema](https://github.com/openai/codex/blob/5c19155cbd93bfa099016e7487259f61669823ff/codex-rs/core/src/tools/handlers/request_user_input_spec.rs)

### oh-my-openagent Prometheus

Prometheus는 grounding 후 먼저 요청을 `CLEAR` 또는 `UNCLEAR`로 분류한다.

#### CLEAR

```text
조사
  ↓
Topology Lock: 독립적으로 성공/실패할 1–6개 component
  ↓
질문 후보 필터
  ├─ 증거로 답할 수 있음 → 조사
  ├─ reversible default로 답할 수 있음 → 기본값 채택
  └─ owner-decision → 사용자 질문
  ↓
가장 흐릿한 gap에 1–3개 질문
  ↓
Clearance Check
  ├─ objective 정의?
  ├─ scope IN/OUT 명시?
  ├─ approach 결정?
  ├─ test strategy 확인?
  └─ blocking ambiguity 없음?
  ↓ 하나라도 NO → 다음 인터뷰 턴
  ↓ 모두 YES
approval brief → 사용자 승인 → plan 생성
```

#### UNCLEAR

```text
넓은 조사
  ↓
best-practice defaults 선택·기록
  ↓
비가역적·파괴적·안전 중요 결정만 최대 한 질문
  ↓
사용자가 defaults를 veto할 approval brief
  ↓
Metis + high-accuracy review
```

따라서 요청이 더 모호할수록 오히려 질문이 줄 수 있다. Prometheus는 모호한 outcome을 사용자에게 다시 작성시키는 대신 조사, default selection, adversarial review를 사용한다.

소스:

- [ulw-plan routing](https://github.com/code-yeongyu/oh-my-openagent/blob/067f34b0e4e8c1011665aa65c833302c9b324b64/packages/shared-skills/skills/ulw-plan/SKILL.md)
- [CLEAR interview](https://github.com/code-yeongyu/oh-my-openagent/blob/067f34b0e4e8c1011665aa65c833302c9b324b64/packages/shared-skills/skills/ulw-plan/references/intent-clear.md)
- [UNCLEAR research/default loop](https://github.com/code-yeongyu/oh-my-openagent/blob/067f34b0e4e8c1011665aa65c833302c9b324b64/packages/shared-skills/skills/ulw-plan/references/intent-unclear.md)

### Superpowers Brainstorming

```text
project context 조사
  ↓
너무 큰 범위인가? → sub-project로 분해
  ↓
정확히 한 질문/메시지
  ├─ purpose
  ├─ constraints
  └─ success criteria
  ↓ 충분히 이해하지 못함 → 다음 한 질문
  ↓ 이해함
2–3개 approach와 recommendation
  ↓
design section별 승인
  ↓ 거절 → 수정 후 재제시
  ↓ 전체 승인
spec 작성·self-review
  ↓
작성된 spec 사용자 승인
  ↓
writing-plans
```

Superpowers는 메시지당 정확히 한 질문을 사용한다. 질문 자체에는 명시적인 clearance checklist가 없고 모델이 충분히 이해했다고 판단하면 approach comparison으로 넘어간다. 대신 질문이 끝난 뒤에도 design section별 승인과 written-spec 승인이 이어진다. 작은 변경에도 design gate를 생략하지 않는다.

소스:

- [brainstorming skill](https://github.com/obra/superpowers/blob/d884ae04edebef577e82ff7c4e143debd0bbec99/skills/brainstorming/SKILL.md)
- [writing-plans skill](https://github.com/obra/superpowers/blob/d884ae04edebef577e82ff7c4e143debd0bbec99/skills/writing-plans/SKILL.md)

### `ultimateinterview`

```text
ORIENT
  ├─ 기존 session resume
  ├─ repo + lessons 조사
  └─ depth와 lens state 선택
  ↓
DUMP + FRAME
  ├─ 사용자 brain dump
  └─ symptom/root cause 및 대안 framing challenge
  ↓
LOOP
  ├─ 답변을 typed evidence로 기록
  ├─ Due Now obligation 처리
  ├─ locality drift와 breadth 점검
  ├─ criticality로 다음 질문 선택
  ├─ 위험한 답변 pressure/triangulation
  ├─ falsification checkpoint
  ├─ open-world sweep
  └─ contrarian probe
  ↓ blocker 또는 미실행 protocol 존재 → LOOP
  ↓ interview_converged
ENDGAME
  ├─ flush
  ├─ sweep/probe
  ├─ checkpoint
  ├─ audit
  ├─ Build Contract compile
  ├─ fresh implementer test
  └─ implementation gate
```

`ultimateinterview`의 stop condition은 단순히 모델이 충분하다고 느끼는 시점이 아니다. ledger blocker, protocol obligation, Build Contract freshness와 traceability를 조합한다. 단, 이 gate는 “발견된 요구사항을 잃지 않고 판정 가능하게 만들었는가”를 확인할 수 있을 뿐, 발견되지 않은 요구사항의 부재를 증명하지는 못한다.

소스:

- [`ultimateinterview` runtime](../../.agents/skills/ultimateinterview/SKILL.md)
- [interview loop methods](../../.agents/skills/ultimateinterview/references/interview-loop.md)
- [deterministic readiness architecture](https://github.com/maceopark/harnesses/blob/32c565c12a2064ad516379fea8effc7afab0ac62/docs/ultimateinterview-deterministic-readiness-hardening.md)

## 구조적 우위

### 1. 거짓 완료 방지

Codex와 Superpowers의 종료는 최종적으로 모델의 self-assessment에 의존한다. `ultimateinterview`는 고위험 ambiguity, evidence independence, protocol completeness, handoff coverage, decidable predicates, executable verification, fresh-implementer findings를 fail-closed gate로 검사한다.

이것은 올바른 질문 생성을 보장하지 않지만, 불완전한 산출물을 implementation-ready라고 잘못 선언할 가능성을 낮춘다.

### 2. 답변과 증거의 권위를 분리

위험한 사용자 답변은 pressure follow-up, 독립적인 evidence group, 또는 명시적인 decision-authority override를 요구한다. 사용자 주장과 code/docs가 충돌하면 하나를 조용히 선택하지 않고 `Contested` 상태로 유지한다.

현재 작업 중인 schema v1은 단순한 channel 개수 대신 `independence_group`을 사용한다. 같은 원인에서 파생된 두 기록을 가짜 triangulation으로 세지 않으려는 개선이다.

### 3. Tunnel vision 방지

현재 설계는 breadth sweep, 두 번의 dry sweep, locality drift, sibling-track zoom-out, falsification checkpoint, L0–L3 contrarian probe를 사용한다. 이는 실제 escape corpus가 주로 `enumeration-miss`였다는 관찰과 맞닿아 있다.

### 4. Handoff synthesis-loss 검출

`ultimateinterview`는 다음 lineage를 추적한다.

```text
question/evidence
→ ledger entry
→ settled requirement
→ Build Contract REQ
→ acceptance predicate
→ verification
→ implementation diff
→ postmortem escape
```

인터뷰에서 잡은 요구사항이 handoff 작성 중 압축되거나 누락된 경우를 `synthesis-loss`로 분리할 수 있다. 이는 질문 품질과 문서 synthesis 품질을 혼동하지 않게 한다.

### 5. 누락을 다음 run의 학습 신호로 사용

```text
interview
→ contract
→ fresh-context implementation
→ independent postmortem
→ escape attribution
→ generalized lesson/guard
→ next interview
```

이 closed loop는 현재 가장 방어 가능한 차별점이다. 다른 도구도 좋은 plan을 만들 수 있지만, 어떤 질문을 놓쳤는지 측정하고 다음 run의 규칙으로 되돌리는 장치는 약하다.

## 우월성이 아직 입증되지 않은 이유

### 테스트는 discovery rate를 증명하지 않는다

현재 deterministic suite와 regression fixtures는 state transition, gate, crash recovery, lint verdict의 안정성을 검증한다. 프로젝트 문서도 이 결과가 실제 discovery rate 우위를 증명하지 않는다고 명시한다.

### 기존 3-arm benchmark에는 confound가 있다

[기존 benchmark](https://github.com/maceopark/harnesses/blob/32c565c12a2064ad516379fea8effc7afab0ac62/docs/ultimateinterview-three-arm-benchmark.md)에서는 `ultimateinterview` arm이 자기 범위에서 가장 좋은 spec 평가를 받았다. 특히 edge/misuse coverage와 traceability가 강했다. 그러나 다음 제약이 있다.

- 세 arm의 기능 범위가 달랐다.
- Claude arm은 planner와 implementer가 같은 context였다.
- 표본은 작은 Todo CLI 한 종류였다.
- `ultimateinterview`만 postmortem machinery를 보유했다.
- 따라서 “자기 escape를 발견했다”는 결과에는 elicitation뿐 아니라 observability 우위가 포함된다.

app-5도 17개 요구사항을 포착했지만 두 개의 predicate를 놓쳐 기록된 discovery rate는 89.5%였다. 완전성 보장은 아니다.

## 복잡성의 핵심 위험

가장 큰 위험은 requirements completeness가 아니라 protocol completeness를 최적화하는 것이다.

- 두 번 dry sweep을 기록해도 unknown unknown이 없다는 뜻은 아니다.
- residual이 0이어도 ledger에 들어오지 않은 requirement는 보이지 않는다.
- predicate lint가 통과해도 잘못된 predicate를 정교하게 적었을 수 있다.
- provenance가 정확해도 잘못된 framing 안의 evidence일 수 있다.
- 모든 script가 green이어도 semantic completeness는 증명되지 않는다.

Deterministic layer가 할 수 있는 일은 LLM discovery를 대체하는 것이 아니라, 발견된 내용을 잃거나 근거 이상으로 확신하지 못하게 하는 것이다.

또한 complexity 자체가 다음 비용을 만든다.

- 긴 session과 높은 사용자 fatigue
- agent가 protocol을 잘못 수행할 surface 증가
- 여러 state file과 schema migration 비용
- harness와 subagent capability 의존성
- 작은 변경에서 가치보다 큰 bookkeeping 비용

## 현재 작업 중인 변경의 의미

현재 미커밋 변경은 주로 다음을 강화한다.

- typed evidence와 causal independence
- open-world sweep와 locality drift
- bounded L0–L3 probe
- digest-bound Build Contract ABI
- readiness와 host-executable verification
- postmortem evidence provenance와 reward-hacking consistency

이들은 기존 failure mode에 대한 합리적인 구조적 대응이다. 그러나 새로운 controlled discovery-rate 실험을 추가한 것은 아니다. 따라서 현재 변경으로 주장할 수 있는 것은 assurance와 observability 강화이지, 질문 생성 우위의 실증이 아니다.

## 어디에서 더 낫고 어디에서 더 나쁜가

`ultimateinterview`가 구조적으로 적합한 경우:

- brownfield 변경
- 데이터, 권한, 상태, 복구, 외부 계약이 얽힌 변경
- planner와 implementer의 context가 분리된 경우
- missed requirement 비용이 인터뷰 비용보다 큰 경우
- 누락을 측정하고 다음 run에서 줄이려는 경우

더 가벼운 도구가 적합한 경우:

- 작고 되돌리기 쉬운 변경
- 초기 아이디어 탐색
- 빠른 디자인 대화
- 이미 충분히 결정된 PRD가 있는 경우
- postmortem까지 운영하지 않을 경우

## 필요한 검증 실험

우월성을 주장하려면 동일 조건의 controlled benchmark와 ablation이 필요하다.

### Arms

1. Codex Plan Mode
2. Superpowers Brainstorming
3. `ultimateinterview-core`
4. `ultimateinterview-full`

`core`는 evidence ledger, risk-ranked question, falsification checkpoint, Build Contract gate, postmortem만 유지한다. `full`은 lenses, open-world sweep, locality, advisory lanes, contrarian probe를 모두 사용한다.

### 통제 조건

- 동일한 brownfield repository와 request
- 동일한 모델 계열 또는 교차 균형 배치
- 동일한 fresh-context executor
- planner transcript를 보지 않는 blinded evaluator
- 동일한 runtime/manual QA budget
- 복수의 과제 유형과 난이도

### Primary metrics

- weighted escaped requirements
- 구현자가 임의로 결정해야 했던 material choices
- handoff synthesis-loss
- contradictory or over-constrained requirements
- scope creep와 forbidden-capability leakage

### Cost metrics

- 사용자 interaction 수와 시간
- token/tool 비용
- abandonment rate
- contract 작성부터 implementation start까지 걸린 시간
- protocol failure와 recovery 횟수

이 ablation이 있어야 어떤 메커니즘이 discovery를 올리고 어떤 메커니즘이 ceremony인지 분리할 수 있다.

## 전략적 포지셔닝

피해야 할 주장:

> 가장 좋은 인터뷰 도구

현재 증거에 맞는 주장:

> 모호한 brownfield 의도를 증거 기반의 반증 가능하고 기계 검증 가능한 Build Contract로 컴파일하는 requirements-assurance system

한 문장 판정:

> `ultimateinterview`는 질문을 더 잘한다는 증거는 아직 부족하지만, 잘못된 확신을 억제하고 누락을 관측·학습하는 구조에서는 가벼운 planning interview loop보다 분명히 강하다.
