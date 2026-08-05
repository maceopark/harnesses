from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from swebench_interview_cases.repository import prepare_checkout


class Result:
    def __init__(self, code=0, stdout="", stderr=""):
        self.returncode = code; self.stdout = stdout; self.stderr = stderr


def test_existing_clean_checkout_is_verified_without_fetch(tmp_path):
    checkout = tmp_path / "alias"
    (checkout / ".git").mkdir(parents=True)
    commit = "a" * 40
    with patch("swebench_interview_cases.repository._run", side_effect=[Result(stdout=commit + "\n"), Result(stdout=commit + "\n"), Result(stdout="")]) as run:
        result = prepare_checkout(repository="org/repo", base_commit=commit, alias="alias", root=tmp_path)
    assert result["base_commit"] == commit
    assert run.call_count == 3


def test_same_checkout_is_serialized_across_parallel_arms(tmp_path):
    checkout = tmp_path / "alias"
    (checkout / ".git").mkdir(parents=True)
    commit = "b" * 40
    def invoke():
        return prepare_checkout(
            repository="org/repo", base_commit=commit, alias="alias", root=tmp_path,
        )
    with patch(
        "swebench_interview_cases.repository._run",
        side_effect=[Result(stdout=commit + "\n"), Result(stdout=commit + "\n"), Result(stdout=""),
                     Result(stdout=commit + "\n"), Result(stdout=commit + "\n"), Result(stdout="")],
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: invoke(), range(2)))
    assert [item["base_commit"] for item in results] == [commit, commit]
