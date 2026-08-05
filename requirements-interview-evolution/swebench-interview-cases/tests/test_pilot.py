from swebench_interview_cases import DATASET_PARQUET_SHA256
from swebench_interview_cases.pilot import (
    _replacement_map,
    candidate_from_row,
    changed_lines,
    reseed_exhausted_slot,
)
from swebench_interview_cases.selection import Candidate, Selection, candidate_order


def test_changed_lines_ignores_diff_headers():
    diff = "--- a/x\n+++ b/x\n-old\n+new\n context\n"
    assert changed_lines(diff) == 2


def test_candidate_uses_repo_as_canonical_family():
    candidate = candidate_from_row({
        "instance_id": "org__repo-1", "repo": "org/repo", "difficulty": "short",
        "patch": "+one\n-two", "test_patch": "+test",
    })
    assert candidate.repository_family == "org/repo"
    assert candidate.patch_lines == 2
    assert candidate.test_lines == 1


def test_replacement_queue_wraps_to_exhaust_entire_stratum() -> None:
    candidates = [
        Candidate(f"org__repo-{number}", "org/repo", "easy", 1, 1)
        for number in range(1, 6)
    ]
    ranked = candidate_order(candidates, DATASET_PARQUET_SHA256)
    selected = Selection("development", ranked[3], ranked[3].candidate.instance_id)
    replacements = _replacement_map(candidates, [selected])[selected.ranked.candidate.instance_id]
    expected = [item.candidate.instance_id for item in ranked[4:] + ranked[:3]]
    assert replacements == expected


def test_exhausted_slot_reseeds_inside_bound_partition(tmp_path, monkeypatch) -> None:
    class Imported:
        def public_source_descriptor(self): return {"revision": "pinned"}
        def sealed_inputs(self): return {"issue": {"digest": "a" * 64}}

    monkeypatch.setattr("swebench_interview_cases.pilot.import_row", lambda *args, **kwargs: Imported())
    rows = [
        {"instance_id": "sea-1", "repo": "sea/repo", "difficulty": "easy", "patch": "+x", "test_patch": "+t"},
        *[
            {"instance_id": f"lint-{n}", "repo": "lint/repo", "difficulty": "easy", "patch": "+x", "test_patch": "+t"}
            for n in range(1, 4)
        ],
    ]
    public = {"cases": [{}, {}]}
    sealed = {"cases": [
        {"partition": "holdout", "repository_family": "sea/repo", "instance_id": "sea-1", "replacement_instance_ids": []},
        {"partition": "holdout", "repository_family": "lint/repo", "instance_id": "lint-1", "replacement_instance_ids": []},
    ]}
    _, amended = reseed_exhausted_slot(
        public=public, sealed=sealed, rows=rows, slot_number=1,
        excluded_instance_ids={"sea-1"}, cache=object(),
    )
    slot = amended["cases"][0]
    assert slot["repository_family"] == "lint/repo"
    assert slot["instance_id"] in {"lint-2", "lint-3"}
    assert len(slot["replacement_instance_ids"]) == 1
    assert slot["reseeded_after_exhaustion"]["excluded_instance_ids"] == ["sea-1"]
