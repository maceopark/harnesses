from swebench_interview_cases.review import (
    DecisionDisposition,
    Finding,
    FindingChannel,
    ReviewDecision,
    classify_finding,
    partition_findings,
    unanimous_disposition,
)


def disposition(reviewer, **overrides):
    values = dict(
        decision_id="decision-1",
        reviewer_id=reviewer,
        material=ReviewDecision.APPROVE,
        issue_time_knowable=ReviewDecision.APPROVE,
        implementation_independent=ReviewDecision.APPROVE,
        separated_from_repository_fact=ReviewDecision.APPROVE,
        leakage_free=ReviewDecision.APPROVE,
    )
    values.update(overrides)
    return DecisionDisposition(**values)


def test_two_independent_unanimous_reviews_approve():
    result = unanimous_disposition("decision-1", [disposition("a"), disposition("b")])
    assert result.approved
    assert result.status == "approved"


def test_missing_duplicate_uncertain_or_rejected_review_requires_human_review():
    cases = [
        [disposition("a")],
        [disposition("a"), disposition("a")],
        [disposition("a"), disposition("b", leakage_free=ReviewDecision.REJECT)],
        [disposition("a"), disposition("b", material=ReviewDecision.UNCERTAIN)],
    ]
    for reviews in cases:
        result = unanimous_disposition("decision-1", reviews)
        assert not result.approved
        assert result.status == "human_review_required"


def test_hindsight_is_diagnostic_unless_separately_adjudicated_public_conflict():
    diagnostic = Finding("f1", "synthesis-loss", "hindsight_only")
    promoted = Finding(
        "f2",
        "synthesis-loss",
        "hindsight_only",
        public_or_repository_contradiction=True,
        separately_adjudicated=True,
    )
    assert classify_finding(diagnostic) is FindingChannel.HINDSIGHT
    assert classify_finding(promoted) is FindingChannel.READINESS
    readiness, hindsight = partition_findings([diagnostic, promoted])
    assert readiness == (promoted,)
    assert hindsight == (diagnostic,)
