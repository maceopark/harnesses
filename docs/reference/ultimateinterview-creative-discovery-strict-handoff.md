# Ultimateinterview 단순화 연구 및 개발 핸드오프

**작성일:** 2026-07-13  
**상태:** 다음 개발 세션을 위한 설계 핸드오프  
**범위:** 인터뷰의 unknown-unknown 발견력, 결정 권한, Build Contract 경계, 관련 테스트 실패

## 1. 결론

`ultimateinterview`의 핵심 가치는 복잡한 인터뷰 상태 머신이 아니다.

> 자유로운 인터뷰와 저장소 관찰에서 나온 불완전한 이해를, 증거·결정 권한·검증 가능성이 연결된 엄격한 구현 계약으로 컴파일하는 것이 핵심이다.

권장 구조는 다음과 같다.

```text
CREATIVE DISCOVERY
  - 저장소·문서·테스트·설정·필요한 history를 조사
  - 한 번에 가장 영향이 큰 질문 하나
  - 답변이 여는 design branch를 자유롭게 추적
  - lens·scenario·contrarian 기법은 선택적 사고 도구
        |
        v
DRAFT CONTRACT
  - user decisions
  - repo-established facts
  - explicitly delegated implementation choices
  - assumptions / unresolved owner decisions
        |
        v
ONE FRESH BLINDSPOT + AUTHORITY AUDIT
  - reviewer는 발견만 하고 계약을 직접 수정하지 않음
  - repo-answerable / delegable-implementation / owner-decision 분류
  - owner-decision 발견 시 사용자에게 반환
        |
        v
STRICT BUILD CONTRACT
  - traceable requirements
  - explicit decision boundaries
  - acceptance predicates
  - verification commands/scenarios
  - unresolved owner decision이 있으면 handoff 차단
```

인터뷰의 창의성을 높이기 위해 per-turn lens scan, lexical trigger, 질문 점수, mandatory sweep 같은 절차를 추가하지 않는다. 엄격함은 draft contract가 구현 명령으로 바뀌는 경계에 집중한다.

## 2. 이 연구가 시작된 실제 실패

Firestore local-first 요구사항 인터뷰의 fresh-implementer/adversarial review에서 다음과 같은 값과 정책 후보가 발견됐다.

- 보존기간
- latency 목표
- actor/authorization ownership
- error/retry/recovery taxonomy
- compatibility 및 migration disposition

문제는 reviewer finding이 사용자의 새 결정 질문으로 돌아가지 않고, 모델이 합리적인 기본값처럼 contract에 반영할 수 있었던 점이다.

핵심 오류는 다음과 같다.

```text
review finding
  -> technically reasonable recommendation
  -> contract patch
  -> reviewer consensus
  -> implementation-ready
```

그러나 올바른 경로는 다음이어야 한다.

```text
review finding
  -> authority triage
      - repo-answerable
      - delegable-implementation
      - owner-decision
  -> owner-decision이면 interview로 반환
```

`consensus`는 `authorization`이 아니며, reviewer recommendation은 user decision이 아니다.

## 3. 현재 로컬에 존재하는 reviewer-triage prototype

현재 harnesses working tree에는 아직 커밋되지 않은 prototype 변경이 있다.

- `.agents/skills/ultimateinterview/SKILL.md`
- `.agents/skills/ultimateinterview/references/handoff-sequence.md`
- `.agents/skills/ultimateinterview/references/audit-checklists.md`
- `.agents/skills/ultimateinterview/references/output-template.md`
- `.agents/skills/ultimateinterview/scripts/test_reviewer_triage_contract.py`

prototype의 핵심 규칙:

1. reviewer finding을 contract에 반영하기 전에 정확히 세 분류 중 하나로 triage한다.
2. observable UX, scope/non-goals, retention/deletion, authorization/actor ownership, lifecycle/error/retry/recovery, irreversible migration/data loss, compatibility floor, numeric quality threshold는 binding repo policy가 없는 한 `owner-decision`이다.
3. `owner-decision`은 ENDGAME을 중단하고 LOOP로 돌아가 사용자에게 질문한다.
4. reviewer/model recommendation이나 conventional default는 owner decision을 성립시키지 않는다.
5. settled ledger citation 없이 duration, timeout, threshold, enum member, permission rule, failure policy, migration disposition, non-goal을 handoff에 직접 추가하지 않는다.

검증 기록:

- 신규 regression test: `4 passed`
- 관련 integration tests: `11 passed`
- `git diff --check -- .agents/skills/ultimateinterview`: 통과
- 전체 suite 당시 결과: `1051 passed, 8 failed`

이 prototype은 즉시 발생한 authority-routing 버그를 막는 데는 유효하지만, 현재 복잡한 LOOP 전체를 유지해야 한다는 결론을 의미하지 않는다.

## 4. Unknown unknowns 연구에서 얻은 결론

검토한 자료:

- [Know your unknowns](https://thariqs.github.io/html-effectiveness/unknowns/)
- [Blindspot pass](https://thariqs.github.io/html-effectiveness/unknowns/01-blindspot-pass.html)
- [The interview](https://thariqs.github.io/html-effectiveness/unknowns/06-interview.html)
- [The tweakable implementation plan](https://thariqs.github.io/html-effectiveness/unknowns/08-implementation-plan.html)

핵심 관찰:

1. 인터뷰는 unknown 발견 도구 중 하나일 뿐이다.
2. unknown unknown은 질문만으로 발견되지 않는다. 코드, 문서, 테스트, 설정, migration, recent/reverted history, prototype, 구현 중 deviation 등 territory와 접촉해야 한다.
3. 짧은 prompt는 frontier LLM의 semantic generalization, adaptive follow-up, multilingual understanding을 잘 이용한다.
4. 상세한 상태 머신과 taxonomy는 instruction entropy, attention competition, anchoring, coverage theater를 만들 수 있다.
5. 같은 context의 self-review는 초기 framing과 correlated되어 있으므로 handoff 직전 fresh-context blindspot pass 한 번이 비용 대비 효과가 높다.

권장 interview prompt shape:

```text
Interview me one question at a time to uncover ambiguities,
assumptions, and blind spots in [goal].

Choose the next question by how much its answer could change
what gets built. Inspect the relevant repo, docs, tests, and
history—or suggest a quick prototype—whenever that would reveal
more than asking me.
```

`architecture`만 우선하면 UX, 정책, 운영, 권한, 데이터 수명 같은 product decision이 묻힐 수 있으므로 `what gets built` 또는 `material implementation impact`가 더 적절하다.

## 5. LLM council 결과

세 개의 독립 read-only council lane이 거의 같은 결론을 냈다.

| Lane | Verdict | 핵심 결론 |
| --- | --- | --- |
| Prompt Minimalist | `SUFFICIENT-WITH-ONE-GUARD` | 짧은 interview prompt는 적절하며 종료 전 repository/history blindspot pass 하나가 필요 |
| Adversarial Unknowns | `WATCH` | 대화 제어 정책으로 충분하지만 evidence acquisition 없이 unknown unknown을 발견할 수 없음 |
| LLM Behavior Review | concise prompt 선호 | detailed workflow는 attention tax와 taxonomy anchoring을 만들며 strictness는 handoff에 배치해야 함 |

공통 결론:

- per-turn independent reviewer는 필요 없다.
- 매 턴 semantic lens schema도 필요 없다.
- 질문보다 관찰이 유리하면 repo/history/reference/prototype를 사용한다.
- 독립 review는 draft contract 이후, seal 이전에 한 번 수행한다.
- review에서 발견된 owner decision은 contract에 직접 넣지 않고 사용자에게 반환한다.

## 6. Grill-with-docs 비교

검토한 소스:

- `skills/skills/engineering/grill-with-docs/SKILL.md`
- `skills/skills/productivity/grilling/SKILL.md`
- `skills/skills/engineering/domain-modeling/SKILL.md`
- `skills/skills/engineering/to-prd/SKILL.md`

`grill-with-docs` 본문은 사실상 다음 한 줄이다.

```text
Run a /grilling session, using the /domain-modeling skill.
```

좋은 점:

- 한 번에 질문 하나
- design tree branch와 decision dependency를 자유롭게 추적
- 코드가 답할 수 있으면 사용자에게 묻지 않고 조사
- fuzzy/overloaded term을 challenge
- concrete scenario로 경계를 압박
- 사용자 설명과 코드를 교차검증

약점:

- `until shared understanding`은 same-context LLM의 주관적 종료 판단이다.
- codebase 외 recent/reverted history, environment differences, hidden consumers를 명시적으로 찾지 않는다.
- 모든 질문에 recommendation을 주므로 owner decision anchoring 위험이 있다.
- 대화 중 glossary/ADR mutation은 잠정 결론을 일찍 굳힐 수 있다.
- 다음 단계인 `to-prd`는 “Do NOT interview; synthesize what you already know”라고 하며 extensive user stories와 implementation decisions를 생성하므로 빈칸을 모델이 채울 위험이 있다.

살릴 철학:

```text
adaptive design-tree interview
+ one question at a time
+ inspect instead of asking facts
+ scenario and vocabulary pressure
```

필요한 보완:

```text
Recommendations are proposals, not settled decisions,
until the owner chooses them.
```

그리고 handoff compiler/authority audit를 별도로 둔다.

## 7. Codex Plan Mode 비교

검토한 pinned source:

- commit: `9e552e9d15ba52bed7077d5357f3e18e330f8f38`
- [Plan Mode prompt](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/collaboration-mode-templates/templates/plan.md)
- [Template loader](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/collaboration-mode-templates/src/lib.rs)

Codex Plan Mode 구조:

```text
PHASE 1: Ground in environment
PHASE 2: Intent chat
PHASE 3: Implementation chat
-> decision-complete <proposed_plan>
```

강점:

- explore first, ask second
- discoverable facts와 preferences/tradeoffs 구분
- intent와 implementation을 분리
- mutation 없이 계획 개선
- implementer가 새 결정을 하지 않아도 되는 plan 생성

핵심 결함:

```text
If unanswered, proceed with the recommended option
and record it as an assumption in the final plan.
```

이 규칙과 `decision complete` 압력이 결합하면 unanswered owner decision을 모델 기본값으로 채울 수 있다.

```text
owner decision unanswered
  -> recommended default
  -> recorded assumption
  -> decision-complete plan
```

권장 수정 원칙:

```text
Unanswered delegated implementation choices may use a recorded default.
Unanswered owner decisions remain blocking and cannot be filled by model consensus.
```

Codex Plan Mode는 `grilling + repo grounding + plan compiler`에 가깝고, Ultimateinterview 단순화의 좋은 골격이다.

## 8. Deep Interview와 Ralplan에서 확인한 경계 문제

검토한 소스:

- `oh-my-codex/skills/deep-interview/SKILL.md`
- `oh-my-codex/skills/ralplan/SKILL.md`

Deep Interview:

- fixed clarity dimensions를 매 답변 후 재채점한다.
- pressure ladder와 Breadth Ledger를 사용한다.
- lexical signal matcher는 없다.
- 별도 semantic reviewer를 매 턴 호출하지 않는다.
- ambiguity weighted average와 subjective closure audit이 owner-decision provenance를 보장하지는 않는다.

Ralplan:

- Planner -> Architect -> Critic consensus loop
- `--interactive`는 draft review와 final approval에서 사용자 접점을 제공한다.
- Critic이 5회 안에 승인하지 않으면 best version을 사용자에게 제시한다.
- 그러나 escalation 조건은 `owner decision 발견`이 아니라 `model consensus 실패`다.

따라서 다음은 가능하다.

```text
Planner가 사용자 정책 기본값 선택
-> Architect가 기술적으로 타당하다고 판단
-> Critic이 테스트 가능하고 일관적이라고 승인
-> 1회에 consensus
-> 사용자 질문 없음
```

반대로 순수 기술 선택도 5회 합의하지 못하면 사용자에게 돌아간다.

필요한 기준은 다음이다.

```text
현재: 모델들이 합의하지 못했는가?
필요: 사용자의 결정 권한이 필요한가?
```

`ralplan --interactive`는 human-in-the-loop planning review이며 proposal-driven interview 효과가 있지만, owner decision을 하나씩 추출하는 requirements interview는 아니다.

## 9. Ultimateinterview에서 반드시 살릴 부분

### 9.1 Evidence provenance

- `from-code`
- `from-docs`
- `from-user`
- `from-research`
- `from-scenario`
- `assumption`

최종 계약의 각 normative clause가 왜 존재하는지 추적할 수 있어야 한다.

### 9.2 Authority routing

- repo fact는 조사
- repo fact가 product policy를 자동 결정하지 않음
- code/docs/user evidence 충돌을 조용히 해소하지 않음
- explicitly delegated implementation choice만 모델이 결정
- owner decision은 사용자에게 반환

### 9.3 Reviewer non-authority

- reviewer는 finding을 반환
- reviewer는 contract를 직접 수정하지 않음
- reviewer consensus는 authorization이 아님

### 9.4 Strict Build Contract

- goal, scope, non-goals
- observable behavior
- explicit decision boundaries
- acceptance predicates
- verification commands/scenarios
- failure behavior
- requirement-to-verification traceability
- unresolved owner-decision blocker

### 9.5 Fresh-context audit 한 번

- initial framing에 갇힌 누락
- repo/history/config/environment mismatch
- hidden consumer/integration
- failure/retry/recovery
- unauthorized defaults
- gameable acceptance criteria

### 9.6 Resume에 필요한 최소 기록

권장 최소 형태:

```text
transcript.md
working-notes.json
draft-contract.md
build-contract.json
```

`working-notes`에는 facts, user decisions, open questions, non-goals, delegated decisions, evidence references만 둔다.

## 10. 선택적 도구로만 살릴 부분

다음은 mandatory state가 아니라 LLM의 prompt technique library로 유지한다.

- viewpoint
- domain/state
- goal/obstacle
- misuse
- quality
- controlled-language
- pressure follow-up
- counterexample
- concrete scenario
- contrarian
- simplifier
- terminology collision
- root-cause reframing

렌즈는 taxonomy가 아니라 필요할 때 꺼내는 사고 도구다.

고위험/감사 환경에서만 선택적으로 켤 것:

- assurance v2
- manifest sealing
- execution receipts
- consumer verification
- 다중 reviewer lane
- evidence independence 계산

## 11. 제거 또는 기본 경로에서 제외할 부분

인터뷰 기본 경로에서 제거 후보:

- 영어 lexical `signal_firing`을 semantic coverage gate로 사용하는 것
- lens triggered/done/skipped state machine
- 질문 점수 공식과 `questions.json`
- residual ambiguity dashboard
- interaction counter 중심 event taxonomy
- every-N-round mandatory sweep
- locality drift 계산
- dry-sweep streak
- mandatory challenge-mode 순서
- 매 답변 bookkeeping ceremony

제거해야 할 종료/결정 관념:

- ambiguity score가 낮으면 충분하다는 판단
- lens를 모두 방문하면 complete라는 판단
- reviewer consensus가 owner approval이라는 판단
- unanswered preference를 추천 기본값으로 채우는 방식

## 12. `signal_firing` 및 receipt test 실패

전체 test suite에서 남았던 8개 실패:

### 12.1 `test_signal_firing.py` 1건

실패 문장:

```text
add a validation rule for the JSON store; reject oversized input on load
```

기존 English lexical matcher가 `domain/state`를 발화하지 못했다.

처음에는 persistence term dictionary와 state-boundary term dictionary를 제안했으나, 한국어·일본어·도메인 동의어 문제 때문에 일반 해결책이 아니다.

결론:

- lexical matcher는 알려진 English regression을 관찰하는 보조 도구로만 사용
- multilingual semantic completeness 또는 handoff readiness를 증명한다고 주장하지 않음
- failing canonical test를 단어 추가로 고치기보다 test가 보장하는 scope를 재정의
- discovery completeness는 evidence contact + fresh blindspot review로 다룸

### 12.2 `test_v2_gate_integration.py` 7건

원인:

- receipt import는 test fixed `NOW = 2026-07-11` 사용
- fixture expiry는 `2026-07-12`
- `session_status.capture_session_snapshot()`은 실제 wall clock `datetime.now(UTC)` 사용
- 현재 날짜가 expiry 이후라 import와 status가 서로 다른 clock으로 같은 receipt를 평가

가장 작은 robust fix:

```python
def _utc_now() -> datetime:
    return datetime.now(UTC)
```

`capture_session_snapshot()`에서 직접 `datetime.now(UTC)` 대신 `_utc_now()`를 한 번 호출하고, v2 integration test에서 기존 `NOW`로 monkeypatch한다.

- production expiry semantics 유지
- public CLI option 추가 없음
- Clock protocol/class 불필요
- fixture 날짜 연장 같은 임시방편 불필요
- import/status가 동일한 test time 사용

추가 regression:

- fixed NOW에서 기존 7개 test 통과
- `_utc_now()`를 expiry 이후로 바꾸면 `execution_receipts_current == false`
- failed execution receipt는 current일 수 있지만 creditable하지 않음을 확인

## 13. 권장 개발 순서

### Step 1: 안전망 버그 정리

1. private `_utc_now()` seam 추가
2. v2 integration test에 fixed clock 주입
3. `signal_firing` test의 보장 범위를 semantic completeness에서 lexical regression으로 축소
4. 전체 suite green 확인

### Step 2: 인터뷰 기본 경로 단순화

1. 짧은 creative interview policy 작성
2. evidence-first exploration과 한 번에 영향도 높은 질문 하나만 비협상 규칙으로 유지
3. lens/scenario/challenge를 optional technique reference로 이동
4. scoring/counter/mandatory sweep을 기본 경로에서 제거
5. resume state를 최소화

### Step 3: strict boundary 강화

1. draft contract 생성
2. fresh-context blindspot review 한 번
3. finding authority triage
4. owner-decision이면 사용자에게 반환
5. settled contract만 Build Contract로 compile/seal
6. requirement -> acceptance -> verification traceability gate 유지

### Step 4: downstream 계약

Ralplan/implementer에게 다음 규칙을 전달한다.

```text
May decide:
  explicitly delegated implementation mechanics
  internal architecture and file/module structure
  algorithms and test organization that preserve settled behavior

Must not decide:
  user-visible behavior
  scope/non-goals
  retention/deletion
  authorization/actor ownership
  retry/recovery semantics
  irreversible migration/data loss
  compatibility floors
  numeric quality thresholds
```

새 owner decision이 발견되면 consensus 대상이 아니라 사용자에게 반환한다.

## 14. Non-goals

이번 단순화의 목적은 다음이 아니다.

- unknown unknown을 완전히 제거했다고 주장
- 인터뷰를 checklist로 대체
- 모든 답변을 event taxonomy로 분류
- 매 턴 별도 LLM reviewer 호출
- multilingual NLP engine 구현
- evidence ledger와 contract gate를 모두 제거
- high-assurance v2 기능 삭제

목표는 일반 인터뷰의 창의성과 질문 품질을 높이고, strictness를 구현 handoff 경계에 집중하는 것이다.

## 15. 성공 기준

새 설계는 최소한 다음을 만족해야 한다.

1. 인터뷰 모델은 workflow bookkeeping보다 사용자 답변과 repo evidence에 attention을 집중한다.
2. 질문은 한 번에 하나이며 답변이 여는 branch를 자유롭게 추적한다.
3. repo가 답할 수 있는 사실은 조사하고, human policy는 사용자에게 묻는다.
4. fresh reviewer는 finding을 직접 contract에 추가할 수 없다.
5. 모든 contract의 normative clause는 evidence 또는 explicit delegation에 연결된다.
6. unresolved owner decision이 있으면 implementation-ready가 될 수 없다.
7. implementer가 delegated 범위 밖에서 product behavior를 결정할 필요가 없다.
8. lexical matcher 결과는 multilingual discovery completeness의 근거로 사용되지 않는다.
9. receipt tests는 wall-clock 날짜에 따라 깨지지 않는다.
10. 기본 인터뷰 prompt와 runtime은 현재보다 현저히 짧고 이해 가능해야 한다.

## 16. 다음 세션을 위한 핵심 문장

> 인터뷰를 더 통제하지 말고 더 잘 관찰하게 하라. 모델의 창의성은 discovery에 사용하고, 결정 권한과 검증 가능성은 handoff compiler에서 강제하라.
