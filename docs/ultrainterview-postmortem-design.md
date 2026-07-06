# Ultrainterview Postmortem Design

작성일: 2026-07-05

이 문서는 `requirements-gap-discovery` → `ultrainterview-improvement-proposal` → `ultrainterview-research-synthesis` → `ultrainterview-hardening-review`에 이어지는 다섯 번째 개발 히스토리다. hardening review의 "남은 아이디어"로 미뤄뒀던 **spec postmortem 피드백 루프**를 별도 스킬 `ultrainterview-postmortem`으로 구현한 기록이다.

스킬 위치: `~/.agents/skills/ultrainterview-postmortem/` (`~/.claude/skills/`에 symlink, 기존 스킬들과 동일한 등록 방식).

## 왜 이것이 필요한가

ultrainterview의 모든 장치 — lens 라우팅, falsification checkpoint, pressure-before-settling, triangulation 강제, 상시 breadth sweep — 는 인터뷰 **중**의 발견률을 높인다. 하지만 어느 것도 발견률 자체를 측정하지 못한다. 인터뷰가 놓친 요구사항은 정의상 인터뷰 안에서는 보이지 않고, 구현이 끝난 뒤 spec과 실제 diff를 대조할 때만 드러난다. 구현 코드에 있는데 spec에 없었던 모든 실질적 행동은 **인터뷰를 탈출한 unknown unknown의 물증**이다.

postmortem은 이 물증을 수확해 두 가지로 바꾼다: (1) 이번 인터뷰의 측정된 발견률(calibration summary), (2) 다음 인터뷰가 상속하는 라우팅 규칙(lessons). 발견률을 **보정**하는 유일한 피드백 루프다.

## 왜 별도 스킬인가

ultrainterview 안의 모드가 아니라 독립 스킬로 분리한 이유 세 가지:

1. **다른 시점, 다른 트리거 문구 공간**: 인터뷰는 코딩 전, postmortem은 PR 머지 후 — 보통 다른 세션, 몇 주 뒤일 수도 있다. 스킬은 트리거 문구로 로드되는데 "spec postmortem", "what did the interview miss"는 인터뷰 트리거와 겹치지 않는다.
2. **다른 입출력**: 입력이 사용자 인터뷰가 아니라 `handoff.md` + 실제 diff이고, 출력이 spec이 아니라 리포트 + 교정 신호다.
3. **시리즈의 자체 원칙 준수**: "방법론 추가가 아니라 라우팅과 gate 개선" — 이미 큰 SKILL.md에 회고 모드를 넣으면 이 원칙을 어긴다. 대신 두 스킬은 같은 `.ultrainterview/<slug>/` 네임스페이스와 ledger 어휘를 공유한다.

## 핵심 설계

### 1. 양방향 divergence audit

handoff의 requirements ledger·acceptance criteria·decision boundaries·non-goals·deferred risks와 구현 diff를 **양방향**으로 대조한다: 각 diff hunk에 "어느 spec 요구사항을 위한 것인가?"를, 각 spec 요구사항에 "어디에 구현되고 어디서 검증되는가?"를 묻는다. 한 방향만 걸으면 절반의 divergence(탈출 또는 drift)만 보인다.

분류는 5종:

| Class | 의미 | 신호 |
| --- | --- | --- |
| `fulfilled` | spec에 있고 구현됨 | 인터뷰가 맞았다는 확인 |
| `escaped-requirement` | 구현됐지만 spec에 없음 | **탈출한 unknown unknown — 귀속 대상** |
| `scope-drift` | spec에 있지만 미구현·미유예 | handoff 과잉 약속 또는 조용한 탈락 |
| `divergent-implementation` | spec과 다르게 구현됨 | decision boundary 침범 또는 확정 결정 번복 |
| `deferred-outcome` | handoff에서 유예됨 | 리스크 실현 여부 기록 |

오분류 방지 규칙 세 가지가 분류의 품질을 결정한다:

- **실질적 행동만 escape로 계산**: error handling, edge case, data 규칙, migration, 보안 체크, 운영 hook. rename·포매팅·주석·순수 리팩토링은 아니다.
- **non-goal 확인 선행**: non-goal이 명시적으로 배제했던 행동이 구현됐다면 그것은 구현 중 결정된 scope 변경(`divergent-implementation`)이지 인터뷰 miss가 아니다.
- **transcript 확인 선행**: 주제를 물었고 답을 받았는데 잘못 기록됐거나 압축으로 소실됐다면, 실패는 enumeration이 아니라 answer handling이다 — 귀속이 달라진다.

### 2. Lens 귀속과 failure class

각 escape에 "어느 메커니즘이 잡았어야 했나 + 왜 못 잡았나"를 귀속한다. failure class 5종:

| Failure class | 진단 | 산출되는 lesson |
| --- | --- | --- |
| `trigger-too-narrow` | 해당 gap 부류를 소유한 lens가 트리거되지 않음 | 새 signal→lens 라우팅 규칙 |
| `enumeration-miss` | lens는 돌았지만 gap을 나열하지 못함 | 해당 lens 내부의 새 질문/체크 |
| `scoring-starved` | ledger에 있었지만 질문이 예산 내 순위에 못 듦 | 체계적으로 과소평가된 스코어 차원 기록 |
| `answer-unpressured` | 묻고 답받았지만 압박/triangulation 없이 확정, 답이 틀림 | 건너뛴 Answer Handling 규칙 |
| `known-deferred` | owner/date와 함께 유예됨 | miss 아님 — deferred outcome으로만 기록 |

이 분해가 이 스킬의 핵심 가치다. "뭘 놓쳤나"만 기록하면 회고는 반성문으로 끝난다. "인터뷰 파이프라인의 **어느 단계**가 놓쳤나"까지 분해해야 교정이 기계적이 된다 — trigger 문제는 lesson 한 줄로, scoring 문제는 anchor rubric 조정으로, answer handling 문제는 압박 규칙 준수로 각각 다른 처방이 나온다. 모든 귀속은 증거(diff hunk + ledger/transcript 행 또는 그 부재)를 동반한다.

### 3. Lessons store: 커밋되는 `docs/ultrainterview-lessons.md`

`.ultrainterview/`는 gitignore된 세션 상태라 lesson을 담을 수 없다. 세션 상태와 축적 지식은 수명이 다르다 — 인터뷰 상태는 slug 하나의 수명, lesson은 레포의 수명. 그래서 lessons는 커밋되는 `docs/ultrainterview-lessons.md`에 산다. grill-with-docs가 CONTEXT.md에 어휘를 축적하는 것과 같은 채널 설계이고, ultrainterview Orientation이 이미 glossary 파일을 읽는 hook이 있어 통합 지점이 저렴했다.

lesson 형식: `| Signal | Lens to trigger | Failure class | Evidence | Date |`

세 가지 제약이 lessons의 품질을 지킨다:

- **signal은 인터뷰 시점에 관측 가능해야 한다**: "change touches a scheduled/cron path", "request mentions export" — hindsight("we forgot X")는 금지. 그래야 다음 인터뷰가 기계적으로 매칭할 수 있다.
- **추가 전 dedupe**: 기존 행을 강화·일반화하는 것이 근사 중복 추가보다 우선.
- **lesson은 라우팅 규칙이지 방법론이 아니다**: 기존 lens를 더 일찍 트리거할 뿐, 새 인터뷰 장치를 추가하지 않는다.

### 4. 루프 폐쇄: ultrainterview 쪽 2줄

- **Orientation**: `docs/ultrainterview-lessons.md`를 glossary와 함께 읽고, lesson의 signal이 요청이나 대상 코드에 나타나면 해당 lens를 트리거된 것으로 취급, ledger에 `lesson-triggered` 기록.
- **Handoff**: 구현이 끝나면 postmortem 스킬로 spec과 diff를 대조할 수 있다고 1회 안내.

이로써 사이클이 닫힌다: interview → handoff → 구현 → postmortem → lessons → 다음 interview의 Orientation.

### 5. Output contract

`.ultrainterview/<slug>/postmortem.md` 리포트와 lessons 파일 갱신을 **같은 턴에** 수행한다. 리포트는 구현 증거, divergence table, 귀속된 escape 목록, deferred outcome, scope drift/divergent 목록(사용자 재결정 필요 여부 포함), 추가된 lesson 행, calibration summary(분류별·failure class별 카운트)를 포함한다.

두 가지 보호 규칙:

- handoff에 기록된 **사용자 결정을 번복한** divergent-implementation은 로그가 아니라 명시적 재확인 요청으로 격상한다.
- postmortem 안에서 ultrainterview 스킬·handoff·구현을 수정하지 않는다. 산출물은 리포트와 lessons 파일뿐이다. (스킬 자체의 교정은 사람이 lessons를 보고 결정한다 — 자기 수정 루프는 별도 결정 사안.)

## 리뷰에서 잡은 것

fresh-context 리뷰 에이전트가 두 스킬 간 계약 불일치를 검사해 4건을 보고했고, 판정 결과:

- **실제 결함 1건**: 템플릿의 owning-lens 어휘가 canonical lens 이름과 어긋남(`domain-state` vs `domain/state`)에 더해, lens가 아닌 것(`contextual-observation`, `framing`)을 lens로 나열. → canonical 6종 + `core-path`로 수정. `core-path` 귀속을 신설한 이유: lessons는 signal→lens 라우팅 규칙인데 항상 실행되는 core path가 놓친 것은 라우팅으로 고칠 수 없다. 이 비대칭을 명시하지 않으면 postmortem이 라우팅 불가능한 lesson을 양산해 Orientation 매칭을 오염시킨다. core-path escape는 정의상 `enumeration-miss`이며, repo-관측 가능한 signal이 더 무거운 lens를 라우팅할 수 있었을 때만 lesson이 된다.
- **의도된 설계 2건**: `known-deferred`가 Escaped Requirements 선택지와 calibration failure-class 표에 없음 — 유예 항목은 escape가 아니라 Deferred Outcomes 소속이므로 설계대로. 혼동 방지 노트만 추가.
- **오탐 1건**: "signal 제약이 skeleton에 없다" — skeleton 산문에 이미 존재.

## 의도적으로 하지 않은 것

- **결정론 스크립트 없음**: divergence 분류와 lens 귀속은 산술이 아니라 판단 작업이다. "결정론은 산술에만 있다"는 시리즈 원칙에 따라 스크립트를 만들지 않았다. calibration summary의 카운트는 표를 채우면 자명해서 헬퍼가 필요 없다.
- **스킬 자동 교정 없음**: postmortem이 ultrainterview SKILL.md를 직접 수정하는 자기 개선 루프는 배제했다. lessons가 라우팅 데이터로 흘러가고, 스킬 프롬프트 자체의 변경은 사람의 리뷰를 거친다.
- **lessons의 lens 트리거 강제 없음**: Orientation의 lesson 매칭은 프롬프트 규칙이다. signal 매칭은 자연어 판단이라 스크립트로 강제할 수 없고, 강제하려면 signal을 정형 패턴으로 제약해야 하는데 그러면 표현력이 죽는다.

## 남은 아이디어 (미반영)

- **lessons 통계 기반 스킬 개정 신호**: 같은 failure class가 N회 누적되면 (예: `scoring-starved` 반복 → anchor rubric 결함) 스킬 개정을 제안하는 메타 규칙. lessons가 충분히 쌓인 뒤에야 의미가 있다.
- **postmortem의 postmortem**: lesson이 실제로 다음 인터뷰에서 escape를 막았는지 추적하는 lesson 효능 측정. lessons 파일에 hit count를 기록하면 가능하지만 현재는 과설계.
- **CI 연동**: PR 머지 시 handoff 존재 여부를 확인해 postmortem 실행을 리마인드하는 자동화. 스킬 밖의 인프라 결정이라 별도 사안.
