# SWE-bench v0 통합 신호 진화 결과

실험과 독립 완료 검증을 마쳤다. development judge 신호가 mutation을 발생시켰고
candidate는 v0와 달라졌다. strict holdout gate는 실패해 승격하지 않았다.

## Development와 mutation

- fresh 구현 decision: 0개
- invented requirement: 2개
- compatibility regression: 1개
- 통합 신호: 3개
- 전수 검토: 3/3
- skill gap: 3개
- mutation: 1회 수행
- candidate SHA-256: `963767bc6c2c8d7816dad3d9cfe1b7bd258790ac0c01a551f3638b57102851d6`

mutation은 저장소 발견, material decision의 owner 확인·승인된 기본값·명시적 위임,
근거 없는 acceptance 확장 금지, 호환성 경계와 잔여 위험 명시를 v0에 추가했다.

## Validation

candidate는 계약 품질에서 baseline보다 명확히 좋아졌다.

- baseline: invented 5, regression 4, repository fidelity 0.837, decision 0
- candidate: invented 0, regression 0, repository fidelity 0.970, decision 1
- 두 arm 모두 implementation-ready 3/3

고정된 사전식 선택 규칙은 implementation decision 수를 계약 품질보다 먼저 비교한다.
따라서 decision 0인 baseline이 승자가 됐다. candidate의 유일한 decision도 전수 검토했고,
기존 overridable helper의 반환 형태 호환성을 계약이 끝까지 확정하지 않은 skill gap이었다.

## Holdout

baseline이 선택되어 재사용 holdout에 실행됐다.

- implementation-ready: 2/4
- invented requirements: 11
- compatibility regressions: 8
- implementation decisions: 0
- leakage: 1
- approved material blockers: 2

strict gate 실패로 v1을 만들거나 deployed v0를 변경하지 않았다. 기존 holdout을
재사용했으므로 신규 blind 일반화 증거로 해석하지 않는다.
