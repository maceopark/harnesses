#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pydantic>=2.7",
#     "rich>=13.7",
#     "typer>=0.12",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run ambiguity_ledger.py --format markdown ledger.json
#      uv run ambiguity_ledger.py --format json < ledger.json
# 3. Or make executable and run:
#      chmod +x ambiguity_ledger.py && ./ambiguity_ledger.py ledger.json
# ──────────────────

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from collections.abc import Callable
from typing import Annotated, ClassVar, Final, assert_never

import typer
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import behavior_atoms as atom_contract, claim_evidence, evidence_identity


DEFERRED_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted-deferred", "defer", "deferred", "explicitly-deferred"},
)
SINGLE_SOURCE_ACCEPTED_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "accepted-single-source"},
)
CONTESTED_STATUS: Final[str] = "contested"
VALID_STATUSES: Final[frozenset[str]] = (
    frozenset({"draft", "triangulated", "contested", "blocked", "accepted", "deferred"})
    | DEFERRED_STATUSES
    | SINGLE_SOURCE_ACCEPTED_STATUSES
)
SECTION_NAMES: Final[tuple[str, ...]] = ("requirements", "gaps", "entries", "ledger")
VALID_WEIGHTS: Final[frozenset[int]] = frozenset({1, 2, 3, 5})
CRITICAL_WEIGHT: Final[int] = 5
CHANNEL_ALIASES: Final[dict[str, str]] = {
    "assumption": "assumption",
    "code": "from-code",
    "doc": "from-docs",
    "docs": "from-docs",
    "from-code": "from-code",
    "from-docs": "from-docs",
    "from-research": "from-research",
    "from-scenario": "from-scenario",
    "from-user": "from-user",
    "research": "from-research",
    "scenario": "from-scenario",
    "user": "from-user",
}
LEGACY_ORIGIN_ALIASES: Final[dict[str, str]] = {"bundle": "batch"}
NON_EVIDENCE_CHANNELS: Final[frozenset[str]] = frozenset({"assumption"})
VALID_ORIGINS: Final[frozenset[str]] = frozenset(
    {
        "",
        "orientation",
        "dump",
        "scored-question",
        "pressure",
        "batch",
        "checkpoint",
        "sweep",
        "probe",
        "contrarian",
        "fold-back",
    }
)
LENS_ORIGIN: Final[re.Pattern[str]] = re.compile(
    r"^lens:(?:viewpoint|domain/state|goal/obstacle|misuse|quality|controlled-language)$"
)


TRACK_DOMAIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
)


class TrackCategory(StrEnum):
    GOAL = "goal"
    SCOPE = "scope"
    BEHAVIOR = "behavior"
    DOMAIN_STATE = "domain-state"
    CONSTRAINT = "constraint"
    DECISION_BOUNDARY = "decision-boundary"
    QUALITY = "quality"
    MISUSE = "misuse"
    VERIFICATION = "verification"
    ROLLOUT_RECOVERY = "rollout-recovery"


class LedgerTrack(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    category: TrackCategory | None = None
    domain: str | None = None
    target_surfaces: tuple[str, ...] = ()

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not TRACK_DOMAIN_PATTERN.fullmatch(normalized):
            raise ValueError("track domain must be a nonblank lowercase kebab-case slug")
        return normalized

    @field_validator("target_surfaces")
    @classmethod
    def normalize_target_surfaces(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for surface in value:
            cleaned = surface.strip().lower()
            if cleaned.startswith("/"):
                raise ValueError("track target surface must be repo-relative, not absolute")
            while cleaned.startswith("./"):
                cleaned = cleaned[2:]
            if not cleaned or any(part == ".." for part in cleaned.split("/")):
                raise ValueError("track target surface must be nonempty and cannot traverse '..'")
            normalized.append(cleaned)
        return tuple(sorted(set(normalized)))

    @model_validator(mode="after")
    def has_a_locality_key(self) -> LedgerTrack:
        if self.category is None and self.domain is None and not self.target_surfaces:
            raise ValueError("track must include a category, domain, or target surface")
        return self


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class DeferredRecord(BaseModel):
    """Structured deferral: the gates require an owner and a decision date."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    owner: str
    decision_date: str

    @model_validator(mode="after")
    def both_fields_non_empty(self) -> DeferredRecord:
        if not self.owner.strip() or not self.decision_date.strip():
            message = "a deferred record needs a non-empty owner and decision_date"
            raise ValueError(message)
        return self


class LedgerEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        populate_by_name=True,
        extra="forbid",
    )

    id: str
    requirement: str = ""
    reason: str = ""
    origin: str = ""  # which mechanism surfaced this entry (dump, pressure, checkpoint, sweep, lens:<name>, ...)
    status: str = "draft"
    deferred: StrictBool | DeferredRecord = False
    ambiguity_score: StrictInt = Field(
        validation_alias=AliasChoices("ambiguity_score", "ambiguity"),
        ge=0,
        le=3,
    )
    impact_weight: StrictInt = Field(
        validation_alias=AliasChoices("impact_weight", "weight"),
    )
    evidence_channels: tuple[str, ...] = Field(
        default=(),
        validation_alias=AliasChoices("evidence_channels", "channels"),
    )
    evidence_records: tuple[claim_evidence.ClaimEvidence, ...] = ()
    assurance_class: atom_contract.AssuranceClass | None = None
    behavior_atoms: tuple[atom_contract.BehaviorAtom, ...] = ()
    track: LedgerTrack | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_conflicting_aliases(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        for canonical, alias in (
            ("ambiguity_score", "ambiguity"),
            ("impact_weight", "weight"),
            ("evidence_channels", "channels"),
        ):
            if canonical in value and alias in value:
                raise ValueError(f"use either {canonical!r} or {alias!r}, not both")
        if "evidence_records" in value:
            raw_records = value["evidence_records"]
            if not isinstance(raw_records, (list, tuple)):
                raise ValueError("evidence_records must be an array")
            records = tuple(
                record
                if isinstance(record, claim_evidence.ClaimEvidence)
                else claim_evidence.ClaimEvidence.model_validate_json(json.dumps(record))
                for record in raw_records
            )
            raw_channels = value.get("evidence_channels", value.get("channels"))
            supplied_channels = None
            if raw_channels is not None:
                supplied_channels = tuple(
                    claim_evidence.CHANNEL_ALIASES[str(channel).strip().lower()]
                    for channel in raw_channels
                )
            evidence_set = claim_evidence.ClaimEvidenceSet(
                evidence_records=records,
                evidence_channels=supplied_channels,
            )
            normalized = dict(value)
            normalized.pop("channels", None)
            normalized["evidence_records"] = evidence_set.evidence_records
            normalized["evidence_channels"] = tuple(
                channel.value for channel in evidence_set.projected_channels
            )
            return normalized
        return value

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        normalized = value.strip().lower()
        normalized = LEGACY_ORIGIN_ALIASES.get(normalized, normalized)
        if normalized not in VALID_ORIGINS and not LENS_ORIGIN.fullmatch(normalized):
            raise ValueError("origin is outside the documented closed vocabulary")
        return normalized

    @field_validator("impact_weight")
    @classmethod
    def parse_impact_weight(cls, value: int) -> int:
        if value not in VALID_WEIGHTS:
            message = "impact_weight must be one of 1, 2, 3, or 5"
            raise ValueError(message)
        return value

    @field_validator("assurance_class", mode="before")
    @classmethod
    def parse_assurance_class(
        cls,
        value: atom_contract.AssuranceClass | str | None,
    ) -> atom_contract.AssuranceClass | None:
        match value:
            case None:
                return None
            case atom_contract.AssuranceClass() as assurance_class:
                return assurance_class
            case str() as raw_class:
                try:
                    return atom_contract.AssuranceClass(raw_class)
                except ValueError as error:
                    raise ValueError("unknown assurance class") from error
            case unreachable:
                assert_never(unreachable)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value.strip().lower() not in VALID_STATUSES:
            allowed = ", ".join(sorted(VALID_STATUSES))
            message = f"unknown status {value!r}; use one of: {allowed}"
            raise ValueError(message)
        return value

    @field_validator("evidence_channels", mode="before")
    @classmethod
    def coerce_channels(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(part for part in (piece.strip() for piece in value.split(",")) if part)
        return value

    @field_validator("evidence_channels")
    @classmethod
    def normalize_channels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for channel in value:
            cleaned = channel.strip().lower()
            if cleaned not in CHANNEL_ALIASES:
                allowed = ", ".join(sorted(set(CHANNEL_ALIASES.values())))
                message = f"unknown evidence channel {channel!r}; use one of: {allowed}"
                raise ValueError(message)
            normalized.append(CHANNEL_ALIASES[cleaned])
        return tuple(dict.fromkeys(normalized))

    @property
    def is_deferred(self) -> bool:
        status = self.status.strip().lower()
        return bool(self.deferred) or status in DEFERRED_STATUSES

    @property
    def deferral_missing_owner(self) -> bool:
        # Gate-time check: a deferral without a structured owner/decision_date
        # cannot appear in Deferred Risks with an accountable owner.
        return self.is_deferred and not isinstance(self.deferred, DeferredRecord)

    @property
    def is_critical_path_candidate(self) -> bool:
        # Mechanical approximation of "critical-path" (SKILL.md Per-Round Loop
        # step 4): score 3, or score 2 touching weight 3/5. The semantic arms
        # (branches implementation, contradicts evidence, narrows scope) stay
        # with the model - this can under-flag, never veto.
        return not self.is_deferred and (
            self.ambiguity_score == 3
            or (self.ambiguity_score == 2 and self.impact_weight >= 3)
        )

    @property
    def is_batchable(self) -> bool:
        return (
            not self.is_deferred
            and self.ambiguity_score == 2
            and self.impact_weight <= 2
        )

    @property
    def distinct_evidence_channels(self) -> frozenset[str]:
        return frozenset(self.evidence_channels) - NON_EVIDENCE_CHANNELS

    @property
    def distinct_evidence_groups(self) -> frozenset[str]:
        if any(record.identity_assertion is not None for record in self.evidence_records):
            return self.settlement_evidence_groups()
        return claim_evidence.eligible_independence_groups(self.evidence_records)

    def settlement_evidence_groups(
        self,
        *,
        adapter: evidence_identity.VerifierAdapter | None = None,
        now: datetime | None = None,
    ) -> frozenset[str]:
        legacy_records = tuple(
            record for record in self.evidence_records if record.identity_assertion is None
        )
        groups = claim_evidence.eligible_independence_groups(legacy_records)
        if adapter is None:
            return groups
        if now is None:
            raise ValueError("verifier settlement groups require an injected policy clock")
        return groups | self.verifier_credit(adapter=adapter, now=now).roots

    def verifier_credit(
        self,
        *,
        adapter: evidence_identity.VerifierAdapter,
        now: datetime,
    ) -> evidence_identity.VerifierCredit:
        return evidence_identity.verifier_credit(
            self.evidence_records,
            adapter=adapter,
            now=now,
            impact_weight=self.impact_weight,
        )

    @property
    def is_single_source_accepted(self) -> bool:
        return self.is_single_source_accepted_for(evidence_schema_version=1)

    def is_single_source_accepted_for(self, *, evidence_schema_version: int) -> bool:
        if self.status.strip().lower() not in SINGLE_SOURCE_ACCEPTED_STATUSES:
            return False
        if self.evidence_records:
            if evidence_schema_version == 2:
                legacy_records = tuple(
                    record for record in self.evidence_records if record.identity_assertion is None
                )
                return (
                    len(self.settlement_evidence_groups()) == 1
                    and claim_evidence.accepts_explicit_single_source(legacy_records)
                )
            return claim_evidence.accepts_explicit_single_source(self.evidence_records)
        return True

    @property
    def is_contested(self) -> bool:
        return self.status.strip().lower() == CONTESTED_STATUS

    @property
    def is_untriangulated_critical(self) -> bool:
        if self.impact_weight != CRITICAL_WEIGHT or self.ambiguity_score > 1:
            return False
        source_count = len(
            self.distinct_evidence_groups
            if self.evidence_records
            else self.distinct_evidence_channels
        )
        # The single-source waiver still needs at least one real channel:
        # zero-channel or assumption-only acceptance is not single-source.
        if self.is_single_source_accepted:
            return source_count < 1
        return source_count < 2

    @property
    def is_thin_critical(self) -> bool:
        return (
            self.impact_weight == CRITICAL_WEIGHT
            and self.ambiguity_score == 1
            and len(
                self.distinct_evidence_groups
                if self.evidence_records
                else self.distinct_evidence_channels
            ) < 2
            and not self.is_single_source_accepted
        )

    @property
    def label(self) -> str:
        return self.requirement or self.reason or self.id

    @property
    def contribution(self) -> int:
        return self.impact_weight * self.ambiguity_score


def entry_track_keys(entry: LedgerEntry) -> dict[str, tuple[str, ...]]:
    """Return normalized locality keys in the dimensions used by routing."""
    if entry.track is None:
        return {"categories": (), "domains": (), "target_files": ()}
    return {
        "categories": () if entry.track.category is None else (entry.track.category.value,),
        "domains": () if entry.track.domain is None else (entry.track.domain,),
        "target_files": entry.track.target_surfaces,
    }


class LedgerDocument(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    requirements: tuple[LedgerEntry, ...] = ()
    gaps: tuple[LedgerEntry, ...] = ()
    entries: tuple[LedgerEntry, ...] = ()
    ledger: tuple[LedgerEntry, ...] = ()

    def normalized_entries(self) -> tuple[LedgerEntry, ...]:
        for group in (self.requirements, self.gaps, self.entries, self.ledger):
            if len(group) > 0:
                return group
        return ()


type LedgerPayload = tuple[LedgerEntry, ...] | LedgerDocument
LEDGER_PAYLOAD_ADAPTER: Final[TypeAdapter[LedgerPayload]] = TypeAdapter(LedgerPayload)


@dataclass(frozen=True, slots=True)
class AmbiguitySummary:
    active_count: int
    deferred_count: int
    residual: int
    denominator: int
    ambiguity_percent: float
    display_percent: str
    handoff_ready: bool
    blockers: tuple[str, ...]
    triangulation_violations: tuple[str, ...]
    triangulation_warnings: tuple[str, ...]
    contested: tuple[str, ...]
    top_drivers: tuple[LedgerEntry, ...]


def parse_entries(raw_json: str) -> tuple[LedgerEntry, ...]:
    payload: LedgerPayload = LEDGER_PAYLOAD_ADAPTER.validate_json(raw_json)
    match payload:
        case LedgerDocument() as document:
            sections = {
                "requirements": document.requirements,
                "gaps": document.gaps,
                "entries": document.entries,
                "ledger": document.ledger,
            }
            populated = [
                name for name in SECTION_NAMES if len(sections[name]) > 0
            ]
            if len(populated) > 1:
                message = (
                    f"ledger document has multiple populated sections {populated}; "
                    "keep every entry in exactly one of "
                    f"{'/'.join(SECTION_NAMES)} so nothing is silently dropped"
                )
                raise ValueError(message)
            entries = document.normalized_entries()
        case tuple() as entries:
            pass
    if len(entries) == 0:
        message = (
            "ledger contains no entries; an empty ledger cannot be handoff-ready - "
            "populate it (check for a typo'd section key) before scoring"
        )
        raise ValueError(message)
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in entries:
        if entry.id in seen and entry.id not in duplicates:
            duplicates.append(entry.id)
        seen.add(entry.id)
    if duplicates:
        message = f"duplicate entry id(s) {duplicates}; every ledger entry needs a unique id"
        raise ValueError(message)
    return entries


def raw_legacy_bundle_origin_ids(raw_json: str) -> tuple[str, ...]:
    payload = json.loads(raw_json)
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = next(
            (
                payload[name]
                for name in SECTION_NAMES
                if isinstance(payload.get(name), list) and payload[name]
            ),
            [],
        )
    else:
        raw_entries = []
    return tuple(
        str(entry.get("id", "<unknown>"))
        for entry in raw_entries
        if isinstance(entry, dict)
        and str(entry.get("origin", "")).strip().lower() == "bundle"
    )


def display_percent(value: float) -> str:
    if value == 0:
        return "0%"
    if 0 < value < 5:
        return f"{value:.1f}%"
    return f"{value:.0f}%"


def uses_structured_evidence(schema_version: int) -> bool:
    match schema_version:
        case 0:
            return False
        case 1 | 2:
            return True
        case unexpected:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")


def evidence_groups_for_gate(entry: LedgerEntry, *, evidence_schema_version: int) -> frozenset[str]:
    match evidence_schema_version:
        case 0:
            return entry.distinct_evidence_channels
        case 1:
            return entry.distinct_evidence_groups
        case 2:
            return entry.settlement_evidence_groups()
        case unexpected:
            raise typer.BadParameter(f"unknown evidence schema version {unexpected}")


def is_untriangulated_critical_for(entry: LedgerEntry, *, evidence_schema_version: int) -> bool:
    if entry.impact_weight != CRITICAL_WEIGHT or entry.ambiguity_score > 1:
        return False
    source_count = len(evidence_groups_for_gate(entry, evidence_schema_version=evidence_schema_version))
    if entry.is_single_source_accepted_for(evidence_schema_version=evidence_schema_version):
        return source_count < 1
    return source_count < 2


def is_thin_critical_for(entry: LedgerEntry, *, evidence_schema_version: int) -> bool:
    return (
        entry.impact_weight == CRITICAL_WEIGHT
        and entry.ambiguity_score == 1
        and len(evidence_groups_for_gate(entry, evidence_schema_version=evidence_schema_version)) < 2
        and not entry.is_single_source_accepted_for(evidence_schema_version=evidence_schema_version)
    )


def summarize_ambiguity(
    entries: tuple[LedgerEntry, ...],
    *,
    top: int = 3,
    evidence_schema_version: int = 0,
) -> AmbiguitySummary:
    if evidence_schema_version == 2:
        atom_contract.validate_entries(entries, evidence_schema_version=2)
    active_entries = tuple(entry for entry in entries if not entry.is_deferred)
    deferred_count = len(entries) - len(active_entries)
    residual = sum(entry.contribution for entry in active_entries)
    denominator = sum(entry.impact_weight * 3 for entry in active_entries)
    ambiguity_percent = 0.0 if denominator == 0 else 100 * residual / denominator

    score_3 = tuple(entry.id for entry in active_entries if entry.ambiguity_score == 3)
    score_2 = tuple(entry.id for entry in active_entries if entry.ambiguity_score == 2)
    untriangulated = tuple(
        entry.id
        for entry in active_entries
        if is_untriangulated_critical_for(entry, evidence_schema_version=evidence_schema_version)
    )
    contested = tuple(entry.id for entry in active_entries if entry.is_contested)
    warnings = tuple(
        triangulation_warning_line(entry, evidence_schema_version=evidence_schema_version)
        for entry in active_entries
        if is_thin_critical_for(entry, evidence_schema_version=evidence_schema_version)
    )
    blockers = list(
        build_blockers(
            score_3=score_3,
            score_2=score_2,
            untriangulated=untriangulated,
            evidence_schema_version=evidence_schema_version,
        ),
    )
    if uses_structured_evidence(evidence_schema_version):
        unevidenced = tuple(
            entry.id
            for entry in active_entries
            if entry.ambiguity_score <= 1
            and not evidence_groups_for_gate(entry, evidence_schema_version=evidence_schema_version)
        )
        if unevidenced:
            blockers.append(
                f"v{evidence_schema_version} settled entries without eligible structured evidence: "
                f"{', '.join(unevidenced)}",
            )
    if evidence_schema_version == 2:
        untrusted = tuple(
            entry.id
            for entry in active_entries
            if any(record.identity_assertion is not None for record in entry.evidence_records)
            and not entry.settlement_evidence_groups()
        )
        if untrusted:
            blockers.append(f"v2 untrusted/collapsed provenance: {', '.join(untrusted)}")
    top_drivers = tuple(
        sorted(
            (entry for entry in active_entries if entry.ambiguity_score > 0),
            key=lambda entry: (
                -entry.contribution,
                -entry.ambiguity_score,
                -entry.impact_weight,
                entry.id,
            ),
        )[:top],
    )
    return AmbiguitySummary(
        active_count=len(active_entries),
        deferred_count=deferred_count,
        residual=residual,
        denominator=denominator,
        ambiguity_percent=ambiguity_percent,
        display_percent=display_percent(ambiguity_percent),
        handoff_ready=len(blockers) == 0,
        blockers=tuple(blockers),
        triangulation_violations=untriangulated,
        triangulation_warnings=warnings,
        contested=contested,
        top_drivers=top_drivers,
    )


def gate_failures(
    entries: tuple[LedgerEntry, ...],
    *,
    evidence_schema_version: int = 0,
) -> tuple[str, ...]:
    """Hard failures for the endgame gates that the readiness helpers only report:
    unresolved Contested entries, and deferrals without structured owner/date."""
    failures: list[str] = []
    blocked = [entry.id for entry in entries if entry.status.lower() == "blocked" and not entry.is_deferred]
    if blocked:
        failures.append(f"blocked entries unresolved: {', '.join(blocked)}")
    structured_evidence = uses_structured_evidence(evidence_schema_version)
    unevidenced = [
        entry.id
        for entry in entries
        if not entry.is_deferred
        and entry.ambiguity_score <= 1
        and (
            not evidence_groups_for_gate(entry, evidence_schema_version=evidence_schema_version)
            if structured_evidence
            else not entry.evidence_channels
        )
    ]
    if unevidenced:
        label = (
            f"v{evidence_schema_version} settled entries without eligible structured evidence"
            if structured_evidence
            else "settled entries without a recorded channel"
        )
        failures.append(f"{label}: {', '.join(unevidenced)}")
    contested = [entry.id for entry in entries if entry.is_contested and not entry.is_deferred]
    if contested:
        failures.append(
            f"contested entries unresolved: {', '.join(contested)}; "
            "ask which source governs, or defer with owner and decision date",
        )
    unowned = [entry.id for entry in entries if entry.deferral_missing_owner]
    if unowned:
        failures.append(
            f"deferred entries missing structured owner/decision_date: {', '.join(unowned)}; "
            'record deferred as {"owner": "...", "decision_date": "..."}',
        )
    return tuple(failures)


def triangulation_warning_line(
    entry: LedgerEntry,
    *,
    evidence_schema_version: int = 0,
) -> str:
    sources = sorted(evidence_groups_for_gate(entry, evidence_schema_version=evidence_schema_version))
    source = sources[0] if sources else (
        "no eligible evidence group"
        if entry.evidence_records
        else "no non-assumption evidence channel"
    )
    return (
        f"{entry.id}: weight-5 gap at score 1 rests on a single evidence source "
        f"({source}); triangulate with a second channel or record explicit acceptance"
    )


def build_blockers(
    *,
    score_3: tuple[str, ...],
    score_2: tuple[str, ...],
    untriangulated: tuple[str, ...],
    evidence_schema_version: int = 0,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if len(score_3) > 0:
        blockers.append(f"active score 3 gaps remain: {', '.join(score_3)}")
    if len(score_2) > 0:
        blockers.append(f"active score 2 gaps remain: {', '.join(score_2)}")
    if len(untriangulated) > 0:
        structured_evidence = uses_structured_evidence(evidence_schema_version)
        requirement = (
            "need two eligible causal groups or an owner/delegated single-source override"
            if structured_evidence
            else "need two distinct evidence channels or explicit accepted status"
        )
        blockers.append(
            "weight-5 gaps settled without triangulation "
            f"({requirement}): "
            f"{', '.join(untriangulated)}",
        )
    return tuple(blockers)


def summary_as_json(summary: AmbiguitySummary) -> str:
    payload = {
        "active_count": summary.active_count,
        "deferred_count": summary.deferred_count,
        "residual": summary.residual,
        "denominator": summary.denominator,
        "ambiguity_percent": round(summary.ambiguity_percent, 4),
        "display_percent": summary.display_percent,
        "handoff_ready": summary.handoff_ready,
        "blockers": list(summary.blockers),
        "triangulation_violations": list(summary.triangulation_violations),
        "contested": list(summary.contested),
        "top_drivers": [
            {
                "id": driver.id,
                "label": driver.label,
                "ambiguity_score": driver.ambiguity_score,
                "impact_weight": driver.impact_weight,
                "contribution": driver.contribution,
                "reason": driver.reason,
            }
            for driver in summary.top_drivers
        ],
    }
    if len(summary.triangulation_warnings) > 0:
        payload["triangulation_warnings"] = list(summary.triangulation_warnings)
    return json.dumps(payload, indent=2, sort_keys=True)


def summary_as_markdown(summary: AmbiguitySummary) -> str:
    lines = [
        "## Ambiguity Dashboard",
        "",
        f"- Handoff ready: {'yes' if summary.handoff_ready else 'no'} (blocker-based: no active score 2 or 3 gaps, weight-5 settlements triangulated or accepted)",
        f"- Residual ambiguity: {summary.residual} (sum of impact_weight x ambiguity_score over active gaps)",
        f"- Ambiguity %: {summary.display_percent} (informational; remaining share, lower is better; never gate handoff on this)",
        f"- Active gaps: {summary.active_count}",
        f"- Deferred gaps: {summary.deferred_count}",
        f"- Residual / denominator: {summary.residual} / {summary.denominator}",
    ]
    if len(summary.blockers) > 0:
        lines.extend(["", "### Blockers"])
        lines.extend(f"- {blocker}" for blocker in summary.blockers)
    if len(summary.contested) > 0:
        lines.extend(["", "### Contested"])
        lines.append(
            f"- unresolved evidence conflicts (resolve or defer with owner before the gates): {', '.join(summary.contested)}",
        )
    if len(summary.triangulation_warnings) > 0:
        lines.extend(["", "### Critical Triangulation Findings"])
        lines.extend(f"- {warning}" for warning in summary.triangulation_warnings)
    if len(summary.top_drivers) > 0:
        lines.extend(
            [
                "",
                "### Top Drivers",
                "",
                "| ID | Ambiguity | Weight | Contribution | Reason |",
                "| --- | --- | --- | --- | --- |",
            ],
        )
        lines.extend(
            driver_row(driver)
            for driver in summary.top_drivers
        )
    return "\n".join(lines)


def driver_row(driver: LedgerEntry) -> str:
    reason = driver.reason or driver.label
    return f"| {driver.id} | {driver.ambiguity_score} | {driver.impact_weight} | {driver.contribution} | {reason} |"


def read_input(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    if not path.exists():
        raise typer.BadParameter(f"input file not found: {path}")
    if not path.is_file():
        raise typer.BadParameter(f"input path is not a file: {path}")
    return path.read_text(encoding="utf-8")


def summarize_validation_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        errors = error.errors()
        # An unknown key is the most actionable failure; surface it over
        # the union-branch noise ("input should be a valid array").
        for item in errors:
            if item["type"] == "extra_forbidden":
                key = item["loc"][-1]
                return (
                    f"invalid ledger JSON: unknown key {key!r}; "
                    f"use exactly one of {'/'.join(SECTION_NAMES)} (or a bare list)"
                )
        # Prefer the deepest error: union-branch mismatches ("input should be
        # a valid array") have shallow locs and mask the actionable one.
        deepest = max(errors, key=lambda item: len(item["loc"]))
        location = ".".join(str(part) for part in deepest["loc"]) or "<root>"
        suffix = "" if len(errors) == 1 else f" (+{len(errors) - 1} more)"
        return f"invalid ledger JSON at {location}: {deepest['msg']}{suffix}"
    return str(error)


def main(
    path: Annotated[Path | None, typer.Argument(help="Ledger JSON path. Reads stdin when omitted.")] = None,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format."),
    ] = OutputFormat.MARKDOWN,
    top: Annotated[int, typer.Option("--top", min=1, help="Number of top drivers.")] = 3,
) -> None:
    try:
        entries = parse_entries(read_input(path))
    except ValueError as error:
        raise typer.BadParameter(summarize_validation_error(error)) from error
    summary = summarize_ambiguity(entries, top=top)
    renderers: dict[OutputFormat, Callable[[AmbiguitySummary], str]] = {
        OutputFormat.JSON: summary_as_json,
        OutputFormat.MARKDOWN: summary_as_markdown,
    }
    typer.echo(renderers[output_format](summary))


if __name__ == "__main__":
    typer.run(main)
