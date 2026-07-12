# docs — index

Documentation for the `ultimateinterview` closed loop, organized by topic. The guide follows a deep retry interview from an ambiguous reliability request to a reviewed contract and pre-implementation verification oracle, while keeping product execution with an independent external builder. The English guide is the authoritative entry point; the `.ko`/`.hi` files are translations.

## guide/ — user-facing

| Doc | What it is |
| --- | --- |
| `guide/ultimateinterview-closed-loop-guide.md` | The user guide: a deep retry interview that exposes an ambiguous commit boundary, produces an execution-independent reviewed contract, and fixes the verification oracle before an external builder begins. **Start here.** |
| `guide/ultimateinterview-closed-loop-guide.ko.md` | Korean translation (English is authoritative). |
| `guide/ultimateinterview-closed-loop-guide.hi.md` | Hindi translation (English is authoritative). |
| `guide/ultimateinterview-conference-talk.html` | Companion conference-talk deck for the English guide. |
| `guide/ultimateinterview-conference-talk.ko.html` | Korean companion deck (English guide is authoritative). |
| `guide/ultimateinterview-conference-talk.hi.html` | Hindi companion deck (English guide is authoritative). |

## reference/ — current, authoritative

| Doc | What it is |
| --- | --- |
| `reference/ultimateinterview-deterministic-readiness-hardening.md` | Current architecture of the deterministic readiness gate and the advisory/deterministic split. |
| `reference/ultimateinterview-vs-planning-interview-loops.md` | Evidence-based comparison of Codex Plan Mode, oh-my-openagent, Superpowers, and `ultimateinterview`, including structural advantages, limits, and the experiment needed to establish discovery-rate superiority. |
| `reference/requirements-gap-discovery.md` | The reusable requirements-gap method (contextual observation, viewpoint matrix, EventStorming, misuse cases, EARS, evidence ledger). Cited by the skill's `comparison.md`. |
| `reference/ultimateinterview-evidence-authority-model-revision.md` | Design note that compresses the proposed unknown-unknown extension into a minimal evidence-scope, counterfactual-discriminator, and authority-routing loop. |

## Runtime store (do not move)

| File | Why it stays at `docs/` root |
| --- | --- |
| `ultimateinterview-lessons.md` | The committed repo-specific lessons store. Its path is hardcoded in `pack_evidence.py` (`DEFAULT_REPO_LESSONS_RELPATH`), read by `orientation.md`, and pinned in a regression fixture. It is runtime data, not a document to file away — moving it breaks the loop. |

## archive/ — superseded development history and completed handoffs

Frozen records kept for provenance. Not needed to use or maintain the loop. Development-history series in order: `requirements-gap-discovery` → `improvement-proposal` → `research-synthesis` → `hardening-review` → `postmortem-design` → `council-review`. (Note: internal `docs/…` path references inside these frozen docs are historical and may point at pre-reorganization locations.)

| Doc | Kind |
| --- | --- |
| `archive/ultimateinterview-research-basis.md` | Research history |
| `archive/ultimateinterview-research-synthesis.md` | Research history |
| `archive/ultimateinterview-improvement-proposal.md` | Development history |
| `archive/ultimateinterview-hardening-review.md` | Development history / review |
| `archive/ultimateinterview-postmortem-design.md` | Development history |
| `archive/ultimateinterview-council-review.md` | External council review record |
| `archive/ultimateinterview-three-arm-benchmark.md` | Benchmark record |
| `archive/ultimateinterview-epistemic-protocols-handoff.md` | Completed implementation handoff |
| `archive/ultimateinterview-followups-handoff.md` | Completed implementation handoff |
| `archive/ultimateinterview-refine-handoff.md` | Completed implementation handoff |
| `archive/ultimateinterview-postmortem-closed-loop-handoff.md` | Completed handoff; design background cited by the guide |
| `archive/ouroboros-evaluate-skill-and-mcp.md` | Verbatim source snapshot of the ouroboros evaluate skill (superseded by live code) |
