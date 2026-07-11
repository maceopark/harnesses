# `ultimateinterview` 6개 렌즈의 충분성에 대한 인식론적·요구공학적 검토

**작성일:** 2026-07-10

**검토 범위:** `ultimateinterview`의 6개 렌즈, core discovery path, evidence model, readiness gate, postmortem closed loop

**방법:** 요구공학, 소프트웨어 아키텍처, 인식론, 인지과학, 사회·윤리, 프로토콜 설계, 로컬 포스트모템 실증 감사, 현 설계 방어의 8개 독립 검토와 교차 반론

## 결론

현재 6개 렌즈는 충분히 효과적이지만, “요구사항 공간을 완전히 분해하는 6개의 독립된 인식론”은 아니다.

> 빠진 핵심은 7번째 체크리스트라기보다, 무엇을 왜 안다고 믿는지, 누가 결정할 권한이 있는지, 현재 분석틀 자체가 무엇을 못 보게 했는지를 검증하는 메타 인식론이다.

## 현재의 6개 렌즈는 같은 종류의 6축이 아니다

| 현재 항목 | 실제 역할 |
| --- | --- |
| `viewpoint` | 누가 아는가, 누구에게 영향을 주는가 |
| `domain/state` | 무엇이 존재하고 어떻게 변하는가 |
| `goal/obstacle` | 왜 필요한가, 무엇이 막는가 |
| `misuse` | 어떻게 잘못되거나 악용되는가 |
| `quality` | 어느 환경에서 얼마나 잘 작동해야 하는가 |
| `controlled-language` | 발견된 요구사항을 어떻게 결정 가능한 문장으로 고정하는가 |

특히 `controlled-language`는 발견 렌즈라기보다 contract compiler 또는 명세 품질 게이트다. 반대로 Contextual Observation과 EventStorming은 핵심 발견 방법이지만 6개 렌즈 밖에 있다.

따라서 실제 스킬은 다음처럼 이해해야 정확하다.

```text
관찰·이벤트 흐름
+ 조건부 요구사항 렌즈
+ 증거 충돌·반증 절차
+ Build Contract compiler
+ fresh implementer·postmortem gate
```

요구공학 자체도 elicitation, modelling, agreement, communication, evolution을 서로 다른 활동으로 구분한다. 이들은 반복적으로 교차하지만 같은 종류의 “렌즈”는 아니다.

## 포스트모템이 보여주는 실제 실패 패턴

5개 todo CLI 포스트모템의 escape 14건을 분류하면 다음과 같다.

- `enumeration-miss`: 12건
- `synthesis-loss`: 2건
- 새 렌즈가 없어 trigger하지 못한 것으로 확인된 사례: 없음

예를 들어 misuse 렌즈를 실행하고도 빈 입력을 빠뜨렸고, domain/state 렌즈를 실행하고도 load-time 재검증, write interruption, schema evolution을 빠뜨렸다.

이는 가장 먼저 보강할 대상이 렌즈 수가 아니라 다음과 같은 **coverage algebra**임을 시사한다.

```text
operation × state
input-time × load-time
success × interruption/failure
normal value × boundary/degenerate value
version × migration direction
actor × handoff boundary
claim × counterexample
```

다만 현재 실험군은 거의 전부 단순 CLI다. 따라서 multi-stakeholder, distributed system, safety, architecture 영역에서 현재 렌즈가 충분하다는 증거로 사용할 수는 없다.

## 가장 근본적으로 빠진 것

### 1. 증거 채널과 인식론적 정당화의 구분

현재는 `from-code`, `from-docs`, `from-user` 같은 서로 다른 채널을 triangulation으로 센다. 그러나 채널이 다르다고 증거가 독립적인 것은 아니다.

- 문서가 동일한 사용자의 주장을 옮겼을 수 있다.
- 테스트와 코드가 같은 잘못된 명세에서 파생됐을 수 있다.
- 독립된 운영자 두 명의 증언은 모두 `from-user` 하나로 압축된다.
- AI가 작성한 checkpoint를 사용자가 “전부 맞음”으로 승인한 것은 독립된 corroboration이 아니다.

필요한 것은 가벼운 `ClaimEvidence` 계층이다.

```text
claim kind: observed fact | causal hypothesis | interpretation |
            normative decision | preference | forecast
source actor and competence
firsthand or derived
derived-from / independence group
time, environment, freshness
warrant: 왜 이 증거가 이 주장을 지지하는가
counterevidence / defeater
epistemic authority
decision authority
```

Triangulation은 단순한 채널 개수가 아니라 독립된 epistemic route와 evidence lineage를 기준으로 해야 한다.

### 2. 사실·원인·해석·결정을 동일하게 닫는 문제

현재 충돌 규칙은 사용자와 코드 또는 문서가 충돌하면 무엇이 governs인지 사용자에게 묻는다. 그러나 다음은 서로 다른 절차가 필요하다.

- production의 현재 동작은 관찰해야 한다.
- 장애 원인은 경쟁 가설을 시험해야 한다.
- 용어의 의미는 사례와 반례를 왕복하며 해석해야 한다.
- 원하는 정책은 정당한 결정권자가 선택해야 한다.

사용자가 factual claim을 선택한다고 그것이 사실이 되지는 않는다. 반대로 코드가 현재 그렇게 동작한다고 desired behavior가 되는 것도 아니다.

### 3. 분석틀 자체를 반증하는 장치의 부재

현재 postmortem은 escape를 반드시 기존 렌즈 중 하나에 귀속시킨다. 따라서 “기존 6개 중 어디에도 자연스럽게 속하지 않는다”는 결론을 낼 수 없다. 모든 anomaly를 기존 분류표에 강제로 넣으면, 6개가 충분하다는 결과가 구조적으로 재생산될 수 있다.

필요한 보강은 다음과 같다.

- `owning-frame: none`
- `failure-class: ontology-miss`
- 현재 ledger를 보지 않은 독립 생성자의 open-world sweep
- 서로 다른 도메인에서 같은 ontology-miss가 반복될 때만 새 렌즈 후보로 승격
- spec과 코드 모두에 나타나지 않은 negative-space requirement를 운영 로그, 지원 티켓, 실사용 결과로 추적

즉 single-loop의 “기존 렌즈를 더 잘 실행하자”뿐 아니라 double-loop의 “렌즈 분류 자체가 틀렸나?”가 필요하다.

## 추가 가치가 큰 분석틀

### 상시 discovery frame 후보: `interface/boundary`

가장 강하게 합의된 누락이다. `domain/state`가 엔터티와 생명주기를 모델링한다면, 이 frame은 세계와 소프트웨어의 책임 경계를 모델링한다.

```text
problem/world domain
machine boundary
shared phenomena
누가 통제하고 누가 관찰하는가
environment/domain assumptions
external dependency contract
data/control/time ownership
handoff와 composition point
mixed-version·migration·rollback state
first valid failure boundary와 terminal evidence
```

Zave와 Jackson의 요구공학은 세계의 가정 `W`, 기계 명세 `S`, 요구 `R` 사이의 만족 관계를 핵심으로 본다. “우리 코드가 실제로 무엇을 통제할 수 있는가?”가 빠지면 명확한 요구사항도 구현 불가능하거나 잘못된 책임 배분이 된다.

### 기존 `viewpoint`의 확장: knowledge·power·harm

현재 viewpoint는 역할별 goal, constraint, failure fear에는 강하지만 다음이 부족하다.

- 직접 사용자, 간접 피해자, 비자발적 대상
- 실제 경험자인가, 대리인인가, AI 시뮬레이션인가
- 누가 발언권·거부권·예산권을 갖는가
- 누가 실패 비용을 부담하는가
- 어떤 조직적 인센티브가 진술을 왜곡하는가
- dissent와 appeal/redress 경로

요구사항의 구현 가능성과 사회적 정당성은 별개의 gate다. Requester의 확인이 다른 이해관계자의 경험이나 권리를 대리 승인해서는 안 된다.

### 조건부 profile로 둘 것

다음은 중요하지만 모든 인터뷰의 전역 렌즈로 추가하면 과도한 의례와 false assurance를 만들 수 있다.

- `architecture/decision`: 대안, architectural forces, quality tradeoff, 비용, lock-in, 가역성
- `socio-technical work`: 실제 작업의 cue, interruption, workaround, coordination artifact, handoff
- `hazard/control`: 정상 구성요소 간 unsafe interaction, feedback failure, human/automation control
- `assurance case`: claim–argument–evidence와 defeater를 연결하는 고위험 ENDGAME profile

특히 STPA식 hazard 분석은 공격자나 오사용자가 없어도 발생하는 시스템 사고를 다루므로 misuse와 같지 않다. 그러나 고위험 자동화, 보안, 개인정보, 재무, 비가역 손실에서만 켜는 편이 적절하다.

## 권장 구조

### 1. Discovery frames

```text
purpose/value
work/authority
world/state
interface/boundary
harm/failure
quality/operability
```

### 2. Evidence & critique operators

```text
contextual observation
scenario/EventStorming
claim provenance and independence
competing hypotheses
reverse evidence
premortem/contrarian
falsification checkpoint
```

### 3. Contract compiler

```text
controlled language
traceability
decision boundaries
verification predicates
Build Contract
```

### 4. Readiness & learning

```text
independent sweep
fresh implementer
real-surface verification
postmortem
ontology-miss review
```

이 구조는 렌즈 수를 크게 늘리지 않으면서 현재의 범주 혼합을 해소한다.

## 개선 우선순위

1. `channel diversity ≠ evidence independence`를 수정한다.
2. claim kind와 epistemic/decision authority를 분리한다.
3. postmortem에 `ontology-miss/no-owner`를 허용한다.
4. `controlled-language`를 discovery lens가 아니라 compiler로 재분류한다.
5. `interface/boundary`를 명시적인 discovery frame으로 추가한다.
6. viewpoint를 power, representation, failure exposure까지 확장한다.
7. architecture, hazard, assurance는 조건부 profile로 실험한다.
8. 새로운 전역 렌즈는 여러 도메인의 독립 postmortem에서 irreducible miss가 반복될 때만 승격한다.

## 신규 렌즈 승격 기준

새로운 전역 렌즈는 다음 조건을 모두 만족할 때만 추가하는 것이 안전하다.

1. 서로 다른 두 도메인에서 독립적인 `ontology-miss/no-owner`가 발생했거나, 하나의 critical incident가 있다.
2. 기존 프로토콜을 완전히 실행했으며 trigger, enumeration, scoring, pressure, synthesis 문제로 설명되지 않는다.
3. 기존 artifact에 정보 손실 없이 담을 수 없는 독립적인 evidence transformation과 typed artifact가 있다.
4. 질문 전에 관찰 가능한 trigger, reverse-evidence, stop condition이 있다.
5. fresh implementer가 weight-3/5 behavior, target surface, rollout/recovery, verification 또는 decision boundary를 실제로 다르게 만든다.
6. 중복 gap, 추가 interaction, false-trigger, incomplete artifact 비용보다 고유한 발견 가치가 크다.
7. protocol enum, artifact schema, scripts, audit checklist, handoff template, regression fixture, postmortem attribution이 함께 변경된다.

요약하면 다음과 같다.

> 현재 6개는 좋은 첫 번째 위험 스캔이지만 충분조건은 아니다. 놓친 가장 중요한 분석틀은 특정 철학 학파 하나가 아니라, 증거의 정당화와 독립성, 지식·결정 권한, 세계–기계 경계, 그리고 분석틀 자체를 반증하는 open-world 학습 루프다.

## 참고 문헌

- Bashar Nuseibeh and Steve Easterbrook, [Requirements Engineering: A Roadmap](https://www0.cs.ucl.ac.uk/staff/A.Finkelstein/fose/fdnuseibeh.pdf)
- Pamela Zave, [Foundations of Requirements Engineering](https://www.pamelazave.com/fre.html)
- W3C, [PROV Overview](https://www.w3.org/TR/prov-overview/)
- Stanford Encyclopedia of Philosophy, [Epistemological Problems of Testimony](https://plato.stanford.edu/entries/testimony-episprob/)
- Batya Friedman, Peter Kahn, and Alan Borning, [Value Sensitive Design and Information Systems](https://onlinelibrary.wiley.com/doi/pdf/10.1002/9780470281819.ch4)
- Carnegie Mellon Software Engineering Institute, [Quality Attribute Workshops](https://www.sei.cmu.edu/library/quality-attribute-workshops-qaws-third-edition/)
- Nancy Leveson and John Thomas, [STPA Handbook](https://psas.scripts.mit.edu/home/get_file.php?name=STPA_handbook.pdf)

## 로컬 근거

- `.agents/skills/ultimateinterview/SKILL.md`
- `.agents/skills/ultimateinterview/references/lenses.md`
- `.agents/skills/ultimateinterview/references/orientation.md`
- `.agents/skills/ultimateinterview/references/interview-loop.md`
- `.agents/skills/ultimateinterview/references/handoff-sequence.md`
- `.ultimateinterview/todo-cli-app*/postmortem.md`
- `.ultimateinterview/ultrainterview-refine/findings.md`
