# RQGM Co-evolution Epoch 3C 최종 결과

실험일: 2026-07-20

## 결론

계획한 네 가지 개선을 구현하고, 독립 감사에서 발견된 원자성·anchor 편향 문제까지 수정한 coordinator로 한 세대를 완료했다.

- Cue-neutral confidence-A validation에서 incumbent는 25/28, challenger는 28/28을 기록했다.
- Challenger 오류가 incumbent 오류의 strict subset이고 A/family 회귀가 없어 evaluator epoch 2로 승격됐다.
- 과거 baseline과 mutation-parent run은 새 evaluator로 인증 replay한 뒤 rejudged view로 물질화했다.
- 새 evaluator 아래에서 8개 mutation signal을 사용해 후보 3개를 실행했다.
- 세 후보 모두 aggregate 지표는 개선했지만 per-case non-regression을 통과하지 못해 skill은 승격하지 않았다.
- 두 verifier를 모두 통과한 뒤 별도 promotion-commit stage를 실행했으며, skill promotion은 없었다.

## 구현한 개선

### Failure-class feedback

이전 세대의 단순 개선/회귀 case 수 대신 다음 변화량을 전략 입력으로 사용한다.

- `invented_requirements`
- `implementation_decisions`
- `not_implementation_ready`
- `approved_finding__invention`
- `approved_finding__omission`
- `approved_finding__unverifiable-acceptance`
- 기타 closed failure class

Raw alias와 case별 delta는 strategist에게 노출하지 않고 class별 횟수만 전달한다.

### Cue-neutral hard anchor

정답을 암시하던 `Additional required clause`, `No additional contract clause`, `incidental` 같은 wrapper를 제거했다. 새 confidence-A boundary pair는 승인된 issue-time evidence 원문과 독립 reviewer가 implementation incidental로 분류한 원문을 직접 비교한다.

| Corpus | Sources | Anchors | Confidence-A | Boundary-A |
|---|---:|---:|---:|---:|
| Parent | 8 | 79 | 21 | 18 |
| Training | 5 | 51 | 14 | 11 |
| Validation | 3 | 28 | 7 | 7 |

이 변경으로 이전의 28/28 대 28/28 포화가 깨지고 25/28 대 28/28의 판별력이 생겼다.

### Evaluator 변경 시 lineage 보존

Evaluator가 바뀌면 과거 run manifest를 그대로 재사용하지 않는다. 2×2 replay의 선택 evaluator cell에서 새 judge를 가져오고 다음을 결합한 rejudged view를 만든다.

- 원래 run manifest digest
- replay manifest digest
- 새 evaluator SHA-256
- 변경되지 않은 transcript, contract, evidence, runtime audit, review, adjudication
- replay된 judge digest

이 view만 새 세대의 baseline 비교와 mutation signal에 사용했다.

### 원자적 coordinator

최종 stage 순서는 다음과 같다.

1. Anchor build/split
2. Evaluator evolution
3. 2×2 replay
4. Rejudged run views
5. Skill generation
6. Read-only generation verifier
7. Read-only evaluator verifier
8. Promotion commit

Promotion commit은 두 verifier receipt를 입력으로 봉인한 뒤에만 실행한다. 따라서 evaluator verifier가 실패한 상태에서 배포 shadow만 바뀌는 경로가 없다.

Input lock에는 config, sealed approval, recorded corpus manifest, strategy history, baseline/mutation skill, source run manifests, anchor sources, coordinator source digest가 포함된다. Verifier resume key도 decision뿐 아니라 generation/evaluator/anchor receipt digest에 결합된다.

## Evaluator 결과

| Evaluator | Validation 정답 | 오류 | 결과 |
|---|---:|---:|---|
| Incumbent epoch 1 | 25/28 | 3 | 교체 |
| Challenger | 28/28 | 0 | epoch 2로 승격 |

선택 evaluator SHA-256:

`0bbeeb9b83914b27a1e868f73dd77590a71597df6ebef76554f0af71a8209ebc`

## 2×2 replay

| Skill | Evaluator | Ready | Invented req. | Impl. decisions | Approved findings | Fidelity |
|---|---|---:|---:|---:|---:|---:|
| 배포 baseline | Incumbent | 7/8 | 25 | 1 | 0 | 0.9175 |
| 배포 baseline | Challenger | 8/8 | 18 | 1 | 0 | 0.9538 |
| Epoch2 Candidate 3 | Incumbent | 8/8 | 1 | 5 | 1 | 0.9975 |
| Epoch2 Candidate 3 | Challenger | 8/8 | 3 | 5 | 1 | 0.9925 |

Evaluator-induced flip은 6개였다. 두 evaluator 모두에서 Candidate 3의 fieldwise skill non-regression은 거짓이었다.

## 인터뷰 스킬 한 세대

새 evaluator로 rejudge한 배포 baseline은 ready 8/8, invented requirement 18, implementation decision 1이었다.

| 후보 | 변경 | Ready | Invented req. | Impl. decisions | Findings | 주요 회귀 | Eligible |
|---|---|---:|---:|---:|---:|---|---|
| 1 | edge/example clause를 요청 결과에 필요한 경우로 제한 | 7/8 | 6 | 2 | 1 | readiness, acceptance, decision | 아니오 |
| 2 | repository inspection 일부 삭제 | 8/8 | 2 | 4 | 0 | decision 4건 | 아니오 |
| 3 | reversible·observable-equivalent 선택을 non-blocker로 위임 | 8/8 | 2 | 2 | 0 | SymPy decision 1건 | 아니오 |

후보 3이 가장 가까웠다. 8개 사례 중 6개를 개선하고 한 사례는 동일했으며, SymPy 한 사례에서 implementation decision 하나만 증가했다. 하지만 gate는 평균 개선이 아니라 모든 사례의 비회귀를 요구하므로 탈락시켰다.

## 검증과 봉인

- 전체 테스트: `118 passed`
- Python compile: 통과
- Generation verifier: `verified: true`
- Evaluator verifier: `verified: true`
- Generation run manifests: 24개, evaluator identity 1개
- Eligible candidates: `[]`
- Validation/holdout: 미개방
- Skill promotion commit: `promoted: false`
- `v-next-SKILL.md`: 없음
- 배포 shadow SHA는 v0와 동일
- Stage receipts: 8개

최종 epoch SHA-256:

`08326c378c8c63a017a1c7af4bf828d191a61573a1343888674624ecf4c9490a`

## 해석

이번 세대에서는 두 진화 축이 처음으로 서로 다르게 움직였다.

- Evaluator는 더 어려운 cue-neutral validation에서 명확히 개선되어 승격됐다.
- Skill은 거의 통과한 후보를 찾았지만 한 사례의 decision 회귀 때문에 유지됐다.

따라서 다음 단계는 후보 3에 SymPy 전용 규칙을 추가하는 것이 아니라 decision 분류 경계를 교정하는 것이다. SymPy에서 기록된 선택은 dtype 문제가 아니라 `_sqrt_match`의 국소 guard와 `split_surds` 계층의 전역 변경 사이의 선택이었다. 모든 대안이 계약의 observable outcome과 compatibility boundary 안에 머무는 경우에는 이를 미해결 material decision이 아니라 bounded implementation choice로 취급해야 한다. 이 교정 뒤 후보 3을 다시 실행해 유일한 회귀가 사라지는지 확인한다. 반면 evaluator는 epoch 2를 다음 세대 incumbent로 사용할 근거가 확보됐다.
