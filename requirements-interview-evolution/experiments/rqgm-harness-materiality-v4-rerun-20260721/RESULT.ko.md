# RQGM Co-evolution Epoch 3 재실행 결과

실험일: 2026-07-21

## 결론

8개 사례를 최대 병렬도(8 workers)로 처리한 재실행이 완료됐다. evaluator는 epoch 2로 승격됐고, generation 및 evaluator verifier도 모두 통과했다. 그러나 새 인터뷰 스킬 후보 3개는 엄격한 개발 게이트를 통과하지 못했으므로 skill과 배포 shadow는 유지했다. validation과 holdout은 열지 않았다.

## 실행 무결성

- Stage receipt 8개가 모두 생성됐다.
- replay는 첫 attempt가 Codex 백엔드 DNS/전송 연결 실패로 17/32건에서 중단됐다. 입력과 완료된 선행 단계는 보존했고, attempt 2에서 32/32건을 완료했다.
- Generation verifier: `verified: true`
- Evaluator verifier: `verified: true`
- 최종 epoch SHA-256: `2f0ccdfbc3577c395828ee84f48a15a3420e3821fcdf9075f693de15e18b38bc`

## Evaluator 결과

| Evaluator | 정답 | 오답 | 결과 |
|---|---:|---:|---|
| Incumbent epoch 1 | 26/28 | 2 | 교체 |
| Challenger | 28/28 | 0 | epoch 2 승격 |

Challenger 오류 집합은 incumbent 오류 집합의 strict subset이고 confidence-A 및 repository-family 회귀가 없었다. 선택 evaluator SHA-256은 다음과 같다.

`2a16852db35182a79957692c7fbb2ae207cad92931fdee2b2c4eb0af9a70525f`

## 2×2 Replay

| Skill | Evaluator | Ready | Invented req. | Impl. decisions | Approved blockers | Fidelity |
|---|---|---:|---:|---:|---:|---:|
| 배포 baseline | Incumbent | 8/8 | 29 | 1 | 0 | 0.8888 |
| 배포 baseline | Challenger | 8/8 | 33 | 1 | 0 | 0.8525 |
| Mutation parent | Incumbent | 8/8 | 1 | 5 | 1 | 0.9950 |
| Mutation parent | Challenger | 8/8 | 3 | 5 | 1 | 0.9863 |

Evaluator-induced flip은 9개였다. 선택된 challenger 아래에서는 baseline 대비 mutation parent의 fieldwise skill non-regression이 성립하지 않았다.

## 인터뷰 스킬 후보 결과

개발 게이트는 `paired-per-case-non-regression-with-strict-improvement`이다. 세 후보 모두 8/8 사례를 implementation-ready로 만들었지만, 사례별 비회귀 조건을 만족하지 못했다.

| 후보 | Ready | Invented req. | Impl. decisions | Material impl. decisions | Approved blockers | Compatibility regressions | 결과 |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 8/8 | 1 | 39 | 2 | 1 | 0 | 탈락 |
| 2 | 8/8 | 2 | 43 | 2 | 0 | 1 | 탈락 |
| 3 | 8/8 | 8 | 52 | 1 | 1 | 0 | 탈락 |

따라서 `development_selected_candidate`는 `null`이고, validation·holdout·skill promotion은 모두 미개방 또는 미실행 상태다.

## Promotion 결과

- Evaluator promotion: `true`
- Skill promotion: `false`
- 배포 skill SHA-256: `144c112df8b12cc465321348a4e5506cec34491ce5485d419104cd847744d144`
- `v-next-SKILL.md`: 생성되지 않음

## 해석

이번 재실행은 evaluator 개선을 재현하고 verifier 경로까지 완료했지만, 후보 스킬의 aggregate 개선이 사례별 비회귀 요구를 대체할 수 없음을 다시 확인했다. 다음 세대에서는 후보가 유발한 approved blocker·compatibility regression·material implementation decision의 원인을 signal 수준에서 분리해, 개발 게이트를 만족하는 변경만 후보에 반영해야 한다.
