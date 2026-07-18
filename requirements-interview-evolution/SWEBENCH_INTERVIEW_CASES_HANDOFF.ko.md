# SWE-bench 기반 인터뷰 학습 사례 확장 핸드오프

## 결정된 목적

SWE-bench의 문제 설명, 당시 저장소, 테스트, gold patch를 이용해 `clarify-requirements` 인터뷰 스킬을 개선할 수 있는 다양한 사례를 만든다.

이 작업의 목적은 구현 에이전트가 gold patch를 맞히는지 측정하는 것이 아니다. Gold patch와 테스트는 인터뷰에서 놓치기 쉬운 결정, 경계 조건, 호환성 요구, 불필요한 가정을 사후에 발견하기 위한 증거다.

따라서 생성물은 `ground-truth requirements`나 구현 정답이 아니라 **gold-informed interview training case**로 취급한다.

## 작업 위치와 연결 지점

- 작업 루트: `/Users/jpark/IdeaProjects/harnesses/requirements-interview-evolution`
- 현재 스킬: `clarify-requirements/SKILL.md`
- 기존 공개 사례: `eval/cases.json`
- 별도 holdout 사례: `eval/holdout-cases.json`
- 역할 분리 진화 실행기: `native-evolution/run_evolution.py`
- 역할 및 정보 경계: `native-evolution/PROTOCOL.md`

기존 dirty 변경과 실행 산출물은 이 작업의 소유가 아니다. 초기 구현은 새 importer/generator 경로와 새 사례 파일에 한정하고, 기존 진화 실행기를 바로 크게 변경하지 않는다.

## 핵심 원칙

### 1. Gold patch는 교재 생성 증거다

Gold patch를 유일하게 옳은 구현으로 취급하지 않는다. 동일한 사용자 요구를 만족하는 대안 구현이 존재할 수 있고, patch에는 우연적인 네이밍, 파일 배치, 리팩터링이 섞일 수 있다.

Patch에서 다음과 같은 결정 흔적을 찾는다.

- 기존 동작과 호환성을 어디까지 유지했는가
- 오류를 거부, 무시, 보정, 기본값 처리 중 어떻게 다뤘는가
- 새 동작이 기본값인지 opt-in인지
- 입력, 출력, 상태 변화의 경계가 무엇인지
- 어떤 회귀를 테스트가 방지하는지
- 요청 범위 밖의 동작을 일부러 바꾸지 않았는지

찾은 흔적은 코드 구조를 설명하는 정답이 아니라, 인터뷰 질문과 실패 패턴으로 변환한다.

### 2. 출처와 인식 가능 시점을 분리한다

각 사실과 결정에는 최소한 다음 두 축의 provenance를 기록한다.

`source`:

- `issue`: 문제 설명에 명시됨
- `repository`: 당시 코드나 문서에서 발견 가능
- `test`: 테스트가 요구하는 관찰 가능한 동작
- `patch`: gold patch에서 사후에 발견됨
- `inferred`: 생성기가 추론했으며 사람의 검토가 필요함

`knowledge_timing`:

- `issue_time_author_knowable`: 당시 이슈 작성자에게 물으면 답할 수 있는 제품 결정
- `repository_discoverable`: 사용자에게 묻지 않고 저장소 조사로 확인해야 하는 사실
- `implementation_time`: 구현자가 기술 조사나 검증으로 정해야 하는 사항
- `hindsight_only`: patch 또는 사후 테스트 결과를 본 뒤에만 알 수 있는 사항

`hindsight_only` 항목을 현실적인 Owner가 알고 있던 요구사항처럼 가장하지 않는다. 이 항목은 누락 가능성 탐색, 반례 생성, 사후 리뷰에만 사용한다.

### 3. 학습 대상은 질문 및 계약 품질이다

주요 학습 신호는 다음과 같다.

- 중요한 미결정을 질문했는가
- 저장소에서 확인할 사실을 사용자에게 떠넘기지 않았는가
- 질문 전에 요구사항을 임의로 만들지 않았는가
- 한 질문에 서로 독립적인 결정을 과도하게 묶지 않았는가
- 답변에 따라 필요한 후속 질문을 선택했는가
- 이미 확정된 사실을 반복해서 묻지 않았는가
- 비목표, 오류 처리, 호환성, 범위, 검증 기준을 확보했는가
- 최종 계약이 실제 답변을 보존했는가
- 제품 요구가 아닌 내부 구현 방식을 불필요하게 강제하지 않았는가

기존 SWE-bench 테스트 통과 여부나 gold patch와의 코드 유사도는 인터뷰 스킬의 주 점수가 아니다.

## 사례 생성 파이프라인

```text
SWE-bench instance
  -> issue / base commit / tests / gold patch 수집
  -> 관찰 가능한 변화와 결정 흔적 추출
  -> 출처 및 knowledge timing 태깅
  -> 구현 종속 단서 제거
  -> 인터뷰 질문, owner answer, failure trap 생성
  -> 독립 감사 및 승인
  -> development 또는 sealed holdout partition에 등록
```

### 단계 A: 원본 묶음 동결

사례마다 다음 입력의 식별자와 digest를 남긴다.

- SWE-bench instance ID와 데이터셋 버전
- issue 본문
- base commit
- FAIL_TO_PASS 및 PASS_TO_PASS 테스트 정보
- gold patch
- 사용한 저장소 파일

라이선스와 재배포 조건을 확인하고, 원문을 저장할 수 없다면 upstream ID와 digest만 보존한다.

### 단계 B: 사후 결정 지도 생성

문제, 저장소, 테스트, patch의 차이를 분석해 다음을 만든다.

- 명시된 요구사항
- 저장소에서 발견할 수 있는 기존 계약
- 미리 질문할 가치가 있었던 제품 결정
- 구현 중 확인해야 할 기술적 결정
- hindsight-only 관찰
- 합리적인 대안 동작
- patch에만 존재하는 우연적 구현 선택

모든 항목은 가능한 한 입력과 출력, 오류, 상태 변화처럼 외부에서 관찰 가능한 표현을 사용한다.

### 단계 C: 인터뷰 훈련 사례로 변환

각 material decision에 대해 다음을 생성한다.

- 왜 결정이 중요한가
- issue만으로 답이 정해지는가
- 저장소 조사로 답할 수 있는가
- Owner에게 물어야 한다면 최소 질문은 무엇인가
- 허용 가능한 질문 표현의 범주
- Owner가 제공할 수 있는 답변
- 답변에 따라 계약의 어떤 부분이 달라지는가
- 질문하지 않았을 때 발생하는 invented requirement 또는 omission
- 무관하거나 너무 세부적인 질문의 예

Owner는 묻지 않은 결정을 자발적으로 공개하지 않는다. 다만 실제 인터뷰 훈련용 Owner는 `issue_time_author_knowable` 항목만 답할 수 있어야 한다. `hindsight_only`까지 답하는 별도 모드는 현실적 인터뷰가 아니라 진단용 상한선으로 명시한다.

### 단계 D: 독립 감사

생성기와 별도의 Reviewer가 모든 항목을 disposition한다.

- 출처 인용이 실제 원본과 일치하는가
- 제품 결정과 저장소 사실이 구분됐는가
- 특정 함수, 파일, 분기 구조 등 gold 구현 단서가 새어 나오는가
- 다른 정상 구현도 수용할 수 있는 표현인가
- 해당 질문이 구현 결과를 바꿀 만큼 material한가
- issue 작성 시점에 Owner가 답할 수 있었다는 주장이 타당한가
- 단순한 코드 차이를 가짜 요구사항으로 만들지 않았는가

미승인 또는 undispositioned 항목이 있으면 사례를 공개 corpus에 넣지 않는다.

## 제안 사례 스키마

기존 `CleanRoomInterviewCases.v1`을 즉시 덮어쓰지 말고, SWE-bench 전용 원본을 별도 버전으로 시작한다.

```json
{
  "schema": "GoldInformedInterviewCase.v1",
  "id": "swebench-instance-id",
  "upstream": {
    "dataset": "SWE-bench",
    "instance_id": "...",
    "base_commit": "...",
    "input_digest": "..."
  },
  "public_request": "original issue text",
  "material_decisions": [
    {
      "id": "stable-decision-id",
      "description": "implementation-independent behavioral decision",
      "source": ["issue", "repository", "test", "patch"],
      "knowledge_timing": "issue_time_author_knowable",
      "materiality": "how the answer changes behavior or scope",
      "owner_answer": "answer available only when asked",
      "acceptable_question_intent": "what the interviewer must resolve",
      "failure_if_missed": "omission, invention, or compatibility regression",
      "evidence": ["sealed source reference"]
    }
  ],
  "repository_facts": [],
  "hindsight_observations": [],
  "implementation_incidentals": [],
  "leakage_flags": [],
  "review": {
    "status": "approved",
    "dispositions_complete": true
  }
}
```

실제 구현에서는 닫힌 JSON schema와 enum을 정의하고, 알 수 없는 필드와 잘못된 provenance를 fail-closed로 거부한다.

## 개발과 평가의 분리

SWE-bench 사례를 이용해 실패 규칙을 찾고 `SKILL.md`를 수정했다면 그 사례는 development lineage에 들어간다. 동일 instance, 동일 issue의 변형, 동일 patch에서 파생된 사례를 향상도 평가에 다시 사용하지 않는다.

권장 partition:

- `development`: 실패 분석, prompt/skill mutation, 회귀 테스트에 사용
- `validation`: 후보 선택과 질문 예산 조정에 사용하되 직접 mutation 근거는 제한
- `holdout`: 최종 비교 전까지 스킬 작성자와 Mutator에게 비공개

프로젝트나 저장소별로 유사 사례가 여러 개 있으면 instance 단위가 아니라 repository 또는 issue family 단위로 분리해 근접 중복 누출을 줄인다. Upstream contamination 가능성이 있는 모델을 사용할 경우, 결과를 절대적인 일반화 증거로 과장하지 않고 동일 모델·조건의 전후 비교로 제한한다.

## 기존 native evolution과의 통합 방향

초기에는 기존 `Lens-Conditioned Case Designer`를 대체하지 않는다. SWE-bench importer가 승인된 `GoldInformedInterviewCase.v1`을 만들고, 별도 adapter가 다음 역할 입력으로 투영하게 한다.

- Repository Discovery에는 public request와 base checkout만 제공
- Evidence Auditor에는 저장소 근거만 제공
- Interviewer에는 public request, 승인된 repository evidence, candidate skill만 제공
- Owner에는 현재 질문과 `issue_time_author_knowable` oracle만 제공
- Judge에는 전체 sealed case, transcript, contract 제공
- Mutator에는 승인된 실패 요약만 제공하고 gold patch와 원본 oracle은 차단

`hindsight_only` 관찰은 Judge가 누락 가능성을 분석할 때 참고할 수 있지만, Owner가 답하지 않은 내용을 계약 필수사항으로 자동 판정해서는 안 된다. 먼저 `질문 가능했던 제품 결정`, `저장소에서 발견할 사실`, `사후에만 보이는 구현 관찰` 중 어디에 속하는지 판정해야 한다.

## 최소 실행 단계

### 1단계: 수동 파일럿

서로 다른 프로젝트와 실패 유형에서 10~20개 instance를 골라 수동으로 변환한다. 목적은 대량 생성이 아니라 schema와 Reviewer 규칙의 결함을 찾는 것이다.

산출물:

- 사례 JSON
- provenance evidence
- leakage review
- 실제 Interviewer transcript
- Judge 결과
- 사례를 통해 발견한 재사용 가능한 실패 패턴

### 2단계: 반자동 생성

LLM이 초안을 만들고 독립 Reviewer가 모든 decision과 evidence를 승인 또는 거부한다. 승인률, 중복률, hindsight-only 비율, 구현 단서 누출률을 기록한다.

### 3단계: 대량 corpus와 진화 연결

품질 기준을 통과한 뒤에만 대량 importer를 실행하고 development/validation/holdout registry에 등록한다. 스킬 mutation은 개별 patch의 세부사항이 아니라 여러 사례에서 반복 관찰된 실패 패턴에 근거해야 한다.

## 성공 기준

첫 번째 파일럿은 다음을 만족하면 성공으로 본다.

- 최소 10개의 서로 다른 instance가 승인됨
- 모든 material decision에 source와 knowledge timing이 존재함
- evidence가 없는 decision이 없음
- implementation incidental이 요구사항으로 승격되지 않음
- Reviewer가 모든 항목을 명시적으로 disposition함
- 실제 인터뷰 실행에서 omission, invention, redundant question, repository-delegation failure 중 하나 이상을 재현함
- 두 개 이상의 사례에서 반복된 실패만 스킬 변경 후보로 승격함
- 개발 사례와 holdout의 instance 및 repository-family 중복 검사가 통과함

## 이 작업에서 주장하지 않을 것

- Gold patch가 실제 사용자 요구사항 전체를 표현한다는 주장
- 생성된 계약이 유일한 정답이라는 주장
- Gold-derived Owner가 현실적인 제품 Owner를 그대로 모사한다는 주장
- 기존 SWE-bench 테스트 통과가 인터뷰 품질을 증명한다는 주장
- development에 사용한 동일 사례의 점수 상승이 일반화 성능을 증명한다는 주장

## 다음 작업자가 먼저 결정할 사항

1. 사용할 SWE-bench variant와 고정 버전
2. 원본 데이터 보관 및 라이선스 정책
3. `GoldInformedInterviewCase.v1`의 닫힌 JSON schema
4. 첫 10~20개 instance의 다양성 기준
5. Reviewer disposition schema와 leakage 판정 규칙
6. repository-family 기반 partition 및 digest 규칙
7. 기존 `native-evolution`에 연결하기 전 수동 파일럿 실행 방식

이 일곱 항목을 결정하기 전에는 대량 corpus 생성이나 현재 진화 실행기 변경을 시작하지 않는다.
