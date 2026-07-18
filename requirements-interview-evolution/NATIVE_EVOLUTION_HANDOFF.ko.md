# 역할 분리형 스킬 진화 개선 핸드오프

## 목적

`clarify-requirements` v4의 역할 분리형 진화 시스템에, LLM이 이미 알고 있는 일반적인 좋은 관행을 이용해 **새로운 실패 관점 자체를 발견하는 경로**를 추가한다.

다른 인터뷰·계획 도구의 본문을 복사하거나 그 도구를 정답으로 사용하지 않는다. 대신 요구사항 발견, 대화, 계약 작성, 구현 인계, 구현, 검증, 사후 분석 과정에서 발생할 수 있는 실패를 독립적으로 도출하고, 실제 실행에서 관찰된 실패만 스킬 개선 근거로 사용한다.

## 작업 위치와 현재 대상

- 작업 루트: `/Users/jpark/IdeaProjects/harnesses/requirements-interview-evolution`
- 현재 배포 스킬: `clarify-requirements/SKILL.md`
- 동결된 현재 버전: `evolution/v4/SKILL.md`
- 진화 실행기: `native-evolution/run_evolution.py`
- 프로토콜 설명: `native-evolution/PROTOCOL.md`
- 테스트: `tests/test_evolution.py`, `tests/test_native_evolution.py`

이 폴더는 아직 root Git 저장소에서 새로 추가되는 작업 묶음이다. 관련 없는 root 변경이나 다른 submodule을 수정하지 않는다.

## 왜 이 작업이 필요한가

### 초기 v0~v3 진화의 문제

초기 진화에서는 같은 Codex LLM이 다음을 모두 수행했다.

1. 평가 사례 작성
2. 중요 결정 목록 작성
3. 각 스킬 버전이 무엇을 물을지 수동 판정
4. 점수 해석
5. 다음 `SKILL.md` 작성

실제 인터뷰 기록 없이 `manual rule-to-scenario walkthrough`를 작성해 점수를 계산했다. 그 결과 자체 평가에서는 v3가 100점을 받았지만, 최초의 실제 Todo CLI 인터뷰에서는 사소한 선택까지 하나씩 물어 총 16개의 질문이 이어졌다.

이를 계기로 v4에는 다음을 추가했다.

- 런타임의 구조화된 질문 UI 우선 사용
- 위험이 낮고 되돌릴 수 있는 기본값 2~5개 일괄 승인
- 여러 관점에서 구현 준비도를 자율 판단
- `build-contract.json` 생성
- 구현자가 스펙 공백을 채울 때 `decision.jsonl` 기록
- 인터뷰 종료 후 구현 시작 프롬프트 출력

하지만 v4 자체도 아직 한정된 실제 실행만 거쳤으며, 다른 종류의 실패를 충분히 경험하지 않았다.

### 다른 도구의 장점을 발견하지 못한 이유

초기 클린룸 실험은 기존 인터뷰 스킬과 저장소 평가 경험을 의도적으로 제외했다. 독립적인 출발점에는 도움이 됐지만, 다른 도구들이 해결하던 다음 문제는 평가 대상에 들어오지 않았다.

- 기존 저장소의 코드·문서·테스트 조사
- 관찰된 사실과 새 동작을 결정할 권한의 분리
- 인터뷰 답변이 최종 계약에서 빠지는 문제
- 요구사항과 검증 방법의 연결
- fresh-context 구현자가 새 제품 결정을 내려야 하는 인계 실패
- 계약과 구현 계획의 충돌
- 구현 후 누락과 임의 결정을 찾아 다음 실행에 반영하는 과정

클린룸은 시작 조건으로는 유효하지만 종료 조건으로 사용하면 안 된다. 다른 도구를 복사하지 않으면서도 LLM의 일반 지식으로 새로운 실패 유형을 제안하고, 실제 관찰을 통해 그 가치를 검증하는 단계가 필요하다.

## 현재 역할 분리 시스템

현재 `native-evolution`은 각 역할을 별도의 `codex exec --ephemeral` 프로세스로 실행한다.

### Greenfield 모드

```text
Case Designer
→ Interviewer
→ Owner
→ Judge
→ Mutator
```

### Repository 모드

```text
Repository Discovery
→ Evidence Auditor
→ Owner Oracle Designer
→ Interviewer
→ Owner
→ Judge
→ Mutator (development에서만)
```

주요 정보 차단:

- Interviewer는 private owner oracle과 Judge 결과를 보지 않는다.
- Owner는 현재 질문과 private oracle만 사용하고 묻지 않은 결정을 자발적으로 제공하지 않는다.
- Judge는 저장소 근거, private oracle, transcript와 contract를 비교한다.
- Mutator는 private oracle과 holdout 자료를 받지 않는다.
- Holdout 모드에서는 Mutator를 호출하지 않는다.
- 개발과 holdout의 seed, public request, 전체 case identity 중 하나라도 겹치면 study registry가 실패하도록 되어 있다.

이 격리는 별도 임시 작업 디렉터리와 프롬프트 입력 차단에 의존하는 논리적 격리다. 적대적인 역할을 막는 OS 수준 read-deny 경계는 아니다. 이 한계를 문서에서 과장하지 않는다.

## 현재 실행 증거

### Greenfield greeting smoke

경로: `native-evolution/runs/greeting-v4-smoke-2/`

결과:

- 중요 결정 6개 중 5개를 다룸: recall `0.8333`
- 질문 5개
- 만들어 낸 요구사항 0개
- 턴 제한으로 최종 계약을 만들지 못함
- Unicode 입력 정책을 놓침

Mutator는 문자 범위 확인과 턴 예산을 남겨 계약 합성 시간을 확보하는 규칙을 제안했다. 이 결과는 현재 배포 v4에 반영되지 않았다.

### Repository greeting `--uppercase` development

경로: `native-evolution/runs/greeting-repo-v4/`

요청:

> 기존 동작을 보존하면서 greeting CLI에 선택적 `--uppercase` 플래그를 추가한다.

결과:

- 저장소 일치도: `0.86`
- 사용자 결정 회수율: `0.83`
- 질문 3개
- 불필요한 질문 0개
- 최종 계약: 구현 준비 미완료

Judge가 찾은 핵심 실패:

1. 기존에는 `--other` 같은 option-looking 단일 인자도 정상적인 이름이었다. 계약이 모든 unknown option을 usage error로 만들어 기존 동작을 깨뜨렸다.
2. Owner는 내부 구현 위치를 위임했지만 계약은 flag parsing과 uppercase 변환을 특정 CLI 계층에 두도록 불필요하게 강제했다.

생성된 후보:

`native-evolution/runs/greeting-repo-v4/candidate-SKILL.md`

후보가 추가한 일반 규칙:

- 기존 동작 보존 요청에서는 이전에 유효하고 무효였던 입력을 먼저 조사한다.
- 새로운 특수 토큰 하나를 인식한다고 다른 option-looking 입력을 자동으로 금지하지 않는다.
- “모든 잘못된 입력” 같은 포괄 표현으로 미결정 동작을 숨기지 않는다.
- 사용자나 권위 있는 근거가 요구하지 않은 내부 구조는 계약 요구사항으로 만들지 않는다.

이 후보도 아직 배포 v5가 아니다.

### Repository holdout

첫 holdout 경로:

`native-evolution/runs/greeting-repo-v4-holdout/`

Evidence Auditor가 Discovery의 conflict를 조용히 누락해 harness가 fail-closed로 중단됐다. 이는 스킬 품질 실패가 아니라 harness 무결성 검사가 작동한 사례다.

재시도 경로:

`native-evolution/runs/greeting-repo-v4-holdout-2/`

요청:

> 기존 동작을 보존하면서 `--count N` 옵션으로 greeting을 N번 출력한다.

결과:

- 정상 종료: `manifest.json`의 `termination_reason`은 `completed`
- 저장소 일치도: `1.00`
- 사용자 결정 회수율: `0.86`
- 질문 6개
- 불필요한 질문 0개
- 최종 계약: 구현 준비 미완료
- holdout이므로 Mutator를 호출하지 않았고 candidate를 만들지 않음

Judge가 찾은 핵심 실패:

1. `--count=N` 형식을 명시적으로 거부하지 않았다.
2. N을 정수라고만 표현해, Owner가 정한 엄격한 signed base-10 token 규칙을 보존하지 못했다.
3. alias, short flag, 환경 변수, 설정 파일, 대화형 입력을 허용하지 않는다는 Owner 경계를 계약에 남기지 않았다.
4. Owner가 요구하지 않은 포괄적인 README 문서화와 테스트 범위를 새 요구사항으로 만들었다.

이 결과는 final-evaluation evidence다. mutation 입력으로 사용하거나 동일 경로를 재실행하지 않는다.

## 이번에 추가할 핵심 기능

현재 시스템은 **주어진 사례 안의 실패를 발견**할 수 있다. 이번 작업은 그 전에 **어떤 실패를 시험해야 하는지 새 평가축을 발견**하는 경로를 추가하는 것이다.

### 1. Failure-Lens Proposer

목적:

LLM의 일반 지식을 사용해 요구사항 및 인계 과정의 서로 다른 실패 유형을 제안한다.

보여 줄 수 있는 것:

- 대상 작업의 매우 일반적인 범주 또는 seed
- 이미 동결된 상위 목적: 모호성을 제거하고 구현 가능한 계약을 만든다

보여 주면 안 되는 것:

- 후보 `SKILL.md`
- 다른 인터뷰·계획 도구의 본문이나 비교표
- 이전 후보의 점수와 mutation
- 특정 후보를 통과 또는 실패시키기 위한 원하는 결과

프롬프트 취지:

```text
요구사항을 정리하고 다른 구현자에게 넘기는 과정이 실패할 수 있는
서로 다른 원인을 제안하라.

질문 내용뿐 아니라 저장소 조사, 사용자 상호작용, 계약 합성,
fresh-context 인계, 구현, 검증, 사후 학습 단계를 고려하라.

특정 해결책이나 스킬 문구를 제안하지 말고, 외부에서 관찰 가능한
실패 형태와 그 실패를 판별할 수 있는 증거를 작성하라.
```

출력은 닫힌 JSON schema를 사용해야 한다. 각 lens에는 최소한 다음 필드가 필요하다.

- stable `id`
- `stage`: discovery, interaction, synthesis, handoff, implementation, verification, learning 중 하나
- `failure_description`
- `observable_signal`
- `why_material`
- `minimal_test_shape`

중복된 표현만 다른 lens는 coordinator가 거부하거나 별도 Deduplicator가 병합해야 한다.

### 2. Lens Auditor 또는 Deduplicator

목적:

제안된 lens가 실제로 서로 다른 실패 유형인지, 관찰 가능한지, 특정 해결책이나 도구의 문구를 몰래 포함하지 않는지 검사한다.

검사 조건:

- 관찰 불가능한 “좋아야 한다” 수준의 주장 거부
- 특정 제품·스킬 이름이나 구현 문구에 의존하는 lens 거부
- 사실상 동일한 실패의 중복 거부 또는 병합
- 단순한 스타일 선호가 아니라 구현 결과나 성공 판정을 바꾸는 실패만 승인

승인된 lens set은 **사례 생성 전에 동결**하고 digest를 남긴다.

### 3. Lens-Conditioned Case Designer

목적:

동결된 실패 lens를 실제로 드러낼 수 있는 개발 또는 holdout 사례를 만든다.

보여 줄 수 있는 것:

- 선택된 lens
- greenfield 또는 repository context
- repository mode에서는 audited evidence pack

보여 주면 안 되는 것:

- 후보 스킬
- Judge가 원하는 실패 문구
- Mutator 결과
- 다른 partition의 holdout 사례

Case Designer는 “이 스킬이 틀리게 만들라”가 아니라 “이 실패가 발생했는지 객관적으로 구분 가능한 상황을 만들라”는 지시를 받아야 한다.

### 4. Adversarial Reviewer

목적:

Interviewer가 `implementation_ready`라고 주장한 계약을 반대 입장에서 검사한다.

입력:

- public request
- audited repository evidence
- transcript
- final contract
- 동결된 failure lens

private owner oracle을 줄지 여부는 두 모드로 분리하는 편이 좋다.

- blind handoff review: oracle 없이 실제 인계 자료만 보고 판단
- oracle adjudication: oracle을 가진 Judge가 blind review 결과의 정당성을 판정

Adversarial Reviewer가 찾을 수 있는 blocker 범위:

- repository evidence 위반
- 확인되지 않은 요구사항 발명
- transcript에서 확인된 결정의 contract 누락
- 객관적으로 판별할 수 없는 acceptance
- fresh implementer가 내려야 하는 새 material decision
- contract 내부 모순
- 보존 요청과 호환되지 않는 동작 변경

근거 없는 문제를 만들어 내면 안 된다. 모든 finding에는 contract/transcript/evidence의 정확한 항목을 인용하게 한다.

### 5. Adjudicator

Adversarial Reviewer의 finding을 바로 Mutator에 넘기지 않는다. 별도 Adjudicator가 다음을 판정한다.

- finding이 실제 관찰 증거로 지지되는가
- lens가 정의한 실패에 해당하는가
- 중요한 실패인가, 단순 선호인가
- owner oracle이나 repository evidence와 충돌하는가

승인된 finding만 mutation 입력으로 사용한다.

## 권장 전체 흐름

```text
일반 seed
→ Failure-Lens Proposer
→ Lens Auditor / Deduplicator
→ lens set 동결 및 digest 기록
→ Lens-Conditioned Case Designer
→ Repository Discovery / Evidence Auditor (repository mode)
→ Owner Oracle Designer
→ Interviewer ↔ Owner
→ blind Adversarial Reviewer
→ oracle-aware Judge / Adjudicator
→ development에서만 Mutator
→ 별도의 holdout으로 재검증
```

LLM의 지식을 곧바로 스킬 규칙으로 바꾸지 않는다.

```text
LLM 일반 지식
→ 가능한 실패 유형
→ 관찰 가능한 검사
→ 실제 실패 관찰
→ 독립 판정
→ 가장 작은 일반화된 수정
```

이 순서를 지켜야 다시 자기 확신형 진화로 돌아가지 않는다.

## 다른 도구의 장점을 독립적으로 재발견하는 예

다른 도구의 본문을 읽지 않아도 다음과 같은 경로가 가능하다.

```text
“인터뷰 답변이 최종 계약에서 빠질 수 있다”
→ transcript-to-contract synthesis-loss 검사

“새 구현자가 계약만 보고 서로 다른 동작을 만들 수 있다”
→ fresh-context handoff 검사

“코드에서 발견한 사실이 새 제품 동작을 결정하는 권한처럼 사용될 수 있다”
→ evidence와 normative authority 분리

“성공 조건은 있지만 실행 가능한 확인 방법이 없다”
→ requirement-to-verification 연결 검사

“구현 과정에서 새 결정을 내렸지만 기록되지 않을 수 있다”
→ implementation decision observability 검사
```

이것은 `ultimateinterview`, Deep Interview 또는 Codex Plan Mode의 문구를 복사하는 것이 아니다. 같은 일반적 실패 원인에서 유사한 방어 장치를 독립적으로 도출하는 것이다.

## 구현 제약

- 기존 실행 산출물은 관찰 증거다. 명시적으로 재실행하는 작업이 아니면 수정하지 않는다.
- 실행 중인 run directory를 재사용하거나 덮어쓰지 않는다.
- 모든 새 역할은 별도 ephemeral `codex exec` 호출이어야 한다.
- 모든 역할 출력은 닫힌 JSON schema로 검증한다.
- role prompt와 실제 input/output을 `calls/NNN-role.json`에 보존한다.
- manifest에 역할 목록, 모델 선택 여부, 입력 digest, lens-set digest, 종료 이유를 기록한다.
- holdout에서는 Mutator를 호출하지 않는다.
- 개발/holdout identity overlap은 fail-closed를 유지한다.
- 논리적 격리를 OS 보안 격리로 표현하지 않는다.
- 역할이 malformed JSON, timeout, 정보 경계 위반, 미처리 finding 또는 미처리 conflict를 남기면 run을 무효화한다.
- 스킬 개선 후보는 자동으로 `clarify-requirements/SKILL.md`에 승격하지 않는다.

## 피해야 할 잘못된 구현

- “좋은 인터뷰 스킬의 특징을 모두 나열하라”는 답을 곧바로 v5에 붙이기
- 다른 도구의 `SKILL.md`를 Failure-Lens Proposer에게 제공하기
- 후보 스킬을 본 Case Designer가 그 후보 전용 함정 사례를 만들기
- Adversarial Reviewer의 모든 주장을 검증 없이 실패로 인정하기
- development 사례에 사용한 lens와 case를 holdout에서 그대로 재사용하기
- 한 greeting 사례의 failure를 모든 도메인의 일반적 진리로 선언하기
- 역할 수가 늘었다는 사실만으로 독립성이나 품질 향상을 주장하기
- 현재 배포 v4와 생성된 candidate skill을 혼동하기

## 완료 조건

다음 조건을 모두 만족해야 이번 개선이 완료된다.

1. Failure-Lens Proposer, Lens Auditor/Deduplicator, Case Designer, Adversarial Reviewer, Adjudicator의 역할과 JSON schema가 코드에 명시되어 있다.
2. 각 역할의 허용 입력과 금지 입력이 `PROTOCOL.md`에 기록되어 있다.
3. lens set이 사례 생성 전에 동결되고 digest가 manifest에 기록된다.
4. Adversarial finding은 독립 adjudication을 통과한 것만 Mutator에 전달된다.
5. development와 holdout 사이의 lens/case/identity 오염을 harness가 fail-closed로 막는다.
6. greenfield와 repository mode 모두 기존 동작을 유지한다.
7. forced close, stagnation, safety ceiling, evidence audit fail-closed 동작이 유지된다.
8. 단위 테스트가 새 정보 경계와 오염 방지 규칙을 증명한다.
9. 최소 한 번의 development run이 완결된 manifest와 candidate를 만든다.
10. 별개의 holdout run이 Mutator 없이 완결되고, development 개선의 일반화 여부를 판정한다.
11. 실패한 holdout도 성공처럼 보고되지 않고 `failure.json` 또는 비준비 계약으로 보존된다.
12. 검증 전에는 candidate를 v5 또는 배포 스킬로 자동 승격하지 않는다.

## 최소 테스트 목록

- Failure-Lens Proposer가 candidate skill을 입력으로 받지 않는지 검사
- Lens Auditor가 중복·관찰 불가능·도구 종속 lens를 거부하는지 검사
- Case Designer가 candidate와 mutation을 받지 않는지 검사
- Adversarial Reviewer가 정확한 evidence/contract 참조 없는 finding을 만들면 거부되는지 검사
- Adjudicator가 단순 선호를 material failure로 승인하지 않는지 검사
- Mutator가 private oracle, raw holdout case 또는 미승인 finding을 받지 않는지 검사
- holdout 경로에서 Mutator 호출이 불가능한지 검사
- 개발/holdout lens set과 case identity 오염을 registry가 차단하는지 검사
- lens-set digest가 변경되면 manifest에 반영되는지 검사
- 기존 repository citation sealing과 conflict disposition 검사가 유지되는지 검사
- 실행 제한 시 non-ready contract로 강제 종료되는지 검사

## 권장 작업 순서

1. 현재 `run_evolution.py`와 `tests/test_native_evolution.py`의 최신 dirty 상태를 다시 읽는다. 이 핸드오프가 작성된 뒤 다른 세션이 수정했을 수 있다.
2. 완료된 `greeting-repo-v4-holdout-2`는 final-evaluation evidence로만 보존하고 mutation 입력이나 재실행 경로로 사용하지 않는다.
3. 역할별 입력 경계와 schema를 먼저 테스트로 고정한다.
4. lens 생성·감사·동결 단계를 구현한다.
5. adversarial review와 adjudication 단계를 구현한다.
6. manifest와 study registry를 확장한다.
7. 기존 테스트와 새 테스트를 모두 실행한다.
8. 새 development run과 오염되지 않은 holdout run을 수행한다.
9. 실제 관찰 결과를 비교하고, candidate 승격 여부는 별도로 보고한다.

## 검증 명령

이 프로젝트의 Python 도구는 owning project의 `uv run`을 사용한다.

```bash
cd /Users/jpark/IdeaProjects/harnesses/requirements-interview-evolution
uv run python -m unittest tests/test_evolution.py tests/test_native_evolution.py
```

새 run은 기존 디렉터리를 재사용하지 말고 고유한 경로를 사용한다. 명령 예시는 `native-evolution/PROTOCOL.md`의 최신 CLI와 일치하도록 조정한다.

## 완료 보고에 포함할 내용

- 변경한 파일
- 추가한 각 역할과 정보 경계
- 새 JSON schema와 coordinator fail-closed 검사
- 실행한 테스트와 결과
- development run 결과
- holdout run 결과
- 실제로 발견된 새로운 failure lens
- mutation이 그 실패를 어떻게 일반화했는지
- candidate를 배포 v5로 승격했는지 여부와 그 근거
- 남은 실험 한계, 특히 논리적 격리와 표본 수 한계

## 최종 주의

이 작업의 성공은 역할이나 규칙이 많아지는 것이 아니다. 성공 기준은 다음이다.

> 다른 도구를 정답으로 보지 않고도 LLM의 일반 지식에서 새로운 실패 가능성을 제안하고, 그 실패를 독립된 실제 실행에서 관찰하며, 검증된 실패만 가장 작은 일반 규칙으로 스킬에 반영할 수 있는가?

관찰되지 않은 좋은 아이디어는 개선 후보일 뿐이며, 검증된 진화로 보고하지 않는다.
