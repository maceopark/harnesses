# 네이티브 역할 분리형 진화 구현 완료 보고

## 결론

`NATIVE_EVOLUTION_HANDOFF.ko.md`에서 요구한 failure-lens 기반 진화 경로를 구현하고 검증했다. 배포 스킬은 검증된 v5로 승격했으며 스킬 본문은 영어, 운영 문서는 한국어를 기본으로 유지한다.

## 변경 파일

- `native-evolution/run_evolution.py`
- `native-evolution/PROTOCOL.md`
- `tests/test_native_evolution.py`
- `tests/test_evolution.py`
- `clarify-requirements/SKILL.md`
- `evolution/v5/SKILL.md`

## 추가·강화한 역할과 정보 경계

- Failure-Lens Proposer: 일반 seed와 고정 목적만 받는다.
- Lens Auditor / Deduplicator: 모든 lens의 관찰 가능성, 중요성, 해결책 중립성, 중복 대표 ID를 판정한다.
- Lens-Conditioned Case Designer: 동결 lens와 context만 받고 candidate, mutation, 다른 partition 사례를 받지 않는다.
- Blind Adversarial Reviewer: 공개 인계 산출물만 보고 정확한 JSON pointer와 전체 값을 인용한다.
- Oracle-aware Adjudicator: 모든 finding을 독립 판정하며 승인된 finding만 Mutator로 보낸다.

모든 역할은 별도의 `codex exec --ephemeral` 프로세스다. 격리는 논리적 context 격리이며 OS read-deny 보안 경계로 표현하지 않는다.

## Schema와 coordinator fail-closed

- 모든 역할 출력은 닫힌 JSON schema를 사용한다.
- transport 강제와 별도로 coordinator가 schema를 다시 검증한다.
- Lens Auditor는 모든 제안을 정확히 한 번 disposition하고 assessment를 남겨야 한다.
- 정확하지 않은 adversarial 인용, 미처리 finding, 모순된 adjudication은 run을 무효화한다.
- `calls/NNN-role.json`에 실제 prompt, prompt digest, input, output을 보존한다.
- registry 완료 전에 lens self digest, manifest/case identity, 모든 주요 산출물 digest, call prompt digest, candidate/holdout 불변식을 다시 검증한다.
- development/holdout의 seed, public request, lens set, lens case, full case identity 중 하나라도 겹치면 양방향으로 차단한다.

## Adaptive interview budget

배포 v5는 미리 정한 질문 수나 turn 수를 인터뷰 예산으로 사용하지 않는다. 매 답변 뒤 material blocker 집합을 다시 계산하고, blocker가 하나라도 남으면 계속한다. blocker가 0일 때만 contract를 봉인한다.

Harness의 기본 turn ceiling도 제거했다. `--safety-max-turns N`을 명시했을 때만 비상 runaway guard로 작동한다. Stagnation 검출과 역할별 timeout은 유지한다. 명시적 operational limit에 걸리면 거짓 ready가 아니라 non-ready contract를 보존한다.

## 테스트

실행 명령:

```bash
uv run python -m unittest tests/test_evolution.py tests/test_native_evolution.py
uv run python -m py_compile native-evolution/run_evolution.py
```

결과: 24 tests, OK. 배포 `clarify-requirements/SKILL.md`와 `evolution/v5/SKILL.md`가 byte-identical함도 확인했다.

테스트는 역할별 allowlist, coordinator schema 재검증, lens 중복·관찰 불가능·도구 종속 거부, 정확 인용, 단순 선호 finding 거부, Mutator 입력 경계, holdout Mutator 차단, 모든 identity 오염 차단, digest 무결성, repository citation sealing, conflict disposition, stagnation, 명시적 safety ceiling, ceiling 없는 adaptive 완료를 포함한다.

## 실제 실행 결과

### Repository development smoke

`native-evolution/runs/todo-json-lens-v4-dev/`

- mode: development / repository
- termination: completed
- repository fidelity: 1.0
- owner recall: 1.0
- candidate 생성, 기존 스킬과 동일
- 신규 repository 흐름과 digest 무결성 검증용 증거

### Development mutation

`native-evolution/runs/webhook-delivery-adaptive-v5-dev/`

- mode: development / greenfield
- 명시적으로 설정했던 30-turn guard에서 non-ready 종료
- owner recall: 0.97
- 관찰 실패: 실행 가능한 acceptance matrix 부족, lifecycle 상태·복구 경로의 coherence 부족, 이미 명시된 구현 권한 재질문
- Mutator가 가장 작은 일반 규칙을 추가한 candidate 생성

추가된 일반화:

- 명시적인 build/fix/change 요청을 구현 권한으로 보존
- fixture, action, exact result, invariant가 있는 실행 가능한 acceptance scenario 요구
- retry, cancellation, revocation, recovery 등 상호작용 상태의 coherence pass
- material guarantee를 presentation preference보다 먼저 해소

### 첫 adaptive holdout 실패

`native-evolution/runs/notes-archive-adaptive-v5-holdout/`

- mode: holdout / greenfield
- 21개 질문을 임의 예산으로 중단하지 않고 정상 contract까지 진행
- Mutator 없음
- Judge는 owner recall 0.52, implementation-ready false로 판정
- Adjudicator는 synthesis loss, completeness evidence, schema, path safety blocker 4개를 승인
- 실패를 성공으로 보고하지 않고 manifest, transcript, evaluation, adjudication으로 보존

### Candidate repository holdout

`native-evolution/runs/todo-overdue-adaptive-v5-holdout/`

- mode: holdout / repository
- turn ceiling: 없음
- termination: completed
- 질문 4개
- repository fidelity: 1.0
- owner recall: 1.0
- invented requirements: 0
- unnecessary questions: 0
- adversarial blocker: 0
- Mutator와 candidate 파일 없음

이 별도 holdout 통과 후 candidate를 `clarify-requirements/SKILL.md`와 `evolution/v5/SKILL.md`로 승격했다.

## 새로 발견된 failure lens

실제 실행에서 다음 관점이 독립적으로 생성·시험됐다.

- repository 보존 요청에서 새 option이 기존 parsing·출력·오류 계약을 암묵적으로 바꾸는 실패
- owner 답변이 최종 contract에서 손실되거나 약화되는 synthesis loss
- fresh implementer가 archive/schema/path 규칙을 새로 결정해야 하는 handoff gap
- 내부 일관성만 검사하고 선택 완전성을 증명하지 못하는 verification gap
- lifecycle action과 authoritative state/outcome/recovery가 충돌하는 coherence failure
- acceptance가 테스트 주제만 나열하고 정확한 실행 oracle을 제공하지 않는 failure

## 승격과 한계

v5는 별도 holdout 통과 후 승격했다. 기존 v4와 과거 run 산출물은 수정하지 않았다. 실패한 run도 그대로 보존했다.

남은 실험 한계는 다음과 같다.

- 역할 격리는 논리적 경계이며 적대적인 host 읽기를 막는 OS 보안 경계가 아니다.
- 실제 표본 수가 적고 Todo CLI, webhook, notes export에 편중돼 있다.
- LLM Judge와 Adjudicator의 판정은 구조적으로 분리했지만 인간 ground truth를 완전히 대체하지 않는다.
- registry와 digest는 harness 무결성을 높이지만 운영자가 파일을 삭제·변조하는 행위까지 막지는 않는다.
