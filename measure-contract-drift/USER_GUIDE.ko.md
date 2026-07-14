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

## Live 인터뷰 평가

Live lifecycle은 `driftbench interview-eval run`과 `driftbench interview-eval resume`입니다.

선택된 각 case와 treatment마다 runtime은 다음을 수행합니다.

1. public starter를 격리된 cell repository에 복사합니다.
2. direct Codex interviewer session을 시작하고 그 인터뷰 안에서만 thread를 유지합니다.
3. vendored Ultimateinterview skill로 Discovery Record를 만듭니다.
4. vendored authority compiler로 Build Contract를 생성합니다.
5. starter tree로 제한된 fresh direct Codex implementation session을 시작합니다.
6. vendored checker로 implementation return과 evidence를 검증합니다.
7. fresh direct Codex postmortem session을 시작하고 report를 검사합니다.

Simulator와 implementation/postmortem session은 ephemeral입니다. Implementation session은 인터뷰 transcript가 아니라 sealed Build Contract를 받습니다.

제한된 실행을 시작합니다.

```sh
measure-contract-drift/scripts/run-live.sh \
  --max-cells 1 \
  --max-parallel 1
```

동일한 CLI를 직접 호출할 수도 있습니다.

```sh
uv run --project measure-contract-drift driftbench interview-eval run \
  --policy <policy-path> \
  --max-cells 1 \
  --max-parallel 1
```

6개 public case를 필수 `baseline`과 `candidate` treatment로 실행하므로 총 12개 cell입니다. baseline은 vendoring된 immutable skill입니다. `candidate_skill`은 workspace 내부의 상대 경로여야 합니다. 실행 전에 candidate bytes, enrollment, corpus row, starter tree를 run의 `inputs/`에 복사합니다. Resume은 고정된 input과 완료된 모든 cell을 검증한 뒤 계속합니다. `--max-cells`는 현재 invocation에서 처리할 pending cell을 1–12개로 제한하고, `--max-parallel`은 1–12개 cell의 동시 실행 수를 지정합니다.

## Run output과 resume

새 run은 다음 위치에 기록됩니다.

```text
<project-root>/.measurecontractdrift/interview-eval/live-<timestamp>-interview-eval/
```

저장된 JSON 파일은 key를 정렬하고 두 칸 들여쓰기로 pretty print됩니다. Run root에는 다음이 있습니다.

- `state.json`: cell별 진행 상태와 결과
- `manifest.json`: 생성된 파일의 hash
- `receipt.json`: 전체 상태, 완료/전체 cell 수, manifest digest

각 cell에는 `repo/`와 `.ultimateinterview/<case-id>/` session directory가 있습니다. 이 경로에는 Discovery Record, Build Contract, implementation return, diff, checker evidence, postmortem이 포함됩니다.

Run directory로 resume합니다.

```sh
measure-contract-drift/scripts/run-live.sh \
  --resume <run-directory> \
  --max-parallel 1
```

완료된 cell은 유지하고, 완료되지 않은 cell만 다시 실행합니다. Resume에도 `--max-cells`를 지정해 해당 invocation을 제한할 수 있습니다.

## 결과 읽기

CLI는 run directory와 status가 담긴 compact JSON을 출력합니다. `partial`은 제한된 invocation이 성공했지만 pending cell이 남았다는 뜻이고, `completed`는 12개 cell이 모두 완료되었다는 뜻입니다. `failed`는 시도한 cell 중 하나 이상이 실패했다는 뜻이므로 `state.json`의 해당 cell과 session evidence를 확인하십시오.

Live path는 public development case만 평가합니다. 비공개 holdout이나 일반적인 모델 성능에 대한 주장을 만들지 않습니다.
