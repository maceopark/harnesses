def test_req24_done_marks_complete(run_cli, read_store):
    run_cli(["add", "Pay rent"])
    code, out, err = run_cli(["done", "1"])
    assert code == 0
    assert out.strip() == 'Completed todo 1: "Pay rent"'
    assert err == ""
    todo = read_store()["todos"][0]
    assert todo["done"] is True
    assert todo["completed_at"]


def test_req25_done_unknown_id(run_cli):
    code, out, err = run_cli(["done", "42"])
    assert code == 1
    assert err.strip() == "Error: no todo with id 42"
    assert out == ""


def test_req26_double_done_is_error(run_cli, read_store):
    run_cli(["add", "x"])
    run_cli(["done", "1"])
    before = read_store()
    code, _, err = run_cli(["done", "1"])
    assert code == 1
    assert err.strip() == "Error: todo 1 is already done"
    assert read_store() == before  # no state change


def test_req27_non_integer_id(run_cli):
    code, _, err = run_cli(["done", "abc"])
    assert code == 2
    assert "invalid int value" in err


def test_req28_delete(run_cli, read_store):
    run_cli(["add", "x"])
    code, out, _ = run_cli(["delete", "1"])
    assert code == 0
    assert out.strip() == 'Deleted todo 1: "x"'
    assert read_store()["todos"] == []


def test_req29_delete_unknown_id(run_cli):
    code, _, err = run_cli(["delete", "9"])
    assert code == 1
    assert err.strip() == "Error: no todo with id 9"


def test_req30_delete_completed_item(run_cli, read_store):
    run_cli(["add", "x"])
    run_cli(["done", "1"])
    code, _, _ = run_cli(["delete", "1"])
    assert code == 0
    assert read_store()["todos"] == []


def test_req31_ids_never_reused(run_cli):
    for title in ("a", "b", "c"):
        run_cli(["add", title])
    run_cli(["delete", "3"])
    _, out, _ = run_cli(["add", "d"])
    assert out.strip() == 'Added todo 4: "d"'
