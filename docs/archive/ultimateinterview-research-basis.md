# Ultrainterview Research Basis

Date: 2026-07-07

이 문서는 `ultimateinterview`와 postmortem closed loop 설계가 "더 좋은 스펙을 만든다"는 목표에 대해 연구적으로 타당한지 검토한 요약이다. 대상 설계는 다음을 포함한다.

- 인터뷰를 통해 구현 가능한 spec을 만든다.
- code fact와 human decision을 분리한다.
- assumption, unresolved gap, requirement source를 ledger에 남긴다.
- 구현 후 postmortem으로 `spec_gap`, `implementation_deviation`, `evaluation_uncertainty`, `execution_process_gap`, `legitimate_spec_evolution`을 분리한다.
- semantic evaluator와 multi-model consensus를 보조적으로 사용한다.

## Executive Summary

접근 방향은 타당하다. 요구사항공학 연구와 표준은 오래전부터 좋은 스펙의 핵심을 `unambiguous`, `complete`, `verifiable`, `traceable`, rationale/assumption 명시로 봐 왔다. `ultimateinterview + evidence ledger + postmortem` 구조는 이 축들과 잘 맞는다.

다만 "모든 요청에 multi-agent question consensus + multi-model semantic judge + golden-set promotion loop"를 기본 적용하는 것은 연구 근거보다 앞서간다. 연구가 강하게 지지하는 것은 더 좁다.

- 좋은 질문을 고른다.
- 모호한 자연어 요구사항을 구조화한다.
- 요구사항과 구현/검증 증거를 trace한다.
- 실패 후 원인을 학습 루프로 되돌린다.

따라서 큰 비전은 맞지만, 기본 경로는 작게 두고 고위험/고불확실성에서만 확장하는 설계가 가장 방어 가능하다.

## Key Papers And Sources

### Requirements Engineering: A Roadmap

Source: Bashar Nuseibeh and Steve Easterbrook, ICSE 2000  
URL: https://www.cs.toronto.edu/~sme/papers/2000/ICSE2000.pdf

핵심 내용:

- Requirements Engineering은 stakeholder needs를 발견하고, 분석/소통/구현 가능한 형태로 문서화하는 활동이다.
- stakeholder goals는 암묵적이거나 충돌할 수 있다.
- validation, negotiation, ambiguity, traceability가 RE의 핵심 문제다.
- 요구사항은 refutable해야 하며, vague한 요구사항은 validation이 어렵다.

`ultimateinterview` 관련성:

- code fact와 human decision을 분리해야 한다.
- ambiguity ledger와 verification surface를 두는 방향이 타당하다.
- 인터뷰는 단순 문답이 아니라 불확실성 감소 과정이어야 한다.

### Identifying And Measuring Quality In A Software Requirements Specification

Source: Alan Davis et al., 1993  
URL: https://ieeexplore.ieee.org/document/263792/  
Accessible PDF mirror: https://git.rehounou.ca/remi/MDAF/raw/commit/89bf06da6ccb27be0e4282f24822de3dbaa8479f/References/F2020_References/Identifying%20and%20measuring%20quality%20in%20a%20software%20requirements%20specification.pdf

핵심 내용:

- SRS 품질 속성으로 unambiguous, complete, correct, understandable, verifiable, internally/externally consistent, achievable, concise, design independent, traceable, modifiable 등을 다룬다.
- 좋은 스펙은 단순히 길거나 자세한 문서가 아니라 측정 가능한 품질 속성을 가진 문서다.

`ultimateinterview` 관련성:

- "좋은 스펙"을 개선 대상으로 삼으려면 평가 기준이 필요하다.
- `ultimateinterview`의 출력은 intent뿐 아니라 verifiability, traceability, assumption, right level of detail을 포함해야 한다.

### An Analysis Of The Requirements Traceability Problem

Source: Orlena C. Z. Gotel and Anthony C. W. Finkelstein, 1994  
URL: https://discovery.ucl.ac.uk/749/1/2.2_rtprob.pdf

핵심 내용:

- pre-RS traceability와 post-RS traceability를 구분한다.
- 많은 traceability 문제는 요구사항이 SRS에 들어가기 전의 출처, rationale, stakeholder context가 약해서 발생한다.
- 연구는 100명 이상의 practitioner를 포함한 empirical study, focus group, questionnaire, interview, observation에 기반한다.

`ultimateinterview` 관련성:

- answer provenance, requirement source, rationale, assumption을 남기는 evidence ledger는 pre-RS traceability 문제에 대한 현대적 대응이다.
- 구현 후 drift를 분석하려면 requirement가 어디서 왔는지 추적 가능해야 한다.

### NASA: How To Write A Good Requirement

Source: NASA Systems Engineering Handbook appendix  
URL: https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/

핵심 내용:

- 좋은 requirement는 clear and unambiguous해야 한다.
- assumptions는 명시되어야 하고 baselining 전에 확인되어야 한다.
- requirement는 test, demonstration, inspection, analysis로 검증 가능해야 한다.
- vague/unverifiable words를 피해야 한다.
- requirement는 higher-level requirement나 mission/system scope와 traceable해야 한다.
- rationale에는 assumptions가 포함되어야 한다.

`ultimateinterview` 관련성:

- final handoff에 assumptions, unresolved deferred risks, verification expectations를 넣는 설계가 타당하다.
- "질문하지 않고 assumption으로 둔 것"을 명시하는 규칙은 NASA식 requirement validation과 잘 맞는다.

### INCOSE Guide To Writing Requirements

Source: INCOSE Requirements Working Group summary sheet  
URL: https://www.incose.org/docs/default-source/working-groups/requirements-wg/guidetowritingrequirements/incose_rwg_gtwr_v4_summary_sheet.pdf

핵심 내용:

- requirement는 unambiguous, complete, feasible, verifiable, traceable해야 한다.
- requirement set은 필요한 capabilities, constraints, interactions, safety, security, resilience, quality factors를 충분히 설명해야 한다.
- 최소 attribute로 rationale, trace to parent, trace to source, owner, verification status, validation status, priority 등을 둔다.

`ultimateinterview` 관련성:

- requirement source와 rationale을 ledger에 남기는 설계가 직접 지지된다.
- verification status와 validation status를 postmortem에서 확인하는 것도 자연스럽다.

### Rapid Quality Assurance With Requirements Smells

Source: H. Femmer, D. Mendez Fernandez, S. Wagner, S. Eder  
URL: https://arxiv.org/abs/1611.08847

핵심 내용:

- code smell 개념을 requirements engineering에 적용한다.
- lightweight static requirements analysis로 요구사항 품질 문제를 빠르게 찾는다.
- automatic detection은 평균 precision 59%, recall 82%였고 variation이 컸다.
- smell detection은 traditional review나 team discussion의 보조 수단으로 유용하다.

`ultimateinterview` 관련성:

- lightweight quality gate는 타당하다.
- 자동 judge/checker는 truth source가 아니라 review aid로 사용해야 한다.

### On Systematically Building A Controlled Natural Language For Functional Requirements

Source: Alvaro Veizaga, Mauricio Alferez, Damiano Torre, Mehrdad Sabetzadeh, Lionel Briand  
URL: https://arxiv.org/abs/2005.01355

핵심 내용:

- Natural language requirement는 vagueness, ambiguity, incompleteness에 취약하다.
- Controlled Natural Language는 자연어의 유연성과 formal language의 엄밀성 사이의 절충이다.
- 금융 도메인 15개 SRS, 3215개 requirement statement를 기반으로 Rimay를 만들었다.
- unseen SRS의 requirement 중 평균 88%를 표현할 수 있었다.

`ultimateinterview` 관련성:

- EARS나 controlled-language style을 final spec/handoff에 조건부로 적용하는 것은 타당하다.
- 다만 모든 요구사항을 formal language로 밀어붙이는 것은 과할 수 있다.

### A Methodology For The Selection Of Requirement Elicitation Techniques

Source: Saurabh Tiwari and Santosh Singh Rathore  
URL: https://arxiv.org/abs/1709.08481

핵심 내용:

- elicitation technique를 모두 사용하는 것이 아니라 context에 따라 subset을 선택해야 한다.
- project, people, process dimension이 technique 선택에 영향을 준다.
- case study로 적용 가능성을 보인다.

`ultimateinterview` 관련성:

- `ultimateinterview`는 모든 lens를 항상 실행하면 안 된다.
- risk-routed conditional lens가 더 연구 근거에 맞다.

### Requirements Elicitation Follow-Up Question Generation

Source: Yuchen Shen, Anmol Singhal, Travis Breaux  
URL: https://arxiv.org/abs/2507.02858

핵심 내용:

- GPT-4o로 requirements elicitation interview의 follow-up question을 생성했다.
- human-authored question과 controlled experiment로 비교했다.
- LLM-generated questions는 clarity, relevancy, informativeness에서 사람 질문보다 나쁘지 않았다.
- common interviewer mistake types로 guide하면 LLM 질문이 human-authored question보다 더 좋았다.

`ultimateinterview` 관련성:

- LLM을 question generator/reviewer로 쓰는 방향은 타당하다.
- 다만 9개 subagent role을 매 라운드 항상 돌려야 한다는 근거는 아니다.
- 더 실용적인 해석은 question quality rubric과 mistake-type guidance를 쓰는 것이다.

### Using LLMs In Software Requirements Specifications

Source: Madhava Krishna, Bhagesh Gaur, Arsh Verma, Pankaj Jalote  
URL: https://arxiv.org/abs/2404.17842

핵심 내용:

- GPT-4와 CodeLlama가 SRS를 생성하고 검토하는 능력을 평가했다.
- GPT-4는 entry-level software engineer 수준의 SRS draft를 만들 수 있었다.
- GPT-4는 requirements document의 문제를 식별하고 수정 피드백을 줄 수 있었다.
- LLM은 SRS generation, validation, rectification에서 생산성 향상을 줄 수 있다.

`ultimateinterview` 관련성:

- LLM은 spec generation/review에 유용하다.
- 하지만 expert replacement보다는 productivity assistant나 reviewer에 가깝다.

### Large Language Models For Requirements Engineering: A Systematic Literature Review

Source: Mohammad Amin Zadenoori, Jacek Dabrowski, Waad Alhoshan, Liping Zhao, Alessio Ferrari  
URL: https://arxiv.org/abs/2509.11446

핵심 내용:

- 2023-2024년 74개 primary studies를 분석한 systematic literature review다.
- LLM4RE 연구는 requirements elicitation과 validation에 많이 집중되어 있다.
- 대부분 GPT-based model과 zero-shot/few-shot prompting에 의존한다.
- 산업 setting과 complex workflow 통합은 제한적이다.

`ultimateinterview` 관련성:

- LLM 기반 RE 도구의 방향성은 유망하다.
- 하지만 full closed-loop workflow는 아직 충분히 검증된 산업 표준이 아니다.
- 실제 적용은 MVP와 measurement를 통해 점진적으로 해야 한다.

### Judging LLM-As-A-Judge With MT-Bench And Chatbot Arena

Source: Lianmin Zheng et al.  
URL: https://arxiv.org/abs/2306.05685

핵심 내용:

- strong LLM judge는 human preference와 80% 이상 agreement를 보일 수 있다.
- 이는 human-human agreement 수준과 비슷하다.
- 하지만 position bias, verbosity bias, self-enhancement bias, limited reasoning ability가 있다.
- LLM-as-a-judge는 scalable/explainable approximation이지 truth source가 아니다.

`ultimateinterview` 관련성:

- semantic evaluator는 drift와 AC compliance를 평가하는 보조 judge로는 타당하다.
- disagreement는 majority vote 대상이 아니라 uncertainty signal로 다루는 것이 맞다.

## Themes And Consensus

### 좋은 스펙은 "자세한 문서"가 아니다

연구와 표준은 공통적으로 좋은 스펙을 다음처럼 본다.

- 다른 구현자가 materially same thing을 만들 수 있다.
- 검증자가 pass/fail을 판단할 수 있다.
- 요구사항의 source, rationale, assumption이 추적 가능하다.
- scope, constraints, non-goals가 구현 분기를 줄인다.

따라서 `ultimateinterview`의 목표는 긴 handoff가 아니라 구현 분기와 검증 불확실성을 줄이는 스펙이어야 한다.

### 인터뷰는 불확실성 감소 과정이다

Requirements elicitation은 사용자의 요구를 단순 수집하는 일이 아니다. stakeholder need는 암묵적이고, 충돌하고, 구현자가 다르게 해석할 수 있다.

따라서 좋은 질문은 "흥미로운 질문"이 아니라 "답을 들으면 구현 분기가 가장 많이 사라지는 질문"이다.

이 관점은 `ultimateinterview`의 ambiguity ledger, one-highest-impact-question-at-a-time, code fact vs human decision routing과 잘 맞는다.

### Ledger는 강한 아이디어다

Pre-RS traceability 문제를 생각하면, final spec만으로는 충분하지 않다. 다음 정보가 필요하다.

- requirement source
- user answer provenance
- assumption
- unresolved gap
- rationale
- verification expectation
- implementation decision
- criteria revision history

이 정보가 있어야 postmortem에서 "스펙이 부족했는가, 구현이 벗어났는가, 평가 증거가 부족했는가"를 분리할 수 있다.

### Postmortem loop는 타당하지만 자동 학습처럼 포장하면 안 된다

Postmortem의 가치는 실패 원인을 attribution하는 데 있다.

- `spec_gap`: 스펙이 구현 판단을 제한하지 못함.
- `implementation_deviation`: 스펙은 충분했지만 구현이 벗어남.
- `evaluation_uncertainty`: 판단 증거가 부족하거나 judge가 불일치함.
- `execution_process_gap`: ledger/evidence가 부족해 실행 복원이 어려움.
- `legitimate_spec_evolution`: 사용자 입력이나 새 발견으로 정당하게 스펙이 바뀜.

이 분류가 가능해지면 인터뷰 스킬을 개선할 수 있다. 하지만 LLM judge가 자동으로 "진짜 원인"을 확정한다고 보면 안 된다.

## Risks And Open Questions

### Multi-agent question consensus의 직접 근거는 약하다

LLM이 requirements follow-up question 생성에 도움 된다는 연구는 있다. 하지만 9개 subagent role을 매 라운드 돌리면 스펙 품질이 좋아진다는 직접 근거는 부족하다.

더 방어 가능한 설계:

- 기본은 single interviewer + structured rubric.
- 고위험/고불확실성에서만 subagent review.
- subagent role은 3개 정도로 축소한다: implementation divergence, QA/evidence, risk/human decision.

### LLM-as-judge는 truth source가 아니다

LLM judge는 scalable evaluator로 유용하지만 bias와 불안정성이 있다.

권장 운영:

- deterministic checks를 먼저 한다.
- semantic judge는 cited evidence와 missing evidence를 강제한다.
- disagreement는 uncertainty signal로 본다.
- high-risk 또는 promotion 후보에만 multi-model consensus를 쓴다.
- golden set으로 calibration한다.

### 모든 task에 full protocol을 적용하면 ceremony가 된다

요구사항공학 연구는 context-sensitive elicitation을 지지한다. 따라서 모든 요청에 full interview, 모든 lens, 모든 judge를 적용하는 것은 과하다.

좋은 기본값은 risk-routed이다.

## Recommended MVP

### Always-On Core

항상 켜야 할 것은 작아야 한다.

- intent
- desired outcome
- in scope / out of scope
- non-goals
- decision boundaries
- code fact vs human decision
- assumptions
- unresolved gaps
- acceptance criteria
- verification surface
- requirement source/provenance

### Always Record

최소 ledger/event는 다음 정도로 시작한다.

```json
{
  "kind": "implementation_decision",
  "decision": "...",
  "specCitation": "...",
  "reason": "...",
  "alternatives": ["..."],
  "implementationImpact": "...",
  "postmortemClassCandidate": "spec_gap | implementation_deviation | evaluation_uncertainty"
}
```

```json
{
  "kind": "assumption",
  "assumption": "...",
  "source": "agent | user | code | docs",
  "risk": "low | medium | high",
  "reversible": true,
  "wouldChangeImplementation": false
}
```

```json
{
  "kind": "criteria_revision",
  "originalCriterion": "...",
  "revisedCriterion": "...",
  "originalSpecCitation": "...",
  "rationale": "...",
  "trigger": "user_input | code_discovery | blocker | evaluation_feedback"
}
```

### Conditional Lenses

조건부로만 켜야 한다.

| Lens | Trigger |
| --- | --- |
| domain/state | identity, lifecycle, state transition, invariant, ownership, consistency, concurrency |
| viewpoint | support/admin/security/finance/compliance/operator/API 관점이 갈릴 수 있음 |
| misuse | auth, privacy, money, destructive action, public input, fraud, irreversible write |
| quality | fast, reliable, scalable, safe, compatible, observable 같은 말이 구현을 바꿈 |
| controlled-language | acceptance criteria가 testable하지 않거나 trigger/condition/response가 모호함 |

### Postmortem

실패 후에는 다음 순서로 분석한다.

1. ledger를 읽어 실행을 복원한다.
2. criteria별 evidence 상태를 확인한다.
3. implementation decision/assumption을 spec gap 후보로 추출한다.
4. semantic evaluator로 original intent/AC 대비 drift를 평가한다.
5. 실패 원인을 분류한다.
6. 과거 spec을 수정하지 않고 interview skill patch proposal을 만든다.

### Escalation Only

다음은 기본값이 아니라 escalation이어야 한다.

- multi-agent question review
- fresh-context gate
- multi-model semantic judge
- golden set benchmark
- skill promotion/rejection loop

Escalation trigger:

- high-risk domain
- security/privacy/data/schema/irreversible write
- external integration
- ambiguity score가 높음
- two implementers would materially diverge
- spec이 다른 agent/team의 implementation seed가 됨
- semantic judge uncertainty 또는 disagreement가 큼

## Bottom Line

`ultimateinterview`의 연구적으로 방어 가능한 핵심 가설은 다음이다.

좋은 스펙은 implementation drift를 완전히 없애지 않는다. 대신 drift가 생겼을 때 그것이 스펙의 빈틈인지, 구현자의 이탈인지, 평가 증거 부족인지 구분 가능하게 만든다.

이 구분 가능성이 `ultimateinterview`와 postmortem closed loop 설계의 진짜 가치다.

따라서 최종 판단은 다음과 같다.

- 방향은 타당하다.
- evidence ledger와 postmortem attribution은 특히 강하다.
- LLM question generation과 semantic evaluation은 유망하지만 보조 장치로 둬야 한다.
- multi-agent/multi-model closed loop는 vision으로는 좋지만 MVP 기본 경로로는 과하다.
- best design은 small always-on core + risk-routed conditional escalation이다.

## Sources

- Nuseibeh and Easterbrook, Requirements Engineering: A Roadmap: https://www.cs.toronto.edu/~sme/papers/2000/ICSE2000.pdf
- Davis et al., Identifying and Measuring Quality in a Software Requirements Specification: https://ieeexplore.ieee.org/document/263792/
- Gotel and Finkelstein, An Analysis of the Requirements Traceability Problem: https://discovery.ucl.ac.uk/749/1/2.2_rtprob.pdf
- NASA, How to Write a Good Requirement: https://www.nasa.gov/reference/appendix-c-how-to-write-a-good-requirement/
- INCOSE Guide to Writing Requirements summary sheet: https://www.incose.org/docs/default-source/working-groups/requirements-wg/guidetowritingrequirements/incose_rwg_gtwr_v4_summary_sheet.pdf
- Femmer et al., Rapid Quality Assurance with Requirements Smells: https://arxiv.org/abs/1611.08847
- Veizaga et al., On Systematically Building a Controlled Natural Language for Functional Requirements: https://arxiv.org/abs/2005.01355
- Tiwari and Rathore, A Methodology for the Selection of Requirement Elicitation Techniques: https://arxiv.org/abs/1709.08481
- Shen, Singhal, and Breaux, Requirements Elicitation Follow-Up Question Generation: https://arxiv.org/abs/2507.02858
- Krishna et al., Using LLMs in Software Requirements Specifications: https://arxiv.org/abs/2404.17842
- Zadenoori et al., Large Language Models for Requirements Engineering: https://arxiv.org/abs/2509.11446
- Zheng et al., Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena: https://arxiv.org/abs/2306.05685

## Rerun Inputs

```yaml
workflow: firecrawl-research-papers
topic: research basis for LLM-assisted requirements elicitation, better software specifications, traceability ledgers, semantic evaluation, and postmortem closed loops
target_count: 12
output: markdown brief
date: 2026-07-07
```
