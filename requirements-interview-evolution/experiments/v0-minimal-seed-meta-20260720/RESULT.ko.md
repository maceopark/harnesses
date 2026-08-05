# v0 minimal seed 재실험 결과

## 결론

새 v0 seed로 한 세대 진화를 다시 실행했으나 development gate에서 세 후보가 모두 탈락했다. validation과 holdout은 열지 않았고, v1은 생성하지 않았다. deployed skill은 v0 그대로다.

## 입력

- seed SHA-256: `144c112df8b12cc465321348a4e5506cec34491ce5485d419104cd847744d144`
- development: 기존 8개 사례 재사용
- validation: 기존 미노출 3개 사례를 예약했으나 열지 않음
- holdout: 기존 4개 사례를 예약했으나 열지 않음
- mutation 입력: development signal 23개
- 후보: replace, delete, add 전략 각 1개씩 총 3개

## Development 결과

| 지표 | baseline | candidate 1 | candidate 2 | candidate 3 |
|---|---:|---:|---:|---:|
| implementation ready | 5 | 6 | 6 | 6 |
| invented requirements | 13 | 2 | 15 | 5 |
| compatibility regressions | 8 | 1 | 7 | 3 |
| implementation decisions | 2 | 2 | 3 | 6 |
| redundant questions | 2 | 0 | 4 | 1 |
| owner recall | 1.0 | 1.0 | 0.9275 | 1.0 |
| repository fidelity | 0.875 | 0.9275 | 0.88 | 0.9075 |

Candidate 1은 합계 지표상 가장 좋았지만 `pallets__flask-5014`와 `sympy__sympy-17318`에서 baseline보다 나빠졌다. 현재 선택 규칙은 같은 사례의 각 결함 지표가 하나도 악화되지 않으면서 적어도 하나는 개선되어야 하므로 탈락했다.

- candidate 1: 3개 사례 개선, 2개 사례 회귀
- candidate 2: 2개 사례 개선, 4개 사례 회귀
- candidate 3: 3개 사례 개선, 3개 사례 회귀
- eligible candidates: 0

## 게이트와 배포 상태

- development selected candidate: 없음
- validation opened: false
- holdout opened: false
- promoted: false
- v1 skill: 생성되지 않음
- deployed SHA-256: v0와 동일

## 검증

독립 verifier가 development 8개, candidate development 24개, 후보 3개, signal 23개, strategy outcome을 다시 계산했다. 결과는 `verified: true`였다.

실행 중 candidate 2의 Flask 구현 한 건이 결과 기록 직전에 중단되어 불완전 산출물을 `interrupted-artifacts/`로 보존하고 그 한 건만 재실행했다. 나머지 완료 산출물은 재사용했다.

## 해석

짧은 v0가 무조건 충분했던 것은 아니다. baseline 자체에서 invented requirements 13건과 compatibility regressions 8건이 검출됐다. 동시에 evidence boundary를 명시한 candidate 1은 전체 합계를 크게 개선했다. 이번 세대가 실패한 직접 원인은 mutation의 무효가 아니라, candidate 1의 개선이 모든 development 사례에서 비회귀적이지 않았기 때문이다.
