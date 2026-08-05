# RQGM 하니스 Epoch 2 결과

실험일: 2026-07-20

## 결론

이번 세대에서는 evaluator와 인터뷰 스킬 모두 승격하지 않았다. 이는 실행 실패가 아니라 강화된 보수적 gate가 의도대로 작동한 결과다.

- Evaluator challenger는 family-disjoint validation anchor 25개를 모두 맞혔지만 incumbent도 25개를 모두 맞혔다. strict-subset 개선이 아니므로 incumbent epoch 1을 유지했다.
- 이전 세대 Candidate 3을 mutation lineage parent로 삼아 세 후보를 만들었다. 세 후보 모두 aggregate invented requirement 수를 줄였지만, 8개 개발 사례의 paired per-case non-regression을 만족하지 못했다.
- 따라서 validation과 holdout은 열지 않았고 v1 및 배포본 승격도 하지 않았다.
- 독립 verifier는 개발 단계 탈락, evaluator identity 단일성, split binding, run/corpus/artifact digest를 모두 재검증했다.

## 이번에 강화한 하니스

1. Evaluator identity를 rubric UTF-8 bytes의 SHA-256과 algorithm version으로 인증한다.
2. Anchor를 repository-family 경계에서 train/validation으로 분리하고 split manifest가 두 corpus digest를 직접 봉인한다.
3. Evaluator 승격은 challenger 오류 집합의 strict subset, confidence-A 무회귀, family별 무회귀를 동시에 요구한다.
4. 동일한 기록 judge payload에 incumbent/challenger를 적용하는 2×2 replay를 추가했다.
5. Replay는 public case와 sealed source를 judge payload에서 재구성하여 원래 run manifest digest와 대조한다. 완료 replay 재사용 시에도 raw artifact와 원본 judge call을 다시 인증한다.
6. Replay의 각 skill arm은 정확히 8개 개발 alias와 단일 skill identity를 요구한다.
7. 외부 baseline 및 mutation lineage run은 evaluator, case, sealed source, artifact digest, alias 집합을 현재 recorded corpus에 결합한다.
8. 실패한 비배포 후보를 다음 세대 mutation parent로 쓰되, 새 후보의 승격 비교 기준은 계속 배포 baseline으로 유지한다.

## Evaluator 실험

Anchor split:

- Training: 5 sources, 4 repository families, 36 confidence-B anchors
- Validation: 3 sources, 2 repository families, 25 anchors(3 confidence-A, 22 confidence-B)
- Training families: `astropy/astropy`, `pydata/xarray`, `scikit-learn/scikit-learn`, `sympy/sympy`
- Validation families: `pallets/flask`, `sphinx-doc/sphinx`
- Split seed: `rqgm-harness-epoch2-20260720-5`

결과:

| Evaluator | Validation 정답 | 오류 | 승격 |
|---|---:|---:|---|
| Incumbent epoch 1 | 25/25 | 0 | 유지 |
| Challenger | 25/25 | 0 | 아니오 |

Validation이 포화되어 challenger의 개선을 구별하지 못했다. 다음 evaluator 세대의 우선 과제는 더 어려운 경계 사례, 특히 material outcome과 implementation incidental이 가깝게 맞닿는 confidence-A anchor를 늘리는 것이다.

## 동일 raw payload 2×2 replay

이 replay는 스킬별로 동일한 기록 payload를 두 evaluator에 적용한다. 서로 다른 스킬 arm 사이에는 transcript 자체가 다르므로 raw control은 각 arm 내부에만 성립한다.

| Skill | Evaluator | Ready | Invented req. | Impl. decisions | Fidelity |
|---|---|---:|---:|---:|---:|
| 배포 baseline v0 | Incumbent | 6/8 | 26 | 1 | 0.8600 |
| 배포 baseline v0 | Challenger | 8/8 | 23 | 1 | 0.9263 |
| 이전 Candidate 3 | Incumbent | 8/8 | 4 | 4 | 0.9700 |
| 이전 Candidate 3 | Challenger | 8/8 | 1 | 4 | 0.9925 |

Evaluator 변경만으로 5개 case outcome이 바뀌었다. 두 evaluator 모두에서 Candidate 3의 aggregate 품질은 높았지만 fieldwise per-case non-regression은 거짓이었다. 즉 evaluator 선택과 무관하게 “평균 개선을 이유로 일부 사례 회귀를 덮어서는 안 된다”는 결론은 유지된다.

## 인터뷰 스킬 한 세대

Mutation parent는 이전 세대 Candidate 3이고 승격 baseline은 배포 v0이다.

| 후보 | 변경 | Ready | Invented req. | Impl. decisions | Blockers | 사례 개선/회귀 | Eligible |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | material threshold를 observable outcome/authorized scope로 교체 | 8/8 | 8 | 3 | 1 | 4/4 | 아니오 |
| 2 | unconditional repository inspection 삭제 | 8/8 | 4 | 7 | 0 | 3/5 | 아니오 |
| 3 | inferred edge case/exhaustive example 승격 금지 문장 추가 | 8/8 | 1 | 5 | 1 | 4/4 | 아니오 |

후보 3은 invented requirement를 20에서 1로 가장 크게 줄였지만 4개 사례에서 다른 ordered badness field가 회귀했다. 후보 2 역시 aggregate 수치는 좋아 보이지만 implementation decision이 1에서 7로 증가했다. 따라서 세 후보 모두 탈락시킨 것이 맞다.

## 검증 증거

- 테스트: `111 passed`
- Python bytecode compile: 통과
- Development rejection verifier: `verified: true`, eligible candidates `[]`, validation/holdout 미개방
- Evaluator epoch verifier: `verified: true`, generation 내 evaluator identity 1개, run manifest 24개
- 2×2 replay 재검증: 기존 manifest와 byte-for-byte 동일
- 배포 SHA-256 유지: `144c112df8b12cc465321348a4e5506cec34491ce5485d419104cd847744d144`

## 다음 순서

1. Candidate 3의 4개 회귀 사례를 failure class별로 분해해 mutation signal을 더 국소화한다.
2. “invented requirement 감소”와 “implementation decision 증가” 사이의 상충을 직접 겨냥한 후보를 만든다.
3. 포화된 evaluator validation set에 어려운 confidence-A anchor를 추가한다.
4. 한 세대 coordinator로 anchor build/split, evaluator evolution, 2×2 replay, skill generation, 두 verifier를 하나의 원자적 epoch manifest에 묶는다.

현재 결과로는 배포 스킬을 바꿀 근거가 없다. 다음 세대는 후보 3 전체를 그대로 누적하기보다, 회귀가 없었던 clause 효과만 분리하는 방향이 적절하다.
