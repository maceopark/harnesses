from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swebench_interview_cases.cache import CacheError, ContentAddressedCache
from swebench_interview_cases.importer import ImportError, import_row


class CacheTests(unittest.TestCase):
    def test_round_trip_is_content_addressed_and_integrity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ContentAddressedCache(directory)
            stored = cache.put_text("hello")
            self.assertEqual(cache.get_text(stored.key, stored.sha256), "hello")
            self.assertNotIn(directory, stored.key)
            path = cache._path_for_digest(stored.sha256)
            path.write_text("corrupt")
            with self.assertRaises(CacheError):
                cache.get_text(stored.key)

    def test_cache_miss_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ContentAddressedCache(directory)
            with self.assertRaises(CacheError):
                cache.get_text("sha256:" + "0" * 64)


class ImporterTests(unittest.TestCase):
    def row(self) -> dict[str, object]:
        return {
            "instance_id": "owner__project-123",
            "repo": "owner/project",
            "base_commit": "0123456789abcdef",
            "problem_statement": "Public issue",
            "patch": "diff --git a/a b/a",
            "test_patch": "diff --git a/t b/t",
            "FAIL_TO_PASS": '["test_fails"]',
            "PASS_TO_PASS": ["test_stays_green"],
        }

    def test_import_keeps_raw_inputs_only_in_cache_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            imported = import_row(
                self.row(), dataset_revision="a" * 40, cache=ContentAddressedCache(directory)
            )
            public = imported.public_source_descriptor()
            self.assertNotIn("Public issue", repr(public))
            self.assertEqual(public["source_url"], "https://github.com/owner/project/pull/123")
            self.assertEqual(set(imported.sealed_inputs()), {"issue", "gold_patch", "test_patch", "fail_to_pass", "pass_to_pass"})

    def test_mutable_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ImportError):
                import_row(self.row(), dataset_revision="main", cache=ContentAddressedCache(directory))

    def test_missing_field_is_rejected(self) -> None:
        row = self.row()
        del row["patch"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ImportError):
                import_row(row, dataset_revision="a" * 40, cache=ContentAddressedCache(directory))


if __name__ == "__main__":
    unittest.main()
