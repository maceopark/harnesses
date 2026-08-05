"""Official SWE-bench harness execution with immutable inputs and evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import HARNESS_REVISION
from .selection import holdout_alias


BASELINE_MARKER_PATCH = """diff --git a/.swebench-baseline-marker b/.swebench-baseline-marker
new file mode 100644
index 0000000..180cf83
--- /dev/null
+++ b/.swebench-baseline-marker
@@ -0,0 +1 @@
+baseline
"""


class HarnessError(RuntimeError):
    """Raised when an instance cannot supply valid official-harness evidence."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None,
         timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    return completed


def docker_fingerprint(work_dir: Path) -> dict[str, Any]:
    version = _run(["docker", "version", "--format", "{{json .}}"], cwd=work_dir)
    info = _run(["docker", "info", "--format", "{{json .}}"], cwd=work_dir)
    if version.returncode != 0 or info.returncode != 0:
        raise HarnessError(f"Docker unavailable: {(version.stderr + info.stderr)[-2000:]}")
    return {
        "platform": "linux/amd64",
        "docker_default_platform": "linux/amd64",
        "version_sha256": hashlib.sha256(version.stdout.encode()).hexdigest(),
        "info_sha256": hashlib.sha256(info.stdout.encode()).hexdigest(),
        "version": json.loads(version.stdout),
        "info": json.loads(info.stdout),
    }


@dataclass(frozen=True)
class HarnessRun:
    kind: str
    command: tuple[str, ...]
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    report_paths: tuple[str, ...]
    report_sha256: dict[str, str]
    tests_status: dict[str, dict[str, tuple[str, ...]]]
    image_digests: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "report_paths": list(self.report_paths),
            "report_sha256": self.report_sha256,
            "tests_status": self.tests_status,
            "image_digests": list(self.image_digests),
        }


class OfficialHarness:
    """Runs baseline-empty and gold evaluation through the pinned SWE-bench package."""

    def __init__(self, project_root: Path, dataset_path: Path, output_root: Path,
                 harness_source: Path,
                 timeout_seconds: int = 7200) -> None:
        self.project_root = project_root.resolve()
        self.dataset_path = dataset_path.resolve()
        self.output_root = output_root.resolve()
        self.harness_source = harness_source.resolve()
        self.timeout_seconds = timeout_seconds
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        revision = _run(["git", "rev-parse", "HEAD"], cwd=self.harness_source)
        if revision.returncode != 0 or revision.stdout.strip() != HARNESS_REVISION:
            raise HarnessError("official harness source is not at the pinned revision")
        if not (self.harness_source / "swebench" / "harness").is_dir():
            raise HarnessError("official harness source checkout is incomplete")

    def _command(self, predictions: str, instance_id: str, run_id: str) -> list[str]:
        return [
            sys.executable, "-m", "swebench.harness.run_evaluation",
            "--dataset_name", str(self.dataset_path),
            "--predictions_path", predictions,
            "--max_workers", "1",
            "--instance_ids", instance_id,
            "--run_id", run_id,
            "--namespace", "none",
            # Keep only the shared base image. The official harness removes the
            # per-run environment and instance images after each invocation.
            "--cache_level", "base",
        ]

    def _capture(
        self, kind: str, command: list[str], run_dir: Path, *, run_id: str,
        model_name: str, instance_id: str,
    ) -> HarnessRun:
        env = os.environ.copy()
        env["DOCKER_DEFAULT_PLATFORM"] = "linux/amd64"
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(self.harness_source)
            if not existing_pythonpath
            else f"{self.harness_source}{os.pathsep}{existing_pythonpath}"
        )
        event_start = int(time.time()) - 1
        completed = _run(
            command, cwd=self.project_root, env=env, timeout=self.timeout_seconds
        )
        event_end = int(time.time()) + 1
        (run_dir / f"{kind}.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (run_dir / f"{kind}.stderr.log").write_text(completed.stderr, encoding="utf-8")
        (run_dir / f"{kind}.process.json").write_text(json.dumps({
            "kind": kind, "command": command, "exit_code": completed.returncode,
            "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
        }, indent=2) + "\n", encoding="utf-8")
        report_path = (
            self.project_root / "logs" / "run_evaluation" / run_id
            / model_name.replace("/", "__") / instance_id / "report.json"
        )
        if completed.returncode != 0:
            raise HarnessError(
                f"{kind} harness run failed with {completed.returncode}: {completed.stderr[-2000:]}"
            )
        if not report_path.is_file():
            raise HarnessError(f"{kind} harness produced no report: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        try:
            raw_status = report[instance_id]["tests_status"]
            tests_status = {
                category: {
                    disposition: tuple(values)
                    for disposition, values in raw_status[category].items()
                }
                for category in ("FAIL_TO_PASS", "PASS_TO_PASS")
            }
        except (KeyError, TypeError, AttributeError) as exc:
            raise HarnessError(f"{kind} report has no usable per-test status") from exc
        reports = [report_path]
        events = _run(
            ["docker", "events", "--since", str(event_start), "--until", str(event_end),
             "--filter", "type=image", "--format", "{{json .}}"], cwd=self.project_root,
        )
        expected_image = f"sweb.eval.x86_64.{instance_id.lower()}:latest"
        image_digests: set[str] = set()
        inspected = _run(
            ["docker", "image", "inspect", expected_image, "--format", "{{.Id}}"],
            cwd=self.project_root,
        )
        inspected_id = inspected.stdout.strip()
        if inspected.returncode == 0 and inspected_id.startswith("sha256:") and len(inspected_id) == 71:
            image_digests.add(inspected_id)
        if events.returncode == 0:
            for line in events.stdout.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                attributes = event.get("Actor", {}).get("Attributes", {})
                names = {attributes.get("name"), attributes.get("image"), attributes.get("ref")}
                if expected_image in names:
                    image_id = str(event.get("Actor", {}).get("ID", ""))
                    if image_id.startswith("sha256:") and len(image_id) == 71:
                        image_digests.add(image_id)
        if not image_digests:
            raise HarnessError(f"{kind} run has no immutable Docker image digest evidence")
        evidence = HarnessRun(
            kind=kind,
            command=tuple(command),
            exit_code=completed.returncode,
            stdout_sha256=hashlib.sha256(completed.stdout.encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(completed.stderr.encode()).hexdigest(),
            report_paths=tuple(str(path.relative_to(self.project_root)) for path in reports),
            report_sha256={
                str(path.relative_to(self.project_root)): sha256_file(path) for path in reports
            },
            tests_status=tests_status,
            image_digests=tuple(sorted(image_digests)),
        )
        return evidence

    @staticmethod
    def _assert_baseline_integrity(
        baseline: HarnessRun,
        expected_f2p: tuple[str, ...],
        expected_p2p: tuple[str, ...],
    ) -> None:
        baseline_f2p = baseline.tests_status["FAIL_TO_PASS"]
        baseline_p2p = baseline.tests_status["PASS_TO_PASS"]
        valid = (
            set(baseline_f2p["failure"]) == set(expected_f2p)
            and not baseline_f2p["success"]
            and set(baseline_p2p["success"]) == set(expected_p2p)
            and not baseline_p2p["failure"]
        )
        if not valid:
            raise HarnessError("instance failed baseline-empty F2P/P2P integrity gate")

    @staticmethod
    def _assert_integrity(
        baseline: HarnessRun, gold: HarnessRun,
        expected_f2p: tuple[str, ...] | None = None,
        expected_p2p: tuple[str, ...] | None = None,
    ) -> None:
        baseline_f2p = baseline.tests_status["FAIL_TO_PASS"]
        baseline_p2p = baseline.tests_status["PASS_TO_PASS"]
        gold_f2p = gold.tests_status["FAIL_TO_PASS"]
        gold_p2p = gold.tests_status["PASS_TO_PASS"]
        valid = (
            not baseline_f2p["success"]
            and bool(baseline_f2p["failure"])
            and not baseline_p2p["failure"]
            and not gold_f2p["failure"]
            and not gold_p2p["failure"]
            and bool(gold_f2p["success"])
        )
        if expected_f2p is not None and expected_p2p is not None:
            f2p = set(expected_f2p)
            p2p = set(expected_p2p)
            valid = valid and (
                set(baseline_f2p["failure"]) == f2p
                and set(baseline_f2p["success"]) == set()
                and set(baseline_p2p["success"]) == p2p
                and set(baseline_p2p["failure"]) == set()
                and set(gold_f2p["success"]) == f2p
                and set(gold_f2p["failure"]) == set()
                and set(gold_p2p["success"]) == p2p
                and set(gold_p2p["failure"]) == set()
            )
        if not valid:
            raise HarnessError("instance failed baseline-empty/gold F2P/P2P integrity gate")

    def validate_instance(self, instance: dict[str, Any]) -> dict[str, Any]:
        instance_id = instance["instance_id"]
        def expected_tests(name: str) -> tuple[str, ...]:
            value = instance[name]
            if isinstance(value, str):
                value = json.loads(value)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise HarnessError(f"{name} is not a test identifier list")
            if len(value) != len(set(value)):
                raise HarnessError(f"{name} contains duplicate test identifiers")
            return tuple(value)
        expected_f2p = expected_tests("FAIL_TO_PASS")
        expected_p2p = expected_tests("PASS_TO_PASS")
        if not expected_f2p:
            raise HarnessError("FAIL_TO_PASS must not be empty")
        safe_id = instance_id.replace("/", "_")
        run_dir = self.output_root / safe_id
        existing_evidence = run_dir / "harness-evidence.json"
        if existing_evidence.is_file():
            manifest = json.loads(existing_evidence.read_text(encoding="utf-8"))
            if manifest.get("harness_revision") != HARNESS_REVISION or manifest.get("instance_id") != instance_id:
                raise HarnessError("existing harness evidence has incompatible identity")
            def restored(kind: str) -> HarnessRun:
                item = manifest[kind]
                for relative, expected in item["report_sha256"].items():
                    report = self.project_root / relative
                    if not report.is_file() or sha256_file(report) != expected:
                        raise HarnessError("existing harness report evidence is missing or drifted")
                return HarnessRun(
                    kind=kind, command=tuple(item["command"]), exit_code=item["exit_code"],
                    stdout_sha256=item["stdout_sha256"], stderr_sha256=item["stderr_sha256"],
                    report_paths=tuple(item["report_paths"]), report_sha256=item["report_sha256"],
                    tests_status={category: {name: tuple(values) for name, values in dispositions.items()} for category, dispositions in item["tests_status"].items()},
                    image_digests=tuple(item.get("image_digests", ())),
                )
            self._assert_integrity(
                restored("baseline"), restored("gold"), expected_f2p, expected_p2p
            )
            if not manifest["baseline"].get("image_digests") or not manifest["gold"].get("image_digests"):
                raise HarnessError("existing harness evidence lacks immutable image digests")
            return manifest
        if run_dir.exists():
            raise HarnessError("incomplete prior harness attempt exists without valid evidence")
        run_dir.mkdir(parents=True, exist_ok=False)
        baseline_path = run_dir / "baseline-empty.json"
        baseline_path.write_text(json.dumps([{
            "instance_id": instance_id,
            "model_name_or_path": "baseline-empty",
            # The official harness skips empty patches entirely. Add an inert
            # marker file so it executes the unmodified base-commit tests.
            "model_patch": BASELINE_MARKER_PATCH,
        }]) + "\n", encoding="utf-8")
        fingerprint = docker_fingerprint(run_dir)
        baseline_id = f"interview-{safe_id}-baseline"
        gold_id = f"interview-{safe_id}-gold"
        (run_dir / "attempt.json").write_text(json.dumps({
            "schema": "SWEbenchHarnessAttempt.v1", "instance_id": instance_id,
            "harness_revision": HARNESS_REVISION,
            "baseline_command": self._command(str(baseline_path), instance_id, baseline_id),
            "gold_command": self._command("gold", instance_id, gold_id),
            "docker": fingerprint,
        }, indent=2) + "\n", encoding="utf-8")
        baseline = self._capture(
            "baseline", self._command(str(baseline_path), instance_id, baseline_id), run_dir,
            run_id=baseline_id, model_name="baseline-empty", instance_id=instance_id,
        )
        self._assert_baseline_integrity(baseline, expected_f2p, expected_p2p)
        gold = self._capture(
            "gold", self._command("gold", instance_id, gold_id), run_dir,
            run_id=gold_id, model_name="gold", instance_id=instance_id,
        )
        self._assert_integrity(baseline, gold, expected_f2p, expected_p2p)
        manifest = {
            "schema": "SWEbenchHarnessEvidence.v1",
            "harness_revision": HARNESS_REVISION,
            "instance_id": instance_id,
            "docker": fingerprint,
            "baseline": baseline.as_dict(),
            "gold": gold.as_dict(),
            "expected": {
                "fail_to_pass": list(expected_f2p),
                "pass_to_pass": list(expected_p2p),
                "baseline_fail_to_pass": "all fail",
                "baseline_pass_to_pass": "all pass",
                "gold_fail_to_pass": "all pass",
                "gold_pass_to_pass": "all pass",
            },
        }
        (run_dir / "harness-evidence.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return manifest


def validate_pilot(
    harness: OfficialHarness,
    rows: list[dict[str, Any]],
    sealed_selection: dict[str, Any],
) -> dict[str, Any]:
    """Validate every slot, replacing invalid cases only within its frozen stratum."""

    by_id = {str(row["instance_id"]): row for row in rows}
    approved: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    used: set[str] = set()
    for slot in sealed_selection["cases"]:
        attempts = [slot["instance_id"], *slot["replacement_instance_ids"]]
        accepted = None
        for instance_id in attempts:
            if instance_id in used:
                continue
            row = by_id.get(instance_id)
            if row is None:
                raise HarnessError(f"selection references missing dataset row: {instance_id}")
            try:
                evidence = harness.validate_instance(row)
            except HarnessError as exc:
                run_dir = harness.output_root / instance_id.replace("/", "_")
                log_digests = {
                    str(path.relative_to(harness.output_root)): sha256_file(path)
                    for path in sorted(run_dir.glob("*.log"))
                } if run_dir.is_dir() else {}
                exclusions.append({
                    "instance_id": instance_id,
                    "partition": slot["partition"],
                    "repository_family": slot["repository_family"],
                    "stratum": [slot["repository_family"], slot["difficulty"], slot["size_bucket"]],
                    "reason": str(exc),
                    "log_sha256": log_digests,
                    "docker": docker_fingerprint(harness.output_root),
                })
                continue
            accepted = {
                "partition": slot["partition"],
                "instance_id": instance_id,
                "alias": holdout_alias(instance_id) if slot["partition"] == "holdout" else instance_id,
                "repository_family": slot["repository_family"],
                "difficulty": slot["difficulty"],
                "size_bucket": slot["size_bucket"],
                "harness_evidence_sha256": hashlib.sha256(
                    json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
            used.add(instance_id)
            break
        if accepted is None:
            raise HarnessError(
                "same-stratum replacement pool exhausted for "
                f"{slot['partition']}:{slot['alias']}"
            )
        approved.append(accepted)
    return {
        "schema": "SWEbenchPilotHarnessValidation.v1",
        "harness_revision": HARNESS_REVISION,
        "approved": approved,
        "exclusions": exclusions,
    }
