# Ultimateinterview Contract-Drift 벤치마크

## 무엇을 측정하는가

이 벤치마크는 소프트웨어 엔지니어링 질문을 다룹니다. 요구사항이 인터뷰와 Build Contract를 거친 뒤, fresh 구현 컨텍스트에 원래 의도한 동작이 얼마나 남는지를 측정합니다.

공개 개발 corpus는 `corpus/public/cases.json`에 정의되어 있습니다. 각 case에는 프롬프트와 깨끗한 starter tree가 있습니다. 비공개 holdout 자료는 이 저장소에 포함하지 않습니다.

## 결정론적 개발 벤치마크

`measure-contract-drift/scripts/run-fake.sh`는 결정론적 개발 fixture를 실행합니다. 모델 호출이나 holdout 접근 없이 벤치마크 mechanics를 검증합니다. 이 결과는 모델 품질, production 인터뷰 효과, holdout 성능의 증거가 아닙니다.

```sh
measure-contract-drift/scripts/run-fake.sh
```

공개 corpus는 별도로 검증할 수 있습니다.

```sh
uv run --project measure-contract-drift \
  driftbench validate-corpus \
  --public-root measure-contract-drift/corpus/public \
  --partition dev
```

## Live 스킬 진화 평가

Live lifecycle은 `driftbench interview-eval run --study ...`와 `driftbench interview-eval resume --run-dir ...`입니다. Study manifest가 모든 direct Codex role의 모델과 reasoning effort를 고정합니다.

각 candidate-case 반복마다 runtime은 다음을 수행합니다.

1. public starter를 격리된 cell repository에 복사합니다.
2. decision ID, 선택지, 추천, 근거, 영향 boundary가 있는 구조화 결정을 받습니다.
3. simulator가 모든 호환 추천을 그대로 제출합니다.
4. implementation spec을 seal합니다.
5. sealed spec만 받은 fresh implementer를 시작합니다.
6. diff, implementation return, 실행 evidence, `decision.jsonl`을 요구합니다.
7. 결정론적 검사, 독립 실행, blinded judge로 다섯 지표를 재구성합니다.

Implementer는 인터뷰 transcript나 evaluator feedback을 받지 않습니다. 추천, evidence binding 또는 decision log가 누락되거나 malformed이면 fail-closed 처리합니다.

제한된 실행을 시작합니다.

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-generations 10 \
  --max-candidates 8
```

동일한 CLI를 직접 호출할 수도 있습니다.

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --study measure-contract-drift/configs/evolution-study.json
```

`--smoke`는 실제 모델 smoke 전용 경로입니다. Frozen candidate 1개를 train case 1개에서 2회 실행하며 effectiveness claim을 만들지 않습니다. 각 direct model role은 wall-clock 5분을 넘으면 fail-closed 처리됩니다.

12개 public case는 고정 6 train / 3 validation / 3 final-test 분할을 사용합니다. 세대 0은 frozen baseline과 7개 변이이며 이후 세대는 8개 후보입니다. Candidate-case는 2–5회 실행합니다. 최대 10세대 또는 validation Pareto hypervolume 3세대 무개선에서 멈춥니다. Final-test는 frozen baseline과 champion을 case당 5회 평가한 뒤 mutation과 재선발을 잠급니다.

모든 case가 public이므로 final-test는 process-isolated 평가이며 private holdout 또는 일반화 증거가 아닙니다. Generator에는 train failure taxonomy와 최대 3개 제안만 제공되고 validation 상세 artifact는 숨겨집니다.

Enrollment 파일 `<project-root>/.measurecontractdrift/live.toml`에서 `model_reasoning_effort`를 설정할 수 있습니다. 생략하면 `"medium"`이 기본값이며 interviewer, simulator, implementation, postmortem Codex session에 모두 적용됩니다. 모델은 `gpt-5.6-sol`로 고정됩니다.

## Run output과 resume

새 run은 다음 위치에 기록됩니다.

```text
<project-root>/.measurecontractdrift/interview-eval/live-<timestamp>-evolution/
```

저장된 JSON 파일은 key를 정렬하고 두 칸 들여쓰기로 pretty print됩니다. Run root에는 다음이 있습니다.

- `state.json`: digest binding, candidate, 완료 cell, archive 진행, final lock
- `rubrics/`, `candidates/`, `cells/`: 고정 rubric과 candidate evidence
- `final-test.json`: public process-isolated baseline/champion 비교
- `receipt.json`: 완료 상태와 champion identity

Run directory로 resume합니다.

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory>
```

완료된 cell은 artifact hash가 일치할 때만 재사용합니다. Study, corpus, baseline skill, runtime, rubric 또는 완료 cell evidence가 drift하면 resume을 거부합니다.

## 결과 읽기

CLI는 run directory와 status가 담긴 compact JSON을 출력합니다. Cell effectiveness는 contract coverage, recommendation integrity, implementation conformance, verification credibility, decision governance의 최솟값입니다. Invalid evidence 또는 critical governance failure가 있으면 0입니다.

Live path는 public development case만 평가합니다. 비공개 holdout이나 일반적인 모델 성능에 대한 주장을 만들지 않습니다.
