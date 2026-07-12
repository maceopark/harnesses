# Ultimateinterview Contract-Drift 벤치마크의 작동 원리

## 대상 독자

이 문서는 CLI, JSON, 테스트, Docker, 해시의 기본 개념에 익숙하지만 ML을 전공하지 않은 3년차 전후 소프트웨어 엔지니어를 대상으로 합니다.

모델 학습, 임베딩, 복잡한 통계를 몰라도 됩니다. 이 벤치마크의 핵심 질문은 소프트웨어 엔지니어링 문제입니다.

> 요구사항이 인터뷰와 인수인계를 통과한 뒤, 원래 의도한 동작이 fresh 구현 컨텍스트에 얼마나 온전하게 전달되는가?

## 1. 무엇을 측정하는가

일반적인 에이전트 개발 과정에는 정보가 손실될 수 있는 경계가 여러 개 있습니다.

1. 사용자가 기능을 설명합니다.
2. 인터뷰어가 명확화 질문을 합니다.
3. 인터뷰 결과를 `handoff`와 Build Contract로 컴파일합니다.
4. 새로운 구현자가 인터뷰 대화 없이 이 산출물만 전달받습니다.
5. 구현 결과를 실제 관찰 가능한 동작으로 검증합니다.

각 경계에서 요구사항이 누락되거나, 약화되거나, 모순되거나, edge case가 잘못 구현될 수 있습니다.

이 벤치마크는 이 과정을 분산 시스템처럼 다룹니다. 각 역할은 제한된 입력 계약을 가지며, immutable artifact를 만들고, 다른 역할의 비공개 컨텍스트를 몰래 읽을 수 없습니다.

## 2. 전체 파이프라인

```text
고정 case + starter 저장소
          |
          v
planner/interviewer ----> handoff + Build Contract
                                  |
                                  v
                              fresh 구현자
                                  |
                                  v
                           독립 observation 역할
                                  |
                                  v
                         typed contract 비교기
                                  |
                                  v
                           fresh postmortem
                                  |
                                  v
                          scorecard + receipts
```

역할은 의도적으로 분리됩니다.

- **Planner/interviewer:** case를 명시적인 handoff와 Build Contract로 변환합니다.
- **Implementer:** 허용된 전달 산출물과 깨끗한 starter tree만 받습니다.
- **Observation 역할:** 구현을 독립적으로 materialize하고 실행합니다.
- **Comparator:** 기대 동작과 관찰 동작을 typed representation으로 정확히 비교합니다.
- **Postmortem:** 구현자의 작업 컨텍스트를 공유하지 않고 완료된 증거만 분석합니다.

이 구조는 동일한 에이전트가 요구사항 작성, 구현, 자기 평가를 모두 수행하면서 숨겨진 컨텍스트까지 유지하는 평가 오류를 방지합니다.

## 3. Case와 프롬프트

공개 개발 corpus는 다음 파일에 있습니다.

```text
corpus/public/cases.json
```

고정된 개발 case 6개를 포함합니다.

- 북마크 태그 추가
- 설정 overlay 병합
- CSV 연락처 가져오기
- 지출 기록
- 리마인더 생성
- todo 완료

각 case는 다음 정보를 고정합니다.

- 안정적인 case ID와 opaque token
- 자연어 프롬프트
- 깨끗한 starter 저장소
- starter tree digest
- 기대 명령과 persistence boundary

전체 연구 설계는 **공개 개발 case 6개 + 비공개 holdout case 4개**입니다. Holdout 프롬프트와 starter는 의도적으로 이 저장소에 포함하지 않습니다. 외부 공급 계약과 공개해도 안전한 commitment만 다음 파일에 있습니다.

```text
corpus/external-holdout/service-manifest.template.json
```

이는 production secret을 테스트 러너에 넣지 않는 것과 비슷합니다. Controller는 trusted evaluation을 요청할 수 있지만 비공개 데이터를 직접 열람하거나 그 데이터에 맞춰 최적화할 수 없습니다.

## 4. 자동 인터뷰

서로 다른 두 개념을 구분해야 합니다.

### 결정론적 fake-development 모드

저장소에 포함된 한 줄 실행은 deterministic role adapter를 사용하며 모델을 호출하지 않습니다. 이 모드는 다음을 검증합니다.

- 역할 경계가 작동하는가
- 인터뷰 산출물을 생성하고 전달할 수 있는가
- 구현을 독립적으로 실행할 수 있는가
- 채점이 재현 가능한가
- 변조와 잘못된 resume이 fail-closed 되는가

즉 개발 인프라에 대한 증거이지 특정 LLM이 우수하다는 증거가 아닙니다.

### Live 인터뷰 모드

Service interface는 외부에서 공급된 모델과 trusted user simulator가 질문 수를 미리 고정하지 않은 인터뷰를 진행할 수 있도록 설계되어 있습니다. Simulator는 interaction budget과 명시적인 routing rule 안에서 검증된 요청에 답합니다.

Live provider credential, simulator, evaluator, reporter, 비공개 holdout 데이터는 이 독립 저장소 밖에서 공급해야 합니다. 필요한 서비스가 없으면 fake answer로 몰래 대체하지 않고 blocked 결과를 냅니다.

## 5. Docker/OCI worker를 사용하는 이유

Planner, implementer, observation, postmortem은 서로 분리된 OCI worker에서 실행됩니다.

Worker 정책은 다음을 강제합니다.

- digest-addressed Linux arm64 이미지
- 네트워크 차단
- read-only root filesystem
- non-root UID/GID
- Linux capability 제거
- `no-new-privileges`
- 고정된 seccomp 정책
- CPU, 메모리, 프로세스, 디스크 제한
- `/tmp`와 역할 전용 named volume만 허용

역할 입력은 canonical JSON으로 named volume에 기록됩니다. 작업 시작 전에 입력 digest를 검증합니다. Worker는 해당 입력 digest에 결속된 canonical output 하나를 기록합니다. Controller는 선언된 artifact만 검증하고 가져옵니다.

이 구조가 악의적인 컴퓨터 소유자까지 방어하는 것은 아닙니다. 로컬 Docker daemon과 운영자는 신뢰합니다. OCI 격리의 목적은 역할 간 우발적인 컨텍스트 공유와 선언되지 않은 파일·네트워크 접근을 방지하는 것입니다.

## 6. Canonical JSON과 해시

많은 artifact는 해싱 전에 canonicalize됩니다.

- UTF-8 인코딩
- 문자열 정규화
- object key 정렬
- compact JSON 표현
- 필요한 경우 trailing newline
- SHA-256 digest

일반 JSON은 동일한 값을 여러 byte 표현으로 쓸 수 있습니다. Canonicalization이 없다면 의미 없는 formatting 차이만으로 해시가 달라져 replay가 불안정해집니다.

Digest chain은 다음을 결속합니다.

```text
run configuration
  -> corpus와 arm 정의
  -> cell input
  -> role context와 전달 artifact
  -> worker input/output
  -> implementation과 observation
  -> lifecycle manifest
  -> attempt receipt
  -> terminal receipt
  -> scorecard
```

어떤 artifact가 바뀌면 downstream replay validation이 오래된 chain을 거부합니다.

## 7. 채점하는 세 가지 arm

개발 벤치마크는 세 가지 workflow shape을 비교합니다.

### `direct-v1`

Planner가 만든 계약 없이 fresh implementer가 공개 case와 starter를 받습니다. Baseline입니다.

### `plan-v1`

Planner가 handoff와 Build Contract를 만듭니다. Fresh implementer는 이 산출물과 깨끗한 starter만 받습니다.

### `ultimateinterview-current-v1-structural`

Planner 경로가 전달 전에 frozen native Ultimateinterview v1 structural/readiness lifecycle을 추가로 실행합니다.

네 번째 fixture인 `ultimateinterview-full-v2-expected-fail`은 conformance test에만 사용합니다. 고정된 snapshot이 해당 protocol version에서 요구하는 creditable execution receipt를 제공할 수 없으므로 채점 대상에서 제외됩니다.

## 8. Fresh-context 전달

Implementer는 원래 인터뷰 transcript나 planner의 hidden state를 받지 않습니다.

Planning arm에서는 다음 정보만 전달됩니다.

- 깨끗한 starter tree
- handoff 데이터
- Build Contract 데이터
- 명시적으로 허용된 metadata와 digest

Implementation output은 deterministic content-addressed implementation recipe로 전달됩니다. Observation worker가 이를 독립적으로 재현하고, 실행 전에 생성된 tree digest를 확인합니다.

따라서 이 벤치마크는 shared conversation memory가 아니라 handoff의 품질을 측정합니다.

## 9. Observation과 semantic comparison

프로세스가 exit 0으로 끝나는 것만으로는 부족합니다. Observation 역할은 case별 동작을 확인합니다.

- 기대한 명령을 실행했는가
- 올바른 case와 state file을 사용했는가
- 명령이 성공을 보고했는가
- 필요할 때 state가 실제로 변경되었는가
- 보고된 state digest가 디스크 파일과 일치하는가
- pre-state와 post-state가 case별 transition을 만족하는가

기대 동작과 관찰 동작은 다섯 차원의 typed atom으로 표현됩니다.

- **guard:** obligation이 적용되는 조건
- **effect:** 발생해야 할 결과
- **polarity:** must 또는 must-not
- **boundary:** 동작이 적용되는 범위
- **temporal:** obligation이 만족되어야 하는 시점

Primary credit은 exact matching입니다. 전체 expected atom set과 observed atom set이 일치해야 합니다. 너무 넓거나, 부분적이거나, 모순된 동작은 exact credit을 받지 못합니다.

## 10. Receipt와 score replay

Controller는 lifecycle의 각 단계에 대한 receipt를 저장합니다.

- input stage
- role launch
- output read
- workspace volume cleanup
- attempt completion
- terminal cell result

Scoring은 복사된 점수 필드를 신뢰하지 않습니다. 다음을 다시 구성하고 검증합니다.

- 허용된 arm
- worker image와 OCI profile
- launch command와 control
- role input/output digest
- native fixture evidence
- observation predicate
- typed comparison 결과

위조된 scorecard, 변경된 worker image, 대체된 receipt, 선언되지 않은 파일, 변조된 observation은 score 또는 resume을 fail-closed로 만듭니다.

## 11. 개발 점수의 의미와 한계

Fake-development scorecard는 deterministic implementation의 exact contract coverage를 보여줍니다. 벤치마크 mechanics와 regression test를 검증하는 데 유용합니다.

다음 사항을 증명하지는 않습니다.

- 모델 품질
- production에서의 인터뷰 효과
- 특정 arm의 우월성
- holdout 성능
- creditable v2 protocol 성능

실제 비교를 위해서는 외부 live model, 여러 case와 seed, 사전 등록된 설정, 비공개 holdout evaluator/reporter 경로가 필요합니다.

## 12. 벤치마크 실행

Workspace root에서 실행합니다.

```sh
benchmark/ultimateinterview-contract-drift/scripts/run-fake.sh
```

스크립트가 수행하는 작업은 다음과 같습니다.

1. 고정된 worker image를 빌드합니다.
2. immutable Docker image ID를 확인합니다.
3. deterministic development run을 시작하거나 resume합니다.
4. 6개 case를 3개 scored arm에서 실행합니다.
5. Artifact를 검증하고 scorecard를 기록합니다.

Corpus 검증:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  driftbench validate-corpus \
  --public-root benchmark/ultimateinterview-contract-drift/corpus/public \
  --partition dev
```

Test suite 실행:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  --extra test pytest -q \
  benchmark/ultimateinterview-contract-drift/tests
```

Worker preflight:

```sh
uv run --project benchmark/ultimateinterview-contract-drift \
  python -m driftbench.worker_launcher \
  --project-root benchmark/ultimateinterview-contract-drift \
  preflight
```

## 13. Run directory 읽기

Run directory에는 다음 파일이 있습니다.

- `run-manifest.json`: immutable run identity와 input binding
- `state.json`: 현재 run과 cell 상태
- `evaluation-status.json`: 외부에 공개해도 안전한 orchestration 상태
- `scorecard.json`: 개발 전용 metric
- `cells/<cell-id>/`: input, context, role execution, implementation, observation, postmortem, receipt

먼저 `scorecard.json`을 보고, 각 cell의 `terminal-receipt.json`과 `lifecycle-manifest.json`을 확인합니다. JSON 파일 하나를 단독 authoritative source로 간주하지 말고 참조된 digest chain을 따라가야 합니다.

## 14. 자주 생기는 오해

### “점수가 1.0이면 인터뷰 방법의 효과가 입증된 것 아닌가?”

아닙니다. Fake 모드에서는 deterministic fixture implementation이 개발 predicate를 만족했다는 뜻입니다.

### “Observer가 implementer가 변경했다고 말한 내용을 믿으면 되지 않나?”

아닙니다. Observer는 implementation을 재현하고 digest를 확인한 뒤 실행하며 state transition을 검증합니다.

### “구현하기 쉽게 전체 transcript를 전달하면 안 되나?”

이 벤치마크는 handoff 품질을 측정합니다. Shared transcript memory는 handoff에서 발생한 정보 손실을 가립니다.

### “Holdout 프롬프트 4개는 왜 없는가?”

Agent나 optimizer가 holdout case를 읽을 수 있으면 반복 개발 과정에서 과적합할 수 있습니다. Holdout secrecy는 단순한 파일 이름 규칙이 아니라 access-control 속성입니다.

### “Docker는 완벽한 보안 sandbox인가?”

아닙니다. 로컬 운영자와 Docker daemon을 신뢰합니다. OCI 격리는 재현 가능한 역할 분리와 least privilege를 위한 것입니다.

## 15. 주요 소스 위치

```text
README.md                              빠른 실행 방법
corpus/public/cases.json               공개 프롬프트 6개
corpus/public/starters/                깨끗한 CLI starter tree
corpus/external-holdout/               private service boundary template
configs/fake-dev.toml                  deterministic run 설정
arms/arms.json                         scored/non-scored arm 정책
oci/profile.json                       worker isolation 정책
src/driftbench/cli.py                  controller와 command flow
src/driftbench/role_worker.py          role 실행과 observation
src/driftbench/worker_launcher.py      Docker launch와 receipt replay
src/driftbench/semantic.py             exact typed comparator
src/driftbench/metrics.py              score 재구성
```
