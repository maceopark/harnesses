# Meta-strategy 구조 편집 진화 실험 결과

## 결론

candidate 내용뿐 아니라 candidate 생성 전략을 명시적으로 생성·평가하는 외부 개선 루프를 구현하고 한 세대 실행했다. 이전 세대의 development-only 전략 성적을 집계해서 meta-strategist에 제공했고, meta-strategist는 `REPLACE`, `DELETE`, `ADD` 전략을 하나씩 선택했다. 각 전략은 baseline 스킬의 정확히 한 위치만 기계적으로 편집했다.

세 전략 모두 일부 development 사례를 개선했지만 다른 사례를 회귀시켜 사례별 비회귀 gate에서 탈락했다. 선택된 candidate는 없으며 validation과 holdout은 열리지 않았다. 배포 스킬은 SHA-256 `963767bc6c2c8d7816dad3d9cfe1b7bd258790ac0c01a551f3638b57102851d6`을 유지했다.

완료 검증은 전략 편집, 3×8 development 실행, 전략 성적, 빈 eligible 목록, validation·holdout 미개봉을 독립 재계산했고 `verified: true`로 통과했다.

## 전략 개선 루프

이전 세대의 세 append 전략은 모두 실패했다. 새 meta-strategist에는 원시 사례명 대신 전략별 개선 사례 수, 회귀 사례 수, 변경 단어 수, 통과 여부만 제공했다. validation과 holdout 정보는 제공하지 않았다.

선택된 전략은 다음과 같다.

1. `materiality-threshold-replace-v1`
   - operation: `REPLACE`
   - item 1의 `each independent decision`을 `each unresolved material decision`으로 교체
2. `compatibility-evidence-delete-v1`
   - operation: `DELETE`
   - item 5의 `and acceptance evidence`만 삭제
3. `locality-boundary-add-v1`
   - operation: `ADD`
   - 국소 오류를 전체 입력 보존 요구로 일반화하지 않는 문장 추가

각 편집은 정확히 한 번 나타나는 anchor, operation 일치, anchor·replacement 각각 120단어 이하, 대상 외 baseline 보존을 기계적으로 검사했다.

## Development 결과

| arm | ready | invented | regression | decisions | blockers | redundant | fidelity |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 8/8 | 0 | 2 | 3 | 0 | 0 | 0.97375 |
| REPLACE | 6/8 | 2 | 3 | 2 | 0 | 1 | 0.89625 |
| DELETE | 8/8 | 4 | 4 | 4 | 0 | 2 | 0.93375 |
| ADD | 7/8 | 5 | 2 | 3 | 0 | 2 | 0.95250 |

## 전략별 판정

| 전략 | 개선 사례 | 회귀 사례 | 변경 단어 | eligible |
|---|---:|---:|---:|---|
| REPLACE | 1 | 4 | 19 | false |
| DELETE | 3 | 3 | 3 | false |
| ADD | 3 | 4 | 31 | false |

DELETE는 가장 작은 편집으로 세 사례를 개선했지만 세 사례에서 새 오류를 만들었다. ADD도 세 사례를 개선했지만 네 사례에서 회귀했다. 따라서 합산 개선 여부와 무관하게 모두 탈락했다.

## Gate 결과

- development signals: 5개
- candidate strategies: 3개
- candidate development runs: 24개
- eligible candidates: 없음
- validation opened: false
- holdout opened: false
- promotion eligible: false
- promoted: false

## 관찰된 다음 개선점

전략 외부 루프는 정상 작동했지만 단일 실행의 변동성이 크다. 직전 세대의 동일 baseline은 ready 7/8, invented 9, regression 4였고 이번 baseline은 ready 8/8, invented 0, regression 2였다. 따라서 현재 전략 성적에는 스킬 차이뿐 아니라 모델 실행 변동도 섞여 있다. 다음 외부 루프에서는 validation이나 holdout을 학습에 쓰지 않은 채 development arm을 반복 실행하거나 독립 judge 반복으로 전략 성적의 안정성을 먼저 측정할 필요가 있다.

## 실행 특이사항

candidate 2의 Xarray 첫 실행은 interviewer가 schema상 문자열이지만 내부 허용값이 아닌 question action을 반환해 실패했다. 미완성 디렉터리는 `pydata__xarray-4075.attempt-1-invalid-question`으로 보존했고 해당 한 건만 재실행해 완료했다.

## 산출물

- `completion-verification.json`: 완료 검증
- `decision.json`: development 탈락 및 미개봉 결정
- `runs/batch-mutation/mutation.json`: meta-strategy 포트폴리오와 구조 편집
- `runs/batch-mutation/strategy-outcomes.json`: 다음 세대용 development-only 전략 성적
- `runs/batch-mutation/development-selection.json`: candidate 선발 근거
- `inputs/prior-strategy-outcomes.json`: 이전 세대 전략 성적 입력
