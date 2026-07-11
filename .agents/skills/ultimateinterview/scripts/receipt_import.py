#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["pydantic>=2.7", "typer>=0.12"]
# ///

from __future__ import annotations

import errno
import json
import os
import secrets
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, ClassVar, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from pydantic import BaseModel, ConfigDict, ValidationError

from scripts import (
    atomic_write,
    build_contract_schema,
    protocol_state,
    receipt_contract,
    session_manifest,
)

TEMPLATE_VERSION = "simulated-current-v1"


class ReceiptImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReceiptImportResult:
    receipt_digest: str
    trust_level: receipt_contract.TrustLevel
    settlement_credit: int


@dataclass(frozen=True, slots=True)
class ReceiptStatus:
    current: bool
    reason: str
    count: int
    execution_kinds: tuple[receipt_contract.ReceiptKind, ...] = ()
    execution_outcomes: tuple[receipt_contract.ReceiptOutcome, ...] = ()
    creditable: bool = False


@dataclass(frozen=True, slots=True)
class ProbeReceiptStatus:
    verified: bool
    reason: str
    receipt_digest: str | None


@dataclass(frozen=True, slots=True)
class SessionBinding:
    session_id: str
    manifest_digest: str
    contract: build_contract_schema.BuildContract
    state: protocol_state.ProtocolState


@dataclass(frozen=True, slots=True)
class _ReceiptsDirectory:
    root_fd: int
    directory_fd: int
    device: int
    inode: int


class StrictTemplate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True, extra="forbid", strict=True
    )


class SimulatedReceiptTemplate(StrictTemplate):
    template_version: Literal["simulated-current-v1"]
    receipt_id: str
    nonce: str
    subject_digest: str
    artifact_digest: str
    stdout_digest: str
    stderr_digest: str
    verification_id: str
    issued_at: str
    expires_at: str
    outcome: receipt_contract.ReceiptOutcome
    impact_weight: Literal[1, 2, 3, 5]


def _session_root(session_dir: Path) -> Path:
    if not session_dir.is_dir() or session_dir.is_symlink():
        raise ReceiptImportError(
            f"session directory is not a regular directory: {session_dir}"
        )
    return session_dir.resolve()


def _binding_locked(root: Path) -> SessionBinding:
    try:
        manifest = session_manifest._manifest_status_locked(root)
    except session_manifest.SessionManifestError as error:
        raise ReceiptImportError(str(error)) from error
    if not manifest.snapshot_complete or manifest.manifest_digest is None:
        raise ReceiptImportError(manifest.reason or "session manifest is not current")
    sidecar = root / "build-contract.json"
    try:
        contract = build_contract_schema.BuildContract.model_validate_json(
            sidecar.read_text(encoding="utf-8"),
        )
        state = protocol_state.parse_state(
            (root / "protocol.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as error:
        raise ReceiptImportError(f"invalid sealed session binding: {error}") from error
    return SessionBinding(root.name, manifest.manifest_digest, contract, state)


def _template_envelope(
    template: SimulatedReceiptTemplate,
    binding: SessionBinding,
) -> receipt_contract.ReceiptEnvelope:
    return receipt_contract.ReceiptEnvelope(
        receipt_id=template.receipt_id,
        kind=receipt_contract.ReceiptKind.VERIFICATION,
        session_id=binding.session_id,
        manifest_digest=binding.manifest_digest,
        contract_digest=binding.contract.contract_digest,
        policy_version=receipt_contract.POLICY_VERSION,
        issuer_id="fixture-simulated",
        key_epoch="fixture-epoch-1",
        issued_at=template.issued_at,
        expires_at=template.expires_at,
        nonce=template.nonce,
        subject_digest=template.subject_digest,
        action_digest=receipt_contract.verification_action_digest(
            binding.contract,
            template.verification_id,
        ),
        claim_digest=None,
        artifact_digest=template.artifact_digest,
        stdout_digest=template.stdout_digest,
        stderr_digest=template.stderr_digest,
        verification_id=template.verification_id,
        probe_id=None,
        observation_spec_digest=None,
        outcome=template.outcome,
        impact_weight=template.impact_weight,
        declared_trust=receipt_contract.TrustLevel.SIMULATED,
    )


def _parse_envelope(
    raw: str, binding: SessionBinding
) -> receipt_contract.ReceiptEnvelope:
    try:
        return receipt_contract.ReceiptEnvelope.model_validate_json(raw)
    except ValidationError as envelope_error:
        try:
            template = SimulatedReceiptTemplate.model_validate_json(raw)
        except ValidationError:
            raise ReceiptImportError(
                f"malformed receipt envelope: {envelope_error}"
            ) from envelope_error
        try:
            return _template_envelope(template, binding)
        except receipt_contract.ReceiptContractError as error:
            raise ReceiptImportError(str(error)) from error


def _validate_binding(
    envelope: receipt_contract.ReceiptEnvelope,
    binding: SessionBinding,
    now: datetime,
) -> None:
    if envelope.session_id != binding.session_id:
        raise ReceiptImportError("receipt session_id does not match the session")
    if envelope.manifest_digest != binding.manifest_digest:
        raise ReceiptImportError(
            "receipt manifest_digest does not match the sealed session"
        )
    if envelope.contract_digest != binding.contract.contract_digest:
        raise ReceiptImportError("receipt contract_digest does not match BuildContract")
    issued = receipt_contract.parse_timestamp(envelope.issued_at)
    expires = receipt_contract.parse_timestamp(envelope.expires_at)
    if issued > now:
        raise ReceiptImportError("receipt issued_at is in the future")
    if expires <= now:
        raise ReceiptImportError("receipt is expired")
    match envelope.kind:
        case receipt_contract.ReceiptKind.VERIFICATION:
            assert envelope.verification_id is not None
            expected = receipt_contract.verification_action_digest(
                binding.contract,
                envelope.verification_id,
            )
            if envelope.action_digest != expected:
                raise ReceiptImportError(
                    "receipt action_digest does not match verification"
                )
        case receipt_contract.ReceiptKind.PROBE:
            decision = binding.state.probe_decision
            if decision is None or envelope.probe_id != decision.probe_id:
                raise ReceiptImportError(
                    "receipt probe_id does not match the persisted ProbeDecision"
                )
            expected = receipt_contract.observation_spec_digest(decision)
            if envelope.observation_spec_digest != expected:
                raise ReceiptImportError(
                    "receipt observation_spec_digest does not match ProbeDecision"
                )
        case (
            receipt_contract.ReceiptKind.EVIDENCE
            | receipt_contract.ReceiptKind.AUTHORITY
        ):
            return


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _open_receipts_directory(
    root: Path,
    *,
    create: bool,
) -> Iterator[_ReceiptsDirectory | None]:
    flags = _directory_open_flags()
    try:
        root_fd = os.open(root, flags)
    except OSError as error:
        raise ReceiptImportError(f"cannot open session root safely: {error}") from error
    directory_fd: int | None = None
    try:
        for _ in range(3):
            try:
                directory_fd = os.open("receipts", flags, dir_fd=root_fd)
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                try:
                    os.mkdir("receipts", 0o700, dir_fd=root_fd)
                except FileExistsError:
                    continue
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise ReceiptImportError(
                        "receipts directory must be a regular directory",
                    ) from None
                raise ReceiptImportError(
                    f"cannot open receipts directory safely: {error}",
                ) from error
            else:
                identity = os.fstat(directory_fd)
                if not stat.S_ISDIR(identity.st_mode):
                    raise ReceiptImportError("receipts path is not a directory")
                yield _ReceiptsDirectory(
                    root_fd,
                    directory_fd,
                    identity.st_dev,
                    identity.st_ino,
                )
                return
        raise ReceiptImportError("receipts directory changed during import")
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(root_fd)


def _assert_receipts_directory_current(directory: _ReceiptsDirectory) -> None:
    try:
        current = os.stat(
            "receipts",
            dir_fd=directory.root_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        raise ReceiptImportError("receipts directory changed during import") from None
    if (
        not stat.S_ISDIR(current.st_mode)
        or current.st_dev != directory.device
        or current.st_ino != directory.inode
    ):
        raise ReceiptImportError("receipts directory changed during import")


def _stage_receipt(directory: _ReceiptsDirectory, content: str) -> str:
    for _ in range(3):
        name = f".receipt-import-{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory.root_fd,
            )
        except FileExistsError:
            continue
        except OSError as error:
            raise ReceiptImportError(f"cannot stage receipt safely: {error}") from error
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            try:
                os.unlink(name, dir_fd=directory.root_fd)
            except FileNotFoundError:
                pass
            raise ReceiptImportError(f"cannot stage receipt safely: {error}") from error
        return name
    raise ReceiptImportError("cannot allocate a receipt staging file")


def _publish_receipt(
    directory: _ReceiptsDirectory,
    digest: str,
    content: str,
) -> None:
    _assert_receipts_directory_current(directory)
    staged_name = _stage_receipt(directory, content)
    target_name = f"{digest}.json"
    try:
        _assert_receipts_directory_current(directory)
        try:
            os.link(
                staged_name,
                target_name,
                src_dir_fd=directory.root_fd,
                dst_dir_fd=directory.directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            raise ReceiptImportError(
                "receipt digest already exists and will not be rewritten",
            ) from None
        except OSError as error:
            raise ReceiptImportError(f"cannot publish receipt safely: {error}") from error
        os.fsync(directory.directory_fd)
        os.fsync(directory.root_fd)
    finally:
        try:
            os.unlink(staged_name, dir_fd=directory.root_fd)
        except FileNotFoundError:
            pass


def _stored_receipts(
    directory: _ReceiptsDirectory,
) -> tuple[receipt_contract.StoredReceipt, ...]:
    records: list[receipt_contract.StoredReceipt] = []
    descriptor = os.dup(directory.directory_fd)
    try:
        scanner = os.scandir(descriptor)
    except OSError as error:
        os.close(descriptor)
        raise ReceiptImportError(f"cannot scan receipts directory safely: {error}") from error
    with scanner:
        for member in sorted(scanner, key=lambda entry: entry.name):
            if (
                member.is_symlink()
                or not member.is_file(follow_symlinks=False)
                or Path(member.name).suffix != ".json"
            ):
                raise ReceiptImportError("receipts directory contains an unsafe member")
            try:
                member_fd = os.open(
                    member.name,
                    os.O_RDONLY | os.O_NOFOLLOW,
                    dir_fd=directory.directory_fd,
                )
                with os.fdopen(member_fd, "r", encoding="utf-8") as handle:
                    records.append(
                        receipt_contract.StoredReceipt.model_validate_json(handle.read())
                    )
            except (OSError, ValidationError, ValueError) as error:
                raise ReceiptImportError(f"invalid stored receipt: {error}") from error
    return tuple(records)


def _stored_json(record: receipt_contract.StoredReceipt) -> str:
    return (
        json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )


def import_receipt(
    session_dir: Path,
    raw_envelope: str,
    *,
    now: datetime,
    registry: receipt_contract.TrustRegistry | None = None,
) -> ReceiptImportResult:
    root = _session_root(session_dir)
    with atomic_write.session_transaction(root):
        binding = _binding_locked(root)
        envelope = _parse_envelope(raw_envelope, binding)
        _validate_binding(envelope, binding, now)
        try:
            resolved_registry = (
                registry
                if registry is not None
                else receipt_contract.ProviderFreeRegistry()
            )
            trust_level = receipt_contract.resolve_trust(envelope, resolved_registry)
        except receipt_contract.ReceiptContractError as error:
            raise ReceiptImportError(str(error)) from error
        credit = receipt_contract.settlement_credit(trust_level, envelope.impact_weight)
        digest = receipt_contract.receipt_digest(envelope)
        stored = receipt_contract.StoredReceipt(
            envelope=envelope,
            receipt_digest=digest,
            trust_level=trust_level,
            settlement_credit=credit,
        )
        with _open_receipts_directory(root, create=True) as directory:
            if directory is None:
                raise ReceiptImportError("receipts directory is unavailable")
            existing = _stored_receipts(directory)
            if any(record.envelope.nonce == envelope.nonce for record in existing):
                raise ReceiptImportError("replayed nonce")
            _publish_receipt(directory, digest, _stored_json(stored))
    return ReceiptImportResult(digest, trust_level, credit)


def _receipt_status_locked(
    root: Path,
    *,
    now: datetime,
    registry: receipt_contract.TrustRegistry | None = None,
) -> ReceiptStatus:
    try:
        binding = _binding_locked(root)
        with _open_receipts_directory(root, create=False) as directory:
            records = () if directory is None else _stored_receipts(directory)
        if not records:
            return ReceiptStatus(False, "no imported receipts", 0)
        nonces = tuple(record.envelope.nonce for record in records)
        if len(nonces) != len(set(nonces)):
            raise ReceiptImportError("replayed nonce in stored receipts")
        for record in records:
            _validate_binding(record.envelope, binding, now)
            try:
                resolved_registry = (
                    registry
                    if registry is not None
                    else receipt_contract.ProviderFreeRegistry()
                )
                _ = receipt_contract.resolve_trust(record.envelope, resolved_registry)
            except receipt_contract.ReceiptContractError as error:
                raise ReceiptImportError(str(error)) from error
        execution_records = tuple(
            record
            for record in records
            if record.envelope.kind
            in (
                receipt_contract.ReceiptKind.VERIFICATION,
                receipt_contract.ReceiptKind.PROBE,
            )
        )
        if not execution_records:
            return ReceiptStatus(False, "no imported execution receipts", len(records))
        creditable_records = tuple(
            record for record in execution_records if record.settlement_credit > 0
        )
        return ReceiptStatus(
            True,
            "current",
            len(records),
            tuple(record.envelope.kind for record in execution_records),
            tuple(record.envelope.outcome for record in creditable_records),
            bool(creditable_records),
        )
    except ReceiptImportError as error:
        return ReceiptStatus(False, str(error), 0)


def receipt_status(
    session_dir: Path,
    *,
    now: datetime,
    registry: receipt_contract.TrustRegistry | None = None,
) -> ReceiptStatus:
    try:
        root = _session_root(session_dir)
        with atomic_write.session_read_transaction(root):
            return _receipt_status_locked(root, now=now, registry=registry)
    except (ReceiptImportError, atomic_write.SessionLockError) as error:
        return ReceiptStatus(False, str(error), 0)


def _probe_receipt_status_locked(
    root: Path,
    *,
    now: datetime,
    registry: receipt_contract.TrustRegistry | None = None,
) -> ProbeReceiptStatus:
    try:
        binding = _binding_locked(root)
        decision = binding.state.probe_decision
        if decision is None:
            return ProbeReceiptStatus(False, "no persisted probe decision", None)
        if decision.contract_digest != binding.contract.contract_digest:
            raise ReceiptImportError(
                "persisted ProbeDecision contract_digest does not match BuildContract"
            )
        with _open_receipts_directory(root, create=False) as directory:
            records = () if directory is None else _stored_receipts(directory)
        nonces = tuple(record.envelope.nonce for record in records)
        if len(nonces) != len(set(nonces)):
            raise ReceiptImportError("replayed nonce in stored receipts")
        matching = tuple(
            record
            for record in records
            if (
                record.envelope.kind is receipt_contract.ReceiptKind.PROBE
                and record.envelope.probe_id == decision.probe_id
            )
        )
        if not matching:
            return ProbeReceiptStatus(
                False, "no imported receipt for persisted probe decision", None
            )
        if len(matching) != 1:
            raise ReceiptImportError(
                "multiple receipts match the persisted probe decision"
            )
        record = matching[0]
        envelope = record.envelope
        if envelope.policy_version != receipt_contract.POLICY_VERSION:
            raise ReceiptImportError(
                "receipt policy_version does not match the current policy"
            )
        if envelope.contract_digest != decision.contract_digest:
            raise ReceiptImportError(
                "receipt contract_digest does not match the persisted ProbeDecision"
            )
        expected_spec = receipt_contract.observation_spec_digest(decision)
        if (
            envelope.observation_spec_digest != expected_spec
            or envelope.action_digest != expected_spec
        ):
            raise ReceiptImportError(
                "receipt observation_spec_digest does not match the persisted ProbeDecision"
            )
        _validate_binding(envelope, binding, now)
        try:
            resolved_registry = (
                registry
                if registry is not None
                else receipt_contract.ProviderFreeRegistry()
            )
            _ = receipt_contract.resolve_trust(envelope, resolved_registry)
        except receipt_contract.ReceiptContractError as error:
            raise ReceiptImportError(str(error)) from error
        return ProbeReceiptStatus(True, "current", record.receipt_digest)
    except ReceiptImportError as error:
        return ProbeReceiptStatus(False, str(error), None)


def probe_receipt_status(
    session_dir: Path,
    *,
    now: datetime,
    registry: receipt_contract.TrustRegistry | None = None,
) -> ProbeReceiptStatus:
    try:
        root = _session_root(session_dir)
        with atomic_write.session_read_transaction(root):
            return _probe_receipt_status_locked(root, now=now, registry=registry)
    except (ReceiptImportError, atomic_write.SessionLockError) as error:
        return ProbeReceiptStatus(False, str(error), None)


def main(
    session_dir: Annotated[
        Path, typer.Argument(help="Sealed schema-v2 session directory.")
    ],
) -> None:
    try:
        imported = import_receipt(
            session_dir,
            sys.stdin.read(),
            now=datetime.now(UTC),
        )
    except ReceiptImportError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "receipt_digest": imported.receipt_digest,
                "trust_level": imported.trust_level.value,
                "settlement_credit": imported.settlement_credit,
            },
            indent=2,
            sort_keys=True,
        ),
    )


if __name__ == "__main__":
    typer.run(main)
