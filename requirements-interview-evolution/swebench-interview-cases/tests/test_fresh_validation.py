import json

from swebench_interview_cases.fresh_validation import (
    copy_corpus_without_old_validation,
    prepare_fresh_validation,
    splice_fresh_validation,
)
from swebench_interview_cases.schemas import artifact_digest


class Imported:
    def __init__(self, instance_id): self.instance_id = instance_id
    def public_source_descriptor(self): return {"revision": "pinned", "id": self.instance_id}
    def sealed_inputs(self): return {"issue": {"digest": "a" * 64}}


def _row(family, number):
    return {
        "instance_id": f"{family.replace('/', '__')}-{number}", "repo": family,
        "difficulty": "easy", "patch": "+x", "test_patch": "+t",
    }


def test_fresh_validation_is_deterministic_excludes_exposed_and_freezes_replacements(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "swebench_interview_cases.fresh_validation.import_row",
        lambda row, **kwargs: Imported(row["instance_id"]),
    )
    rows = [_row(f"org/repo{family}", number) for family in range(5) for number in range(3)]
    exposed = {rows[0]["instance_id"]}
    first = prepare_fresh_validation(
        rows, exposed_instance_ids=exposed, cache=object(),
        forbidden_repository_families={"org/repo4"},
    )
    second = prepare_fresh_validation(
        reversed(rows), exposed_instance_ids=exposed, cache=object(),
        forbidden_repository_families={"org/repo4"},
    )
    assert first == second
    public, sealed = first
    assert len(public["cases"]) == len(sealed["cases"]) == 3
    assert all(item["partition"] == "validation" for item in sealed["cases"])
    assert len({item["repository_family"] for item in sealed["cases"]}) == 3
    assert all(item["replacement_instance_ids"] for item in sealed["cases"])
    frozen_ids = {
        instance_id for item in sealed["cases"]
        for instance_id in [item["instance_id"], *item["replacement_instance_ids"]]
    }
    assert not frozen_ids & exposed
    assert all(not value.startswith("org__repo4-") for value in frozen_ids)


def test_splice_preserves_development_and_holdout_and_replaces_validation():
    def cases(partition, count, prefix):
        return [{"partition": partition, "instance_id": f"{prefix}{i}"} for i in range(count)]
    pilot_public = {"cases": cases("development", 8, "d") + cases("validation", 3, "v") + cases("holdout", 4, "h")}
    pilot_sealed = {"cases": list(pilot_public["cases"]), "public_selection_digest": "old"}
    fresh_public = {"cases": cases("validation", 3, "new")}
    fresh_sealed = {"cases": list(fresh_public["cases"]), "public_selection_digest": artifact_digest(fresh_public)}
    public, sealed = splice_fresh_validation(
        pilot_public=pilot_public, pilot_sealed=pilot_sealed,
        fresh_public=fresh_public, fresh_sealed=fresh_sealed,
    )
    assert [item for item in sealed["cases"] if item["partition"] == "development"] == pilot_sealed["cases"][:8]
    assert [item for item in sealed["cases"] if item["partition"] == "holdout"] == pilot_sealed["cases"][-4:]
    assert {item["instance_id"] for item in sealed["cases"] if item["partition"] == "validation"} == {"new0", "new1", "new2"}
    assert sealed["public_selection_digest"] == artifact_digest(public)


def test_splice_preserves_existing_slot_numbers_for_resumable_cases():
    pilot_cases = (
        [{"partition": "development", "instance_id": f"d{i}"} for i in range(4)]
        + [{"partition": "validation", "instance_id": "v0"}]
        + [{"partition": "holdout", "instance_id": f"h{i}"} for i in range(2)]
        + [{"partition": "development", "instance_id": f"d{i}"} for i in range(4, 8)]
        + [{"partition": "validation", "instance_id": "v1"}]
        + [{"partition": "holdout", "instance_id": f"h{i}"} for i in range(2, 4)]
        + [{"partition": "validation", "instance_id": "v2"}]
    )
    fresh_cases = [
        {"partition": "validation", "instance_id": f"new{i}"} for i in range(3)
    ]
    public, sealed = splice_fresh_validation(
        pilot_public={"cases": pilot_cases},
        pilot_sealed={"cases": pilot_cases, "public_selection_digest": "old"},
        fresh_public={"cases": fresh_cases},
        fresh_sealed={
            "cases": fresh_cases,
            "public_selection_digest": artifact_digest({"cases": fresh_cases}),
        },
    )
    assert [
        (index, item["instance_id"])
        for index, item in enumerate(sealed["cases"])
        if item["partition"] == "validation"
    ] == [(4, "new0"), (11, "new1"), (14, "new2")]
    assert public["cases"] == sealed["cases"]


def test_copy_corpus_removes_only_old_validation_artifacts(tmp_path):
    source = tmp_path / "source"
    for alias in ("dev", "old-validation", "holdout"):
        path = source / "cases" / alias
        path.mkdir(parents=True, exist_ok=True)
        (path / "case.json").write_text(alias)
    (source / "validation").mkdir()
    (source / "validation" / "index.json").write_text(json.dumps({"cases": [{"alias": "old-validation"}]}))
    (source / "development").mkdir()
    (source / "development" / "index.json").write_text("dev-index")
    (source / "holdout").mkdir()
    (source / "holdout" / "index.json").write_text("holdout-index")
    (source / "pilot-manifest.json").write_text("stale")
    destination = tmp_path / "destination"
    copy_corpus_without_old_validation(source, destination)
    assert (destination / "cases" / "dev" / "case.json").read_text() == "dev"
    assert (destination / "cases" / "holdout" / "case.json").read_text() == "holdout"
    assert not (destination / "cases" / "old-validation").exists()
    assert not (destination / "validation" / "index.json").exists()
    assert (destination / "development" / "index.json").read_text() == "dev-index"
    assert (destination / "holdout" / "index.json").read_text() == "holdout-index"
