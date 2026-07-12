# ULW-Research Synthesis: 암호학과 Zero Trust에서 ultimateinterview가 배울 수 있는 것

Research axes: 31 · Research waves: 3 (expansion 2회) · Unique URLs observed: 262 · Historical local baseline: 666 tests + bypass probes (2026-07-10) · Current v1 rebaseline: 13 focused integration tests (2026-07-11)

## Executive summary

결론부터 말하면, `ultimateinterview`를 “암호학적 증명 시스템”으로 만드는 것은 불가능하고 그렇게 표현해서도 안 된다. 암호학이 불신 가능한 prover로부터 믿을 만한 판정을 얻는 이유는 주장 공간, witness relation, verifier predicate, adversary, 확률 경계가 수학적으로 고정되어 있기 때문이다. 자연어 요구사항 인터뷰에는 이런 조건이 없다. 따라서 가져올 수 있는 것은 **보증 자체가 아니라 보증을 가능하게 하는 통제 구조**다: 주장을 고정하고, 반례를 독립적으로 선택하고, 판정 조건을 명시하고, 증거의 출처·시점·파생관계를 기록하고, 알려진 미해결 항목이 있으면 다음 상태로 넘어가지 못하게 하는 구조다. [Source 1][Source 2][Source 3]

가장 좋은 목표 표현은 다음과 같다.

> 이 절차는 기록된 근거에 따라 요구사항의 인수 가능성을 판정한다. 통과는 해당 범위·가정·환경·시점에서 구현 준비 조건을 만족했다는 뜻이며, 주장이 전역적으로 참이거나 완전하거나 독립적으로 입증됐거나 지식으로 추출 가능하다는 뜻은 아니다.

2026-07-11의 committed v1은 좋은 출발점을 더 강화했다. typed evidence와 causal lineage, material-revision invalidation, 재컴파일되는 `build-contract.json` sidecar, open-world/probe/checkpoint 의무, fresh-implementer test, blocker-based readiness가 실제 composite gate에 들어갔다. 그러나 실행 반례는 더 강한 주장을 막는다. 같은 actor가 서로 다른 `independence_group` 문자열을 붙이면 두 독립 그룹으로 셀 수 있고, 2000년 관찰을 `freshness=current`로 선언해도 통과하며, 존재하지 않는 pytest 경로도 “명령 head가 존재한다”는 이유로 verification declaration을 통과한다. ID가 문서 어디엔가 등장하기만 해도 실제 subcase가 빠진 synthesis-loss를 기계적으로 검출하지 못한다. 즉 현재 구현은 더 강해진 **ABI·구조/process-policy floor**이지, 인증된 provenance·실제 독립성·의미 보존·검증 실행의 증명은 아니다. [Source 4][Source 15][Source 17]

따라서 가장 적용 가치가 큰 변화는 “질문을 더 많이 하는 것”이 아니다. 첫째, 증거 레코드의 중요 분류를 claimant 입력이 아니라 verifier가 provenance/dependency policy로 계산하게 한다. 둘째, ABI/trace/property/adequacy/stakeholder의 다섯 판정을 하나의 `ready`에 합치지 않는다. 셋째, reflection/debate/다중 에이전트는 후보와 반례 생성에 쓰고, settlement는 claim-bound source, 실행 가능한 checker, 또는 명시적 human authority로만 한다. 넷째, handoff 이후의 delivery·dispatch·runtime PEP는 `ultimateinterview`가 실행 루프를 소유해서 구현할 기능이 아니라, BuildContract가 downstream harness에 요구하는 **소비자 통합 계약**으로 둔다. 스킬의 제품 경계는 canonical interview state, BuildContract, readiness policy까지다. [Source 5][Source 6][Source 7][Source 8][Source 16]

## 1. 암호학에서 가져올 것과 버릴 것

### 가져올 것: protocol discipline

| 암호학의 구조 | 안전한 적용 | 보존되는 것 | 잃는 보증 |
|---|---|---|---|
| statement/witness relation | 특정 REQ에 대해 실행 가능한 evidence predicate를 정의 | 그 predicate 범위의 재현 가능한 판정 | predicate가 실제 의도를 충분히 표현한다는 보증 |
| commit before challenge | test phase 전에 claim/scope/evidence manifest를 version-fix하고 변경 delta를 보존 | 반례를 본 뒤 조용히 기준을 바꾸는 것을 탐지 | truth, non-repudiation, replay resistance |
| independent challenge | frozen claim에 대해 별도 provenance의 discriminating counterexample을 제시 | checklist 맞춤형 답변을 줄이고 불일치를 노출 | cryptographic soundness/error bound |
| efficient verifier | 작성자는 근거를 구성하고 검토자는 작은 결정 조건을 재실행 | acceptance의 비용과 감사 가능성 개선 | 모델/요구사항 adequacy |
| separate properties | provenance, semantic support, freshness, authority, privacy를 별도 verdict로 유지 | category confusion 방지 | 각 속성이 참이라는 자동 보증 |

이 전이는 모두 **bounded analogy**다. 유일하게 exact라고 부를 수 있는 것은 “checker `R`가 환경 `e`, 시점 `t`, scope `s`에서 artifact `w`에 대해 predicate `x`를 통과시켰다”는 국소 판정뿐이다. 그것도 predicate adequacy나 stakeholder truth를 말하지 않는다. [Source 1][Source 3][Source 9]

### 버릴 것: guarantee-bearing vocabulary

- “인터뷰가 sound하다/complete하다”: 자연어 요구사항에는 닫힌 language, adversary model, error bound가 없다. 대신 `known-valid false-rejection`과 `seeded-false false-acceptance`를 선언된 corpus에서 측정한다. [Source 1]
- “답변이 proof of knowledge다”: PoK에는 extractor와 witness relation이 필요하다. 그럴듯한 transcript는 지식 보유의 증거가 아니다. [Source 2]
- “최소 공개라 zero knowledge다”: ZK는 simulator/indistinguishability property다. redaction은 privacy engineering이지 ZK가 아니다. [Source 1]
- “결정론적 질문 생성은 Fiat–Shamir다”: random-oracle/transform theorem과 완전한 transcript binding이 없으므로 보안 성질은 전이되지 않는다. 결정론은 재현성에만 사용한다. [Source 3]
- “여러 번 물으면 soundness가 증폭된다”: 반복이 같은 모델·prompt·retrieval·oracle을 공유하면 같은 실패를 재생산한다. 확률을 곱할 근거가 없다. [Source 6][Source 8]

## 2. Zero Trust가 주는 더 직접적인 설계

Zero Trust의 유용한 핵심은 “아무것도 믿지 마라”가 아니라 **암묵적 권한을 부여하지 않고 consequential resource/action을 현재 context로 평가하며, 결정이 실제 enforcement point에서 차단되게 하라**는 것이다. NIST의 PDP/PEP 분리는 이 문제에 정확히 맞는다. [Source 5]

`ultimateinterview`에서는 다음과 같이 매핑할 수 있다.

| ZT 요소 | ultimateinterview |
|---|---|
| subject | model, user, reviewer, tool, dispatcher |
| resource | claim, decision, handoff, implementation start, destructive probe |
| action | propose, settle, defer, finalize, deliver, execute |
| context | provenance, freshness, scope, contradiction, verification result, policy version, authority |
| PDP | transition을 allow/deny/revise/revoke하는 deterministic gate |
| PEP | deny 시 handoff/dispatch/tool effect를 실제로 막는 dispatcher/wrapper |

현재 `session_update.py`는 자신이 소유한 state mutation에 대해서는 실제 PEP다. v1의 `session_status.py --gate`는 typed state, BuildContract sidecar, open-world/probe/checkpoint 조건을 함께 판정하지만, 호출자가 반드시 존중할 때만 PEP다. question emission, handoff copy/send, implementation dispatch, runtime tool path는 보편적으로 매개되지 않는다. 그러므로 “게이트가 있다”와 “우회할 수 없다”를 구분해야 한다. 이 중 canonical state와 BuildContract readiness는 스킬의 소유 범위지만, delivery·dispatch·runtime effect의 complete mediation은 downstream harness/consumer의 책임이다. `ultimateinterview`는 필요한 grant/receipt/deny semantics를 계약에 표현할 수는 있어도 execute/evolve loop를 복제하지 않는다. [Source 4][Source 16][Source 17]

권장되는 grant는 최소한 `{subject, resource, action, session, generation, payload_digest, policy_version, expiry, nonce}`에 bind되어야 한다. PEP가 effect 직전에 grant를 검증·소비하고 receipt를 남겨야 한다. 같은 idempotency key와 같은 binding의 retry는 이전 receipt를 반환하고, 같은 key의 다른 payload는 거부한다. 외부 effect에는 exactly-once를 주장하지 말고 durable intent/outbox와 effect observation을 사용한다. LangGraph도 resume 시 node가 재실행되므로 side effect idempotency를 애플리케이션이 보장해야 한다고 명시한다. [Source 10][Source 11]

## 3. “독립 증거”를 문자열이 아니라 failure domain으로 다루기

BFT의 quorum 수학은 authenticated fixed membership, bounded faults, correct voting/locking, timing assumptions를 전제로 한다. 이 전제가 없는 LLM 다수결에 `2-of-3`이나 `3-of-4` 숫자만 가져오면 theorem이 아니다. 합의는 정의된 predicate에 대한 일관성을 만들 뿐 외부 진실을 만들지 않는다. [Source 6]

실무적으로는 `independence_group`을 caller가 쓰는 이름으로 세지 말고 다음 공통 의존성을 graph로 계산해야 한다.

- 같은 retry/cache/copied answer
- 같은 principal, credential custody, admin/control plane
- 같은 process, session, context, 이전 결론 노출
- 같은 model checkpoint/provider/architecture lineage
- 같은 prompt/rubric/examples
- 같은 source/citation chain/retriever/passages
- 같은 verifier/parser/harness/runtime
- 같은 specification/oracle/schema
- 같은 snapshot/release/time window
- 같은 incentive/reward/approval pressure

같은 root에 연결된 record는 한 표로 collapse한다. unknown material dependency는 자동 settlement를 막는다. dissent는 다수결로 지우지 말고 새 evidence, scoped checker, authority decision으로 adjudicate한다. 단, 다양성이 무용하다는 뜻도 아니다. 서로 다른 방법은 후보 생성과 robustness에 도움을 줄 수 있지만 그 이득은 empirical calibration의 대상이지 확률적 진실 보증이 아니다. [Source 6][Source 8][Source 12]

## 4. Verifier routing: 무엇이 결정을 내릴 수 있는가

LLM 연구의 일관된 메시지는 “더 그럴듯한 critique”보다 “오류를 판정할 수 있는 외부 feedback”이 중요하다는 것이다. intrinsic self-correction은 여러 설정에서 성능을 떨어뜨렸고, tool-grounded critique는 도구가 실제 signal을 제공할 때 개선됐다. same-LLM verification이 악화된 formal task에서 SymPy/constraint/VAL 같은 sound checker는 크게 개선됐다. 반대로 learned verifier와 best-of-N은 search가 verifier의 약점을 찾으면 성능이 다시 떨어질 수 있다. [Source 7][Source 8][Source 13]

권한은 다음처럼 비대칭으로 둔다.

| verifier class | 허용 역할 | settlement authority |
|---|---|---|
| intrinsic reflection / persona / debate | 후보, 반례, missing question 생성 | 없음 |
| retrieval/search | source candidate와 contradiction 생성 | source가 claim을 entail하는지 별도 판정 필요 |
| learned verifier/rubric | calibrated slice에서 ranking/advice | high-impact 단독 settlement 불가 |
| deterministic scoped checker | encoded predicate의 pass/fail | 정확히 그 predicate에 한정 |
| authorized stakeholder/domain owner | preference/policy/risk acceptance | 인증된 scope에 한정; factual truth와 구분 |
| live runtime observation | 실제 system behavior의 특정 관찰 | 관찰 조건/시점/환경에 한정 |

reflection/debate가 새 source, observation, counterexample, executable result를 추가하지 않았다면 confidence를 올리지 않는다. `unknown`, `needs user decision`, `needs runtime evidence`는 정상적인 terminal state다. [Source 7][Source 8]

## 5. 다섯 verdict firewall

현재 가장 중요한 구조 개선은 하나의 green status를 다섯 가지로 분해하는 것이다.

1. `abi`: Part 1과 sidecar가 schema/digest상 정확히 결합되어 있는가.
2. `trace`: material source obligation, REQ, VER, impact가 참조상 닫혀 있는가.
3. `property`: `P`가 모델 `M`, 가정 `A`, 범위 `S`에서 실행된 checker에 의해 확인됐는가.
4. `adequacy`: representation이 선언된 fault model의 mutation, vacuity, independent counterexample을 견뎠는가.
5. `stakeholder`: 인증된 권한자가 이 exact digest, omissions, assumptions, residuals를 받아들였는가.

이들은 implication chain이 아니다. ABI가 맞아도 내용이 틀릴 수 있고, trace가 닫혀도 subcase가 좁아질 수 있으며, property가 pass해도 모델이 현실을 빠뜨릴 수 있고, mutation을 모두 죽여도 선택하지 않은 fault class가 남을 수 있으며, stakeholder acceptance도 factual proof가 아니다. [Source 9][Source 14][Source 15]

현재 v1은 `abi`와 structural `trace`에 더해 typed evidence shape, revision-bound open-world/probe obligations, fresh-review sidecar binding, real-surface row, host-resolvable command head를 기계적으로 판정한다. 그렇다고 `property`가 된 것은 아니다. Verification row는 여전히 실행 결과가 아니라 실행 계획이며, `adequacy`·authenticated provenance/freshness·stakeholder verdict도 외부에 남는다. 다음 확장은 임의 v1 field가 아니라 versioned assurance result 또는 `contract_digest`에 bind된 receipt로 두는 편이 안전하다. [Source 4][Source 15][Source 17]

## 6. 구체적인 적용 우선순위

### P0 — 구현된 의미 분리를 유지하고, 남은 과장을 제거한다

- v1은 이미 `interview_converged`와 `implementation_ready`를 분리한다. `implementation_ready`는 “implemented policy를 통과”로 제한한다.
- “independently tested”, “verified”, “discovery rate” 같은 categorical 문구를 scope/version/evidence-qualified 문구로 바꾼다.
- exact / bounded analogy / metaphor / rejected transfer를 문서에 명시한다.
- formation phase와 test phase를 구분한다. 요구사항은 종종 숨겨진 witness를 추출하는 것이 아니라 인터뷰 중 공동 형성된다. [Source 3][Source 12]

이 단계는 저비용이며 security theater를 가장 빨리 줄인다.

### P1 — 이미 구현된 structural control 위의 거짓 양성을 막는다

1. **Verifier-derived evidence identity**: canonical source locator/revision/digest, observer/collector identity, observation method, claim binding을 검증한다.
2. **Correlation graph**: group 문자열 대신 공통 source/model/prompt/tool/spec/governance root를 계산한다.
3. **Executed verification receipt**: command syntax/head가 아니라 실제 command, environment, stdout/stderr digest, exit status, subject digest를 기록한다.
4. **Semantic fidelity challenge**: v1은 fresh-implementer review와 full-subcase 비교를 요구하지만, ID presence를 넘어 omission/narrowing, condition deletion, polarity, referent, boundary, temporal, coercion, oracle weakening mutation을 기계적으로 판정하지는 못한다.
5. **Complete composite gate**: v1은 sidecar·protocol obligations·decision-log instruction을 추가했지만 questions/transcript/decisions와 evidence payload를 하나의 required session manifest로 bind하지 않는다. [Source 4][Source 9][Source 15][Source 17]
6. **Bounded probe execution**: v1은 least-capable L0-L3 decision/result contract와 L2/L3 scoped authorization을 구현했다. L1의 두 behavioral-stub shape와 result는 아직 실행·artifact authenticity·unique-catch calibration을 증명하지 않으므로, executor-generated receipt와 empirical calibration이 남는다. [Source 16][Source 17]

### P2 — downstream consumer와 enforcement 계약을 맺는다

- `ultimateinterview`는 canonical state, BuildContract, readiness decision까지 소유한다. handoff delivery와 implementation dispatch는 downstream harness가 fresh digest-bound grant를 소비하도록 **consumer contract**에 명시한다.
- L2/L3 probe, destructive/credentialed action의 authenticated scope, target, payload digest, expiry, halt rules 검증은 외부 wrapper/실행 에이전트가 소유한다. 스킬은 장기 execute/evolve loop를 구현하지 않는다.
- fast-risk row의 `substrate:` 문자열은 PEP proof가 아니다. resolvable PEP identity와 per-surface deny/no-effect mutation evidence를 요구한다.
- retry/resume/crash를 대상으로 same-key/same-payload, same-key/different-payload, stale generation, consumed nonce, unknown external outcome을 검증한다. [Source 10][Source 11]

### P3 — provenance와 freshness를 session-level로 올린다

- v1은 material revision과 reviewed Part 1 sidecar에 대해 freshness를 부분적으로 구현했다. 아래는 그 범위를 whole session으로 확장하는 작업이다.
- ledger, protocol, questions, transcript tail, decisions, handoff, BuildContract, repo/material revision을 하나의 snapshot manifest로 bind한다.
- persisted monotonic head, same-version/different-digest rejection, expiry/event invalidation, authority epoch를 둔다.
- policy/authority rotation은 가능하면 old+new authorization을 모두 요구한다. compromise 시 quarantine → window bounding → derivative invalidation → re-observation → reissue를 수행한다.
- whole-directory replay가 threat model에 포함되면 mutable workspace 밖의 privacy-minimal checkpoint가 필요하다. [Source 9][Source 14]

### P4 — high-risk에만 assurance/mutation/formalization을 추가한다

- claim-context-warrant-evidence-assumption-defeater를 중요한/비가역적 claim에만 요구한다.
- security/privacy, data/schema, irreversible writes, external integration, concurrency/retry/rollback 같은 finite/bounded property에만 Alloy/TLA+/SMT 등 formal obligation을 고려한다.
- `unknown`, timeout, unchecked assumption은 pass가 아니다.
- property checker와 model-adequacy reviewer는 분리한다. real-surface evidence를 formal proof로 대체하지 않는다. [Source 9][Source 14]

### P5 — postmortem으로 calibration한다

- 기존 app-4/app-5 escape를 mutant catalog의 seed로 사용한다.
- reflection only, same-model debate, source-bound counter-search, deterministic/human outcome gate를 blinded adjudication으로 비교한다.
- baseline-only, taxonomy-stacked, trigger-routed lens의 unique material catch, false alarm, time, downstream escape를 측정한다.
- A1/A2 reviewer threshold나 confidence/abstention threshold는 이 local dataset에서 calibration되기 전에는 heuristic template로만 둔다. [Source 7][Source 12][Source 15]
- Postmortem은 어떤 모호성이 샜는지를 되먹임하되 실행을 재현하거나 소유하지 않는다. v1 bounded probe의 unique material catch와 비용도 함께 계측한다. [Source 16][Source 17]

## 7. 현재 코드베이스에서 확인된 사실

- Current committed v1 (`944a0c1`, followed by `1b0ed6f`) defines typed ClaimEvidence, causal lineage, material revision, a recompiled BuildContract sidecar, open-world/probe/checkpoint obligations, and a fresh-implementer gate. Actor/channel/identity/freshness values still enter without external authentication. [Source 4][Source 17]
- `session_status.py --gate` now blocks many more malformed/stale structural states, but it does not execute verification commands, require every session file, or detect a coherent direct ledger mutation through a whole-session manifest. [Source 17]
- `handoff_coverage.py` remains an ID-citation floor. v1 adds mandatory fresh-review/full-subcase comparison, but semantic narrowing remains non-mechanical. [Source 4][Source 15][Source 17]
- The 666-test result and its original bypass commands are historical evidence from the 2026-07-10 pre-commit snapshot. Current rebaseline: 13 focused v1 integration tests passed under Python 3.13; no new full-suite claim is made here. [Source 15][Source 17]

## 8. Contradictions and resolutions

| 충돌 | 해결 |
|---|---|
| “다양한 agent가 많을수록 안전” vs correlated failure | agent 수는 exploration에 유용하지만 corroboration은 failure-domain graph와 calibration이 있어야 한다. |
| “fail closed가 안전” vs liveness/fatigue | irreversible/high-impact consequential transition만 fail closed; low-risk/read-only fail-open은 명시적 residual로 제한한다. |
| “formal proof가 strongest evidence” vs spec bugs | property verdict와 adequacy/stakeholder verdict를 분리하고 mutation/vacuity/real-surface evidence를 유지한다. |
| “fresh digest면 최신” vs coherent replay | local digest는 integrity를 주지만 current-head truth는 external monotonic state/expiry/revocation이 필요하다. |
| “independent review” vs same-model/shared context | fresh context는 contamination을 줄이지만 독립성을 증명하지 않는다. model/source/tool/incentive lineage를 기록한다. |
| “더 많은 threat lenses가 coverage를 높임” vs false positives | trigger-routed mechanism diversity와 candidate adjudication을 사용하고 completeness 대신 bounded coverage를 보고한다. |

## 9. Gaps and residual risks

- 직접적인 `ultimateinterview` task distribution에서 reflection/debate/verifier/threshold를 비교한 empirical study는 없다. P5 benchmark 전까지 효과 크기는 unresolved다.
- authenticated human authority를 어떤 identity system과 연결할지는 배포 환경 결정이다.
- whole-session external checkpoint, retention/deletion, privacy classification은 조직 정책과 threat model이 필요하다.
- natural-language semantic equivalence는 일반적으로 decidable하지 않다. high-risk synthesis fidelity에는 human/domain evidence가 계속 필요하다.
- 한 `agent_systems` 연구 lane은 최종 산출물 없이 중단됐다. 그 축의 최종 주장은 completed guardrail/enforcement lanes와 official docs로만 구성했다.

## 10. Expansion trace and convergence

- Wave 1: 15 axes—local contract/runtime/history; crypto; zero trust; BFT; formal methods; supply chain; LLM reliability; requirements/human factors; threat modeling; agent systems; skeptical audit; pinned implementations.
- Wave 2: 10 leads—PoK boundary, evidence authenticity, freshness/replay, external verifiers, spec adequacy, PDP/PEP, lens diversity, assurance warrants, guardrail coverage, correlated quorum.
- Wave 3: 6 contradiction pairs—crypto↔skeptic, ZT↔human/threat, BFT↔LLM, provenance↔local runtime, formal↔local adequacy, agent controls↔local enforcement.
- Convergence: all conceptual/applicability leads investigated or closed as duplicate/dead end; remaining items are explicitly future implementation or empirical calibration, not premises required for this answer.

## Ranked sources

1. [Goldwasser, Micali, Rackoff, interactive proofs](https://evervault.com/papers/zkp-1986.pdf) — completeness/soundness/verifier assumptions.
2. [Bellare and Goldreich, Proofs of Knowledge](https://www.wisdom.weizmann.ac.il/~oded/PSX/pok.pdf) — extractor-defined knowledge.
3. [Canetti, Goldreich, Halevi, Random Oracle Methodology Revisited](https://eprint.iacr.org/1998/011.pdf) and [Goldwasser–Kalai](https://doi.org/10.1109/SFCS.2003.1238185) — transfer/Fiat-Shamir counterexamples.
4. Local live-contract/history artifacts — [live map](source-memos/live-contract-zero-trust-map.md), [history](source-memos/design-history-evolution-map.md).
5. [NIST SP 800-207 Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final) — PDP/PEP, per-resource policy, continuous evaluation.
6. [Castro and Liskov, PBFT](https://www.usenix.org/conference/osdi-99/practical-byzantine-fault-tolerance) — quorum assumptions and failure independence.
7. [Huang et al., intrinsic self-correction limits](https://arxiv.org/abs/2310.01798) — negative self-correction evidence.
8. [Stechly et al., sound vs LLM verifiers](https://proceedings.iclr.cc/paper_files/paper/2025/hash/f3c5e56274140e0420baa3916c529210-Abstract-Conference.html) and [Kim et al., correlated LLM errors](https://arxiv.org/abs/2506.07962).
9. [TUF specification](https://theupdateframework.github.io/specification/latest/), [in-toto specification](https://github.com/in-toto/specification/blob/master/in-toto-spec.md), [SLSA verification](https://slsa.dev/spec/v1.2/verifying-artifacts).
10. [OpenAI Agents SDK guardrails](https://openai.github.io/openai-agents-python/guardrails/) — explicit coverage boundaries.
11. [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — resume/replay and idempotency.
12. [SEI threat-model method comparison](https://www.sei.cmu.edu/blog/cyber-threat-modeling-an-evaluation-of-three-methods/) — breadth/false-positive/consistency tradeoffs.
13. [CRITIC](https://arxiv.org/abs/2305.11738) — tool-grounded critique.
14. [IronSpec](https://www.usenix.org/conference/osdi24/presentation/goldweber), [Alloy bounded analysis](https://alloytools.org/spec.html), and [NIST specification mutation](https://www.nist.gov/publications/mutation-operators-specifications) — property/adequacy boundary.
15. [Historical local verification](verify-current-deterministic-gates.md) — 2026-07-10 pre-commit test and bypass evidence.
16. [Local execution-agnostic spec-layer strategy](../../../docs/ultimateinterview-spec-layer-strategy.md) — handoff-as-product ownership and bounded execution borrowing. This tracked strategy document is used only for its strategic direction; its pre-v1 implementation inventory is stale.
17. [Current contract-oracle rebaseline](verify-current-contract-oracle.md) — 2026-07-11 focused v1 tests, present structural controls, and reproduced residual gaps.

## Epistemic instrumentation

- Intent closure: 3 true, 1 live-enforcement violation documented.
- Claim graph: 10 high-risk nodes supported and allowlisted; 1 normal privacy node partial/recommendation-only.
- Observation manifest: local execution, history, standards, primary papers, empirical studies, pinned implementations, and cross-lens audits are separately labeled.
- Verification economics: runtime, crypto-transfer, correlation, freshness/provenance, verdict firewall, and privacy deferral decisions recorded.
- Cause disappearance: “interview alone eliminates hallucination” refuted; “multiple agents imply independence” and “digest implies freshness” remain observed live gaps.
