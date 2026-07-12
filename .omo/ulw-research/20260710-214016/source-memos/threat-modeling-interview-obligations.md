# Threat Modeling as a Generator of Interview Obligations

## Research protocol and evidence grading

Read-only research conducted 2026-07-10. Search set comprised 19 distinct queries across NIST, OWASP, MITRE/CAPEC/ATT&CK, Schneier's primary attack-tree article, original misuse/abuse-case literature, and empirical studies/counter-studies. Full source texts were read where available; inaccessible publisher text was cross-checked against abstracts and accessible primary/authoritative sources.

Evidence grades used below:

- **A — normative/authoritative primary guidance:** final NIST SP 800-30r1 and SP 800-115; maintained OWASP and MITRE guidance. Strong for prescribed process and explicit limitations, not proof that a method improves outcomes.
- **B — primary method paper:** original misuse-case and attack-tree publications. Strong for the method's intended semantics; weaker for effectiveness.
- **C — empirical study:** CMU/SEI multi-site experiment (>250 participants), 2014 industrial comparison, and 2025 USENIX qualitative study (25 OSS developers). Stronger for observed tradeoffs; bounded by setting/sample and, where noted, need for replication.
- **D — taxonomies/libraries:** CAPEC and ATT&CK. Strong for generating candidate threats and evidence vocabulary; intrinsically incomplete and context-dependent.

## Executable obligation model

Every threat-derived interview item should be a typed record:

`{asset_or_goal, actor/source, entry_or_trigger, preconditions/trust_assumptions, path/steps, boundary_crossings, adverse_postcondition, prevention_or_detection_claim, observable_evidence, residual_risk, owner, expiry/revisit_trigger, disposition}`

A threat is not resolved by naming a control. It is resolved only when the interview yields one of:

1. **Falsifiable requirement:** a prohibited or required outcome with a measurable condition.
2. **Evidence demand:** an artifact or executable observation capable of contradicting the control claim.
3. **Explicit risk decision:** named owner accepts/defer/transfers the residual risk with scope and expiry.
4. **Stop condition:** handoff or implementation cannot proceed because scope, authority, evidence, or risk ownership is missing.

## Method-to-obligation mappings

### 1. System model + trust-boundary analysis (DFD/decomposition)

**Authoritative method.** OWASP requires the system representation to expose trust boundaries, data flows, stores, processes, and external entities because these are candidate attack points. NIST's data-centric draft begins by narrowly identifying the system/data and enumerating authorized storage, transmission, execution, input, and output locations, plus flows, users, workflows, trust assumptions, and security objectives. Sources: [OWASP Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html), [NIST SP 800-154 draft, pp. 11–13](https://csrc.nist.gov/files/pubs/sp/800/154/ipd/docs/sp800_154_draft.pdf).

**Interview generator.** For every flow crossing a trust boundary ask: “What exact principal/data crosses from zone A to zone B, under whose authority, and what observable result would prove the receiving side accepted an unauthorized or malformed instance?”

- Falsifiable requirement: “A request carrying a tenant-A credential must never authorize access to tenant-B data; an attempted cross-tenant read returns the defined denial and emits the defined audit event.”
- Evidence demand: current DFD/architecture, identity and authorization policy, data classification, request/response trace, and an executable negative test at each boundary.
- Stop gate: any external entity, data store, privileged process, or cross-zone flow lacks an owner, trust assumption, authentication/authorization decision point, or evidence source.
- Reopen trigger: new integration, data class, privilege level, execution environment, or flow/boundary change.

**Limitations.** A DFD is an abstraction, not runtime proof. It can omit human/physical/organizational paths, and its quality depends on current architecture knowledge. NIST SP 800-154 is still an initial public draft (NIST stated in 2025 that it planned to finalize it), so use its principles, not its status as a final standard.

### 2. STRIDE/category-driven threat enumeration

**Authoritative method.** OWASP uses STRIDE to prompt spoofing, tampering, repudiation, information disclosure, denial of service, and elevation of privilege against modeled elements, then requires actionable mitigations documented as requirements. Source: [OWASP cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html).

**Interview generator.** Apply each applicable category to each boundary element, but require a concrete scenario: “Can caller X impersonate principal Y at interface Z, given credential state C? What observation distinguishes rejection from success?”

- Evidence demand by category: authentication proof; integrity/versioning proof; audit attribution/retention; confidentiality/egress test; load/failure budget; authorization/privilege test.
- Stop gate: a high-impact STRIDE scenario has only a control noun (“MFA”, “encryption”, “RBAC”) with no actor, precondition, adverse outcome, test oracle, or owner.
- Coverage gate: record `applicable`, `not applicable + rationale`, or `unresolved` for each category on every in-scope boundary; unresolved high-impact entries block handoff.

**Limitations/counter-evidence.** In CMU/SEI's >250-subject comparison, STRIDE produced few false positives but inconsistent results dependent on team background and was onerous to apply. No method won overall; creative Security Cards found a broader spectrum but more false positives, while persona modeling was more consistent yet incomplete. The authors asked for replication. Source: [CMU/SEI evaluation](https://www.sei.cmu.edu/blog/cyber-threat-modeling-an-evaluation-of-three-methods/). Thus STRIDE is a prompt set, never a completeness certificate.

### 3. Misuse/abuse cases

**Primary method.** A misuse case is a sequence the system must not allow that ends in loss; it is modeled alongside normal use because ordinary functions can enable misuse. The original template includes misuser profile, trigger, assumptions, preconditions, basic/alternate paths, capture points, worst-case threat, prevention guarantee, detection guarantee, affected stakeholders/business rules, scope, and abstraction level. It explicitly distinguishes the requirement (“this must not happen”) from the later design choice of how to prevent it. Source: [Sindre & Opdahl, Capturing Security Requirements through Misuse Cases](https://www.se.rit.edu/~se555/Reading%20Materials/Capturing%20Security%20Requirements%20through%20Misuse%20Cases.pdf).

**Interview generator.** For each valuable normal use case ask: “Who could use or extend this legitimate path to produce stakeholder loss? What must already be true, what is the worst successful postcondition, and what prevention/detection guarantee is required?”

- Falsifiable requirement: formulate the wanted prevention/detection guarantee without prematurely selecting a mechanism.
- Evidence demand: trace from misuse to enabled normal use, violated business rule, capture point, negative acceptance test, and detection/response observation.
- Feature gate: if optional feature UC1 enables severe misuse MUC1 and no feasible mitigation/evidence exists, drop or redesign UC1, or obtain explicit risk acceptance. This consequence is stated in the primary paper.
- Stop gate: worst-case postcondition, affected stakeholder, or prevention/detection guarantee is unknown for a high-impact misuse.

**Limitations/counter-evidence.** The original authors state misuse analysis alone is not a complete requirements method and initially had only small-example evaluation. An industrial experiment later found attack trees elicited more threats, while misuse cases elicited threats associated with earlier development stages; it concluded they are complementary. Source: [Karpati et al., 2014 abstract and article summary](https://www.sciencedirect.com/science/article/pii/S0950584913001924). Misuse cases can also remain too high-level unless tied to concrete architecture/assets and executable or observable guarantees.

### 4. Attack trees

**Primary method.** Set a precise attacker goal as root; recursively decompose alternative (OR) and jointly required (AND) steps; attach attacker-dependent attributes such as cost, skill, access, time, detectability, or probability; research node values; peer-review and update over time; recalculate after controls or environment change. Source: [Schneier, Attack Trees](https://www.schneier.com/academic/archives/1999/12/attack_trees.html).

**Interview generator.** For each unacceptable root outcome ask: “What are all currently known minimal paths to this goal; which steps are alternatives versus jointly necessary; what assumption or control breaks each minimal path; and what evidence supports each node value?”

- Falsifiable requirement: “Every currently modeled minimal attack path to root R contains at least one independently testable prevention or detection point meeting threshold T.”
- Evidence demand: root definition; AND/OR semantics; provenance for each leaf and attribute; mapped control/test; independent reviewer additions; residual uncovered paths.
- Stop gate: root is vague; AND/OR meaning is ambiguous; a feasible high-impact minimal path has no control, detector, response, or accepted risk; numeric node values lack provenance/range/date.
- Reopen trigger: cheaper/new attack, changed adversary capability, altered control, new dependency, or expired node evidence.

**Limitations/counter-evidence.** Schneier explicitly says attacks may be forgotten and values change; peer iteration may last months. Formal work later observed that attack trees lacked unambiguous semantics without a denotational interpretation ([Mauw & Oostdijk, Foundations of Attack Trees](https://www.researchgate.net/publication/225151465_Foundations_of_Attack_Trees)). A tree's exhaustiveness is not established by finishing decomposition. The 2014 industrial study supports pairing trees with misuse cases rather than treating either as sufficient.

### 5. ATT&CK/CAPEC threat libraries

**Authoritative method.** CAPEC provides a reusable catalog of known attack patterns; its schema supplies prerequisites, skills/resources, execution flow, consequences, indicators, and mitigations. ATT&CK adversary emulation converts observed behavior into executable plans and analytics. Sources: [CAPEC](https://capec.mitre.org/), [CAPEC schema](https://capec.mitre.org/documents/schema/schema_v3.1.html), [MITRE adversary emulation plans](https://attack.mitre.org/resources/adversary-emulation-plans/).

**Interview generator.** For each relevant pattern/technique ask: “Do its prerequisites hold here; which concrete implementation is plausible; what telemetry could observe it; and what control/response is expected?”

- Evidence demand: relevance rationale tied to architecture and threat intelligence; public/local source; procedure variant; required telemetry and retention; expected alert/response; test/emulation result.
- Stop gate: a selected high-priority TTP has neither required telemetry nor an explicit blind-spot/risk decision.
- Exclusion gate: every high-relevance catalog item omitted from scope needs rationale; “not in the matrix” is not evidence of safety.

**Limitations/counter-evidence.** MITRE says ATT&CK documents observed real-world behavior, not hypothetical or lab-only behavior; it warns against 100% matrix coverage, marking a technique green after one implementation, or limiting analysis to the matrix. Public reports rarely show complete technique chains/on-keyboard behavior, so emulation plans inherit those gaps and add expert-inferred sequencing. Sources: [MITRE ATT&CK Get Started](https://attack.mitre.org/resources/), [contribution criteria](https://attack.mitre.org/resources/engage-with-attack/contribute/), [emulation limitations](https://attack.mitre.org/resources/adversary-emulation-plans/). ATT&CK is therefore evidence-backed candidate generation, not a full future-adversary model.

### 6. Red teaming/adversary emulation

**Authoritative method.** NIST SP 800-115 separates planning, execution, and post-execution. Planning must capture goals, scope, roles, limitations, success factors, assumptions, resources, timeline, and deliverables. Its Rules of Engagement template requires authorized/excluded targets, allowed/prohibited acts, data handling, contacts, reporting, signatures, and explicit halt/restart criteria. Sources: [NIST SP 800-115](https://doi.org/10.6028/NIST.SP.800-115), especially pp. 11–14 and Appendix B; [MITRE emulation plans](https://attack.mitre.org/resources/adversary-emulation-plans/).

**Interview generator before any test.** “Which exact defense claim is being challenged; against which actor/path/environment; what counts as observed prevention/detection/response; what may be touched; and what condition immediately halts the exercise?”

- Authorization stop gate: no signed authority, target/exclude list, allowable actions, data-handling rules, incident contacts, or halt/restart criteria → do not execute.
- Safety stop gate: unexpected service degradation, contact with excluded/third-party assets, uncontrolled sensitive-data access, or a real incident → halt and invoke the ROE chain.
- Evidence gate after execution: retain successful and unsuccessful actions, timestamps, telemetry, control/analyst response, deviations, and limitations; a narrative “red team passed” is insufficient.
- Remediation gate: a claimed fix remains provisional until the relevant attack step/path is re-executed or an explicit reason prevents retest.

**Limitations/counter-evidence.** NIST says testing is not comprehensive, is time/scope constrained, is less intrusive than a real attacker, and may miss policy/configuration weaknesses; combine testing with examination. Covert testing specifically does not test every control, vulnerability, or system. MITRE evaluation results are objective for the scenario but not comprehensive or directly transferable to another environment. A failed exploit does not prove the path impossible; a successful scenario proves existence, not prevalence.

### 7. NIST risk assessment as the disposition/stop-gate layer

**Authoritative method.** SP 800-30r1 requires explicit purpose, scope, time frame, assumptions, constraints, risk tolerance, priorities/tradeoffs, sources, assessment model, threat sources/events, vulnerabilities, likelihood, impact, uncertainty, communication, and maintenance. Adversarial sources are characterized by capability, intent, and targeting; non-adversarial sources by effects. Sources and rationale should be referenced, and assumptions/constraints make results more repeatable. Source: [NIST SP 800-30r1](https://doi.org/10.6028/NIST.SP.800-30r1), especially pp. 24–39.

**Interview generator.** “What decision will this assessment support, for how long; which sources/events are excluded; what evidence and uncertainty support likelihood/impact; and who has authority to accept risk beyond tolerance?”

- Stop gate: purpose/scope/decision owner or organizational risk tolerance is unknown.
- Evidence-quality gate: likelihood or impact presented without source, date, rationale, uncertainty, and assumptions cannot support irreversible/high-impact prioritization.
- Acceptance gate: residual risk above tolerance requires named authorized acceptance, compensating action, or redesign; interviewer/model cannot accept it implicitly.
- Freshness gate: assessment expires/reopens on incident, architecture/mission change, new vulnerability/TTP, control degradation, or evidence/risk-factor threshold.

**Limitations.** NIST cautions that risk assessments are not precise instruments: results reflect method limits, subjectivity, data quality/trustworthiness, interpretation, and assessor skill. Quantification does not remove epistemic uncertainty; NIST SP 800-154 notes quantitative metrics are difficult and qualitative scales may be appropriate.

## Cross-method interview gates

| Trigger | Mandatory question/evidence | Gate |
|---|---|---|
| New external dependency or trust-zone crossing | owner, identity, data, protocol, assumptions, authn/authz point, telemetry, negative test | unresolved high-impact boundary blocks handoff |
| High-value/regulated data introduced or relocated | all authorized at-rest/in-transit/in-use/input/output locations and security objectives | unknown location/flow blocks completeness claim |
| Privileged/admin or cross-tenant path | misuse case + attack tree + executable denial/audit oracle | no oracle or owner blocks acceptance |
| Severe root outcome | at least two complementary enumeration lenses and independent review | one taxonomy/person cannot close it |
| Control named as mitigation | threat/path mapping, mechanism, configuration, observable expected behavior, negative test, residual risk | control noun alone is unresolved |
| Numeric likelihood/cost/effectiveness | provenance, range, date, sensitivity/uncertainty, decision threshold | unsupported point estimate cannot prioritize high-impact work |
| Planned adversarial execution | signed ROE, inclusions/exclusions, allowed acts, data rules, contacts, halt/restart, success oracle | absent item means do not run |
| ATT&CK/CAPEC used | contextual prerequisites, local relevance, procedure variants, telemetry, gaps beyond library | matrix/catalog coverage cannot be labeled complete |
| Fix claimed | path-specific retest/examination and evidence | no retest means provisional, not verified |
| Unresolved residual risk | authorized owner, decision, rationale, expiry, reopen trigger | AI/interviewer may not silently accept |

## Evidence hierarchy for interview answers

1. **Best:** reproducible executable observation in a representative environment, with raw logs/traces, test oracle, scope, configuration/version, and timestamp.
2. **Strong:** current implementation/configuration/architecture plus independent corroborating observation.
3. **Moderate:** authoritative policy/specification and named accountable owner, but still only a claim about intended behavior.
4. **Weak:** interview testimony, generic best practice, catalog mapping, tool output without validation, or unsupported risk score.
5. **Non-evidence:** method completion, diagram presence, “industry standard,” “encrypted/RBAC/MFA,” ATT&CK green box, or red-team “pass” without scenario artifacts.

The required grade should rise with impact, irreversibility, novelty, and boundary privilege. Weak evidence may generate a follow-up; it must not close a severe scenario.

## OBSERVATIONS

- Threat modeling's most defensible contribution to elicitation is not prediction; it is systematic production of questions about actors, assumptions, paths, boundaries, adverse outcomes, and evidence.
- Trust assumptions are the unifying unit: NIST defines vulnerabilities as violable trust assumptions; DFDs locate them; misuse cases narrate their violation; attack trees decompose paths; red teams attempt them; evidence/risk decisions dispose of them.
- Negative requirements become testable only after adding a concrete actor/precondition, adverse postcondition, control claim, and observable oracle.
- Independent complementary enumeration is justified empirically: techniques find different threat subsets, and team background materially changes results.
- Real adversarial testing is strongest as existential evidence that a path works and weak as evidence that untested paths do not.

## CLAIMS

1. A requirements interview may claim **bounded coverage**, never threat completeness. Its coverage statement must name scope, methods, participants, source libraries, exclusions, uncertainty, and date.
2. Every high-impact threat must terminate in a falsifiable requirement, evidence demand, authorized risk decision, or stop condition; otherwise the handoff is incomplete.
3. For severe outcomes, one person plus one taxonomy is insufficient. Use at least two structurally different generators (e.g., boundary/STRIDE plus misuse/attack tree) and an independent challenge pass.
4. A control is not evidence. Closure requires an observable claim and suitable proof; severe claims normally require executable or independently corroborated evidence.
5. Red-team activity requires fail-closed authorization and safety gates before execution, and scenario-specific evidence plus retest after remediation.
6. Catalogs such as ATT&CK/CAPEC seed known patterns but cannot bound unknown, hypothetical, local, or unpublished behavior.
7. Risk scores must carry provenance and uncertainty, and residual risk above tolerance must be owned by an authorized human decision-maker.

## EXPAND

- Map these records and gates against the live `ultimateinterview` schema/helpers: identify which fields are already machine-enforced and which are prose-only.
- Add typed evidence grades, freshness/expiry, source independence, and `coverage_bound` fields to the evidence ledger rather than a generic “verified” boolean.
- Prototype a machine-checkable gate: each severe threat requires `method_count >= 2`, `independent_review`, `oracle`, `owner`, and one disposition; red-team actions additionally require a complete ROE record.
- Test the proposed gate on prior handoffs/postmortems to measure false blocks and missed obligations before making it normative.
- Define a small, domain-neutral library of trigger questions for trust crossings, cross-tenant access, privileged operations, irreversible actions, sensitive-data lifecycle, and external dependencies, while preserving context-specific threat discovery.
