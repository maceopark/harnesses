# SWE-bench v0 decision 기반 단일 세대 진화 실험

이 실험은 `evolution/v0/SKILL.md`에서 새로 시작한다. 기존에 승인된 SWE-bench
개발 8개, 검증 3개, holdout 4개와 공식 harness 증거는 그대로 재사용하되,
인터뷰와 구현, mutation, 검증 산출물은 이 디렉터리에 새로 만든다.

## 진화 규칙

- 각 인터뷰 계약을 받은 fresh 구현 agent는 계약에 없는 결정을 내려야 할 때만
  결정 전에 저장소 루트의 `decision.jsonl`에 한 행을 기록한다.
- 결과에 영향을 주는 기술 선택도 대안에 따라 동작, 호환성, 안전, 비용, 데이터,
  acceptance, 가역성이 달라지면 기록 대상이다.
- 개발 8개 구현에서 생성된 모든 행을 빠짐없이 정확히 한 번 검토한다.
- skill이 미리 해소했어야 할 결정은 모두 포괄하는 일반적인 최소 수정 하나로
  candidate를 최대 한 개 만든다. 행이 0개면 mutation을 호출하지 않는다.
- 검증에서는 `decision.jsonl` 행 수가 더 적은 arm을 우선한다.
- holdout 4개 모두에서 행이 0개여야 strict gate를 통과한다.

## 병렬성과 격리

- train: 개발 8개 동시 실행
- test: baseline 3개와 candidate 3개, 총 6개 동시 실행
- holdout: test 승자 4개 동시 실행
- 단계 순서는 train → mutation → test → holdout이다.
- 구현 agent에는 public request, audited repository evidence, contract만 전달한다.
  gold patch, hidden test, owner oracle은 전달하지 않는다.
- 기존 holdout 재사용 결과이므로 신규 blind-holdout 일반화 증거로 해석하지 않는다.

candidate와 모든 decision 검토 증거는 `runs/batch-mutation/`에 보존한다.
