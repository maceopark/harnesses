from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE_CLI = Path(__file__).resolve().with_name("cli.py")


class BookmarkCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        shutil.copy2(SOURCE_CLI, self.root / "cli.py")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @property
    def store(self) -> Path:
        return self.root / "bookmarks.json"

    def write_store(self, value: object) -> bytes:
        content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        self.store.write_bytes(content)
        return content

    def run_cli(self, *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        result = subprocess.run(
            [sys.executable, str(self.root / "cli.py"), *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        return result, json.loads(lines[0])

    def test_adds_tag_without_changing_existing_values(self) -> None:
        self.write_store(
            [
                {
                    "id": "b1",
                    "url": "https://example.test/a",
                    "title": "Example",
                    "extra": 7,
                },
                {
                    "id": "b2",
                    "url": "https://example.test/b",
                    "title": "Other",
                    "tags": ["old"],
                },
            ]
        )

        result, observation = self.run_cli("bookmark", "tag", "b1", "새 태그")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            observation,
            {
                "schema": "StarterObservation.v1",
                "status": "completed",
                "exit_code": 0,
                "changed": True,
                "state_digest": hashlib.sha256(self.store.read_bytes()).hexdigest(),
            },
        )
        self.assertEqual(
            json.loads(self.store.read_text()),
            [
                {
                    "id": "b1",
                    "url": "https://example.test/a",
                    "title": "Example",
                    "extra": 7,
                    "tags": ["새 태그"],
                },
                {
                    "id": "b2",
                    "url": "https://example.test/b",
                    "title": "Other",
                    "tags": ["old"],
                },
            ],
        )

    def test_duplicate_tag_is_successful_without_rewrite(self) -> None:
        original = self.write_store(
            [{"id": "b1", "url": "u", "title": "t", "tags": ["saved"]}]
        )

        result, observation = self.run_cli("bookmark", "tag", "b1", "saved")

        self.assertEqual(result.returncode, 0)
        self.assertFalse(observation["changed"])
        self.assertEqual(observation["state_digest"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.store.read_bytes(), original)

    def test_unknown_id_fails_without_mutation(self) -> None:
        original = self.write_store([{"id": "b1", "url": "u", "title": "t"}])

        result, observation = self.run_cli("bookmark", "tag", "missing", "tag")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(observation["status"], "failed")
        self.assertEqual(observation["exit_code"], 1)
        self.assertFalse(observation["changed"])
        self.assertEqual(observation["error"]["code"], "UNKNOWN_BOOKMARK_ID")
        self.assertEqual(observation["state_digest"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.store.read_bytes(), original)

    def test_empty_tag_fails_without_mutation(self) -> None:
        original = self.write_store([{"id": "b1", "url": "u", "title": "t"}])

        result, observation = self.run_cli("bookmark", "tag", "b1", "")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(observation["error"]["code"], "EMPTY_TAG")
        self.assertEqual(observation["state_digest"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.store.read_bytes(), original)

    def test_missing_and_invalid_store_report_null_digest(self) -> None:
        result, observation = self.run_cli("bookmark", "tag", "b1", "tag")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(observation["error"]["code"], "STORE_NOT_FOUND")
        self.assertIsNone(observation["state_digest"])

        self.store.write_text("not-json")
        result, observation = self.run_cli("bookmark", "tag", "b1", "tag")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(observation["error"]["code"], "INVALID_STORE")
        self.assertIsNone(observation["state_digest"])

    def test_invalid_command_reports_existing_digest(self) -> None:
        original = self.write_store([])

        result, observation = self.run_cli("bookmark", "remove", "b1", "tag")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(observation["error"]["code"], "INVALID_COMMAND")
        self.assertEqual(observation["state_digest"], hashlib.sha256(original).hexdigest())


if __name__ == "__main__":
    unittest.main()
