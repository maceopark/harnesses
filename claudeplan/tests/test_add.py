import pytest


def test_req01_add_on_fresh_store(run_cli):
    code, out, err = run_cli(["add", "Buy milk"])
    assert code == 0
    assert out.strip() == 'Added todo 1: "Buy milk"'
    assert err == ""


def test_req02_sequential_ids(run_cli):
    run_cli(["add", "one"])
    code, out, _ = run_cli(["add", "two"])
    assert code == 0
    assert out.strip() == 'Added todo 2: "two"'


def test_req03_default_priority_medium(run_cli, read_store):
    run_cli(["add", "x"])
    assert read_store()["todos"][0]["priority"] == "medium"


def test_req04_priority_choices(run_cli):
    for prio in ("high", "medium", "low"):
        assert run_cli(["add", f"t-{prio}", "--priority", prio])[0] == 0
    code, _, err = run_cli(["add", "bad", "--priority", "urgent"])
    assert code == 2
    assert "invalid choice" in err


@pytest.mark.parametrize("bad", ["07/10/2026", "20260710", "tomorrow", "2026-2-5"])
def test_req05_due_format_rejected(run_cli, bad):
    code, _, err = run_cli(["add", "x", "--due", bad])
    assert code == 2
    assert "YYYY-MM-DD" in err


def test_req05_due_format_accepted(run_cli, read_store):
    code, _, _ = run_cli(["add", "x", "--due", "2026-02-28"])
    assert code == 0
    assert read_store()["todos"][0]["due"] == "2026-02-28"


@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01"])
def test_req06_impossible_dates(run_cli, bad):
    code, _, err = run_cli(["add", "x", "--due", bad])
    assert code == 2
    assert "YYYY-MM-DD" in err


@pytest.mark.parametrize("title", ["", "   "])
def test_req07_empty_title(run_cli, store_file, title):
    code, _, err = run_cli(["add", title])
    assert code == 2
    assert "title must not be empty" in err
    assert not store_file.exists()


def test_req08_title_trimmed(run_cli, read_store):
    run_cli(["add", "  Buy milk  "])
    assert read_store()["todos"][0]["title"] == "Buy milk"
