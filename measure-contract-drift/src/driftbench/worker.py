"""Role-scoped worker sessions with explicit capability isolation.

A worker session is bound to exactly one role and the complete fixed capability set
for that role.  It cannot request a smaller or larger ad-hoc set, impersonate a
second worker, or cross a session boundary.  No worker implementation here runs a
tool or contacts a provider; the unavailable client blocks until a trusted adapter
is injected and the fake client is deterministic for tests.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import re
from types import MappingProxyType
from collections.abc import Mapping
from typing import Annotated, Any, Literal, NoReturn, Protocol
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")

Identifier = Annotated[StrictStr, Field(min_length=3, max_length=64)]


class WorkerServiceUnavailable(RuntimeError):
    """Raised when no trusted worker-session service has been provisioned."""


class WorkerSessionError(ValueError):
    """Raised for a role, worker, session, or capability isolation violation."""


ServiceUnavailableError = WorkerServiceUnavailable


class WorkerRole(StrEnum):
    """The benchmark's mutually isolated worker roles."""

    PLANNER = "planner"
    IMPLEMENTER = "implementer"
    OBSERVATION = "observation"
    POSTMORTEM = "postmortem"


class WorkerCapability(StrEnum):
    """Capabilities intentionally aligned with the role-scoped tool contract."""

    READ = "read"
    SEARCH = "search"
    TASK = "task"
    WRITE_PATCH = "write_patch"
    RUN = "run"


ROLE_CAPABILITIES = MappingProxyType(
    {
        WorkerRole.PLANNER: frozenset(
            {WorkerCapability.READ, WorkerCapability.SEARCH, WorkerCapability.TASK}
        ),
        WorkerRole.IMPLEMENTER: frozenset(
            {
                WorkerCapability.READ,
                WorkerCapability.SEARCH,
                WorkerCapability.WRITE_PATCH,
                WorkerCapability.RUN,
            }
        ),
        WorkerRole.OBSERVATION: frozenset(
            {WorkerCapability.READ, WorkerCapability.RUN}
        ),
        WorkerRole.POSTMORTEM: frozenset({WorkerCapability.READ, WorkerCapability.SEARCH}),
    }
)
"""The complete fixed capability set for each role; callers cannot extend it."""


class WorkerSessionState(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class _StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)


class WorkerSessionRequest(_StrictServiceModel):
    """Request a role-bound session without supplying any capability choice."""

    schema_: Literal["WorkerSessionRequest.v1"] = Field(
        default="WorkerSessionRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    worker_id: Identifier
    role: WorkerRole

    @field_validator("request_id", "worker_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class WorkerSession(_StrictServiceModel):
    """A service-issued session with capabilities fixed by its single role."""

    schema_: Literal["WorkerSession.v1"] = Field(
        default="WorkerSession.v1", alias="schema", serialization_alias="schema"
    )
    session_id: Identifier
    worker_id: Identifier
    role: WorkerRole
    capabilities: tuple[WorkerCapability, ...] = Field(min_length=1, max_length=5)
    state: WorkerSessionState = WorkerSessionState.ACTIVE
    provenance: Literal["trusted-worker", "deterministic-fake", "oci-deterministic-worker"]

    @field_validator("session_id", "worker_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))

    @model_validator(mode="after")
    def require_exact_role_capabilities(self) -> "WorkerSession":
        expected = tuple(sorted(ROLE_CAPABILITIES[self.role], key=str))
        if self.capabilities != expected:
            raise ValueError("worker session capabilities must exactly match its role")
        return self


class WorkerCapabilityRequest(_StrictServiceModel):
    """Ask the worker service to authorize exactly one session-bound capability."""

    schema_: Literal["WorkerCapabilityRequest.v1"] = Field(
        default="WorkerCapabilityRequest.v1", alias="schema", serialization_alias="schema"
    )
    request_id: Identifier
    session_id: Identifier
    worker_id: Identifier
    role: WorkerRole
    capability: WorkerCapability

    @field_validator("request_id", "session_id", "worker_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class WorkerAuthorizationReceipt(_StrictServiceModel):
    """A successful authorization only; denied attempts fail closed with an exception."""

    schema_: Literal["WorkerAuthorizationReceipt.v1"] = Field(
        default="WorkerAuthorizationReceipt.v1", alias="schema", serialization_alias="schema"
    )
    receipt_id: Identifier
    request_id: Identifier
    session_id: Identifier
    worker_id: Identifier
    role: WorkerRole
    capability: WorkerCapability
    authorized: Literal[True] = True
    provenance: Literal["trusted-worker", "deterministic-fake", "oci-deterministic-worker"]

    @field_validator("receipt_id", "request_id", "session_id", "worker_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, getattr(info, "field_name", "identifier"))


class WorkerClient(Protocol):
    """Trusted worker-session authority; no worker capability is implicit."""

    def open_session(self, request: WorkerSessionRequest) -> WorkerSession:
        """Issue a new role-bound session."""

    def authorize(self, request: WorkerCapabilityRequest) -> WorkerAuthorizationReceipt:
        """Authorize one capability after checking session isolation."""

    def close_session(self, session_id: str) -> WorkerSession:
        """Close a session so later authorizations block."""


class UnavailableWorkerClient:
    """Fail-closed default that never opens an untrusted local worker session."""

    def open_session(self, request: WorkerSessionRequest) -> NoReturn:
        del request
        raise WorkerServiceUnavailable(
            "live worker endpoint is unavailable; provide a trusted adapter explicitly"
        )

    def authorize(self, request: WorkerCapabilityRequest) -> NoReturn:
        del request
        raise WorkerServiceUnavailable(
            "live worker endpoint is unavailable; provide a trusted adapter explicitly"
        )

    def close_session(self, session_id: str) -> NoReturn:
        del session_id
        raise WorkerServiceUnavailable(
            "live worker endpoint is unavailable; provide a trusted adapter explicitly"
        )


class FakeWorkerClient:
    """In-memory deterministic session authority for tests, never live evidence."""

    def __init__(
        self,
        *,
        provenance: Literal["deterministic-fake", "oci-deterministic-worker"] = "deterministic-fake",
    ) -> None:
        self._provenance = provenance
        self._sessions: dict[str, WorkerSession] = {}

    def open_session(self, request: WorkerSessionRequest) -> WorkerSession:
        digest = sha256(f"{request.request_id}:{request.worker_id}:{request.role.value}".encode("utf-8")).hexdigest()
        session_id = f"session-{digest[:24]}"
        if session_id in self._sessions:
            raise WorkerSessionError("worker session has already been issued")
        session = WorkerSession(
            session_id=session_id,
            worker_id=request.worker_id,
            role=request.role,
            capabilities=tuple(sorted(ROLE_CAPABILITIES[request.role], key=str)),
            provenance=self._provenance,
        )
        self._sessions[session_id] = session
        return session

    def authorize(self, request: WorkerCapabilityRequest) -> WorkerAuthorizationReceipt:
        session = self._sessions.get(request.session_id)
        if session is None:
            raise WorkerSessionError("unknown worker session")
        _require_session_authorizes(session, request)
        digest = sha256(f"{request.request_id}:{request.session_id}:{request.capability.value}".encode("utf-8")).hexdigest()
        return WorkerAuthorizationReceipt(
            receipt_id=f"workauth-{digest[:23]}",
            request_id=request.request_id,
            session_id=session.session_id,
            worker_id=session.worker_id,
            role=session.role,
            capability=request.capability,
            provenance=self._provenance,
        )

    def close_session(self, session_id: str) -> WorkerSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise WorkerSessionError("unknown worker session")
        if session.state is WorkerSessionState.CLOSED:
            raise WorkerSessionError("worker session is already closed")
        closed = session.model_copy(update={"state": WorkerSessionState.CLOSED})
        self._sessions[session_id] = closed
        return closed


def authorize_worker_capability(
    session: WorkerSession, request: WorkerCapabilityRequest
) -> WorkerAuthorizationReceipt:
    """Pure isolation check for trusted adapters that already resolved a session."""

    _require_session_authorizes(session, request)
    digest = sha256(f"{request.request_id}:{request.session_id}:{request.capability.value}".encode("utf-8")).hexdigest()
    return WorkerAuthorizationReceipt(
        receipt_id=f"workauth-{digest[:23]}",
        request_id=request.request_id,
        session_id=session.session_id,
        worker_id=session.worker_id,
        role=session.role,
        capability=request.capability,
        provenance=session.provenance,
    )


def _require_session_authorizes(session: WorkerSession, request: WorkerCapabilityRequest) -> None:
    if session.state is not WorkerSessionState.ACTIVE:
        raise WorkerSessionError("worker session is not active")
    if session.session_id != request.session_id:
        raise WorkerSessionError("capability request crosses a worker session boundary")
    if session.worker_id != request.worker_id:
        raise WorkerSessionError("capability request impersonates another worker")
    if session.role is not request.role:
        raise WorkerSessionError("capability request crosses a worker role boundary")
    if request.capability not in session.capabilities:
        raise WorkerSessionError("capability is not granted to this worker role")


def _identifier(value: str, field_name: str) -> str:
    if normalize("NFC", value) != value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase opaque identifier")
    return value
_FILENAME_RE = re.compile(r"[a-z][a-z0-9-]{2,63}\.json\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class DeclaredArtifact(_StrictServiceModel):
    """One exact JSON artifact permitted to cross a fresh role boundary."""

    schema_: Literal["DeclaredArtifact.v1"] = Field(
        default="DeclaredArtifact.v1", alias="schema", serialization_alias="schema"
    )
    artifact_id: Identifier
    filename: StrictStr = Field(min_length=6, max_length=69)
    digest: StrictStr = Field(min_length=64, max_length=64)

    @field_validator("artifact_id")
    @classmethod
    def validate_artifact_id(cls, value: str) -> str:
        return _identifier(value, "artifact_id")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not _FILENAME_RE.fullmatch(value):
            raise ValueError("filename must be a lowercase flat JSON filename")
        return value

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("digest must be lowercase SHA-256 hexadecimal")
        return value


_TRANSFER_INPUT_PROFILES = MappingProxyType(
    {
        WorkerRole.PLANNER: ((None, ("cell-input",)),),
        WorkerRole.IMPLEMENTER: (
            (None, ("cell-input",)),
            (WorkerRole.PLANNER, ("build-contract", "handoff")),
        ),
        WorkerRole.OBSERVATION: (
            (WorkerRole.IMPLEMENTER, ("cell-input", "implementation")),
            (WorkerRole.IMPLEMENTER, ("build-contract", "implementation")),
        ),
        WorkerRole.POSTMORTEM: (
            (
                WorkerRole.IMPLEMENTER,
                ("evidence-manifest", "implementation", "observation", "postmortem-request"),
            ),
            (
                WorkerRole.IMPLEMENTER,
                (
                    "build-contract",
                    "evidence-manifest",
                    "implementation",
                    "observation",
                    "postmortem-request",
                ),
            ),
        ),
    }
)
LIFECYCLE_ARTIFACT_FILENAMES = MappingProxyType(
    {
        "cell-input": "input.json",
        "planner-context": "planner-context.json",
        "planner-execution": "planner-execution.json",
        "handoff": "handoff.json",
        "build-contract": "build-contract.json",
        "implementer-context": "implementer-context.json",
        "implementer-execution": "implementer-execution.json",
        "implementation": "implementation.json",
        "observation-context": "observation-context.json",
        "observation-execution": "observation-execution.json",
        "observation": "observation.json",
        "evidence-manifest": "evidence-manifest.json",
        "postmortem-context": "postmortem-context.json",
        "postmortem-request": "postmortem-request.json",
        "postmortem-execution": "postmortem-execution.json",
        "postmortem-report": "postmortem-report.json",
        "native-v1-runtime": "native-v1-runtime.json",
    }
)
LIFECYCLE_MANIFEST_FILENAME = "lifecycle-manifest.json"


class FreshRoleContext(_StrictServiceModel):
    """A new role context whose complete input closure is declared and checked."""

    schema_: Literal["FreshRoleContext.v1"] = Field(
        default="FreshRoleContext.v1", alias="schema", serialization_alias="schema"
    )
    context_id: Identifier
    role: WorkerRole
    source_role: WorkerRole | None = None
    fresh: Literal[True] = True
    declared_artifacts: tuple[DeclaredArtifact, ...] = Field(min_length=1, max_length=8)
    provenance: Literal["trusted-worker", "deterministic-fake", "oci-deterministic-worker"]

    @field_validator("context_id")
    @classmethod
    def validate_context_id(cls, value: str) -> str:
        return _identifier(value, "context_id")

    @model_validator(mode="after")
    def require_complete_declared_transfer(self) -> "FreshRoleContext":
        artifact_ids = tuple(item.artifact_id for item in self.declared_artifacts)
        if artifact_ids != tuple(sorted(artifact_ids)) or len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("declared artifacts must be uniquely sorted by artifact_id")
        filenames = tuple(item.filename for item in self.declared_artifacts)
        if len(set(filenames)) != len(filenames):
            raise ValueError("declared artifacts must use distinct filenames")
        profile = (self.source_role, artifact_ids)
        if profile not in _TRANSFER_INPUT_PROFILES[self.role]:
            raise ValueError("fresh role context has an invalid source role or artifact closure")
        return self


def artifact_reference(artifact_id: str, filename: str, document: Any) -> DeclaredArtifact:
    """Bind an artifact name and flat filename to its canonical document digest."""

    from .state import canonical_digest

    return DeclaredArtifact(
        artifact_id=artifact_id,
        filename=filename,
        digest=canonical_digest(document),
    )


def fresh_role_context(
    role: WorkerRole,
    context_id: str,
    artifacts: Mapping[str, tuple[str, Any]],
    *,
    provenance: Literal["trusted-worker", "deterministic-fake", "oci-deterministic-worker"] = "deterministic-fake",
) -> FreshRoleContext:
    """Create a fresh context from one declared, role-allowed input closure."""

    artifact_ids = tuple(sorted(artifacts))
    profiles = [
        (source_role, expected_ids)
        for source_role, expected_ids in _TRANSFER_INPUT_PROFILES[role]
        if artifact_ids == expected_ids
    ]
    if len(profiles) != 1:
        raise WorkerSessionError("fresh role context must receive an allowed complete artifact closure")
    source_role, expected_ids = profiles[0]
    references = tuple(
        artifact_reference(artifact_id, artifacts[artifact_id][0], artifacts[artifact_id][1])
        for artifact_id in expected_ids
    )
    return FreshRoleContext(
        context_id=context_id,
        role=role,
        source_role=source_role,
        declared_artifacts=references,
        provenance=provenance,
    )


def require_distinct_fresh_contexts(*contexts: FreshRoleContext) -> None:
    """Reject reused or non-fresh contexts within one arm lifecycle."""

    if not contexts or any(context.fresh is not True for context in contexts):
        raise WorkerSessionError("lifecycle contexts must all be explicitly fresh")
    context_ids = tuple(context.context_id for context in contexts)
    if len(set(context_ids)) != len(context_ids):
        raise WorkerSessionError("lifecycle contexts must be distinct")


def transferred_artifacts(context: FreshRoleContext, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return only declared documents after proving their names and digests match."""

    from .state import canonical_digest

    expected = tuple(item.artifact_id for item in context.declared_artifacts)
    if tuple(sorted(artifacts)) != expected:
        raise WorkerSessionError("fresh role context received an undeclared or missing artifact")
    for reference in context.declared_artifacts:
        if canonical_digest(artifacts[reference.artifact_id]) != reference.digest:
            raise WorkerSessionError(f"declared artifact digest drift: {reference.artifact_id}")
    return MappingProxyType(dict(artifacts))


DETERMINISTIC_STARTER_IMPLEMENTATION = "public-starter-implementation-v1"

class FakeDevelopmentAdapter:
    """Deterministic development treatment that performs real artifact handoffs."""

    def __init__(
        self,
        *,
        worker_client: WorkerClient | None = None,
        postmortem_client: Any | None = None,
        simulator_client: Any | None = None,
    ) -> None:
        from .postmortem import FakePostmortemClient
        from .simulator_service import FakeSimulatorClient

        self._worker_client = worker_client or FakeWorkerClient()
        self._postmortem_client = postmortem_client or FakePostmortemClient()
        self._simulator_client = simulator_client or FakeSimulatorClient()
        self._executions: dict[str, dict[str, Any]] = {}

    def planner(self, context: FreshRoleContext, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        """Produce the plan-v1 generic contract from a simulator response."""

        from .simulator_service import SimulatorRequest
        from .state import canonical_digest

        received = transferred_artifacts(context, artifacts)
        if context.role is not WorkerRole.PLANNER:
            raise WorkerSessionError("planner execution requires a planner context")
        cell_input = _cell_input(received["cell-input"])
        identity = _document_mapping(cell_input["identity"], "cell input identity")
        cell_id = _required_identifier(cell_input["cell_id"], "cell_id")
        request = SimulatorRequest(
            request_id=_derived_identifier("simreq", context.context_id),
            case_token=_required_text(identity.get("opaque_case_token"), "opaque_case_token"),
            turn=1,
            message="State the public command boundary without supplying domain facts.",
        )
        answer = self._simulator_client.answer(request)
        answer_document = answer.model_dump(mode="json", by_alias=True, exclude_none=False)
        handoff = {
            "schema": "GenericSimulatorHandoff.v1",
            "cell_id": cell_id,
            "source_input_digest": context.declared_artifacts[0].digest,
            "arm_id": _required_text(identity.get("arm_id"), "arm_id"),
            "simulator_request": request.model_dump(mode="json", by_alias=True, exclude_none=False),
            "simulator_answer": answer_document,
            "case_contract": _document_mapping(cell_input["case_contract"], "case contract"),
        }
        build_contract = {
            "schema": "GenericSimulatorBuildContract.v1",
            "cell_id": cell_id,
            "handoff_digest": canonical_digest(handoff),
            "arm_id": handoff["arm_id"],
            "acceptance_atom_ids": _atom_ids(cell_input["acceptance_requirement_ids"]),
            "metric_case": _document_mapping(cell_input["metric_case"], "metric case"),
            "simulator_answer_digest": canonical_digest(answer_document),
            "case_contract": _document_mapping(cell_input["case_contract"], "case contract"),
        }
        return {
            "execution": self._execution(context),
            "handoff": handoff,
            "build_contract": build_contract,
        }

    def native_v1_planner(
        self,
        context: FreshRoleContext,
        artifacts: Mapping[str, Any],
        native_runtime: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Bind the canonical arm to a validated, invoked vendored v1 runtime receipt."""

        from .state import canonical_digest

        received = transferred_artifacts(context, artifacts)
        if context.role is not WorkerRole.PLANNER:
            raise WorkerSessionError("native v1 planning requires a planner context")
        cell_input = _cell_input(received["cell-input"])
        identity = _document_mapping(cell_input["identity"], "cell input identity")
        cell_id = _required_identifier(cell_input["cell_id"], "cell_id")
        runtime = _document_mapping(native_runtime, "native v1 runtime receipt")
        if runtime.get("schema") not in {"NativeV1FixtureRuntimeReceipt.v1", "NativeV1FixtureRuntimeReceipt.v2"} or runtime.get("implementation_ready") is not True:
            raise WorkerSessionError("canonical arm requires a successful native v1 runtime receipt")
        handoff = {
            "schema": "NativeV1StructuralHandoff.v1",
            "cell_id": cell_id,
            "source_input_digest": context.declared_artifacts[0].digest,
            "arm_id": _required_text(identity.get("arm_id"), "arm_id"),
            "case_contract": _document_mapping(cell_input["case_contract"], "case contract"),
        }
        build_contract = {
            "schema": "NativeV1StructuralBuildContract.v1",
            "cell_id": cell_id,
            "handoff_digest": canonical_digest(handoff),
            "arm_id": handoff["arm_id"],
            "acceptance_atom_ids": _atom_ids(cell_input["acceptance_requirement_ids"]),
            "metric_case": _document_mapping(cell_input["metric_case"], "metric case"),
            "native_runtime_digest": canonical_digest(runtime),
            "case_contract": _document_mapping(cell_input["case_contract"], "case contract"),
        }
        return {
            "execution": self._execution(context),
            "handoff": handoff,
            "build_contract": build_contract,
        }

    def direct_implementer(self, context: FreshRoleContext, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        """Run direct-v1 from the cell input with no planner handoff or build contract."""

        from .state import canonical_digest

        received = transferred_artifacts(context, artifacts)
        if context.role is not WorkerRole.IMPLEMENTER or context.source_role is not None:
            raise WorkerSessionError("direct implementation requires a direct implementer context")
        cell_input = _cell_input(received["cell-input"])
        cell_id = _required_identifier(cell_input["cell_id"], "cell_id")
        acceptance_atom_ids = _atom_ids(cell_input["acceptance_requirement_ids"])
        implementation = {
            "schema": "DirectDevelopmentImplementation.v1",
            "cell_id": cell_id,
            "input_digest": context.declared_artifacts[0].digest,
            "implemented_atom_ids": acceptance_atom_ids,
            "implementation_recipe": DETERMINISTIC_STARTER_IMPLEMENTATION,
            "changes": [{"path": "starter/cli.py", "operation": "replace"}],
            "case_contract": _document_mapping(cell_input["case_contract"], "case contract"),
            "provenance": self._execution(context)["provenance"],
        }
        return {
            "execution": self._execution(context),
            "implementation": implementation,
        }

    def implementer(self, context: FreshRoleContext, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        """Execute a generic or native-v1 contract after verifying its handoff binding."""

        from .state import canonical_digest

        received = transferred_artifacts(context, artifacts)
        if context.role is not WorkerRole.IMPLEMENTER or context.source_role is not WorkerRole.PLANNER:
            raise WorkerSessionError("contract implementation requires a planned implementer context")
        handoff = _document_mapping(received["handoff"], "handoff")
        build_contract = _document_mapping(received["build-contract"], "build contract")
        if build_contract.get("schema") not in {
            "GenericSimulatorBuildContract.v1",
            "NativeV1StructuralBuildContract.v1",
        }:
            raise WorkerSessionError("implementer requires a supported generic or native v1 build contract")
        if build_contract.get("handoff_digest") != canonical_digest(handoff):
            raise WorkerSessionError("build contract is not bound to its declared handoff")
        cell_id = _required_identifier(build_contract.get("cell_id"), "cell_id")
        acceptance_atom_ids = _atom_ids(build_contract.get("acceptance_atom_ids"))
        build_contract_digest = context.declared_artifacts[
            tuple(item.artifact_id for item in context.declared_artifacts).index("build-contract")
        ].digest
        implementation = {
            "schema": "DevelopmentImplementation.v1",
            "cell_id": cell_id,
            "build_contract_digest": build_contract_digest,
            "implemented_atom_ids": acceptance_atom_ids,
            "implementation_recipe": DETERMINISTIC_STARTER_IMPLEMENTATION,
            "changes": [
                {
                    "path": "starter/cli.py",
                    "operation": "replace",
                    "build_contract_digest": build_contract_digest,
                }
            ],
            "case_contract": _document_mapping(build_contract.get("case_contract"), "case contract"),
            "provenance": self._execution(context)["provenance"],
        }
        return {
            "execution": self._execution(context),
            "implementation": implementation,
        }

    def postmortem(
        self,
        context: FreshRoleContext,
        artifacts: Mapping[str, Any],
        request: Any,
    ) -> dict[str, Any]:
        received = transferred_artifacts(context, artifacts)
        if context.role is not WorkerRole.POSTMORTEM:
            raise WorkerSessionError("postmortem execution requires a postmortem context")
        if isinstance(request, Mapping):
            return self._direct_postmortem(context, received, request)
        return self._contract_postmortem(context, received, request)

    def _contract_postmortem(
        self,
        context: FreshRoleContext,
        received: Mapping[str, Any],
        request: Any,
    ) -> dict[str, Any]:
        from .state import canonical_digest

        evidence_manifest = _document_mapping(received["evidence-manifest"], "evidence manifest")
        if canonical_digest(received["postmortem-request"]) != canonical_digest(
            request.model_dump(mode="json", by_alias=True, exclude_none=False)
        ):
            raise WorkerSessionError("postmortem request was not transferred as a declared artifact")
        if request.artifact_manifest_digest != canonical_digest(evidence_manifest):
            raise WorkerSessionError("postmortem request is not bound to declared evidence manifest")
        for artifact_id, request_field in (
            ("build-contract", "build_contract_digest"),
            ("implementation", "implementation_digest"),
            ("observation", "observation_digest"),
        ):
            if getattr(request, request_field) != canonical_digest(received[artifact_id]):
                raise WorkerSessionError(f"postmortem request is not bound to {artifact_id}")
        report = self._postmortem_client.attribute(request)
        return {
            "execution": self._execution(context),
            "report": report.model_dump(mode="json", by_alias=True, exclude_none=False),
        }

    def _direct_postmortem(
        self,
        context: FreshRoleContext,
        received: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        from .state import canonical_digest

        request_document = _document_mapping(request, "direct postmortem request")
        evidence_manifest = _document_mapping(received["evidence-manifest"], "evidence manifest")
        if request_document.get("schema") != "DirectPostmortemRequest.v1":
            raise WorkerSessionError("direct postmortem requires its direct request shape")
        if canonical_digest(received["postmortem-request"]) != canonical_digest(request_document):
            raise WorkerSessionError("direct postmortem request was not transferred as a declared artifact")
        for artifact_id, request_field in (
            ("evidence-manifest", "artifact_manifest_digest"),
            ("implementation", "implementation_digest"),
            ("observation", "observation_digest"),
        ):
            if request_document.get(request_field) != canonical_digest(received[artifact_id]):
                raise WorkerSessionError(f"direct postmortem request is not bound to {artifact_id}")
        return {
            "execution": self._execution(context),
            "report": {
                "schema": "DirectPostmortemReport.v1",
                "report_id": _derived_identifier("postreport", context.context_id),
                "request_id": _required_identifier(request_document.get("request_id"), "request_id"),
                "run_id": _required_identifier(request_document.get("run_id"), "run_id"),
                "cell_id": _required_identifier(request_document.get("cell_id"), "cell_id"),
                "fresh_context_id": context.context_id,
                "artifact_manifest_digest": canonical_digest(evidence_manifest),
                "implementation_digest": canonical_digest(received["implementation"]),
                "observation_digest": canonical_digest(received["observation"]),
                "provenance": self._execution(context)["provenance"],
                "assurance": "none",
            },
        }

    def _execution(self, context: FreshRoleContext) -> dict[str, Any]:
        cached = self._executions.get(context.context_id)
        if cached is not None:
            return cached
        request_id = _derived_identifier("request", context.context_id)
        worker_id = f"worker-{context.role.value}"
        session = self._worker_client.open_session(
            WorkerSessionRequest(
                request_id=request_id,
                worker_id=worker_id,
                role=context.role,
            )
        )
        authorizations = tuple(
            self._worker_client.authorize(
                WorkerCapabilityRequest(
                    request_id=_derived_identifier(capability.value.replace("_", "-"), context.context_id),
                    session_id=session.session_id,
                    worker_id=worker_id,
                    role=context.role,
                    capability=capability,
                )
            )
            for capability in session.capabilities
        )
        closed = self._worker_client.close_session(session.session_id)
        result = {
            "schema": "RoleExecutionReceipt.v1",
            "context_id": context.context_id,
            "role": context.role.value,
            "session": session.model_dump(mode="json", by_alias=True, exclude_none=False),
            "authorizations": [
                item.model_dump(mode="json", by_alias=True, exclude_none=False) for item in authorizations
            ],
            "closed_session": closed.model_dump(mode="json", by_alias=True, exclude_none=False),
            "provenance": session.provenance,
        }
        self._executions[context.context_id] = result
        return result


def _document_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkerSessionError(f"{field_name} must be a JSON object")
    return value
def _cell_input(value: Any) -> Mapping[str, Any]:
    document = _document_mapping(value, "cell input")
    if document.get("schema") != "CellInput.v2":
        raise WorkerSessionError("worker requires a CellInput.v2 artifact")
    return document



def _required_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise WorkerSessionError(f"{field_name} must be an opaque identifier")
    try:
        return _identifier(value, field_name)
    except ValueError as error:
        raise WorkerSessionError(str(error)) from error


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerSessionError(f"{field_name} must be nonblank text")
    return value


def _atom_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        candidates = value
    elif isinstance(value, list):
        candidates = tuple(value)
    else:
        raise WorkerSessionError("acceptance atoms must be a JSON array")
    atom_ids: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            candidate = candidate.get("atom_id")
        atom_ids.append(_required_identifier(candidate, "atom_id"))
    normalized = tuple(sorted(atom_ids))
    if not normalized or len(set(normalized)) != len(normalized):
        raise WorkerSessionError("acceptance atom identifiers must be unique and sorted")
    return normalized


def _derived_identifier(prefix: str, value: str) -> str:
    return f"{prefix}-{sha256(value.encode('utf-8')).hexdigest()[:24]}"
