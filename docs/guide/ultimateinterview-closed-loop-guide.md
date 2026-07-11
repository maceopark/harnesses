# The retry that created two orders

## An engineer's guide to `ultimateinterview`

[View the companion conference-talk deck (HTML).](./ultimateinterview-conference-talk.html)

A team receives what looks like a small reliability change:

> Retry transient failures from `POST /orders` with exponential backoff.

The planner finds the HTTP client, adds three attempts with jitter, and writes a test whose mock fails before the vendor processes the request. The second attempt succeeds. The suite is green.

Production exercises a different timeline:

```text
10:00:00.000  checkout sends POST /orders for client_order_id=checkout-734
10:00:00.041  vendor inserts order O-481 and commits the transaction
10:00:00.044  vendor charges the customer once
10:00:00.600  the 600 ms per-attempt observation timeout expires; checkout still cannot tell whether the write committed
10:00:00.800  after retry scheduling/backoff, the first retry sends another POST without a stable idempotency key
10:00:00.843  vendor inserts order O-482 and charges the customer again
10:00:02.000  the separate 2 s end-to-end checkout deadline would expire, but the duplicate already exists
```

The `600 ms` limit answers “how long may this attempt wait for an observable response?” The `2 s` limit answers “how long may the whole checkout invocation run?” They are not interchangeable. The first retry at roughly `800 ms` is inside the total budget, so the incident does not depend on illegally retrying after the deadline.

The retry algorithm works exactly as designed. The plan is still wrong. It never defined what a retry means when the side effect succeeds but the response is lost.

This guide follows that one request through an `ultimateinterview` session. It shows protocol state and decision logic: recorded hypotheses, evidence, scores, questions, and gates. It does **not** claim to reveal an LLM's private chain-of-thought.

## 1. Fictional repository facts for the case study

Everything in this table is **fictional but realistic**. These are not claims about the `harnesses` repository or a real vendor.

| Surface inspected | Repository or contract fact |
| --- | --- |
| Order client | `OrderGateway.submit()` makes one synchronous vendor `POST /orders` call. |
| Request model | Every checkout request contains a stable `client_order_id`. |
| Local schema | `orders` has a unique key on `(merchant_id, client_order_id)`. |
| Current headers | The gateway forwards `X-Request-Id`, which changes per HTTP attempt, but does not send the vendor's `Idempotency-Key`. |
| Vendor OpenAPI | Connect reset, timeout, `502`, `503`, and `504` may be retried. A `429` may be retried using `Retry-After`. |
| Vendor idempotency | Reusing the same key and payload within 24 hours returns the original order. Reusing the key with a different payload returns `409`. |
| Existing policy | Idempotent `GET`s use three total attempts, a 100 ms base delay, exponent 2, full jitter, and a 1 s cap. |
| Request budget | Each vendor attempt has a 600 ms observation timeout; the containing checkout invocation has a separate 2 s end-to-end deadline. |
| Shared utilities | Existing code provides versioned canonical tuple serialization for merchant-scoped identifiers and dependency telemetry that records attempts, outcomes, failure classes, and hashed correlation identifiers. |
| Test capability | A fixture can make the vendor commit an order and then close the connection before the response reaches checkout. |

The original request is not implementable yet. Words such as “transient” and “exponential” pull attention toward a retry library, attempt count, and timing. The dangerous branch is earlier:

```text
Did the vendor reject the request,
or did it commit the order while only the response failed?
```

Those states look identical to the caller but require different behavior. The real outcome is therefore restated as:

> Recover from selected transport failures while preserving one logical order, one charge, and the existing synchronous deadline.

That is a product contract. “Add exponential backoff” is only one possible mechanism.

## 2. Why an LLM can miss a failure mode it already knows

Strong language models know about idempotency, ambiguous network outcomes, retry storms, and deadlines. The problem is not lack of stored knowledge. It is deciding which knowledge applies here and refusing to treat a plausible pattern as a local fact.

Several properties of an LLM workflow make the shallow plan attractive:

1. **The request frames attention.** “Add retries” makes timing and retry libraries more likely topics than transaction state or duplicate charges.
2. **A familiar implementation appears quickly.** Exponential backoff is a sensible general pattern, so the model can reach a coherent plan before it investigates the commit boundary.
3. **One context repeats its own premise.** A planner can choose a design, write a test that assumes failure-before-commit, and then cite the passing test as confirmation. The artifacts agree because they inherited one assumption.
4. **Copied evidence looks plural.** An OpenAPI paragraph, generated SDK comment, and internal wiki may all repeat one source. Counting them as three witnesses launders one causal root into apparent triangulation.
5. **Fluency hides missing predicates.** “Retry transient failures safely” sounds precise until someone asks what is transient, what “safely” means, and what observable result proves it.

`ultimateinterview` uses LLM knowledge, but gives it a limited role:

> Model knowledge proposes hypotheses, applicability questions, falsifiers, and evidence routes. It receives no settlement credit by itself.

A **falsifier** is evidence that would make the current model wrong. For “the failed attempt never committed,” a commit-then-close trace is a falsifier. Naming it turns general knowledge into an investigation plan.

## 3. ORIENT before asking the user

The interview does not begin with a questionnaire. It first checks the repository, prior lessons, and any unfinished interview state. The core rule is simple: do not ask a person for a fact the repository can answer.

### 3.1 Repository-first scan

For this case, the first bounded scan finds:

- the synchronous `OrderGateway.submit()` call;
- stable `client_order_id` and merchant-scoped uniqueness;
- a changing `X-Request-Id` but no vendor idempotency header;
- the 600 ms per-attempt observation timeout, separate 2 s end-to-end deadline, and existing `GET` retry policy;
- vendor-documented retry classes, key behavior, and 24-hour retention; and
- the commit-then-close fixture.

This already prevents several low-value user questions. The interview does not ask the user which status codes the vendor documents, how the local unique index is shaped, or what the current timeout is. It asks only where the evidence leaves a consequential product or policy choice.

### 3.2 Zero-cost open-world hypotheses

Before selecting analysis lenses, the model records up to three missing possibilities. Each starts as `origin: open-world`, `model-prior`, `assumption`, and `hypothesis-only`.

| Hypothesis | Applicability question | Falsifier | Evidence route | Initial status |
| --- | --- | --- | --- | --- |
| The upstream may commit before the caller observes failure. | Can `POST /orders` commit before a timeout or connection reset reaches the client? | The operation and response delivery are atomic, or stable-key idempotency is already wired. | Vendor contract, call site, commit-then-close fixture, authorized production traces if still needed. | Hypothesis only; no credit. |
| Retries may amplify a brownout and exhaust the checkout deadline. | Can many requests retry concurrently while the vendor is degraded? | Traffic is serialized elsewhere, or this call is outside the interactive deadline. | Deadline configuration, metrics, retry library behavior, bounded load scenario. | Hypothesis only; no credit. |
| Automatic retry may escape the invocation and outlive the vendor retention window. | Can any retry introduced by this change run in another invocation or after 24 hours? | All automatic retries are confined to the original 2 s invocation; cross-invocation replay needs a separate durable design. | Call graph, retry lifecycle, vendor TTL contract, support workflow. | Hypothesis only; no credit. |

The change activates several analysis lenses: domain state, goal versus obstacle, reliability quality, controlled language, stakeholder viewpoints, and misuse. The names matter less than their obligations: enumerate states, surface competing outcomes, quantify vague qualities, define deciding predicates, check affected actors, and stress caller-controlled keys.

Because this is an external financial write with reliability consequences, the case selects `full` depth and a ceiling of 20 user decision interactions.

### 3.3 Brain dump

Only after the scan does the visible interview begin:

> Tell me the outcome you want, what you are afraid of breaking, constraints you already know, and any edge case you have seen. I’m treating this as a full interview, up to 20 decision interactions, because it changes an external financial write and reliability behavior.

The user answers:

- checkout must stay synchronous;
- duplicate orders or charges are unacceptable;
- the recurring incident is vendor `503`s; and
- this change must not introduce a queue.

These become separate claims. “No queue” is recorded as a non-goal. “No duplicate charge” is a user-owned product decision, not a fact inferred from the code.

### 3.4 Framing challenge

The protocol challenges the requested mechanism against the outcome:

1. add a retry loop;
2. preserve one logical order across ambiguous transport outcomes; or
3. avoid retry and introduce reconciliation.

The visible restatement is:

> I think the requested loop is a mechanism, not the actual contract. The change should recover from selected transport failures without creating a second logical order or exceeding the current synchronous deadline. A queue or background reconciliation flow is out of scope. Correct this if it changes your intent.

The user confirms. The artifact remains a synchronous behavior change, but its success condition has changed from “eventually gets a response” to “recovers without duplicating the durable business effect.”

## 4. The first ledger says active residual ambiguity is 99

The ledger is the source of truth for what is known, what can still branch implementation, and what blocks a safe handoff.

| ID | Initial claim or gap | Ambiguity score | Impact weight | Status | Initial basis |
| --- | --- | ---: | ---: | --- | --- |
| `F-CURRENT` | Current `POST /orders` makes one attempt. | 0 | 2 | Triangulated | Call site and test. |
| `G-TRANSIENT` | Exact retryable failure set is unclear. | 2 | 3 | Draft | Vendor contract and existing `GET` policy differ around `429`. |
| `G-POST-COMMIT` | Behavior after commit plus lost response is undefined. | 3 | 5 | Blocked | Fixture shows the state is possible. |
| `G-IDEMPOTENCY` | Stable identity across attempts is undefined. | 3 | 5 | Blocked | `client_order_id` exists but is not sent as the vendor key. |
| `G-DUPLICATE` | “At most one order and charge” is not yet a stated invariant. | 2 | 5 | Draft | Financial impact inferred; user authority required. |
| `G-ATTEMPTS` | Attempt count is unspecified. | 2 | 3 | Draft | `GET` default exists but may not govern `POST`. |
| `G-TTL` | Cross-invocation replay behavior after the vendor's 24-hour key window is unresolved. | 3 | 3 | Draft | Vendor documentation defines the TTL; current code retries only inside one 2 s invocation and has no durable replay store or controllable clock seam. |
| `G-KEY-PAYLOAD` | Same key with different payload is undefined locally. | 3 | 3 | Draft | Vendor contract says `409`; local API is silent. |
| `G-CONCURRENCY` | Concurrent requests with the same logical identity are undefined. | 3 | 5 | Blocked | Local uniqueness does not prove upstream behavior. |
| `G-DEADLINE` | Retry behavior within the 2 s deadline is unspecified. | 2 | 3 | Draft | Request configuration. |
| `G-OBSERVE` | Operators cannot distinguish initial calls from retries. | 2 | 2 | Draft | Current logs and metrics. |
| `G-SCOPE` | Whether this becomes an async queue or reconciliation feature is unclear. | 2 | 2 | Draft | Model-generated alternative, not user intent. |

Residual ambiguity is the weighted sum of active, non-deferred gaps. `G-TTL` is still active at this point, so its `3 * 3 = 9` remains in the total:

```text
6 + 15 + 15 + 10 + 6 + 9 + 9 + 15 + 6 + 4 + 4 = 99
```

The number does not claim “99% unknown.” It makes the active risk drivers and their movement visible. Repository evidence may later justify recommending deferral, but evidence alone cannot make that scope decision or remove `G-TTL` from active residual.

## 5. The protocol requires the financial-state question first; the helper makes the arithmetic deterministic

After mandatory breadth or state obligations are clear, `question_score.py` ranks candidates by impact, implementation branch split, uncertainty reduction, coverage, user cost, and redundancy.

The formula is:

```text
impact * branch_split * uncertainty_reduction * coverage
----------------------------------------------------------------
1 + user_cost + redundancy
```

The factors used in this case are explicit rather than reconstructed from the final number:

| Rank | Candidate | Impact | Branch split | Uncertainty reduction | Coverage | User cost | Redundancy | Exact score |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Post-commit lost response | 5 | 5 | 5 | 5 | 3 | 0 | `625 / 4 = 156.25` |
| 2 | Logical-order key | 5 | 4 | 5 | 4 | 3 | 0 | `400 / 4 = 100` |
| 3 | Total attempt ceiling | 3 | 3 | 3 | 3 | 1 | 0 | `81 / 2 = 40.5` |
| 4 | Retryable failure classes | 3 | 4 | 3 | 4 | 3 | 0 | `144 / 4 = 36` |

A representative scorer input and invocation are:

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

```text
## Question Scores

| Rank | ID | Score | Target IDs | Question |
| --- | --- | --- | --- | --- |
| 1 | q-post-commit | 156.25 | G-POST-COMMIT | Post-commit lost response? |
| 2 | q-key | 100.00 | G-IDEMPOTENCY | Logical-order key? |
| 3 | q-attempts | 40.50 | G-ATTEMPTS | Total attempt ceiling? |
| 4 | q-retryable | 36.00 | G-TRANSIENT | Retryable failure classes? |
```

Post-commit semantics remain dominant because they affect a financial invariant, collapse a score-3 gap, cover an unvisited state transition, and split multiple designs. Logical identity ranks next because `G-IDEMPOTENCY` is also a score-3 gap. Under the declared judgments, the attempt ceiling narrowly outranks the failure taxonomy (`40.5` versus `36`): both have impact `3` because each changes behavior and tests, while the attempt question costs less to answer. Neither determines whether the feature can create two orders, so both remain well below the post-commit question.

Backoff parameters are deliberately absent from this scored queue because no ledger gap anchors such a candidate. Only after the critical state, identity, deadline, and attempt gaps settle does the existing `GET` policy support those numbers as an evidence-backed low-risk default in the smart-default batch.

A capable Claude or Codex planner **can** reach the same question. The structural claim is narrower: once this risk is in the ledger, the session runtime rule requires the interviewer to take the highest-ranked askable critical-path question before easier mechanism settings. `question_score.py` makes the supplied judgments and arithmetic deterministic; it cannot detect a missing candidate, repair bad dimension judgments, or independently enforce that the interviewer obeyed the top rank. The runtime rule plus persisted-session review provide that remaining guard.

## 6. The first structured question

The interview shows the evidence, presents a concrete failure sequence, opens several branches, recommends only the branch supported by evidence, and states what would falsify the current model.

> I found that the caller has a stable `client_order_id`, but the gateway does not currently send the vendor's `Idempotency-Key`. Consider this sequence: the vendor creates order `O-481` and charges the customer, then the connection closes before our service receives the response. When the same logical request is retried, what must happen? This would falsify my current model if duplicate creation is acceptable or another system already guarantees reconciliation.

Options:

1. **Return the original order; never create or charge twice — Recommended.** The vendor contract supports stable-key replay, and the local model already has a unique `client_order_id`.
2. **Return an unknown or pending result and do not retry.** This requires a later reconciliation owner and is a scope addition.
3. **Retry as a new order and tolerate a duplicate.** Suggestion only; it conflicts with the stated failure fear.
4. **Other.** The structured interface always leaves a free-form escape hatch.

The user selects option 1. That answer does not immediately erase a weight-5 gap. It must survive pressure, be corroborated by an independent causal source, or be explicitly accepted by the authority that owns the decision.

### Free pressure follow-up

The next prompt asks for a story rather than another abstract choice:

> Walk one concrete outcome. The vendor stored `O-481`, charged once, and the response was lost. Two hundred milliseconds later our service retries. What exact result should the caller receive, what records may exist, and what must never happen?

The user answers:

> The caller should receive `O-481`. There must be one local order, one vendor order, and one charge. The retry must use the same logical key. If the payload changed, it must fail instead of reusing the first result.

The protocol decomposes that rich answer instead of compressing it into “idempotent”:

1. a retry returns the same successful `order_id`;
2. at most one local order exists;
3. at most one vendor order and one charge exist; and
4. the same key with a different payload is rejected.

This story-eliciting pressure follow-up is free under the protocol's two-free-follow-ups-per-thread rule. More importantly, it gives later acceptance criteria observable nouns and counts.

## 7. Evidence is counted by causal independence and authority

The interview does not count file names or channel labels as votes.

| Evidence | Channel | Independence group | Authority and credit |
| --- | --- | --- | --- |
| `OrderGateway.submit()` call site | `from-code` | `repo:order-call-site` | Establishes current behavior: one attempt and no vendor key. |
| Unique index on `(merchant_id, client_order_id)` | `from-code` | `repo:order-schema` | Establishes the local uniqueness boundary. |
| Vendor OpenAPI idempotency section | `from-docs` | `vendor:idempotency-contract` | Establishes the vendor's documented key behavior and 24-hour TTL. |
| Generated SDK comment copied from the OpenAPI | `from-code` | Still `vendor:idempotency-contract` | Adds no independence credit because it is derived from the same root. |
| User decision: one order and one charge | `from-user` | `user-dependency:G-DUPLICATE` | Has product-decision authority. It does not establish current code behavior. |
| Commit-then-close fixture observation | `from-scenario` | `scenario:commit-close` | Establishes that the ambiguous sequence occurs in this surrogate. |
| Model prior: POST retries can duplicate writes | `assumption` | `model-prior:post-retry` | Generates a search path only; receives no settlement credit. |

The distinctions prevent common category errors:

- code establishes what the system does now; it cannot decide what the business should want;
- the user can own desired behavior without being treated as an authoritative source for current implementation details;
- copied docs and generated code remain one causal source;
- an owner can explicitly accept a single-source decision, but that does not manufacture a second witness; and
- a scenario proves what its fixture demonstrated, not what the vendor always does in production.

Contradictory sources remain `Contested`. The interviewer cannot quietly choose the source that makes the current plan easier.

## 8. The rest of the interview follows implementation branches

The next questions are not a generic checklist. Each follows from the current ledger, repository facts, and the previous answer.

### 8.1 What is one logical order?

The repo has a merchant-scoped unique key, while `X-Request-Id` changes per transport attempt. The visible question is:

> The repo has a unique `(merchant_id, client_order_id)`, while `X-Request-Id` changes when an HTTP request is repeated. Which value defines one logical order across retries?

Options:

1. **`(merchant_id, client_order_id)` — Recommended.** It is stable across attempts and matches local uniqueness.
2. `X-Request-Id`.
3. A random key generated for every attempt.
4. Other.

The decision fixes observable identity while leaving serialization and hashing mechanics to the builder.

### 8.2 Which failures, including `429`, may consume the deadline?

The vendor contract already answers most status-code facts. The user is asked only for the unresolved policy branch:

> The vendor marks connect timeout/reset and `502`, `503`, and `504` as transient. It also returns `429` with `Retry-After`. If that delay plus the full 600 ms next-attempt observation budget fits inside the remaining 2-second checkout deadline, should we retry it?

Decision:

- retry connect timeout/reset, `502`, `503`, and `504`;
- retry `429` only if `Retry-After` plus the full 600 ms next-attempt observation budget fits;
- do not retry other `4xx` responses; and
- never start a sleep or attempt that cannot fit inside the remaining deadline.

The repository answered the documented classes and deadline value. The user decided how server-directed waiting interacts with the product deadline.

### 8.3 Deadline and attempt count stay separate because they are critical and interacting

`G-DEADLINE` and `G-ATTEMPTS` both start at ambiguity score `2` with impact weight `3`. Either decision changes runtime behavior and tests, and their answers constrain each other. They therefore remain critical-path gaps: neither belongs in a low-risk smart-default batch, and they cannot share the optional multi-question critical round-trip because they are not independent.

The deadline question comes first as its own structured question:

> The repository has two clocks: a 600 ms observation timeout for each vendor attempt and a hard 2 s end-to-end deadline for the checkout invocation. Which boundary governs starting a retry?

Options:

1. **The 2 s deadline wins; start another attempt only when its full 600 ms observation budget plus required delay fits — Recommended.** This preserves the existing caller contract and keeps the two clocks explicit.
2. Start whenever the attempt count permits, even if the attempt can finish after 2 s. This changes the caller-visible deadline.
3. Dynamically shorten the next attempt below 600 ms. Suggestion only; the repository has no evidence that a shorter observation window is useful.
4. Other.

The user selects option 1. Because this settles a weight-3 gap, the protocol applies pressure before lowering it below score `2`:

> At `t=1.55 s`, a retry is otherwise eligible and its delay is `100 ms`, leaving only `350 ms` before the end-to-end deadline. Do we start it even though the configured per-attempt observation budget is `600 ms`?

The user answers no: return the mapped dependency-unavailable result without sleeping or starting that attempt. This makes “fits” a decidable predicate rather than a vague instruction to “respect timeouts.”

Only then does the interview ask `G-ATTEMPTS` as a separate structured question:

> Subject to that hard deadline rule, what is the maximum number of total vendor attempts in one invocation?

Options:

1. **Three total attempts — Recommended.** This matches the existing `GET` policy, while the deadline can still reduce the realized count.
2. Two total attempts.
3. Continue until the 2 s deadline with no numeric ceiling. Suggestion only; this can amplify a brownout.
4. Other.

The user selects three. The pressure scenario checks the interaction rather than merely repeating the number:

> The first attempt reaches its 600 ms observation timeout, the first retry starts at roughly `800 ms`, and a later delay means a third full 600 ms attempt no longer fits. Is “three” a target or a ceiling?

The user confirms it is a ceiling: run fewer attempts when the end-to-end predicate rejects the next one. The sequence matters. Had the attempt question been accepted in a batch first, “three attempts” could easily have been misread as mandatory even when the last attempt violates the 2 s contract.

### 8.4 Only low-risk mechanism defaults are batched

After the critical state, deadline, and attempt decisions settle, the interview can batch defaults whose answers no longer constrain those branches. Every recommendation names its repository evidence:

> Proposed low-risk defaults:
>
> 1. **Backoff:** based on the existing `GET` retry policy, use full-jitter exponential delays with 100 ms base, exponent 2, and a 1 s cap.
> 2. **Key serialization:** based on the existing versioned canonical tuple serializer, serialize `(merchant_id, client_order_id)` with that utility before producing the vendor-safe key; do not invent delimiter concatenation.
> 3. **Observability:** based on existing dependency telemetry, emit attempt number, final outcome, failure class, and an idempotency-key hash—never the raw key.
>
> Accept all, or correct individual items.

The user accepts. Attempt count and deadline behavior are deliberately absent from this batch. These defaults are recommendations because local evidence supports them and their remaining choices are low risk after the critical contract has settled, not because the LLM invented a familiar retry recipe.

### 8.5 Same key with a different payload

The vendor returns `409`, but the local contract still needs a response and a definition of equality:

> When the same logical key is reused with a different payload, should the API expose a deterministic conflict, return the first order, or create a new order?

The user chooses a local `409 IDEMPOTENCY_KEY_REUSED`, no further vendor call, and logging of the key hash plus payload fingerprints without payload contents.

The answer creates another question: does “same payload” mean identical JSON bytes? The settled predicate is equality of canonical business fields after normalization. Field order and harmless representation differences do not change identity.

### 8.6 Cross-invocation replay is a deferred risk, not a current requirement

The repository now answers the reachability question but not the scope decision: current retries run only inside one invocation with a 2 s deadline, while durable cross-invocation replay detection would require a new vendor-key store and controllable clock seam. The interview must not pretend that stable-key reuse alone can detect “after 24 hours,” and it must not silently defer the active `G-TTL` gap merely because the missing capability is outside the current path.

The interviewer therefore asks a visible structured scope question:

> Current code retries only inside the original 2-second invocation. Detecting a replay across invocations or beyond the vendor's 24-hour retention window requires a durable original-order store plus a controllable clock seam that this change does not add. How should `G-TTL` be handled?

Options:

1. **Defer to Payments Platform review on 2026-08-15 — Recommended.** Adding durable state and time control would be a scope addition to this invocation-scoped retry change; record the owner, date, and missing proof explicitly.
2. **Expand the current scope.** Scope addition: design and implement the durable store, retention policy, cross-invocation behavior, and clock-controlled verification before handoff.
3. **Other.** Supply a different owner, date, or boundary.

The user selects option 1. Only this explicit decision changes `G-TTL` from `Draft` to `Deferred`, removes its 9 points from active residual, and moves it into Deferred Risks. It does not create a current implementation requirement.

The current scope records one boundary: **no automatic resubmit beyond the original invocation**. Durable cross-invocation replay detection and proof are deferred instead of smuggled into this patch:

| Deferred risk | Owner | Review date | Reason |
| --- | --- | --- | --- |
| Define cross-invocation replay behavior, durable original-order proof, retention semantics, and a testable store/clock seam. | Payments Platform | 2026-08-15 | Implementing or promising a detectable 24-hour replay would require new persistent state and time control outside the invocation-scoped retry change. |

Until that review produces a separate contract, the retry code neither auto-resubmits nor claims to return a special 24-hour conflict that it cannot reliably detect.

### 8.7 Concurrent callers

> Two workers receive the same `(merchant_id, client_order_id)` at nearly the same time. What outcome must be observable?

The accepted behavior is:

- identical payloads converge on one `order_id`;
- at most one vendor order and one charge exist; and
- different payloads cannot both succeed—one result wins and the other returns a deterministic conflict.

The implementation may use a local constraint, distributed lock, or vendor idempotency mechanism. The interview fixes behavior, not an internal technique.

## 9. The vague request becomes five controlled requirements

Each requirement has a trigger, condition, response, and observable failure boundary.

```text
REQ-001
Given a POST /orders request with merchant_id M and client_order_id C
When an attempt ends in connect timeout, connection reset, 502, 503, or 504
Then the gateway may make at most two further attempts
And every attempt shall use the same vendor Idempotency-Key derived from (M, C)
And all automatic retries shall remain inside the original invocation.

REQ-002
Given the vendor committed order O for (M, C)
And the response was lost before the gateway observed it
When the gateway retries within the same invocation
Then the caller shall receive O
And exactly one local order, one vendor order, and one charge shall exist.

REQ-003
Given an idempotency key previously used with canonical payload fingerprint P1
When the same key is presented with fingerprint P2 where P1 != P2
Then the service shall return 409 IDEMPOTENCY_KEY_REUSED
And shall not perform another vendor POST.

REQ-004
Given two concurrent requests with the same (M, C) and equal canonical payloads
When both reach the order gateway
Then all successful responses shall contain the same order_id
And the vendor order count and charge count for that logical order shall each be one.

REQ-005
Given a 429 response with Retry-After D
And a 600 ms per-attempt observation budget
When D plus 600 ms fits within the remaining 2-second end-to-end deadline
Then the gateway may retry after D
Otherwise it shall stop without sleeping or starting another vendor attempt
And return the mapped dependency-unavailable result.
```

Cross-invocation replay is intentionally absent from these current implementation requirements. Its owner, review date, prerequisite durable proof, and reason remain in Deferred Risks; the implementation must not synthesize a detectable 24-hour policy without that future contract.

The most important verification is not “the HTTP client was called twice.” It reproduces the ambiguous business outcome:

```text
VER-ORDER-COMMIT-DROP
1. Start a stateful fake vendor that records created orders and charges.
2. Send (M, C) with canonical payload P and stable outbound key K.
3. On the first call, commit vendor order O and one charge, then drop the response.
4. Allow the gateway to retry.
5. Capture the outbound key and payload of every attempt and the final response order_id R.
6. Pass only if all attempts used K, R == O, vendor_order_count(K) == 1,
   vendor_charge_count(K) == 1, and the local order count for (M, C) is 1.
```

This oracle cannot be satisfied by a mock that always returns the same ID while the real client sends a new key on each attempt. It observes the outbound request and durable effects.

## 10. A fresh implementer still finds holes

The first draft is given to a fresh implementer with the repository, but without the interview conversation.

At L0—static inspection plus an independent reading—it reports four blocking questions:

1. Is `client_order_id` global or merchant-scoped?
2. Does equal payload mean raw JSON, normalized JSON, or selected business fields?
3. What happens when `Retry-After` exceeds the remaining deadline?
4. Can the test pass by making a mock return one order even when the real client emits a different key per attempt?

The repository answers the first: uniqueness is `(merchant_id, client_order_id)`. That is synthesis loss in the draft, not a reason to ask the user. Questions 2 and 3 require explicit contract decisions. Question 4 rebinds verification from mock call count to the real outbound request plus a stateful vendor fake.

The protocol always requires an explicit, resolved decision for the least capable probe level from L0 through L3. In this case, L0 cannot observe race behavior, so this case selects L1 as the least adequate level: two independently authored behavioral stubs.

- **Producer A:** a database-backed fake commits and then closes the socket. It demonstrates that a new key per attempt creates two durable rows.
- **Producer B:** a barrier-based concurrent fake interleaves two callers. It demonstrates that “use the same key” is insufficient unless different-payload reuse has an explicit conflict rule.

These producers use different failure mechanisms and causal roots. They are still surrogates, not proof of vendor production behavior.

The material divergence adds a new `origin: probe` gap. Mechanically, that:

- clears the dry-sweep streak;
- makes the last checkpoint stale;
- invalidates the reviewed Build Contract; and
- returns the session to the interview loop.

After merchant scope, payload equality, conflict behavior, and the observable oracle are corrected, one targeted confirmation reruns the bounded probe. If it finds no new divergence, that neutral result earns **no completeness credit**. It only closes the bounded probe sequence. Absence of a new finding is not evidence that no other failure exists.

## 11. Representative interview trace

The useful trace is not a list of phases. It is the evidence-to-question transition at each turn:

| Step | New evidence or user decision | LLM hypothesis and candidate generation | Protocol routing | Visible next interaction |
| ---: | --- | --- | --- | --- |
| 1 | Code shows a mutable `X-Request-Id`; the fixture can commit then close. | “A failed response may hide a successful write” becomes an applicability question and a falsifier, not a fact. | `G-POST-COMMIT` enters at score 3, weight 5; scorer ranks it `156.25`. | Ask the post-commit outcome question before retry settings. |
| 2 | User chooses one order and one charge. | Candidate interpretations still include “same HTTP response,” “same durable order,” and “later reconciliation.” | Critical answer requires pressure before the gap can fall below score 2. | Ask for one concrete result, record count, charge count, and forbidden outcome. |
| 3 | Pressure story requires the original `order_id`, one local row, one vendor row, one charge, and changed-payload rejection. | “Same logical request” now needs an identity predicate. | Repo evidence makes `(merchant_id, client_order_id)` recommended; per-attempt `X-Request-Id` is falsified as logical identity. | Ask the structured logical-key question. |
| 4 | Vendor docs identify retryable classes; code exposes 600 ms and 2 s as different clocks. | `429` and `Retry-After` create a remaining-budget branch. | `G-DEADLINE` is score 2, weight 3 and therefore a due critical obligation; in the scored candidates, attempt ceiling is `40.5` and retryable classes are `36`. | Ask the deadline-boundary question, then pressure it at `t=1.55 s`. |
| 5 | User says the hard deadline wins and a full 600 ms attempt budget must fit. | Attempt count is now constrained by the timing predicate. | `G-ATTEMPTS` remains a separate score-2, weight-3 question and narrowly outranks the failure taxonomy under the declared judgments. | Ask for a maximum, then pressure whether three is a ceiling or a mandatory count. |
| 6 | User confirms a ceiling of three; actual count may be lower. | Backoff shape, tuple encoding, and telemetry no longer change critical semantics. | Only these low-risk, independent, evidence-backed defaults enter a smart-default batch. | Offer backoff, serialization, and observability defaults with their repository evidence. |
| 7 | Cross-invocation replay requires a store and controllable time that do not exist; current retries end with the 2 s invocation. | A model may imagine a 24-hour conflict, but the current system cannot prove the predicate. | Keep `G-TTL` Draft until the user chooses between a scope addition and explicit deferral. | Ask the structured scope question; the user selects Payments Platform deferral for 2026-08-15, then `G-TTL` moves to Deferred Risks. |
| 8 | Fresh implementer spots merchant scope, payload equality, oversized `Retry-After`, and a gameable mock. | The contract that sounded complete has observable synthesis loss. | Select L1 as this case's least adequate L0-L3 probe; material divergence invalidates readiness. | Reopen the affected questions and verification oracle. |

This is why the loop is structurally stronger than an unpersisted planner conversation. The LLM still proposes the hypotheses and factor judgments, but the session state determines which unresolved branch must be handled next, which answer needs pressure, which questions cannot be batched, and which new evidence invalidates prior readiness.

## 12. Static ownership boundaries

The implementation separates responsibilities with a small number of durable artifacts:

| Owner or surface | Owns | Must not claim |
| --- | --- | --- |
| Interview runtime | Repository-first evidence, ambiguity ledger, due obligations, question routing, pressure, sweeps, and the resolved least-capable L0-L3 probe decision. | That model priors are facts, that scoring found every candidate, or that a neutral probe proves completeness. |
| `question_score.py` | Deterministic validation, arithmetic, and ordering for the candidate JSON it receives; here it yields `156.25`, `100`, `40.5`, and `36` in rank order. | Candidate completeness, correct human dimension judgments—including the behavior/tests impact anchor—or independent enforcement that the top-ranked question was asked. |
| Reviewed contract | Stable `REQ` and `VER` identities plus the digest of the human-reviewed behavior. | Implementation mechanics or behavior outside the reviewed/deferred scope. |
| External Claude, Codex, CI, or human builder | Product edits, runtime tools, worktrees, permissions, and implementation choices allowed by the contract. | Authority to rewrite the contract or award itself specification completeness. |
| Returned evidence and fresh postmortem | Compare promised behavior, actual changes, decisions, and observable proof; register escaped requirements. | Permission to erase an earlier miss by rewriting interview history. |

The boundary is deliberate: the interviewer cannot silently implement missing decisions, and the builder cannot silently redefine the contract it is judged against.

## 13. Claude and Codex: what a strong model can do versus what the protocol must do

The baseline deserves a fair comparison. Codex CLI can inspect a repository, plan, edit, and run tools; it supports skills and a dedicated planning surface. See the [official Codex CLI guide](https://learn.chatgpt.com/docs/codex/cli) and [current Codex feature documentation](https://learn.chatgpt.com/docs/features). Claude Code also supports read-only planning and an Explore → Plan → Implement → Commit workflow. See [Claude Code permission modes](https://code.claude.com/docs/en/permission-modes) and [Claude Code best practices](https://code.claude.com/docs/en/best-practices).

A strong model in either environment **can** ask every question in this case. A careful team can reproduce much of the method with custom instructions, skills, reviewers, and CI. `ultimateinterview` is not evidence of superior model intelligence and is not universally superior to native planning.

Its advantage is the difference between **can** and **must**:

| A strong Claude or Codex planner can… | `ultimateinterview` must… |
| --- | --- |
| Recall that POST retries need idempotency. | Record that recall as a hypothesis with an applicability question, falsifier, and evidence route; model prior receives no fact credit. |
| Inspect the repo before asking questions. | Prune every question the repo can answer and preserve the evidence source separately from user intent. |
| Ask about duplicate orders. | Rank the post-commit state question above retry count and backoff once its impact and ambiguity are in the ledger. |
| Follow up on an important answer. | Pressure-test critical answers or require independent evidence or explicit owner authority before lowering the gap. |
| Mention identity, cross-invocation replay risk, concurrency, and observability. | Keep active and deferred sibling tracks in persisted state and use sweeps and locality correction to prevent a locally deep conversation from forgetting them. |
| Write detailed acceptance criteria. | Bind stable `REQ` and `VER` identities to a reviewed digest and reject stale or substituted contracts. |
| Ask another agent to review the plan. | Give a fresh implementer only the contract, treat material divergence as a new gap, and invalidate stale readiness state. |
| Run tests and summarize success. | Accept only a typed executor return and evidence bound to the exact contract; the executor cannot award itself specification completeness. |
| Learn informally from a failure. | Classify the escaped requirement under a stable identity and feed the lesson into the next orientation. |

The duplicate-order case is persuasive only if the protocol changes the sequence of work:

1. remembered idempotency advice cannot masquerade as repository evidence;
2. financial-state semantics outrank easy mechanism settings;
3. a concrete pressure story turns “safe retry” into observable counts and identities;
4. independent challenge can reopen a spec that already sounded complete; and
5. the build is judged against an oracle written before implementation choices were known.

Native planners can be prompted to do those things. The protocol makes them persistent, ordered, and fail-closed across context compaction, handoff, and different executor runtimes.

## 14. Why the interview deliberately does not own product execution

The separation is central. If one context interviews, implements, and judges whether the spec was sufficient, three signals collapse:

1. a missing requirement can be silently filled during coding;
2. an implementation choice can later be described as if the spec required it; and
3. the implementer can write a test that satisfies the wording while avoiding the real behavior.

In this case, an executing interviewer might choose a process-local lock and make unit tests pass without revealing that two service replicas can still race. A separate builder must either implement the written cross-replica behavior or return a deviation. That preserves a measurable counterfactual:

> Could a fresh implementer build the same observable behavior from the reviewed contract alone?

There is also a practical boundary. Claude, Codex, CI systems, and human teams already own tools, permissions, worktrees, sandboxes, deployments, and runtime-specific recovery. Rebuilding each execution environment would create an adapter treadmill without directly improving requirement discovery.

The interview still owns two narrow execution surfaces:

- bounded L0–L3 probes that measure one unresolved semantic question; and
- `safe-auto` evidence capture for predeclared, allowlisted, repo-local verification commands.

`safe-auto` cannot edit product code, deploy, choose implementation mechanics, or run an arbitrary shell command. Work outside that boundary belongs to the external executor or to an execution-owning control plane. Regulated attestation, deployment rollback, persistent experiments, production telemetry custody, and hard sandbox guarantees still require such a control plane; artifact schemas alone cannot make an arbitrary executor trustworthy.

## 15. Why a closed loop is still necessary

Pre-build discovery cannot prove that uncertainty is zero. The external builder therefore returns `execution-return.json`, changed surfaces, `decisions.jsonl`, requirement and verification outcomes, and hash-bound evidence. A fresh postmortem compares the promise, implementation, and proof.

Suppose stable keys prevent duplicate order rows but fulfillment publishes twice. The original contract protected the primary table and omitted another durable side effect. The postmortem records that escape—even if no existing category fits—and the lesson changes the next interview's open-world orientation from “one order row” to “all externally visible side effects.”

The loop is not interesting because artifacts point in a circle. It matters because execution can falsify the interview's model without allowing the interviewer to rewrite history.

## 16. Stop and handoff are blocker-based

The session stops when, and only when:

- every score-2 or score-3 gap is settled or explicitly deferred with an owner and date;
- two fresh breadth sweeps find no new implementation-changing gap;
- the mandatory falsification checkpoint confirms the current model;
- the probe decision is resolved at the least capable L0-L3 level; this case selected L1 as least adequate;
- a fresh implementer has no remaining blocking ask;
- gameable criteria are rebound to real observable surfaces; and
- the deterministic implementation gate passes.

The handoff is deliberately small at its boundary:

- `handoff.md` contains the human-readable agreement;
- `build-contract.json` contains its strict, digest-bound `BuildContract v1`; and
- the builder appends unforced choices to `decisions.jsonl` and returns `execution-return.json` with evidence.

For this case, `handoff.md` must also carry the user's explicit `G-TTL` deferral under Deferred Risks: Payments Platform owns it, the review date is 2026-08-15, and durable store-plus-clock proof is the prerequisite. Without that recorded owner/date decision, `G-TTL` remains an active score-3 gap and stop is blocked.

The builder may choose a retry library, lock mechanism, module decomposition, or hashing implementation. It may not silently change retryable conditions, identity scope, duplicate behavior, the invocation-only retry boundary, the deferred cross-invocation risk, the deadline, or the verification oracle.

## 17. When the overhead is worth paying

Use the full method when several conditions are present:

- a wrong assumption can corrupt money, data, permissions, or compatibility;
- the change crosses a network, transaction, lifecycle, concurrency, or ownership boundary;
- the repository is old, distributed, or unfamiliar;
- implementation will move to another person, session, model, or runtime;
- acceptance can be gamed by a shallow mock or self-authored test; or
- the team needs evidence and decisions to survive context compaction and handoff.

Use a normal planner or a minimal interview for a typo, a reversible local refactor, a mechanical dependency bump, or a change already fully constrained by an authoritative test suite. The protocol is valuable when the cost of a false premise is greater than the cost of exposing it.

The main lesson from the duplicate-order incident is not “always ask about idempotency.” That would be another fixed checklist. It is:

> Use the LLM to generate dangerous possibilities, force each important possibility through local evidence and decision authority, ask the highest-consequence question first, and preserve enough separation for a fresh builder or runtime result to prove the interview wrong.
