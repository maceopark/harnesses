# SWE-bench v0 단일 세대 진화 실험

이 디렉터리는 `evolution/v0/SKILL.md`를 baseline으로 삼아 기존의 고정된
SWE-bench 개발 8개, 검증 3개, holdout 4개 사례를 재사용하는 단일 세대
실험이다. 이전 v5→v6 실행 산출물은 입력으로 사용하지 않는다.

## 실행 규칙

- train: 개발 사례 8개를 동시에 실행한다.
- mutation: 서로 다른 개발 사례 두 개 이상에서 독립 승인된 반복 실패만
  사용해 candidate를 최대 한 개 만든다.
- test: v0와 candidate의 검증 실행 6개를 동시에 수행한다.
- holdout: test 승자만 기존 holdout 4개에 동시에 실행한다.
- 단계 간 실행 순서는 train → mutation → test → holdout으로 고정한다.
- 기존 holdout을 재사용하므로 결과를 신규 blind-holdout 일반화 증거로
  해석하지 않는다.

candidate와 mutation 증거는 `runs/batch-mutation/`에 보존한다. 입력 corpus,
sealed 입력, content-addressed cache, repository checkout과 모든 실행 출력은
이 디렉터리 아래에서 기존 실험과 분리한다.
