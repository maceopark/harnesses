# ultimateinterview vs ouroboros — 실행-불가지 스펙/계약 층 전략 (조사 기록)

**작성일:** 2026-07-11
**범위:** 두 렌즈 리뷰(LLM Council / GPT six-lens)의 대조 검증 → ouroboros evaluate/evolve 메커니즘 정독 → v0.50.x 철학 전환 확인 → `ultimateinterview` 스킬의 전략적 포지셔닝
**방법:** 스킬 런타임 소스 + ouroboros v0.50.1 소스 직접 대조(파일:라인 인용), LLM Council 적대적 재검증, 다회차 정정
**대조 기준 커밋:** ouroboros `v0.50.1` (`34c39011`); 스킬 `.agents/skills/ultimateinterview/`

---

## 0. TL;DR (결론)

1. 두 리뷰 중 **GPT six-lens의 진단(카테고리-내 열거 + 증거 정당화 + 닫힌 분류표)** 이 실제 실패 분포에 부합한다. Council의 "요구사항 간 상호작용 창발" 진단은 이론적으로 우아하나 코퍼스 증거가 없다.
2. ontology-miss 발견을 postmortem에 넣는 것은 **ouroboros의 evaluate→evolve 루프를 스킬 안에 복제**하는 것이라 목적(shift-left)에 반한다. 진짜 레버는 **인터뷰 시점의 프레임-불가지 divergence probe**다.
3. ouroboros v0.50.0 철학 전환("contracts, not claims")과 v0.50.x 코드(N-version tournament, reviewer independence, grounded elenchus)는 우리가 논한 인식론과 강하게 수렴한다 — 단 **전부 빌드-후 / 승자선택 / AC-입도**라 "빌드-전·델타채굴·프레임불가지"의 빈칸은 남는다.
4. 실행 층이 프론티어 코딩 에이전트로 커모디티화되는 추세에서, **실행을 소유하는 ouroboros식 방향은 지는 베팅**이다. 방어가능한 코어는 "모호한 의도 → 기계검증·반증가능·게이밍내성 계약"의 컴파일러다.

---

## 1. 질문의 아크

- 두 문서(`ultimateinterview-lens-council-review.md`, `ultimateinterview-six-lens-epistemic-review.md`)의 주안점이 다름 → 어느 개선이 최대 효과인가?
- ontology-miss 발견은 ouroboros evaluate→evolve가 이미 하는 일 아닌가? 그 루프가 너무 오래 돌아서 인터뷰 단계로 당기려는 것이 스킬의 목적.
- ouroboros evaluate/evolve의 전체 옵션과 실제 동작은? (`--no-execute` 등)
- v0.50.x 철학 업데이트의 실체는?
- 추세상 실행은 코딩 에이전트에 맡기고 인터뷰·스펙에 집중하는 방향은?

---

## 2. 검증된 사실 (소스 인용)

### 2.1 스킬 측
- **residual은 가법적:** `scripts/ambiguity_ledger.py:427` `residual = sum(entry.contribution)`, contribution = `impact_weight × ambiguity_score`. 상호작용 항 없음.
- **삼각검증 = 채널 개수:** `SKILL.md:35` "the script counts distinct channels". 증거 lineage/독립성은 세지 않음.
- **postmortem 실패분류가 닫혀 있음:** `trigger-too-narrow / enumeration-miss / scoring-starved / answer-unpressured / synthesis-loss / known-deferred`. **`ontology-miss` / `owning-frame: none` 없음.** escape마다 기존 렌즈 귀속 필수 → "6렌즈 충분" 이 구조적으로 재생산됨.
- **실제 escape 코퍼스:** 14건 중 12 enumeration-miss + 2 synthesis-loss. 최근 app-5 2건(`next_id` predicate, `>=3.11` version floor)은 **열거된 카테고리 내부의 predicate 미고정** = 카테고리-내 깊이 실패. requirement×requirement 창발 실패 사례는 코퍼스에 없음.

### 2.2 ouroboros 루프
- **사이클:** `Interview → Seed → Execute → Evaluate → Evolve`. Evolve = `Wonder("무엇을 아직 모르나") → Reflect → 다음 세대`. 수렴 = ontology similarity ≥ 0.95, 최대 30세대(`ralph`는 수렴까지 반복).
- **`ouroboros_evolve_step` 옵션:** `execute`(기본 true; false=ontology-only, 실행·평가 스킵), `parallel`(기본 true; AC 병렬, import 충돌 유발→`_evolution_validator` 사후 reconcile), `skip_qa`, `project_dir`, `checkpoint_policy`/`checkpoint_commits`.
- **`ouroboros_evaluate` 3단계:** Mechanical($0, lint/build/test, fail-fast) → Semantic(AC준수·drift, AC별 병렬) → Consensus(다모델 투표, 불확실성/수동). evaluate SKILL의 "2.5 acting verification"은 실제 실행·관찰 후 증거 주입.
- **수렴 판정(`evolution/convergence.py`):** ANY of 자기유사도≥0.95 / stagnation(3세대) / repetitive wonder(70% 겹침) / oscillation(period-2) / 30세대 캡. signal 1은 5개 게이트로 보류 가능(evolved_count==0 등). **`eval_gate_enabled: bool = False`(`:55`)** — 기본적으로 수렴은 평가 품질을 안 보고 온톨로지 자기유사도 우선. convergence.py는 v0.50 diff에 없음 = 미변경.
- **Wonder의 자기종료 편향(`evolution/wonder.py:291`):** "질문/tension 하나라도 생성하면 should_continue=true; 진짜 0일 때만 false" + `:298` "온톨로지는 항상 불완전". LLM은 "뭘 모르나"에 사실상 항상 ≥1개 답 → 루프를 멈추는 건 Wonder의 충분성 판단이 아니라 자기유사도 임계값.
- **`execute=false`의 한계:** `wonder()` 시그니처는 `evaluation_summary: ... | None, execution_output: str | None`; `_build_prompt`가 `if eval_summary`/`if execution_output`로 게이팅. execute=false → 둘 다 None → **빌드-온리 진실(load-time vs input-time, 미고정 predicate)에 눈멂.** 단 grounded elenchus의 `kind:"gap"`(`:283`)이 실행 없이도 goal-vs-AC-coverage gap은 명명 가능.

### 2.3 v0.50.0 철학 전환 — "The Verifiable Loop: contracts, not claims"
> "지금까지 루프는 에이전트가 *했다고 말한* 것을 신뢰했다 … 보고된 것이 아니라 실제로 실행된 것에 근거한다."

- **구조화 AC (#1551):** `AcceptanceCriterionSpec`(`verify_command` / `expected_artifacts` / `output_assertion`) — 기계검증 계약. 기존 맨-문자열 seed는 바이트-동일 로드.
- **실행자가 계약 소비 (#1575/#1548):** leaf에 SUCCESS CONTRACT 블록, 증거 게이트가 선언된 command/artifact를 런타임 대조로 요구.
- **평가자 계약 판정 + reward-hacking veto (#1572/#1585):** 게이밍 신호는 Stage 3 합의 통과 후에도 승인 거부.
- **verify-by-default (#1548):** verify 게이트·retry·fat-harness가 기본 경로.
- **권위 있는 실행에 근거 (#1592/#1591):** 계약-AC 평가가 재구성 transcript가 아니라 오케스트레이터 실행 기록을 읽음.
- **철학 RFC** `docs/rfc/reflect-grounded-elenchus-scoped-reexecution.md`:
  - Socratic **grounded elenchus:** "무엇을 반박하는지 이름 못 대는 질문은 질문이 아니라 기분이다. 모든 Wonder 질문은 명명된 AC를 challenge하거나 gap을 명명해야 한다."
  - Simon **satisficing + near-decomposability:** 통과 AC는 재도출 안 함; 다음 세대 아젠다 = 델타(failed ∪ regressed ∪ challenged ∪ gaps).
  - 설계 규칙: **"LLM proposes, deterministic code disposes."** (satisficing backstop이 보호 인덱스의 LLM revise를 강제 keep으로 override.)

### 2.4 v0.50.x가 우리 논의를 채택한 부분 (그리고 남은 빈칸)
- **reviewer independence(`evaluation/reviewer_independence.py`):** 백엔드→벤더군, 모델→벤더 매핑으로 executor와 같은 벤더 투표자를 걸러 jury를 `independent/same_vendor/unavailable/unverified` 판정. **`consensus.py:337`에 실제 배선.** = six-lens #1("채널 개수 ≠ 증거 독립성")의 실현(단, 평가 jury 층).
- **N-version tournament(`orchestrator/n_version_tournament.py`):** 최대 2개 다른 런타임이 격리 worktree에서 병렬 빌드, 검증 통과 첫 놈이 승자, 승자 diff 적용. = 독립 구성. **그러나 config 기본 `False`(opt-in), docstring "NOT live-wired", 그리고 `parallel_executor.py`/`cross_harness_redispatch.py`/`runner.py`/`mcp` 전체 grep 결과 호출부 0** → 기능적으로 불활성 scaffolding.

**남은 빈칸(스킬의 차별점):**
| 축 | ouroboros v0.50.x | 스킬의 자리 |
|---|---|---|
| divergence 용법 | 승자 선택, 패자·델타 버림 | 델타(불일치)를 **신호로 채굴** → 미결정 요구 재개방 |
| 시점 | 빌드 후 | 빌드 전(인터뷰/스펙) |
| 입도 | AC 입도(seed 안에서 명명 가능해야) | 프레임-불가지(미명명 요구의 under-determination도 diff로) |

---

## 3. LLM Council 적대적 재검증 결과

5개 핵심 주장 v0.50.1 소스 대조 판정:
- residual 가법 — ✅ 확인.
- Wonder 자기종료 편향 — ✅ 확인(정제: `:301`에 "AC 커버+회귀·실패 없음→false" 신규 조건 있음).
- `eval_gate` 기본 off / 수렴=자기유사도 우선 — ✅ 확인(convergence.py 미변경).
- N-version opt-in·미배선·승자선택 — ✅ **강화**(grep 호출부 0).
- reviewer_independence consensus 배선 — ✅ 확인.

**정직한 정제 3건(결론 반전 아님):**
1. N-version의 "이중실패 트리거"는 docstring상 *의도*이며, 실제 배선은 호출부 0 → 순수 scaffolding.
2. execute=false는 "완전 눈멂"이 아니라 "gap은 보되 빌드-온리 진실은 못 봄".
3. "3-C(실패 AC 품고 수렴)를 upstream이 닫음"은 층위 구분 필요 — 수렴 층은 `eval_gate` 기본 off로 그대로, 닫힌 건 평가 층(verify-by-default + grounding).

**의장 판정:** 조사결과는 진짜다. 반전된 결론 없음. 최고신뢰 단일 사실 = **N-version 호출부가 코드베이스 전체에 없음**(grep empty + 기본 False + docstring "NOT live-wired").

---

## 4. 전략 결론 — 실행-불가지 스펙/계약 층

### 왜 ouroboros식(실행 소유)이 지는 베팅인가
- 실행 소유 = 런타임 어댑터 난립(claude/codex/copilot/gemini/hermes/kiro/goose/pi/grok/antigravity/gjc). 프론티어 에이전트가 자체 흡수하는 커모디티 층과 무한 추격.
- "루프 너무 오래 돈다"의 근원이 실행 소유(매 세대 build+eval). 실행을 안 소유하면 문제 소멸.
- v0.50.0의 진짜 자산은 실행이 아니라 **계약**(실행-불가지). 오케스트레이터·어댑터는 껍데기.
- 커모디티화 안 되는 것 = "모호한 인간 의도 → 반증가능한 기계검증 계약" 사이의 간극. 에이전트는 스펙 *실행*은 잘하나 *뭘 만들지 아는* 건 여전히 못 함.

### 반드시 안고 갈 제약
닫힌 어휘로는 빌드-온리 진실을 스펙 단계에서 못 본다. ouroboros는 실행을 소유해서 봤다. 따라서 방향은 "실행 버리기"가 아니라 **"실행을 소유하지 않되 실행 진실은 최소 비용으로 빌려오기"** — divergence probe를 영속 루프가 아니라 **핸드오프 직전 1회성 borrow-and-discard**로.

### 권장 액션 (우선순위)
1. **포지션 고정:** "실행-불가지 계약 컴파일러". evolve/execute 루프 소유·복제 야심 폐기. 핸드오프 문서가 제품. (스킬은 이미 Build Contract에서 멈추고 넘김 — 전략 중심으로 승격.)
2. **산출물 = 기계검증 계약:** v0.50의 `AcceptanceCriterionSpec` 모양(verify_command / expected_artifacts / output_assertion)을 채택해 "Verification commands + EARS/GWT"를 타입 있는, 에이전트가 바로 소비·자가검증 가능한 계약으로. 목표: 에이전트의 native verify-by-default가 이 계약을 만족 못 하면 done 선언 불가.
3. **anti-gaming 계약 내장:** fresh-implementer test의 "테스트 게이밍 재바인딩"을 1급 속성으로 — acceptance가 claim이 아니라 관찰가능 표면에 묶이도록.
4. **divergence probe = 1회성 실행 차용:** 애매한 코어에 2개 독립 stub → diff → 미결정 지점 채굴 → 계약에 접어넣고 버림. 영속 루프 아님. 빌드-온리 진실을 스펙 단계로 들여오는 최소 장치.
5. **핸드오프→결과 경량 계측(postmortem):** 어떤 모호성이 샜는지만 학습 → 인터뷰 개선. 실행 재현 안 함. 스펙 층위의 값싼 evolve 루프.

### 이 포지션의 정직한 비용
- 실행 미소유 = ouroboros가 공짜로 얻던 폐루프 학습신호 상실 → (5)의 경량 계측이 필수(안 하면 스펙 유효성에 눈뜬장님).
- 벤더가 스펙/plan 층으로 상승 중 → 방어코어는 "PRD 써주기"가 아니라 **모호성 회계 + 반증 + 증거 provenance + fresh-implementer/divergence 체크**(스킬이 이미 인코딩한 인식론적 규율).

**한 줄 전략:** 실행은 에이전트의 native 장기 멀티에이전트에 맡기고, 스킬은 "의도→기계검증·반증가능·게이밍내성 계약"의 컴파일러가 된다. 계약이 둘 사이의 API고, divergence probe는 계약을 빌드 전에 조이는 1회성 실행 차용일 뿐 실행 시스템이 아니다.

---

## 5. 열린 다음 단계
- (A) 스킬의 Build Contract를 `AcceptanceCriterionSpec` 스타일 타입 계약으로 재설계(스키마 + 에이전트-불가지 핸드오프 규약 + divergence probe 삽입 지점).
- (B) grounded-elenchus + satisficing backstop 구현(`wonder.py`/`reflect.py`) 정독 → 스킬 게이트에 이식할 "LLM proposes, deterministic disposes" 패턴 추출.
- (C) evidence provenance/independence를 스킬 ledger의 1급 속성으로(six-lens #1).

## 6. 출처
- 스킬: `.agents/skills/ultimateinterview/{SKILL.md, references/*, scripts/*, lessons.md}`, `.agents/skills/ultimateinterview-postmortem/*`
- ouroboros v0.50.1: `src/ouroboros/evolution/{loop,wonder,convergence,reflect}.py`, `src/ouroboros/evaluation/{reviewer_independence,consensus}.py`, `src/ouroboros/orchestrator/n_version_tournament.py`, `src/ouroboros/mcp/tools/{evolution_handlers,evaluation_handlers}.py`, `docs/rfc/reflect-grounded-elenchus-scoped-reexecution.md`
- 릴리즈: `github.com/Q00/ouroboros/releases/tag/v0.50.0` ("The Verifiable Loop: contracts, not claims")
- 리뷰 원본: `docs/ultimateinterview-lens-council-review.md`, `docs/ultimateinterview-six-lens-epistemic-review.md`
