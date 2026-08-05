# SWE-bench v0 통합 신호 단일 세대 진화 실험

`evolution/v0/SKILL.md`에서 새로 시작하며 기존 승인 corpus와 재사용 holdout만
공유한다. 실행 산출물은 이 디렉터리에 새로 생성한다.

development 8개에서 다음 원시 항목을 모두 mutation 신호로 사용한다.

- fresh 구현의 `decision.jsonl` 전체 행
- 독립 judge의 `invented_requirements` 전체 항목
- 독립 judge의 `compatibility_regressions` 전체 항목

모든 신호를 정확히 한 번 검토하고 `skill_gap`인 모든 신호를 포괄하는 일반적인
최소 mutation 하나만 허용한다. 신호가 0개일 때만 mutation을 생략한다. train 8개,
validation 두 arm 6개, holdout 4개는 각 단계의 최대 병렬도로 실행한다.

기존 holdout을 재사용하므로 결과는 신규 blind 일반화 증거가 아니다.
