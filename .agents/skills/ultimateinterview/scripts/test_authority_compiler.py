#!/usr/bin/env python3
"""Unit tests for the standalone, fail-closed authority compiler."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from authority_compiler import (
    BUILD_CONTRACT_SCHEMA,
    CompilerError,
    acceptance_binding_digest,
    canonical_json,
    compile_discovery_record,
    contract_digest,
    sha256_canonical_json,
)


SCRIPT = Path(__file__).with_name("authority_compiler.py")


def _source(uri: str) -> dict[str, str]:
    return {"uri": uri, "version": "2026-07-13"}


def _clause(
    text: str,
    decision_class: str,
    authority_refs: list[str],
    *,
    identifier: str | None = None,
    scope: list[str] | None = None,
    constraints: list[str] | None = None,
    preserved_behaviors: list[str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "text": text,
        "decision_class": decision_class,
        "scope": scope or ["todo-cli"],
        "constraints": ["no-network"] if constraints is None else constraints,
        "preserved_behaviors": ["Existing local task data remains local."] if preserved_behaviors is None else preserved_behaviors,
        "authority_refs": authority_refs,
        "evidence_refs": evidence_refs or [],
    }
    if identifier is not None:
        value["id"] = identifier
    return value


def valid_record() -> dict[str, Any]:
    """A fully traced record with owner decisions and a valid internal delegation."""

    owner_decision_classes = ["goal", "scope", "non-goals", "observable-behavior"]
    record: dict[str, Any] = {
        "schema": "ultimateinterview.discovery-record.v1",
        "goal": _clause("Provide a local task CLI.", "goal", ["A-owner"]),
        "scope": [
            _clause("Support create and list commands.", "scope", ["A-owner"], identifier="S-1"),
        ],
        "non_goals": [
            _clause("Do not add network synchronization.", "non-goals", ["A-owner"], identifier="N-1"),
        ],
        "authorities": [
            {
                "id": "A-owner",
                "kind": "owner-decision",
                "status": "active",
                "source": _source("conversation://owner/42"),
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "decision_classes": owner_decision_classes,
                "preserved_behaviors": ["Existing local task data remains local."],
                "statement": "The owner approves a local-only task CLI with create and list behavior.",
                "supersedes": [],
                "conflicts_with": [],
                "owner": "product-owner",
            },
            {
                "id": "A-implementer",
                "kind": "bounded-delegation",
                "status": "active",
                "source": _source("conversation://owner/43"),
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "decision_classes": ["internal-architecture", "test-organization"],
                "preserved_behaviors": ["Existing task command behavior remains local."],
                "statement": "The implementer may choose local module structure and tests only.",
                "supersedes": [],
                "conflicts_with": [],
                "delegate": "builder-17",
                "delegation_boundary": {
                    "kind": "named-component",
                    "includes": ["todo-cli"],
                    "excludes": ["legacy-todo-cli"],
                },
            },
        ],
        "evidence": [
            {
                "id": "E-repo",
                "kind": "repository-evidence",
                "source": _source("repo://README.md"),
                "summary": "The existing command is local-only.",
            },
        ],
        "requirements": [
            _clause(
                "Listing tasks shows every locally created task.",
                "observable-behavior",
                ["A-owner"],
                identifier="R-list",
                evidence_refs=["E-repo"],
            ),
        ],
        "acceptance_predicates": [
            {
                "id": "P-list",
                "requirement_ref": "R-list",
                "precondition": "The local task store is empty.",
                "input": "Create one task named alpha.",
                "action": "Run the list command.",
                "observable_result": "The command shows alpha exactly once.",
                "failure_result": "Invalid create input exits nonzero and stores no task.",
            },
        ],
        "verifications": [
            {
                "id": "V-list",
                "requirement_ref": "R-list",
                "acceptance_refs": ["P-list"],
                "method": "scenario",
                "procedure": "Create alpha in an empty temporary store, then list tasks.",
                "expected_result": "The command shows alpha exactly once.",
            },
        ],
        "trace": [
            {
                "authority_ref": "A-owner",
                "requirement_ref": "R-list",
                "acceptance_ref": "P-list",
                "verification_ref": "V-list",
            },
        ],
        "unresolved_decisions": [],
        "conflicts": [],
    }
    record["requirements"][0]["acceptance_bindings"] = [
        {
            "acceptance_ref": "P-list",
            "digest": acceptance_binding_digest(
                record["requirements"][0],
                record["acceptance_predicates"][0],
            ),
        },
    ]
    return record


class AuthorityCompilerTests(unittest.TestCase):
    def assert_rejected(self, record: dict[str, Any], code: str) -> None:
        with self.assertRaises(CompilerError) as raised:
            compile_discovery_record(record)
        self.assertEqual(raised.exception.code, code)

    def test_compiles_owner_authorized_record_to_sealed_contract(self) -> None:
        record = valid_record()

        contract = compile_discovery_record(record)

        self.assertEqual(contract["schema"], BUILD_CONTRACT_SCHEMA)
        self.assertEqual(contract["source_discovery_digest"], sha256_canonical_json(record))
        self.assertEqual(contract["requirements"][0]["authority_refs"], ["A-owner"])
        self.assertEqual(contract["bounded_implementation_delegations"][0]["delegate"], "builder-17")
        self.assertTrue(contract["bounded_implementation_delegations"][0]["non_transferable"])
        self.assertEqual(
            contract["bounded_implementation_delegations"][0]["delegation_boundary"],
            record["authorities"][1]["delegation_boundary"],
        )
        self.assertEqual(
            contract["requirements"][0]["preserved_behaviors"],
            record["requirements"][0]["preserved_behaviors"],
        )
        self.assertEqual(contract["requirements"][0]["acceptance_bindings"], record["requirements"][0]["acceptance_bindings"])
        self.assertEqual(contract["unresolved_decisions"], [])
        self.assertEqual(contract["contract_digest"], contract_digest(contract))
        self.assertTrue(canonical_json(contract).endswith("\n"))

    def test_missing_authority_fails_closed(self) -> None:
        record = valid_record()
        record["requirements"][0]["authority_refs"] = []

        self.assert_rejected(record, "MISSING_AUTHORITY")

    def test_evidence_cannot_be_used_as_authority(self) -> None:
        record = valid_record()
        record["requirements"][0]["authority_refs"] = ["E-repo"]

        self.assert_rejected(record, "EVIDENCE_IS_NOT_AUTHORITY")

    def test_unresolved_owner_question_blocks_compilation(self) -> None:
        record = valid_record()
        record["unresolved_decisions"] = [
            {"id": "Q-retention", "question": "How long are tasks retained?", "owner": "product-owner"},
        ]

        self.assert_rejected(record, "UNRESOLVED_DECISION")

    def test_unresolved_authority_conflict_blocks_compilation(self) -> None:
        record = valid_record()
        record["conflicts"] = [
            {
                "id": "C-1",
                "authority_refs": ["A-owner", "A-implementer"],
                "status": "unresolved",
            },
        ]

        self.assert_rejected(record, "UNRESOLVED_CONFLICT")

    def test_delegation_scope_requires_an_explicit_named_component_boundary(self) -> None:
        record = valid_record()
        record["authorities"][1]["scope"] = ["repo"]
        record["authorities"][1]["delegation_boundary"] = {
            "kind": "repository-paths",
            "includes": ["src/task_cli"],
            "excludes": ["tests"],
        }

        self.assert_rejected(record, "INVALID_DELEGATION")

        record["authorities"][1]["delegation_boundary"] = {
            "kind": "named-component",
            "includes": ["repo"],
            "excludes": ["legacy-repo"],
        }
        compile_discovery_record(record)

    def test_repository_delegation_boundary_rejects_unsafe_or_unbounded_paths(self) -> None:
        invalid_boundaries = (
            {"kind": "repository-paths", "includes": ["src/*"], "excludes": ["tests"]},
            {"kind": "repository-paths", "includes": ["../src"], "excludes": ["tests"]},
            {"kind": "repository-paths", "includes": ["/src"], "excludes": ["tests"]},
            {"kind": "repository-paths", "includes": ["src/task_cli"], "excludes": []},
        )
        for boundary in invalid_boundaries:
            with self.subTest(boundary=boundary):
                record = valid_record()
                record["authorities"][1]["scope"] = ["src/task_cli"]
                record["authorities"][1]["delegation_boundary"] = boundary
                self.assert_rejected(record, "INVALID_DELEGATION")

        record = valid_record()
        record["authorities"][1]["scope"] = ["src/task_cli"]
        record["authorities"][1]["delegation_boundary"] = {
            "kind": "repository-paths",
            "includes": ["src/task_cli"],
            "excludes": ["src/legacy"],
        }
        compile_discovery_record(record)

    def test_clause_must_preserve_every_authority_behavior(self) -> None:
        record = valid_record()
        record["requirements"][0]["preserved_behaviors"] = ["Unapproved replacement behavior."]

        self.assert_rejected(record, "AUTHORITY_SCOPE_MISMATCH")

    def test_owner_only_product_decision_cannot_be_delegated(self) -> None:
        record = valid_record()
        requirement = record["requirements"][0]
        requirement["authority_refs"] = ["A-implementer"]

        self.assert_rejected(record, "OWNER_DECISION_REQUIRED")

    def test_scope_mismatched_delegation_is_rejected(self) -> None:
        record = valid_record()
        requirement = record["requirements"][0]
        requirement["decision_class"] = "internal-architecture"
        requirement["authority_refs"] = ["A-implementer"]
        requirement["scope"] = ["other-cli"]

        self.assert_rejected(record, "AUTHORITY_SCOPE_MISMATCH")
    def test_acceptance_binding_digest_mismatch_is_rejected(self) -> None:
        record = valid_record()
        record["requirements"][0]["acceptance_bindings"][0]["digest"] = "0" * 64

        self.assert_rejected(record, "ACCEPTANCE_DIGEST_MISMATCH")

    def test_acceptance_binding_stales_when_requirement_core_changes(self) -> None:
        record = valid_record()
        record["requirements"][0]["text"] = "Listing tasks silently deletes alpha."
        self.assert_rejected(record, "ACCEPTANCE_DIGEST_MISMATCH")

        record = valid_record()
        record["authorities"][0]["scope"].append("todo-admin")
        record["requirements"][0]["scope"] = ["todo-admin"]
        self.assert_rejected(record, "ACCEPTANCE_DIGEST_MISMATCH")

        record = valid_record()
        replacement = copy.deepcopy(record["authorities"][0])
        replacement["id"] = "A-owner-replacement"
        replacement["source"] = _source("conversation://owner/44")
        record["authorities"].append(replacement)
        record["requirements"][0]["authority_refs"] = ["A-owner-replacement"]
        self.assert_rejected(record, "ACCEPTANCE_DIGEST_MISMATCH")

    def test_verification_expected_result_must_be_authorized(self) -> None:
        record = valid_record()
        record["verifications"][0]["expected_result"] = "The command deletes alpha."

        self.assert_rejected(record, "UNAUTHORIZED_EXPECTED_RESULT")

    def test_canonical_applicability_and_precedence_are_enforced(self) -> None:
        applicability_mismatch = valid_record()
        canonical = {
            "id": "A-canonical",
            "kind": "canonical-contract",
            "status": "active",
            "source": _source("contract://todo-cli/v1"),
            "scope": ["todo-cli", "other-cli"],
            "constraints": ["no-network"],
            "preserved_behaviors": ["Existing local task data remains local."],
            "decision_classes": ["observable-behavior"],
            "statement": "The contract specifies local task listing behavior.",
            "supersedes": [],
            "conflicts_with": [],
            "canonical_artifact": "todo-cli-contract-v1",
            "applicability": ["todo-cli"],
            "precedence": 1,
        }
        applicability_mismatch["authorities"].append(canonical)
        applicability_mismatch["requirements"][0]["authority_refs"] = ["A-canonical"]
        applicability_mismatch["requirements"][0]["scope"] = ["other-cli"]
        self.assert_rejected(applicability_mismatch, "AUTHORITY_SCOPE_MISMATCH")

        ambiguous_precedence = valid_record()
        first = copy.deepcopy(canonical)
        first["id"] = "A-canonical-one"
        first["scope"] = ["todo-cli"]
        second = copy.deepcopy(first)
        second["id"] = "A-canonical-two"
        second["canonical_artifact"] = "todo-cli-contract-v2"
        ambiguous_precedence["authorities"].extend([first, second])
        self.assert_rejected(ambiguous_precedence, "AMBIGUOUS_PRECEDENCE")


    def test_incomplete_acceptance_fails_closed(self) -> None:
        record = valid_record()
        del record["acceptance_predicates"][0]["failure_result"]

        self.assert_rejected(record, "ACCEPTANCE_INCOMPLETE")

    def test_missing_requirement_to_verification_trace_fails_closed(self) -> None:
        record = valid_record()
        record["trace"] = []

        self.assert_rejected(record, "TRACE_INCOMPLETE")

    def test_missing_verification_makes_requirement_unverifiable(self) -> None:
        record = valid_record()
        record["verifications"] = []
        record["trace"] = []

        self.assert_rejected(record, "UNVERIFIABLE_REQUIREMENT")

    def test_digest_is_deterministic_and_detects_tampering(self) -> None:
        first = compile_discovery_record(valid_record())
        second = compile_discovery_record(copy.deepcopy(valid_record()))
        tampered = copy.deepcopy(first)
        tampered["goal"]["text"] = "Provide a remote task CLI."

        self.assertEqual(first, second)
        self.assertEqual(first["contract_digest"], contract_digest(first))
        self.assertNotEqual(first["contract_digest"], contract_digest(tampered))
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}\n')

    def test_unknown_field_is_rejected(self) -> None:
        record = valid_record()
        record["requirements"][0]["reviewer_consensus"] = "looks good"

        self.assert_rejected(record, "UNKNOWN_FIELD")

    def test_duplicate_ids_and_unknown_references_are_rejected(self) -> None:
        duplicate = valid_record()
        duplicate["scope"][0]["id"] = "R-list"
        self.assert_rejected(duplicate, "DUPLICATE_ID")

        unknown_reference = valid_record()
        unknown_reference["requirements"][0]["authority_refs"] = ["A-missing"]
        self.assert_rejected(unknown_reference, "UNKNOWN_REFERENCE")

    def test_unreferenced_superseded_authority_is_retained(self) -> None:
        record = valid_record()
        historical = copy.deepcopy(record["authorities"][0])
        historical["id"] = "A-owner-v0"
        historical["status"] = "superseded"
        historical["statement"] = "The owner previously approved an earlier local task CLI decision."
        record["authorities"][0]["supersedes"] = ["A-owner-v0"]
        record["authorities"].append(historical)

        contract = compile_discovery_record(record)

        retained = next(authority for authority in contract["authorities"] if authority["id"] == "A-owner-v0")
        self.assertEqual(retained["status"], "superseded")
    def test_supersession_cycle_and_status_mismatch_are_rejected(self) -> None:
        status_mismatch = valid_record()
        status_mismatch["authorities"][0]["supersedes"] = ["A-implementer"]
        self.assert_rejected(status_mismatch, "INVALID_SUPERSESSION")

        cycle = valid_record()
        cycle["authorities"][0]["status"] = "superseded"
        cycle["authorities"][0]["supersedes"] = ["A-implementer"]
        cycle["authorities"][1]["status"] = "superseded"
        cycle["authorities"][1]["supersedes"] = ["A-owner"]
        self.assert_rejected(cycle, "SUPERSESSION_CYCLE")

    def test_revoked_delegation_is_omitted_from_active_delegations(self) -> None:
        record = valid_record()
        record["authorities"][1]["status"] = "revoked"

        contract = compile_discovery_record(record)

        self.assertEqual(contract["bounded_implementation_delegations"], [])
        retained = next(authority for authority in contract["authorities"] if authority["id"] == "A-implementer")
        self.assertEqual(retained["status"], "revoked")

    def test_inactive_historical_delegation_is_retained_without_active_checks(self) -> None:
        record = valid_record()
        delegation = record["authorities"][1]
        delegation["status"] = "superseded"
        delegation["scope"] = ["repository"]
        delegation["decision_classes"] = ["goal"]
        delegation["delegation_boundary"] = {
            "kind": "named-component",
            "includes": ["repository"],
            "excludes": ["legacy-repository"],
        }

        contract = compile_discovery_record(record)

        retained = next(authority for authority in contract["authorities"] if authority["id"] == "A-implementer")
        self.assertEqual(retained["status"], "superseded")
        self.assertEqual(contract["bounded_implementation_delegations"], [])

    def test_conflict_winner_and_resolver_are_structurally_validated(self) -> None:
        invalid_winner = valid_record()
        invalid_winner["conflicts"] = [
            {
                "id": "C-invalid-winner",
                "authority_refs": ["A-owner", "A-implementer"],
                "status": "resolved",
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "preserved_behaviors": ["Existing local task data remains local."],
                "decision_class": "internal-architecture",
                "winning_authority_ref": "A-missing",
                "resolution_authority_ref": "A-owner",
            },
        ]
        self.assert_rejected(invalid_winner, "INVALID_CONFLICT_RESOLUTION")

        delegated_resolver = valid_record()
        delegated_resolver["conflicts"] = [
            {
                "id": "C-invalid-resolver",
                "authority_refs": ["A-owner", "A-implementer"],
                "status": "resolved",
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "preserved_behaviors": ["Existing task command behavior remains local."],
                "decision_class": "internal-architecture",
                "winning_authority_ref": "A-implementer",
                "resolution_authority_ref": "A-implementer",
            },
        ]
        self.assert_rejected(delegated_resolver, "OWNER_DECISION_REQUIRED")

    def test_narrow_conflict_resolution_does_not_clear_other_dimensions(self) -> None:
        record = valid_record()
        first = record["authorities"][0]
        first["scope"].append("todo-admin")
        first["conflicts_with"] = ["A-owner-peer"]
        peer = copy.deepcopy(first)
        peer["id"] = "A-owner-peer"
        peer["source"] = _source("conversation://owner/45")
        peer["conflicts_with"] = ["A-owner"]
        record["authorities"].append(peer)
        record["conflicts"] = [
            {
                "id": "C-one-dimension",
                "authority_refs": ["A-owner", "A-owner-peer"],
                "status": "resolved",
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "preserved_behaviors": ["Existing local task data remains local."],
                "decision_class": "observable-behavior",
                "winning_authority_ref": "A-owner",
                "resolution_authority_ref": "A-owner",
            },
        ]

        self.assert_rejected(record, "UNRESOLVED_CONFLICT")

    def test_referenced_revoked_or_superseded_authority_is_rejected(self) -> None:
        for status in ("revoked", "superseded"):
            with self.subTest(status=status):
                record = valid_record()
                record["authorities"][0]["status"] = status

                self.assert_rejected(record, "INACTIVE_AUTHORITY")

    def test_inactive_conflict_resolution_authority_is_rejected(self) -> None:
        record = valid_record()
        historical = copy.deepcopy(record["authorities"][0])
        historical["id"] = "A-owner-v0"
        historical["status"] = "revoked"
        historical["statement"] = "The owner previously approved an earlier local task CLI decision."
        record["authorities"].append(historical)
        record["conflicts"] = [
            {
                "id": "C-resolved",
                "authority_refs": ["A-owner", "A-owner-v0"],
                "status": "resolved",
                "scope": ["todo-cli"],
                "constraints": ["no-network"],
                "preserved_behaviors": ["Existing local task data remains local."],
                "decision_class": "observable-behavior",
                "winning_authority_ref": "A-owner",
                "resolution_authority_ref": "A-owner-v0",
            },
        ]

        self.assert_rejected(record, "INACTIVE_AUTHORITY")

    def test_cli_writes_pretty_contract_with_canonical_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            discovery = root / "discovery.json"
            output = root / "build-contract.json"
            discovery.write_text(json.dumps(valid_record(), indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(discovery), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            written = output.read_text(encoding="utf-8")
            self.assertTrue(written.endswith("\n"))
            self.assertTrue(written.startswith('{\n  "implementation_decision_policy": {\n'))
            self.assertGreater(len(written.splitlines()), 2)
            parsed = json.loads(written)
            self.assertEqual(
                parsed["implementation_decision_policy"]["log_path"],
                ".ultimateinterview/<session>/decision.jsonl",
            )
            self.assertIn("evidence, not authority", parsed["implementation_decision_policy"]["authority_boundary"])
            self.assertEqual(json.loads(written)["contract_digest"], contract_digest(json.loads(written)))

    def test_cli_never_overwrites_output_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            discovery = root / "invalid-discovery.json"
            output = root / "build-contract.json"
            invalid = valid_record()
            invalid["requirements"][0]["authority_refs"] = []
            discovery.write_text(json.dumps(invalid), encoding="utf-8")
            output.write_text("existing contract must survive\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(discovery), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("MISSING_AUTHORITY", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing contract must survive\n")
            output.unlink()
            absent_result = subprocess.run(
                [sys.executable, str(SCRIPT), str(discovery), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(absent_result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
