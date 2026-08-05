# SWE-bench v1 계약 오류 우선 다음 세대 결과

사전 고정한 계약 오류 우선 선택 규칙과 회전 validation으로 다음 세대를 완료했고,
독립 완료 검증을 통과했다. candidate가 validation에서 승리해 holdout에 실행됐지만
strict gate는 실패해 승격하지 않았다.

## Development와 mutation

- 통합 신호: 18개
- implementation decision: 2개
- invented requirement: 10개
- compatibility regression: 6개
- 전수 검토: 18/18
- skill gap: 17개
- mutation: 수행
- baseline SHA-256: `963767bc6c2c8d7816dad3d9cfe1b7bd258790ac0c01a551f3638b57102851d6`
- candidate SHA-256: `3ffaf233371eecb728b4bcff945ad9d2ba9185f4dda33f2aaafafe9a77ee333e`

## 회전 Validation

- baseline: invented 2, regression 0, ready 3/3, decision 0, fidelity 0.980
- candidate: invented 0, regression 0, ready 3/3, decision 2, fidelity 0.993
- 사전 고정 규칙의 승자: candidate

candidate의 validation decision 2개는 전수 검토 결과 skill gap이 아니었다. snapshot을
어느 내부 계층에서 수행할지와 state assertion 또는 image comparison 중 어떤 테스트
방식을 쓸지는 승인된 observable behavior를 만족하는 구현 재량이었다. 따라서 raw
decision 수가 과잉 신고를 포함한다는 추가 증거가 됐다.

## 재사용 Holdout

- implementation-ready: 1/4
- invented requirements: 13
- compatibility regressions: 8
- implementation decisions: 0
- leakage: 0
- approved material blockers: 0

candidate는 새 validation에서는 계약 오류를 제거했지만 다른 repository family의
holdout에서는 다시 과도한 scope·compatibility 조건을 계약에 넣었다. strict gate 실패로
v2를 만들거나 deployed v1을 변경하지 않았다.

새 validation은 직전 mutation 신호를 만들지 않은 기존 development 3개를 회전한 것으로,
계보상 완전히 미노출된 표본은 아니다. holdout 역시 재사용 세트이므로 신규 blind
일반화 증거가 아니다.
