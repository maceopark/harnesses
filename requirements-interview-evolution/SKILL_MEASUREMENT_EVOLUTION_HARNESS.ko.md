# 스킬 측정·진화 하니스 설계 메모

## 1. 문제의식

프롬프트 엔지니어링, 컨텍스트 엔지니어링, 루프, 그래프 등 어떤 형식이든 좋은 스킬은 여전히 중요하다. 그러나 인간의 직관만으로 좋은 스킬을 안정적으로 만드는 데에는 한계가 있다. 스킬을 개선하려면 현재 스킬이 실제 과업에서 어느 정도의 성능을 내는지 판정할 수 있는 심판이 필요하다.

문제는 심판도 하나의 스킬이라는 점이다. 심판의 판정을 신뢰하려면 다시 심판의 심판이 필요하고, 이를 자유형 판단 스킬로 계속 만들면 무한 회귀가 발생한다.

이 회귀를 끊는 방법은 심판의 심판을 더 영리한 평가자로 만드는 것이 아니다. 가능한 한 판단하지 않고, 측정 프로토콜의 자명한 불변조건만 기계적으로 검사하는 장치로 만드는 것이다. 최하단 토대는 실행 가능한 결과, 고정된 fixture, 사전등록된 규칙, 사람이 봉인한 최소한의 규범이어야 한다.

## 2. 핵심 명제

좋은 스킬 생성은 다음 네 층을 분리해야 한다.

```text
Skill
  ↓ 실제 과업 수행
Task Judge
  ↓ 결과가 요구사항을 만족하는지 판정
Judge Auditor
  ↓ Task Judge가 올바른 측정 프로토콜을 따랐는지 검사
Frozen Ground
  ↓ 실행 가능한 사실·불변조건·사전등록·사람이 봉인한 규범
```

- `Skill`은 과업을 수행한다.
- `Task Judge`는 결과의 정확성·충실성·회귀를 평가한다.
- `Judge Auditor`는 평가 의견을 내지 않고 평가 절차의 불변조건만 검사한다.
- `Frozen Ground`는 더 아래의 심판을 요구하지 않는 기계적·규범적 토대다.

Human-in-the-Loop보다 Human-on-the-Loop가 적합하다. 인간은 모든 실행을 직접 채점하지 않고 다음에 책임을 진다.

- 무엇을 좋은 결과로 볼지 최초 규범을 봉인한다.
- 절대 허용하지 않을 손실과 위험을 정한다.
- 사전등록 이후의 amendment를 승인하거나 거부한다.
- 결정론적으로 해소할 수 없는 규범 충돌을 판정한다.
- 최종 승격에 책임진다.

## 3. 관련 접근에서 가져올 요소

### 3.1 Noo-style 과업 분해

큰 스킬을 한 번에 만들지 않는다. 먼저 전체 과업을 인지적 하위 과업의 트리로 분해하고, 독립적으로 측정 가능한 작은 스킬부터 만든다.

예를 들어 “PPT를 잘 만드는 스킬”은 하나의 스킬이 아니라 다음과 같은 과업 그래프로 분해할 수 있다.

```text
메시지 정의
├─ 청중과 목적 분석
├─ 스토리라인 구성
├─ 장표별 논증 분배
├─ 장표 카피 작성
├─ 시각 구조 설계
├─ 디자인 시스템 적용
└─ 발표 흐름 및 품질 검증
```

각 하위 스킬은 독립적인 입력·출력·실패 조건·평가법을 가져야 한다. 충분히 검증된 뒤에만 결합 스킬을 만든다.

### 3.2 Skill-α의 점진적 편집

스킬 생성은 한 번의 전면 재작성보다 국소 편집의 연속으로 다룬다.

```text
CREATE  새 규칙이나 절차 추가
UPDATE  기존 규칙 수정
MERGE   겹치거나 충돌하는 규칙 통합
PRUNE   잘못되거나 과도한 규칙 삭제
NOOP    현재 스킬 유지
```

각 편집 전후에 동일한 worker, anchored query, verifier, 환경을 사용한다. 편집 후 결과가 편집 전보다 좋아졌을 때만 rollback reward를 부여한다.

이 방식은 편집별 credit assignment를 개선하지만 verifier 문제 자체를 해결하지는 않는다. 국소 비교 한 번은 noisy sample이며, 국소 개선이 전체 task family의 개선을 보장하지 않는다. 따라서 rollback reward 위에 독립적인 Judge Auditor와 승격 게이트가 필요하다.

### 3.3 사전등록과 독립 비판

측정 전에 다음을 동결한다.

- 과업과 성공 조건
- 데이터 partition
- 평가 지표
- timeout과 retry 정책
- invalid·unsolvable·missing 처리
- 통계 분석법
- 승격과 중단 조건
- 예상 결과와 반대 가설

작성자와 비판자는 분리한다. 서로 다른 모델·벤더·프롬프트 계보의 reviewer가 자신이 작성하지 않은 명세와 기록을 공격한다. 이질성은 진실을 보장하지 않지만, 동일한 전제와 맹점을 공유할 위험을 줄인다.

## 4. Judge Auditor의 공리적 불변조건

Judge Auditor는 “이 결과가 좋은가?”를 자유롭게 판단하지 않는다. 다음 속성을 검사한다.

### 4.1 동일성

스킬 전후 비교에서 스킬 외의 조건이 동일해야 한다.

- 동일 worker와 model revision
- 동일 query와 repository revision
- 동일 tool과 environment
- 동일 seed 또는 동일 sampling protocol
- 동일 timeout과 retry 정책
- 동일 verifier와 rubric

### 4.2 대칭성

A/B 표시 순서를 뒤집어도 의미상 판정이 유지돼야 한다.

```text
judge(A, B) = A
judge(B, A) = B
```

이를 만족하지 않으면 position bias가 있다.

### 4.3 자기동일성

동일한 결과 두 개를 비교해 임의의 승자를 만들면 안 된다.

```text
judge(A, A) = tie
```

### 4.4 보존

평가기 입력과 출력의 개수 및 identity가 보존돼야 한다.

- 누락을 0점으로 조용히 변환하지 않는다.
- timeout을 일반 실패로 합치지 않는다.
- dropped pair를 분모에서 감추지 않는다.
- 조건마다 평가 모집단이 달라지지 않는다.
- 원시 입력에서 집계 지표까지 모든 변환을 추적할 수 있어야 한다.

### 4.5 상태 분리

최소한 다음 상태를 별도로 표현한다.

```text
pass
fail
invalid
unsolvable
timeout-never-produced
timeout-stalled
timeout-still-producing
instrument-error
```

### 4.6 재계산 가능성

원시 artifact만으로 점수, confidence interval, 사례별 비교, 승격 결정을 다시 계산할 수 있어야 한다.

### 4.7 정보 경계

Interviewer, Mutator, Skill Editor에 다음 정보가 노출되지 않아야 한다.

- holdout 내부 식별자와 결과
- gold patch와 test patch
- private owner oracle
- Judge의 내부 reasoning
- calibration fixture의 정답
- 거부된 blind finding

### 4.8 반례 민감성

정답 artifact에서 한 가지 중요한 사실만 고의로 바꾼 mutant를 넣었을 때 점수가 반드시 나빠져야 한다. 반대로 표현만 바꾼 의미 동일 artifact에는 점수가 안정적이어야 한다.

### 4.9 Null 보존

효과가 없는 `NOOP`이나 byte-identical 후보를 개선으로 승격시키면 안 된다.

### 4.10 실패 폐쇄

평가기 자체가 불완전하거나 protocol invariant를 위반하면 후보를 통과시키지 않는다. 이때 후보 실패와 instrument failure를 구분해 기록한다.

## 5. 하니스 구성

```text
1. Task Mapper
   큰 과업을 독립적인 cognitive task로 분해

2. Atomic Skill Contract
   입력·출력·권한·불변조건·실패 상태·검증법 정의

3. Evidence Store
   문서·실행 trace·실패·반례를 provenance와 함께 저장

4. Skill Editor
   CREATE / UPDATE / MERGE / PRUNE / NOOP 수행

5. Paired Runner
   편집 전후를 동일 anchor와 동일 조건에서 실행

6. Task Judge
   환경·테스트·상태 전이로 직접 판정하고,
   불가피한 의미 판단만 독립 LLM Judge에 위임

7. Judge Auditor
   공리적 불변조건과 metamorphic test 실행

8. Independent Critics
   이질적인 reviewer가 명세·Judge·결과를 독립 공격

9. Promotion Gate
   사례별 비회귀와 엄격한 개선을 확인

10. Human-on-the-Loop
    공리 변경·amendment·규범 충돌·최종 승격 책임
```

## 6. 점수 체계

단일 종합점수는 사용하지 않는 것이 원칙이다. 한 숫자는 심각한 실패를 다른 지표의 향상으로 상쇄할 수 있고, 평가기를 공략하기 쉽게 만든다.

다음과 같은 점수 벡터를 유지한다.

```yaml
validity:
  protocol_violations: 0
  leakage: 0
  missing_results: 0

correctness:
  passed: 18
  failed: 2
  invalid: 1
  unsolvable: 3

regression:
  improved_cases: 3
  unchanged_cases: 17
  regressed_cases: 0

skill_quality:
  omissions: 0
  inventions: 1
  redundant_rules: 2
  contradictions: 0

efficiency:
  questions: 4
  tokens: 8200
  tool_calls: 11

uncertainty:
  repetitions: 5
  pairwise_win_rate: 0.72
  confidence_interval: [0.55, 0.84]
```

승격은 가중합이 아니라 사전식 hard gate를 사용한다.

```text
모든 protocol invariant 통과
AND 모든 development 사례에서 baseline 대비 비회귀
AND 적어도 한 development 사례에서 엄격한 개선
AND validation repository family에서 비회귀
AND sealed holdout에서 사전등록된 절대 gate 통과
```

## 7. 인터뷰 스킬에 적용

### 7.1 현재 변이 전략의 초기 유지

새 평가 체계를 도입하는 첫 단계에서는 기존 인터뷰 스킬 변이를 유지한다.

```text
개발 실패
→ 기존 meta-strategist
→ REPLACE / DELETE / ADD 후보
→ 동일 조건 paired execution
→ 새 Task Judge
→ Judge Auditor
→ promotion gate
```

변이와 평가를 동시에 바꾸지 않는 이유는 인과 분리다. 성능 변화가 새 변이 전략 때문인지 새 평가 체계 때문인지 식별해야 한다.

### 7.2 구조화된 변이로 전환

평가 체계가 검증된 뒤 Markdown의 임의 위치가 아니라 policy primitive 단위로 편집한다.

| 기존 변이 | 구조화된 변이 |
| --- | --- |
| `ADD` | `CREATE` |
| `REPLACE` | `UPDATE` |
| `DELETE` | `PRUNE` |
| 없음 | `MERGE` |
| 없음 | `NOOP` |

예시:

```yaml
action: UPDATE
target: question_selection
before:
  strategy: highest_materiality
after:
  strategy: dependency_unlock
```

한 편집은 원칙적으로 하나의 인지 정책만 변경해야 한다. 질문 우선순위, 종료 조건, acceptance 생성, 권한 판정을 한 번에 바꾸면 rollback reward의 원인을 식별할 수 없다.

### 7.3 탐색 가능한 인터뷰 정책 축

질문 선택:

- risk-first
- expected information gain
- dependency unlock
- acceptance-first
- compatibility-first
- lowest-cost-first
- value-of-information per cost

질문 구성:

- 한 결정씩 질문
- 저위험 독립 결정을 묶어 질문
- binary question
- 2~3개 선택지
- 추천과 tradeoff 포함 여부

상태 갱신:

- 답변에 따른 dependent decision 전파
- 모순 발견 시 기존 결정 재개방
- `모름` 답변 시 repository investigation
- `상관없음` 답변 시 approved default
- scope 변경 시 decision graph 재계산

종료:

- material blocker set이 비었을 때
- acceptance scenario가 완성됐을 때
- 기대 정보가 질문비용보다 작을 때
- stagnation 시 non-ready 종료

계약 생성:

- requirement coverage
- non-goal
- compatibility invariant
- failure behavior
- state transition
- executable acceptance scenario
- provenance
- unresolved non-blocker

## 8. 변이 전략 자체의 발견

새 평가 체계는 좋은 스킬 후보뿐 아니라 좋은 변이 전략을 발견하는 reward function으로 사용할 수 있다.

```text
변이 전략
→ 스킬 편집
→ 인터뷰 실행
→ 평가
→ 편집 성과
→ 전략 성과 누적
→ 다음 변이 전략 선택
```

스킬 편집 reward와 변이 전략 reward를 구분한다.

```text
편집 reward:
  이 편집으로 생성된 스킬이 baseline보다 좋아졌는가?

전략 reward:
  이 전략이 여러 세대와 여러 task family에서
  좋은 편집을 안정적으로 생성했는가?
```

변이 전략 genotype 예시:

```yaml
strategy:
  evidence_selection:
    failure_family: omission
    minimum_independent_cases: 2
  target_selection:
    component: question_selection
    choose: highest_regression_contributor
  operator:
    type: UPDATE
  scope:
    max_policy_primitives: 1
  validation:
    require_per_case_non_regression: true
```

탐색할 수 있는 항목:

- 어떤 failure class를 mutation signal로 사용할지
- 몇 개의 독립 사례에서 반복돼야 일반화할지
- 어떤 policy component를 우선 수정할지
- 어떤 편집 연산자를 사용할지
- evidence batch 크기
- 편집 크기 제한
- 실패 시 rollback 여부
- lineage 지속 세대 수
- exploration/exploitation 비율
- 과거 성공 전략 재사용률

전략 성과도 단일 점수보다 사전식 비교를 사용한다.

```text
1. hard invariant 위반 최소화
2. 사례별 회귀 최소화
3. validation 통과율 최대화
4. 독립 task family 개선 수 최대화
5. 편집 복잡도 최소화
6. 평가 비용 최소화
```

## 9. 이중 진화와 evaluator epoch

스킬과 변이 전략은 함께 학습할 수 있지만 evaluator는 같은 epoch 안에서 바뀌면 안 된다.

```text
┌─ Skill evolution ──────────────────┐
│ mutation strategy → skill edit     │
│ → execution → evaluation → reward  │
└────────────────────────────────────┘
                 ↓
          strategy outcomes
                 ↓
┌─ Strategy evolution ───────────────┐
│ strategy mutation → application    │
│ → cross-family outcomes → reward   │
└────────────────────────────────────┘
```

Evaluator는 epoch 단위로 동결한다.

```text
Epoch N:
  evaluator-N 동결
  → 모든 skill/strategy 후보 평가
  → winner와 전체 artifact 봉인

Epoch N+1 준비:
  evaluator challenger를 calibration fixture로 검증
  → 통과하면 evaluator-N+1 동결
  → 이전 winner를 새 evaluator로 replay
```

Evaluator candidate는 다른 자유형 evaluator의 선호만으로 승격하지 않는다.

```text
Evaluator candidate
→ 고정 calibration fixture 실행
→ deterministic expected verdict와 비교
→ symmetry / identity / mutation sensitivity test
→ 조건별 confusion matrix 계산
→ 기존 evaluator 오류의 strict subset일 때만 승격
```

## 10. 평가기 공략 방지

변이 전략을 자동 탐색하면 평가기의 허점을 찾는 속도도 빨라진다. 예상되는 보상 해킹은 다음과 같다.

- 특정 키워드 반복으로 Judge 점수 올리기
- 질문을 과도하게 늘려 owner recall만 올리기
- 항상 non-ready로 종료해 invention 회피하기
- 평가되지 않는 acceptance 항목 생략하기
- timeout을 유발해 어려운 사례를 분모에서 제거하기
- Judge가 선호하는 문체를 모방하기

대응책:

- Mutator에 Judge 내부 reasoning을 공개하지 않는다.
- calibration fixture와 metamorphic mutant를 비공개로 둔다.
- 결과 누락과 timeout은 fail-closed 처리한다.
- A/B 순서 반전과 identity test를 반복한다.
- evaluator가 바뀌면 기존 승자를 cross-judge replay한다.
- evaluator rotation과 adversarial holdout을 사용한다.
- 복잡도와 불필요한 질문에 비용을 부여한다.
- 원시 artifact와 집계 결과를 모두 보존한다.

## 11. 현재 SWE-bench 인터뷰 하니스와의 연결

현재 하니스가 이미 가진 요소:

- public/sealed 정보 분리
- development/validation/holdout partition
- 사례별 paired non-regression
- candidate mutation
- evaluator epoch
- 2×2 skill/evaluator replay
- artifact digest와 독립 verifier
- promotion 전 decision sealing
- development-only strategy outcome 집계

추가로 필요한 요소:

1. 자연어 `SKILL.md`를 atomic skill graph로 분해하는 schema
2. Judge 공리와 metamorphic test catalog
3. `CREATE/UPDATE/MERGE/PRUNE/NOOP` 편집 단위 rollback runner
4. Judge calibration용 known-good, known-bad, ambiguous, unsolvable fixture
5. structured mutation strategy genotype와 outcome ledger
6. invalid·unsolvable·instrument failure를 분리하는 닫힌 상태 모델

현재 SWE-bench 파일럿은 하니스 무결성과 “질문하면 안 되는 것을 묻지 않는가”를 시험하는 데 유용하다. 그러나 공개적으로 검사 가능한 development/validation 사례에서 명시적 Owner material decision이 매우 적어 질문 순서, 분기, 정보이득 정책을 발견하기에는 부족하다.

추가 corpus는 다음 유형을 포함해야 한다.

- material decision이 없는 사례
- 단일 material decision 사례
- 독립 decision 2~4개
- 종속 decision 2~5개
- 답변에 따라 새 decision이 열리는 사례
- 모순 때문에 이전 결정을 재개방하는 사례
- repository 조사와 Owner 질문이 섞인 사례
- 안전상 자동 default가 금지된 사례
- 정답이 존재하지 않거나 식별 불가능한 사례

## 12. 단계적 도입 계획

### Phase 1: 평가 체계 교체

- 기존 v5와 기존 `ADD/DELETE/REPLACE` mutation 유지
- 새 Judge Auditor 추가
- 기존 Judge와 새 Judge의 2×2 replay
- calibration fixture와 metamorphic test 구축
- 기존 실험 결과의 재계산 가능성 검증

성공 조건은 기존 결과를 설명할 수 있고, 알려진 측정 결함을 모두 탐지하며, byte-identical 후보를 개선으로 승격하지 않는 것이다.

### Phase 2: 구조화된 스킬 편집

- atomic policy schema 도입
- `CREATE/UPDATE/MERGE/PRUNE/NOOP` 구현
- 한 편집당 하나의 policy primitive만 변경
- edit-level rollback reward 기록
- Markdown `SKILL.md`는 구조화된 정책에서 컴파일

### Phase 3: 변이 전략 탐색

- 전략 genotype과 mutation operator 구현
- strategy outcome ledger 구축
- exhaustive, beam, evolutionary, bandit 탐색 비교
- development family에서 전략 학습
- validation과 holdout을 전략 생성 입력에서 봉인

### Phase 4: Evaluator 진화

- calibration fixture 기반 evaluator challenger 평가
- Judge Auditor invariant를 hard gate로 적용
- evaluator identity를 epoch 동안 동결
- evaluator 승격 후 과거 winner 전체 replay

### Phase 5: 규모 확장

- decision-lattice 사례 확장
- repository family 단위 partition
- 다양한 worker와 모델 계보로 transfer test
- 인터뷰 이외의 작은 스킬로 도메인 이전 검증

## 13. 최종 정의

이 시스템의 핵심 산출물은 스킬 생성기가 아니라 다음 구조다.

> 작은 스킬 편집을 수행하고, 동일 조건에서 전후 차이를 측정하며, 심판의 측정 행위는 공리적 불변조건으로 감사하고, 인간은 그 공리와 승격에만 책임지는 스킬 측정·진화 하니스.

좋은 evaluator가 확보되면 좋은 스킬을 고르는 데서 끝나지 않는다. 어떤 failure signal, 편집 연산자, evidence granularity, rollback 규칙이 여러 task family에서 좋은 스킬을 반복적으로 만드는지까지 발견할 수 있다.

단, 변이기와 evaluator가 같은 epoch 안에서 서로를 보며 동시에 바뀌면 점수의 의미가 사라진다. 스킬 편집, 변이 전략, 평가기라는 세 층을 분리하고 evaluator를 epoch 동안 동결하는 것이 전체 설계의 핵심 불변조건이다.

## 14. 참고 자료

- Jihoon Jeong, [Karpathy Says AI Can’t Audit Itself. Our Instruments Can’t Either](https://medium.com/@hiconcep/karpathy-says-ai-cant-audit-itself-our-instruments-can-t-either-f2d3b4258bf5)
- JKF, [Skill-α: RL로 에이전트 스킬을 점진적으로 만드는 방법](https://jkf87.github.io/posts/2026-08-05-skill-alpha-progressive-agent-skill-rl)
- Shen et al., [Progressive Agent Skill Generation via Reinforcement Learning](https://arxiv.org/abs/2608.01678)
- [Skill-α repository](https://github.com/ejhshen/skill-alpha)
- [Organum](https://ludex-lab.github.io/organum/)
- [Ludex Measurement Records](https://ludex-lab.github.io/measurements.html)
- [Karpathy Autoresearch](https://github.com/karpathy/autoresearch)
- Bilgic and Getoor, [Value of Information Lattice](https://arxiv.org/abs/1401.3881)
- [Active Task Disambiguation with LLMs](https://arxiv.org/abs/2502.04485)
- [QuestBench](https://arxiv.org/abs/2503.22674)
