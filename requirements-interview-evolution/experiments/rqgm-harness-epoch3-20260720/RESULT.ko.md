# RQGM Co-evolution Epoch 3 결과

> 이 실행은 coordinator 초기 검증용으로 보존됐다. 독립 감사에서 발견된 성공 경로 원자성 및 anchor lexical-cue 문제를 수정한 최종 실험은 `../rqgm-harness-epoch3c-20260720/RESULT.ko.md`를 기준으로 한다.

실험일: 2026-07-20

## 결론

계획한 네 가지 개선을 구현하고 새 coordinator로 한 세대를 끝까지 실행했다. 두 독립 verifier는 통과했고 최종 epoch manifest가 원자적으로 커밋됐다. Evaluator와 인터뷰 스킬은 모두 승격하지 않았다.

- Epoch2 회귀를 failure class별로 재구성해 다음 mutation에 전달했다.
- Confidence-A boundary anchor를 18개 추가했다.
- Anchor, evaluator, replay, generation, 두 verifier를 하나의 digest-sealed epoch로 묶었다.
- 세 후보 모두 invented requirement를 크게 줄였지만 사례별 implementation decision 또는 승인된 finding이 증가해 개발 gate에서 탈락했다.
- Validation과 holdout은 열지 않았으며 실제 배포본과 epoch-local 배포 shadow는 v0 SHA를 유지했다.

## 1. 회귀 분석과 mutation signal

Epoch2 Candidate 3의 회귀를 다시 계산한 결과는 다음과 같았다.

- 개선: invented requirement 감소가 8개 case-field에서 관찰됨
- 회귀: implementation decision 증가 4건
- 회귀: 승인된 `invention` finding 증가 1건

기존 strategy history는 개선/회귀 case 수만 전달했다. 새 v2 history는 다음 class별 횟수를 추가하되 raw alias와 case별 delta는 strategist에게 전달하지 않는다.

- `invented_requirements`
- `implementation_decisions`
- `approved_finding__invention`
- `approved_finding__omission`
- `approved_finding__unverifiable-acceptance`
- 그 밖의 closed failure class

Mutator prompt에도 “aggregate 오류 하나를 줄이는 대신 decision, blocker, readiness 오류로 이동시키지 말 것”과 “unsupported inferred requirement를 억제하더라도 unresolved material choice를 반드시 해결할 것”을 명시했다.

## 2. 어려운 confidence-A anchor

기존 8개 개발 source에는 material decision이 1개뿐이어서 owner-answer omission anchor만으로는 validation 난도가 충분히 늘지 않았다. 그래서 독립 reviewer가 implementation incidental로 승인한 항목을 다음 쌍으로 만드는 boundary template을 추가했다.

- 선호: 승인된 issue-time evidence에서 추가 계약 조항이 나오지 않음
- 기각: incidental을 추가 필수 조항으로 승격

Anchor corpus 결과:

| Corpus | Sources | Anchors | Confidence-A | Boundary-A |
|---|---:|---:|---:|---:|
| Parent | 8 | 79 | 21 | 18 |
| Training | 5 | 51 | 14 | 11 |
| Validation | 3 | 28 | 7 | 7 |

Validation family는 `astropy/astropy`, `scikit-learn/scikit-learn`이며 training family와 겹치지 않는다.

Evaluator 결과:

| Evaluator | Validation | 오류 | 승격 |
|---|---:|---:|---|
| Incumbent epoch 1 | 28/28 | 0 | 유지 |
| Challenger | 28/28 | 0 | 아니오 |

기존보다 restraint 경계가 강한 시험이 됐지만 두 evaluator가 다시 만점을 받아 차이는 드러나지 않았다. 엄격한 subset gate에 따라 incumbent를 유지했다.

## 3. 2×2 replay

Epoch1 배포 baseline과 Epoch2 Candidate 3의 동일 기록 payload를 incumbent/challenger로 재평가했다.

| Skill | Evaluator | Ready | Invented req. | Impl. decisions | Approved findings | Fidelity |
|---|---|---:|---:|---:|---:|---:|
| 배포 baseline | Incumbent | 7/8 | 21 | 1 | 0 | 0.9063 |
| 배포 baseline | Challenger | 7/8 | 26 | 1 | 0 | 0.9200 |
| Epoch2 Candidate 3 | Incumbent | 8/8 | 1 | 5 | 1 | 0.9938 |
| Epoch2 Candidate 3 | Challenger | 8/8 | 1 | 5 | 1 | 0.9900 |

Evaluator-induced flip은 6개였고 두 evaluator 모두에서 skill non-regression은 거짓이었다. 즉 evaluator가 달라져도 Candidate 3의 “과잉 요구 감소와 구현 결정 증가” 상충은 남았다.

## 4. 새 인터뷰 스킬 세대

Mutation parent는 Epoch2 Candidate 3이고 승격 baseline은 배포 v0이다.

| 후보 | 변경 | Ready | Invented req. | Impl. decisions | Approved findings | 사례 개선/회귀 | Eligible |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | inference guard를 deliverable·문서·완전 열거에만 좁힘 | 8/8 | 0 | 3 | 2 | 4/4 | 아니오 |
| 2 | `runtime-required` 수식어 삭제 | 8/8 | 3 | 4 | 1 | 4/4 | 아니오 |
| 3 | outcome-neutral choice 분류 문장 추가 | 8/8 | 3 | 4 | 2 | 3/4 | 아니오 |

후보 1은 invented requirement를 `20 → 0`으로 줄이고 이전 Candidate 3의 일부 implementation-decision 회귀도 제거했다. 그러나 두 사례에서 implementation decision이 남고, `omission`과 `unverifiable-acceptance` finding이 각각 하나씩 새로 승인됐다. 평균은 좋아졌지만 per-case non-regression은 아니므로 탈락이 맞다.

이번 세대에서 얻은 가장 중요한 새 정보는 tradeoff가 단순히 “불필요한 요구를 줄이면 decision이 늘어난다”가 아니라 다음 세 갈래라는 점이다.

1. 과잉 요구를 억제하면서 필수 결과를 빠뜨리는 `omission`
2. 충분한 검증 근거 없이 acceptance를 약속하는 `unverifiable-acceptance`
3. 실제로 결과를 바꾸는 선택을 구현자에게 넘기는 `implementation_decisions`

## 5. Coordinator와 원자적 봉인

새 `run-coevolution-epoch`는 다음 단계를 한 입력 lock에 묶었다.

1. Hard anchor build/split
2. Evaluator evolution
3. 동일 raw payload 2×2 replay
4. Tradeoff-aware skill generation
5. Generation verifier
6. Evaluator verifier

각 단계는 `stages/<stage>/attempt-NNN/receipt.json`으로 모든 output digest를 봉인한다. 완료 receipt가 유효하면 재실행 시 재사용하며, 미완료 또는 변조 attempt는 보존한 채 다음 attempt를 만든다.

첫 evaluator attempt에서 기존 함수의 output-directory 생성 계약과 충돌하는 버그가 발견됐다. `attempt-001`을 삭제하지 않고 보존했으며 수정 후 `attempt-002`로 재개했다. 이후 마지막 manifest map의 키 충돌도 감사에서 발견해 최초 manifest를 `epoch-manifest.attempt-001.json`으로 보존하고 올바른 6단계 receipt map을 가진 최종 manifest를 다시 커밋했다.

최종 봉인:

- Epoch SHA-256: `7295383a16b22d5109d946ebe2b41f21debd6275efc9b0db67835ada29ff3202`
- Input lock: `c050d6538911aaf05b6369612e309f8600ac2e387905f8e579e11cf2d4dbee48`
- Selected evaluator: `092d710631296b3eafbae335cbc557f498ae9c8664fe16bc31b5e66112958c40`
- Deployed shadow: `144c112df8b12cc465321348a4e5506cec34491ce5485d419104cd847744d144`
- Generation verifier: `verified: true`
- Evaluator verifier: `verified: true`

## 검증

- 전체 테스트: `116 passed`
- Python compile: 통과
- Generation run manifests: 24개, evaluator identity 1개
- Candidate eligible set: `[]`
- Validation/holdout: 미개방
- `v-next-SKILL.md`: 생성되지 않음
- 실제 배포 스킬: 변경하지 않음

## 다음 세대에 남은 과제

후보 1이 가장 가까웠다. 다음 mutation은 이 후보 전체를 다시 넓히기보다 새로 드러난 두 finding을 직접 겨냥해야 한다.

1. “무단 deliverable은 금지” 규칙 뒤에, evidence가 요구하는 observable result는 생략하지 않는 대칭 규칙을 둔다.
2. Acceptance clause는 repository evidence 또는 명시적 owner answer로 검증 가능한 경우에만 넣도록 한다.
3. 결과·호환성·안전·데이터·reversibility가 실제로 달라지는 선택만 질문하고, 그렇지 않은 내부 선택은 계약 밖으로 둔다.

현재도 배포를 바꿀 근거는 없다. 다만 Epoch2의 모호한 4개 회귀가 Epoch3에서는 `implementation decision 2 + omission 1 + unverifiable acceptance 1`로 더 정확히 분해됐고, 다음 후보가 겨냥해야 할 범위가 좁아졌다.
