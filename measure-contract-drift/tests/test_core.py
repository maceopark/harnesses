from __future__ import annotations

from pathlib import Path

import pytest

from driftbench import cli
from driftbench.decision_log import validate_decision_log
from driftbench.models import RunConfig, RunManifest, RunMode, RunState, RunStatus
from driftbench.semantic import compare_assertions
from driftbench.state import StateStore


def test_schema_alias_preserves_run_config_json_contract() -> None:
    document = {
        "schema": "RunConfig.v1",
        "mode": "fake-dev",
        "release_id": "release-v1",
        "corpus_root": "corpus/public",
        "arms": [{"arm_id": "direct-v1", "source": "scored"}],
        "models": {
            "planner": "planner-v1",
            "implementer": "implementer-v1",
            "postmortem": "postmortem-v1",
        },
        "seed_label": "seed-v1",
        "partition": "dev",
        "max_attempts": 1,
    }

    config = RunConfig.model_validate(document)

    assert config.schema_ == "RunConfig.v1"
    assert config.model_dump(mode="json", by_alias=True) == document


def test_semantic_comparison_only_awards_exact_equivalence() -> None:
    expected = {
        "atoms": [
            {
                "guard": "a task is created",
                "effect": "the task has a title",
                "polarity": "must",
                "boundary": "title is nonblank",
                "temporal": "at creation",
            },
            {
                "guard": "a task is created",
                "effect": "the task has a status",
                "polarity": "must",
                "boundary": "status is a supported value",
                "temporal": "at creation",
            },
        ]
    }

    exact = compare_assertions(expected, {"atoms": list(reversed(expected["atoms"]))})
    broad = compare_assertions(expected, {"atoms": [expected["atoms"][0]]})

    assert (exact.relation, exact.primary_credit, exact.exact_equivalent) == (
        "exact",
        1,
        True,
    )
    assert (broad.relation, broad.primary_credit, broad.exact_equivalent) == (
        "broader",
        0,
        False,
    )


def test_decision_log_rejects_noncontiguous_records() -> None:
    with pytest.raises(ValueError, match="ordered, unique, and contiguous"):
        validate_decision_log(
            [
                {
                    "schema_version": "DecisionLog.v1",
                    "id": "decision#2",
                    "decision": "Skip the required first decision.",
                }
            ]
        )


def test_local_score_denies_holdout_run(tmp_path: Path, capsys) -> None:
    digest = "0" * 64
    run_dir = tmp_path / "holdout-run"
    manifest = RunManifest(
        run_id="run-holdout",
        release_id="release-v1",
        mode=RunMode.LIVE_HOLDOUT,
        partition="holdout",
        config_digest=digest,
        corpus_digest=digest,
        arm_digests={"direct-v1": digest},
        worker_image=f"sha256:{digest}",
        status=RunStatus.CREATED,
    )
    state = RunState(
        run_id=manifest.run_id,
        status=RunStatus.CREATED,
        config_digest=digest,
        corpus_digest=digest,
        arm_digests=manifest.arm_digests,
        worker_image=manifest.worker_image,
        cells=(),
    )
    StateStore(run_dir).initialize(manifest, state)

    assert cli.main(["score", "--run-dir", str(run_dir)]) == cli.EXIT_UNSAFE_LOCAL
    assert "cannot score holdout/private results" in capsys.readouterr().err
