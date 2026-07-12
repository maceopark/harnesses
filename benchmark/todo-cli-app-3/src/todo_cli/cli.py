"""Command dispatch. Closed operation set: view (bare), add, done, rm (REQ-008).

Exit codes: 0 success / 1 validation or store failure / 2 usage error.
Stream discipline: lists -> stdout; errors and usage -> stderr.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from todo_cli import render, store

EXIT_VALIDATION = 1
EXIT_USAGE = 2


def _due(value: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --due date (expected YYYY-MM-DD): {value!r}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo",
        description="아침 todo CLI: `todo`로 오늘 할일 보기",
    )
    sub = parser.add_subparsers(dest="command")

    add = sub.add_parser("add", help="할일 추가: todo add <제목...> [--pri] [--due] [--memo]")
    add.add_argument("title", nargs="+")
    add.add_argument("--pri", choices=store.VALID_PRI, default="mid")
    add.add_argument("--due", type=_due, default=None)
    add.add_argument("--memo", default=None)

    done = sub.add_parser("done", help="완료 처리: todo done <번호> [<번호>...]")
    done.add_argument("numbers", nargs="+")

    rm = sub.add_parser("rm", help="삭제: todo rm <번호> [<번호>...]")
    rm.add_argument("numbers", nargs="+")

    return parser


def _resolve_numbers(raw: list[str], view_size: int) -> list[int]:
    """Validate all-or-nothing: integers in [1..view_size], no duplicates (REQ-005/006)."""
    numbers: list[int] = []
    for token in raw:
        try:
            number = int(token)
        except ValueError:
            raise ValueError(f"번호가 아닙니다: {token!r}")
        if not 1 <= number <= view_size:
            raise ValueError(f"목록에 없는 번호입니다: {number}")
        if number in numbers:
            raise ValueError(f"중복된 번호입니다: {number}")
        numbers.append(number)
    return numbers


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    day = render.today()
    try:
        data = store.load()

        if args.command == "add":
            title = " ".join(args.title).strip()
            if not title:
                print("에러: 제목이 비어 있습니다 - 아무것도 추가하지 않았습니다", file=sys.stderr)
                return EXIT_VALIDATION
            data["items"].append(
                {
                    "title": title,
                    "pri": args.pri,
                    "due": args.due,
                    "memo": args.memo,
                    "seq": store.next_seq(data),
                    "done_on": None,
                }
            )
            store.save(data)

        elif args.command in ("done", "rm"):
            snapshot = render.open_items_in_view(data, day)
            try:
                numbers = _resolve_numbers(args.numbers, len(snapshot))
            except ValueError as exc:
                print(f"에러: {exc} - 아무것도 변경하지 않았습니다", file=sys.stderr)
                return EXIT_VALIDATION
            targets = [snapshot[number - 1] for number in numbers]
            if args.command == "done":
                for item in targets:
                    item["done_on"] = day.isoformat()
            else:
                target_seqs = {item["seq"] for item in targets}
                data["items"] = [i for i in data["items"] if i["seq"] not in target_seqs]
            store.save(data)

        print(render.render_view(data, day))
        return 0
    except store.StoreError as exc:
        print(f"에러: {exc}", file=sys.stderr)
        return EXIT_VALIDATION


if __name__ == "__main__":
    sys.exit(main())
