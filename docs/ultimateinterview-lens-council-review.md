# ultimateinterview 6렌즈 분해 — LLM Council 리뷰 (1페이지)

**날짜:** 2026-07-10 · **위원:** 인식론 / SW설계·요구공학 / 레드팀 (각 architect 세션) · **판정:** 만장일치 **WATCH**
**질문:** 6개 렌즈(`viewpoint`, `domain/state`, `goal/obstacle`, `misuse`, `quality`, `controlled-language`) + 상시 core-path로 요구사항을 분해하는 것이 충분히 효과적인가? 놓친 분석틀은?

## 한 줄 판정
6렌즈는 *개별 요구사항 정련*에는 동급 최고이나, "충분한가"는 **범주 오류**다. 렌즈 분해는 **자기가 그린 지도 위의 불확실성만** 점수화한다 → 지도 밖은 원리적으로 `residual=0`으로 보인다. 정확히 말하면 **"충분히 효과적"이 아니라 "알려진 미지(known-unknown)에 한해 효과적"**이다.

## 만장일치 헤드라인 — 세 위원이 독립적으로 같은 곳을 찍음
> **요구사항 *간* 상호작용을 원리적으로 못 본다. 근본 원인은 `residual = Σ(impact × ambiguity)`라는 가법적 지표다.**

- 가법 지표 = "전체 = 부분의 합" 가정. 개별 점수 0인 두 요구가 결합 시 모순을 만들어도 residual은 0 → `handoff_ready` (false-green).
- 열거되지 않은 불확실성은 지표에서 0 — 플래그되는 게 아니라 **보이지 않음.**
- **벤치마크가 실증:** 3-arm에서 세 방식 모두 같은 `undefined-predicate`로 샜다. 이는 '스키마 × 입력검증 × 로드-시-신뢰'의 **상호작용에서 창발**하는 속성 → 어느 단일 렌즈도 소유 안 함. 병목이 *분해 카탈로그와 직교*한다는 직접 증거. Arm C는 `residual=0`으로 handoff에 도달하고도 escape 2건을 품고 있었다.

## 놓친 분석틀 (중요도 순)
| 순위 | 분석틀 | 이론 | 왜 새는가 (한 줄) |
|---|---|---|---|
| **P0** | 요구사항 상호작용/충돌 + 개념적 통합성 | RIM, Brooks, Alexander | 가법 residual이 항목을 독립 처리; N² 상호작용 항 부재. 상호작용을 "질문 분리 이유"로만 취급 |
| **P0** | unknown-unknown 생성 부재 (Cynefin complex) | 프레임 문제/Kuhn, Snowden | 닫힌 어휘는 known-unknown만 소진; 전면 pre-action → probe-sense-respond 없음. checkpoint·contrarian·sweep은 *부정*이지 새 차원의 *생성(abduction)*이 아님 |
| **P1** | 가치/우선순위/전략 | Kano, CoD, MoSCoW, Wardley, ToC | `impact_weight`는 '모호도 오해의 영향'이지 '가치'가 아님(직교). commodity를 아름답게 de-risk하며 저가치임을 표면화 못 함 |
| **P1** | data-flow / 정보 lineage | DFD, data lineage | domain/state=단일 엔티티, EventStorming=이벤트 흐름. datum이 신뢰/보존 경계를 횡단(PII→export→외부)하는 경로 추적 렌즈 없음 |
| **P1** | systemic 안전/신뢰성 | STPA, FMEA, Fault Tree, STRIDE completeness | misuse는 *적대적 행위자 목표* 구동 → 악의 없는 창발 실패(ack 유실→재발행→중복 청구)에 눈멂 |
| **P1** | Gettier 취약성 + 반증 오라클 | JTB/Gettier, Popper 반증 독립성 | 삼각검증이 '채널 구별'만 카운트 → 스테일 코드+사용자 오기억(둘 다 status quo)이 우연 일치 시 거짓을 삼각검증. 반증 오라클이 대개 '같은 사용자' |
| **P2** | i*/Tropos 의존·soft goal · Jackson Problem Frames · 가정 생애주기(ABP)+ADR · from-code의 is/ought 태그 | — | 위 항목들의 하위 사례 |

## 가장 깊은 층위 ("안다는 것")
Cynefin *complicated*(전문성으로 분해 가능) 영역에서는 최상급. 그러나 두 **원리적**(구조적) 벽: ① 닫힌 표상 어휘는 자기 밖 요구 범주를 생성 불가 → unknown-unknown을 '사용자가 우연히 정정해주길' 하는 운에 의존. ② 전면 pre-action 설계는 "만들어봐야 아는" complex 요구의 **인식적 지위 자체를 표상 못 함.**

## 단 하나만 보강한다면 — 새 렌즈가 아니다
**독립 구성 발산 프로브(independent-construction divergence probe).** full-depth handoff 직전, 모호한 코어를 **2개 독립 컨텍스트**가 Part 1만으로 구현/스텁하고 **행위 차이**를 측정 → 대시보드에 상시 **비-0 "비열거 잔차"**로 표시.
- **분해가 아님** → 렌즈 증식/트리거 불완전성/예산 폭발 회피. 독립 영토에 부딪혀 **반증**(Popper적 수를 제대로 둠).
- 상호작용·잠재 니즈·미지 실패 부류·거짓 확신을 **동시에** 잡음. `residual=0=안전` 착시를 구조적으로 깸(경험적 오차막대 주입).
- 스킬이 **이미 도구 소유** — blind-rebuild 연구·fresh-implementer test가 있으나 런타임 메트릭으로 안 씀.

## 하지 말 것
- **"렌즈를 더 추가하라"는 처방은 악화시킴.** 새 렌즈는 (a) 트리거-게이트되어 같은 맹점 공유 or (b) 상시 켜져 모든 인터뷰에 과세. 공짜 점심 없음.
- lessons가 todo-CLI 코퍼스에 과적합(분산 일관성·timezone·규제 보존엔 눈멂). **지표 게이밍(Goodhart) 경계.**
- residual=0 / green-gate를 "충분히 안다"의 증거로 제시하지 말 것 — 산문 disclaimer는 헤드라인 메트릭을 못 이긴다.

## 후속
- **P0 편입은 load-bearing 변경**(가법 residual 수정) → `ralplan` 합의 계획으로 진행 권장.
- 전체 리포트: `agent://43-Epistemology-Member`, `agent://44-DesignTheory-Member`, `agent://45-RedTeam-Member`.
