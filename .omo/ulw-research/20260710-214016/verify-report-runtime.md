# REPORT.html runtime verification

Originally observed on 2026-07-10; revalidated on 2026-07-11 with the bundled Node runtime, Playwright, and Chrome Stable after the committed-v1 rebaseline and final 375 px line-break adjustment. The report is a local static research artifact; this ledger records the browser behavior that was actually executed.

## Three falsifiable hypotheses

### H1 — Mobile page overflow

- Prediction: the report's wide tables force the 375 px page itself beyond the viewport.
- RED observation: before the scroll-region fix, Chrome reported `scrollWidth=529`, `clientWidth=375`.
- Cause toggle: moving the wide tables into bounded, focusable `.table-scroll` regions and giving only the table an internal `min-width` changed the page result to `scrollWidth=375`, `clientWidth=375`; reverting that containment recreated the overflow during the earlier visual round.
- Final result: refuted for the fixed artifact at 375, 768, and 1280 px.

### H2 — CJK and table content becomes unreadable on mobile

- Prediction: Korean predicates/orphan particles and English tokens split or clip at 375 px.
- Runtime evidence: fresh post-fix full-page captures were directly inspected at 375, 768, and 1280 px. The CJK precision reviewer confirmed that the four previously vulnerable phrases now remain intact, with no orphan endings, split predicates, tofu, clipping, or unreadably small text. At 375 px, both 680 px tables remain intact inside explicitly labeled horizontal-scroll regions.
- Final result: refuted for all three fixed captures.

### H3 — Accessibility and design-contract drift

- Prediction: secondary text/focus indicators fail contrast, reduced-motion is ignored, or priority rows omit their declared verifier/residual fields.
- RED observation: the first independent review measured the 35%-alpha focus ring at only 1.67–1.69:1, and earlier rounds found no reduced-motion override and incomplete priority-row labels.
- Cause toggle: replacing the focus outline with `3px solid var(--accent)` changed the live keyboard-focused element to `rgb(23, 105, 170) solid 3px`; the reviewer measured this token at 5.29–5.77:1 on report surfaces. Chrome now computes `scroll-behavior:auto` under reduced motion, and the DOM exposes 12 labeled verifier/residual fields across six priority rows.
- Final result: fixed. The final independent visual/accessibility re-check returned PASS with high confidence and no blockers after inspecting all three fresh captures and the live focus state.

## Final browser matrix

| Viewport | Page width (`scroll/client`) | Body height | Table regions | Visible mobile hints | Priority labels | Reduced motion |
|---:|---:|---:|---:|---:|---:|---|
| 375 | 375 / 375 | 11978 | 2 | 2 | 12 | `auto` |
| 700 | 700 / 700 | 9777 | 2 | 0 | 12 | `auto` |
| 768 | 768 / 768 | 9013 | 2 | 0 | 12 | `auto` |
| 1280 | 1280 / 1280 | 7916 | 2 | 0 | 12 | `auto` |

Fresh artifacts: `report-375.png`, `report-768.png`, and `report-1280.png`; each is newer than `REPORT.html` at capture time. The 2026-07-11 DOM had 17 source entries and zero unresolved internal anchors. A live 700 px probe additionally confirmed the declared below-760 single-column card layout (`grid-template-columns: 636px`) without adding a fourth delivery screenshot.

## Silent-failure scan

- Chrome launched and exited normally; the capture command exited 0.
- All three PNGs exist and were regenerated after the final source edit.
- The page has no network/API integration, asynchronous job, hidden success payload, or service worker that could create the application-level silent-failure patterns relevant to this static artifact.
- No temporary Playwright scripts, trace archives, debugger statements, inspector processes, or debug ports were created.
