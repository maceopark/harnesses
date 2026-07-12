"""Strict, public-safe data models for driftbench artifacts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_HEX_LENGTH = 64
FULL_V2_ARM_ID = "ultimateinterview-full-v2-expected-fail"

NonEmptyText = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(min_length=SHA256_HEX_LENGTH, max_length=SHA256_HEX_LENGTH)]
_WORKER_IMAGE_RE = re.compile(r"(?:[a-z0-9][a-z0-9./_-]*@)?sha256:[0-9a-f]{64}\Z")


def _normalized_nonempty(value: str, field_name: str) -> str:
    value = normalize("NFC", value)
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


def _validate_digest(value: str) -> str:
    value = value.lower()
    if len(value) != SHA256_HEX_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("must be a lowercase SHA-256 hexadecimal digest")
    return value


def _validate_worker_image(value: str) -> str:
    if type(value) is not str or _WORKER_IMAGE_RE.fullmatch(value) is None:
        raise ValueError("must be an immutable sha256-addressed worker image")
    return value


def validate_worker_image_identity(value: str) -> str:
    return _validate_worker_image(value)


class StrictModel(BaseModel):
    """Base model whose serialized shape is a versioned artifact contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class RunMode(StrEnum):
    FAKE_DEV = "fake-dev"
    LIVE_DEV = "live-dev"
    LIVE_HOLDOUT = "live-holdout"
    CONFORMANCE = "conformance"


class RunStatus(StrEnum):
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    RUNNING = "running"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CellStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    PLANNER = "planner"
    PRE_TRANSFER_READINESS = "pre-transfer-readiness"
    IMPLEMENTER = "implementer"
    EXPORT = "export"
    EVALUATED_PRIVATE = "evaluated-private"
    POSTMORTEM = "postmortem"
    SCORED_DEV = "scored-dev"
    COMPLETED_PRIVATE = "completed-private"
    COMPLETED = "completed"
    INVALID = "invalid"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_CELL_STATUSES = frozenset(
    {
        CellStatus.COMPLETED,
        CellStatus.COMPLETED_PRIVATE,
        CellStatus.INVALID,
        CellStatus.BLOCKED,
        CellStatus.FAILED,
        CellStatus.CANCELLED,
    }
)


class RoleModels(StrictModel):
    planner: NonEmptyText
    implementer: NonEmptyText
    postmortem: NonEmptyText

    @field_validator("planner", "implementer", "postmortem")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        return _normalized_nonempty(value, "model name")


class ArmDefinition(StrictModel):
    arm_id: NonEmptyText
    source: NonEmptyText

    @field_validator("arm_id", "source")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)


class RunConfig(StrictModel):
    """The portable, public configuration accepted by ``driftbench run``."""

    schema_: Literal["RunConfig.v1"] = Field(
        default="RunConfig.v1", alias="schema", serialization_alias="schema"
    )
    mode: RunMode
    release_id: NonEmptyText
    corpus_root: NonEmptyText
    arms: tuple[ArmDefinition, ...] = Field(min_length=1)
    models: RoleModels
    seed_label: NonEmptyText
    partition: Literal["dev", "holdout"] = "dev"
    max_attempts: int = Field(default=1, ge=1, le=32)

    @field_validator("release_id", "corpus_root", "seed_label")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)

    @model_validator(mode="after")
    def validate_arms(self) -> RunConfig:
        arm_ids = [arm.arm_id for arm in self.arms]
        if len(set(arm_ids)) != len(arm_ids):
            raise ValueError("arms must have unique arm_id values")
        if self.mode is RunMode.LIVE_HOLDOUT or self.partition == "holdout":
            if self.mode is not RunMode.LIVE_HOLDOUT:
                raise ValueError("holdout partition requires live-holdout mode")
        return self


class CellIdentity(StrictModel):
    """All fields participating in a deterministic experimental cell identity."""

    corpus_version: NonEmptyText
    partition: Literal["dev", "holdout"]
    opaque_case_token: NonEmptyText
    arm_id: NonEmptyText
    planner_model: NonEmptyText
    implementer_model: NonEmptyText
    postmortem_model: NonEmptyText
    seed_label: NonEmptyText

    @field_validator(
        "corpus_version",
        "opaque_case_token",
        "arm_id",
        "planner_model",
        "implementer_model",
        "postmortem_model",
        "seed_label",
    )
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)


class CellRecord(StrictModel):
    schema_: Literal["CellRecord.v1"] = Field(
        default="CellRecord.v1", alias="schema", serialization_alias="schema"
    )
    cell_id: NonEmptyText
    identity: CellIdentity
    input_digest: Digest
    status: CellStatus = CellStatus.PENDING
    attempt: int = Field(default=0, ge=0)
    fence: int = Field(default=0, ge=0)
    attempt_receipt_digest: Digest | None = None
    terminal_receipt_digest: Digest | None = None

    @field_validator("cell_id")
    @classmethod
    def validate_cell_id(cls, value: str) -> str:
        return _normalized_nonempty(value, "cell_id")

    @field_validator("input_digest", "attempt_receipt_digest", "terminal_receipt_digest")
    @classmethod
    def validate_digests(cls, value: str | None) -> str | None:
        return None if value is None else _validate_digest(value)

    @model_validator(mode="after")
    def validate_terminal_receipt(self) -> CellRecord:
        if self.status in TERMINAL_CELL_STATUSES and self.terminal_receipt_digest is None:
            raise ValueError("terminal cells require a terminal receipt digest")
        if self.attempt_receipt_digest is not None and self.attempt == 0:
            raise ValueError("attempt receipt requires a positive attempt number")
        return self


class RunState(StrictModel):
    schema_: Literal["RunState.v2"] = Field(
        default="RunState.v2", alias="schema", serialization_alias="schema"
    )
    run_id: NonEmptyText
    status: RunStatus
    config_digest: Digest
    corpus_digest: Digest
    arm_digests: dict[str, Digest]
    worker_image: NonEmptyText
    cells: tuple[CellRecord, ...]

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        return _normalized_nonempty(value, "run_id")

    @field_validator("config_digest", "corpus_digest")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        return _validate_digest(value)

    @field_validator("worker_image")
    @classmethod
    def validate_worker_image(cls, value: str) -> str:
        return _validate_worker_image(value)

    @field_validator("arm_digests")
    @classmethod
    def validate_arm_digests(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("arm_digests must not be empty")
        normalized: dict[str, str] = {}
        for arm_id, digest in value.items():
            normalized[_normalized_nonempty(arm_id, "arm_id")] = _validate_digest(digest)
        return normalized

    @model_validator(mode="after")
    def validate_cells(self) -> RunState:
        cell_ids = [cell.cell_id for cell in self.cells]
        if len(set(cell_ids)) != len(cell_ids):
            raise ValueError("cells must have unique cell_id values")
        return self


class RunManifest(StrictModel):
    schema_: Literal["RunManifest.v2"] = Field(
        default="RunManifest.v2", alias="schema", serialization_alias="schema"
    )
    run_id: NonEmptyText
    release_id: NonEmptyText
    mode: RunMode
    partition: Literal["dev", "holdout"]
    config_digest: Digest
    corpus_digest: Digest
    arm_digests: dict[str, Digest]
    worker_image: NonEmptyText
    status: RunStatus

    @field_validator("run_id", "release_id")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)

    @field_validator("config_digest", "corpus_digest")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        return _validate_digest(value)

    @field_validator("worker_image")
    @classmethod
    def validate_worker_image(cls, value: str) -> str:
        return _validate_worker_image(value)

    @field_validator("arm_digests")
    @classmethod
    def validate_arm_digests(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("arm_digests must not be empty")
        normalized: dict[str, str] = {}
        for arm_id, digest in value.items():
            normalized[_normalized_nonempty(arm_id, "arm_id")] = _validate_digest(digest)
        return normalized


class NativeV1Invocation(StrictModel):
    argv: tuple[NonEmptyText, ...] = Field(min_length=1)
    working_directory: NonEmptyText


class NativeV1RuntimeReceipt(StrictModel):
    schema_: Literal["NativeV1FixtureRuntimeReceipt.v2"] = Field(
        default="NativeV1FixtureRuntimeReceipt.v2", alias="schema", serialization_alias="schema"
    )
    cell_id: NonEmptyText
    input_digest: Digest
    snapshot_id: NonEmptyText
    source_tree_digest: Digest
    source_record_count: int = Field(ge=1)
    fixture_id: NonEmptyText
    fixture_digest: Digest
    invocation: NativeV1Invocation
    exit_code: Literal[0]
    stdout_digest: Digest
    native_runtime_receipt: dict[str, object]
    implementation_ready: Literal[True]
    provenance: Literal["oci-deterministic-worker"]

    @field_validator("input_digest", "source_tree_digest", "fixture_digest", "stdout_digest")
    @classmethod
    def validate_digests(cls, value: str) -> str:
        return _validate_digest(value)

class EvaluationStatusReceipt(StrictModel):
    """The controller-facing status-only receipt; it cannot carry private scores."""

    schema_: Literal["EvaluationStatusReceipt.v1"] = Field(
        default="EvaluationStatusReceipt.v1", alias="schema", serialization_alias="schema"
    )
    run_id: NonEmptyText
    status: RunStatus
    mode: RunMode
    partition: Literal["dev", "holdout"]
    public_safe: Literal[True] = True
    assurance: Literal["none"] = "none"
    provider_execution: Literal["not-attempted", "unavailable"]
    completed_cells: int = Field(ge=0)
    invalid_cells: int = Field(ge=0)
    private_result_ref: None = None
    message: NonEmptyText

    @field_validator("run_id", "message")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)


class DevelopmentScore(StrictModel):
    """Observed, weighted development credit from closed lifecycle evidence."""

    case_count: int = Field(ge=1)
    total_weight: float = Field(gt=0)
    weighted_primary_credit: float = Field(ge=0, le=1)


class DevelopmentBootstrapCI(StrictModel):
    """Deterministic bootstrap interval for a closed development score."""

    point_estimate: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    confidence: float = Field(gt=0, lt=1)
    seed: int
    resamples: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_interval(self) -> "DevelopmentBootstrapCI":
        if self.lower > self.upper:
            raise ValueError("bootstrap lower bound must not exceed upper bound")
        return self


class DevelopmentArmScore(DevelopmentScore):
    """One arm's observed share of a development scorecard."""

    arm_id: NonEmptyText

    @field_validator("arm_id")
    @classmethod
    def validate_arm_id(cls, value: str) -> str:
        return _normalized_nonempty(value, "arm_id")


class Scorecard(StrictModel):
    """A manifest/state-bound development scorecard or explicit unavailable card."""

    schema_: Literal["Scorecard.v1"] = Field(
        default="Scorecard.v1", alias="schema", serialization_alias="schema"
    )
    run_id: NonEmptyText
    partition: Literal["dev"] = "dev"
    mode: RunMode
    scored: bool = False
    claim: Literal["mechanics-only", "deterministic-development-treatment"] = "mechanics-only"
    reason: NonEmptyText
    completed_cells: int = Field(ge=0)
    invalid_cells: int = Field(ge=0)
    manifest_digest: Digest
    state_digest: Digest
    development_metrics: DevelopmentScore | None = None
    bootstrap_ci: DevelopmentBootstrapCI | None = None
    arm_scores: tuple[DevelopmentArmScore, ...] | None = None

    @field_validator("run_id", "reason")
    @classmethod
    def validate_text(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "value")
        return _normalized_nonempty(value, field_name)

    @field_validator("manifest_digest", "state_digest")
    @classmethod
    def validate_score_digests(cls, value: str) -> str:
        return _validate_digest(value)

    @model_validator(mode="after")
    def validate_score_evidence(self) -> "Scorecard":
        if self.scored:
            if self.mode is not RunMode.FAKE_DEV:
                raise ValueError("only deterministic fake-development scorecards are locally scoreable")
            if self.claim != "deterministic-development-treatment":
                raise ValueError("scored cards must identify deterministic development treatment")
            if self.reason != "deterministic-development-observations":
                raise ValueError("scored cards require observed development evidence")
            if self.invalid_cells != 0:
                raise ValueError("scored cards cannot contain invalid cells")
            if self.development_metrics is None or self.bootstrap_ci is None or self.arm_scores is None:
                raise ValueError("scored cards require metrics, bootstrap CI, and per-arm scores")
            if self.development_metrics.case_count != self.completed_cells:
                raise ValueError("scorecard metrics must cover every completed cell")
            if self.bootstrap_ci.point_estimate != self.development_metrics.weighted_primary_credit:
                raise ValueError("bootstrap point estimate must match development metrics")
            arm_ids = tuple(item.arm_id for item in self.arm_scores)
            if arm_ids != tuple(sorted(arm_ids)) or len(set(arm_ids)) != len(arm_ids):
                raise ValueError("arm scores must have unique sorted arm_id values")
            if sum(item.case_count for item in self.arm_scores) != self.completed_cells:
                raise ValueError("arm scores must cover every completed cell")
        elif (
            self.claim != "mechanics-only"
            or self.development_metrics is not None
            or self.bootstrap_ci is not None
            or self.arm_scores is not None
        ):
            raise ValueError("unscored cards cannot carry development score evidence")
        return self
