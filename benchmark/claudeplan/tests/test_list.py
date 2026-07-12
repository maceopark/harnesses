from conftest import listed_ids


def _seed_open_and_done(run_cli):
    run_cli(["add", "open item"])
    run_cli(["add", "done item"])
    run_cli(["done", "2"])


def test_req09_default_hides_done(run_cli):
    _seed_open_and_done(run_cli)
    code, out, _ = run_cli(["list"])
    assert code == 0
    assert "open item" in out
    assert "done item" not in out


def test_req10_all_includes_done_marked(run_cli):
    _seed_open_and_done(run_cli)
    _, out, _ = run_cli(["list", "--all"])
    assert "open item" in out and "done item" in out
    done_line = next(line for line in out.splitlines() if "done item" in line)
    assert "[x]" in done_line


def test_req11_done_only(run_cli):
    _seed_open_and_done(run_cli)
    _, out, _ = run_cli(["list", "--done"])
    assert "done item" in out
    assert "open item" not in out


def test_req12_all_and_done_conflict(run_cli):
    code, _, err = run_cli(["list", "--all", "--done"])
    assert code == 2
    assert "not allowed with" in err


def test_req13_no_matches_message(run_cli):
    run_cli(["add", "x"])
    run_cli(["done", "1"])
    code, out, _ = run_cli(["list"])
    assert code == 0
    assert out.strip() == "No todos found."


def test_req14_missing_store_file(run_cli, store_file):
    code, out, _ = run_cli(["list"])
    assert code == 0
    assert out.strip() == "No todos found."
    assert not store_file.exists()


def test_req15_17_sort_matrix(run_cli):
    run_cli(["add", "m-nodue"])                                    # id 1
    run_cli(["add", "h-late", "-p", "high", "-d", "2026-07-20"])   # id 2
    run_cli(["add", "h-early", "-p", "high", "-d", "2026-07-10"])  # id 3
    run_cli(["add", "l-early", "-p", "low", "-d", "2026-01-01"])   # id 4
    run_cli(["add", "h-nodue", "-p", "high"])                      # id 5
    run_cli(["add", "m-due", "-d", "2026-07-10"])                  # id 6
    _, out, _ = run_cli(["list"])
    # priority first; within priority dated items ascending, then no-due; low last
    assert listed_ids(out) == [3, 2, 5, 6, 1, 4]


def test_req18_full_tie_breaks_by_id(run_cli):
    run_cli(["add", "b", "-p", "high", "-d", "2026-07-10"])
    run_cli(["add", "a", "-p", "high", "-d", "2026-07-10"])
    _, out, _ = run_cli(["list"])
    assert listed_ids(out) == [1, 2]


def test_req19_priority_filter(run_cli):
    run_cli(["add", "hi", "-p", "high"])
    run_cli(["add", "lo", "-p", "low"])
    _, out, _ = run_cli(["list", "--priority", "high"])
    assert listed_ids(out) == [1]


def test_req19_priority_filter_composes_with_status(run_cli):
    run_cli(["add", "hi", "-p", "high"])
    run_cli(["done", "1"])
    _, out, _ = run_cli(["list", "--priority", "high"])
    assert out.strip() == "No todos found."
    _, out, _ = run_cli(["list", "--done", "--priority", "high"])
    assert listed_ids(out) == [1]


def test_req20_due_before_strict_boundary(run_cli):
    run_cli(["add", "before", "-d", "2026-07-09"])  # id 1: included
    run_cli(["add", "on", "-d", "2026-07-10"])      # id 2: excluded (strictly before)
    run_cli(["add", "nodue"])                       # id 3: excluded (no due date)
    _, out, _ = run_cli(["list", "--due-before", "2026-07-10"])
    assert listed_ids(out) == [1]


def test_req21_overdue(run_cli, frozen_today):
    run_cli(["add", "yesterday", "-d", "2026-07-06"])  # included
    run_cli(["add", "today", "-d", "2026-07-07"])      # excluded: due today is not overdue
    run_cli(["add", "nodue"])                          # excluded
    _, out, _ = run_cli(["list", "--overdue"])
    assert listed_ids(out) == [1]


def test_req22_filters_and_together(run_cli, frozen_today):
    run_cli(["add", "h-over", "-p", "high", "-d", "2026-07-01"])
    run_cli(["add", "l-over", "-p", "low", "-d", "2026-07-01"])
    run_cli(["add", "h-future", "-p", "high", "-d", "2026-08-01"])
    _, out, _ = run_cli(["list", "--priority", "high", "--overdue"])
    assert listed_ids(out) == [1]


def test_req23_due_before_validated(run_cli):
    code, _, err = run_cli(["list", "--due-before", "garbage"])
    assert code == 2
    assert "YYYY-MM-DD" in err
