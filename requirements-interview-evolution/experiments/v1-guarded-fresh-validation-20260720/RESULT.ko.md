# SWE-bench 인터뷰 스킬 진화 완료 보고서

## 결과

고정된 SWE-bench Verified 15개 사례를 개발 8개, 검증 3개, 홀드아웃 4개로 실행했다. 개발 구현의 decision 행과 judge가 판정한 invented requirement 및 compatibility regression을 모두 batch mutation 입력으로 사용했다. 검증 파티션의 고정 사전식 규칙에 따른 선택 결과는 `candidate`였고, 선택된 스킬만 홀드아웃에 한 번 실행했다. 최종적으로 홀드아웃 절대 게이트를 통과하지 못해 배포본 v5를 유지했다.

이번 개발 실행에서 전수 검토한 mutation 신호는 14개였고, 실제 mutation 수행 여부는 `true`였다. 후보와 v5의 byte 동일 여부는 `false`다.

Readiness finding은 공개 요청, 저장소 사실, transcript와 contract에서 관찰 가능한 구현 차단 요인이다. Gold patch와 test patch에서 사후에만 발견한 내용은 hindsight diagnostic으로 분리했으며, 별도의 blind development 재현 없이는 readiness 점수나 mutation 근거로 사용하지 않았다.

## 정량 결과

- 승인 사례: 15개
- 저장소 family: 11개
- 개발 실행: 8개
- 검증 실행: 6개
- 홀드아웃 실행: 4개
- 홀드아웃 implementation-ready: 1/4
- contamination: 0
- leakage: 0
- 승인된 material blocker: 0

## 한계

- 생성자·리뷰어·인터뷰 역할이 모두 `gpt-5.6-sol`이므로 학습 데이터나 모델 계보에 따른 model contamination 가능성을 배제할 수 없다.
- 역할 격리는 별도 ephemeral 프로세스, 최소 allowlist payload와 gitignored cache를 이용한 논리적 격리다. 적대적 프로세스를 막는 OS 수준 read-deny 경계는 아니다.
- SWE-bench Verified dataset card에는 별도 license 선언이 없다. 저장소별 license 파일 digest는 기록했지만 법률 해석은 하지 않았고, 원문·patch·test·checkout은 재배포하지 않고 cache에만 보관했다.
- 표본은 15개와 최소 6개 repository family에 한정되므로 일반화 가능성을 넓게 주장하지 않는다.
- 홀드아웃 alias는 plain SHA-256 가명화일 뿐이며 알려진 500개 instance ID를 열거하는 공격에 대한 비밀성을 제공하지 않는다.
- arm64 호스트에서 `linux/amd64` 에뮬레이션으로 공식 Docker harness를 실행했다. native amd64 환경과 성능·타이밍 특성이 다를 수 있다.
