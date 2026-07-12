# Agent-system reliability patterns: enforced behavior vs architecture prose

Research date: 2026-07-10. Read-only inspection. Search coverage: 20+ varied web/GitHub queries, 9 shallow-cloned OSS repositories, official documentation, source, tests, and issue counter-searches.

## Executive result

Reliable agent systems do not trust a model's narrative that a tool succeeded. The strongest implementations separate proposal, authorization, execution, receipt validation, persistence, and evaluation. Each boundary is typed and fail-closed, and replay is explicitly treated as at-least-once wherever external side effects can occur.

The central failure pattern is configuration masquerading as enforcement. A framework may expose guardrails, approvals, sandboxes, checkpointing, or traces while leaving them optional, scoped to only some tool types, bypassable, or unsuitable for security/audit purposes.

## Pinned observations

### 1. Typed tool receipts are strongest when consumers validate, not merely producers

- MCP 2025-06-18 specifies `outputSchema`: servers **MUST** conform but clients only **SHOULD** validate. This is portable protocol intent, not universal client enforcement: [spec @ `2058728`](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/2058728385da440bf9424952bb7287a8b9f08194/docs/specification/2025-06-18/server/tools.mdx#L297-L309).
- The current MCP Python SDK v2 pre-release goes further: after every non-error tool call it refreshes the listed tool schema, rejects missing `structuredContent`, and runs `jsonschema.validate`, raising on invalid content: [client enforcement @ `1216c53`](https://github.com/modelcontextprotocol/python-sdk/blob/1216c536937819070981e63177b258b79a615bfd/src/mcp/client/session.py#L1001-L1044). Executable tests prove rejection of wrong types and missing structured output: [tests](https://github.com/modelcontextprotocol/python-sdk/blob/1216c536937819070981e63177b258b79a615bfd/tests/client/test_output_schema_validation.py#L36-L89).
- Applicability limit: validation is skipped for `isError` results, and Python SDK v2 is explicitly pre-release; stable v1 behavior must not be inferred from v2 source. Error payloads remain evidence to classify, not typed success receipts.
- OpenAI Agents SDK likewise constructs a Pydantic `TypeAdapter`, strictens JSON Schema, and validates final output with `strict=True`, raising `ModelBehaviorError`: [runtime code @ `0885933`](https://github.com/openai/openai-agents-python/blob/08859339ee3a7cd6529e9a86f85a1be2d6dc4a6c/src/agents/agent_output.py#L79-L169).

**ultimateinterview mapping:** retain the typed build contract, but add a typed `VerificationReceipt` for every claimed check: `operation_id`, canonical command/tool name and args digest, capability/sandbox profile, start/end, exit/status, stdout/stderr artifact digests, environment/version, and linked ledger IDs. A prose statement such as "tests passed" must never satisfy the implementation gate without a validated receipt.

### 2. Tool mediation must cover every execution path

- OpenAI tool guardrails can run before and after `function_tool` execution, but the official docs explicitly exclude handoffs, hosted tools, built-in computer/shell/apply-patch/local-shell tools, and `Agent.as_tool()`: [guardrail scope @ `0885933`](https://github.com/openai/openai-agents-python/blob/08859339ee3a7cd6529e9a86f85a1be2d6dc4a6c/docs/guardrails.md#L54-L67). A system-level statement "we use Agents SDK guardrails" therefore does not imply universal mediation.
- PydanticAI's `ApprovalRequiredToolset` enforces approval immediately before dispatch by raising when the exact call is unapproved: [code @ `3adb9b0`](https://github.com/pydantic/pydantic-ai/blob/3adb9b0260383d0f9f2b2a9433f07e1ecfc768c1/pydantic_ai_slim/pydantic_ai/toolsets/approval_required.py#L15-L32). Deferred approval results use discriminated typed unions keyed by tool-call ID: [receipt types](https://github.com/pydantic/pydantic-ai/blob/3adb9b0260383d0f9f2b2a9433f07e1ecfc768c1/pydantic_ai_slim/pydantic_ai/tools.py#L363-L419).
- Yet approval is opt-in (`requires_approval=False` by default), and the Vercel adapter documents that approval responses are client-controlled/trusted unless the application persists IDs server-side: [trust boundary](https://github.com/pydantic/pydantic-ai/blob/3adb9b0260383d0f9f2b2a9433f07e1ecfc768c1/docs/ui/vercel-ai.md#L143-L170).
- Inspect AI has a clean approval interceptor, but if no approval system is registered it returns allow: [default allow @ `0532269`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/approval/_apply.py#L23-L68). Once policies are configured, unmatched/escalated calls fail closed: [policy](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/approval/_policy.py#L35-L81).

**ultimateinterview mapping:** compile every tool surface into one policy registry. Approval binds `(session revision, operation_id, tool_call_id, tool, canonical validated args, capability profile)`; changed args require a new approval. Do not accept a resumed/client-supplied boolean as authorization. Built-in or hosted tools that cannot pass the same interceptor must be proxied or declared outside the trusted path.

### 3. "Sandbox" has several meanings; only OS isolation constrains hostile code

- AutoGen's default factory prefers Docker, but catches any Docker initialization failure and falls back to `LocalCommandLineCodeExecutor`, which executes on the host after only a warning: [factory @ `027ecf0`](https://github.com/microsoft/autogen/blob/027ecf0a379bcc1d09956d46d12d44a3ad9cee14/python/packages/autogen-ext/src/autogen_ext/code_executors/__init__.py#L41-L80). Its Docker executor mounts the workspace read-write and does not set `network_disabled`, `read_only`, `cap_drop`, or `security_opt` in this creation path: [container creation](https://github.com/microsoft/autogen/blob/027ecf0a379bcc1d09956d46d12d44a3ad9cee14/python/packages/autogen-ext/src/autogen_ext/code_executors/docker/_docker_code_executor.py#L525-L550). Docker is a boundary, not automatic least privilege.
- Temporal's Python "workflow sandbox" exists to catch nondeterminism. The project explicitly says it is best effort and **not secure**: [purpose and limits @ `aa26c8d`](https://github.com/temporalio/sdk-python/blob/aa26c8d12e8ebc32294398460acd6656042b393a/README.md#L1094-L1137), [security warning](https://github.com/temporalio/sdk-python/blob/aa26c8d12e8ebc32294398460acd6656042b393a/README.md#L1322-L1336).
- Inspect AI makes sandboxing an explicit `Task` field rather than pretending it is always present; `solver`, `scorer`, `model_roles`, `sandbox`, approval, and resource limits are distinct controls: [Task API @ `0532269`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/_eval/task/task.py#L66-L145). `sandbox=None` remains valid, so the configuration must be checked before execution.
- OpenHands calls Docker a sandbox, but its current container launcher permits configured RW host mounts, optional host networking, and KVM device passthrough; it does not add a read-only root filesystem/capability drop in that call: [launcher @ `e318599`](https://github.com/All-Hands-AI/OpenHands/blob/e3185990ddece1a8ffd31fcc5ece38789436d4c6/openhands/app_server/sandbox/docker_sandbox_service.py#L450-L509).

**ultimateinterview mapping:** label sandbox kinds (`determinism`, `filesystem`, `process`, `network`, `credential`) rather than one boolean. Read-only probes should default to a read-only workspace, no credentials, and network denied unless the evidence channel requires it. Verification commands should run in a disposable snapshot. Any sandbox startup failure must block; never fall back to host execution.

### 4. Durable execution is at-least-once around uncommitted side effects

- LangGraph persists checkpoints and task outputs, but its official durable-execution guidance requires side effects to be wrapped and made idempotent because a task that started but did not commit may execute again. Replay after a checkpoint explicitly re-runs later LLM/API/interrupt nodes: [persistence docs](https://docs.langchain.com/oss/python/langgraph/persistence), [functional API](https://docs.langchain.com/oss/python/langgraph/functional-api), [interrupt idempotency](https://docs.langchain.com/oss/python/langgraph/interrupts).
- An open LangGraph issue provides a minimal reproduction where nesting an interrupting graph causes the prior task to rerun and returns duplicated interrupts: [#6792](https://github.com/langchain-ai/langgraph/issues/6792). A separate historical bug routed concurrent resume values to the wrong tool because interrupts shared an ID: [#6533](https://github.com/langchain-ai/langgraph/issues/6533).
- Temporal enforces deterministic Workflow code and can replay recorded histories to raise on nondeterminism: [workflow contract @ `aa26c8d`](https://github.com/temporalio/sdk-python/blob/aa26c8d12e8ebc32294398460acd6656042b393a/README.md#L720-L734), [Replayer](https://github.com/temporalio/sdk-python/blob/aa26c8d12e8ebc32294398460acd6656042b393a/README.md#L1924-L1955). But its LangGraph integration explicitly says activity-attempt streaming is at-least-once, can duplicate published writes, and consumers must dedupe: [retry semantics](https://github.com/temporalio/sdk-python/blob/aa26c8d12e8ebc32294398460acd6656042b393a/temporalio/contrib/langgraph/README.md#L283-L293).

**ultimateinterview mapping:** add an idempotency envelope to `session_update.py`: caller-supplied operation ID, expected prior revision/hash (compare-and-swap), deterministic per-delta event IDs, and a persisted dedupe index. Replay tests should reconstruct ledger/protocol/questions/build-contract from events and compare digests. External side effects need provider idempotency keys or verify-before-write logic; "atomic file replace" alone prevents torn writes, not duplicate logical operations.

### 5. Evaluators should be separable and rerunnable over recorded evidence

- Inspect's `Task` keeps solver and scorer distinct, supports named model roles, and stores model output, scores, sandbox spec, state store, and an event list per sample: [Task](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/_eval/task/task.py#L66-L145), [typed sample log](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/log/_log.py#L382-L468).
- It can apply new scorers/models to an existing `EvalLog` without rerunning the solver, producing a deep-copied rescored log by default: [post-hoc scoring @ `0532269`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/_eval/score.py#L80-L151), [execution](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/_eval/score.py#L254-L336).
- OpenAI's own monitoring work is a caution against self-certification: monitoring only actions/final outputs underperforms monitoring richer trajectories, and optimizing against a monitor can teach hidden reward hacking. This is evidence for defense in depth, not proof that an LLM judge is reliable: [monitorability study](https://openai.com/index/evaluating-chain-of-thought-monitorability/), [reward-hacking monitor failure](https://openai.com/index/chain-of-thought-monitoring/).

**ultimateinterview mapping:** preserve the fresh-context critic, but make separation auditable: immutable input snapshot digest, reviewer identity/model/version/prompt digest, no write capability, and a typed verdict. Run deterministic schema/predicate/command scorers first; LLM reviewers are additional observations, never the sole gate. Support post-hoc re-evaluation of the same receipt bundle without re-running side effects.

### 6. Traces are observability records, not automatically audit logs

- OpenAI Agents tracing covers generations, tool calls, handoffs, and guardrails, but it can be disabled globally or per run, is unavailable under ZDR, exports asynchronously unless explicitly flushed, and includes sensitive inputs/outputs by default: [tracing @ `0885933`](https://github.com/openai/openai-agents-python/blob/08859339ee3a7cd6529e9a86f85a1be2d6dc4a6c/docs/tracing.md#L1-L51), [sensitive data](https://github.com/openai/openai-agents-python/blob/08859339ee3a7cd6529e9a86f85a1be2d6dc4a6c/docs/tracing.md#L124-L144).
- Inspect `EvalLog` is strongly typed and versioned but explicitly supports post-eval edits (`log_updates`, tags, metadata). That is useful provenance, not tamper evidence: [log model @ `0532269`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/05322696a0f784ec399ef6abbafd3d2a250ea9cc/src/inspect_ai/log/_log.py#L1094-L1144).

**ultimateinterview mapping:** keep operational traces separate from the authoritative ledger. The ledger should have monotonic sequence numbers, previous-record/content hashes, actor and tool identity, timestamp, session revision, and artifact digests; mutations become new events, not silent edits. Redact sensitive tool I/O before durable storage while retaining hashes and classification.

## Failure cases and what they disprove

| Failure evidence | What it disproves | Design response |
|---|---|---|
| AutoGen Docker failure falls back to host execution | "Docker preferred" is not fail-closed isolation | Startup attestation; block on sandbox failure |
| LangGraph #6792 repeats task and interrupt on nested resume | Checkpointing is not exactly-once side effects | Operation IDs, CAS revision, provider idempotency |
| LangGraph #6533 historically misrouted concurrent approval values | A human approved *something* is insufficient binding | Approval keyed to unique call ID plus args digest |
| PydanticAI #3350 historically marked a resumed first-step call approved (fixed by #3355) | Framework approval machinery can have resume-path bugs | Regression test resume/approval invariants; pin versions |
| MCP SEP-834 documented schema-dialect/runtime drift | "JSON Schema" alone is not a portable type contract | Pin dialect/version and conformance-test both ends |
| OpenAI Agents #2664 reports hosted shell call without matching output | Tool-call presence is not execution proof | Require a correlated terminal receipt; orphan => unknown/fail |
| OpenAI traces can be disabled or buffered | Trace availability is not audit completeness | Independent authoritative event ledger |

## Minimal architecture for ultimateinterview

1. **Proposal:** typed operation request with risk/capability classification.
2. **Authorization:** policy engine validates exact canonical args; approval produces a bound receipt.
3. **Execution:** fail-closed sandbox/profile; no host fallback.
4. **Observation:** typed result schema; correlate call ID; distinguish success, tool error, transport loss, timeout, and unknown.
5. **Verification:** deterministic checks over artifacts first, independent critic second.
6. **Commit:** CAS session revision plus idempotency key; append event and artifact hashes atomically.
7. **Replay:** reconstruct state from events; never repeat external effects unless the operation's dedupe contract permits it.
8. **Audit:** immutable event lineage plus redacted observability traces; post-hoc evaluators consume the same snapshot.

## OBSERVATIONS

- All seven requested patterns exist in production-grade frameworks, but none becomes universal merely by selecting a framework.
- The best enforced examples are narrow and explicit: Pydantic validation at a consumer boundary, exact-call approval wrappers, fail-closed configured policy matching, deterministic replay checks, and scorers rerunnable over stored logs.
- Defaults repeatedly weaken guarantees: no approval, optional sandbox, host fallback, client-trusted approval, replayed side effects, disableable traces.

## CLAIMS

- **Supported:** ultimateinterview already has the right substrate family—typed state, atomic writer, fail-closed deterministic gates, append-oriented transcript, fresh reviewer—but needs runtime receipts, exact-call mediation, logical idempotency, sandbox profiles, and audit integrity to turn process instructions into execution guarantees.
- **Supported:** typed artifacts without consumer validation are documentation; sandbox without declared isolation dimensions is ambiguous; checkpointing without idempotency is at-least-once; tracing without completeness/integrity is observability, not audit.
- **Partial:** third-party LLM review can reduce correlated self-review, but it is not an independent ground-truth oracle. Deterministic evidence and replayable receipts must remain authoritative.

## EXPAND

- LEAD: conformance-test current ultimateinterview `session_update.py` with duplicate operation delivery and stale-revision races — WHY: atomic writes may still duplicate logical evidence — ANGLE: repeat identical deltas and concurrent CAS simulation.
- LEAD: enumerate every actual tool surface used by ultimateinterview and mark whether pre/post mediation is enforceable — WHY: hosted/built-in tools commonly bypass framework guardrails — ANGLE: capability registry plus negative tests.
- LEAD: test transcript/decisions truncation and reordering detection — WHY: append-only prose is not tamper evidence — ANGLE: hash-chain/sequence verifier.
- LEAD: build a resume matrix for approval-bound operations (single tool, concurrent tools, nested/delegated critic) — WHY: real frameworks have failed specifically on resumed approval identity — ANGLE: exact call-id/args-digest invariants.
