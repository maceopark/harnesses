# todo-cli-codexplan

Clean-room Basic CRUD todo CLI benchmark fixture.

This project is intentionally small and standard-library-only at runtime.

## Run

```bash
uv run codexplan --help
uv run codexplan add "buy milk"
uv run codexplan list
uv run codexplan done 1
uv run codexplan rm 1
```

## Storage

- Default store: `~/.codexplan_todos.json`
- Override store: `CODEXPLAN_FILE=/tmp/todos.json`
- Missing store files are treated as an empty list and are not created by `list`.
- Writes are atomic: temp file in the same directory, flush/fsync, then replace.
- Corrupt or schema-invalid stores return exit `3` and are not overwritten.

## Commands

### `add TITLE`

Adds a todo with the next immutable id.

```text
added 1
```

### `list`

Prints one row per todo sorted by id.

```text
1	[ ]	buy milk
```

### `done ID`

Marks a todo complete. Already-complete todos are idempotent.

```text
done 1
already done 1
```

### `rm ID`

Removes a todo by immutable id. Removed ids are never reused.

```text
removed 1
```

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Domain error, such as empty title or unknown id |
| 2 | Usage error, such as missing args or non-integer id syntax |
| 3 | Storage error, such as corrupt JSON or invalid schema |

## Verify

```bash
uv run ruff check .
uv run basedpyright
uv run pytest
```
