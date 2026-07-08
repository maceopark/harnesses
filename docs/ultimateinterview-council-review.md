# Ultrainterview Council Review & 5-Idea Upgrade

시리즈 여섯 번째 개발 히스토리. `requirements-gap-discovery` → `improvement-proposal` → `research-synthesis` → `hardening-review` → `postmortem-design`에 이어, 이번에는 외부 AI council(agent-council 플러그인: codex GPT-5.5 + agy)의 적대적 비교 리뷰와, 그 평결에서 나온 개선안 5개의 반영 기록이다.

## 리뷰 설정

비교 대상은 두 겹이었다. repo 내부: ouroboros interview(MCP 기반, 779줄), oh-my-codex deep-interview(가중 ambiguity 공식, 579줄), grill-me(13줄, stateless), feature-dev(에이전트 fanout), ouroboros pm. 외부 공개 도구: obra/superpowers brainstorming(~247k★, prose HARD-GATE), github/spec-kit /clarify(~118k★, 11-category taxonomy + 5문항 cap), BMAD-METHOD(~50k★, brain dump + stakes calibration, "MCQ 트리는 anti-pattern" 철학), Agent-OS, PRPs(research-first, "No Prior Knowledge" test), rizethereum requirements-builder(yes/no 배치 + smart defaults), Anthropic doc-coauthoring(info-dump + batch questions + fresh-reader test).

council 질문은 5개 판정 기준을 강제했다: unknown-unknown 발견률, 사용자 응답 부담, enforcement 신뢰성(543줄 prose 프로토콜이 컨텍스트 압박에서 실제로 실행되는가), task-size 적합성, 구현 handoff로서의 스펙 품질.

## 평결

두 멤버가 독립적으로 수렴했다: **고위험 brownfield 변경에서만 materially better, 일상 작업에서는 over-engineered ceremony.** 차별점으로 인정받은 것은 evidence ledger, falsification checkpoint, 그리고 postmortem lessons 루프(조사한 12개 도구 중 유일). 수렴된 결함 4건:

1. **MCQ confirmation-bias corridor** — LLM이 자기 모델로 선택지를 만들고 사용자는 recommended를 고른다. LLM이 예상 못한 것은 선택지에 존재할 수 없으므로 unknown-unknown이 구조적으로 억압된다.
2. **prose-gate drift** — 산수만 스크립트고 lens 실행·pressure·sweep·checkpoint 타이밍은 prose. "enforcement boundary is fake past the Python helpers" (codex). 스킬이 ledger에는 "status 라벨을 신뢰하지 말라"는 fail-closed 원칙을 적용하면서 프로토콜 실행 자체에는 적용하지 않은 자기모순.
3. **응답 부담** — one-at-a-time × 12 + 전 답변 pressure follow-up = cross-examination. 사용자가 지치면 얕은 답이 오고 스펙 품질이 무너진다.
4. **implementation-noisy handoff** — ~20개 섹션의 감사 자료가 핵심 빌드 결정을 묻는다. 구현자에게 필요한 건 "계약 먼저, 증거는 분쟁 시".

의장 정정 2건: "사전 코드 마이닝 부재" 주장은 Orientation의 inspect-first 규칙을 놓친 오독, "stakes calibration 부재"는 risk-triggered depth를 놓친 절반 오독(단, minimal 경로도 전체 시스템의 정신적 무게를 진다는 재구성은 유효).

## 반영된 개선 5건

### 1. Brain-dump-first intake (Orientation 4단계)

기본 첫 상호작용이 질문이 아니라 서사 초대가 됐다: 원하는 것과 이유, 아는 제약, 깨질까 두려운 것, 본 적 있는 edge case, "by the way". dump를 `from-user` ledger 항목으로 채굴하고 실제 implementation branch를 추출한 뒤에야 scored question을 시작한다. 요청 자체가 이미 dump인 경우(풍부한 issue text, 기존 draft)나 사용자가 거절하면 `brain_dump_waiver`에 이유를 기록하고 건너뛴다. 기존 context-first entry(heavy pre-work → falsification checkpoint 첫 상호작용)는 waiver를 겸한다.

Converge 6단계에도 같은 원칙: **option space가 code/docs/dump로 증거화된 gap에만 고정 선택지 제공.** 증거 없이 선택지를 발명하면 사용자를 내 가정으로 유도하는 것이므로 scenario/freeform으로 묻는다.

### 2. Smart-default batching (Converge 5단계)

gap을 criticality로 라우팅한다. `critical-path`(weight 3/5, score-3 붕괴, 실제 분기, 증거 모순, scope 축소)는 기존대로 top-ranked 1문항 적응형. 나머지(weight 1/2 확인, repo가 이미 제안하는 default)는 3-5개를 한 메시지에 배치 — 각 항목은 `Based on <evidence>, default: <X>` 형식이고 사용자는 항목별 응답 또는 한 줄로 전체 수락. 배치는 예산과 sweep cadence에 1로 계산된다(예산의 단위가 "question"에서 "interaction" = 사용자 중단 횟수로 재정의됨). 수락된 default는 score 1 + 유래 채널 + `from-user`로 정착. critical-path gap은 절대 배치에 넣지 않는다.

### 3. Pressure 범위 축소 (Answer Handling 규칙 1)

`Pressure before settling` → `Pressure where it pays`. follow-up 의무는 이제 트리거 기반: weight 3/5 정착, score-3 붕괴, `from-code`/`from-docs` 모순, scope/artifact class 축소, hedged 답변("probably", "I think"). 그 외 저위험 선호·default 확인은 채널 기록과 함께 즉시 정착. 2차 채널 corroboration 대체 규칙은 유지.

### 4. Build Contract (Output Contract 재구조화)

스펙이 고정된 2부 구조가 됐다. **Part 1 Build Contract**: goal 한 문장, target surface(파일/모듈별 예상 변경), behavior contract(요구사항 + acceptance criterion), decision boundaries, out of scope, implementation constraints, verification commands, deferred risks. **fresh-implementer test를 통과해야 handoff 가능**: 대화에 접근 없는 구현자가 Part 1만 읽고 같은 변경을 구현할 수 있는가 — "I would have to ask" 항목은 전부 gap으로 환류. PRP의 "No Prior Knowledge" test를 게이트로 이식한 것. **Part 2 audit trail**: 기존 대시보드·매트릭스·로그 전부. `references/output-template.md`도 같은 구조로 개편.

### 5. Protocol state 스크립트화 (`scripts/protocol_state.py`)

council의 2위 결함(prose-gate drift)에 대한 직접 응답. `.ultimateinterview/<slug>/protocol.json`이 프로토콜 실행 사실을 기록하고 — depth, budget 사용량, 6개 lens 결정(triggered/done/skipped+이유), sweep/probe/checkpoint 카운터, brain-dump/framing 상태, residual history — 새 스크립트가 ledger와 같은 fail-closed 검증으로 판정한다: 모르는 lens 이름 거부, 6개 전부 명시적 결정 강제, 이유 없는 skip 거부. 산출은 두 층: `Due Now` interview obligations(sweep 지연, 예산 소진, 정체 → 다음 scored question을 선점)와 handoff blockers(framing/brain-dump/sweep/probe/checkpoint/미완 lens/미검증 build contract). handoff 정지 조건이 `handoff_ready`(ledger) + `protocol_ready`(protocol) 양 헬퍼 공동 판정이 됐다. "기록되지 않은 프로토콜 단계는 일어나지 않은 것이다."

테스트는 13 → 31개(protocol_state 18개 신규: ready/blocker 판정, 경계값, 정체 감지, fail-closed 거부 6종). 구현 중 잡힌 버그 1건: `is_stagnant`의 `zip(strict=True)`가 의도적으로 길이가 다른 window 쌍에서 ValueError — 테스트가 즉시 잡았다.

## 검증 라운드 (ultracode workflow)

구현 직후 4-lens 적대적 검증 워크플로를 돌렸다: 스크립트 실행 공격(reviewer가 malformed 입력을 실제 실행), 문서 일관성, fresh-context 실행가능성(처음 읽는 에이전트가 충실히 실행 가능한가), 기존 계약 회귀. 리뷰어 finding 각각을 별도 skeptic 에이전트가 현재 파일을 다시 읽고 반증 시도 — 26개 검증 에이전트, **13건 확정 / 9건 기각 / 4건 계약 보존 확인**(question_score 공식, ambiguity_ledger 의미론, postmortem 아티팩트 참조, 양-헬퍼 정지 조건).

확정 결함 중 굵직한 것들과 수정:

- **fail-open 구멍**: `protocol_state.py`가 pydantic 기본값(extra='ignore')으로 미지 최상위 필드를 조용히 무시 — `residual_hist0ry` 오타 하나가 정체 감지를 무음으로 껐다. 문서화된 fail-closed 계약 위반. → 양 모델에 `extra="forbid"`.
- **정체 obligation 재발화**: escalation을 이행해도 residual이 계속 평평하면 스크립트가 같은 지시를 무한 반복 → `stagnation_escalated_at` 필드 신설, escalation 이후의 새 평탄 구간만 재트리거.
- **Part 2 목록 누락 4종**: SKILL.md의 audit-trail 목록에 Protocol dashboard, Goal+obstacle, Glossary updates, Restated approval check가 빠져 템플릿·Handoff 요구와 모순.
- **initial protocol.json 미명세**: 스크립트의 필수 필드(카운터들)와 Orientation의 생성 지시가 어긋나 첫 실행이 ValidationError가 되는 경로 → 초기 파일 전체 형태 명시.
- **interaction 회계 불완전**: sweep 질문·framing 확인·pressure follow-up의 예산 계산 규칙 부재 → "사용자를 중단시키면 1, pressure follow-up은 부모 스레드 소속으로 0" 원칙으로 전면 정의.
- **batch stranding**: 남은 batchable gap 1-2개를 영원히 붙들 수 있는 규칙 공백 → flush rule(critical-path 부재 시 3개 미만이라도 발송, pre-handoff checkpoint 전 필수 flush).
- **build contract 순환 독해**: handoff 안의 계약을 테스트해야 handoff가 열리는 닭-달걀 → draft→test→fold-back→finalize 시퀀스 명문화.
- **postmortem 어휘 낡음**: `answer-unpressured`가 "pressure는 전 답변 의무" 전제로 정의돼 있었음 → scoped pressure의 두 sub-case(트리거 발화 후 무시 vs 트리거 자체가 위험 신호를 놓침 — smart default·brain-dump claim 포함)로 재정의. 후자는 규칙 위반이 아니라 트리거/라우팅 확장 신호다.

기각 9건 중 대표: "Core Rule이 batching을 모른다"(critical-path 분기의 압축 서술로 판정), "lens에 미평가 상태가 없다"(provisional 결정 강제가 의도된 설계), "fresh-implementer test 표가 계약 8섹션 목록에 없다"(목록 직후 문장이 명시). skeptic 단계가 없었으면 이 9건의 오탐 수정이 실제 결함 13건 사이에 섞여 들어갔을 것이다.

## 의도적으로 하지 않은 것

- **MCQ 전면 삭제(agy의 삭제 권고)**: 채택하지 않았다. MCQ의 결함은 "증거 없이 선택지를 발명할 때"이므로, 삭제 대신 evidence-gated MCQ(dump/code/docs로 증거화된 option space에만 허용)로 원인을 겨냥했다. 저비용 응답이라는 MCQ의 장점은 유지된다.
- **MCP 서버로 상태 기계 이전(양 멤버의 1순위 권고)**: 채택하지 않았다. protocol.json + 스크립트는 같은 drift 문제를 플레인 파일로 풀고, 스킬의 "uv run 하나로 동작, 서버 프로세스 없음" 배포 모델을 지킨다. MCP는 강제력이 더 세지만(호출을 물리적으로 순서화) 설치 표면이 커진다 — 현재 판단으로는 비용이 이득을 넘는다.
- **protocol.json 자동 기록**: 카운터 갱신은 여전히 모델의 책임이다. 모델이 기록을 잊으면 스크립트는 낙관이 아니라 비관으로 실패한다(미기록 = 미이행 = blocker). 자동화하려면 대화 훅이 필요한데 그건 스킬 범위 밖.
- **postmortem 스킬 변경 없음**: handoff 구조가 바뀌었지만 postmortem은 spec 내용과 diff를 비교하지 섹션 구조에 의존하지 않는다. Build Contract는 오히려 비교 대상을 명확하게 만든다.

## 남은 아이디어 (미반영)

- **interaction 로그의 자동 검산**: transcript.md의 Q&A 수와 protocol.json의 `interactions_used`를 대조하는 스크립트 — 모델의 카운터 누락을 탐지할 수 있지만 transcript 파싱 규약이 필요하다.
- **batch 항목의 postmortem 추적**: 수락된 smart default가 escaped-requirement의 온상이 되는지 postmortem 통계로 검증 — batch 도입이 발견률을 깎는다면 되돌릴 근거가 된다.
- **stakes calibration의 명시적 사용자 확인**: BMAD처럼 인터뷰 시작 시 depth 추천을 사용자에게 1회 확인받는 상호작용 — 현재는 모델이 조용히 분류한다.
- **council 정기 재심**: 이번 리뷰 자체를 postmortem lessons처럼 주기화 — 스킬이 또 한 라운드 진화한 뒤 같은 질문으로 재소집해 결함 4건이 실제로 닫혔는지 외부 검증.
