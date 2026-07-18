# Senior Owner + Latent Frontier 전환 핸드오프 v1

## 1. 문서 상태

- 상태: 구현 승인된 설계 핸드오프
- 대상: `measure-contract-drift` discovery live run
- 목표: case별 완전한 Owner World Model을 정답지로 사용하는 구조를 제거하고, 하나의 공유 Senior Software Engineer owner와 숨겨진 latent frontier 평가로 전환한다.
- 변경 종류: 평가 의미론 변경. 기존 G00 결과와 점수는 새 구조의 결과와 직접 비교하지 않는다.
- 구현 범위: owner 응답, authority 생성, coverage 평가, train/selection/final 분리, artifact/receipt, 테스트와 문서 갱신
- 비목표: seed skill 또는 고정 Build Contract 컴파일러의 계약 표면을 진화시키는 것

이 문서는 구현자가 이전 대화 없이도 작업을 시작할 수 있는 기준 문서다. 기존 설계 철학 문서의 Owner World Model, unresolved owner item, discovery success 관련 설명과 충돌하면 이 문서가 우선한다.

## 2. 해결하려는 문제

현재 harness는 case마다 숨겨진 Owner Card를 두고, candidate가 카드의 모든 material item을 질문으로 찾아야 성공하는 방식이다. 이 방식은 고정된 정답에 대한 재현 가능한 recall은 측정하지만 다음 두 가정을 필요로 한다.

1. 카드 작성자가 현실의 중요한 의사결정을 충분히 열거했다.
2. 좋은 인터뷰란 그 열거된 항목을 빠짐없이 복원하는 것이다.

첫 번째 가정은 현실적으로 충족할 수 없다. 더 중요한 blind spot이 카드 밖에 있을 수 있고, 고정 카드에 오래 최적화하면 인터뷰 알고리즘이 아니라 카드 taxonomy를 학습한다. G00의 train end-to-end success `0/80`도 상당 부분 이 의미론에서 생겼다. 후보가 유효한 결정을 만들고 owner가 합리적인 선택을 했더라도, 카드에 적힌 다른 항목을 묻지 않으면 `unresolved-owner-item`으로 구현이 차단되었다.

새 실험이 묻는 질문은 다음과 같다.

> 동일한 시니어 엔지니어 owner를 상대할 때, 어떤 인터뷰 전략이 모델 안의 잠재적인 material decision 공간을 적은 질문으로 더 넓고 깊게 드러내는가?

이 질문에는 완전한 정답지가 없다. 따라서 절대적 완전성을 주장하지 않고, 고정된 생성·평가 프로토콜 아래의 상대적 coverage를 측정한다.

## 3. 현재 코드에서 제거해야 하는 의미

다음 표면은 현 구조의 핵심 결합 지점이다.

| 현재 표면 | 현재 의미 | 새 의미 |
|---|---|---|
| `discovery-study.json:owner_cards_dir` | case별 숨은 정답 디렉터리 | 제거하고 하나의 `owner_persona` 경로로 교체 |
| `discovery.py:OwnerCard` | 미리 열거된 owner authority | legacy 결과 재현용 타입으로만 남기거나 제거 |
| `discovery.py:selection_from_owner_exchange` | 카드의 `owner_statement`를 authority로 복사 | owner가 선택한 candidate option의 `normative_statement`를 authority로 복사 |
| `discovery_backend.py:_resolve_owner` | 질문을 카드 item과 매칭 | 공유 persona와 case-local decision history로 옵션 하나를 선택 |
| `discovery_backend.py:interview` | starter repository를 조사하며 질문 생성 | 빈 discovery workspace에서 open requirement만으로 질문 생성 |
| `discovery_backend.py:interview_blockers` | 미해결 카드 item도 구현 blocker | 인터뷰어가 명시한 unresolved material decision만 blocker |
| `discovery_runner.py:_owner_card` | 매 cell에서 case card 로드 | 공유 persona 로드; cell마다 독립 owner history 생성 |
| `discovery/oracle/*.md` | 실행 중인 숨은 진실 | 과거 G00 provenance로만 보존하고 새 runtime에서는 읽지 않음 |

`discovery/oracle/*.md`는 삭제할 필요가 없다. 과거 실험을 해석할 수 있도록 보존하되, 새 manifest와 runtime digest에서 authority 입력으로 참조하지 않아야 한다.

## 4. 고정할 핵심 결정

### 4.1 하나의 공유 Senior Owner

모든 case는 동일한 `discovery/owner-persona.md`를 사용한다. persona는 case별 요구사항을 미리 알지 않으며, 짧고 안정적인 판단 우선순위만 가진다.

초기 persona의 규범은 다음과 같다.

1. 기존 데이터와 요청 밖 동작을 보존한다.
2. 동작은 결정적이고 직접 검증 가능하게 만든다.
3. 실패는 명시적이어야 하며 부분 변경을 남기지 않는다.
4. 요청이 바꾸지 않은 호환성은 보존한다.
5. 요청을 만족하는 가장 작은 observable behavior를 선호한다.
6. 요청, 앞선 owner 결정, 위 우선순위와 충돌하지 않으면 추천 선택지를 받아들인다.

persona는 숨겨진 정책 목록이나 case별 답을 포함하지 않는다. v1 discovery에서 candidate, owner, frontier sampler는 starter repository를 보지 않는다. 이들이 받는 task-specific evidence는 open requirement뿐이다. starter repository는 Build Contract가 봉인된 뒤 fresh implementer에게만 implementation seam으로 제공되며, product truth나 blind-spot 정답지로 취급하지 않는다.

### 4.2 공유 persona와 공유 mutable session은 다르다

12개 case를 하나의 mutable LLM conversation으로 직렬 처리하지 않는다. 그러면 case 간 내용이 누출되고 12-worker 병렬성이 사라진다.

대신 다음을 고정한다.

- 모든 owner invocation은 같은 persona bytes, model, reasoning 설정을 사용한다.
- 각 cell은 독립적인 owner session을 가진다.
- 한 cell 안에서는 이전 owner decision ledger를 다음 turn에 모두 제공한다.
- 다른 case, candidate, repetition의 transcript나 결정을 owner에게 제공하지 않는다.
- candidate ID, skill text, 점수, frontier sample도 owner에게 제공하지 않는다.

즉, 동일한 사람의 판단 원칙을 복제하되 대화 기억은 case-local이다.

### 4.3 Owner는 항상 옵션 하나를 선택한다

각 material decision에 대해 owner는 다음 순서로 정확히 하나를 선택한다.

1. 요청, 이전 owner 결정, persona 우선순위와 충돌하는 옵션을 제외한다.
2. 추천 옵션이 남아 있으면 추천 옵션을 선택한다.
3. 추천 옵션이 충돌하면 남은 옵션 중 persona에 가장 잘 맞는 것을 선택한다.
4. 모든 옵션이 불완전해도 가장 덜 충돌하는 하나를 선택하고 그 한계를 `answer`에 짧게 기록한다.

정상적인 질문에 `irrelevant`, `ambiguous`, `not-specified`를 반환해 authority 공백을 만들지 않는다. transport/schema 오류나 option ID 불일치는 candidate failure가 아니라 runtime failure다.

이 정책은 owner가 현실의 정답을 알고 있다는 뜻이 아니다. 인터뷰어가 만든 의사결정 경계 안에서 한 정책을 명시적으로 선택했다는 뜻이다.

### 4.4 선택된 option이 authority다

owner가 선택한 option의 candidate-authored `normative_statement`를 byte-for-byte authority register와 Build Contract에 복사한다. evaluator나 compiler가 더 좋은 문장으로 바꾸거나 hidden frontier sample로 보충하면 안 된다.

권장 schema는 다음과 같다.

```json
{
  "schema": "DiscoveryOwnerDecision.v2",
  "decision_id": "D-3",
  "selected_option_id": "O-2",
  "normative_statement": "...exact candidate option text...",
  "basis": "accepted-recommendation",
  "answer": "추천안이 요청 및 기존 결정과 충돌하지 않아 선택합니다.",
  "authority_id": "OWNER-..."
}
```

`basis`는 `explicit-persona`, `accepted-recommendation`, `prior-decision` 중 하나다. `authority_id`는 최소한 persona digest, case ID, repetition, decision ID, selected option ID, normative statement digest에 결합한다.

### 4.5 숨겨진 frontier는 평가 증거일 뿐 authority가 아니다

frontier sampler가 생성한 material fork는 candidate가 보지 못한다. 그것은 다음 용도로만 사용한다.

- 질문이 중요한 결과 분기를 명시적으로 드러냈는지 평가
- owner 답변으로 그 분기가 실제 정책 하나로 닫혔는지 평가
- 인터뷰가 끝난 뒤 가장 중요한 잔여 blind spot을 공격적으로 찾기

frontier sample은 Build Contract에 복사하지 않으며 구현 blocker를 만들지 않는다. sampled fork를 놓친 것은 evaluation miss이지 pre-implementation 권한 공백이 아니다.

## 5. 목표 end-to-end 흐름

```text
공유 Senior Owner persona ─────────────────────────────┐
                                                       │
open requirement + candidate overlay + empty workspace │
            │                                          │
            v                                          │
candidate interview ──question/options/recommendation──> case-local owner
            ^                                          │
            └──────── selected option + short answer ──┘
            │
            v
owner decision ledger
            │
            v
고정 compiler -> Build Contract -> fresh implementer -> postmortem

open requirement + frozen FrontierSampler protocol
            │
            v
hidden material-fork batch (candidate-independent, case/generation별 1회)
            │
            ├── blinded matcher <── frozen interview transcript/decision ledger
            │          │
            │          └── surface/resolution/risk coverage
            │
            └── residual scout <── transcript + contract
                       │
                       └── 가장 중요한 unresolved fork 한 개 또는 none
```

인터뷰 transcript와 owner ledger를 완전히 동결한 다음 matcher와 residual scout를 실행한다. evaluator 결과를 이용해 같은 cell의 질문을 추가하거나 수정하면 안 된다.

## 6. Latent Frontier Coverage 프로토콜

### 6.1 주장 범위

LLM 내부의 전체 탐색 공간을 직접 열거하거나 절대 coverage를 측정하는 것은 불가능하다. 보고할 값은 반드시 다음처럼 명명한다.

> `coverage under SeniorOwner/FrontierSampler protocol v1`

이 값은 고정된 model/persona/sampler prompt/sampling procedure 아래에서 후보를 상대 비교하는 operational metric이다. 실제 사용자 암묵지나 현실의 모든 edge case에 대한 절대 coverage가 아니다.

### 6.2 Frontier sample schema

```json
{
  "schema": "DiscoveryFrontierSample.v1",
  "sample_id": "F-017",
  "scenario": "...concrete operating situation...",
  "material_decision": "...decision whose alternatives change observable behavior...",
  "plausible_outcomes": ["...", "..."],
  "why_material": "...failure, compatibility, data loss, ownership, or lifecycle impact...",
  "severity": 4
}
```

`severity`는 1에서 5까지다. sampler는 단순 구현 세부사항, 순수 naming/style 선택, 이미 요청이 명시한 정책을 sample로 만들면 안 된다.

### 6.3 Sampling procedure

v1은 case당 32개 sample을 사용한다.

- 8개씩 4회의 독립 ephemeral invocation으로 생성한다.
- sampler 입력은 open requirement, 공유 senior persona, protocol version뿐이다.
- candidate question, transcript, overlay, candidate ID, owner answer, 구현, 점수는 입력하지 않는다.
- duplicate sample을 제거하지 않는다. 반복 생성 빈도도 protocol 아래의 확률 질량 신호다.
- batch는 case와 generation당 한 번 만들고 같은 generation의 모든 candidate와 repetition에 재사용한다.
- candidate 간 공정성과 비용 절감을 위해 sample batch를 candidate별로 다시 생성하지 않는다.
- model API가 seed를 보장하지 않으면 논리적 seed/sample index와 실제 output digest를 모두 receipt에 기록한다.

32는 절대적 충분성 기준이 아니다. 구현 안정화 후 64개로 늘렸을 때 candidate 순위와 Pareto membership이 안정적인지만 별도 점검한다.

### 6.4 Blinded matcher

matcher는 frontier batch와 frozen transcript/owner ledger만 본다. candidate ID, overlay text, train/selection 구분, 기존 점수는 보지 않는다. 32개를 한 번에 처리하기 어렵다면 8개씩 네 chunk로 처리하되 chunk 경계와 prompt digest를 기록한다.

각 sample에 대해 다음 schema를 반환한다.

```json
{
  "schema": "DiscoveryCoverageJudgment.v1",
  "sample_id": "F-017",
  "surface_covered": true,
  "resolution_covered": true,
  "question_refs": ["D-3"],
  "decision_refs": ["D-3/O-2"],
  "rationale": "질문과 선택지가 두 observable outcome을 직접 구분했고 owner가 하나를 선택했다."
}
```

판정 규칙은 다음과 같다.

- `surface_covered`: 질문 또는 선택지가 sample의 materially different outcomes를 명시적으로 구분한다.
- `resolution_covered`: `surface_covered`가 true이고 owner selection이 그 분기에 대해 정책 하나를 닫는다.
- “다른 요구사항이 있나요?”, “edge case는 어떻게 할까요?” 같은 포괄 질문만으로는 coverage를 인정하지 않는다.
- 단어 일치가 아니라 observable outcome의 의미적 구분을 본다.
- 여러 질문을 합쳐야 분기가 드러나면 모든 `question_refs`를 기록한다.

### 6.5 Primary metrics

sample `i`의 surface/resolution 판정을 각각 `s_i`, `r_i`, severity를 `w_i`라 한다.

```text
surface_mass_coverage    = Σ s_i / N
resolution_mass_coverage = Σ r_i / N
risk_weighted_resolution = Σ (w_i × r_i) / Σ w_i
```

duplicate를 유지하므로 mass coverage는 sampler가 자주 생성한 영역에 더 많은 질량을 준다. semantic cluster breadth는 진단 지표로 추가할 수 있지만 v1의 candidate 선택을 좌우하는 primary metric으로 사용하지 않는다. 먼저 clustering prompt와 ranking stability를 검증해야 한다.

질문 수, material decision 수, tokens, wall time은 coverage와 합산한 단일 총점으로 숨기지 않는다. 다음 축을 Pareto 비교한다.

- `risk_weighted_resolution`
- `resolution_mass_coverage`
- material decision burden
- token/wall-clock burden

### 6.6 Residual blind-spot scout

각 cell에 한 번, transcript와 Build Contract를 본 독립 scout가 아직 해결되지 않은 가장 중요한 material fork 하나를 구성한다.

```json
{
  "schema": "DiscoveryResidualBlindspot.v1",
  "status": "found",
  "scenario": "...",
  "material_decision": "...",
  "plausible_outcomes": ["...", "..."],
  "severity": 5,
  "why_unresolved": "...",
  "evidence_refs": ["request", "D-2"]
}
```

`status`는 `found` 또는 `none`이다. scout는 누락을 주장하려면 두 개 이상의 plausible observable outcome과 material impact를 제시해야 한다. 단순히 질문 표현이 마음에 들지 않거나 구현 세부사항을 더 알고 싶은 것은 valid residual이 아니다.

residual은 v1에서 hard veto로 쓰지 않는다. 별도의 robustness signal로 보고하고, 반복적으로 같은 residual family가 나오는 경우 evolution feedback에 coarse failure pattern으로 제공한다.

## 7. Train, selection, final 분리

고정 hidden checklist 과적합을 막기 위해 frontier batch와 feedback authority를 세 단계로 분리한다.

### Train frontier

- 현재 8개 train case에서 사용한다.
- candidate별 coverage와 residual의 coarse failure pattern을 evolution input으로 제공한다.
- raw hidden sample, 정답처럼 보이는 exact fork 문장, matcher rationale 전체는 generator에 주지 않는다.
- 허용 feedback 예: “failure/lifecycle 고위험 분기의 resolution coverage가 낮음”.
- 금지 feedback 예: “duplicate import 정책을 질문하라”.

### Selection frontier

- 현재 4개 validation case를 selection partition으로 취급한다.
- fresh sampler invocations와 digest를 사용한다.
- 결과는 parent/candidate 선택에만 사용한다.
- generator와 다음 mutation prompt에는 raw 결과를 제공하지 않는다.

### Final frontier

- 최종 후보를 선택한 뒤 fresh logical seeds와 batch로 한 번 실행한다.
- 가능하면 다른 sampler prompt family 또는 다른 judge model을 사용한다.
- 최종 보고에만 사용하고 추가 evolution에는 재사용하지 않는다.
- final batch를 보고 후보를 수정하면 그 평가는 final이 아니다.

## 8. 구현 파일과 작업 순서

### 단계 1: 공유 persona와 manifest v4

대상:

- `discovery/owner-persona.md` 신규
- `discovery-study.json`
- `src/driftbench/discovery_runner.py`

작업:

1. `owner_cards_dir`를 `owner_persona`로 교체한다.
2. frontier protocol version, sample count 32, sampler calls 4, samples per call 8, train/selection/final logical seed namespace를 manifest에 추가한다.
3. manifest validation은 persona가 root 내부의 regular file인지 확인한다.
4. manifest/runtime digest에 persona bytes와 frontier 설정을 포함한다.
5. case별 oracle 파일 존재 여부 검사를 제거한다.

### 단계 2: owner authority v2

대상:

- `src/driftbench/discovery.py`
- `src/driftbench/discovery_backend.py`
- 관련 JSON schema 상수

작업:

1. `DiscoveryOwnerDecision.v2` model과 schema를 추가한다.
2. `_resolve_owner`가 persona, request, 현재 decisions, case-local prior ledger만 받도록 바꾼다.
3. interview invocation은 starter repository 대신 controller-owned empty discovery workspace에서 실행한다.
4. 정확히 한 option ID를 선택하도록 schema와 controller validation을 fail-closed로 만든다.
5. `selection_from_owner_exchange`를 owner-selected option 기반 변환으로 교체한다.
6. option의 `normative_statement`가 ledger와 compiler authority에 byte-identical하게 남는지 검증한다.
7. `interview_blockers`에서 `unresolved-owner-item`과 card coverage 의존성을 제거한다.
8. interviewer가 제출한 `contract_draft.status=incomplete` 또는 `unresolved_material_decisions`는 계속 blocker로 유지한다.

### 단계 3: frontier 평가 모듈

대상:

- `src/driftbench/discovery_frontier.py` 신규 권장
- `src/driftbench/discovery_backend.py`
- `src/driftbench/discovery_runner.py`

작업:

1. sample, judgment, residual, aggregate result Pydantic models를 구현한다.
2. sampler prompt는 explicit allowlist로 구성한다.
3. runner가 case/generation별 frontier batch를 먼저 만들고 candidate cell들이 read-only로 공유하게 한다.
4. transcript가 동결된 뒤 matcher와 residual scout를 실행한다.
5. matcher completeness를 검증한다. 모든 sample ID가 정확히 한 번 나타나지 않으면 runtime invalid다.
6. aggregate coverage와 burden을 candidate/generation summary에 추가한다.

### 단계 4: artifact와 receipt

cell evidence 디렉터리에 다음을 남긴다.

- `owner-decisions.json`
- `coverage-judgments.json`
- `coverage-result.json`
- `residual-blindspot.json`

frontier sample 자체는 candidate process가 접근할 수 없는 controller-owned generation 디렉터리에 한 번만 둔다.

- `frontier/<partition>/<case-id>/frontier-samples.json`
- `frontier/<partition>/<case-id>/receipt.json`

cell receipt에는 sample batch 파일의 상대 경로가 아니라 digest만 넣는다. receipt에 다음 digest와 설정을 결합한다.

- owner persona
- owner responder prompt/schema/model config
- frontier sampler prompt/schema/model config
- matcher prompt/schema/model config
- residual scout prompt/schema/model config
- sample batch output
- logical seed namespace와 sample indices
- transcript와 owner decision ledger

dashboard와 tmux pane에는 raw hidden sample을 출력하지 않는다. 다음 진행 상태만 출력한다.

```text
[cell] interview started
[Q&A] D-3 ...
[Owner] selected O-2 (accepted-recommendation)
[compile] contract complete
[coding] started
[postmortem] started
[frontier] matching 32 samples
[frontier] coverage complete: resolution=... risk=...
[residual] found|none
```

### 단계 5: selection/evolution summary

대상:

- `src/driftbench/discovery.py`
- `src/driftbench/discovery_runner.py`
- comparison/report 생성 코드

작업:

1. 기존 card recall 기반 discovery success를 primary selection에서 제거한다.
2. candidate summary에 mass/risk coverage와 burden을 분리 저장한다.
3. Pareto archive가 coverage 증가와 질문 비용을 함께 비교하도록 바꾼다.
4. mutation generator에는 train의 coarse failure family와 burden만 제공한다.
5. selection/final raw frontier와 rationale가 mutation input에 들어가지 않는 allowlist test를 추가한다.

### 단계 6: G00 fresh rerun

새 의미론을 구현한 뒤 기존 G00 checkpoint를 resume하지 않는다.

- 새 study/runtime digest로 fresh G00를 시작한다.
- 기존 G00 candidate를 parent로 승격하지 않는다.
- 과거 결과는 “Owner Card recall protocol”로 라벨링한다.
- 새 결과는 “SeniorOwner/FrontierSampler protocol v1”로 라벨링한다.

## 9. 실패 의미론

실험적 실패와 runtime 실패를 분리한다.

| 상황 | 분류 | 처리 |
|---|---|---|
| candidate가 중요한 fork를 묻지 않음 | evaluation miss | coverage 하락, run 계속 |
| candidate가 너무 많은 질문을 함 | efficiency cost | burden 증가, run 계속 |
| residual scout가 유효한 blind spot을 찾음 | robustness signal | 기록하고 run 계속 |
| interviewer가 contract를 incomplete로 종료 | candidate failure | `interview-blocked` |
| implementer가 sealed contract gap을 발견 | candidate failure | `blocked-contract-gap` |
| owner가 option ID를 누락/중복 반환 | runtime failure | run 일시 중단, 고친 뒤 fresh retry |
| sampler가 32개 유효 sample을 만들지 못함 | runtime failure | candidate 점수로 기록하지 않음 |
| matcher가 sample을 누락/중복 판정 | runtime failure | candidate 점수로 기록하지 않음 |
| hidden frontier가 candidate prompt/artifact에 노출 | protocol violation | run 전체 무효 |
| postmortem/implementation transport 오류 | runtime failure | 기존 runtime retry 정책 적용 |

모델 capacity, malformed JSON, prompt/schema framing, orphan process 같은 harness 결함을 candidate miss로 바꾸지 않는다.

## 10. 테스트 계획

### Unit tests

`tests/test_discovery.py`:

- owner-selected option의 exact normative statement가 authority가 된다.
- 추천안이 충돌하지 않으면 추천 option을 선택한다.
- prior decision과 충돌하는 추천안은 다른 option으로 대체된다.
- owner decision authority ID가 persona/case/repetition/decision/option/text에 결합된다.
- hidden frontier sample은 compiler authority로 변환될 수 없다.

`tests/test_discovery_backend.py`:

- `interview_blockers`가 hidden owner item을 요구하지 않는다.
- incomplete contract와 explicit unresolved material decision은 계속 block한다.
- owner prompt allowlist에 candidate ID, skill, score, frontier가 없다.
- interview와 owner prompt에 starter repository의 파일 내용이나 경로가 없다.
- matcher prompt allowlist에 candidate ID, overlay, partition label, score가 없다.
- broad catch-all 질문은 surface coverage가 false다.
- surface만 있고 selection이 없으면 resolution coverage가 false다.
- 32개 sample ID completeness 위반은 runtime error다.

`tests/test_discovery_runner.py`:

- 하나의 persona가 12개 case에 사용된다.
- owner ledger는 cell 내부 turn에는 유지되고 case/candidate/repetition 사이에는 격리된다.
- frontier batch는 case/generation당 한 번 생성되고 candidate 간 재사용된다.
- selection/final frontier raw data가 evolution input에 들어가지 않는다.
- persona/frontier config 변경 시 resume input digest가 바뀐다.
- runtime failure는 completed/failed candidate score로 저장되지 않는다.

새 `tests/test_discovery_frontier.py` 권장:

- schema validation과 severity range
- metric 계산
- duplicates-retained semantics
- risk-weighted denominator
- residual validity contract
- controller-owned artifact path와 digest binding

### Integration tests

1. fake backend로 12 cases × 5 candidates × 2 repetitions의 120 cell을 실행한다.
2. 각 case frontier sampler가 generation당 정확히 4회 호출되는지 확인한다.
3. 각 cell owner가 모든 material decision에서 정확히 한 option을 선택하는지 확인한다.
4. `unresolved-owner-item` 때문에 구현이 block되는 cell이 없음을 확인한다.
5. frontier/matcher 한 건의 malformed response가 run을 runtime-invalid로 멈추는지 확인한다.
6. hidden sample 문자열이 interview prompt, owner prompt, compiler bundle, implementer prompt, pane log에 나타나지 않는지 검사한다.

### 최종 검증 명령

```bash
cd /Users/jpark/IdeaProjects/harnesses/measure-contract-drift
uv run pytest
uv run ruff check src tests
./run-live.sh --one-generation
```

live run은 먼저 fake/smoke backend를 통과한 뒤 실행한다. 실제 one-generation run에서 첫 worker cell이 contract compile, implementation, postmortem, frontier match까지 완료되는 것을 확인하기 전에는 120개 결과를 신뢰하지 않는다.

## 11. 완료 조건

다음 조건을 모두 만족해야 구현 완료다.

1. 새 runtime은 `discovery/oracle/*.md`를 owner authority나 평가 정답으로 읽지 않는다.
2. 동일한 `owner-persona.md` bytes가 모든 case에서 사용된다.
3. discovery candidate, owner, frontier sampler는 starter repository를 보지 않으며 open requirement만 task evidence로 받는다.
4. 각 cell의 owner context는 다른 cell과 격리되고, 같은 cell의 이전 결정은 유지된다.
5. owner는 모든 유효 material decision에서 정확히 한 option을 선택한다.
6. 선택된 option의 `normative_statement`가 byte-for-byte compiler authority가 된다.
7. 미해결 hidden item 때문에 `interview-blocked`가 발생하지 않는다.
8. case/generation별 32개 frontier sample이 candidate-independent하게 생성되고 모든 후보에 공정하게 재사용된다.
9. coverage는 transcript 동결 후 blinded matcher가 surface와 resolution으로 나눠 판정한다.
10. raw frontier sample은 candidate, owner, compiler, implementer, postmortem, pane에 노출되지 않는다.
11. coverage와 질문 비용은 Pareto 축으로 분리된다.
12. train feedback만 coarse form으로 evolution에 들어가며 selection/final frontier는 누출되지 않는다.
13. frontier/owner runtime 오류는 candidate 성능으로 기록되지 않는다.
14. persona, prompts, schemas, model configs, logical seeds, outputs가 digest로 receipt에 결합된다.
15. 기존 G00는 새 실험의 parent나 baseline으로 재사용되지 않는다.
16. 전체 test suite와 fresh one-generation smoke run이 통과한다.

## 12. 알려진 한계와 해석 규칙

- 공유 Senior Owner는 실제 인간 owner가 아니다. 모델에 학습된 시니어 엔지니어 prior를 일관된 정책으로 끌어내는 장치다.
- 실제 사용자의 조직 맥락, 취향, 비공개 제약, 진짜 암묵지는 이 방식만으로 복원할 수 없다.
- interviewer, owner, sampler, matcher가 같은 model family이면 같은 blind spot과 표현 선호를 공유할 수 있다.
- sampler frequency는 현실의 실제 사건 확률이 아니다. protocol 아래에서 모델이 떠올리는 빈도다.
- 높은 coverage는 선택한 정책이 현실의 유일한 정답이라는 뜻이 아니다. 중요한 분기를 질문으로 드러내고 owner가 명시적으로 닫았다는 뜻이다.
- postmortem은 spec-to-implementation divergence를 측정하고, frontier는 spec 이전의 탐색 폭을 측정한다. 두 센서를 하나의 점수로 합쳐 서로의 실패를 숨기지 않는다.

따라서 보고서에는 “latent space를 82% 커버했다”라고 쓰지 않는다. “SeniorOwner/FrontierSampler protocol v1의 32-sample batch에서 risk-weighted resolution coverage가 82%였다”라고 쓴다.

## 13. 구현 시작 체크리스트

1. root와 `measure-contract-drift`의 dirty state를 확인하고 unrelated change를 보존한다.
2. 현재 G00 artifact와 manifest digest를 보존해 과거 provenance를 유지한다.
3. `owner-persona.md`와 manifest v4부터 구현한다.
4. owner decision v2와 compiler authority exact-copy test를 먼저 통과시킨다.
5. `unresolved-owner-item` blocker를 제거하고 기존 blocker 회귀 테스트를 갱신한다.
6. frontier 모듈을 owner/compiler 경로와 분리해 추가한다.
7. hidden-data leakage allowlist test를 먼저 만든 뒤 runner에 연결한다.
8. fake 120-cell integration을 통과시킨다.
9. fresh study ID로 실제 G00 one-generation을 시작한다.
10. 첫 runtime 오류에서 즉시 중단하고 수정한 뒤, 의미론이나 digest가 바뀌면 fresh run으로 재시작한다.
