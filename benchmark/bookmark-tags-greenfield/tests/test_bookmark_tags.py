from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE_CLI = Path(__file__).resolve().parents[1] / "cli.py"
EXPECTED_KEYS = {
    "schema",
    "status",
    "exit_code",
    "changed",
    "state_digest",
}
HEX_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)
PYTHON = shutil.which("python") or sys.executable


def canonical_digest(state: object) -> str:
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BookmarkTagScenarios(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = Path(self.temporary_directory.name)
        shutil.copy2(SOURCE_CLI, self.app / "cli.py")

        self.guard = self.app / "network-guard"
        self.guard.mkdir()
        self.marker = self.guard / "attempted"
        (self.guard / "sitecustomize.py").write_text(
            """\
import os
import socket

def blocked(*args, **kwargs):
    with open(os.environ["NETWORK_ATTEMPT_MARKER"], "a", encoding="utf-8") as stream:
        stream.write("attempted\\n")
    raise RuntimeError("network access blocked by bookmark-tag verification")

socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_state(self, state: object, *, compact: bool = False) -> bytes:
        if compact:
            content = json.dumps(
                state,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        else:
            content = (
                json.dumps(state, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
        (self.app / "bookmarks.json").write_bytes(content)
        return content

    def invoke(self, bookmark_id: str, tag: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        environment = os.environ.copy()
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part
            for part in (str(self.guard), existing_pythonpath)
            if part
        )
        environment["NETWORK_ATTEMPT_MARKER"] = str(self.marker)

        result = subprocess.run(
            [PYTHON, "cli.py", "bookmark", "tag", bookmark_id, tag],
            cwd=self.app,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        observed = json.loads(result.stdout)
        self.assertEqual(set(observed), EXPECTED_KEYS)
        self.assertEqual(observed["schema"], "StarterObservation.v1")
        self.assertEqual(observed["exit_code"], result.returncode)
        self.assertIsNotNone(HEX_DIGEST.fullmatch(observed["state_digest"]))
        self.assertFalse(self.marker.exists(), "bookmark command attempted network access")
        return result, observed

    def assert_failed_without_mutation(
        self,
        before: object,
        bookmark_id: str,
        tag: str,
    ) -> None:
        original_bytes = self.write_state(before)

        result, observed = self.invoke(bookmark_id, tag)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            observed,
            {
                "schema": "StarterObservation.v1",
                "status": "failed",
                "exit_code": 1,
                "changed": False,
                "state_digest": canonical_digest(before),
            },
        )
        self.assertEqual((self.app / "bookmarks.json").read_bytes(), original_bytes)

    def test_success_adds_exact_tag_and_preserves_existing_fields(self) -> None:
        before = [
            {
                "id": "one",
                "url": "https://example.test/한글",
                "title": 'First "bookmark"',
                "other": {"kept": True},
            },
            {
                "id": "two",
                "url": "https://example.test/two",
                "title": "Second",
                "tags": ["existing"],
            },
        ]
        self.write_state(before)

        result, observed = self.invoke("one", "  Work Tag  ")

        after = json.loads((self.app / "bookmarks.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            observed,
            {
                "schema": "StarterObservation.v1",
                "status": "completed",
                "exit_code": 0,
                "changed": True,
                "state_digest": canonical_digest(after),
            },
        )
        self.assertEqual(after[0]["tags"], ["  Work Tag  "])
        self.assertEqual(
            [(item["url"], item["title"]) for item in after],
            [(item["url"], item["title"]) for item in before],
        )
        self.assertEqual(after[0]["other"], {"kept": True})
        self.assertEqual(after[1], before[1])

    def test_unknown_id_fails_without_mutation(self) -> None:
        self.assert_failed_without_mutation(
            [{"id": "one", "url": "u", "title": "t"}],
            "missing",
            "tag",
        )

    def test_duplicate_tag_fails_without_mutation(self) -> None:
        self.assert_failed_without_mutation(
            [{"id": "one", "url": "u", "title": "t", "tags": ["same"]}],
            "one",
            "same",
        )

    def test_empty_tag_fails_without_mutation(self) -> None:
        self.assert_failed_without_mutation(
            [{"id": "one", "url": "u", "title": "t"}],
            "one",
            "",
        )

    def test_case_sensitive_tags_retain_insertion_order(self) -> None:
        self.write_state(
            [{"id": "one", "url": "u", "title": "t", "tags": ["Tag"]}]
        )

        for tag in ("tag", " tag", "tag "):
            result, observed = self.invoke("one", tag)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(observed["status"], "completed")
            self.assertTrue(observed["changed"])

        state = json.loads((self.app / "bookmarks.json").read_text(encoding="utf-8"))
        self.assertEqual(state[0]["tags"], ["Tag", "tag", " tag", "tag "])

    def test_failure_digest_uses_canonical_complete_state(self) -> None:
        state = [
            {"title": "한글", "url": "u", "id": "one", "tags": ["same"]},
            {"id": "two", "url": "v", "title": "second"},
        ]
        original_bytes = self.write_state(state, compact=True)

        result, observed = self.invoke("one", "same")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(observed["state_digest"], canonical_digest(state))
        self.assertNotEqual(observed["state_digest"], hashlib.sha256(original_bytes).hexdigest())
        self.assertEqual((self.app / "bookmarks.json").read_bytes(), original_bytes)

    def test_implementation_has_no_network_or_process_launch_surface(self) -> None:
        tree = ast.parse(SOURCE_CLI.read_text(encoding="utf-8"))
        forbidden_imports = {
            "aiohttp",
            "http",
            "httpx",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    calls.add(f"{node.func.value.id}.{node.func.attr}")

        self.assertTrue(imports.isdisjoint(forbidden_imports))
        self.assertTrue(
            calls.isdisjoint(
                {
                    "os.execv",
                    "os.execve",
                    "os.popen",
                    "os.spawnl",
                    "os.spawnle",
                    "os.spawnlp",
                    "os.spawnlpe",
                    "os.spawnv",
                    "os.spawnve",
                    "os.spawnvp",
                    "os.spawnvpe",
                    "os.system",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
