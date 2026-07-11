import json

import pytest
from pydantic import ValidationError

import execution_return as schema
from postmortem_bundle import JsonValue


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DECISION_LOG = ".ultimateinterview/demo/decisions.jsonl"


def _expectation(
    *, contract_digest: str = DIGEST_A, decision_log_digest: str = DIGEST_A, decision_log_path: str = DECISION_LOG
) -> schema.ExecutionExpectation:
    return schema.ExecutionExpectation(
        contract_digest=contract_digest,
        requirement_ids=("REQ-001", "REQ-002"),
        verifications=(
            schema.ExpectedVerification(id="VER-001", command_action="pytest -q -k ver-001"),
            schema.ExpectedVerification(id="VER-002", command_action="pytest -q -k ver-002"),
        ),
        decision_log_path=decision_log_path,
        decision_log_digest=decision_log_digest,
        decision_record_refs=("decision#1", "decision#2"),
    )


def _exact(subject_id: str, capture_id: str) -> dict[str, JsonValue]:
    return {
        "subject_id": subject_id,
        "result": "exact-pass",
        "actual_command": f"pytest -q -k {subject_id.lower()}",
        "capture_artifact_id": capture_id,
        "evidence_artifact_ids": ["evidence-diff"],
    }


def _adapted(subject_id: str, capture_id: str) -> dict[str, JsonValue]:
    return {
        "subject_id": subject_id,
        "result": "adapted-pass",
        "actual_command": f"pytest -q -k {subject_id.lower()}_adapted",
        "capture_artifact_id": capture_id,
        "evidence_artifact_ids": ["evidence-diff"],
        "adaptation_reason": "The original selector was unavailable on this host.",
        "decision_record_ref": "decision#1",
    }


def _completed_envelope() -> dict[str, JsonValue]:
    return {
        "marker": "EXECUTION-RETURN",
        "schema_version": 1,
        "contract_digest": DIGEST_A,
        "status": "completed",
        "changed_paths": ["src/café.py", "src/cafe\u0301.py", "src/資料.py", "src/😀.py"],
        "requirement_outcomes": [
            _exact("REQ-001", "capture-req1"),
            _adapted("REQ-002", "capture-req2"),
        ],
        "verification_outcomes": [
            _exact("VER-001", "capture-ver1"),
            _exact("VER-002", "capture-ver2"),
        ],
        "decision_log": {"path": DECISION_LOG, "sha256": DIGEST_A},
        "blocker_reasons": [],
        "deviations": ["decision#2"],
        "capture_artifact_ids": ["capture-req1", "capture-req2", "capture-ver1", "capture-ver2"],
        "evidence_artifact_ids": ["evidence-diff"],
    }


def _json_list(envelope: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = envelope[key]
    assert isinstance(value, list)
    return value


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _blocked_envelope() -> dict[str, JsonValue]:
    envelope = _completed_envelope()
    envelope["status"] = "blocked"
    envelope["blocker_reasons"] = ["Credentialed staging access was unavailable."]
    _json_list(envelope, "requirement_outcomes")[1] = {
        "subject_id": "REQ-002",
        "result": "not-run",
        "reason": "Credentialed staging access was unavailable.",
    }
    return envelope


def _failed_envelope() -> dict[str, JsonValue]:
    envelope = _completed_envelope()
    envelope["status"] = "failed"
    _json_list(envelope, "verification_outcomes")[1] = {
        "subject_id": "VER-002",
        "result": "fail",
        "actual_command": "pytest -q -k ver-002",
        "capture_artifact_id": "capture-ver2",
        "evidence_artifact_ids": ["evidence-diff"],
        "failure_reason": "The real-surface assertion failed.",
    }
    return envelope


@pytest.mark.parametrize(
    ("envelope_factory", "expected_status"),
    [(_completed_envelope, "completed"), (_blocked_envelope, "blocked"), (_failed_envelope, "failed")],
)
def test_round_trip_when_envelope_is_valid(envelope_factory, expected_status) -> None:
    # Given: complete executor-owned coverage for a known BuildContract
    raw = json.dumps(envelope_factory())

    # When: the JSON boundary is parsed and serialized again
    parsed = schema.validate_execution_return(raw, _expectation())
    reparsed = schema.validate_execution_return(parsed.model_dump_json(), _expectation())

    # Then: provenance and the terminal status survive the round trip
    assert reparsed == parsed
    assert reparsed.status == expected_status


def test_unknown_field_fails_closed_when_owned_return_is_present() -> None:
    # Given: a parseable owned return with undeclared embedded output
    envelope = _completed_envelope()
    envelope["stdout"] = "misleading success"

    # When/Then: strict parsing rejects the malformed owned envelope
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_foreign_contract_digest_is_rejected() -> None:
    # Given: a structurally valid return bound to a stale contract digest
    envelope = _completed_envelope()

    # When/Then: expected-contract validation rejects foreign provenance
    with pytest.raises(schema.ExecutionReturnContractError, match="contract_digest"):
        schema.validate_execution_return(
            json.dumps(envelope), _expectation(contract_digest=DIGEST_B)
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign"])
def test_requirement_coverage_is_exact_when_ids_are_expected(mutation: str) -> None:
    # Given: a return whose REQ outcomes do not bijectively cover the contract
    envelope = _completed_envelope()
    if mutation == "missing":
        _json_list(envelope, "requirement_outcomes").pop()
    elif mutation == "duplicate":
        _json_object(_json_list(envelope, "requirement_outcomes")[1])["subject_id"] = "REQ-001"
    else:
        _json_object(_json_list(envelope, "requirement_outcomes")[1])["subject_id"] = "REQ-999"

    # When/Then: validation rejects missing, duplicate, and foreign REQ IDs
    with pytest.raises(schema.ExecutionReturnContractError, match="requirement"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_verification_coverage_is_exact_when_ids_are_expected() -> None:
    # Given: a return missing one expected VER result
    envelope = _completed_envelope()
    _json_list(envelope, "verification_outcomes").pop()

    # When/Then: coverage validation rejects the incomplete VER projection
    with pytest.raises(schema.ExecutionReturnContractError, match="verification"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize(
    ("requirement_ids", "verification_ids", "decision_ref"),
    [("REQ-NAME", "VER-001", "decision#1"), ("REQ-001", "VER-NAME", "decision#1"), ("REQ-001", "VER-001", "DEC-001")],
)
def test_expected_ids_match_build_contract_v1_shape(
    requirement_ids: str, verification_ids: str, decision_ref: str
) -> None:
    # Given: an expectation containing an ID BuildContract v1 cannot emit
    # When/Then: expectation parsing rejects the incompatible coordinate
    with pytest.raises(ValidationError):
        schema.ExecutionExpectation(
            contract_digest=DIGEST_A,
            requirement_ids=(requirement_ids,),
            verifications=(
                schema.ExpectedVerification(id=verification_ids, command_action="pytest -q"),
            ),
            decision_log_path=DECISION_LOG,
            decision_log_digest=DIGEST_A,
            decision_record_refs=(decision_ref,),
        )


@pytest.mark.parametrize("empty_coordinate", ["requirements", "verifications"])
def test_expectation_requires_nonempty_contract_coverage(
    empty_coordinate: str,
) -> None:
    # Given: a BuildContract expectation with one empty required ID set
    requirement_ids = () if empty_coordinate == "requirements" else ("REQ-001",)
    verifications = () if empty_coordinate == "verifications" else (
        schema.ExpectedVerification(id="VER-001", command_action="pytest -q -k ver-001"),
    )

    # When/Then: zero-outcome completion cannot be made valid by an empty expectation
    with pytest.raises(ValidationError):
        schema.ExecutionExpectation(
            contract_digest=DIGEST_A,
            requirement_ids=requirement_ids,
            verifications=verifications,
            decision_log_path=DECISION_LOG,
            decision_log_digest=DIGEST_A,
        )


def test_completed_status_rejects_open_blocker() -> None:
    # Given: a completed return that still reports an open blocker
    envelope = _completed_envelope()
    envelope["blocker_reasons"] = ["Deployment approval is pending."]

    # When/Then: terminal-state validation rejects misleading completion
    with pytest.raises(ValidationError, match="completed"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize("terminal_outcome", ["fail", "not-run"])
def test_completed_status_rejects_nonpassing_outcome(terminal_outcome: str) -> None:
    # Given: a completed return whose required REQ did not pass
    envelope = _failed_envelope() if terminal_outcome == "fail" else _blocked_envelope()
    envelope["status"] = "completed"
    envelope["blocker_reasons"] = []

    # When/Then: completion cannot hide a failed or unexecuted requirement
    with pytest.raises(ValidationError, match="completed"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize(
    "missing_field",
    ["actual_command", "capture_artifact_id", "adaptation_reason", "decision_record_ref"],
)
def test_adapted_pass_requires_provenance(missing_field: str) -> None:
    # Given: an adapted pass missing one provenance coordinate
    envelope = _completed_envelope()
    del _json_object(_json_list(envelope, "requirement_outcomes")[1])[missing_field]

    # When/Then: the discriminated variant fails structurally
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_exact_verification_pass_must_match_build_contract_command() -> None:
    # Given: an exact-pass VER that actually ran an arbitrary substitute command
    envelope = _completed_envelope()
    _json_object(_json_list(envelope, "verification_outcomes")[0])["actual_command"] = "true"

    # When/Then: exact-pass provenance is bound to the expected VER command
    with pytest.raises(schema.ExecutionReturnContractError, match="exact_command"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_adapted_verification_command_must_differ_from_exact_command() -> None:
    # Given: an adapted-pass VER whose command is byte-identical to BuildContract
    envelope = _completed_envelope()
    _json_list(envelope, "verification_outcomes")[0] = {
        **_adapted("VER-001", "capture-ver1"),
        "actual_command": "pytest -q -k ver-001",
    }

    # When/Then: an exact execution cannot be laundered as adapted
    with pytest.raises(schema.ExecutionReturnContractError, match="adapted_command"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_adapted_pass_decision_record_must_resolve_in_expected_log_index() -> None:
    # Given: an adapted pass citing a syntactically valid but foreign decision record
    envelope = _completed_envelope()
    _json_object(_json_list(envelope, "requirement_outcomes")[1])["decision_record_ref"] = "decision#999"

    # When/Then: the decision reference must resolve against the validated log index
    with pytest.raises(schema.ExecutionReturnContractError, match="decision_record"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_deviation_record_must_resolve_in_expected_log_index() -> None:
    # Given: a deviation reference absent from the validated decision-log index
    envelope = _completed_envelope()
    envelope["deviations"] = ["decision#999"]

    # When/Then: provenance validation rejects the dangling record ID
    with pytest.raises(schema.ExecutionReturnContractError, match="decision_record"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_decision_log_provenance_must_match_expected_digest() -> None:
    # Given: a return citing the right log path but stale log content
    envelope = _completed_envelope()

    # When/Then: validation rejects the stale decision-log digest
    with pytest.raises(schema.ExecutionReturnContractError, match="decision_log_digest"):
        schema.validate_execution_return(
            json.dumps(envelope), _expectation(decision_log_digest=DIGEST_B)
        )


def test_decision_contents_cannot_be_duplicated_into_return() -> None:
    # Given: decision contents copied into the provenance-only decision-log reference
    envelope = _completed_envelope()
    _json_object(envelope["decision_log"])["decisions"] = [{"decision": "copied content"}]

    # When/Then: the nested strict model rejects duplicated decision content
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize("bad_path", ["/tmp/decisions.jsonl", ".ultimateinterview/../decisions.jsonl", ".ultimateinterview/demo\\sub/decisions.jsonl", ".ultimateinterview/demo\u0085/decisions.jsonl", ".ultimateinterview/demo\u202e/decisions.jsonl"])
def test_decision_log_path_uses_build_contract_shape(bad_path: str) -> None:
    # Given/When/Then: return and expectation boundaries reject noncanonical log paths
    with pytest.raises(ValidationError):
        schema.DecisionLogReference(path=bad_path, sha256=DIGEST_A)
    with pytest.raises(ValidationError):
        _expectation(decision_log_path=bad_path)


def test_outcome_artifact_reference_must_be_declared() -> None:
    # Given: an exact pass citing a capture absent from the envelope inventory
    envelope = _completed_envelope()
    _json_object(_json_list(envelope, "requirement_outcomes")[0])["capture_artifact_id"] = "capture-foreign"

    # When/Then: the envelope rejects the dangling artifact reference
    with pytest.raises(ValidationError, match="capture"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize("artifact_id", ["not valid", "../capture", "capture/id"])
def test_artifact_ids_are_stable_tokens(artifact_id: str) -> None:
    # Given: a capture inventory containing a path-like or whitespace ID
    envelope = _completed_envelope()
    _json_list(envelope, "capture_artifact_ids")[0] = artifact_id

    # When/Then: artifact-reference shape validation rejects it
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_failed_variant_cannot_also_claim_pass() -> None:
    # Given: a failed VER variant with an extra pass claim
    envelope = _failed_envelope()
    _json_object(_json_list(envelope, "verification_outcomes")[1])["claimed_result"] = "pass"

    # When/Then: the discriminated strict variant rejects the impossible state
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


def test_missing_requirement_command_is_rejected() -> None:
    # Given: an exact REQ pass without the actual command it reports executing
    envelope = _completed_envelope()
    del _json_object(_json_list(envelope, "requirement_outcomes")[0])["actual_command"]

    # When/Then: the exact-pass variant cannot be constructed
    with pytest.raises(ValidationError):
        schema.validate_execution_return(json.dumps(envelope), _expectation())


@pytest.mark.parametrize("changed_path", ["/tmp/foreign.py", "../escape.py", "src\\app.py", "src/\u0000app.py", "src/\u0085app.py", "src/\u202eapp.py"])
def test_changed_paths_are_canonical_repo_relative_paths(changed_path: str) -> None:
    # Given: a return with a non-repository-relative changed path
    envelope = _completed_envelope()
    envelope["changed_paths"] = [changed_path]

    # When/Then: path-shape validation rejects it
    with pytest.raises(ValidationError, match="changed_paths"):
        schema.validate_execution_return(json.dumps(envelope), _expectation())
