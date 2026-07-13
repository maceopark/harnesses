# Todo CLI App 6

A local, single-user Todo CLI for Python 3.10+ on macOS and Linux. Runtime code uses only the Python standard library.

## Commands

```text
todo add TITLE
todo list
todo done ID
```

`add` trims outer whitespace, allows duplicate titles, and rejects empty titles, dash-prefixed titles, and Unicode `Cc` control characters. It prints `added #ID: TITLE`. IDs start at 1, increase from the maximum stored ID, include completed records in allocation, and are never reused.

`list` prints active records as `ID TITLE` in ascending ID order. An empty list produces no output and does not create storage.

`done` retains the selected record with `done: true`, hides it from future lists, and prints `done #ID: TITLE`. Missing, nonpositive, and already-completed IDs are domain errors. Non-integer IDs are argparse usage errors.

No edit, delete, search, tags, priorities, dates, history, migration, networking, authentication, or concurrent-access support is provided.

## Storage

Each process uses `.todo.json` in its current working directory:

```json
{
  "schema_version": 1,
  "items": [
    {
      "id": 1,
      "title": "write tests",
      "done": false
    }
  ]
}
```

The schema is closed. Writes use literal UTF-8, two-space indentation, fixed key order, and one trailing newline. Mutations use a same-directory temporary file, flush, `fsync`, and atomic replacement. Invalid UTF-8, malformed or invalid-schema JSON, symlinks, non-regular paths, and storage failures are rejected without changing original bytes; temporary files are cleaned when possible.

## Streams and exits

- Success: stdout only, exit 0.
- Domain error: `error: REASON` on stderr, exit 1.
- Usage error: argparse usage on stderr, exit 2.
- Storage error: `error: .todo.json: REASON` on stderr, exit 3.

## Development

```bash
uv run --project benchmark/todo-cli-app-6 pytest -q
```
