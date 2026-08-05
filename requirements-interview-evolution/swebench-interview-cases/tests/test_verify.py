import hashlib

import pytest

from swebench_interview_cases.verify import VerificationError, _verify_run_artifacts


def test_completion_verifier_rejects_tampered_run_artifact(tmp_path):
    artifact = tmp_path / "judge.json"
    artifact.write_text("original")
    manifest = {"artifact_sha256": {"judge.json": hashlib.sha256(b"original").hexdigest()}}
    _verify_run_artifacts(tmp_path, manifest)
    artifact.write_text("tampered")
    with pytest.raises(VerificationError, match="drifted"):
        _verify_run_artifacts(tmp_path, manifest)
