#!/usr/bin/env python3
"""Unit tests for the owner-approved Authority Register reconciliation tool."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from authority_compiler import CompilerError, authority_register_digest, reconcile_authority_register


SCRIPT = Path(__file__).with_name("authority_reconcile.py")


def valid_reconciliation() -> dict[str, Any]:
    authority = {
        "id": "A-owner",
        "kind": "owner-decision",
        "status": "active",
        "source": {"uri": "conversation://owner/42", "version": "2026-07-14"},
        "scope": ["todo-cli"],
        "constraints": ["no-network"],
        "preserved_behaviors": ["Task data remains local."],
        "decision_classes": ["goal", "scope", "non-goals", "observable-behavior"],
        "statement": "The owner approves the local task CLI authority boundary.",
        "supersedes": [],
        "conflicts_with": [],
        "owner": "product-owner",
    }
    return {
        "schema": "ultimateinterview.authority-reconciliation-input.v1",
        "owner_approval": {
            "id": "AR-approval",
            "owner": "product-owner",
            "source": {"uri": "conversation://owner/43", "version": "2026-07-14"},
            "statement": "The owner approves this complete Authority Register.",
            "approval_authority_ref": "A-owner",
            "approved_authority_refs": ["A-owner"],
            "approved_conflict_refs": [],
        },
        "authorities": [authority],
        "conflicts": [],
        "unresolved_decisions": [],
    }


class AuthorityReconcileTests(unittest.TestCase):
    def assert_rejected(self, value: dict[str, Any], code: str) -> None:
        with self.assertRaises(CompilerError) as raised:
            reconcile_authority_register(value)
        self.assertEqual(raised.exception.code, code)

    def test_reconciles_owner_approved_register_deterministically(self) -> None:
        first = reconcile_authority_register(valid_reconciliation())
        second = reconcile_authority_register(copy.deepcopy(valid_reconciliation()))

        self.assertEqual(first, second)
        self.assertEqual(first["authority_register_digest"], authority_register_digest(first))
        self.assertEqual(first["schema"], "ultimateinterview.authority-register.v1")

    def test_rejects_unresolved_conflicting_and_laundered_authority(self) -> None:
        unresolved = valid_reconciliation()
        unresolved["unresolved_decisions"] = [
            {"id": "Q-retention", "question": "Who owns retention?", "owner": "product-owner"}
        ]
        self.assert_rejected(unresolved, "UNRESOLVED_DECISION")

        conflict = valid_reconciliation()
        peer = copy.deepcopy(conflict["authorities"][0])
        peer["id"] = "A-peer"
        peer["source"] = {"uri": "conversation://owner/44", "version": "2026-07-14"}
        peer["conflicts_with"] = ["A-owner"]
        conflict["authorities"][0]["conflicts_with"] = ["A-peer"]
        conflict["authorities"].append(peer)
        conflict["owner_approval"]["approved_authority_refs"].append("A-peer")
        self.assert_rejected(conflict, "UNRESOLVED_CONFLICT")

        laundering = valid_reconciliation()
        laundering["authorities"][0]["id"] = "E-repository"
        laundering["owner_approval"]["approval_authority_ref"] = "E-repository"
        laundering["owner_approval"]["approved_authority_refs"] = ["E-repository"]
        self.assert_rejected(laundering, "EVIDENCE_IS_NOT_AUTHORITY")

    def test_rejects_unbounded_delegation(self) -> None:
        value = valid_reconciliation()
        authority = value["authorities"][0]
        authority.update(
            {
                "kind": "bounded-delegation",
                "decision_classes": ["internal-architecture"],
                "delegate": "builder-17",
                "delegation_boundary": {
                    "kind": "repository-paths",
                    "includes": ["src/*"],
                    "excludes": ["tests"],
                },
            }
        )
        del authority["owner"]
        self.assert_rejected(value, "INVALID_DELEGATION")

    def test_cli_writes_exact_bytes_and_preserves_output_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "reconciliation.json"
            output = root / "authority-register.json"
            source.write_text(json.dumps(valid_reconciliation(), indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            written = output.read_text(encoding="utf-8")
            self.assertEqual(written, json.dumps(json.loads(written), ensure_ascii=False, indent=2) + "\n")

            invalid = valid_reconciliation()
            invalid["unresolved_decisions"] = [
                {"id": "Q-1", "question": "Unresolved?", "owner": "product-owner"}
            ]
            source.write_text(json.dumps(invalid), encoding="utf-8")
            output.write_text("existing register survives\n", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, str(SCRIPT), str(source), "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("UNRESOLVED_DECISION", failed.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing register survives\n")


if __name__ == "__main__":
    unittest.main()
