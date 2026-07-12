# Requirements engineering and human-factors evidence for zero-trust elicitation

## Scope and method

This memo covers structured elicitation, falsification and confirmation bias, independent review, traceability, assurance-case claims/evidence/warrants, reproducibility, and the limits of interviews. It is based on more than 25 searches across standards, official guidance, primary empirical studies, and counter-arguments. Source pages and PDFs were read directly. The mappings below are structural analogies only where the source control and the elicitation failure have the same causal shape.

Evidence labels:

- **Standard / official requirement:** normative or agency guidance in its own domain. Transfer to elicitation remains an engineering proposal unless the source itself concerns elicitation.
- **Primary empirical evidence:** observed in a study; generalization is bounded by the study population and task.
- **Systematic/consensus evidence:** synthesis or consensus report; strength depends on the included literature.
- **Expert practice:** plausible, institutionalized practice without a demonstrated causal effect in this target domain.

## Evidence

### 1. Structured requirements validation and traceability

- **NASA Systems Engineering Handbook (official engineering guidance).** Requirements validation asks whether requirements are correctly written, technically correct, stakeholder-satisfying, feasible, verifiable, and nonredundant/necessary. Technical reviewers check bidirectional traceability to baselined stakeholder expectations, valid assumptions, and necessity/consistency. NASA also says to record rationale, assumptions, relationships to operations, and design constraints. This is strong official practice for systems engineering, not evidence that any particular interview protocol causes better outcomes. [NASA Systems Engineering Handbook, pp. 59–61](https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf)
- **ISO/IEC/IEEE 29148:2018 (active international standard).** It specifies requirements-engineering processes and information items throughout the life cycle, defines characteristics of good requirements, and treats the process as iterative and recursive. The freely accessible abstract does not justify importing detailed clauses not inspected. [ISO record](https://www.iso.org/standard/72089.html), [IEEE record](https://standards.ieee.org/ieee/29148/6937/)
- **OMB cognitive-interview standards (official federal standard in survey research).** Before interviews: define objectives, sampling, recruitment, interview guide, and analysis. During/after: use a guide with probes; analyze systematically within interviews, across interviews by question, and across subgroups; ensure findings represent the full range rather than an overemphasized case; make each finding traceable to raw data; retain an audit trail; report counterexamples, coverage gaps, and limitations. These controls are directly relevant to interview-derived requirements, although the standard's target is survey-question evaluation. [OMB Statistical Policy Directive No. 2 Addendum](https://obamawhitehouse.archives.gov/sites/default/files/omb/inforeg/directive2/final_addendum_to_stat_policy_dir_2.pdf)

Structurally valid elicitation controls:

1. Predeclare the interview objective, stakeholder/source coverage, core guide, planned analysis, and stopping rule. Version later changes rather than suppressing them.
2. Give each requirement/claim a stable identifier and links to exact source fragments, analyst interpretation, assumptions, rationale, conflicts, and intended verification method.
3. Run separate quality gates for syntax, technical correctness, stakeholder fit, feasibility, verifiability, and necessity; agreement with the interviewee is not a substitute for these gates.
4. Analyze across stakeholders and stakeholder classes, not merely conversation-by-conversation; preserve outliers and counterexamples.

### 2. Interviews are generative and incomplete, not an oracle

- **Ferrari, Spoletini, and Debnath (primary controlled study, 30 analysts with a fictional customer).** Only 30–38% of post-interview requirements were fully traceable to the customer's initial ideas; much content refined or added ideas. The authors conclude interviews co-create requirements and that external product/app analysis contributes complementary requirements. They explicitly caution that the experimental setting limits generalization. [Full article](https://link.springer.com/article/10.1007/s00766-022-00383-7)
- **Spoletini et al. (primary controlled study, 42 students at two universities).** Reviewing recorded interviews by the original analyst and another reviewer found 68% of all detected ambiguities after the live interview; reviewer and analyst found materially different ambiguities. The authors propose turning them into follow-up questions. Important boundary: student subjects, role-play tasks, ambiguity detection rather than delivered-system correctness. [Full paper](https://par.nsf.gov/servlets/purl/10061985)
- **Bano et al. (primary empirical study, 248 students over two cohorts).** Novices made 34 kinds of mistakes across question formulation/omission/order, communication, behavior, interaction, teamwork, and planning; major difficulties did not improve across three interviews. This supports checklists/training for novices, not a universal claim about expert interviewers. [Repository record](https://openportal.isti.cnr.it/doc?id=people______%3A%3A85b3ae1033da300fd6bd64d26db8e47d)
- **Carrizo et al. (family of four student experiments, 167 subjects).** Paper prototyping produced more requirements and better measured completeness/quality/performance than JAD or unstructured interviews in this setting; unstructured interviews were fastest but found fewer requirements and had lower measured quality. JAD elicited more nonfunctional requirements. This argues for technique diversity and against a universal best interview form; student tasks and an instructor-defined reference solution limit external validity. [Article](https://www.sciencedirect.com/science/article/abs/pii/S0950584920301282)
- **Requirements elicitation SLR (systematic review).** Reviews report that interviews, often structured, can be effective, but technique performance varies by knowledge type and domain; quality requirements need distinct analysis and there is no single unified technique. Only 26 of 564 screened empirical papers contributed 30 eligible studies in one cited review, indicating a thinner evidence base than raw search counts suggest. [Pacheco et al. abstract and review summary](https://onlinelibrary.wiley.com/doi/10.1049/iet-sen.2017.0144)
- **OMB limit (official standard).** Cognitive interviews use purposive samples and do not yield statistically generalizable findings; they reveal interpretation patterns and possible measurement error. This is a direct warning against treating interview saturation or unanimity as proof of population completeness. [OMB Addendum, pp. 2–3](https://obamawhitehouse.archives.gov/sites/default/files/omb/inforeg/directive2/final_addendum_to_stat_policy_dir_2.pdf)

Valid controls:

- Record and review interviews; force a second-pass ambiguity review by the interviewer and a separate reviewer; convert each ambiguity into a tracked clarification question.
- Triangulate interview claims with behavior/observation, existing artifacts, logs/data, prototypes, and counter-stakeholders when those sources exist. Different methods expose different phenomena; numerical agreement among correlated interviews is not independent corroboration.
- Treat requirements as authored transformations. Preserve three links: what the source said, what the analyst inferred, and the final normative requirement. Flag novel analyst-added content explicitly.
- Do not use `N interviews`, `saturation`, confidence language, or unanimous stakeholder assent as proof of completeness. State the covered population and uncovered complement.

### 3. Assurance cases need warrants, context, and defeaters—not evidence piles

- **GSN Community Standard (community standard hosted by FAA).** An assurance case is a reasoned argument supported by evidence for a defined application/environment. GSN explicitly models a hierarchy of claims, the strategy/reasoning connecting claims to subclaims, evidence references, context, assumptions, and justifications. It is designed to support discussion, challenge, review, and lifecycle maintenance. [GSN Community Standard v1](https://www.faa.gov/about/office_org/headquarters_offices/ang/redac/redac-sas-201503-gsn-community-standard-v1.pdf)
- **NIST SP 800-160 (official guidance).** A reasoned, auditable assurance case combines explicit claims, credible/relevant evidence, valid arguments relating evidence to claims, and explicit assumptions/constraints/inferences; it must be maintained as conditions vary. The appropriate rigor depends on consequences, complexity, and desired assurance. [NIST SP 800-160](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=922194)
- **Assurance 2.0 (expert research report, not a standard).** Confidence should not collapse into one score. The authors separate positive soundness, negative defeaters, and residual doubts; they warn developers to search vigorously for defeaters and record their resolution. This is a useful critique of confirmation-only assurance cases, but its proposed probabilistic machinery is not established empirical evidence for requirements elicitation. [Bloomfield and Rushby report](https://openaccess.city.ac.uk/id/eprint/29444/)
- **NCSC Principles Based Assurance (official expert guidance).** Evidence is an artifact that supports or rebuts a claim through an argument. Independent assessment is more appropriate as criticality or assessor-skill concerns rise; low-criticality cases may accept self-assertion. This establishes risk-tiered practice, not a universal requirement for external review. [NCSC PBA](https://www.ncsc.gov.uk/information/principles-based-assurance)

Valid control schema for each important requirement or handoff assertion:

```text
claim: precise, bounded, falsifiable statement
context: system boundary, environment, actors, time/version
subclaims: necessary decomposition
warrant: why this evidence would support or rebut this claim
evidence: exact artifact/source, provenance, freshness, method, result
assumptions: explicit premises not established here
defeaters: plausible conditions or evidence that would break claim/warrant
residual_doubts: unresolved uncertainty and accepted risk owner
status: supported | contradicted | unresolved | stale
```

Do not infer that a populated diagram is a valid case. GSN makes reasoning inspectable; it does not prove premises, completeness of hazards, validity of warrants, independence, or freshness.

### 4. Confirmation bias and falsification controls

- **Wason 1960 (primary laboratory study, n=29).** In a rule-discovery task, many participants repeatedly proposed cases compatible with their current hypothesis and failed to eliminate it. This is classic evidence of weak hypothesis elimination in one artificial task. [Primary article](https://journals.sagepub.com/doi/10.1080/17470216008416717)
- **Klayman and Ha 1987 (theoretical review with prior empirical results).** They distinguish a positive-test strategy from a motivation to confirm. Testing expected-positive instances can be informative and effective depending on hypothesis structure, environment, and feedback; more opportunities and neutral feedback can widen testing. Therefore, `always ask the negation` is not a justified universal rule. [Full paper](https://psy.ucsd.edu/~mckenzie/KlaymanHaPsychReview1987.pdf)
- **CIA structured analytic techniques (official tradecraft/expert practice).** Analysis of Competing Hypotheses arrays evidence against multiple explanations; devil's advocacy attacks key assumptions; Team A/Team B assigns separate teams to competing views. These are institutional challenge practices, not controlled evidence that they eliminate bias. [Tradecraft Primer](https://www.cia.gov/resources/csi/static/955180a45afe3f5013772c313b16face/Tradecraft-Primer-apr09.pdf)
- **UK Forensic Science Regulator cognitive-bias guidance (official expert guidance).** It ranks independent review of critical findings as lower risk, recommends withholding the original outcome and examiner identity where possible, limiting irrelevant contextual information, describing evidence before viewing the reference, and recording features noticed only after comparison. These controls directly address outcome/context leakage but come from forensic comparison tasks, not open-ended elicitation. [Guidance on Cognitive Bias, pp. 77–80](https://assets.publishing.service.gov.uk/media/5f4fc26ce90e074695f80977/217_FSR-G-217_Cognitive_bias_appendix_Issue_2.pdf)

Valid controls:

- Maintain multiple live hypotheses for consequential unknowns and select questions/tests by their expected ability to distinguish them, not by grammatical negativity.
- Before inspecting confirming evidence, record what result would contradict each hypothesis and what observation would discriminate alternatives.
- Sequence information to reduce contamination: obtain an independent description/analysis before revealing the current favored interpretation or prior conclusion.
- Maintain a defeater/counterevidence ledger with the same provenance and closure discipline as supporting evidence. `No defeater found` is not `no defeater exists`.

### 5. Independent review must be independent in information and incentives

- **NASA-STD-8739.8B (official standard).** IV&V uses rigorous analysis/testing and objective evidence throughout the lifecycle. Independence has technical, managerial, and financial dimensions. This prevents relabeling same-team review as fully independent. [NASA-STD-8739.8B](https://standards.nasa.gov/system/files/tmp/NASA-STD-87398-Revision-B_0.pdf)
- **Forensic Science Regulator (official guidance).** Blind independent assessment of critical findings should occur without knowing the initial result and, where possible, the first examiner's identity. This isolates information independence from organizational independence. [Guidance, pp. 77–80](https://assets.publishing.service.gov.uk/media/5f4fc26ce90e074695f80977/217_FSR-G-217_Cognitive_bias_appendix_Issue_2.pdf)
- **NHMRC independent-review guidance (official expert practice).** Reviewers should add perspectives not involved in development, represent a balance of expertise/perspectives, and have conflicts identified and managed; the process and questions/frameworks should be transparent. [NHMRC guidance](https://www.nhmrc.gov.au/guidelinesforguidelines/review/independent-review)
- **Spoletini et al. (primary study).** A second reviewer found different ambiguities from the original analyst, empirical support for perspective diversity in interview review, bounded to the student role-play design. [Study](https://par.nsf.gov/servlets/purl/10061985)

Risk-tiered independence controls:

1. Low consequence: author self-check with explicit counterevidence checklist.
2. Moderate: another reviewer, no authorship of the claim, separate analysis recorded before reconciliation.
3. High: reviewer blinded to initial conclusion where feasible, technically competent, and managerially/incentive independent; use fresh evidence or reproduce the decisive check.
4. Always record reviewer identity/role, information disclosed before review, conflicts, method, disagreements, and disposition. Multiple agents sharing the same prompt, model, retrieval context, or sponsor are correlated—not independent merely because their outputs are separate.

### 6. Reproducibility and preregistration are transparency controls, not truth certificates

- **National Academies consensus report (consensus evidence).** Transparency enables quality assessment, replication, and detection of HARKing/p-hacking. Preregistration can distinguish planned confirmatory analyses from exploration, expose deviations, and make new hypotheses subject to tests on independent data. But the report also says poor ideas/methods can be preregistered; effectiveness for improving replication rates was uncertain; it can burden or discourage open exploration. Independently reproducing/replicating before publication is effective but often too costly. [Improving Reproducibility and Replicability](https://www.ncbi.nlm.nih.gov/books/NBK547525/)
- **OMB cognitive-interview standard.** An outsider should be able to trace findings to raw interview data and replicate the analysis from a documented audit trail. This is analysis reproducibility, not independent confirmation that the requirement is correct. [OMB Addendum](https://obamawhitehouse.archives.gov/sites/default/files/omb/inforeg/directive2/final_addendum_to_stat_policy_dir_2.pdf)

Valid mapping:

- Preserve a versioned `prior`: initial problem statement, known unknowns, candidate interpretations, evidence plan, and acceptance/rejection criteria before inspecting decisive evidence.
- Preserve deviations with timestamps and rationale; permit exploration, but label it exploratory. Promote a discovered claim only after an appropriately fresh confirmatory check.
- Define two distinct gates: **replay/reproducibility** (another analyst can reach the same transformation from the same raw evidence and method) and **replication/corroboration** (fresh source/data/test supports the same claim). Neither alone proves completeness.
- Do not score confidence from artifact count, reviewer count, or formal completeness alone. Calibrate claim strength to provenance, test severity, independence, coverage, and residual doubt.

## Recommended minimal control set

For a zero-trust elicitation method, the smallest source-grounded set is:

1. A versioned elicitation plan with objectives, stakeholder/source coverage, interview guide, analysis method, and stop/escalation criteria.
2. Recorded source material and an audit trail from fragments to interpretations to normative requirements.
3. A coverage matrix across stakeholder classes, operational modes (including off-nominal), constraints, quality attributes, and lifecycle stages.
4. Explicit claim-context-warrant-evidence-assumption records, plus defeaters and residual doubts.
5. Alternative hypotheses and discriminating tests for consequential unknowns; counterexamples are first-class evidence.
6. Second-pass recording review by author and separate reviewer; unresolved ambiguity re-enters elicitation.
7. Risk-tiered independent review with disclosure/blinding controls and documented conflicts.
8. Separate exploratory findings from confirmed requirements; require fresh evidence for promotion when consequences justify it.
9. Separate reproducibility from replication and stakeholder agreement from technical verification.
10. A fail-closed handoff: unresolved high-impact claims, stale decisive evidence, absent warrants, uncovered critical stakeholder classes, or non-independent high-risk review remain explicitly open rather than silently accepted.

## What the evidence does not establish

- No reviewed source establishes that interviews can prove requirement completeness.
- No reviewed evidence yields a universal interview count or saturation threshold.
- No reviewed evidence shows that a formal assurance-case notation by itself improves truth or safety.
- No reviewed evidence justifies treating multiple same-context LLM agents as independent reviewers.
- The best direct RE experiments here frequently use students, fictional customers, or bounded tasks; exact effect sizes should not be carried into industrial practice.
- Falsification is not mechanically equivalent to asking negative questions. Tests must discriminate plausible alternatives in the actual environment.
- Traceability can preserve a bad inference perfectly; warrant review and empirical validation are still required.

## OBSERVATIONS

- The strongest cross-domain convergence is on *inspectability*: predeclared method, preserved raw evidence, explicit transformations, visible assumptions, and recorded deviations/counterexamples.
- Direct RE evidence shows that live interviews leave ambiguity behind and that analysts materially shape the result. The interview transcript is evidence of a conversation, not a direct dump of stakeholder truth.
- Independent review has at least four separable dimensions: different person/perspective, information blinding, technical competence, and managerial/financial incentive independence.
- Structured argument adds value only when the warrant and defeaters are explicit; evidence volume without a valid inferential bridge is weak assurance.
- Reproducibility tests transformation consistency; replication tests robustness to fresh evidence. A trustworthy handoff should name which has actually occurred.

## CLAIMS

1. **Established within bounded studies:** interview review by the original analyst and another reviewer detects additional, differing ambiguities missed live.
2. **Established official practice:** mature requirements processes require rationale, assumptions, bidirectional traceability, stakeholder validation, feasibility, verifiability, and lifecycle maintenance.
3. **Established official structure:** assurance cases consist of bounded claims, explicit arguments/warrants, evidence, context, and assumptions; they are auditable artifacts, not self-validating proofs.
4. **Established human-factors risk with nuance:** people often use positive tests and can fail to eliminate hypotheses, but positive testing is not always irrational; use discriminating alternatives rather than ritual negation.
5. **Established official/consensus practice:** transparent protocols, raw-data traceability, independent checks, and explicit separation of exploratory from confirmatory findings reduce specific avenues for unnoticed bias; they do not guarantee correctness.
6. **Expert-practice proposal for ultimateinterview:** require a versioned claim/evidence/defeater ledger, blind or context-limited review for critical claims, and fail-closed unresolved states. This is structurally justified but needs empirical evaluation in the target workflow.

## EXPAND

- Test the proposed controls in a reduced space: replay the same recorded requirements interview with (a) author only, (b) second reviewer shown the conclusion, and (c) blinded second reviewer; compare unique ambiguities, claim corrections, time, and false alarms.
- Search industrial—not student—RE studies on interview review, structured prompting, and mixed-method elicitation; direct external-validity evidence is the main gap.
- Define an executable schema and linter for claim/context/warrant/evidence/assumption/defeater/residual-doubt records; validate whether it catches known postmortem misses without creating checkbox compliance.
- Study correlated reviewers: same model/prompt/context versus deliberately diverse tools, evidence order, and incentives. Independence claims need an operational test.
- Establish severity tiers and measurable escalation predicates before adding heavy review everywhere; NIST/NCSC/NASA all imply rigor should scale with consequence and risk.
- Counter-test the process for bureaucracy failure: stale ledgers, fabricated trace links, perfunctory defeaters, and premature closure caused by formal completeness.
