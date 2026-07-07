# todo-cli-deep-interview

A small, single-user todo CLI written with the Python standard library only
(no runtime dependencies). It stores tasks in a single JSON file and exposes
exactly four commands: `add`, `list`, `done`, `rm`.

## Requirements

- Python >= 3.10 (uses `str | None` typing and dataclasses)

## Install / run

You can run the module directly:

```bash
python -m todo_cli <command> [args]
```

Or install the console script (`todo`) via the packaging metadata:

```bash
pip install .
todo <command> [args]
```

## Storage

- Default location: `~/.todos.json`.
- Override with the `TODO_FILE` environment variable (paths starting with `~`
  are expanded):

  ```bash
  TODO_FILE=/tmp/my-todos.json todo list
  ```

- A missing store file is treated as an empty todo list and is **not** created
  until you add a task.
- Writes are atomic (temp file in the same directory + `fsync` + `os.replace`),
  and a corrupt or invalid store file is never overwritten.

## Commands

### add

```bash
todo add TITLE [--due YYYY-MM-DD] [--priority {low,medium,high}]
```

- `TITLE` is a single positional argument; quote multi-word titles.
- `--due` must be an exact ISO `YYYY-MM-DD` calendar date (default: none).
- `--priority` defaults to `medium`.
- Prints `added {id}` on success.

```bash
todo add "buy milk" --due 2026-07-10 --priority high
# added 1
```

### list

```bash
todo list [--priority {low,medium,high}] [--due YYYY-MM-DD]
```

- Prints one row per task:

  ```
  {id}\t{[ ]|[x]}\t{priority}\t{due|-}\t{title}
  ```

  where the status is `[ ]` for incomplete and `[x]` for done, and the due
  column shows `-` when there is no due date.
- Filters (`--priority`, `--due`) are exact matches and can be combined.
- An empty list prints nothing and exits 0.

**Default sort order** (applied after filtering):

1. incomplete tasks before done tasks,
2. higher priority first (`high` > `medium` > `low`),
3. nearer due date first (tasks with no due date sort *after* any dated task),
4. lower id first as a deterministic tiebreaker.

```bash
todo list
# 1	[ ]	high	2026-07-10	buy milk
```

### done

```bash
todo done ID
```

- `ID` is the immutable integer task id (not the list position).
- Prints `done {id}` when it marks an incomplete task complete.
- Already-done tasks are idempotent: prints `already done {id}`, does **not**
  rewrite the store, and exits 0.

### rm

```bash
todo rm ID
```

- Removes the task with the given immutable id and prints `removed {id}`.
- Removing a task never reuses its id; the internal `next_id` counter only ever
  increases, so a deleted id is never handed out again.

## Exit codes

| Code | Meaning | Examples |
| ---- | ------- | -------- |
| 0 | OK | successful `add`/`list`/`done`/`rm`, already-done |
| 1 | Domain error | empty title, nonexistent id |
| 2 | Usage error | invalid `--due` date, invalid `--priority`, missing/invalid argument |
| 3 | Storage error | corrupt or schema-invalid store file |

Domain and storage errors print `error: {message}` to stderr. Usage errors are
produced by argument parsing; the process still returns exit code 2.

## Tests

```bash
python -m pytest tests/test_todo.py
```
