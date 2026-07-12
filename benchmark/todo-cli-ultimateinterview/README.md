# Todo CLI Ultimateinterview Fixture

This isolated Python 3.10+ fixture provides a sequential local todo command. Runtime code uses only the standard library; pytest is the development dependency.

## Commands

Run the installed console command from the directory that should own the store:

```text
todo add TITLE
todo list
todo done ID
```

`todo add TITLE` trims outer whitespace, rejects empty titles, Unicode `Cc` code points, and titles that cannot be UTF-8 encoded (such as lone surrogates), then prints `added #ID: TITLE` to stdout. Dash-prefixed values use normal argparse option syntax; pass a title that begins with `-` after the separator, for example `todo add -- --alpha`. `todo list` prints active records as `ID TITLE` in ascending ID order. `todo done ID` retains the record, sets it complete, and prints `done #ID: TITLE`.

There are no dates, priorities, tags, search, edit, delete, history, migration, network, or concurrent-access features.

## Store

Each process uses `.todo.json` in its current working directory. The closed JSON v1 schema is:

```json
{
  "schema_version": 1,
  "items": [
    {"id": 1, "title": "write tests", "done": false}
  ]
}
```

Only `schema_version` and `items` are allowed at the root; every item contains exactly `id`, `title`, and `done`. IDs are positive unique integers and continue at maximum stored ID plus one, including retained completed records. Successful mutations write deterministic UTF-8 JSON with one trailing newline through a same-directory temporary file, flush, fsync, and atomic replacement.

## Streams and exits

Successful commands write only to stdout and exit 0. Invalid title or completion transitions write `error: ...` to stderr and exit 1. Argparse usage errors write usage to stderr and exit 2. Invalid, unreadable, non-UTF-8, malformed, non-regular, or unwritable `.todo.json` storage writes `error: .todo.json: ...` to stderr and exit 3. `todo list` never creates a missing store and performs no write-permission preflight.

## Verification

From the harness root, run:

```bash
uv run --project benchmark/todo-cli-ultimateinterview pytest -q
uv run --project benchmark/todo-cli-ultimateinterview pytest -q -k 'req010 or req011'
uv run --project benchmark/todo-cli-ultimateinterview python benchmark/todo-cli-ultimateinterview/tests/verify_real_surface.py
```
