# 다중 candidate·absolute-zero 진화 실험 결과

## 결론

동결된 development 8개에서 baseline을 새로 실행하고, 그 결과만으로 서로 다른 mutation 전략 3개와 candidate 3개를 생성했다. candidate 3개를 동일한 development 8개에 최대 병렬도로 실행했으나, 세 후보 모두 사례별 비회귀 조건을 위반했다. 따라서 선택된 candidate는 없으며 validation과 holdout은 열지 않고 세대를 종료했다. 배포 스킬은 baseline SHA-256 `963767bc6c2c8d7816dad3d9cfe1b7bd258790ac0c01a551f3638b57102851d6`을 유지했다.

완료 검증 결과는 `verified: true`다.

## Mutation 입력과 후보

- 입력 partition: development만 사용
- development 신호: 16개
  - implementation decision: 3개
  - invented requirement: 9개
  - compatibility regression: 4개
- 생성 candidate: 3개
- candidate별 development 실행: 8개, 총 24개
- candidate별 skill-gap 분류: 14개, 14개, 16개

세 전략은 각각 저장소 증거 우선 확인, owner 질문·승인된 default·위임 경계, observable behavior·compatibility boundary 확인을 강조했다.

## Development 결과

| arm | ready | invented | regression | decisions | blockers | redundant | fidelity |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 7/8 | 9 | 4 | 3 | 0 | 5 | 0.8925 |
| candidate 1 | 6/8 | 8 | 7 | 0 | 0 | 3 | 0.8825 |
| candidate 2 | 6/8 | 13 | 6 | 1 | 1 | 4 | 0.8500 |
| candidate 3 | 6/8 | 4 | 6 | 2 | 0 | 2 | 0.9175 |

candidate 3이 합산 invented requirement와 decision 수, fidelity에서는 가장 좋아 보이지만 다음과 같은 사례별 회귀가 있어 탈락했다.

- `astropy__astropy-7671`: compatibility regression 0 → 2
- `pallets__flask-5014`: redundant question 0 → 1
- `pydata__xarray-4075`: implementation decision 0 → 1
- `sphinx-doc__sphinx-9229`: compatibility regression 2 → 3, redundant question 0 → 1
- `sympy__sympy-17318`: implementation-ready 1 → 0, compatibility regression 0 → 1

candidate 1과 2도 Xarray와 Sphinx 사례 등에서 readiness 또는 계약 오류가 증가했다. 따라서 `eligible_candidates`는 빈 배열이다.

## Gate 결과

- development selected candidate: 없음
- validation opened: false
- holdout opened: false
- promotion eligible: false
- promoted: false
- v1 skill 생성: 없음

이번 결과는 새 규칙이 합산 점수 개선만으로 후보를 validation에 보내지 않고, 알려진 development 회귀를 실제로 차단했음을 보여준다. absolute-zero validation gate는 development를 통과한 후보가 없어서 이번 세대에는 실행되지 않았다.

## 실행 특이사항

최초 24개 candidate development 실행 중 candidate 3의 Xarray interviewer 한 건이 900초 제한을 초과했다. 미완성 실행은 `pydata__xarray-4075.attempt-1-timeout`으로 보존했고 해당 한 건만 재실행했다. 재실행은 정상 완료됐다.

## 검증 산출물

- `completion-verification.json`: `DevelopmentRejectionVerification.v1`, `verified: true`
- `decision.json`: development 탈락과 validation·holdout 미개봉 결정
- `runs/batch-mutation/mutation.json`: 세 mutation 전략과 전 신호 검토
- `runs/batch-mutation/development-selection.json`: baseline/candidate 지표와 빈 eligible 목록
