# claudeplan

A minimal todo CLI with a single JSON store. Spec-benchmark arm built via plain
plan-mode elicitation (see the REQ list in the approved plan).

## Usage

```bash
uv sync

uv run todo add "Pay rent" --priority high --due 2026-07-10
uv run todo add "Buy milk"                 # priority defaults to medium
uv run todo list                           # open items: priority → due date → id
uv run todo list --all                     # include completed ([x])
uv run todo list --done                    # completed only
uv run todo list --priority high --overdue # filters AND together
uv run todo done 1
uv run todo delete 2
```

- Store: `~/.config/claudeplan/todos.json` (override with `$CLAUDEPLAN_HOME` or
  `$XDG_CONFIG_HOME`). Writes are atomic; a corrupt store is never overwritten.
- IDs are sequential and never reused after deletion.
- Exit codes: `0` success, `1` domain/data error (unknown id, already done,
  corrupt store), `2` usage error (bad flags, invalid date, empty title).

## Tests

```bash
uv run pytest -q
```
