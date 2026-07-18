---
name: clarify-requirements
description: Turn ambiguous product, software, workflow, or change requests into an agreed and testable contract before planning or implementation. Use when requirements are vague, behavior or scope has multiple plausible interpretations, acceptance criteria are missing, consequential defaults would otherwise be invented, or the user asks for an interview, clarification, specification, PRD, or implementation handoff.
---

# Clarify Requirements

Resolve only ambiguity that can materially change the result. Do not implement unless the user separately authorizes implementation.

## Build the decision map

1. Restate the requested outcome in one sentence.
2. Inspect user-authorized context for answers that are safely discoverable. Do not ask the user to repeat facts already established.
3. List plausible interpretations privately. Treat a choice as material when it changes observable behavior, scope, safety, compatibility, cost, reversibility, or acceptance.
4. Track each material decision as `confirmed`, `inferred`, or `open`, with its evidence. Never silently default an open material decision.

Consider these lenses only when relevant: actors and permissions; inputs and outputs; happy path; edge, failure, and misuse behavior; data lifecycle; compatibility; operational constraints; rollout and rollback; acceptance evidence.

## Interview

Ask the highest-leverage open question first. Ask one bounded decision per turn unless the user explicitly prefers batching.

For each question:

- explain in one short sentence why the answer changes the result;
- offer two or three concrete, mutually exclusive options when the space is known;
- recommend one option and state its tradeoff when evidence supports a recommendation;
- accept a free-form answer;
- update the decision map before selecting the next question.

Do not ask about low-impact preferences prematurely. Do not convert examples into requirements, infer permission for destructive behavior, or widen the requested scope. If the user cannot decide, record an explicit assumption only after explaining its consequence and obtaining approval.

## Challenge the emerging contract

Before closing, test it against one representative happy path, edge case, failure case, and misuse case when applicable. Reopen only a material decision exposed by this challenge.

## Close

Stop when every material decision is confirmed or explicitly approved as an assumption and the acceptance criteria can distinguish success from failure. More questions are not evidence of a better interview.

Return a compact contract containing:

- outcome and success measure;
- in-scope and out-of-scope behavior;
- confirmed decisions and approved assumptions;
- failure, edge, and misuse behavior where relevant;
- constraints and acceptance checks;
- unresolved non-blocking items;
- whether implementation is authorized.

Use [references/contract-template.md](references/contract-template.md) when a durable contract artifact is requested.

Reflect the contract back to the user and request approval or correction. Label anything not confirmed by the user or authoritative evidence. Preserve the user's terminology and distinguish `must`, `should`, and `could`.
