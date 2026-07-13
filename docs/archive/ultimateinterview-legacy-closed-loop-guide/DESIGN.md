# Ultimateinterview guide and deck design

This is the shared visual and writing contract for the English, Korean, and Hindi editions of the guide and the standalone HTML talk.

## 1. Audience and outcome

The primary reader is a software engineer with a computer science degree and roughly three years of professional experience. They can read API, transaction, test, and distributed-systems examples. They should finish able to explain:

- why a plausible LLM plan can encode a false premise;
- how `ultimateinterview` turns model knowledge into testable hypotheses rather than local facts;
- why a precommitted contract is different from an implementation plan;
- why the protocol owns semantics and evidence but deliberately does not own execution; and
- why a post-build loop is required when unknown unknowns cannot be eliminated in advance.

## 2. Narrative contract

Open with one concrete failure, not a feature overview:

> A planner adds exponential-backoff retries to `POST /orders`. Its mock fails before commit, so tests pass. Production loses the first response after `DB COMMIT`; the retry commits a second order.

Follow that failure through cause, design response, execution boundary, and learned rule. No Mina story, school example, or child-oriented metaphor remains.

The writing is technical but readable:

- define a term at first use, then use its standard engineering name;
- prefer causal sentences over slogans;
- show one precise requirement and verification oracle before discussing abstractions;
- distinguish local evidence from a model prior;
- state limits and costs, including cases where the method is not justified;
- compare Claude and Codex fairly, with official sources next to claims; and
- say “stronger specification under ambiguous, high-cost brownfield conditions,” never “universally better.”

## 3. Visual direction

The deck is an engineering incident review on a dark stage: a single failure trace in rose and amber moves toward a mint contract and a lavender learning loop. The existing offline, keyboard-driven deck shell remains the visual reference. Density may increase, but every slide must preserve one dominant claim and one supporting structure.

## 4. Color tokens

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#0b0e14` | Main stage |
| `--bg-raised` | `#121823` | Cards, traces, and diagrams |
| `--ink` | `#f3f6fa` | Primary text |
| `--muted` | `#aeb9c8` | Supporting text |
| `--mint` | `#5eead4` | Verified contract and focus |
| `--lavender` | `#c4b5fd` | Hypotheses and learning loop |
| `--rose` | `#fb7185` | Failure and contradiction |
| `--amber` | `#fbbf24` | Unsettled boundary |
| `--green` | `#86efac` | Verified outcome |
| `--line` | `#364154` | Borders and separators |

All CSS colors must resolve to these tokens. The atmosphere uses only token-derived radial light; it does not fetch images or fonts.

## 5. Type, spacing, and reusable primitives

- Use the offline system stack with Noto fallbacks for all three languages.
- Body text is at least 18px on a typical laptop and 16px on a phone.
- Long prose stays near 65 characters per line; code and trace rows may scroll horizontally.
- Use a 4px spacing base and declared multiples only.
- Do not shrink text to make a slide fit; allow the active slide to scroll.

Reusable primitives:

- **Stage:** one full-viewport slide inside `<main>`.
- **Kicker:** concise chapter or incident label in mint.
- **Timeline:** ordered event rows with an explicit clock, observed state, and hidden durable state; failure rows use rose and unsettled boundaries use amber.
- **Evidence table:** each hypothesis stays beside its applicability question, falsifier, evidence route, and current credit.
- **Ledger table:** stable gap IDs, ambiguity scores, impact weights, status, and residual arithmetic remain inspectable.
- **Scored-question table:** factor judgments and exact helper arithmetic remain visible; the UI never presents the score as model certainty.
- **Structured-question panel:** evidence, one concrete scenario, mutually exclusive options, a justified recommendation, and an explicit falsifier.
- **Pressure decomposition:** a follow-up story is split into observable identities, counts, outcomes, and forbidden effects.
- **Acceptance criterion:** REQ/VER rows use monospace identifiers and name the durable surface that decides pass or fail.
- **Can-versus-must comparison:** native planner capability and protocol obligation appear side by side, without winner-take-all language.
- **Source note:** compact official citation with a real `https` link.
- **Controls:** Previous and Next buttons with a minimum 44px target.

Interactive states: mint focus ring, visible hover border, subtle pressed translation, disabled end controls, and no decorative animation.

## 6. Case-study structure

Diagrams are not required. The duplicate-order interview is the explanatory spine, and concrete state transitions carry more meaning than a generic architecture picture. Each edition must show the same causal sequence:

1. a request that names retry mechanics but omits the business invariant;
2. repository-first orientation and open-world hypotheses with zero fact credit;
3. a persistent ledger that makes the most consequential unresolved branch visible;
4. deterministic question ranking followed by one exact structured question;
5. a pressure follow-up that turns “safe” into observable identities and counts;
6. independent causal evidence and decision authority;
7. separately routed identity, retry-class, deadline, attempt, TTL, and concurrency decisions;
8. REQ/VER criteria that a fresh implementer can challenge; and
9. external execution plus a postmortem that can falsify the interview without rewriting it.

Use tables, timelines, and structured panels when they make the state legible. Mermaid source, pre-rendered SVG, renderer metadata, source hashes, and diagram-only touch rules are intentionally excluded from the guide and deck.

## 7. Accessibility and responsive constraints

- The visible slide is the only active slide; all others are `hidden`, `inert`, and `aria-hidden`.
- Arrow keys, Space, Page Up/Down, Home, End, buttons, swipe, and URL hashes work.
- Keyboard shortcuts do not fire from buttons, links, details, code, or diagram canvases.
- A semantic progress bar and polite live region announce slide changes.
- Focus remains visible. Reduced-motion preferences remove transitions.
- External citations remain keyboard reachable and use readable link text.
- Dense tables sit inside a focusable `.table-wrap` horizontal scroll region. Keyboard shortcuts and deck swipes must ignore interactions that start inside it.
- At 375px, 768px, and 1280px, controls remain reachable, content does not clip, and dense tables scroll inside their own regions.

## 8. Citation and comparison rules

Use first-party sources for current product behavior:

- OpenAI Codex CLI and current feature documentation;
- Anthropic Claude Code permission modes and best practices.

Do not claim either planner lacks exploration, verification, structured output, or implementation support. The comparison is architectural: native planners optimize a coding workflow; `ultimateinterview` adds a portable evidence and contract protocol that can run on those planners and hand execution back to them.

## 9. Accepted debt and exclusions

- The deck is a standalone static HTML file, so navigation JavaScript and styles are inline.
- No external runtime fonts, scripts, images, analytics, or network assets.
- No emoji, decorative icons, tiny footnotes, placeholder content, or screenshot-only text.
- Deployment orchestration, regulated evidence custody, and long-lived experiment control planes are explicitly out of scope for this protocol and may require an execution-owning system.
