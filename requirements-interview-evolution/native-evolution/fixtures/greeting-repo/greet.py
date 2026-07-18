from __future__ import annotations

import sys


def greeting(name: str) -> str:
    return f"Hello, {name}!"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: greet.py NAME", file=sys.stderr)
        return 2
    print(greeting(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
