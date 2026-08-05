# SWE-bench v1 계약 오류 우선 다음 세대 실험

직전 통합 신호 실험의 candidate를 v1 baseline으로 사용한다. 실행 전에 validation
선택 우선순위와 파티션 회전을 다음과 같이 고정했다.

## 선택 우선순위

1. contamination과 leakage가 모두 0인 안전한 arm
2. `invented_requirements + compatibility_regressions`가 적은 arm
3. `implementation_ready`가 많은 arm
4. `implementation_decisions`가 적은 arm
5. approved blocker, owner recall, repository fidelity, redundant question 순

## 회전된 파티션

- 새 validation: `psf__requests-5414`, `django__django-15268`,
  `matplotlib__matplotlib-26466`
- development: 나머지 승인 비-holdout 8개
- holdout: 기존 4개 그대로 재사용

새 validation 3개는 직전 세대 development에서 mutation 신호를 만들지 않은 사례다.
그러나 이전 실행 이력이 있으므로 완전히 미노출된 validation은 아니다. holdout 역시
재사용 세트이므로 신규 blind 일반화 증거가 아니다.

각 단계는 development 8개, validation 두 arm 6개, holdout 4개의 최대 병렬도로
실행한다. development의 decision, invented requirement, compatibility regression은
전부 정확히 한 번 검토해 candidate를 최대 하나 만든다.
