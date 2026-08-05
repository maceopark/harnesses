from __future__ import annotations

import unittest
from pathlib import Path

from swebench_interview_cases.harness import (
    BASELINE_MARKER_PATCH,
    HarnessError,
    HarnessRun,
    OfficialHarness,
)


def harness_run(*, f2p_success=(), f2p_failure=(), p2p_success=(), p2p_failure=()):
    return HarnessRun(
        kind="test", command=(), exit_code=0, stdout_sha256="a", stderr_sha256="b",
        report_paths=(), report_sha256={},
        tests_status={
            "FAIL_TO_PASS": {"success": tuple(f2p_success), "failure": tuple(f2p_failure)},
            "PASS_TO_PASS": {"success": tuple(p2p_success), "failure": tuple(p2p_failure)},
        },
    )


class HarnessTests(unittest.TestCase):
    def test_baseline_marker_is_nonempty_inert_file_patch(self) -> None:
        self.assertIn("new file mode 100644", BASELINE_MARKER_PATCH)
        self.assertIn(".swebench-baseline-marker", BASELINE_MARKER_PATCH)
        self.assertNotIn("--- a/", BASELINE_MARKER_PATCH)

    def test_command_keeps_only_base_images(self) -> None:
        harness = object.__new__(OfficialHarness)
        harness.dataset_path = Path("/tmp/test.parquet")
        command = harness._command("gold", "django__django-15268", "test-run")
        cache_level = command[command.index("--cache_level") + 1]
        self.assertEqual(cache_level, "base")

    def test_integrity_gate_accepts_required_behavior(self) -> None:
        OfficialHarness._assert_integrity(
            harness_run(f2p_failure=("regression",), p2p_success=("existing",)),
            harness_run(f2p_success=("regression",), p2p_success=("existing",)),
        )

    def test_baseline_gate_rejects_pass_to_pass_failure_before_gold(self) -> None:
        with self.assertRaisesRegex(HarnessError, "baseline-empty"):
            OfficialHarness._assert_baseline_integrity(
                harness_run(f2p_failure=("regression",), p2p_failure=("existing",)),
                ("regression",), ("existing",),
            )

    def test_integrity_gate_rejects_resolved_baseline(self) -> None:
        with self.assertRaisesRegex(HarnessError, "integrity gate"):
            OfficialHarness._assert_integrity(
                harness_run(f2p_success=("regression",), p2p_success=("existing",)),
                harness_run(f2p_success=("regression",), p2p_success=("existing",)),
            )

    def test_integrity_gate_rejects_missing_expected_test(self) -> None:
        with self.assertRaisesRegex(HarnessError, "integrity gate"):
            OfficialHarness._assert_integrity(
                harness_run(f2p_failure=("one",), p2p_success=("existing",)),
                harness_run(f2p_success=("one",), p2p_success=("existing",)),
                ("one", "missing"), ("existing",),
            )


if __name__ == "__main__":
    unittest.main()
