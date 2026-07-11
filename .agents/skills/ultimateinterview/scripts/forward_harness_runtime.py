from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

from scripts import (
    ambiguity_ledger,
    assurance_schema,
    build_contract_schema,
    handoff_coverage,
    implementation_gate,
    protocol_state,
    receipt_contract,
    receipt_import,
    session_manifest,
    session_status,
)
from scripts.forward_harness_contract import (
    ForwardGate,
    ForwardHarnessError,
    ForwardInput,
    ForwardResult,
    ForwardVerdicts,
)

RECEIPT_NOW: Final[datetime] = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _source_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or path.as_posix() != relative or ".." in path.parts:
        raise ForwardHarnessError(
            "forward fixture source path must be normalized and relative"
        )
    candidate = root / path
    if candidate.is_symlink() or not candidate.is_file():
        raise ForwardHarnessError(
            f"forward fixture source is not a regular file: {relative}"
        )
    return candidate


def _stored_receipt(
    root: Path,
    relative: str,
    source_manifest: str,
    session_manifest_digest: str,
) -> receipt_contract.StoredReceipt:
    record = receipt_contract.StoredReceipt.model_validate_json(
        _source_path(root, relative).read_text(encoding="utf-8")
    )
    if record.envelope.manifest_digest != source_manifest:
        return record
    envelope = record.envelope.model_copy(
        update={"manifest_digest": session_manifest_digest}
    )
    return receipt_contract.StoredReceipt(
        envelope=envelope,
        receipt_digest=receipt_contract.receipt_digest(envelope),
        trust_level=record.trust_level,
        settlement_credit=record.settlement_credit,
    )


def _apply_input_artifacts(
    session: Path, root: Path, input_value: ForwardInput
) -> None:
    sources = {
        "ledger.json": input_value.ledger_path,
        "protocol.json": input_value.protocol_path,
        "handoff.md": input_value.handoff_path,
        "build-contract.json": input_value.sidecar_path,
    }
    for target, relative in sources.items():
        if relative != f"source/{target}":
            _ = (session / target).write_bytes(
                _source_path(root, relative).read_bytes()
            )


def _receipt_state(
    status: receipt_import.ReceiptStatus,
) -> assurance_schema.ReceiptState:
    return session_status.receipt_state(status)


def _materialized_result(
    root: Path, input_value: ForwardInput
) -> tuple[ForwardVerdicts, ForwardGate]:
    source = root / "source"
    if source.is_symlink() or not source.is_dir():
        raise ForwardHarnessError(
            "forward corpus source session is not a regular directory"
        )
    source_manifest = session_manifest.SessionManifest.model_validate_json(
        _source_path(root, input_value.manifest_path).read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory() as directory:
        session = Path(directory) / input_value.session_id
        _ = shutil.copytree(source, session)
        if input_value.mutation_phase == "before-seal":
            _apply_input_artifacts(session, root, input_value)
        baseline = session_manifest.seal_session(session)
        receipts = session / "receipts"
        shutil.rmtree(receipts, ignore_errors=True)
        _ = receipts.mkdir()
        for index, relative in enumerate(input_value.receipt_paths):
            record = _stored_receipt(
                root,
                relative,
                source_manifest.manifest_digest,
                baseline.manifest_digest,
            )
            _ = (receipts / f"{index}.json").write_text(
                json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        if input_value.mutation_phase == "after-seal":
            _apply_input_artifacts(session, root, input_value)
        raw_ledger = (session / "ledger.json").read_text(encoding="utf-8")
        handoff = (session / "handoff.md").read_text(encoding="utf-8")
        state = protocol_state.parse_state(
            (session / "protocol.json").read_text(encoding="utf-8")
        )
        persisted = state.assurance_result
        if persisted is None:
            raise ForwardHarnessError(
                "forward fixture protocol requires assurance_result"
            )
        manifest = session_manifest.manifest_status(session)
        receipts_status = receipt_import.receipt_status(session, now=RECEIPT_NOW)
        try:
            sidecar = build_contract_schema.BuildContract.model_validate_json(
                (session / "build-contract.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise ForwardHarnessError(
                "forward fixture BuildContract sidecar is invalid"
            ) from error
        entries = ambiguity_ledger.parse_entries(raw_ledger)
        gate = implementation_gate.evaluate(
            entries,
            ambiguity_ledger.summarize_ambiguity(
                entries, evidence_schema_version=state.evidence_schema_version
            ),
            protocol_state.summarize_protocol(state),
            handoff,
            protocol=state,
            contract_sidecar=sidecar,
            raw_ledger_text=raw_ledger,
            snapshot_complete=manifest.snapshot_complete,
            execution_receipts_current=receipts_status.current,
            execution_receipts_creditable=receipts_status.creditable,
            require_manifest=True,
            require_execution_receipts=True,
        )
        if (
            not manifest.snapshot_complete
            or receipts_status.reason == "no imported receipts"
        ):
            assurance = session_status.runtime_assurance_result(
                persisted, manifest, receipts_status, entries, handoff
            )
        else:
            requirements_covered, atoms_covered = handoff_coverage.v2_trace_coverage(
                entries, handoff
            )
            assurance = assurance_schema.derive_assurance_result(
                assurance_schema.AssuranceInputs(
                    manifest=assurance_schema.ArtifactState.VALID,
                    sidecar=assurance_schema.ArtifactState.VALID,
                    requirements_covered=requirements_covered,
                    atoms_covered=atoms_covered,
                    receipt=_receipt_state(receipts_status),
                    adequacy=persisted.adequacy,
                    stakeholder=persisted.stakeholder,
                )
            )
    return (
        ForwardVerdicts(
            abi=assurance.abi,
            trace=assurance.trace,
            property=assurance.property,
            adequacy=assurance.adequacy,
            stakeholder=assurance.stakeholder,
        ),
        ForwardGate(
            implementation_ready=gate.implementation_ready, failures=gate.failures
        ),
    )


def computed_result(
    root: Path, input_value: ForwardInput, corpus_digest: str
) -> ForwardResult:
    verdicts, gate = _materialized_result(root, input_value)
    return ForwardResult(corpus_digest=corpus_digest, verdicts=verdicts, gate=gate)
