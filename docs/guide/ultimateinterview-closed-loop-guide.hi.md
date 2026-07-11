# वह retry जिसने दो orders बना दिए

## `ultimateinterview` के लिए एक engineer's guide

[साथ की conference-talk deck (HTML) देखें।](./ultimateinterview-conference-talk.hi.html)

एक team को छोटा-सा reliability change मिलता है:

> `POST /orders` की transient failures को exponential backoff के साथ retry करें।

Planner HTTP client ढूँढता है, jitter के साथ कुल तीन attempts जोड़ता है, और ऐसा test लिखता है जिसमें vendor request process करने से पहले mock fail हो जाता है। दूसरा attempt सफल होता है। पूरी suite green है।

Production में timeline अलग है:

```text
10:00:00.000  checkout client_order_id=checkout-734 के साथ POST /orders भेजता है
10:00:00.041  vendor order O-481 insert करके transaction commit करता है
10:00:00.044  vendor customer को एक बार charge करता है
10:00:00.600  हर attempt की 600 ms observation timeout खत्म; checkout अभी नहीं जानता कि write commit हुई या नहीं
10:00:00.800  backoff के बाद पहला retry stable idempotency key के बिना दूसरा POST भेजता है
10:00:00.843  vendor O-482 insert करता है और customer फिर charge होता है
10:00:02.000  अलग 2 s end-to-end checkout deadline खत्म होती—पर duplicate पहले ही बन चुका है
```

`600 ms` का उत्तर है: “इस attempt को observable response के लिए कितनी देर प्रतीक्षा करनी है?” `2 s` का उत्तर है: “पूरी checkout invocation कितनी देर चल सकती है?” ये एक ही सीमा नहीं हैं। लगभग `800 ms` पर पहला retry total budget के अंदर है; incident किसी illegal post-deadline retry पर निर्भर नहीं करता।

Retry algorithm अपने design के अनुसार सही चलता है। फिर भी plan गलत है, क्योंकि उसने यह define नहीं किया कि side effect सफल हो जाए पर response खो जाए, तब retry का अर्थ क्या है।

यह guide उसी request को एक `ultimateinterview` session में आगे बढ़ाती है। इसमें protocol state और decision logic—hypotheses, evidence, scores, questions और gates—दिखते हैं। यह LLM की private chain-of-thought दिखाने का दावा नहीं करती।

## 1. Case study के fictional repository facts

इस table के सभी facts **काल्पनिक लेकिन realistic** हैं। ये `harnesses` repository या किसी real vendor के बारे में दावे नहीं हैं।

| देखी गई surface | Repository या contract fact |
| --- | --- |
| Order client | `OrderGateway.submit()` vendor को एक synchronous `POST /orders` call करता है। |
| Request model | हर checkout request में stable `client_order_id` है। |
| Local schema | `orders` पर `(merchant_id, client_order_id)` unique key है। |
| Current headers | Gateway हर HTTP attempt पर बदलने वाला `X-Request-Id` भेजता है, लेकिन vendor का `Idempotency-Key` नहीं। |
| Vendor OpenAPI | Connect reset, timeout, `502`, `503`, `504` retry हो सकते हैं; `429` को `Retry-After` के अनुसार retry किया जा सकता है। |
| Vendor idempotency | 24 घंटे के भीतर वही key और payload दोहराने पर original order मिलता है; key वही और payload अलग हो तो `409` मिलता है। |
| Existing policy | Idempotent `GET` में कुल तीन attempts, 100 ms base delay, exponent 2, full jitter और 1 s cap है। |
| Request budget | हर vendor attempt की 600 ms observation timeout है; containing checkout invocation की अलग 2 s end-to-end deadline है। |
| Shared utilities | Versioned canonical tuple serialization और dependency telemetry पहले से हैं; telemetry attempt, outcome, failure class और hashed correlation ID दर्ज करती है। |
| Test capability | Fixture vendor को order commit करके response पहुँचने से पहले connection close करा सकती है। |

Original request अभी implementable नहीं है। “Transient” और “exponential” ध्यान को retry library, attempt count और timing की ओर खींचते हैं। खतरनाक branch उससे पहले है:

```text
क्या vendor ने request reject की,
या order commit हो गया और केवल response fail हुआ?
```

Caller को दोनों states एक जैसी दिखती हैं, पर behavior अलग होना चाहिए। इसलिए outcome को फिर लिखा जाता है:

> चुनी हुई transport failures से recover करें, लेकिन एक logical order, एक charge और existing synchronous deadline को बनाए रखें।

यह product contract है। “Exponential backoff जोड़ें” केवल एक संभव mechanism है।

## 2. LLM उस failure mode को क्यों छोड़ सकता है जिसे वह जानता है

Strong LLMs idempotency, ambiguous network outcomes, retry storms और deadlines जानते हैं। समस्या stored knowledge की कमी नहीं है। समस्या है तय करना कि कौन-सा knowledge यहाँ लागू होता है, और plausible pattern को local fact मानने से इनकार करना।

1. **Request attention frame करती है।** “Retry जोड़ो” transaction state या duplicate charge की तुलना में timing और retry libraries को अधिक likely बनाता है।
2. **Familiar implementation जल्दी मिल जाती है।** Exponential backoff सामान्यतः उचित है, इसलिए model commit boundary जाँचे बिना coherent plan बना सकता है।
3. **एक context अपनी premise दोहराता है।** Planner design चुनता है, failure-before-commit वाला test लिखता है, फिर passing test को confirmation मानता है। Artifacts agree करते हैं क्योंकि उनकी assumption एक है।
4. **Copied evidence plural दिखता है।** OpenAPI paragraph, generated SDK comment और wiki एक source को दोहरा सकते हैं। इन्हें तीन witnesses मानना evidence laundering है।
5. **Fluency missing predicates छिपाती है।** “Transient failures को safely retry करें” तब तक precise लगता है जब तक कोई पूछे: transient कौन-सी, safely का observable अर्थ क्या, और कौन-सा result इसे prove करेगा?

`ultimateinterview` LLM knowledge को सीमित role देता है:

> Model knowledge hypotheses, applicability questions, falsifiers और evidence routes सुझाता है। अपने आप उसे settlement credit नहीं मिलता।

**Falsifier** वह evidence है जो current model को गलत कर दे। “Failed attempt commit नहीं हुआ” के लिए commit-then-close trace falsifier है। इसे नाम देने से generic knowledge investigation plan बनता है।

## 3. User से पूछने से पहले ORIENT

Interview questionnaire से शुरू नहीं होता। पहले repository, prior lessons और unfinished session state देखता है। Rule: जो fact repository बता सकती है, उसके लिए user का समय मत लो।

Bounded scan में synchronous call, stable identity, missing vendor key, दोनों time limits, vendor failure classes और commit-then-close fixture मिलते हैं। इसलिए user से status codes, schema या current timeout नहीं पूछा जाता। User को केवल consequential product/policy choice दी जाती है।

### 3.1 Zero-cost open-world hypotheses

Analysis lenses चुनने से पहले model अधिकतम तीन missing possibilities record करता है। हर item `origin: open-world`, `model-prior`, `assumption`, `hypothesis-only` से शुरू होता है।

| Hypothesis | Applicability question | Falsifier | Evidence route | Initial status |
| --- | --- | --- | --- | --- |
| Upstream caller को failure दिखने से पहले commit कर सकता है। | क्या timeout/reset client तक आने से पहले `POST /orders` commit हो सकता है? | Operation और delivery atomic हैं, या stable-key idempotency पहले से wired है। | Vendor contract, call site, commit-close fixture, जरूरत हो तो authorized traces। | Hypothesis only; zero credit। |
| Retries brownout बढ़ाकर deadline खा सकती हैं। | Vendor degraded हो तो क्या कई requests साथ retry करती हैं? | Traffic कहीं और serialized है, या call interactive deadline के बाहर है। | Deadline config, metrics, retry behavior, bounded load scenario। | Hypothesis only; zero credit। |
| Automatic retry invocation से बाहर या 24-hour retention के बाद चल सकती है। | क्या change की retry किसी और invocation में या 24 घंटे बाद चल सकती है? | सारी automatic retries original 2 s invocation में खत्म होती हैं; cross-invocation replay अलग durable design है। | Call graph, lifecycle, TTL contract, support workflow। | Hypothesis only; zero credit। |

यह external financial write है, इसलिए session `full` depth और 20 user decision interactions की ceiling चुनता है।

User बताता है: checkout synchronous रहना चाहिए; duplicate order/charge unacceptable है; recurring incident `503` है; queue scope में नहीं है। “No queue” non-goal है। “One charge” user-owned product decision है, code से inferred fact नहीं।

Framing challenge retry loop, stable business effect और reconciliation alternative अलग करती है। Confirmed restatement है: selected failures से recover करें, duplicate durable effect न बनाएं, 2 s synchronous boundary न बदलें, queue/background reconciliation out of scope रखें।

## 4. First ledger में active residual ambiguity 99 है

| ID | Initial claim या gap | Ambiguity | Impact | Status | Basis |
| --- | --- | ---: | ---: | --- | --- |
| `F-CURRENT` | Current `POST /orders` एक attempt करता है। | 0 | 2 | Triangulated | Call site + test। |
| `G-TRANSIENT` | Exact retryable set unclear है। | 2 | 3 | Draft | Vendor contract और `GET` policy में `429` difference। |
| `G-POST-COMMIT` | Commit + lost response का behavior undefined है। | 3 | 5 | Blocked | Fixture state को possible दिखाती है। |
| `G-IDEMPOTENCY` | Attempts के बीच stable identity undefined है। | 3 | 5 | Blocked | `client_order_id` है, vendor key नहीं। |
| `G-DUPLICATE` | “At most one order and charge” अभी explicit invariant नहीं। | 2 | 5 | Draft | Financial impact inferred; user authority चाहिए। |
| `G-ATTEMPTS` | Attempt count unspecified है। | 2 | 3 | Draft | `GET` default `POST` को जरूरी नहीं govern करे। |
| `G-TTL` | 24-hour window के बाद cross-invocation replay unresolved है। | 3 | 3 | Draft | Current code 2 s में retry करता है; durable store/clock seam नहीं। |
| `G-KEY-PAYLOAD` | Same key + different payload का local behavior undefined। | 3 | 3 | Draft | Vendor `409`; local API silent। |
| `G-CONCURRENCY` | Same logical identity के concurrent requests undefined। | 3 | 5 | Blocked | Local uniqueness upstream behavior prove नहीं करती। |
| `G-DEADLINE` | 2 s deadline के अंदर retry predicate unspecified। | 2 | 3 | Draft | Request config। |
| `G-OBSERVE` | Operators initial call और retry अलग नहीं देख सकते। | 2 | 2 | Draft | Current telemetry। |
| `G-SCOPE` | Async queue/reconciliation scope unclear है। | 2 | 2 | Draft | Model-generated alternative। |

`G-TTL` अभी active है, इसलिए उसके `3 × 3 = 9` points भी total में हैं:

```text
6 + 15 + 15 + 10 + 6 + 9 + 9 + 15 + 6 + 4 + 4 = 99
```

यह “99% unknown” नहीं है। यह active implementation-branching risk का inspectable weight है। Repository बाद में deferral recommend कर सकती है, लेकिन scope decision user का है; evidence अपने आप `G-TTL` हटाती नहीं।

## 5. Financial-state question पहले आना चाहिए

`question_score.py` candidates को impact, branch split, uncertainty reduction, coverage, user cost और redundancy से rank करता है:

```text
impact × branch_split × uncertainty_reduction × coverage
-------------------------------------------------------
1 + user_cost + redundancy
```

| Rank | Candidate | Impact | Branch | Uncertainty | Coverage | Cost | Redundancy | Exact score |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Post-commit lost response | 5 | 5 | 5 | 5 | 3 | 0 | `625 / 4 = 156.25` |
| 2 | Logical-order key | 5 | 4 | 5 | 4 | 3 | 0 | `400 / 4 = 100` |
| 3 | Total attempt ceiling | 3 | 3 | 3 | 3 | 1 | 0 | `81 / 2 = 40.5` |
| 4 | Retryable failure classes | 3 | 4 | 3 | 4 | 3 | 0 | `144 / 4 = 36` |

```json
{
  "questions": [
    {"id":"q-post-commit","question":"Post-commit lost response?","impact":5,"branch_split":5,"uncertainty_reduction":5,"coverage":5,"user_cost":3,"redundancy":0,"target_ids":["G-POST-COMMIT"]},
    {"id":"q-key","question":"Logical-order key?","impact":5,"branch_split":4,"uncertainty_reduction":5,"coverage":4,"user_cost":3,"redundancy":0,"target_ids":["G-IDEMPOTENCY"]},
    {"id":"q-attempts","question":"Total attempt ceiling?","impact":3,"branch_split":3,"uncertainty_reduction":3,"coverage":3,"user_cost":1,"redundancy":0,"target_ids":["G-ATTEMPTS"]},
    {"id":"q-retryable","question":"Retryable failure classes?","impact":3,"branch_split":4,"uncertainty_reduction":3,"coverage":4,"user_cost":3,"redundancy":0,"target_ids":["G-TRANSIENT"]}
  ]
}
```

```bash
uv run .agents/skills/ultimateinterview/scripts/question_score.py --format markdown questions.json
```

Helper supplied candidates की validation, arithmetic और ordering deterministic बनाता है। वह missing candidate खोज नहीं सकता, bad factor judgment सुधार नहीं सकता, और यह independently enforce नहीं करता कि interviewer ने top rank ही पूछा। Runtime rule और persisted-state review यह बाकी guard देते हैं। Backoff parameters queue में नहीं हैं क्योंकि अभी कोई critical ledger gap उन्हें anchor नहीं करता।

## 6. पहला structured question

> **Evidence:** caller में stable `client_order_id` है, पर gateway vendor `Idempotency-Key` नहीं भेजता। **Scenario:** vendor `O-481` बनाकर customer को charge करता है, फिर response मिलने से पहले connection close हो जाता है। उसी logical request को retry करने पर क्या होना चाहिए? अगर duplicate acceptable है या कोई दूसरा system reconciliation guarantee करता है, तो मेरा current model falsify होगा।

Options:

1. **Original order लौटे; order या charge दो बार न बने — Recommended.** Vendor contract और local identity इसे support करते हैं।
2. Unknown/pending लौटे और retry न हो। इसके लिए later reconciliation owner चाहिए।
3. New order की तरह retry हो और duplicate tolerate हो। Stated failure fear से conflict।
4. Other. Free-form escape hatch हमेशा रहता है।

User option 1 चुनता है। पर weight-5 gap एक उत्तर से तुरंत erase नहीं होता। Critical answer को pressure, independent causal evidence, या owning authority की explicit acceptance चाहिए।

### Free pressure follow-up

> Vendor ने `O-481` store किया, एक बार charge किया और response खो गया। 200 ms बाद retry होता है। Caller को exact क्या मिले, कितने records हो सकते हैं, और क्या कभी नहीं होना चाहिए?

उत्तर decomposed predicates बनता है:

1. retry वही `order_id` लौटाता है;
2. exactly one local order;
3. exactly one vendor order और one charge; और
4. same key के साथ changed payload reject होता है।

यह protocol के two-free-follow-ups-per-thread rule के अंदर है। “Safe retry” अब observable identity और counts हैं।

## 7. Evidence causal independence और authority से count होती है

| Evidence | Channel | Independence group | Authority और credit |
| --- | --- | --- | --- |
| `OrderGateway.submit()` call site | `from-code` | `repo:order-call-site` | Current behavior: one attempt, no vendor key। |
| `(merchant_id, client_order_id)` unique index | `from-code` | `repo:order-schema` | Local uniqueness boundary। |
| Vendor OpenAPI idempotency section | `from-docs` | `vendor:idempotency-contract` | Key behavior और 24-hour TTL। |
| OpenAPI से copied SDK comment | `from-code` | वही group | कोई additional independence credit नहीं। |
| User decision: one order, one charge | `from-user` | `user-dependency:G-DUPLICATE` | Product-decision authority; current code prove नहीं करती। |
| Commit-then-close fixture | `from-scenario` | `scenario:commit-close` | Surrogate में ambiguous sequence prove; production frequency नहीं। |
| “POST retry duplicate कर सकती है” | `assumption` | `model-prior:post-retry` | Search path only; zero settlement credit। |

Contradictory sources `Contested` रहते हैं। Interviewer current plan आसान बनाने वाला source चुपचाप नहीं चुन सकता।

## 8. बाकी interview implementation branches के अनुसार चलता है

### 8.1 One logical order क्या है?

Repo में merchant-scoped unique key है; `X-Request-Id` हर transport attempt में बदलता है। Structured choice `(merchant_id, client_order_id)` को logical identity बनाती है। Serialization/hashing builder का mechanic है।

### 8.2 किन failures में deadline consume हो सकती है?

Decision: connect timeout/reset, `502`, `503`, `504` retry हों; `429` केवल तब जब `Retry-After` plus पूरा अगला 600 ms observation budget remaining 2 s deadline में fit हो; दूसरे `4xx` retry न हों; ऐसा sleep/attempt शुरू न हो जो remaining budget में पूरा fit न करे।

### 8.3 Deadline और attempt count अलग critical questions हैं

`G-DEADLINE` और `G-ATTEMPTS` दोनों ambiguity 2, impact 3 से शुरू होते हैं और एक-दूसरे को constrain करते हैं। इन्हें batch नहीं किया जाता।

Deadline question पहले पूछता है: 600 ms per-attempt clock और hard 2 s invocation clock में कौन retry start को govern करे? User चुनता है: 2 s wins; required delay + पूरा next 600 ms budget fit होना चाहिए। Pressure case `t=1.55 s`, delay `100 ms`, remaining `350 ms`: attempt शुरू नहीं होगा; mapped dependency-unavailable result लौटेगा।

फिर attempt ceiling अलग पूछी जाती है। User कुल तीन attempts चुनता है। Pressure स्पष्ट करता है कि तीन **ceiling** है, target नहीं; deadline predicate तीसरा attempt रोक सकती है। यह sequencing “three attempts” को deadline तोड़ने वाली mandatory count बनने से रोकती है।

### 8.4 केवल low-risk mechanism defaults batch होते हैं

Critical semantics settle होने के बाद evidence-backed batch है:

1. Existing `GET` policy से full-jitter backoff: 100 ms base, exponent 2, 1 s cap।
2. Existing versioned tuple serializer से `(merchant_id, client_order_id)` canonical serialization; delimiter concatenation नहीं।
3. Existing telemetry से attempt number, final outcome, failure class और hashed key; raw key नहीं।

Attempt count और deadline इस batch में नहीं हैं।

### 8.5 Same key, different payload

Local behavior: canonical business fields normalize करके fingerprint compare हो; mismatch पर `409 IDEMPOTENCY_KEY_REUSED`, कोई नया vendor POST नहीं; key hash और fingerprints log हों, payload contents नहीं। JSON field order जैसी harmless representation identity नहीं बदलती।

### 8.6 Cross-invocation replay explicit deferred risk है

Current retries original 2 s invocation में हैं। 24-hour window के पार replay detect करने के लिए durable original-order store और controllable clock seam चाहिए, जो इस change में नहीं हैं। Stable key अकेली यह predicate prove नहीं कर सकती। इसलिए visible scope question पूछी जाती है:

1. **Payments Platform review के लिए 2026-08-15 तक defer — Recommended.** Owner, date और missing proof record करें।
2. Current scope expand करें: durable store, retention policy, cross-invocation behavior और clock-controlled verification design करें।
3. Other।

User option 1 चुनता है। तभी `G-TTL` Draft से Deferred होता है और active residual से 9 points हटते हैं। Current boundary: **original invocation के बाहर कोई automatic resubmit नहीं।**

| Deferred risk | Owner | Review date | Reason |
| --- | --- | --- | --- |
| Cross-invocation replay behavior, durable original-order proof, retention semantics और testable store/clock seam define करें। | Payments Platform | 2026-08-15 | Detectable 24-hour replay के लिए invocation-scoped retry से बाहर persistent state और time control चाहिए। |

### 8.7 Concurrent callers

Same `(merchant_id, client_order_id)` वाले two workers के लिए equal payloads one `order_id` पर converge करें; at most one vendor order और charge हो; different payloads दोनों success न हों—एक result wins, दूसरा deterministic conflict पाए। Lock, local constraint या vendor mechanism builder चुन सकता है; interview observable behavior तय करता है।

## 9. Vague request पाँच controlled requirements बनती है

```text
REQ-001
Given POST /orders with merchant_id M and client_order_id C
When an attempt ends in connect timeout, reset, 502, 503, or 504
Then at most two further attempts may occur
And every attempt uses one Idempotency-Key derived from (M, C)
And all automatic retries remain in the original invocation.

REQ-002
Given vendor committed order O for (M, C) and response was lost
When gateway retries in the same invocation
Then caller receives O
And exactly one local order, one vendor order, and one charge exist.

REQ-003
Given key used with canonical fingerprint P1
When same key arrives with P2 where P1 != P2
Then return 409 IDEMPOTENCY_KEY_REUSED
And do not perform another vendor POST.

REQ-004
Given concurrent requests with same (M, C) and equal payloads
When both reach the gateway
Then successful responses contain the same order_id
And vendor order count and charge count are each one.

REQ-005
Given 429 with Retry-After D and 600 ms attempt budget
When D + 600 ms fits the remaining 2 s deadline
Then gateway may retry after D
Otherwise stop without sleeping or starting another attempt
And return mapped dependency-unavailable.
```

Cross-invocation replay intentionally current REQs में नहीं है; owner/date/prerequisite proof Deferred Risks में हैं।

```text
VER-ORDER-COMMIT-DROP
1. Stateful fake vendor orders और charges record करे।
2. (M, C), canonical payload P और outbound stable key K भेजें।
3. First call पर order O और one charge commit करके response drop करें।
4. Gateway को retry करने दें।
5. हर attempt का key/payload और final response order_id R capture करें।
6. Pass only if every attempt used K, R == O, vendor_order_count(K) == 1,
   vendor_charge_count(K) == 1, and local_order_count(M, C) == 1.
```

Real client हर attempt पर नया key भेजे तो केवल mock call-count इस oracle को game नहीं कर सकता।

## 10. Fresh implementer अभी भी holes निकालता है

Fresh implementer को repository और first draft मिलता है, interview conversation नहीं। L0 static reading में चार blockers आते हैं:

1. `client_order_id` global है या merchant-scoped?
2. Equal payload raw JSON, normalized JSON या selected business fields है?
3. `Retry-After` remaining deadline से बड़ा हो तो क्या?
4. क्या mock एक order लौटाकर test pass करा सकता है, जबकि real client हर attempt पर अलग key भेजे?

पहला repo answer करती है; यह draft synthesis loss है, user question नहीं। 2 और 3 explicit decisions हैं। 4 oracle को mock count से real outbound request + stateful fake की ओर rebind करता है।

Protocol L0–L3 में least capable adequate level का explicit decision मांगता है। इस case में L0 race behavior observe नहीं कर सकता, इसलिए L1 चुना जाता है: दो independently authored behavioral stubs।

- Producer A: DB-backed fake commit करके socket close करती है; per-attempt new key से two durable rows दिखाती है।
- Producer B: barrier-based concurrent fake two callers interleave करती है; same key के बावजूद changed payload के लिए conflict rule की जरूरत दिखाती है।

Material divergence `origin: probe` gap जोड़ती है, dry-sweep streak clear करती है, checkpoint stale करती है, reviewed Build Contract invalidate करती है और session interview में लौटता है। Targeted rerun में नया divergence न मिले तो उसे completeness credit नहीं मिलता; bounded probe sequence केवल close होती है।

## 11. प्रतिनिधि interview trace

| चरण | नया evidence या user decision | LLM की hypothesis और candidates | Protocol routing | अगला visible interaction |
| ---: | --- | --- | --- | --- |
| 1 | Code में mutable `X-Request-Id` है; fixture commit करने के बाद connection बंद कर सकती है। | “असफल response किसी सफल write को छिपा सकता है” को fact नहीं, बल्कि applicability question और falsifier बनाया जाता है। | `G-POST-COMMIT` score 3 और weight 5 के साथ दर्ज होता है; scorer इसे `156.25` देता है। | Retry settings से पहले post-commit financial outcome पूछें। |
| 2 | User एक order और एक charge चुनता है। | “वही HTTP response”, “वही durable order” और “बाद में reconciliation” अब भी अलग interpretations हैं। | Critical answer का score 2 से नीचे करने से पहले pressure आवश्यक है। | Exact result, local record count, vendor record count, charge count और forbidden outcome पूछें। |
| 3 | Pressure story में original ID, सभी counts और changed-payload rejection तय होते हैं। | “Same logical request” के लिए अब identity predicate चाहिए। | Repo evidence के आधार पर `(merchant_id, client_order_id)` recommended है; per-attempt request ID logical identity के रूप में falsify होती है। | Structured logical-key question पूछें। |
| 4 | Vendor docs retryable failure classes देती हैं; code 600 ms और 2 s की अलग clocks दिखाता है। | `429` और `Retry-After` remaining-budget branch बनाते हैं। | `G-DEADLINE` एक due critical obligation है; scored candidates में attempt ceiling `40.5` और failure taxonomy `36` है। | Deadline-boundary question पूछें, फिर `t=1.55 s` पर pressure करें। |
| 5 | User तय करता है कि hard deadline सर्वोपरि है और अगली पूरी 600 ms attempt window उपलब्ध होनी चाहिए। | Attempt count अब timing predicate से सीमित होता है। | `G-ATTEMPTS` अलग score-2, weight-3 question बना रहता है। | Maximum पूछें, फिर स्पष्ट करें कि three एक ceiling है या mandatory count। |
| 6 | User three-attempt ceiling की पुष्टि करता है; वास्तविक count कम हो सकता है। | Backoff shape, tuple encoding और telemetry अब critical semantics नहीं बदलते। | केवल independent, low-risk, evidence-backed defaults को batch किया जाता है। | Backoff, serialization और observability defaults का evidence-backed batch दें। |
| 7 | Cross-invocation path के लिए durable store या controllable clock मौजूद नहीं है। | Model 24-hour conflict की कल्पना कर सकता है, लेकिन वर्तमान system उस predicate को prove नहीं कर सकता। | Explicit scope decision होने तक `G-TTL` Draft रहता है। | User इसे Payments Platform के पास 2026-08-15 तक defer करता है। |
| 8 | Fresh implementer merchant scope, payload equality, oversized `Retry-After` और gameable mock में synthesis loss पाता है। | Complete लगने वाले contract में observable gaps सामने आते हैं। | इस case में L1 least adequate probe है; material divergence readiness को invalidate करती है। | प्रभावित questions और verification oracle दोबारा खोलें। |

इसी कारण persisted loop, unpersisted planner chat की तुलना में संरचनात्मक रूप से अधिक मजबूत है। LLM hypotheses और factor judgments बनाता है, लेकिन session state तय करती है कि अगला कौन-सा unresolved branch संभालना है, किस answer पर pressure आवश्यक है, किन questions को batch नहीं किया जा सकता और कौन-सा नया evidence पुरानी readiness को invalidate करता है।

## 12. स्थिर ownership boundaries

Implementation कुछ durable artifacts के माध्यम से responsibilities को स्पष्ट रूप से अलग रखता है:

| Owner या surface | किसका उत्तरदायित्व है | क्या दावा नहीं कर सकता |
| --- | --- | --- |
| Interview runtime | Repository-first evidence, ambiguity ledger, due obligations, question routing, pressure, sweeps और resolved least-capable L0–L3 probe decision। | यह कि model priors facts हैं, scoring ने हर candidate खोज लिया है या neutral probe completeness सिद्ध करता है। |
| `question_score.py` | उसे मिले candidate JSON का deterministic validation, arithmetic और ordering; इस case में rank order `156.25`, `100`, `40.5` और `36` है। | Candidate completeness, human dimension judgments की correctness—जिसमें behavior/tests impact anchor भी शामिल है—या यह independent enforcement कि top-ranked question वास्तव में पूछा गया। |
| Reviewed contract | Stable `REQ` और `VER` identities तथा human-reviewed behavior का digest। | Implementation mechanics या reviewed/deferred scope के बाहर का behavior। |
| External Claude, Codex, CI या human builder | Product edits, runtime tools, worktrees, permissions और contract द्वारा अनुमत implementation choices। | Contract को दोबारा लिखने का authority या स्वयं को specification completeness देने का अधिकार। |
| Returned evidence और fresh postmortem | Promised behavior, actual changes, decisions और observable proof की तुलना करना तथा escaped requirements दर्ज करना। | Interview history को दोबारा लिखकर किसी पुराने miss को मिटाने की अनुमति। |

यह सीमा जानबूझकर रखी गई है: interviewer missing decisions को चुपचाप implement नहीं कर सकता और builder उस contract को चुपचाप बदल नहीं सकता जिसके विरुद्ध उसका मूल्यांकन होना है।

## 13. Claude और Codex: “कर सकते हैं” बनाम protocol में “करना ही है”

Codex repository inspect, plan और edit कर सकता है तथा tools चला सकता है; वह skills और dedicated planning surface को support करता है। [Official Codex CLI guide](https://learn.chatgpt.com/docs/codex/cli) और [current features](https://learn.chatgpt.com/docs/features) देखें। Claude Code भी read-only planning और Explore → Plan → Implement → Commit workflow को support करता है। [Permission modes](https://code.claude.com/docs/en/permission-modes) और [best practices](https://code.claude.com/docs/en/best-practices) देखें।

एक strong planner इस case का हर सवाल **पूछ सकता है**। अंतर model intelligence का नहीं, process obligation का है:

| Strong Claude/Codex planner कर सकता है… | `ultimateinterview` को करना ही है… |
| --- | --- |
| Idempotency risk याद रखना। | Prior को hypothesis, applicability question, falsifier और evidence route के रूप में दर्ज करना; prior को zero fact credit मिलता है। |
| User से पूछने से पहले repo inspect करना। | Repo-answerable questions हटाना और evidence source को user intent से अलग सुरक्षित रखना। |
| Duplicate orders के बारे में पूछना। | Ledger में आते ही post-commit state को retry count और backoff से ऊपर rank करना। |
| Important answer पर follow-up करना। | High-impact gap घटाने से पहले pressure, independent evidence या explicit authority मांगना। |
| Identity, TTL, concurrency और observability का उल्लेख करना। | Active और deferred sibling tracks को persisted state में रखना तथा local depth के कारण उन्हें भूलने से रोकना। |
| Detailed tests लिखना। | Stable `REQ`/`VER` identities को reviewed digest और observable oracle से bind करना। |
| दूसरे agent से review कराना। | Fresh implementer को केवल contract देना; material divergence को new gap मानना और stale readiness invalidate करना। |
| Tests चलाकर success summarize करना। | Exact-contract-bound typed executor return और evidence स्वीकार करना; executor स्वयं specification completeness नहीं दे सकता। |

Native planners को prompt देकर यही moves कराए जा सकते हैं। Protocol उन्हें context compaction, handoff और अलग executor runtimes के पार persistent, ordered और fail-closed बनाता है। Ambiguous, high-cost brownfield changes में यह अधिक मजबूत spec देता है; यह सार्वभौमिक रूप से बेहतर होने का दावा नहीं है।

## 14. Interview product execution का उत्तरदायित्व क्यों नहीं लेता

यदि एक ही context interview, implementation और sufficiency judgment तीनों करे, तो तीन signals आपस में घुल जाते हैं:

1. missing requirement coding के दौरान चुपचाप भरी जा सकती है;
2. implementation choice को बाद में ऐसे बताया जा सकता है जैसे spec ने उसे अनिवार्य किया हो; और
3. implementer ऐसा test लिख सकता है जो wording को satisfy करे, लेकिन वास्तविक behavior से बच निकले।

यहाँ executing interviewer process-local lock चुनकर unit tests pass करा सकता है, जबकि दो service replicas के बीच race जारी रहे। Separate builder को लिखित cross-replica behavior implement करना होगा या deviation लौटाना होगा। इससे measurable counterfactual सुरक्षित रहता है:

> क्या fresh implementer केवल reviewed contract के आधार पर वही observable behavior बना सकता है?

एक practical कारण भी है: Claude, Codex, CI और human teams अपने tools, permissions, worktrees, deployments और runtime recovery पहले से संभालते हैं। हर execution environment को दोबारा बनाना adapter treadmill पैदा करता है; उससे requirement discovery सीधे बेहतर नहीं होती।

Interview केवल दो सीमित execution surfaces का उत्तरदायित्व रखता है:

- एक unresolved semantic question को मापने वाले bounded L0–L3 probes; और
- predeclared, allowlisted, repo-local verification commands की `safe-auto` evidence capture।

`safe-auto` product code edit या deploy नहीं कर सकता, implementation mechanics नहीं चुन सकता और arbitrary shell command नहीं चला सकता। Regulated attestation, rollback, persistent experiments, production telemetry custody और hard sandbox guarantees के लिए अब भी execution-owning control plane चाहिए। Typed artifacts किसी arbitrary executor को trustworthy नहीं बना सकते।

## 15. Closed loop secondary है, लेकिन आवश्यक है

Pre-build discovery यह prove नहीं कर सकती कि uncertainty शून्य है। Builder `execution-return.json`, changed surfaces, `decisions.jsonl`, REQ/VER outcomes और hash-bound evidence लौटाता है। Fresh postmortem promised behavior, implementation और proof की तुलना करता है।

मान लें stable key duplicate order rows रोकती है, लेकिन fulfillment event दो बार publish होता है। Original contract ने primary table को protect किया, पर दूसरा durable side effect छूट गया। Postmortem उस escape को stable identity देता है—या आवश्यकता होने पर “no existing category” दर्ज करता है—लेकिन history को rewrite नहीं करता। अगली orientation “one row” नहीं, बल्कि “all externally visible side effects” पूछती है।

Loop इसलिए आवश्यक है कि execution interview के world model को falsify कर सके, और interviewer पुरानी spec बदलकर अपना miss न छिपा सके।

## 16. Stop और handoff blockers पर आधारित हैं

Session तभी रुकती है जब सभी score-2 या score-3 gaps settle हो चुके हों या owner/date के साथ explicitly deferred हों; दो fresh breadth sweeps में कोई नया implementation-changing gap न मिले; falsification checkpoint current model की पुष्टि करे; least-capable L0–L3 probe decision resolved हो; fresh implementer का कोई blocking ask न बचे; gameable criteria real observable surfaces से rebound हों; और deterministic implementation gate pass हो।

Handoff boundary पर artifacts जानबूझकर छोटे रखे गए हैं:

- `handoff.md` में human-reviewed agreement होता है;
- `build-contract.json` में strict, digest-bound `BuildContract v1` होता है; और
- builder `decisions.jsonl` में unforced choices जोड़ता है तथा evidence सहित `execution-return.json` लौटाता है।

इस case में `G-TTL` deferral—owner Payments Platform, review date 2026-08-15 और store+clock proof prerequisite—`handoff.md` में होना अनिवार्य है। इसके बिना `G-TTL` active score-3 gap रहता है और stop block हो जाता है। Builder retry library, lock mechanism, module decomposition या hashing implementation चुन सकता है; वह retryable conditions, identity scope, duplicate behavior, invocation-only retry boundary, deferred cross-invocation risk, deadline या verification oracle को चुपचाप नहीं बदल सकता।

## 17. Overhead कब उचित है

Full method तब उपयोग करें जब गलत assumption money, data, permissions या compatibility को नुकसान पहुँचा सकती हो; change network, transaction, lifecycle, concurrency या ownership boundary पार करता हो; repository पुरानी, distributed या unfamiliar हो; implementation किसी दूसरे person, session, model या runtime को जाना हो; shallow mock या self-authored test acceptance को game कर सकता हो; या evidence और decisions को context compaction तथा handoff के पार सुरक्षित रखना हो।

Typo, reversible local refactor, mechanical dependency bump या authoritative test suite से पूरी तरह constrained change के लिए normal planner या minimal interview पर्याप्त है।

Duplicate-order incident का मुख्य lesson “हर बार idempotency पूछो” नहीं है—वह केवल एक और fixed checklist बन जाएगा:

> LLM से dangerous possibilities उत्पन्न कराएँ; हर consequential possibility को local evidence और decision authority से settle करें; सबसे बड़े consequence वाला सवाल पहले पूछें; और पर्याप्त separation बनाए रखें ताकि fresh builder या runtime result interview को गलत साबित कर सके।
