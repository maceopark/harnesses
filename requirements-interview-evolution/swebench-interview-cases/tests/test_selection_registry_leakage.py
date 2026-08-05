from __future__ import annotations

import hashlib
import unittest

from swebench_interview_cases.leakage import (
    audit_public_payload,
    lexical_leakage_findings,
    patch_only_sentinels,
)
from swebench_interview_cases.registry import PartitionRegistry, RegistryEntry, RegistryViolation
from swebench_interview_cases.selection import (
    Candidate,
    SelectionError,
    candidate_order,
    derive_seed,
    holdout_alias,
    holdout_alias_metadata,
    stratified_select,
)


REVISION = hashlib.sha256(b"verified-revision").hexdigest()
CASE_DIGEST = hashlib.sha256(b"case").hexdigest()


def candidates() -> list[Candidate]:
    return [
        Candidate(f"repo{family}__issue-{index}", f"org/repo{family}", "medium", index + 1, index + 2)
        for family in range(8)
        for index in range(3)
    ]


class SelectionTests(unittest.TestCase):
    def test_seed_requires_digest_and_is_stable(self) -> None:
        self.assertEqual(derive_seed(REVISION), derive_seed(f"sha256:{REVISION}"))
        with self.assertRaises(SelectionError):
            derive_seed("latest")

    def test_candidate_and_replacement_order_is_reproducible(self) -> None:
        first = candidate_order(candidates(), REVISION)
        second = candidate_order(reversed(candidates()), REVISION)
        self.assertEqual(first, second)

    def test_selection_fills_fixed_quota_without_crossing_family(self) -> None:
        result = stratified_select(candidates(), REVISION)
        self.assertEqual(15, len(result))
        family_partitions: dict[str, set[str]] = {}
        for item in result:
            family_partitions.setdefault(item.ranked.candidate.repository_family, set()).add(item.partition)
        self.assertTrue(all(len(partitions) == 1 for partitions in family_partitions.values()))

    def test_holdout_alias_is_explicitly_weak_pseudonymization(self) -> None:
        self.assertEqual(hashlib.sha256(b"known-id").hexdigest(), holdout_alias("known-id"))
        metadata = holdout_alias_metadata()
        self.assertFalse(metadata["confidential"])
        self.assertFalse(metadata["enumeration_resistant"])


class RegistryTests(unittest.TestCase):
    def test_family_overlap_fails_closed(self) -> None:
        registry = PartitionRegistry()
        registry.register(RegistryEntry("one", "org/repo", "development", CASE_DIGEST))
        with self.assertRaisesRegex(RegistryViolation, "crosses partitions"):
            registry.register(RegistryEntry("two", "org/repo", "validation", CASE_DIGEST))

    def test_unresolved_family_and_unapproved_case_fail_closed(self) -> None:
        registry = PartitionRegistry()
        with self.assertRaises(RegistryViolation):
            registry.register(RegistryEntry("one", "", "development", CASE_DIGEST))
        with self.assertRaises(RegistryViolation):
            registry.register(RegistryEntry("two", "org/repo", "development", CASE_DIGEST, "pending"))

    def test_manifest_does_not_publish_holdout_id_and_warns_about_alias(self) -> None:
        registry = PartitionRegistry(quotas={"development": 0, "validation": 0, "holdout": 1})
        registry.register(RegistryEntry("secret-id", "org/repo", "holdout", CASE_DIGEST))
        manifest = registry.manifest()
        self.assertNotIn("secret-id", str(manifest))
        self.assertNotIn("org/repo", str(manifest))
        self.assertFalse(manifest["holdout_alias"]["confidential"])


class LeakageTests(unittest.TestCase):
    PATCH = """diff --git a/pkg/base.py b/pkg/base.py
+++ b/pkg/base.py
@@ -1 +1,3 @@
+def gold_only_handler(request):
+    result = internal_cache/patch_only_bucket
+    return publish_exactly_once(result)
"""

    def test_extracts_patch_only_symbols_paths_and_fragments(self) -> None:
        sentinels = patch_only_sentinels(self.PATCH, base_repository_text="request result")
        self.assertIn("gold_only_handler", sentinels["identifier"])
        self.assertIn("internal_cache/patch_only_bucket", sentinels["path"])
        self.assertNotIn("request", sentinels["identifier"])

    def test_detects_nested_payload_and_exact_identifier_boundaries(self) -> None:
        sentinels = {"identifier": {"gold_only_handler"}, "path": set(), "code_fragment": set()}
        findings = audit_public_payload({"contract": ["call gold_only_handler now"]}, sentinels)
        self.assertEqual(1, len(findings))
        self.assertEqual("$.contract[0]", findings[0].location)
        self.assertFalse(lexical_leakage_findings("gold_only_handler_v2", sentinels))


if __name__ == "__main__":
    unittest.main()
