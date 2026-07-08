# Spec: attribute-search-mysql — Observed-Query Search Evaluation Harness

> **To the implementing agent:** Build from Part 1 only; Part 2 is evidence, read it only on dispute. Deferred Risks are decisions reserved to their owners - never resolve one silently; if your implementation needs an answer to one, stop and ask. After the implementation lands, run the `ultimateinterview-postmortem` skill to diff this spec against the actual change.

# Part 1 — Build Contract

## Goal

Build a repeatable, committed evaluation harness that runs real observed search terms (from BigQuery trace spans) through multiple candidate MySQL fulltext query variants against the stage dictionary, scores each candidate's result adequacy, and produces a comparison that lets the owner select the final search query for the attributes `/search` endpoint.

## Target Surface

| File / module | Expected change |
| --- | --- |
| `uam-api-service/scripts/dev/search-eval/` (NEW) | CLI tool(s): term extraction, candidate runner, metrics + report generation, optional LLM judge |
| `uam-api-service/scripts/dev/search-eval/README.md` (NEW) | Runbook: prerequisites (proxy, bq auth, claude CLI), end-to-end commands, how to add a candidate |
| Production code (`internal/domain/attributes/*`) | **UNTOUCHED this iteration** — applying the winning query is a follow-up task |

## Behavior Contract

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| REQ-001 | Extract observed search terms from BQ traces | Given authenticated `bq` CLI, When extraction runs against `viant-imp-partners.trace_spans_bq._AllSpans` filtering span `name LIKE '%attributes/search%'`, Then it emits every distinct `q` value with frequency and timestamps. The term lives in the span **`name`** column, which is the full request URL — extract with `REGEXP_EXTRACT(name, r'[?&]q=([^&]+)')` and URL-decode; `attributes` is a JSON column that also carries `url.query`. (2026-06 window ≈ 412 distinct / 597 spans; numbers grow with retention) |
| REQ-002 | Session-collapse type-ahead bursts | Given the raw term stream, When collapsing, Then consecutive queries where each is a prefix-extension of the previous within ≤10s (e.g. `pres`→`presby`→`presbyopia`) form one burst, grouped by the span's `client.address` JSON attribute when present, else by time-adjacency alone; the terminal term is classed `intent`, intermediates are classed `fragment`; both classes are kept for evaluation |
| REQ-003 | Run candidates against stage | Given cloud-sql-proxy to `viant-imp-partners:us-central1:uam-db` (**requires `--private-ip`**) and a registered candidate set, When the runner executes, Then every term runs through every candidate against `uam_stage.data_partner_dictionary` capturing raw rows, and the baseline candidate is the current production SQL verbatim (`repository.go:133-144`) |
| REQ-004 | Replicate production leaf filtering before scoring | Given raw SQL results, When scoring, Then the harness applies the service-layer leaf filter (port of `leafDepth`/`isSentinel` from `service.go`) and scores the **post-filter** top-N (default N=20); per-candidate non-leaf drop rate is reported. Candidates with LIMIT are scored post-filter only |
| REQ-005 | Deterministic adequacy metrics | When a run completes, Then per candidate it reports: zero-result rate (intent terms), fragment zero-result rate (prefix responsiveness), result-count distribution, top-N vertical coherence (share of top-N rows agreeing with the modal `vertical` column value), name-match vs definition-match rank ratio (a row is a *name match* when the sanitized term LIKE-matches any of `l1..l4_external_name`, else *definition-only* — MySQL does not attribute FT matches, so this is a post-hoc LIKE heuristic), per-query latency (p50/p95), non-leaf drop rate. Every rate is reported **both** per-distinct-term and frequency-weighted |
| REQ-006 | Side-by-side report | When a run completes, Then a human-readable report shows, per term, baseline vs candidate post-filter top-N side by side, plus the metric summary table across candidates |
| REQ-007 | LLM judge (advisory) | Given `claude` CLI available, When judge stage runs, Then top-K results per intent term are scored 0-2 via headless `claude -p` with rubric: 2 = clearly serves the query's likely targeting intent, 1 = plausibly related, 0 = unrelated; aggregated per candidate as an **advisory** column; judge failure or absence must not fail the run |
| REQ-008 | Boolean-mode input sanitization | Given a boolean-mode candidate, When a term contains FT operators (`+ - * " ( ) < > ~ @`) or stopwords, Then the candidate's term-builder strips/tokenizes safely (e.g. `+tok*` per token, stopword-aware) and never passes raw user text as boolean syntax |
| REQ-009 | Repeatable + parameterized target | Given a completed setup, When re-run with a changed candidate set, Then one command reproduces extraction (or reuses cached terms) and evaluation; target schema is a parameter (default `uam_stage`, prod swappable later without code change) |

## Decision Boundaries

| Decision | Agent may decide? | Boundary |
| --- | --- | --- |
| Implementation language of the tooling | yes | Consistent with repo dev-script precedent (`scripts/dev/`); Go or Python acceptable |
| Exact candidate list | yes | MUST include: current-production baseline, at least one boolean prefix variant, at least one progressive-relaxation variant (strict AND → relaxed fallback); boost dimensions (name-column, vertical-match) and LIMIT variants encouraged per k5/k6 evidence |
| Metric formulas, N/K values, burst window | yes | Defaults: N=20, K=5, burst ≤10s; must be flags/config, not hardcoded |
| Report format (md/html/tsv) | yes | Must be diffable or viewable without extra infra |
| Caching of extracted terms | yes | Do not commit trace-derived datasets to git; regenerate or cache locally |
| Interpreting evaluation results / picking the winner | **no** | Owner (jpark) selects the final query from the report |
| Changing production code | **no** | Follow-up task after selection |

## Out Of Scope / Non-Goals

- Modifying production search code, API contract, or indexes in this iteration
- External search engines, embeddings, vector search (explicit user non-goal)
- Typo/fuzzy correction (out of MySQL fulltext reach; `hven`-style typos accepted as unserved)
- UI changes (type-ahead behavior stays as is)
- Scheduling/automation (manual invocation only; no Magnus)
- Reading prod DB (deferred; harness must merely be *ready* to point at prod)

## Implementation Constraints

- Interfaces: read-only SQL against `uam_stage.data_partner_dictionary`; `bq` CLI for trace extraction; `claude -p` for judge
- Credentials: stage MySQL creds are `MYSQL_UAM_STAGE_USER` / `MYSQL_UAM_STAGE_PASSWORD`, whose values live in the `--set-env-vars` block of `deploy-uam-mysql-proxy.sh` **at the uam-api-service repo root**; source at runtime from that file or user env — never hardcoded in committed files, never echoed in output
- Connectivity: cloud-sql-proxy for `viant-imp-partners:us-central1:uam-db` requires `--private-ip` (instance has no public IP); document in README
- MySQL specifics: InnoDB FT — `innodb_ft_min_token_size=3` default, stopword list applies; multi-column `MATCH` requires an FT index on exactly that column set (per-column boosts via extra `MATCH` need new liquibase DDL — allowed but candidates should prefer LIKE/CASE boosts first to stay SELECT-only)
- Failure visibility: each external dependency (proxy/MySQL, bq, claude) fails with a clear actionable message; judge is optional-degraded, extraction/eval are hard-fail
- Latency measurement: wall-clock per query from the tool's host; document that absolute numbers are proxy-and-locale dependent, comparisons candidate-vs-candidate are the signal

## Verification Commands

| Check | Command / action | Pass condition |
| --- | --- | --- |
| Extraction works | run extraction CLI | distinct-term dataset produced; count plausible vs BQ spot-check (≈412 in the 2026-06 window) |
| Burst collapse | inspect collapsed output around 2026-06-23/24 | `pres`,`presby`,`presbyopia` collapse to one burst with `presbyopia` as intent |
| Known anchor: prefix gap | run baseline + prefix candidate for `neurolog` | baseline post-filter results = 0; prefix candidate > 0 (stage evidence: 0 vs 34 raw) |
| Known anchor: strict AND | run strict-AND candidate for `acura enthusiast` | strict AND = 0 results; relaxation candidate ≥ baseline's relevant results |
| Leaf filter parity | compare harness leaf classification vs `GET /api/v1/attributes/search` on a local/dev instance for ≥3 terms | identical leaf sets |
| Full tournament | run ≥3 candidates over full term set | report + metrics emitted; no crash on typo/operator terms (e.g. `presbyo[p`) |
| Judge degradation | run with claude CLI unavailable | run completes; advisory column empty with warning |
| Runbook | fresh engineer follows README | end-to-end run without asking questions |

## Deferred Risks

| Risk | Owner | Decision date | Mitigation |
| --- | --- | --- | --- |
| Stage↔prod dictionary parity unverified (IDF/token distribution may differ; winner may rank differently on prod) | jpark | before final query ships to prod | harness target-schema parameter; spot-check per-vertical row counts when prod access granted |
| Trace window/volume small (597 spans/~4wk; retention-bound) | jpark | at selection time | treat frequency weights with caution; re-run extraction later for more coverage |
| LLM judge non-determinism | implementer must keep advisory-only | n/a | heuristics are the primary signal |

## Fresh-Implementer Test

| Reviewer | "Would have to ask" items found | Folded back as gaps? |
| --- | --- | --- |
| fresh-context subagent (Part 1 only, no ledger/conversation) | 6 items: (1) q-extraction location BLOCKER, (2) credentials file/env-var names BLOCKER (file exists at repo root — reviewer miss — but exact var names were indeed unstated), (3) burst "same-origin" undefined, (4) vertical-coherence / name-vs-definition attribution undefined, (5) frequency-weighted vs per-distinct unstated, (6) judge rubric missing | All 6 folded directly into REQ-001/002/005/007 and Constraints in this revision — none required a user decision (evidence already in ledger). Contract re-passes self-check: extraction expression, env-var names, burst grouping, metric definitions, dual weighting, rubric now explicit |

# Part 2 — Audit Trail

## Problem

Attribute search (`GET /api/v1/attributes/search`) uses a single 11-column `MATCH ... AGAINST(? IN NATURAL LANGUAGE MODE)` with no prefix matching, no intent-aware ranking, no LIMIT. The user's initial anecdote (q=`auto` surfacing "auto immune disease") was withdrawn as hypothetical; the evidenced real problems are: type-ahead fragment queries return 0 results (`neurolog`), multi-word semantics are fragile (strict AND would zero out the most frequent real query), and there is no way to measure whether any "improvement" actually improves results. Root need: an empirical selection mechanism, not a guessed query change.

## Framing Challenge Outcome

| Check | Result |
| --- | --- |
| Symptom vs root cause | Original ask ("upgrade the query") reframed by user into root need: evaluation system driving query selection |
| Do-nothing option | Search stays unmeasured; type-ahead keystrokes keep returning 0s |
| Simpler alternative | UI category-scoped search rejected (out of MySQL-only scope); direct query swap without eval rejected by pivot |
| Artifact class confirmed | Dev tooling (committed CLI harness) + follow-up query change; confirmed at checkpoint #1 |

## Desired Outcome

Owner runs one CLI against real observed terms, reads a side-by-side + metrics report over candidate SQL variants, and picks the final query with quantified confidence.

## Existing Evidence

| Source | Evidence | Confidence |
| --- | --- | --- |
| from-code | `repository.go:132-151` current query; `service.go` post-SQL leaf filter; FT index def `010-...sql:40`; no order-pinning tests | high |
| from-docs | `attributes/CLAUDE.md` domain contract, JOIN asymmetry, `field`/`id` semantics | high |
| from-user | pivot to eval harness; final-query-selection purpose; scope (all-of-MySQL allowed); signals (heuristics+report+LLM judge); form factor; checkpoint "전부 다 정확해" | high |
| from-research | BQ `_AllSpans`: 597 spans/412 terms/4wk; top terms; fragment bursts; type-ahead confirmed | high |
| from-scenario | stage probes: `neurolog` 0 vs 34 (prefix), `acura enthusiast` natural 170/AND 0, `auto` top-15 all automotive, autoimmune rows don't match `auto` | high |

## Triggered Lenses

| Lens | State | Reason |
| --- | --- | --- |
| viewpoint | skipped | single consumer (targeting-rule UI) + owner-operated dev tool; no ops/compliance/billing impact |
| domain/state | skipped | stateless read query + read-only tooling; no lifecycle/invariants touched |
| goal/obstacle | done | outcome pivoted+settled into a1; obstacles enumerated empirically (k5-k8) |
| misuse | skipped | read-only parameterized queries; FT-operator input handled as correctness (REQ-008); LLM egress noted (internal ad-taxonomy data) |
| quality | done | "적정성/outdated" converted to measurable metric set (REQ-005) incl. latency and non-leaf drop rate |
| controlled-language | done | behavior contract written as Given/When/Then with testable criteria (REQ-001..009) |

## Requirements Ledger

Full machine-readable ledger: `.ultimateinterview/attribute-search-mysql/ledger.json` (24 entries). Key rows:

| ID | Requirement (condensed) | Evidence channels | Ambiguity | Weight | Status |
| --- | --- | --- | --- | --- | --- |
| a1 | Primary artifact: observed-query eval harness for final-query selection | from-user, from-scenario | 1 | 5 | Triangulated |
| g9 | Candidate variants chosen empirically via tournament; enumeration = decision boundary | from-user, from-scenario | 1 | 5 | Triangulated |
| g11 | Adequacy = heuristics + side-by-side report + advisory LLM judge + latency | from-user, from-scenario | 1 | 5 | Triangulated |
| g15 | HARD: replicate service-layer leaf filter before scoring; LIMIT post-filter | from-code | 1 | 5 | Draft |
| g2 | Scope: everything within MySQL allowed (SELECT/DDL/flags) | from-user, from-code | 0 | 5 | Triangulated |
| g1 | auto/autoimmune anecdote withdrawn; evidenced pains stand | from-user, from-scenario | 0 | 5 | Accepted |
| g10 | Form: scripts/dev/search-eval/ CLI + README | from-user, from-code | 0 | 3 | Triangulated |
| g12 | Eval set: all distinct terms, session-collapsed, intent/fragment classes | from-research, from-scenario | 1 | 2 | Triangulated |
| g14 | Judge: claude CLI headless, advisory | from-user, from-code | 1 | 3 | Triangulated |
| k5-k8 | Facts: real term distribution, probe results, low volume, type-ahead | research/scenario | 0 | 2-3 | — |
| d1 | Deferred: stage-prod parity | assumption | (excl.) | 3 | Deferred |

## Ambiguity Dashboard

| Residual | Blockers | Handoff ready? | Progress (informational) |
| --- | --- | --- | --- |
| 38 | none | yes | 16% |

Top remaining drivers are all score-1 decision-boundary residuals (a1/g9/g11/g15 at 5 each) — implementation detail latitude, not open questions.

## Protocol Dashboard

| Depth | Budget used | Protocol ready? | Outstanding blockers |
| --- | --- | --- | --- |
| focused | 6 / 12 | yes | none — build contract fresh-implementer tested, all lenses resolved |

## Seed-Readiness Audit

| Check | Finding | Action |
| --- | --- | --- |
| Fact vs assumption | prod-parity assumption isolated | d1 deferred with owner |
| Implementation-changing gap | leaf-filter validity (found by contrarian review) | REQ-004 hard constraint |
| Code fact to inspect | tests don't pin order; leaf filter location | inspected, k-entries |
| Missing user decision | none open (all score ≤1) | — |
| Weak boundary | "MySQL query level" ambiguity | resolved: all-of-MySQL allowed, SELECT-first preference recorded |
| Unobservable acceptance criterion | none — anchors from stage probes are concrete | — |
| Checkpoint since last change | yes, #1, zero corrections | — |
| Fresh-context reviewer finding | see Fresh-Implementer Test table | folded |

## Q&A Record

Condensed; full transcript: `.ultimateinterview/attribute-search-mysql/transcript.md`.

| # | Question / event | Decision | Pressure / correction |
| --- | --- | --- | --- |
| 1 | Brain dump + depth calibration | pain=intent ranking (`auto` anecdote); MySQL-only best | seed walk corroborated mechanism; anecdote later withdrawn |
| 1-f1/f2 | DDL boundary; ranking rule | all of MySQL allowed; boosts a+b+c | liquibase precedent corroborates |
| 2 | Verification method | user pointed at BQ traces + stage MySQL | both verified accessible; probes run |
| 3 | Evidence collision on `auto` | anecdote was hypothetical → PIVOT to eval harness for final-query selection | contested resolved |
| 4 | Adequacy signals | heuristics + report + LLM judge | latency + non-leaf drop rate added from probes |
| 5 | Form factor; judge invocation | scripts/dev CLI; claude headless | — |
| 6 | Falsification checkpoint (10 statements) | "전부 다 정확해" | zero corrections |

## Contested Log

| Entry | User claim | Repo evidence | Governing source | Resolution |
| --- | --- | --- | --- | --- |
| g1 | q=`auto` surfaces autoimmune noise | stage: top-15 all automotive; autoimmune rows don't match `auto` | user (withdrew) | anecdote hypothetical; evidenced pains (prefix, multi-word) drive design instead |

## Goal + Obstacle Analysis

| Goal | Assumptions | Obstacles | Derived requirements | Residual risk |
| --- | --- | --- | --- | --- |
| Pick final search query with evidence | observed terms represent demand; stage≈prod | low volume (k7); type-ahead bursts distort frequency (k8); post-SQL leaf filter invalidates naive comparison (g15); strict AND zeroes real queries (k6) | REQ-002 collapse, REQ-004 leaf parity, REQ-005 metrics, progressive-relaxation candidates | d1; trace window |

## Quality Attribute Scenarios

| Attribute | Source | Stimulus | Environment | Artifact | Response | Response measure |
| --- | --- | --- | --- | --- | --- | --- |
| Relevance | user typing full term | intent term issued | stage data | candidate query | relevant leaf attributes in top-N | vertical coherence, name-vs-def ratio, judge score |
| Responsiveness (recall) | type-ahead keystroke | fragment issued | stage data | candidate query | non-empty useful results mid-typing | fragment zero-result rate |
| Latency | per-keystroke QPS | each keystroke query | proxy to stage | candidate query | timely response | p50/p95 per candidate (comparative) |
| Robustness | typo/operator input | `presbyo[p`-like terms | any | term sanitizer | no crash, no boolean-syntax leak | full-run completes over all 412 terms |

## Verification Plan Detail

| Evidence | Surface | Command/action | Pass condition |
| --- | --- | --- | --- |
| Manual QA | report file | open side-by-side for `auto`, `neurolog`, `acura enthusiast`, `presbyopia` | qualitative sanity vs anchors |
| Logs/metrics | harness stdout | run summary | per-candidate metric table emitted |

## Restated Approval Check

- Final goal: committed CLI harness that evaluates candidate MySQL search queries on real observed terms so the owner selects the final query
- Key non-goals: no production code change now; no external engines; no fuzzy; no scheduling; no prod reads
- Important assumptions: stage data representative (deferred d1); trace terms represent demand (k7 caveat)
- Deferred risks: d1 stage-prod parity (jpark); trace-window coverage (jpark); judge advisory-only
- Decision boundaries: candidate enumeration (with mandatory baseline/prefix/relaxation), metric formulas, language, report format
- Verification expectations: anchors (`neurolog` 0→>0, `acura enthusiast` AND=0), leaf-filter parity vs live endpoint, full-run robustness, README fresh-engineer test
- Approval status: **Approved** (checkpoint #1 "전부 다 정확해 계속하자"; structured picks on signals/form/judge)
