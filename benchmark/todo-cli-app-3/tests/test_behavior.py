"""Behavior contract rows beyond the raw matrix: REQ-001..008, 011."""

from __future__ import annotations

from conftest import TODAY, TOMORROW, YESTERDAY, populate, read_store, run, store_file


def test_req001_today_view_composition(home):
    populate(
        home,
        [
            {"title": "이월 미완", "seq": 1},  # undated, added earlier
            {"title": "오늘 기한", "due": TODAY, "seq": 2},
            {"title": "내일 기한", "due": TOMORROW, "seq": 3},
            {"title": "연체 항목", "due": YESTERDAY, "seq": 4},
            {"title": "어제 완료", "done_on": YESTERDAY, "seq": 5},
        ],
    )
    out = run(home).stdout
    assert "이월 미완" in out and "오늘 기한" in out and "연체 항목" in out
    assert "내일 기한" not in out
    assert "어제 완료" not in out


def test_req001_overdue_marker_distinct_from_normal_rendering(home):
    # same item rendered overdue vs not-yet-due differs by a marker token
    populate(home, [{"title": "정산 제출", "due": YESTERDAY}])
    overdue_line = run(home).stdout.strip()
    populate(home, [{"title": "정산 제출", "due": TOMORROW}])
    normal_line = run(home, today=YESTERDAY).stdout.strip()
    assert overdue_line != normal_line
    marker = "[기한 지남!]"
    assert marker in overdue_line and marker not in normal_line


def test_req002_done_today_checked_at_bottom_unnumbered(home):
    populate(
        home,
        [
            {"title": "남은 일"},
            {"title": "오늘 끝낸 일", "done_on": TODAY},
            {"title": "어제 끝낸 일", "done_on": YESTERDAY},
        ],
    )
    lines = run(home).stdout.strip().splitlines()
    assert lines[0].strip().startswith("1. 남은 일")
    assert lines[-1].strip().startswith("✓ 오늘 끝낸 일")
    assert all("어제 끝낸 일" not in line for line in lines)


def test_req003_sort_priority_then_insertion_overdue_no_boost(home):
    populate(
        home,
        [
            {"title": "보통 일", "pri": "mid", "seq": 1},
            {"title": "급한 일 A", "pri": "high", "seq": 2},
            {"title": "급한 연체", "pri": "high", "due": YESTERDAY, "seq": 3},
        ],
    )
    lines = run(home).stdout.strip().splitlines()
    assert "1. 급한 일 A" in lines[0]
    assert "2. 급한 연체" in lines[1] and "[기한 지남!]" in lines[1]
    assert "3. 보통 일" in lines[2]


def test_req004_add_variants(home):
    assert run(home, "add", "   ").returncode == 1
    assert not store_file(home).exists() or read_store(home)["items"] == []

    assert run(home, "add", "보고서", "작성", "--pri", "high").returncode == 0
    item = read_store(home)["items"][0]
    assert item["title"] == "보고서 작성" and item["pri"] == "high"

    assert run(home, "add", "메일 회신").returncode == 0
    assert read_store(home)["items"][1]["pri"] == "mid"  # default priority

    assert run(home, "--pri", "low", "add", "임시").returncode == 2  # flag before subcommand: usage
    assert run(home, "add", "--pri", "low", "청소").returncode == 0  # flag before positional
    assert read_store(home)["items"][2]["pri"] == "low"


def test_req005_multi_arg_atomic_and_rejections(home):
    items = [{"title": f"할일 {i}", "seq": i} for i in range(1, 4)]
    populate(home, items)
    assert run(home, "done", "1", "2").returncode == 0
    store = read_store(home)["items"]
    assert store[0]["done_on"] == TODAY and store[1]["done_on"] == TODAY
    assert store[2]["done_on"] is None

    populate(home, items)
    before = store_file(home).read_bytes()
    for bad in (["2", "9"], ["0"], ["-1"], ["x"], ["1", "1"]):
        result = run(home, "done", *bad)
        assert result.returncode == 1, bad
        assert store_file(home).read_bytes() == before, bad


def test_req006_rm_deletes_outright(home):
    populate(home, [{"title": "지울 일"}, {"title": "남길 일"}])
    assert run(home, "rm", "1").returncode == 0
    titles = [i["title"] for i in read_store(home)["items"]]
    assert titles == ["남길 일"]
    assert run(home, "rm", "0").returncode == 1


def test_req007_mutations_print_refreshed_view(home):
    populate(home, [{"title": "끝낼 일"}, {"title": "남을 일"}])
    out = run(home, "done", "1").stdout
    assert "✓ 끝낼 일 (오늘 완료)" in out
    assert "1. 남을 일" in out
    out = run(home, "add", "새 일").stdout
    assert "새 일" in out


def test_req008_usage_surface(home):
    result = run(home, "--help")
    assert result.returncode == 0 and "usage" in result.stdout.lower()
    result = run(home, "add")  # missing operand
    assert result.returncode == 2 and "usage" in result.stderr.lower()
    result = run(home, "done")  # missing operand
    assert result.returncode == 2


def test_req011_day_boundary_pure_render(home):
    populate(
        home,
        [
            {"title": "수요일 미완", "seq": 1},
            {"title": "수요일 완료", "done_on": YESTERDAY, "seq": 2},
        ],
    )
    wed = run(home, today=YESTERDAY).stdout
    assert "수요일 미완" in wed and "✓ 수요일 완료" in wed
    thu = run(home, today=TODAY).stdout
    assert "수요일 미완" in thu and "수요일 완료" not in thu
