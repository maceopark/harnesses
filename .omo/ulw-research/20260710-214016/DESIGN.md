# Zero-Trust Interview Research Report Design System

## 0. Research Log

- Embedded refs: shortlisted Notion, Stripe, Linear → picked Minimalist UI + Notion because this is a long-form Korean research artifact whose priority is calm editorial scanning, not product marketing.
- Lazyweb: skipped — this is a local research report with no real-product screen to emulate; the curated editorial reference supplies the complete layout grammar.
- Imagen drafts: skipped — the subject benefits from a live evidence-flow diagram and semantic cards rather than decorative bitmap imagery.
- Selected grammar: warm paper canvas, whisper borders, one blue action color, one red caution color, serif display + system sans body, wide reading column, compact evidence metadata.

## 1. Atmosphere & Identity

A quiet audit notebook: rigorous, warm, and deliberately non-theatrical. The signature is the verdict firewall, a five-column stepped band that keeps structural validity, traceability, property checks, adequacy, and stakeholder authority visually separate.

## 2. Color

| Role | Token | Value | Usage |
|---|---|---|---|
| Canvas | `--canvas` | `#fbfaf7` | Page background |
| Paper | `--paper` | `#ffffff` | Primary surfaces |
| Warm surface | `--surface` | `#f6f5f1` | Alternating sections |
| Ink | `--ink` | `#20201e` | Headlines and body |
| Muted | `--muted` | `#68645f` | Metadata and secondary text |
| Faint | `--faint` | `#918b84` | Tertiary labels |
| Border | `--border` | `#e5e1da` | Whisper divisions |
| Accent | `--accent` | `#1769aa` | Links and supported controls |
| Accent soft | `--accent-soft` | `#e8f2fa` | Supported badges |
| Warning | `--warning` | `#9a5418` | Conditional proposals |
| Warning soft | `--warning-soft` | `#fbf0df` | Conditional surfaces |
| Reject | `--reject` | `#8f3d3a` | Rejected guarantee transfer |
| Reject soft | `--reject-soft` | `#f8e8e7` | Rejected surfaces |
| Success | `--success` | `#2f6b45` | Verified/current strengths |
| Success soft | `--success-soft` | `#e8f2eb` | Verified badges |
| Lead | `--lead` | `#3e3c39` | Executive-summary text |

Rules: accent colors encode verdicts only. No decorative gradients, saturated section fills, or undisclosed colors.

## 3. Typography

| Level | Size | Weight | Line height | Tracking | Usage |
|---|---:|---:|---:|---:|---|
| Display | `clamp(2.4rem, 7vw, 5rem)`; `1.8rem` at <=640px | 700 | 1.02 | -0.035em | Title |
| H1 | `clamp(1.8rem, 4vw, 3rem)` | 700 | 1.15 | -0.025em | Major sections |
| H2 | `1.5rem` | 700 | 1.3 | -0.015em | Subsections |
| H3 | `1.125rem` | 700 | 1.4 | 0 | Cards |
| Lead | `1.2rem` | 450 | 1.75 | 0 | Executive summary |
| Body | `1rem` | 400 | 1.75 | 0 | Reading text |
| Small | `0.875rem` | 450 | 1.55 | 0 | Metadata |
| Label | `0.75rem` | 700 | 1.4 | 0.08em | Verdict labels |

Font stacks: Display uses `Georgia, 'Noto Serif KR', serif`; body uses `-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif`; mono uses `ui-monospace, SFMono-Regular, Menlo, monospace`.

## 4. Spacing & Layout

Base unit is 4px. Tokens: `--s1:4px`, `--s2:8px`, `--s3:12px`, `--s4:16px`, `--s5:20px`, `--s6:24px`, `--s8:32px`, `--s12:48px`, `--s16:64px`, `--s20:80px`, `--s24:96px`.

Max page width 1200px; reading column 760px. Desktop uses a 220px sticky evidence rail + flexible article. Tablet removes the rail. Cards collapse to one column below 760px. Body padding is 20px mobile, 32px tablet, 48px desktop. The display title uses a documented 1.8rem mobile override to preserve Korean phrase integrity at 375px.

## 5. Components

### Verdict badge
- Variants: verified, conditional, reject, local-evidence.
- States: static only; no hover animation.
- Accessibility: verdict is always present as text, never color alone.

### Evidence card
- Structure: label, title, claim, bounded meaning, source links.
- Variants: strength, gap, recommendation.
- Spacing: `--s6`; whisper border; 12px radius.
- States: links expose hover underline and focus ring.

### Verdict firewall
- Five ordered cells: ABI, trace, property, adequacy, stakeholder.
- Mobile: vertical flow with arrows removed; labels remain complete.
- Accessibility: ordered list semantics and explicit “does not imply” text.

### Priority row
- Structure: priority tag, control title, why, verifier, residual risk; verifier and residual are visible labeled fields in the row body.
- Variants: P0-P5.
- Mobile: all fields stack; no horizontal scrolling.

### Source list
- Numbered references matching `SYNTHESIS.md`.
- Links use visible source names, not bare URLs.

## 6. Motion & Interaction

Static report by default. Only interactive behavior is native link/focus and `<details>` expansion. No decorative entry animation. `prefers-reduced-motion` is therefore inherently respected.

## 7. Depth & Surface

Strategy: borders-only with alternating tonal surfaces. Cards use one 1px border and no shadow. The verdict firewall uses tonal color shifts to convey separation.

## 8. Accessibility Constraints & Accepted Debt

- WCAG 2.2 AA target; body contrast >= 4.5:1; focus outline on all links/summary controls.
- Semantic landmarks, tables with headers, ordered verdict list, descriptive links, Korean `lang` attribute.
- CJK: `word-break: keep-all`, `overflow-wrap: anywhere` only on URLs/code, headings capped to avoid orphan syllables.
- Accepted debt: no automated Lighthouse score because the artifact is a local static report rather than a deployed site; visual QA still covers 375/768/1280 browser captures.
