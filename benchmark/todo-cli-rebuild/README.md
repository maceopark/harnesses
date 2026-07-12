# todo-rebuild

Blind-rebuild arm of the todo CLI variation experiment.
Spec: `.ultimateinterview/todo-cli-app-2/handoff.md` (Part 1 is the contract).

## Commands

```
todo               show today's view
todo add <title>   add a pending item (empty/whitespace titles are rejected)
todo done <number> complete the pending item shown with that number
```

The default view lists every pending item (unfinished items carry over
automatically day to day) followed by items completed **today**, rendered
struck-through. Items completed on earlier days are hidden from the view but
never removed from the store.

## Store

One human-readable JSON file: `~/.todo-rebuild/todos.json`

```json
{"items": [{"title": "buy milk", "created": "2026-07-06", "done_at": null}]}
```

- `done_at` is `null` while pending, a local `YYYY-MM-DDTHH:MM:SS` stamp once
  completed (the date part drives day-boundary hiding; the time orders the
  "Done today" section).
- **Hand-editing the file is the sanctioned recovery path**: set `done_at`
  back to `null` to un-complete an item; remove an item object to delete it.
  The CLI deliberately has no un-complete or delete command.
- Multi-line titles are supported; JSON escaping round-trips any characters
  the shell passes.
- If the file cannot be parsed, every command reports the path and exits
  non-zero **without touching the file** — fix it by hand and rerun.

## Exit codes

`0` success · `1` unreadable/invalid store (file left untouched) · `2` usage
or input error (empty title, bad item number, unknown command).

## Experiment isolation

Do not install this onto your PATH while the experiment runs. Use the local
venv (`uv sync`, then `uv run todo`) with an overridden `HOME`, e.g.:

```bash
HOME=$(mktemp -d) uv run todo add "buy milk"
```

Tests do the same (`uv run pytest`); they never touch your real `$HOME`.
