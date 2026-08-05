# SWE-bench v0 decision 기반 진화 결과

실험은 완료됐고 독립 완료 검증을 통과했다. 단, strict holdout gate는 실패해
승격하지 않았다.

## 결과

- development 8개: fresh 구현 8개 완료, `decision.jsonl` 행 0개
- mutation: 입력 행이 없어 호출하지 않음, candidate는 v0와 동일
- validation 6개: fresh 구현 6개 완료, candidate arm에서 행 1개 생성
- validation 승자: baseline. candidate와 파일은 같지만 candidate 실행에 결정 1개가
  생겨 0개인 baseline이 우선됨
- holdout 4개: fresh 구현 4개 완료, 행 0개
- holdout 품질: implementation-ready 1/4, invented requirements 16,
  compatibility regressions 5, approved material blocker 1
- promotion: 불가, v0 유지

## 생성된 결정 전수 검토

성공 실행과 `failed-attempts`를 모두 검색했다. 생성된 행은 validation의 한 행뿐이고
`all-decision-review.json`에서 검토했다. 여러 signature가 하나의 입력에서 나올 때
기존 extension hook을 집계 결과에 한 번 호출할지 각 signature마다 호출할지는
extension side effect와 호환성을 바꾸는 실제 material decision이다. v0 계약이 이를
미리 결정하지 못했으므로 skill gap으로 판정했다.

이 행은 validation에서 발견됐으므로 이미 끝난 generation의 candidate를 소급 변경하지
않는다. 다음 generation의 development mutation 입력으로 보존한다.

## 해석

이번 결과는 “v0가 충분히 좋다”는 뜻이 아니다. development에서 자기보고 로그가 0개였지만
holdout 인터뷰 품질 지표는 크게 실패했다. 이 메커니즘은 구현자가 실제로 로그한 공백은
직접 포착하지만, 구현자가 공백을 인식하지 못하고 임의 선택하거나 계약 자체가 잘못된
경우까지 자동으로 검출하지는 않는다.

기존 holdout을 재사용했으므로 신규 blind-holdout 일반화 증거로 해석하지 않는다.
