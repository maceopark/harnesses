# Assurance warrants and defeaters: minimal additive contract

## Outcome

Do not turn each `ClaimEvidence` row into a miniature assurance case. Keep the existing evidence/provenance record intact and add one strict `AssuranceFragment` per ambiguity-ledger entry. The fragment explicitly represents the claim-to-evidence support edge, the conditions under which that inference is valid, challenges to any node, and the revision to which the assessment applies.

This is smaller than full GSN/SACM but preserves their essential distinction between claim, inference/rationale, evidence, context, and assumption. NIST defines an assurance case as a reasoned, auditable artifact containing systematic argumentation, evidence, and explicit assumptions; evidence alone is not a case [NIST assurance-case glossary](https://csrc.nist.gov/glossary/term/assurance_case). The GSN standard likewise distinguishes goals, strategies, solutions, contexts, assumptions, and justifications, and makes evidential/inferential relationships explicit [GSN Community Standard v1, FAA-hosted copy](https://www.faa.gov/about/office_org/headquarters_offices/ang/redac/redac-sas-201503-gsn-community-standard-v1.pdf).

## Current contract and the gap

Current `ClaimEvidence` already records provenance, independence group, observation time/environment, freshness, a nonblank free-text `warrant`, opaque `counterevidence` strings, and epistemic/decision authority (`claim_evidence.py:129-183`). Collection validation protects IDs and derivation lineage (`:186-237`). Settlement credit only counts current, firsthand, non-assumption, `establishes` records (`:279-288`), with a typed owner/delegate single-source decision override (`:291-302`).

What is missing:

- the supported claim is only implicit in containment;
- the warrant is not an addressable inference and cannot cite multiple premises;
- context and argument assumptions are not represented (the current `assumption` channel is correctly hypothesis-only evidence, a different concept);
- `counterevidence` has no target, kind, state, resolution, or risk acceptance;
- readiness counts evidence groups without checking whether its support inference remains applicable or defeated;
- evidence freshness does not bind the claim wording, warrant, context, assumptions, or material revision.

## Proposed schema

Add an optional, versioned field to each ledger entry only in a new evidence schema version. Do not add these fields ad hoc to `ClaimEvidence`: it is strict/frozen, channel projection is exact, and BuildContract is a digest-bound ABI.

```yaml
assurance_fragment:
  schema_version: 1
  claim:
    ledger_entry_id: GAP-007
    statement_sha256: "..."       # digest of normalized requirement/reason + decision
    material_revision: 12

  support_links:
    - id: SUP-001
      evidence_ids: [EV-014, EV-015]
      warrant: "Observed behavior under C-001 is sufficient to establish the predicate."
      context_ids: [CTX-001]
      assumption_ids: [ASM-001]

  contexts:
    - id: CTX-001
      statement: "Applies to service version X in staging with flag Y enabled."
      status: current             # current | stale | unknown
      evidence_ids: [EV-016]      # optional factual basis
      change_triggers: [runtime-version, environment, feature-flag]

  assumptions:
    - id: ASM-001
      statement: "Staging authorization semantics match production."
      status: open                # open | discharged | accepted-residual | invalidated
      evidence_ids: []            # required when discharged
      acceptance: null            # required when accepted-residual

  defeaters:
    - id: DEF-001
      target_kind: support-link   # claim | evidence | support-link | context | assumption
      target_id: SUP-001
      kind: undercutting          # rebutting | undermining | undercutting | applicability
      statement: "The probe bypasses the production policy-enforcement path."
      status: open                # open | refuted | sustained | accepted-residual
      raised_by: reviewer-id
      raised_at: "2026-07-10T20:00:00-07:00"
      resolution_evidence_ids: []
      resolution_warrant: null
      acceptance: null

  maintenance:
    assessed_material_revision: 12
    fragment_sha256: "..."        # canonical self-excluding digest
    assessed_at: "2026-07-10T20:10:00-07:00"
    assessor: reviewer-id
    review_due_at: null
    change_triggers: [claim-text, evidence, warrant, context, assumption, system]
    defeater_search:
      searched_at: "2026-07-10T20:05:00-07:00"
      searcher: reviewer-id
      scope: [claim, evidence, inference, applicability]
      methods: [contrarian-probe, falsification-checkpoint]
```

`acceptance`, where allowed, is a strict object: `{authority: owner|delegated, actor, rationale, accepted_at, review_due_at, risk}`. It is decision authority, not epistemic proof.

### Mapping from v1 evidence records

| Existing field | New relationship | Migration rule |
|---|---|---|
| enclosing ledger entry | `claim.ledger_entry_id` + `statement_sha256` | Bind explicitly; fail on digest drift. |
| `ClaimEvidence.id` | `support_links[].evidence_ids` | Preserve IDs and all current provenance/lineage rules. |
| `warrant: str` | `support_links[].warrant` | One legacy support link per evidence record is mechanically possible; human review is required before it can establish because legacy text may not state an inference. |
| `counterevidence: [str]` | `defeaters[]` | Do not silently infer target or type. Import as `kind: applicability` (or `unspecified` in a migration-only type), `status: open`, targeting the migrated support link, and block readiness until classified. |
| `freshness` | evidence-node validity | Retain; fragment maintenance additionally covers claim/inference/context/assumption drift. |
| `decision_authority` | `acceptance.authority` | Preserve only for explicit decisions. It must not convert a factual premise or inference into established truth. |
| assumption channel/model prior | no automatic `assumptions[]` mapping | These are hypothesis-only evidence candidates, not intentionally unsubstantiated argument premises. Promote only by explicit human action. |

## Fail-closed gate predicates

1. **Structural integrity.** All IDs are unique and every reference resolves within the ledger entry; `claim.ledger_entry_id`, normalized statement digest, and `material_revision` match live state. Support/derivation graphs are acyclic. Unknown fields fail.
2. **Evidence eligibility is preserved.** A support link can establish only through records already eligible under v1: current, firsthand, non-assumption, `establishes`. Derived evidence never adds independence and retains its current one-root/hypothesis-taint invariants.
3. **No orphan establishment.** Every evidence record credited toward settlement is used by at least one support link; every active support link has at least one eligible evidence ID and a nonblank warrant.
4. **Context applicability.** Every referenced context is `current`; `stale|unknown` blocks the link. Context evidence, if present, must itself be current. A changed trigger invalidates the fragment even if each evidence row still says `current`.
5. **Assumption closure.** `open|invalidated` assumptions block the link. `discharged` requires current resolution evidence. `accepted-residual` requires typed owner/delegate acceptance, risk, rationale, and an unexpired review date; it is surfaced as residual risk, never counted as another evidence group.
6. **Defeater propagation.** An `open` defeater makes its target unsupported. A `sustained` rebutter reopens/refutes the claim; a sustained underminer excludes the evidence; a sustained undercutter excludes the support link; a sustained applicability defeater invalidates its context/assumption. The effect propagates to any link/claim depending on that node.
7. **Resolution integrity.** `refuted` requires resolution evidence plus a resolution warrant. Resolution evidence must first pass identity/source-digest verification, then satisfy `roots(resolution) ⊈ roots(defeated evidence)` after policy correlation collapse; a newly signed derivative of the defeated lineage is authentic but not an independent resolution. `accepted-residual` is allowed only through typed acceptance with explicit risk and review deadline. Deleting a defeater is not resolution; retain it for audit.
8. **Current challenge pass.** Critical settled entries require a current `defeater_search` covering claim, evidence, inference, and applicability, performed after the last material revision. This gate proves a named search was performed, not that the search was exhaustive.
9. **Authority separation.** Owner/delegate acceptance may settle a preference, normative decision, or consciously accepted residual risk. For observed-fact/causal claims it cannot replace eligible evidence or repair an invalid inference.
10. **Readiness.** A critical entry is settled only if it has the currently required independent evidence groups *and* at least one undefeated applicable support link, or an explicit type-correct single-source/ residual-risk acceptance. Evidence count alone is insufficient.
11. **Maintenance.** Any change to claim digest, cited evidence, warrant, context, assumption, defeater state, source artifact digest, environment, or declared trigger increments/invalidate `assessed_material_revision`, clears the challenge pass, and reopens the affected entry until reassessed. Expired reviews fail closed.

Assurance 2.0 gives the central propagation rule: a doubt or incompletely investigated defeater makes its target unsupported and this propagates to the top claim; a sustained defeater requires changing the case/system or explicitly accepting residual risk [Bloomfield, Netkachova & Rushby, 2024](https://arxiv.org/abs/2405.15800). The older SEI confidence framework likewise treats confidence as increasing when reasons for doubt are identified and eliminated, not merely when supporting artifacts accumulate [Goodenough, Weinstock & Klein, 2012](https://www.sei.cmu.edu/library/toward-a-theory-of-assurance-case-confidence/).

## Why the defeater kinds matter

- **rebutting**: challenges the claim itself (counterexample or evidence for its negation);
- **undermining**: challenges a premise/evidence item (authenticity, correctness, freshness, representativeness);
- **undercutting**: challenges the warrant/inference (even if evidence and claim could both be true);
- **applicability**: challenges a context or assumption that scopes the inference.

NASA training illustrates the distinction: contrary DMV records undermine a premise, accident statistics can undercut the inference from license to safe driving, while a defeater of the conclusion rebuts the conclusion [NASA, Understanding Assurance Cases, Module 3](https://shemesh.larc.nasa.gov/arg/uac-all5.pdf).

## Limits and irreducible human judgment

- A validator can prove graph well-formedness and freshness bindings, not that natural-language evidence actually entails a claim or that a warrant is substantively adequate.
- No finite defeater sweep proves completeness in an open world. Search scope/method/time are auditable process evidence only.
- Context boundaries, acceptable assumptions, residual-risk tolerability, proportional evidence, and whether a decision belongs to the named owner remain human decisions.
- Declared independence groups may hide common-cause or correlated sources; this schema does not authenticate them.
- Change triggers are themselves an incomplete model. Unknown changes can evade automated invalidation, so periodic and event-driven human review remain necessary.
- A structured diagram/record can create assurance theater. The Nimrod review found failures from stale/non-representative cases, missing operator input, weak independent scrutiny, compliance-only paperwork, self-fulfilling arguments, and cases that were not living documents [UK MOD Manual of Air System Safety Cases, pp. 43-45](https://assets.publishing.service.gov.uk/media/642283502fa848000cec0c63/MASSC_Issue_3.pdf).
- An argument fragment is not the full assurance case. NASA distinguishes reasoning steps from the wider plans, analyses, and reports on which premises depend; small fragments are not complete cases [NASA/TM-20250001849, Appendix B](https://ntrs.nasa.gov/api/citations/20250001849/downloads/NASA-TM-20250001849.pdf?attachment=true).
- LLM assistance must remain advisory. NASA's 2025 critical review found existing studies did not establish effects on overall safety, cost, or adequate human supervision and recommends treating LLM-based argument technology as experimental until replicated evidence exists.

## Recommendation

Make this a schema v2 experiment behind the existing v1 contract, with a migration linter but no automatic readiness upgrade. Start with critical ledger entries only. The minimum valuable increment is: explicit support link + typed defeater + material-revision invalidation. Context/assumption records are necessary as soon as a warrant is conditional; omitting them would preserve the present false-positive path.

## OBSERVATIONS

- OBS-W1: Current code enforces evidence provenance and causal-group eligibility but not the semantic or defeater status of the claim-to-evidence inference (`claim_evidence.py:129-148,279-302`; `ambiguity_ledger.py:332-373`).
- OBS-W2: GSN and NIST both define assurance as explicit argumentation linking claims, evidence, context/assumptions; a bag of evidence is insufficient.
- OBS-W3: Assurance 2.0 treats unresolved doubts as support blockers and retains resolved defeaters for future assessors.
- OBS-W4: Safety-case maintenance research and the Nimrod record show that design, operation, environment, evidence, and assumptions can invalidate an argument even when the old artifact remains unchanged.

## CLAIMS

- CLAIM-W1: A separate `AssuranceFragment` is the smallest additive design that avoids conflating evidence objects with inference objects.
- CLAIM-W2: Critical readiness must conjunct evidence eligibility with an undefeated, applicable support link; evidence-count thresholds alone are unsound.
- CLAIM-W3: Automated gates can establish structural closure and freshness binding, but cannot establish warrant soundness, defeater-search completeness, or residual-risk acceptability.

## EXPAND

- EXPAND: `/root/spec_adequacy` — mutation-test the gate: remove/alter one context, assumption, warrant, or defeater and prove readiness flips closed.
- EXPAND: `/root/evidence_authenticity` — define how resolution evidence and independence groups are authenticated rather than self-declared.
- EXPAND: `/root/policy_enforcement` — map defeater propagation/invalidation to the actual session-update and implementation-gate enforcement points.
- EXPAND: `/root/requirements_human` — define reviewer competence/independence and residual-risk acceptance policy; schema alone cannot choose them.
