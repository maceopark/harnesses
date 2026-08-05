"""Reviewer consensus and readiness classification rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


class FindingChannel(StrEnum):
    READINESS = "readiness"
    HINDSIGHT = "hindsight"


class ReviewModel(Protocol):
    """External reviewer boundary; implementations must use isolated calls."""

    def review(self, *, reviewer_id: str, payload: object) -> object:
        """Return the reviewer's schema-validated response."""


@dataclass(frozen=True)
class DecisionDisposition:
    decision_id: str
    reviewer_id: str
    material: ReviewDecision
    issue_time_knowable: ReviewDecision
    implementation_independent: ReviewDecision
    separated_from_repository_fact: ReviewDecision
    leakage_free: ReviewDecision

    def __post_init__(self) -> None:
        if not self.decision_id or not self.reviewer_id:
            raise ValueError("decision_id and reviewer_id are required")

    @property
    def approved(self) -> bool:
        return all(
            value is ReviewDecision.APPROVE
            for value in (
                self.material,
                self.issue_time_knowable,
                self.implementation_independent,
                self.separated_from_repository_fact,
                self.leakage_free,
            )
        )


@dataclass(frozen=True)
class Consensus:
    decision_id: str
    status: str
    approved: bool


def unanimous_disposition(
    decision_id: str, dispositions: Iterable[DecisionDisposition]
) -> Consensus:
    """Approve only two independent, complete, unanimous approvals.

    Any rejection, uncertainty, duplicate reviewer, missing reviewer, or
    disagreement is routed to human review and cannot enter the approved quota.
    """

    reviews = tuple(dispositions)
    if any(review.decision_id != decision_id for review in reviews):
        raise ValueError("all dispositions must address the requested decision")
    reviewer_ids = {review.reviewer_id for review in reviews}
    independent_pair = len(reviews) == 2 and len(reviewer_ids) == 2
    approved = independent_pair and all(review.approved for review in reviews)
    return Consensus(
        decision_id=decision_id,
        status="approved" if approved else "human_review_required",
        approved=approved,
    )


READINESS_KINDS = frozenset(
    {
        "owner-decision-gap",
        "repository-fact-violation",
        "synthesis-loss",
        "invention",
        "compatibility-regression",
        "unverifiable-acceptance",
    }
)


@dataclass(frozen=True)
class Finding:
    finding_id: str
    kind: str
    knowledge_timing: str
    public_or_repository_contradiction: bool = False
    separately_adjudicated: bool = False


def classify_finding(finding: Finding) -> FindingChannel:
    """Keep hindsight diagnostic-only unless separately promoted on public facts."""

    if finding.knowledge_timing == "hindsight_only":
        promoted = (
            finding.public_or_repository_contradiction
            and finding.separately_adjudicated
            and finding.kind in READINESS_KINDS
        )
        return FindingChannel.READINESS if promoted else FindingChannel.HINDSIGHT
    return (
        FindingChannel.READINESS
        if finding.kind in READINESS_KINDS
        else FindingChannel.HINDSIGHT
    )


def partition_findings(
    findings: Iterable[Finding],
) -> tuple[tuple[Finding, ...], tuple[Finding, ...]]:
    readiness: list[Finding] = []
    hindsight: list[Finding] = []
    for finding in findings:
        target = readiness if classify_finding(finding) is FindingChannel.READINESS else hindsight
        target.append(finding)
    return tuple(readiness), tuple(hindsight)
