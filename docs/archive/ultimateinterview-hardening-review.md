# Ultrainterview Hardening Review

작성일: 2026-07-05

이 문서는 `docs/requirements-gap-discovery.md` → `docs/ultimateinterview-improvement-proposal.md` → `docs/ultimateinterview-research-synthesis.md`에 이어지는 네 번째 개발 히스토리다. 스킬의 선언된 목적(unknown unknowns 발견)에 비추어 세 로컬 레퍼런스 구현 — Ouroboros interview(hardening RFC 포함), oh-my-codex deep-interview(ambiguity 모델·QA 검증 포함), grill 계열(grilling/grill-me/grill-with-docs) — 과 비교 리뷰를 수행했고, 발견된 개선점 전부를 같은 날 스킬에 반영했다.

## 리뷰 방법

- `ultimateinterview` 본체(SKILL.md, scripts, references)와 기존 이론 문서 3편을 직접 정독.
- 병렬 분석 에이전트 3개로 레퍼런스 시스템의 메커니즘 전수 조사:
  - Ouroboros: SKILL.md, socratic-interviewer agent, interview-hardening / inverted-interview / context-first / milestone-lateral RFC, convergence contract, auto driver
  - deep-interview: SKILL.md, ambiguity 모델(TS 구현), autopilot gate, QA 검증 문서, autoresearch UX 리뷰
  - grill 계열: 세 변형의 질문 전략, 정지 조건, domain-modeling 연계
- Ouroboros RFC는 예상이 아니라 **프로덕션에서 관측된** 실패(답변 절단 → confirmation loop, artifact-class drift, plateau oscillation)를 기록하고 있어 가장 신뢰도 높은 입력으로 취급했다.

## 핵심 발견

### 1. 구조적 편향: 열거(enumeration) 9 : 반증(falsification) 1

세 레퍼런스는 서로 다른 방향에서 같은 발견 인식론으로 수렴한다: grill의 recommended answer, Ouroboros의 inverted interview, deep-interview의 evidence-backed confirmation은 모두 같은 수다 — **구체적이고 반증 가능한 것을 단언한 뒤 수정(충돌)을 수확하는 것**. unknown unknowns는 더 좋은 질문이 아니라, 제시한 모델이 코드·문서·사용자와 충돌할 때 드러난다.

기존 ultimateinterview는 lens 카탈로그(열거 장치)로는 최강이었지만 메인 루프가 질문 중심이었다:

- divergence가 단발성: lens 1회 실행 후 converge는 알려진 gap 목록만 줄임. re-diverge 트리거와 saturation 기준(연속 sweep에서 새 gap 없음) 부재.
- 문제 프레이밍 자체에 대한 도전 부재: 모든 lens가 현재 프레이밍을 전제로 동작. "잘못된 문제" 부류의 unknown unknown에 대응하는 수가 없음.
- 순수 exploitation 질문 정책: 스코어 공식에 exploration 항이 없어 미방문 차원을 찔러보는 질문에 보상이 없음.

### 2. 레퍼런스에는 있고 ultimateinterview에 없던 메커니즘

| 출처 | 메커니즘 | 방어하는 실패 모드 |
| --- | --- | --- |
| Ouroboros | Answer Refine gate | 풍부한 답변이 헤드라인 결정으로 압축 → label-confirmation loop (관측된 실패) |
| Ouroboros | Breadth-keeper | 흥미로운 한 트랙으로의 터널 시야, 부차 트랙 무단 탈락 |
| Ouroboros | Intent guard | 보수적 추천 옵션이 확정된 artifact class를 조용히 좁힘 (관측된 실패) |
| Ouroboros | Stagnation → lateral 에스컬레이션 | ambiguity plateau에서 무한 질문 반복 |
| Ouroboros | Inverted / context-first mode | 무거운 사전 작업 보유 사용자에게 열린 질문 → context 손실, 얕은 수렴, 피로 |
| Ouroboros | 질문별 contrarian advisory fanout | 프레이밍 오류가 handoff 직전까지 도전받지 않음 |
| deep-interview | Pressure ladder + stay-deep rule | 후속 검증 없는 답변이 score 0으로 확정되는 속 빈 수렴 |
| deep-interview | Challenge modes (Contrarian/Terminologist/Simplifier/Ontologist) + 정체 트리거 | 증상-해결, 용어 충돌, scope 팽창 |
| deep-interview | 라운드 캡 + residual-risk 출구 | 무한 심문, 사용자 피로 예산 부재 |
| deep-interview | doc/code 불일치 시 양쪽 명시 규칙 | 증거 충돌의 조용한 해소 |
| grill-with-docs | CONTEXT.md/ADR 어휘 축적 | 인터뷰 간 glossary 미상속, 확정 트레이드오프 재론 |

### 3. 지표 설계 결함

- **분모 불안정성**: `ambiguity_percent = 100 * sum(w×s) / sum(w×3)`의 분모가 settled 항목을 포함해서, score-1/weight-5 gap 하나가 단독이면 33%(차단), settled 20개와 함께면 ~3.7%(통과). 동일 잔여 위험에 정반대 판정이 나오고, 끝내고 싶은 모델이 settled 사실을 더 기록할수록 보상받는 잘못된 인센티브.
- **5% 임계값의 잉여성**: score-2 blocker 규칙이 이미 안전 역할을 다 하므로 임계값은 장부 정리만 추적.
- **자기 채점 산술**: question_score의 결정론은 곱셈에 있지 추정에 있지 않음. anchor rubric 부재, 곱셈형이라 잘못된 0 하나가 좋은 질문을 소거.

### 4. 이론 → 스킬 퇴행

`requirements-gap-discovery.md`의 창립 명제("서로 다른 증거 형태를 충돌시켜 빈칸을 드러낸다")가 스킬에서 탈락해 있었다: `Triangulated`/`Contested` status가 template에만 남고 converge 규칙에서 사용되지 않았고, from-user 주장을 from-code와 교차 확인하라는 의무가 없었다. viewpoint matrix는 개발자 1인의 역할극 행이 검사된 코드와 동일한 증거 지위로 ledger에 들어가는 provenance 사각지대가 있었다.

### 5. 운영 리스크

- ledger가 대화 텍스트로만 존재 → context compaction 경계를 넘으면 조용한 상태 손실, 결정론 스크립트가 손상된 상태 위에서 계산.
- handoff에 Q&A 기록 부재 → "증거로 확정"과 "도전받지 않은 문장 하나로 확정"을 다운스트림에서 구별 불가.

## 사용자 결정 (2026-07-05)

1. **판정 gate**: blocker 기반 채택. `handoff_ready` = active score 2/3 gap 없음. 퍼센트는 진행 표시로 강등, 절대 잔여치(`residual = sum(w×s)`) 병기. 5% 임계값과 `--threshold` 옵션 제거.
2. **상태 폴더**: `.ultimateinterview/<slug>/` 슬러그별 하위폴더 + `.gitignore` 자동 추가. 파일: `ledger.json`(source of truth), `questions.json`, `transcript.md`(append-only Q&A).
3. **handoff 위치**: `docs/`가 아닌 `.ultimateinterview/<slug>/handoff.md`. durable 커밋 산출물을 원하면 `docs/<slug>-handoff.md` 복사를 handoff 시점에 1회 제안.

## 반영된 변경

### scripts/ambiguity_ledger.py (+ test_deterministic_helpers.py)

- blocker 기반 `handoff_ready`, `numerator` → `residual` 개명, threshold blocker 제거.
- markdown 출력에 "informational only; never gate handoff on this" 명시.
- 희석 무관성 테스트 추가(`test_readiness_ignores_percent_dilution`): 단독 score-1/weight-5 gap은 퍼센트 33%여도 ready.

### SKILL.md (전면 개정, lens 카탈로그는 보존)

- `Session State` 신설: `.ultimateinterview/<slug>/` 영속화, gitignore 자동화, context 요약 후 파일 재로드 의무("대화 기억의 ledger는 신뢰하지 않는다").
- `Challenge The Framing` 신설: 첫 질문 전 증상 vs 근본원인 / do-nothing / 더 단순한 대안 / artifact class 확인. 결과를 ledger에 기록.
- `Answer Handling` 신설: pressure-before-settling(답변은 압박 후속 1회를 견디거나 제2 증거 채널로 교차 확인되기 전까지 score 2 아래로 못 내림), stay-deep, 뉘앙스 분해(decision/reasoning/constraints/non-goals 분리), 증거 충돌 시 양쪽 제시 + `Contested`, weight-5 triangulation 의무, scope-reduction 옵션 recommended 금지(intent guard). ledger status 6종 채택.
- `Falsification Checkpoints` 신설: 번호 매긴 반증 가능 진술 제시, 사용자는 틀린 줄만 수정. 트리거: 무거운 사전 작업의 context-first 진입, 저점수 질문 다수 대기 시, 정체 에스컬레이션 시, handoff 전 필수 1회. "확정으로 믿었던 진술에 대한 수정 = unknown unknown 표면화 → 해당 lens 재실행".
- Diverge에 re-diverge 트리거와 saturation(`divergence: dry`) 명시 — divergence는 단발성이 아님.
- Converge에 breadth sweep(인간 결정 4답변마다), 정체 에스컬레이션(2라운드 residual 무변동 → contrarian probe/checkpoint), anchor rubric(차원별 1/3/5 앵커)과 "0 대신 0.5" 하한 지침, "스크립트는 산술의 결정론만 보장" 정직화.
- 질문 예산: minimal 3 / focused 12 / full 20. 초과 시 명시적 defer(residual-risk handoff) 또는 연장 — 조용한 초과 금지.
- Fresh-Context Gate 확장: full depth에서 breadth sweep마다 슬림 contrarian 리뷰(반증 진술 + ledger + 경로만 제공, "가장 틀렸을 법한 진술과 그것을 드러낼 질문 하나"만 요청). 전체 게이트는 handoff 시 유지.
- Orientation에 repo glossary(CONTEXT.md 등) 읽기, handoff에 glossary 갱신 제안 — 인터뷰 간 어휘 상속.
- viewpoint matrix에 `simulated`/`confirmed` provenance — simulated 행은 assumption이며 단독으로 critical 요구사항을 triangulate할 수 없음.
- Gates 갱신: 5% 게이트 제거, blocker 기반 + triangulation + Contested 해소 + checkpoint 실행 게이트 추가.
- Output Contract/Handoff에 `Framing challenge outcome`, `Q&A record`, `Contested log` 추가.

### references/output-template.md, references/comparison.md

- template: residual/blocker 대시보드, Framing Challenge / Q&A Record / Contested Log / Glossary Updates 섹션, viewpoint provenance 열.
- comparison: falsification·triangulation·영속 ledger·blocker 판정·intent guard·예산을 반영해 비교 주장 갱신.

## 의도적으로 하지 않은 것

- **question_score.py 공식 무변경**: SKILL.md가 "exact converge formula"로 계약 선언하고 있어, 0-곱셈 문제는 프롬프트 수준의 "0 대신 0.5" 지침으로 해결. 공식 자체는 계약 안정성을 위해 유지.
- **triangulation의 스크립트 강제 없음**: ledger JSON에 evidence channel 필드가 없어 스크립트는 채널을 모름. "결정론은 산술에만 있다" 원칙에 따라 프롬프트 게이트로 유지.
- **contrarian probe / breadth sweep의 상시 실행 없음**: 이전 문서들의 핵심 명제("방법론 추가가 아니라 라우팅과 gate 개선")는 이번 추가 장치에도 적용된다. minimal depth는 여전히 가볍다.

## 남은 아이디어 (미반영)

- **spec postmortem 피드백 루프**: 구현 완료 후 spec과 실제 PR을 대조해 놓친 요구사항을 새 lens 트리거로 축적하는 회고 모드. unknown-unknown 발견률 자체를 보정하는 유일한 방법이지만, 이번 범위에서는 제외.
- **ledger JSON에 evidence-channel 필드 추가**: 추가하면 triangulation 게이트를 스크립트로 강제할 수 있다. 스키마 변경이라 별도 결정 필요.
- **질문 스코어에 exploration 항**: 미방문 차원 탐침에 보상을 주는 항. 현재는 breadth sweep이 그 역할을 구조적으로 대신한다.

## 후속 반영 (2026-07-05, 같은 날 2차)

사용자 결정으로 위 목록 중 세 항목이 추가 반영되어, 이 문서의 "의도적으로 하지 않은 것" 중 2·3번과 "남은 아이디어" 중 2번은 더 이상 현재 상태를 서술하지 않는다:

- **ledger 스키마에 `evidence_channels` 필드 추가**: 엔트리별 evidence channel 목록(`from-code` 등 6종, 축약형 정규화, 콤마 문자열 허용). `assumption`은 channel로 카운트되지 않고, 어휘 밖의 값은 검증 에러로 거부된다(fail-closed) — 오타 `assumptions`나 임의 채널명이 두 번째 증거로 조용히 카운트되는 것을 적대적 리뷰에서 발견해 막았다.
- **triangulation의 스크립트 강제**: `ambiguity_ledger.py`가 active·weight-5·score-0 엔트리에 distinct channel 2개 미만이고 `Accepted` status가 아니면 handoff blocker로 판정한다. status 라벨(`Triangulated` 자기 선언)은 신뢰하지 않고 기록된 채널만 계산한다 — 자기 채점 방지가 강제의 목적이므로.
- **contrarian probe / breadth sweep 상시 실행**: breadth sweep은 4답변 cadence에 더해 모든 depth에서 인터뷰당 최소 1회(cadence 미발화 시 pre-handoff checkpoint 직전), slim contrarian review는 full 한정에서 모든 depth의 sweep으로 확장(subagent 불가 시 self-run 후 transcript 기록), contrarian probe는 정체와 무관하게 handoff 전 최소 1회. Gates에 두 장치의 최소 1회 실행 게이트 추가.

미반영으로 남은 것: question_score 공식 무변경(계약 유지), 질문 스코어 exploration 항(상시 breadth sweep이 대체).

**spec postmortem 피드백 루프는 같은 날 3차로 별도 스킬 `ultimateinterview-postmortem`으로 구현했다.** 설계 근거·divergence 분류·failure class 귀속·lessons 루프의 전체 기록은 다섯 번째 개발 히스토리인 `docs/ultimateinterview-postmortem-design.md`를 보라.
