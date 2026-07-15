# docs — index

Documentation for the compiler-only `ultimateinterview` workflow. The executable source of truth is `.agents/skills/ultimateinterview/` and `.agents/skills/ultimateinterview-postmortem/`; documents here provide design rationale, reusable discovery guidance, and historical provenance.

## Current references

| Document | Purpose |
| --- | --- |
| `ultimateinterview-pitch-deck.html` · `.ko.html` · `.hi.html` | Current English, Korean, and Hindi pitch decks. They explain the shift from exhaustive exception hunting and three-reviewer ceremony to material questions, a deterministic stop rule, implementation decision receipts, and contract-drift detection. |
| `reference/ultimateinterview-creative-discovery-strict-handoff.md` | Design rationale for creative discovery, authority compilation, sealed Build Contracts, substrate-neutral implementation returns, and the separate postmortem boundary. |
| `reference/ultimateinterview-evidence-authority-model-revision.md` | Minimal evidence-scope, counterfactual-discriminator, and authority-routing model. |
| `reference/requirements-gap-discovery.md` | Reusable requirements-gap discovery method independent of the retired session protocol. |
| `sw-eng-howtofindout-unknown-unknowns.md` | General software-engineering treatment of unknown-unknown discovery. |

## Runtime learning store

| File | Purpose |
| --- | --- |
| `ultimateinterview-lessons.md` | Repository-specific postmortem lessons and Fired/Caught history. Keep at this path while the postmortem skill uses it as its durable local lesson store. |

## archive/ — frozen history

Archived documents are superseded design history, completed handoffs, benchmark records, or material tied to the retired ledger/protocol/handoff runtime. They are retained for provenance and are not instructions for the current compiler-only skills.

### Retired closed-loop guide

`archive/ultimateinterview-legacy-closed-loop-guide/` contains the former multilingual closed-loop guide, conference decks, and guide design notes. They describe the removed ledger, protocol, question queue, transcript, readiness scripts, and legacy ExecutionReturn flow.

### Superseded architecture and review documents

| Document | Kind |
| --- | --- |
| `archive/ultimateinterview-deterministic-readiness-hardening.md` | Retired four-file session and readiness-gate architecture. |
| `archive/ultimateinterview-vs-planning-interview-loops.md` | Comparison based on the retired protocol implementation. |
| `archive/ultimateinterview-spec-layer-strategy.md` | Historical strategic synthesis tied to removed lens/ledger machinery. |
| `archive/ultimateinterview-six-lens-epistemic-review.md` | Historical epistemic review of the retired lens system. |
| `archive/ultimateinterview-lens-council-review.md` | Historical council review of residual/lens behavior. |

### Earlier provenance

| Document | Kind |
| --- | --- |
| `archive/ultimateinterview-research-basis.md` | Research history. |
| `archive/ultimateinterview-research-synthesis.md` | Research history. |
| `archive/ultimateinterview-improvement-proposal.md` | Development history. |
| `archive/ultimateinterview-hardening-review.md` | Development history and review. |
| `archive/ultimateinterview-postmortem-design.md` | Historical postmortem design. |
| `archive/ultimateinterview-council-review.md` | External council review record. |
| `archive/ultimateinterview-three-arm-benchmark.md` | Benchmark record. |
| `archive/ultimateinterview-epistemic-protocols-handoff.md` | Completed implementation handoff. |
| `archive/ultimateinterview-followups-handoff.md` | Completed implementation handoff. |
| `archive/ultimateinterview-refine-handoff.md` | Completed implementation handoff. |
| `archive/ultimateinterview-postmortem-closed-loop-handoff.md` | Completed legacy postmortem handoff. |
| `archive/ouroboros-evaluate-skill-and-mcp.md` | Superseded source snapshot. |
