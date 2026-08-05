# v0 단일 세대 진화 실험 결과

## 판정

한 세대 실행은 완료됐고 verifier를 통과했다. 개발 8개 사례에서 mutation
자격을 충족한 반복 승인 실패 패턴은 없었다. 따라서 Mutator를 호출하지
않았으며 candidate는 v0 baseline과 byte-identical하다.

검증에서는 독립 실행 변동으로 baseline arm과 candidate arm의 지표가
달랐다. 고정 사전식 선택 규칙은 baseline을 선택했다. 선택된 v0를 기존
holdout 4개에 실행한 결과 절대 승격 게이트를 통과하지 못해 v0를 유지했다.

## 실행 및 검증

- train: 8/8 완료, 단계 최대 동시성 8
- test: baseline 3개와 candidate 3개, 총 6/6 완료, 단계 최대 동시성 6
- holdout: 4/4 완료, 단계 최대 동시성 4
- 역할 실행 모델: `gpt-5.6-sol`
- contamination: 0
- leakage: 0
- verifier: `verified: true`
- baseline/candidate/deployed SHA-256:
  `bc064226bc01f9e896a3b0ce843861c1480593e08cc95c02c952091092960c9a`

## 검증 지표

| 지표 | baseline | candidate |
|---|---:|---:|
| implementation-ready | 2/3 | 2/3 |
| owner recall | 0.98 | 1.00 |
| repository fidelity | 0.8067 | 0.7867 |
| invented requirements | 4 | 8 |
| redundant questions | 0 | 3 |
| compatibility regressions | 4 | 3 |
| approved material blockers | 0 | 1 |

Holdout 결과는 implementation-ready 3/4, invented requirements 7,
compatibility regressions 4, approved material blockers 0이었다.

## 실행 기록

최초 test 병렬 실행에서 `pallets__flask-5014` candidate arm의 Evidence
Auditor가 모든 fact를 정확히 한 번 disposition하지 않아 fail-closed됐다.
불완전 실행은 `failed-attempts/test/` 아래에 보존하고 해당 run만
재실행했다. 나머지 완결 run은 digest 검증 후 재사용했다.

기존 holdout을 재사용하라는 실험 조건을 따랐으므로 이 결과는 신규 blind
holdout에서의 일반화 증거가 아니다. 동일한 고정 사례에 대한 v0 단일 세대
재실행 결과로 해석해야 한다.
