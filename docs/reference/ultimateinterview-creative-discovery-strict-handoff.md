# Ultimateinterview: Creative Discovery, Strict Handoff Compiler

**작성일:** 2026-07-13  
**상태:** compiler-only 스킬에 구현된 현재 아키텍처의 설계 근거
**범위:** discovery, authority compilation, implementation handoff의 최소 계약

## 1. 목적

`ultimateinterview`의 목적은 다음 하나다.

> 자유로운 대화와 저장소 관찰에서 발견한 내용을, 권한이 확인되고 검증 가능한 Build Contract로 컴파일한다.

이 설계는 두 원칙만 따른다.

1. **Consensus is not authorization.** 모델이나 reviewer의 합의는 사용자 결정을 대신하지 않는다.
2. **Creativity belongs in discovery; strictness belongs in the compiler.** 발견 방법은 자유롭게 두고, 구현으로 넘어가는 경계만 fail-closed로 검사한다.

이 원칙을 직접 강화하지 않는 workflow, taxonomy, score, counter, sweep, reviewer ceremony는 기본 경로에 두지 않는다.

## 2. 최소 구조

```text
CREATIVE DISCOVERY
  conversation, repo, docs, tests, config, history,
  research, scenarios, prototypes, optional reviewers
        |
        v
UNSEALED DISCOVERY RECORD
  facts, proposals, assumptions, conflicts,
  owner decisions, delegations, open questions
        |
        v
STRICT AUTHORITY COMPILER
  validate authority, scope, derivation, acceptance,
  verification, and unresolved decisions
        |
        +-- blocked -> return owner decision to user
        |
        v
BUILD CONTRACT
```

Discovery record의 내용은 그 자체로 normative하지 않다. 구현 명령은 compiler를 통과한 Build Contract에만 존재한다.

## 3. Creative Discovery

Discovery는 정해진 질문 순서나 coverage taxonomy 없이 진행한다.

- 사용자 답변이 여는 branch를 자유롭게 추적한다.
- 무엇이 만들어지는지를 materially 바꿀 다음 질문을 고른다.
- 저장소가 답할 수 있는 사실은 사용자에게 묻기 전에 조사한다.
- 질문보다 관찰이 유리하면 코드, 문서, 테스트, 설정, 관련 history 또는 작은 prototype을 사용한다.
- recommendation, scenario, assumption은 proposal로 기록하며 settled decision으로 승격하지 않는다.
- 충돌하는 사용자 설명과 repository evidence를 조용히 해소하지 않는다.

권장 prompt shape:

```text
Discover ambiguities, assumptions, and blind spots that could materially
change [goal]. Inspect the relevant repo, docs, tests, configuration, and
history whenever observation would reveal more than asking. Ask the owner
when a choice requires owner authority. Keep proposals and assumptions
unsettled until they are explicitly authorized.
```

Fresh-context review는 필요할 때 사용할 수 있는 discovery 도구다. 의무 횟수, risk-trigger, readiness gate가 아니다. Reviewer는 finding만 반환하며, finding과 reviewer consensus에는 결정 권한이 없다.

## 4. Authority Register

Discovery 중 확인된 권한은 하나의 register로 기록한다. 각 항목은 최소한 다음을 가진다.

- stable authority ID
- authority kind
- owner 또는 canonical artifact
- 결정 내용 또는 delegation 범위
- 제약과 보존해야 할 observable behavior
- source와 version
- status
- 충돌 및 supersession 관계

Normative clause를 허가할 수 있는 authority는 다음뿐이다.

1. **Explicit owner decision** — 식별된 owner가 명시적으로 확정한 결정
2. **Canonical owner-approved contract** — 적용 범위, version, precedence가 식별된 기존 계약
3. **Bounded explicit delegation** — decision class, scope, constraints가 명시된 위임

다음은 authority가 아니다.

- repository의 현재 동작
- 일반 문서, 테스트 또는 설정
- research와 conventional default
- model recommendation
- assumption 또는 owner의 침묵
- reviewer finding, confidence 또는 consensus
- 대화가 계속되었다는 사실

Repository evidence는 authority를 지지하거나 반박할 수 있지만 스스로 product policy를 승인하지 않는다. Delegation은 추론하거나 확대하거나 재위임할 수 없다. 권한이 불확실하면 compiler는 owner decision으로 취급하고 차단한다.

## 5. Strict Authority Compiler

Compiler는 발견하거나 추천하지 않는다. 입력을 정규화하고 다음 조건을 fail-closed로 검사한다.

### 5.1 Clause authority

모든 normative clause는 적용 가능한 authority ID를 가져야 한다. Supporting evidence는 authority와 별도로 기록한다.

### 5.2 Authority scope

Authority의 scope와 constraints가 clause 전체를 허용해야 한다. 넓거나 모호한 delegation으로 product choice를 채우지 않는다.

Owner authority가 필요한 선택의 예시는 다음과 같으며, 이 목록은 exhaustive하지 않다.

- user-visible behavior와 UX
- scope와 non-goals
- 권리, 의무, actor 및 authorization ownership
- retention, deletion 및 lifecycle
- failure, retry 및 recovery semantics
- irreversible migration 또는 data loss
- compatibility floor
- numeric quality threshold

### 5.3 Conflict and settlement

Authority source가 충돌하거나 precedence가 불명확하면 compiler가 임의로 해소하지 않는다. Owner에게 반환한다.

### 5.4 Acceptance derivation

Acceptance predicate와 failure outcome은 authorized requirement에서만 파생한다. Test oracle을 작성하기 위해 새로운 behavior를 선택해야 한다면 compilation을 차단한다.

Acceptance는 가능한 경우 다음 형태로 표현한다.

```text
precondition/input -> action -> observable result -> applicable failure result
```

### 5.5 Traceability

모든 normative requirement는 다음 연결을 가져야 한다.

```text
authority -> requirement -> acceptance -> verification
```

### 5.6 Blocking diagnostics

다음 중 하나라도 있으면 Build Contract를 생성하지 않는다.

- missing authority
- invalid or over-broad delegation
- unresolved authority conflict
- unresolved owner decision
- acceptance가 도입한 unauthorized behavior
- unverifiable normative requirement
- missing requirement-to-verification trace

Compiler는 빈칸을 model default나 consensus로 채우지 않는다.

## 6. Build Contract

Sealed Build Contract에는 compiler가 승인한 내용만 포함한다.

- goal
- scope와 non-goals
- observable behavior와 failure behavior
- normative clause별 authority reference
- explicit decision boundaries와 bounded delegations
- acceptance predicates
- verification commands 또는 scenarios
- requirement-to-acceptance-to-verification traceability

Implementer는 특정 제품, agent runtime 또는 orchestration substrate에 고정되지 않은 coding agent다. Build Contract와 repository access만으로 구현할 수 있어야 하며, bounded delegation 안에서 internal architecture, file/module structure, algorithm, test organization을 결정할 수 있다. Settled observable behavior를 바꾸거나 delegation 밖의 product decision을 만들 수 없다.

구현 중 새 owner decision이 발견되면 consensus 대상이 아니라 사용자에게 반환하며, 기존 Build Contract를 자동 확장하지 않는다.
## 7. Downstream Evaluation Loop

Build Contract의 효용은 구현 완료 후 실제 결과와 비교해 평가한다. 이 단계는 `ultimateinterview-postmortem`의 핵심인 **spec-vs-implementation divergence audit**를 단순화해 유지한다.

### 7.1 Coding-agent implementation return

어떤 coding agent가 구현하더라도 동일하게 이해할 수 있도록 Build Contract는 substrate-neutral handback protocol을 포함한다. 구현자는 완료 시 현재 Build Contract digest에 결합된 `implementation-return.json`을 남긴다.

- 각 requirement와 verification의 실제 outcome
- 변경한 repository path
- 실제 실행한 command와 exit/result
- 존재하는 evidence artifact
- spec이 강제하지 않아 구현 중 내린 결정과 이유
- `not-run`, `blocked`, `failed`를 포함한 정직한 미완료 상태

Implementation Return은 구현자의 self-report이지 최종 평가가 아니다. Coding agent가 이를 누락하거나 contract digest와 맞지 않게 작성해도 postmortem은 중단하지 않는다. 해당 축을 missing evidence 또는 process gap으로 기록하고 repository-observed evidence만으로 평가를 계속하며, 구현 의도는 추정하지 않는다.

### 7.2 Independent postmortem evaluator

Evaluator는 구현자와 분리된 `ultimateinterview-postmortem` skill이다. 구현 coding agent의 종류, memory, 내부 state 또는 execution substrate에 의존하지 않는다.

Postmortem의 primary inputs는 현재 Build Contract, before/after repository state 또는 실제 diff, repository의 현재 상태, 직접 관찰 가능한 verification 결과다. 실행할 수 없는 verification은 이유와 함께 `unverifiable`로 남긴다. Implementation Return, decision log, PR 설명, commit message, 구현자가 만든 artifact는 존재할 때만 사용하는 optional evidence다.

Postmortem은 이 입력을 직접 수집해 bounded evidence bundle을 만든다. 구현자가 작성한 자체 postmortem은 참고 evidence일 뿐 독립 평가로 인정하지 않는다. 구현자와 같은 agent 또는 context가 평가를 시작했다면 spec과 diff만 받은 fresh-context evaluator에게 양방향 inventory를 맡긴다.

### 7.3 Bidirectional audit

Evaluator는 두 방향을 모두 확인한다.

```text
each implementation change -> authorized requirement or delegation
each contract requirement  -> implementation location and verification evidence
```

각 requirement와 unmatched implementation behavior를 다음 중 하나로 분류한다.

- `fulfilled` — authorized requirement가 구현되고 검증됨
- `escaped-requirement` — 구현에 필요했지만 Build Contract에 없었음
- `scope-drift` — Build Contract에 있지만 구현되지 않았고 defer되지 않음
- `divergent-implementation` — authorized behavior 또는 decision boundary와 다르게 구현됨
- `deferred-outcome` — 명시적으로 defer된 결정의 실제 결과
- `unverifiable` — 결과를 판정할 evidence가 부족함

### 7.4 Evaluation authority

Evaluator는 divergence를 발견하고 분류할 뿐 새 product decision을 승인하지 않는다.

- owner-authorized behavior를 뒤집은 divergence는 사용자 재결정으로 반환한다.
- escaped requirement가 owner authority를 요구하면 사용자에게 반환한다.
- implementation consensus, passing tests 또는 evaluator recommendation은 contract authority를 변경하지 않는다.
- evaluation 결과로 Build Contract나 implementation을 자동 수정하지 않는다.

최소 산출물은 evidence scope, divergence table, missing evidence, owner에게 반환할 결정 목록이다. 교훈은 다음 discovery의 관찰 대상을 개선할 수 있지만 새 taxonomy나 mandatory interview ceremony를 자동 생성하지 않는다.

### 7.5 `ultimateinterview-postmortem` 단순화 방향

기본 경로에서 유지할 책임:

- current contract에 binding된 implementation return 검증
- 실제 diff와 verification evidence의 bounded packing
- requirement와 implementation의 양방향 inventory
- divergence classification과 evidence citation
- owner 재결정이 필요한 divergence의 명시적 반환
- 독립적인 postmortem report 생성
- coding agent의 협조 여부와 무관한 repository-observed fallback

기본 경로에서 제거할 책임:

- lens attribution
- Wonder generalization
- lessons routing과 Fired/Caught lifecycle
- ontology 및 discovery-rate calibration
- schema version별 중복 report ceremony

Receipt signature, artifact digest, property observation 같은 high-assurance 검증은 core divergence audit와 분리된 optional adapter로 둔다. 기본 evaluator는 evidence가 없거나 신뢰할 수 없을 때 결과를 추정하지 않고 `unverifiable`로 분류한다.

## 8. 명시적 제외

다음은 discovery completeness 또는 implementation readiness의 근거로 사용하지 않는다.

- ambiguity score 또는 question score
- lexical signal coverage
- interaction counter
- fixed taxonomy 또는 mandatory sweep
- reviewer 수, review 횟수 또는 consensus
- 모든 blind spot을 발견했다는 주장
- prototype 및 test history 자체

Research, comparison, prototype chronology, 개별 test repair plan은 이 handoff의 실행 계약이 아니다. 필요한 경우 별도 evidence로 참조하되 compiler authority를 부여하지 않는다.

## 9. 성공 조건

새 설계는 다음을 만족해야 한다.

1. Discovery가 workflow bookkeeping보다 사용자 답변과 실제 evidence에 집중한다.
2. Reviewer, model, repository fact 또는 conventional default가 owner decision을 제조할 수 없다.
3. 모든 normative clause가 유효한 authority와 검증 가능한 acceptance에 연결된다.
4. Compiler가 새로운 behavior, default 또는 delegation을 발명하지 않는다.
5. Unresolved owner decision이나 authority conflict가 있으면 implementation-ready가 될 수 없다.
6. Implementer가 위임 범위 밖의 product behavior를 결정할 필요가 없다.
7. 구현 결과와 Build Contract를 양방향으로 비교하고 divergence와 missing evidence를 구분할 수 있다.
8. Evaluator가 divergence를 발견하더라도 owner decision을 대신하거나 contract를 자동 수정하지 않는다.
9. Postmortem이 특정 coding agent나 execution substrate에 의존하지 않고 repository evidence만으로도 평가를 완료할 수 있다.

> 인터뷰를 더 통제하지 말고 더 잘 관찰하게 하라. 모델의 창의성은 discovery에 사용하고, 결정 권한과 검증 가능성은 handoff compiler에서 강제하라.
