#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "pytest>=8.0", "rich>=13.7", "typer>=0.12"]
# ///

from __future__ import annotations

import json
import shutil
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import typer
from typer.testing import CliRunner

from scripts import atomic_write, build_contract, implementation_gate, protocol_state, receipt_import, session_init, session_status, session_update

V0_READY = Path(__file__).parent / "regression_fixtures" / "ready-minimal"
V1_READY = Path(__file__).parent / "integration_fixtures" / "v1-ready"
V2_READY = Path(__file__).parent / "integration_fixtures" / "v2-ready"
NOW = datetime(2026, 7, 11, tzinfo=UTC)


def manifest_module() -> ModuleType:
    from scripts import session_manifest

    return session_manifest


def status_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_status.main)
    return app


def init_app() -> typer.Typer:
    app = typer.Typer()
    app.command()(session_init.main)
    return app


def v2_session(tmp_path: Path, name: str = "v2-ready") -> Path:
    session = tmp_path / ".ultimateinterview" / name
    session.parent.mkdir()
    shutil.copytree(V2_READY, session)
    handoff_path = session / "handoff.md"
    handoff = handoff_path.read_text(encoding="utf-8").replace("v2-ready", name)
    handoff_path.write_text(handoff, encoding="utf-8")
    protocol_path = session / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol.update(
        {
            "build_contract_digest": implementation_gate.contract_digest(handoff),
        },
    )
    protocol_state.parse_state(json.dumps(protocol))
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
    contract = build_contract.compile_handoff(handoff)
    (session / "build-contract.json").write_text(
        build_contract.canonical_json(contract),
        encoding="utf-8",
    )
    return session


@pytest.mark.parametrize("fixture", (V0_READY, V1_READY))
def test_v0_v1_status_remains_unsealed_and_byte_compatible(
    tmp_path: Path,
    fixture: Path,
) -> None:
    # Given
    session = tmp_path / fixture.name
    shutil.copytree(fixture, session)

    # When
    result = CliRunner().invoke(status_app(), ["--format", "json", str(session)])

    # Then
    assert result.exit_code == 0, result.output
    assert "manifest_digest" not in json.loads(result.output)
    assert "snapshot_complete" not in json.loads(result.output)


def test_v2_session_init_creates_decision_log_and_valid_protocol(tmp_path: Path) -> None:
    # Given
    repo = tmp_path / "repo"
    repo.mkdir()
    entries = json.dumps(
        [
            {
                "id": "REQ-001",
                "requirement": "A bounded behavior",
                "origin": "orientation",
                "status": "draft",
                "ambiguity_score": 3,
                "impact_weight": 5,
                "assurance_class": "high",
                "behavior_atoms": [
                    {
                        "id": "ATOM-001",
                        "condition": "The bounded behavior is invoked.",
                        "polarity": "must",
                        "observable_response": "The bounded behavior is observable.",
                        "boundary_context": None,
                        "temporal_context": None,
                        "coercion_context": None,
                    },
                ],
                "evidence_channels": ["from-user"],
            },
        ],
    )

    # When
    result = CliRunner().invoke(
        init_app(),
        [str(repo), "v2-init", "--entries", entries, "--schema-version", "2"],
    )

    # Then
    session = repo / ".ultimateinterview" / "v2-init"
    assert result.exit_code == 0, result.output
    assert (session / "decisions.jsonl").read_text(encoding="utf-8") == ""
    assert protocol_state.parse_state((session / "protocol.json").read_text()).evidence_schema_version == 2


def test_seal_binds_every_required_member_and_status_reports_complete_snapshot(
    tmp_path: Path,
) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest = manifest_module()

    # When
    sealed = manifest.seal_session(session)
    result = CliRunner().invoke(
        status_app(),
        ["--format", "json", "--require-manifest", str(session)],
    )

    # Then
    rendered = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert rendered["manifest_digest"] == sealed.manifest_digest
    assert rendered["snapshot_complete"] is True
    assert tuple(member.path for member in sealed.members) == manifest.REQUIRED_MEMBERS


def test_v2_noncreditable_receipt_preserves_trace_but_fails_readiness(
    tmp_path: Path,
) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest_module().seal_session(session)
    receipt_import.import_receipt(
        session,
        (V2_READY / "verification-receipt.json").read_text(encoding="utf-8"),
        now=NOW,
    )

    # When
    result = CliRunner().invoke(
        status_app(),
        ["--format", "json", "--gate", "--require-manifest", "--require-execution-receipts", str(session)],
    )

    # Then
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["assurance"]["trace"] == "pass"
    assert payload["assurance"]["property"] == "not-run"
    assert payload["execution_receipts_creditable"] is False


def test_status_does_not_report_ready_from_mixed_session_generations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an initially sealed generation with a current simulated receipt.
    session = v2_session(tmp_path)
    manifest = manifest_module()
    generation_a = manifest.seal_session(session)
    receipt_import.import_receipt(
        session,
        (V2_READY / "verification-receipt.json").read_text(encoding="utf-8"),
        now=NOW,
    )
    generation_b: list[str] = []

    def replace_with_blocked_generation() -> None:
        ledger_path = session / "ledger.json"
        with original_write_transaction(session):
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["entries"][0]["ambiguity_score"] = 3
            atomic_write.commit_text_files(
                {ledger_path: json.dumps(ledger, indent=2) + "\n"},
                locked=True,
            )
        generation_b.append(manifest.seal_session(session).manifest_digest)
        with original_write_transaction(session):
            for receipt_path in (session / "receipts").glob("*.json"):
                receipt_path.unlink()
        receipt_import.import_receipt(
            session,
            (V2_READY / "verification-receipt.json").read_text(encoding="utf-8"),
            now=NOW,
        )

    # When: the old reader has released its first lock but has not yet read the
    # manifest or receipt generation. The writer completes a blocked reseal.
    original_write_transaction, original_read_transaction = (
        atomic_write.session_transaction,
        atomic_write.session_read_transaction,
    )
    barrier_armed = True
    writer: threading.Thread | None = None

    @contextmanager
    def transaction_with_generation_barrier(root: Path) -> Iterator[None]:
        nonlocal barrier_armed, writer
        with original_read_transaction(root):
            yield
        if root.resolve() == session.resolve() and barrier_armed:
            barrier_armed = False
            writer = threading.Thread(target=replace_with_blocked_generation)
            writer.start()
            writer.join(timeout=2)

    monkeypatch.setattr(atomic_write, "session_read_transaction", transaction_with_generation_barrier)
    result = CliRunner().invoke(
        status_app(),
        [
            "--format",
            "json",
            "--gate",
            "--require-manifest",
            "--require-execution-receipts",
            str(session),
        ],
    )

    # Then: the serialized reader reports only its coherent pre-write snapshot.
    assert writer is not None
    assert not writer.is_alive()
    assert generation_b
    assert generation_b[0] != generation_a.manifest_digest
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["interview_converged"] is True
    assert payload["implementation_gate"]["implementation_ready"] is False
    assert payload["manifest_digest"] == generation_a.manifest_digest
    assert payload["execution_receipts_current"] is True
    assert payload["execution_receipts_creditable"] is False


def test_seal_rejects_missing_required_member(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    (session / "questions.json").unlink()
    manifest = manifest_module()

    # When / Then
    with pytest.raises(manifest.SessionManifestError, match="questions.json"):
        manifest.seal_session(session)


def test_seal_rejects_a_non_session_decision_log_path(tmp_path: Path) -> None:
    session = v2_session(tmp_path)
    sidecar_path = session / "build-contract.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["decision_log_path"] = "decisions.jsonl"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    with pytest.raises(manifest_module().SessionManifestError, match="decision_log_path"):
        manifest_module().seal_session(session)


def test_seal_rejects_a_stale_derived_build_contract(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    handoff_path = session / "handoff.md"
    handoff_path.write_text(
        handoff_path.read_text(encoding="utf-8").replace(
            "validation command executes",
            "validation command executes with a stale source mutation",
        ),
        encoding="utf-8",
    )
    manifest = manifest_module()

    # When / Then
    with pytest.raises(manifest.SessionManifestError, match="build-contract"):
        manifest.seal_session(session)


def test_seal_rejects_symlink_and_escaping_manifest_member(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    decisions = session / "decisions.jsonl"
    decisions.unlink()
    decisions.symlink_to(session / "ledger.json")
    manifest = manifest_module()

    # When / Then
    with pytest.raises(manifest.SessionManifestError, match="symlink"):
        manifest.seal_session(session)


def test_manifest_status_rejects_symlinked_session_lock_without_creating_target(
    tmp_path: Path,
) -> None:
    # Given
    session = v2_session(tmp_path)
    lock_target = tmp_path / "outside-session.lock"
    lock_path = session / atomic_write.LOCK_NAME
    lock_path.unlink(missing_ok=True)
    lock_path.symlink_to(lock_target)

    # When
    status = manifest_module().manifest_status(session)

    # Then
    assert status.snapshot_complete is False
    assert status.reason is not None
    assert "session lock" in status.reason
    assert not lock_target.exists()


def test_session_status_rejects_symlinked_session_lock_without_creating_target(
    tmp_path: Path,
) -> None:
    # Given
    session = v2_session(tmp_path)
    lock_target = tmp_path / "outside-session.lock"
    lock_path = session / atomic_write.LOCK_NAME
    lock_path.unlink(missing_ok=True)
    lock_path.symlink_to(lock_target)

    # When
    result = CliRunner().invoke(status_app(), ["--format", "json", str(session)])

    # Then
    assert result.exit_code != 0
    assert "session lock must be a regular non-symlink file" in result.output
    assert not lock_target.exists()


def test_session_readers_fail_closed_for_a_pending_recovery_journal(
    tmp_path: Path,
) -> None:
    # Given: an interrupted writer has left a journal and an incomplete source file.
    session = v2_session(tmp_path)
    manifest = manifest_module()
    manifest.seal_session(session)
    ledger_path = session / "ledger.json"
    original_ledger = ledger_path.read_text(encoding="utf-8")
    atomic_write.write_recovery_journal({ledger_path: original_ledger}, root=session)
    ledger_path.write_text("{\"incomplete\": true}\n", encoding="utf-8")
    before = {
        path.relative_to(session): path.read_bytes()
        for path in sorted(session.rglob("*"))
        if path.is_file()
    }

    # When: status and manifest readers inspect the interrupted session.
    status_result = CliRunner().invoke(status_app(), ["--format", "json", str(session)])
    manifest_result = manifest.manifest_status(session)

    # Then: both report recovery is pending and neither reader mutates the session.
    assert status_result.exit_code != 0
    assert "pending recovery" in status_result.output
    assert manifest_result.snapshot_complete is False
    assert manifest_result.reason is not None
    assert "pending recovery" in manifest_result.reason
    after = {
        path.relative_to(session): path.read_bytes()
        for path in sorted(session.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_manifest_rejects_an_escaping_member_path_even_when_bytes_match(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest = manifest_module()
    manifest.seal_session(session)
    manifest_path = session / manifest.MANIFEST_NAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["members"][0]["path"] = "../ledger.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    # When
    status = manifest.manifest_status(session)

    # Then
    assert status.snapshot_complete is False
    assert "path" in status.reason


def test_same_schema_version_different_source_digest_requires_a_new_seal(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest = manifest_module()
    first = manifest.seal_session(session)
    decisions = session / "decisions.jsonl"
    decisions.write_text(decisions.read_text(encoding="utf-8") + '{"decision":"keep"}\n', encoding="utf-8")

    # When
    second = manifest.seal_session(session)

    # Then
    assert first.schema_versions == second.schema_versions == {"evidence": 2, "contract": 2}
    assert first.manifest_digest != second.manifest_digest


def test_recompile_after_seal_requires_reseal_before_manifest_is_required(
    tmp_path: Path,
) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest = manifest_module()
    manifest.seal_session(session)
    handoff = (session / "handoff.md").read_text(encoding="utf-8")
    (session / "build-contract.json").write_text(
        build_contract.canonical_json(build_contract.compile_handoff(handoff)),
        encoding="utf-8",
    )

    # When
    stale = CliRunner().invoke(
        status_app(),
        ["--format", "json", "--require-manifest", str(session)],
    )
    manifest.seal_session(session)
    resealed = CliRunner().invoke(
        status_app(),
        ["--format", "json", "--require-manifest", str(session)],
    )

    # Then
    assert stale.exit_code == 1
    assert json.loads(stale.output)["snapshot_complete"] is False
    assert resealed.exit_code == 0, resealed.output


def test_rejected_update_keeps_manifest_and_source_bytes_atomic(tmp_path: Path) -> None:
    # Given
    session = v2_session(tmp_path)
    manifest = manifest_module()
    manifest.seal_session(session)
    paths = tuple(session / name for name in (*manifest.REQUIRED_MEMBERS, manifest.MANIFEST_NAME))
    before = {path: path.read_bytes() for path in paths}
    delta = session_update.parse_delta(
        json.dumps({"set": [{"id": "missing", "ambiguity_score": 0}]}),
    )

    # When / Then
    with pytest.raises(typer.BadParameter, match="no ledger entry"):
        session_update.update_session(session, delta)
    assert {path: path.read_bytes() for path in paths} == before
    assert manifest.manifest_status(session).snapshot_complete is True


def test_authored_update_keeps_the_prior_manifest_as_an_atomic_stale_snapshot(
    tmp_path: Path,
) -> None:
    session = v2_session(tmp_path)
    manifest = manifest_module()
    manifest.seal_session(session)
    manifest_path = session / manifest.MANIFEST_NAME
    before = manifest_path.read_bytes()
    delta = session_update.parse_delta(
        json.dumps({"transcript": {"title": "authored note", "lines": ["bound change"]}}),
    )

    session_update.update_session(session, delta)

    assert manifest_path.read_bytes() == before
    status = manifest.manifest_status(session)
    assert status.snapshot_complete is False
    assert status.reason in {
        "session manifest is stale for ledger.json",
        "session manifest is stale for protocol.json",
        "session manifest is stale for transcript.md",
    }


def test_v2_preseal_fixture_is_portable_to_the_manual_qa_session_path(
    tmp_path: Path,
) -> None:
    session = tmp_path / "session"
    shutil.copytree(V2_READY, session)
    handoff = (session / "handoff.md").read_text(encoding="utf-8")
    (session / "build-contract.json").write_text(
        build_contract.canonical_json(build_contract.compile_handoff(handoff)),
        encoding="utf-8",
    )

    sealed = manifest_module().seal_session(session)

    assert manifest_module().manifest_status(session).manifest_digest == sealed.manifest_digest
